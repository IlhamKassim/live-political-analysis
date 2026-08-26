"""Ingestion: build `data/bills.json` (issues #80, #106).

Run by hand, not part of the daily pipeline — a Bill's stage changes on the
order of days during a sitting and not at all between sittings, and the
register offers no feed to poll for a diff. #106 scaled this from #80's
four-Bill pilot to the register's full default view (below) but kept the
manual cadence: the failure mode here is a page layout change, a PDF whose
HURAIAN section can't be cleanly excerpted, or a Division that can be named
but not dated (see `AMBIGUOUS_DIVISIONS`) — all things worth a human glancing
at the run's printed skip list before `data/bills.json` ships, not something
a cron job should paper over by shipping whatever it got. See ADR 0010's
Consequences for this call.

## What is read from where

1. **Title, year, stage and stage date** — Parliament's own Bills register
   (`www.parlimen.gov.my/bills-dewan-rakyat.html?uweb=dr`), the same page
   `scripts/build_mp_profiles.py`'s `bill_sponsors()` reads for a different
   purpose. Parsed by splitting on each `<tr class="maintable">` row rather
   than by flattening the page to text first: the register embeds every
   row's detail popup inline as a sibling `<div>`, and flattening scrambles
   which popup belongs to which row — this pipeline got that wrong once
   during development (two different Bills' tabling ministers swapped)
   before switching to a row-scoped parse. `parse_register` is checked
   against this failure mode by `tests/test_bill_tracker.py`.
2. **The plain-language summary** — a verbatim excerpt of each Bill's own
   "HURAIAN" (Explanation) section, read from the Bill's own PDF (linked
   from the register). See `lpa.bill_tracker`'s module docstring for why
   this is a quote and not a paraphrase. A Bill whose PDF has no extractable
   HURAIAN (a scanned image, most often) is skipped rather than shipped with
   an invented summary — printed in the run's skip list, not silently
   dropped.
3. **Division result** — not fetched here at all. Where a Bill's Division
   already appears in `data/mp_profiles.json` (issue #78 read Hansard's full
   name lists and Chair-declared tallies for the 15th Parliament's ten
   Divisions), this script pulls the same tally by matching sitting date and
   subject — see `BILL_DIVISIONS`. A Bill with no recorded Division needs no
   new sourcing either: #78's ADR 0009 already established the complete list
   of the term's Divisions, so a Bill absent from `BILL_DIVISIONS` is known,
   not merely unchecked, to have passed on a voice vote — except a Bill
   named in `AMBIGUOUS_DIVISIONS`, whose title matches one of the ten but
   whose date does not; see that dict for why matching stops there rather
   than forcing an attachment.

## Scope

The register's full default view — everything `fetch_register` returns,
which as of #106 is Bills from 2024 into 2026; the register offers no way
to page further back, and #80's ADR 0010 already flagged going past that
default view as untested. Not every Bill in that view makes it into
`data/bills.json`: a Bill whose PDF yields no HURAIAN excerpt is skipped
(see point 2 above) rather than shipped with a placeholder.
"""

from __future__ import annotations

import argparse
import io
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from lpa.scraper import RateLimiter, RobotsPolicy, new_client

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "bills.json"
MP_PROFILES_PATH = Path(__file__).resolve().parents[1] / "data" / "mp_profiles.json"

PARLIMEN = "https://www.parlimen.gov.my"
REGISTER_URL = f"{PARLIMEN}/bills-dewan-rakyat.html?uweb=dr"

# D.R. code -> the exact `subject` string of its Division in
# data/mp_profiles.json's P.102 profile, verified by hand against both the
# register's own dates (matching exactly) and a live fetch of the
# corresponding Hansard sitting. Of P.102's ten recorded Divisions (#78's ADR
# 0009), only four name a Bill title that appears anywhere in the register's
# current default view at all (the other six are 2023-2024 events the
# register's default view no longer lists) — and of those four, only three
# have a stage date that agrees with the Division's own sitting date; see
# AMBIGUOUS_DIVISIONS for the fourth (D.R.30/2025).
BILL_DIVISIONS: dict[str, str] = {
    "D.R.28/2025": (
        "RANG INDANG-UNDANG > RANG UNDANG-UNDANG PEROLEHAN KERAJAAN 2025 "
        "Bacaan Kali Yang Kedua dan Ketiga"
    ),
    "D.R. 5/2025": (
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG PERLEMBAGAAN (PINDAAN) 2025 "
        "Bacaan Kali Yang Kedua dan Ketiga"
    ),
    "D.R.4/2026": (
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG PERLEMBAGAAN (PINDAAN) 2026 "
        "Bacaan Kali Yang Kedua"
    ),
}

