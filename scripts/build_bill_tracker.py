"""One-off ingestion: build `data/bills.json` (issue #80).

Run by hand, not part of the daily pipeline — a Bill's stage changes on the
order of days during a sitting and not at all between sittings, and the
register offers no feed to poll for a diff.

## What is read from where

1. **Title, year, stage and stage date** — Parliament's own Bills register
   (`www.parlimen.gov.my/bills-dewan-rakyat.html?uweb=dr`), the same page
   `lpa.mp_profile`'s `bill_sponsors()` reads for a different purpose. Parsed
   by splitting on each `<tr class="maintable">` row rather than by
   flattening the page to text first: the register embeds every row's detail
   popup inline as a sibling `<div>`, and flattening scrambles which popup
   belongs to which row — this pipeline got that wrong once during
   development (two different Bills' tabling ministers swapped) before
   switching to a row-scoped parse. `_parse_register` is checked against
   this failure mode by `tests/test_bill_tracker.py`.
2. **The plain-language summary** — a verbatim excerpt of each Bill's own
   "HURAIAN" (Explanation) section, read from the Bill's own PDF (linked
   from the register). See `lpa.bill_tracker`'s module docstring for why
   this is a quote and not a paraphrase.
3. **Division result** — not fetched here at all. Where a Bill's Division
   already appears in `data/mp_profiles.json` (issue #78 read Hansard's full
   name lists and Chair-declared tallies for the 15th Parliament's ten
   Divisions), this script pulls the same tally by matching sitting date and
   subject — see `BILL_DIVISIONS`. A Bill with no recorded Division needs no
   new sourcing either: #78's ADR 0009 already established the complete list
   of the term's Divisions, so a Bill absent from `BILL_DIVISIONS` is known,
   not merely unchecked, to have passed on a voice vote.

## Scope

Pilot slice: four Bills, chosen because two have a real, already-verified
Division and two do not — enough to exercise both shapes of the schema.
Scaling to the full register is follow-up work under #80.
"""

from __future__ import annotations

import argparse
import io
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from lpa.scraper import RateLimiter, RobotsPolicy, new_client

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "bills.json"
MP_PROFILES_PATH = Path(__file__).resolve().parents[1] / "data" / "mp_profiles.json"

PARLIMEN = "https://www.parlimen.gov.my"
REGISTER_URL = f"{PARLIMEN}/bills-dewan-rakyat.html?uweb=dr"

# The pilot slice. Two have a real Division (see BILL_DIVISIONS below); two
# passed on a voice vote, confirmed by absence from #78's complete list of
# the term's ten Divisions rather than by a fresh check here.
BILLS = ("D.R.20/2026", "D.R.8/2026", "D.R.28/2025", "D.R. 5/2025")

# D.R. code -> the exact `subject` string of its Division in
# data/mp_profiles.json's P.102 profile, verified by hand against both the
# register's own dates (matching exactly) and a live fetch of the
# corresponding Hansard sitting on 2026-08-24.
BILL_DIVISIONS: dict[str, str] = {
    "D.R.28/2025": (
        "RANG INDANG-UNDANG > RANG UNDANG-UNDANG PEROLEHAN KERAJAAN 2025 "
        "Bacaan Kali Yang Kedua dan Ketiga"
    ),
    "D.R. 5/2025": (
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG PERLEMBAGAAN (PINDAAN) 2025 "
        "Bacaan Kali Yang Kedua dan Ketiga"
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
    return {row["code"]: row for row in (_parse_row(r) for r in rows) if row["code"]}


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
    pdf = re.search(r"loadResult\('([^']+\.pdf)'", row)

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
    """The date of a Bill's current stage: its most recent milestone."""
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

    url = f"{PARLIMEN}{pdf_path}"
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


def load_division_tallies(seat_code: str = "P.102") -> dict[str, dict[str, Any]]:
    """Every Division already shipped for `seat_code`, keyed by its subject.

    Reads the already-verified `data/mp_profiles.json` (#78) rather than
    Hansard directly — see the module docstring for why re-deriving these
    tallies here would risk the same fact disagreeing with itself in two
    files.
    """
    config = json.loads(MP_PROFILES_PATH.read_text())
    return {d["subject"]: d for d in config["profiles"][seat_code]["divisions"]}


def build_bill(row: dict[str, Any], summary: str, summary_url: str, division: dict[str, Any] | None) -> dict[str, Any]:
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
        entry["unverified"] = {
            "division": (
                "Not among the 15th Parliament's ten recorded Divisions (see "
                "data/mp_profiles.json and ADR 0009) — this Bill passed on a voice "
                "vote, which Hansard records as a decision with no individual "
                "position taken."
            )
        }
    return entry


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
        for code in BILLS:
            if code not in register:
                raise ValueError(f"{code} is not on the register's default view")
            row = register[code]
            pdf_url = f"{PARLIMEN}{row['pdf_path']}"
            if not robots.is_allowed(pdf_url):
                raise SystemExit(f"robots.txt disallows {pdf_url}: {robots.refusal_reason(pdf_url)}")
            limiter.wait_turn(pdf_url, robots.crawl_delay(pdf_url))
            summary, summary_url = fetch_summary(client, row["pdf_path"])

            division = None
            if code in BILL_DIVISIONS:
                division = divisions_by_subject.get(BILL_DIVISIONS[code])
                if division is None:
                    raise ValueError(
                        f"{code}: BILL_DIVISIONS names a subject not found in "
                        f"{MP_PROFILES_PATH} — the curated mapping may be stale"
                    )

            bills[code] = build_bill(row, summary, summary_url, division)

    output = {
        "_comment": [
            "Bills tracked on the homepage's bill tracker (issue #80). Pilot",
            "slice: four Bills — see scripts/build_bill_tracker.py, which",
            "generated this file, and ADR 0010 for the method. `stage` is",
            "Parliament's own status label, not a translated or invented one;",
            "`summary` is a verbatim excerpt of the Bill's own explanatory",
            "statement, not this pipeline's paraphrase.",
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

    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(bills)} Bills to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