# D.R. code -> why this Bill's Division is known but not attached. Added by
# #106: this Bill's title is an exact, unambiguous match for one of P.102's
# ten recorded Divisions (data/mp_profiles.json), but the register's own
# "Bacaan Kedua Pada" date (01/12/2025) does not agree with that Division's
# sitting date (2025-11-04) the way BILL_DIVISIONS' three entries do —
# Budget bills run an extended second-reading debate, and the vote that
# closes debate is not always the date the register records for "Bacaan
# Kedua". Recording the disagreement rather than guessing which date is
# right, and rather than defaulting to "passed on a voice vote", which the
# real Division record shows is false for this Bill.
AMBIGUOUS_DIVISIONS: dict[str, str] = {
    "D.R.30/2025": (
        "A Division exists for this Bill's second reading (data/mp_profiles.json, "
        "P.102, sitting 2025-11-04, subject \"RANG UNDANG-UNDANG PERBEKALAN 2026 "
        "Bacaan Kali Yang Kedua\") but is not attached here: the Bills register "
        "gives this Bill's own \"Bacaan Kedua Pada\" as 01/12/2025, not 2025-11-04, "
        "and this pipeline will not attach a Division to a Bill whose own stage "
        "date disagrees with the Division's sitting date. Needs a fresh Hansard "
        "check to resolve which date is right, not a guess."
    ),
}

_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def fetch_register(client: httpx.Client) -> dict[str, dict[str, Any]]:
    """Every Bill on the register's default view, by D.R. code."""
    html = client.get(REGISTER_URL).raise_for_status().text
    return parse_register(html)


def parse_register(html: str) -> dict[str, dict[str, Any]]:
    """Parse the register's HTML into Bills, by D.R. code. Pure — no network.

    Parsed row by row rather than from text flattened across the whole page:
    the register embeds each row's detail popup as a sibling `<div>` rather
    than nested inside the row's own cell, so flattening a page like this
    into text interleaves one row's popup with an adjacent row's cells in a
    way that reads as coherent prose. An earlier version of this function
    did exactly that and misattributed a Bill's tabling Minister and passage
    date to a different Bill nearby in the file — `tests/test_bill_tracker.py`
    reproduces the fixture shape that caused it.
    """
    rows = re.split(r'<tr class="maintable">', html)[1:]
    if not rows:
        raise ValueError("no Bill rows parsed from the register — its markup may have changed")
    parsed = [_parse_row(r) for r in rows]
    bills = {row["code"]: row for row in parsed if row["code"]}
    for code, row in bills.items():
        missing = [
            field
            for field in ("year", "title", "status", "pdf_path")
            if row[field] is None
        ]
        if missing:
            raise ValueError(
                f"{code}: could not parse {', '.join(missing)} from its register row — "
                "the markup may have changed"
            )
    return bills


def _parse_row(row: str) -> dict[str, Any]:
    def field(label: str) -> str | None:
        match = re.search(
            re.escape(label) + r"</td>\s*<td[^>]*>\s*:\s*</td>\s*<td[^>]*>\s*(.*?)\s*</td>",
            row,
            re.S,
        )
        return _clean(match.group(1)) if match else None

    code = re.search(r">\s*(D\.R\.\s*\d+/\d{4})\s*<", row)
    year = re.search(r'<td align="center" class="maintd">\s*(\d{4})\s*</td>', row)
    title = re.search(r'<td class="maintd">\s*([^<]+?)\s*(?:<|$)', row)
    status = re.search(r'class="parent ruustatus\d+" id="row\d+">([^<]+)<', row)
    # Case-insensitive: at least one row on the live register links a ".PDF"
    # (a Windows 8.3 short filename, "RUULAN~1.PDF") rather than ".pdf".
    pdf = re.search(r"loadResult\('([^']+\.pdf)'", row, re.IGNORECASE)

    return {
        "code": _clean(code.group(1)) if code else None,
        "year": int(year.group(1)) if year else None,
        "title": _clean(title.group(1)) if title else None,
        "status": _clean(status.group(1)) if status else None,
        "first_reading": field("Bacaan Pertama Pada"),
        "second_reading": field("Bacaan Kedua Pada"),
        "referred_jkpk": field("Dirujuk JKPK Pada"),
        "passed": field("Diluluskan Pada"),
        "pdf_path": pdf.group(1) if pdf else None,
    }


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: str | None) -> date | None:
    """A register date, "DD/MM/YYYY", or `None` for "-" or an empty cell."""
    if not raw:
        return None
    match = _DATE.search(raw)
    return datetime.strptime(match.group(0), "%d/%m/%Y").date() if match else None


def stage_date(row: dict[str, Any]) -> date:
    """The date of a Bill's current stage.

    Takes the first of (passed, referred to JKPK, second reading, first
    reading) that has a date — a fixed priority order, not a computed
    maximum. The two agree for every ordinary path a Bill takes, where each
    milestone strictly follows the last; they could disagree for a Bill
    referred to a Special Select Committee *after* a second reading. #106
    checked this against all 67 Bills the register's default view carried at
    the time (each field's presence and chronological order against the
    others, keyed to each row's own status label) and found no such case,
    but this function still does not claim to handle one correctly should
    the register's contents change to include one.
    """
    for key in ("passed", "referred_jkpk", "second_reading", "first_reading"):
        parsed = _parse_date(row[key])
        if parsed is not None:
            return parsed
    raise ValueError(f"{row['code']}: no reading date of any kind — the row may be malformed")


def fetch_summary(client: httpx.Client, pdf_path: str) -> tuple[str, str]:
    """A verbatim excerpt of a Bill's "HURAIAN" opening, and its source URL.

    Takes the first sentence containing "bertujuan" ("is intended to") —
    the substantive purpose clause — rather than always the section's
    literal first sentence: some Bills open HURAIAN with a sentence about
    their constitutional basis instead (a citation to the Ninth Schedule,
    for example), and that is not what a reader wants from a plain-language
    line. Falls back to the literal first sentence if none contains it,
    since that is still a verbatim excerpt even if less on point. Internal
    line breaks are collapsed to spaces — the PDF's own line wrapping, not
    part of the sentence — the same mechanical cleanup `_clean` applies to
    every register field, never a change to a word.

    Imports `pypdf` locally rather than at module level: it is declared
    under the `bills` extra (`pip install -e ".[bills]"`), not this
    project's core or `dev` dependencies, since nothing but this one
    function needs it. A module-level import would make every other
    function here — including `parse_register`, which
    `tests/test_bill_tracker.py` imports and runs without any network
    access or optional dependency — fail to import in an environment that
    never installed it, which is exactly the CI environment this repo
    actually tests in.
    """
    import pypdf

    url = f"{PARLIMEN}{quote(pdf_path)}"
    response = client.get(url)
    response.raise_for_status()
    reader = pypdf.PdfReader(io.BytesIO(response.content))
    for index, page in enumerate(reader.pages):
        text = page.extract_text()
        if "HURAIAN" not in text:
            continue
        body = text.split("HURAIAN", 1)[1].strip()
        sentences = [s.strip() for s in re.split(r"(?<=[.])\s+", body) if s.strip()]
        if not sentences:
            raise ValueError(f"{pdf_path}: found HURAIAN but no sentence after it")
        sentence = next((s for s in sentences if "bertujuan" in s.lower()), sentences[0])
        return _clean(sentence), f"{url}#page={index + 1}"
    raise ValueError(
        f"{pdf_path}: no HURAIAN section found — the Bill's PDF may be laid out differently"
    )


def load_division_tallies() -> dict[str, dict[str, Any]]:
    """Every Division already shipped for P.102, keyed by its subject.

    P.102 Bangi, and any Seat would do since #105 populated most of the
    House: a Division's tallies are the Chair's declared result, the same
    four numbers on every Member's copy of it, so this reads one Seat rather
    than reconciling 199. Reads the already-verified
    `data/mp_profiles.json` rather than Hansard directly, since re-deriving
    these tallies here would risk the same fact disagreeing with itself in
    two files (see the module docstring). Bangi is hardcoded because it is
    the Seat with a complete voting record that this repo has quoted from
    the start; three Seats' records are one Division short (see ADR 0009)
    and picking one of those would lose a Bill its Division.
    """
    config = json.loads(MP_PROFILES_PATH.read_text())
    return {d["subject"]: d for d in config["profiles"]["P.102"]["divisions"]}


def build_bill(
    code: str, row: dict[str, Any], summary: str, summary_url: str, division: dict[str, Any] | None
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "title": row["title"],
        "year": row["year"],
        "stage": row["status"],
        "stage_date": stage_date(row).isoformat(),
        "summary": summary,
        "summary_source_url": summary_url,
    }
    if division is not None:
        entry["division"] = {
            "sitting_date": division["sitting_date"],
            "ayes": division["ayes"],
            "noes": division["noes"],
            "abstentions": division["abstentions"],
            "absent": division["absent"],
            "outcome": division["outcome"],
            "hansard_url": division["hansard_url"],
        }
        entry["unverified"] = {}
    else:
        entry["division"] = None
        entry["unverified"] = {"division": _no_division_reason(code, row)}
    return entry


def _no_division_reason(code: str, row: dict[str, Any]) -> str:
    """Why this Bill has no Division — checked against its actual stage.

    A Bill only reaches a vote once it is read a second time, so "passed on
    a voice vote" is true only when it has, in fact, passed; a Bill still
    awaiting a second reading or sitting with a Special Select Committee
    (JKPK) has not reached a point where a Division could have happened at
    all, and saying otherwise would be exactly the false-blank failure this
    pipeline's `unverified` discipline exists to prevent.

    Checks `AMBIGUOUS_DIVISIONS` first: a Bill named there does have a real
    Division (its title is an unambiguous match), just not one this pipeline
    will attach without a date it can confirm — "passed on a voice vote"
    would be false for a Bill that in fact went to a Division, so that
    default is skipped for exactly this case.
    """
    if code in AMBIGUOUS_DIVISIONS:
        return AMBIGUOUS_DIVISIONS[code]
    if row["status"] == "Lulus":
        return (
            "Not among the 15th Parliament's ten recorded Divisions (see "
            "data/mp_profiles.json and ADR 0009) — this Bill passed on a voice "
            "vote, which Hansard records as a decision with no individual "
            "position taken."
        )
    return (
        f'Still at the "{row["status"]}" stage per the Bills register — no vote has '
        "been put to the House on this Bill yet, so there is no Division to have "
        "or not have."
    )


def _fetch_summary_resilient(client: httpx.Client, pdf_path: str) -> tuple[str, str]:
    """`fetch_summary`, retried once on a transient transport failure.

    A sequence of ~70 requests to one host over a couple of minutes hits the
    occasional dropped connection that has nothing to do with the Bill's own
    PDF — a `RemoteProtocolError` was seen mid-run during #106's own scrape.
    Retrying once turns that into a non-event; a `ValueError` (no HURAIAN
    section found) is not retried, since it is a real finding about the
    PDF's own layout that a second fetch will not change.
    """
    try:
        return fetch_summary(client, pdf_path)
    except httpx.HTTPError:
        return fetch_summary(client, pdf_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    limiter = RateLimiter()
    with new_client() as client:
        robots = RobotsPolicy(client=client, limiter=limiter)
        if not robots.is_allowed(REGISTER_URL):
            raise SystemExit(f"robots.txt disallows {REGISTER_URL}: {robots.refusal_reason(REGISTER_URL)}")

        limiter.wait_turn(REGISTER_URL, robots.crawl_delay(REGISTER_URL))
        register = fetch_register(client)

        divisions_by_subject = load_division_tallies()

        bills: dict[str, Any] = {}
        skipped: list[str] = []
        for code, row in register.items():
            pdf_url = f"{PARLIMEN}{quote(row['pdf_path'])}"
            if not robots.is_allowed(pdf_url):
                skipped.append(f"{code}: robots.txt disallows {pdf_url}: {robots.refusal_reason(pdf_url)}")
                continue
            limiter.wait_turn(pdf_url, robots.crawl_delay(pdf_url))
            try:
                summary, summary_url = _fetch_summary_resilient(client, row["pdf_path"])
            except httpx.HTTPError as error:
                skipped.append(f"{code}: fetch failed after retry: {type(error).__name__}: {error}")
                continue
            except ValueError as error:
                skipped.append(f"{code}: {error}")
                continue

            division = None
            if code in BILL_DIVISIONS:
                division = divisions_by_subject.get(BILL_DIVISIONS[code])
                if division is None:
                    raise ValueError(
                        f"{code}: BILL_DIVISIONS names a subject not found in "
                        f"{MP_PROFILES_PATH} — the curated mapping may be stale"
                    )

            bills[code] = build_bill(code, row, summary, summary_url, division)

    output = {
        "_comment": [
            "Bills tracked on the homepage's bill tracker (issues #80, #106).",
            "See scripts/build_bill_tracker.py, which generated this file, and",
            "ADR 0010 for the method. `stage` is Parliament's own status label,",
            "not a translated or invented one; `summary` is a verbatim excerpt",
            "of the Bill's own explanatory statement, not this pipeline's",
            "paraphrase. Covers the Bills register's full default view as of",
            "`_source.retrieved`, minus any Bill whose PDF yielded no clean",
            "HURAIAN excerpt — see the run's own printed skip list, not",
            "recorded in this file, for which and why.",
        ],
        "_source": {
            "register": {
                "name": "Parlimen Malaysia — Rang Undang-Undang (Bills) register",
                "url": REGISTER_URL,
            },
            "summaries": {
                "name": "Each Bill's own PDF, \"HURAIAN\" (Explanation) section",
            },
            "division_data": {
                "name": "This repo's own data/mp_profiles.json (issue #78)",
                "note": "Not re-fetched from Hansard — see the module docstring.",
            },
            "retrieved": date.today().isoformat(),
            "generated_by": "scripts/build_bill_tracker.py",
        },
        "bills": bills,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for reason in skipped:
        print(f"skipped {reason}")
    print(f"wrote {len(bills)} Bills to {OUTPUT_PATH} ({len(skipped)} skipped)")


if __name__ == "__main__":
    main()
