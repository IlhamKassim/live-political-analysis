"""One-off ingestion: build `data/mp_profiles.json` (issue #78).

Run by hand, not part of the daily pipeline. A Member's contact details, a
term's Divisions and a GE15 result all change on the order of months or
years, and none of the three sources publishes a feed to poll for a diff.

## What is read from where

1. **Identity and contact** — `parlimen.gov.my`'s own Members directory and
   the per-Member profile page behind it. This is Parliament stating who
   holds a Seat and how to reach them, and it is the only official source
   for either.
2. **GE15 result** — Thevesh Theva's Malaysian election dataset, already the
   Baseline Loader's source (`lpa.sources`), at candidate level plus the
   Election Commission's own per-Seat turnout and elector counts. Fetched
   here rather than read back out of Storage so this script has no database
   dependency, and cross-checked against itself: the candidates' votes must
   reconcile with the official ballot accounting.
3. **Voting record** — the Digital Hansard portal (`hansard.parlimen.gov.my`),
   Parliament's own full-text Hansard, which prints each Division's four
   name lists as structured sections. Every sitting of the term is fetched
   and searched; see `_divisions_in_sitting`.

## Why the tallies are curated and the votes are not

A Member's position is read from the primary source and never curated: the
script finds the Division's *Ahli-Ahli Yang Bersetuju / Tidak Bersetuju /
Tidak Mengundi / Tidak Hadir* sections and looks for the Seat's name in
them, and it fails if the Seat appears in none or in more than one.

The *tallies*, by contrast, live in `DECLARED_RESULTS` below, transcribed by
hand from the Chair's spoken declaration. That declaration is free prose,
phrased differently every time ("Yang tidak mengundi ― seorang", "Tetapi
bersetuju― 146", "Ahli yang tidak hadir mengundi – 14 undi"), and a parser
that guessed at it would fail silently on the next new phrasing. The
transcription is checked rather than trusted: the four numbers must very
nearly account for the whole House (`MAX_UNACCOUNTED`), and each must land
within `LIST_TOLERANCE` of the number of names Hansard actually lists in
that section.

That tolerance is not slack for a bad transcription — it is the gap between
the two, which is real. Hansard's name lists carry transcription artefacts
(a name run together with the next, a missing entry) that the Chair's
declared count does not, so the declaration is the authority and the lists
are the corroboration. A disagreement wider than a handful of names means
something is genuinely wrong, and the script stops.

A Division found in Hansard that `DECLARED_RESULTS` does not cover is also a
failure, not a skip — otherwise the next sitting's vote would quietly go
missing from a record that claims to be complete.

## Scope

Pilot slice: P.102 Bangi only, the Seat #76's postcode index also pilots.
The shape scales to all 222 — nothing below is Bangi-specific except
`SEATS` — but the curation step above does not, and extending it means
transcribing each new Division's declared result once. Follow-up work under
#78 rather than done here.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from lpa.mp_profile import TOTAL_SEATS

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "mp_profiles.json"

PARLIMEN = "https://www.parlimen.gov.my"
MEMBERS_URL = f"{PARLIMEN}/ahli-dewan.html?uweb=dr"
BILLS_URL = f"{PARLIMEN}/bills-dewan-rakyat.html?uweb=dr"
HANSARD = "https://hansard.parlimen.gov.my"
CATALOGUE_URL = f"{HANSARD}/katalog/dewan-rakyat"

ELECTION_DATA_BASE = "https://raw.githubusercontent.com/Thevesh/analysis-election-msia/main/data"
GE15_CANDIDATES_URL = f"{ELECTION_DATA_BASE}/candidates_ge15.csv"
GE15_RESULTS_URL = f"{ELECTION_DATA_BASE}/results_parlimen_ge15.csv"

TERM = "15"
"""The Parliament whose record is ingested. Members and Divisions both belong
to a term; a profile that mixed two would attribute a predecessor's votes."""

SEATS = ("P.102",)
"""The Seats to build profiles for. The pilot slice — see the module docstring."""

LIST_TOLERANCE = 6
"""How far a Hansard name list may differ from the Chair's declared count.

Two things move the two apart by a name or three, neither of them an error.
The lists run to hundreds of entries and carry transcription artefacts — a
name run together with the one before it, a missing bracket. And where a
Bill is read a second and a third time in the same sitting the House divides
twice under one heading, so the lists gathered here are the union of both
votes while the declared count belongs to one of them: the handful of
Members who arrived or left between the two show up in the difference.

Anything wider is a misread section, not noise, and stops the build.
"""

MAX_UNACCOUNTED = 3
"""How many of the 222 Seats a declared result may leave out entirely.

Not every Division accounts for the whole House: a Seat can be vacant, and a
Member serving a suspension is barred from voting and named in no list. Two
of this term's ten Divisions come to 221 for those reasons. A wider gap
means a whole category was missed in transcription.
"""

# Division heading -> the position it records. Hansard prints these four as
# structured sections after each Division, and together they name all 222
# Members, which is what makes a per-Member voting record possible at all.
VOTE_SECTIONS = {
    "ahli-ahli yang bersetuju:": "aye",
    "ahli-ahli yang tidak bersetuju:": "no",
    "ahli-ahli yang tidak mengundi:": "abstain",
    "ahli-ahli yang tidak hadir:": "absent",
}

# Position -> the `DECLARED_RESULTS` key holding its count, which is also the
# field name on `lpa.mp_profile.Division`.
TALLY_KEYS = {"aye": "ayes", "no": "noes", "abstain": "abstentions", "absent": "absent"}

# (sitting date, Hansard heading) -> the Chair's declared result, transcribed
# by hand from the sitting's Hansard. `ayes`/`noes`/`abstentions`/`absent`
# are the numbers announced to the House; `outcome` is what the Chair
# declared them to have decided. Verified against the linked Hansard on
# 2026-08-24. See the module docstring for why this is curated.
DECLARED_RESULTS: dict[tuple[str, str], dict[str, Any]] = {
    (
        "2023-05-25",
        "USUL > WAKTU MESYUARAT DAN URUSAN DIBEBASKAN DARIPADA PERATURAN MESYUARAT",
    ): {
        "ayes": 83,
        "noes": 52,
        "abstentions": 1,
        "absent": 86,
        "outcome": "Usul dipersetujui",
    },
    (
        "2024-06-26",
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG SURUHANJAYA PENERBANGAN MALAYSIA "
        "(PEMBUBARAN) 2024 Bacaan Kali Yang Kedua dan Ketiga",
    ): {
        "ayes": 93,
        "noes": 63,
        "abstentions": 0,
        "absent": 66,
        "outcome": "Dibacakan kali kedua",
    },
    (
        "2024-07-18",
        "USUL USUL MENTERI DI JABATAN PERDANA MENTERI DI BAWAH P.M. 27(3) > "
        "Penggantungan YB Machang Daripada Perkhidmatan Majlis Mesyuarat dan "
        "Jawatankuasa Pilihan Selama Enam (6) Bulan",
    ): {
        "ayes": 110,
        "noes": 63,
        "abstentions": 3,
        "absent": 46,
        "outcome": "Usul dipersetujui",
    },
    (
        "2024-10-17",
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG PERLEMBAGAAN (PINDAAN) 2024 "
        "Bacaan Kali Yang Kedua dan Ketiga",
    ): {
        # 221, not 222: the Chair noted one Member could not vote, being
        # under the suspension agreed on 18 July 2024.
        "ayes": 206,
        "noes": 1,
        "abstentions": 0,
        "absent": 14,
        "outcome": "Melepasi dua pertiga; dibacakan kali kedua dan ketiga",
    },
    (
        "2024-12-09",
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG KOMUNIKASI DAN MULTIMEDIA "
        "(PINDAAN) 2024 Bacaan Kali Yang Kedua dan Ketiga",
    ): {
        "ayes": 59,
        "noes": 40,
        "abstentions": 1,
        "absent": 122,
        "outcome": "Dibacakan kali kedua dan ketiga",
    },
    (
        "2024-12-11",
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG KESELAMATAN DALAM TALIAN 2024 "
        "Bacaan Kali Yang Kedua dan Ketiga",
    ): {
        "ayes": 77,
        "noes": 55,
        "abstentions": 0,
        "absent": 90,
        "outcome": "Dibacakan kali kedua dan ketiga",
    },
    (
        "2025-03-04",
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG PERLEMBAGAAN (PINDAAN) 2025 "
        "Bacaan Kali Yang Kedua dan Ketiga",
    ): {
        "ayes": 148,
        "noes": 0,
        "abstentions": 57,
        "absent": 17,
        "outcome": "Melepasi dua pertiga; dibacakan kali ketiga dan diluluskan",
    },
    (
        "2025-08-28",
        "RANG INDANG-UNDANG > RANG UNDANG-UNDANG PEROLEHAN KERAJAAN 2025 "
        "Bacaan Kali Yang Kedua dan Ketiga",
    ): {
        # 221, not 222: the Chair declared these four numbers and gave no
        # reason for the shortfall. Recorded as announced rather than
        # adjusted to fit — see `lpa.mp_profile.Division.members_accounted`.
        "ayes": 125,
        "noes": 63,
        "abstentions": 1,
        "absent": 32,
        "outcome": "Dibacakan kali kedua",
    },
    (
        "2025-11-04",
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG PERBEKALAN 2026 Bacaan Kali "
        "Yang Kedua DAN USUL ANGGARAN PEMBANGUNAN 2026",
    ): {
        "ayes": 120,
        "noes": 67,
        "abstentions": 0,
        "absent": 35,
        "outcome": "Dibacakan kali kedua",
    },
    (
        "2026-03-02",
        "RANG UNDANG-UNDANG > RANG UNDANG-UNDANG PERLEMBAGAAN (PINDAAN) 2026 "
        "Bacaan Kali Yang Kedua",
    ): {
        "ayes": 146,
        "noes": 0,
        "abstentions": 44,
        "absent": 32,
        "outcome": "Kurang daripada dua pertiga majoriti; tidak diluluskan",
    },
}

# Why each optional field on the pilot's profile is unset. Every entry is a
# statement about what was checked, not a note to fill this in later — see
# `lpa.mp_profile.MPProfile.unverified` and ADR 0009.
UNVERIFIED: dict[str, str] = {
    "party": (
        "No source consulted states the component party. Parliament's Members "
        "directory publishes the Coalition ('PH') in its Parti field, and the "
        "Election Commission's GE15 record gives the ballot line, which is also "
        "the Coalition — component parties contested GE15 under their "
        "Coalition's registered logo."
    ),
    "attendance": (
        "Nobody publishes it. Parliament's Digital Hansard has a per-Member "
        "attendance page (hansard.parlimen.gov.my/kehadiran/dewan-rakyat) but it "
        "returns HTTP 500 and is absent from the site's own navigation, so the "
        "feature is built and not released. Hansard names who was absent from a "
        "Division, which is not the same thing and must not be presented as it."
    ),
    "contact.opening_hours": (
        "Parliament publishes no service-centre hours for any Member; its "
        "profile page carries address, telephone, fax and email only."
    ),
}

_SEAT_LABEL = re.compile(r"^(P\.\d+)\s+(.*)$")
_LIST_ENTRY = re.compile(r"\d{1,3}\.\s+[^()]{5,120}\(([^()]{2,50})\)")


def fetch_csv(client: httpx.Client, url: str) -> list[dict[str, str]]:
    text = _get(client, url).text
    return list(csv.DictReader(io.StringIO(text)))


def _next_payload(client: httpx.Client, url: str) -> Any:
    """The whole Next.js payload embedded in a Digital Hansard page.

    The portal renders server-side and exposes no API, so its own embedded
    payload is the structured form of what it displays — the same data the
    page shows, not a scrape of the rendered HTML.
    """
    html = _get(client, url).text
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise ValueError(f"no Next.js payload at {url} — the portal's markup may have changed")
    return json.loads(match.group(1))


def _next_data(client: httpx.Client, url: str) -> Any:
    """The page props behind a Digital Hansard page."""
    payload: Any = _next_payload(client, url)["props"]["pageProps"]
    return payload


def _get(client: httpx.Client, url: str, attempts: int = 4) -> httpx.Response:
    """Fetch `url`, retrying a timeout or a 5xx with a widening pause.

    The sweep below makes a request per sitting day of the term, and over a
    few hundred of them the portal will stall on one or two. Without this the
    whole build is lost to a single slow response near the end.
    """
    for attempt in range(attempts):
        try:
            return client.get(url).raise_for_status()
        except (httpx.TimeoutException, httpx.HTTPStatusError) as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if attempt == attempts - 1 or (status is not None and status < 500):
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _sitting_props(client: httpx.Client, build: tuple[str, str], sitting: str) -> Any:
    """One sitting's Hansard, from the portal's own data endpoint.

    The same payload the page embeds, fetched without the surrounding markup
    — roughly a third of the bytes, which over a whole term's sittings is the
    difference between a courteous fetch and hammering Parliament's server.
    Falls back to the page itself if the portal redeploys mid-sweep and the
    build id in the URL goes stale.
    """
    build_id, locale = build
    page = f"{HANSARD}/hansard/dewan-rakyat/{sitting}"
    url = f"{HANSARD}/_next/data/{build_id}/{locale}/hansard/dewan-rakyat/{sitting}.json"
    try:
        return json.loads(_get(client, f"{url}?date={sitting}").text)["pageProps"]
    except (httpx.HTTPStatusError, KeyError, json.JSONDecodeError):
        return _next_data(client, page)


def portal_build(client: httpx.Client) -> tuple[str, str]:
    """The portal's current build id and locale, for its data endpoint.

    Both are read live rather than pinned: the build id changes with every
    deploy, so a hard-coded one would work until it silently didn't.
    """
    payload = _next_payload(client, HANSARD)
    return payload["buildId"], payload.get("locale", "ms-MY")


def fetch_members(client: httpx.Client) -> dict[str, dict[str, str]]:
    """Seat code -> the sitting Member's name and directory profile URL.

    Parliament writes a Seat as "P102" in this listing and "P.102" everywhere
    else, including its own profile pages; normalised here so a caller never
    has to know which spelling it is holding.
    """
    html = _get(client, MEMBERS_URL).text
    members = {}
    for block in re.findall(r"<li>.*?</li>", html, re.S):
        href = re.search(r'href="(profile-ahli\.html\?[^"]+)"', block)
        name = re.search(r'<span class="first-name">([^<]+)</span>', block)
        seat = re.search(r'<div class="constituency">(P\d+)</div>', block)
        if not (href and name and seat):
            continue
        code = f"P.{seat.group(1)[1:]}"
        members[code] = {
            "name": name.group(1).strip(),
            "profile_url": f"{PARLIMEN}/{href.group(1).replace('&amp;', '&')}",
        }
    if not members:
        raise ValueError(f"no Members parsed from {MEMBERS_URL} — its markup may have changed")
    return members


def fetch_member_details(client: httpx.Client, profile_url: str) -> dict[str, str]:
    """The labelled fields on a Member's own page in Parliament's directory.

    Returned as the page's own Malay labels ("No. Telefon", "Alamat
    Surat-menyurat"), lower-cased, so a label Parliament adds later shows up
    rather than being silently dropped by a fixed field list. A field the
    page renders as "-" is omitted: that is the page saying it has none.
    """
    html = _get(client, profile_url).text
    body = re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.S | re.I)
    cells = [re.sub(r"\s+", " ", c).strip() for c in re.split(r"<[^>]+>", body)]
    cells = [c for c in cells if c]
    details = {}
    for label, value in zip(cells, cells[1:], strict=False):
        key = label.rstrip(":").strip().lower()
        if key in {
            "nama",
            "parti",
            "parlimen",
            "kawasan",
            "negeri",
            "no. telefon",
            "no. faks",
            "email",
            "alamat surat-menyurat",
        } and value not in {"-", ""}:
            details.setdefault(key, value)
    return details


def ge15_result(
    candidates: Sequence[Mapping[str, str]],
    results: Sequence[Mapping[str, str]],
    seat_code: str,
) -> tuple[dict[str, Any], str, str]:
    """The winning candidate's GE15 result for one Seat, and who won it.

    Returns `(result fields, winner's name, ballot party)`.

    The two files are reconciled rather than merged on trust. The Election
    Commission's ballot accounting (`undi_dalam_peti` less `undi_tolak`) must
    equal the votes the candidate rows add up to; if it does not, one of the
    two has changed shape upstream and every figure derived from them is
    suspect, which is worth stopping for rather than publishing.
    """
    rows = [c for c in candidates if _split_seat(c["parlimen"])[0] == seat_code]
    if not rows:
        raise ValueError(f"no GE15 candidates for {seat_code}")
    summary = next((r for r in results if _split_seat(r["parlimen"])[0] == seat_code), None)
    if summary is None:
        raise ValueError(f"no GE15 result row for {seat_code}")

    by_votes = sorted(rows, key=lambda r: -int(r["votes"]))
    winner, runner_up = by_votes[0], by_votes[1]
    valid_votes = sum(int(r["votes"]) for r in rows)

    accounted = int(summary["undi_dalam_peti"]) - int(summary["undi_tolak"])
    if accounted != valid_votes:
        raise ValueError(
            f"{seat_code}: the Election Commission's ballot accounting gives "
            f"{accounted} valid votes but the candidate rows add up to {valid_votes}. "
            "One of the two upstream files has changed shape."
        )
    majority = int(winner["votes"]) - int(runner_up["votes"])
    if majority != int(summary["majoriti"]):
        raise ValueError(
            f"{seat_code}: computed a majority of {majority}, but the official "
            f"result states {summary['majoriti']}."
        )

    return (
        {
            "votes": int(winner["votes"]),
            "majority": majority,
            "vote_share": int(winner["votes"]) / valid_votes,
            "valid_votes": valid_votes,
            "runner_up_votes": int(runner_up["votes"]),
            "runner_up_coalition": _ballot_coalition(runner_up["party"]),
            "electors": int(summary["pengundi_jumlah"]),
            "turnout": float(summary["peratus_keluar"]) / 100.0,
        },
        winner["name"],
        winner["party"],
    )


def _ballot_coalition(party: str) -> str:
    """The short code inside a ballot party name: "PERIKATAN NASIONAL (PN)" -> "PN".

    The same reading `lpa.baseline_loader` gives these strings, so a profile
    and its Seat's Baseline name a Coalition the same way.
    """
    match = re.search(r"\(([^)]+)\)\s*$", party.strip())
    if not match:
        raise ValueError(f"no short code in ballot party {party!r}")
    return match.group(1)


def _split_seat(label: str) -> tuple[str, str]:
    """Split a "P.102 Bangi" dataset label into its code and its name."""
    match = _SEAT_LABEL.match(label.strip())
    if not match:
        raise ValueError(f"unrecognised Seat label: {label!r}")
    return match.group(1), match.group(2).strip()


def sitting_dates(client: httpx.Client) -> list[str]:
    """Every Dewan Rakyat sitting day of `TERM`, oldest first.

    From the portal's own catalogue rather than a date range: the House sits
    in irregular blocks, and a range would either miss sittings or fetch
    hundreds of days that never happened.
    """
    archive = _next_data(client, CATALOGUE_URL)["archive"][TERM]
    dates = []
    for session in sorted((k for k in archive if k.isdigit()), key=int):
        meetings = archive[session]
        for meeting in sorted((k for k in meetings if k.isdigit()), key=int):
            dates += [s["date"] for s in meetings[meeting]["sitting_list"]]
    if not dates:
        raise ValueError(f"the catalogue lists no sittings for Parliament {TERM}")
    return sorted(dates)


def _walk(node: Any, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    """Every speech in a sitting, with the nested headings it sits under.

    A sitting's Hansard is a tree of headings ("RANG UNDANG-UNDANG" ->
    a Bill -> "Ahli-Ahli Yang Bersetuju:"), and it is the innermost heading
    that says what a block of names means. Flattening keeps that path.
    """
    if isinstance(node, list):
        for item in node:
            yield from _walk(item, path)
    elif isinstance(node, dict):
        if "speech" in node:
            yield path, node
        else:
            for heading, child in node.items():
                yield from _walk(child, path + (heading,))


def _divisions_in_sitting(page: Mapping[str, Any]) -> dict[str, dict[str, set[str]]]:
    """Every Division in one sitting: subject -> position -> the Seats listed.

    Only blocks with no `author` count as name lists. Hansard's tree puts the
    debate that follows a Division under the same heading, so a speech by a
    Member for a Seat would otherwise read as that Seat being listed in it —
    the transcript's structure is loose in a way its authorship is not.

    One entry per question, not per vote: a Bill read a second and a third
    time in the same sitting divides twice under one heading, and the two are
    the same question put to the same House minutes apart. `DECLARED_RESULTS`
    carries the result the Chair declared in full, and `LIST_TOLERANCE`
    absorbs the few Members who moved between the two.
    """
    found: dict[str, dict[str, set[str]]] = {}
    for path, speech in _walk(page["speeches"]):
        if not path or speech.get("author") is not None or speech.get("is_annotation"):
            continue
        position = VOTE_SECTIONS.get(path[-1].strip().lower())
        if position is None:
            continue
        seats = {m.strip() for m in _LIST_ENTRY.findall(speech.get("speech") or "")}
        if not seats:
            continue
        subject = " > ".join(path[:-1])
        found.setdefault(subject, {}).setdefault(position, set()).update(seats)
    return found


def divisions_for_seat(
    client: httpx.Client, seat_name: str, dates: Sequence[str]
) -> list[dict[str, Any]]:
    """Every Division of the term in which `seat_name` was recorded, newest first.

    Fetches each sitting in turn — the portal offers no search across them,
    and a Division is announced nowhere but in the sitting it happened in.
    Expect this to take a few minutes and a hundred-odd megabytes.
    """
    build = portal_build(client)
    divisions = []
    for sitting in dates:
        page = _sitting_props(client, build, sitting)
        for subject, positions in _divisions_in_sitting(page).items():
            declared = DECLARED_RESULTS.get((sitting, subject))
            if declared is None:
                raise ValueError(
                    f"Hansard records a Division on {sitting} under {subject!r} that "
                    "DECLARED_RESULTS does not cover. Transcribe the Chair's declared "
                    "result from that sitting and add it, rather than letting a vote "
                    f"go missing: {HANSARD}/hansard/dewan-rakyat/{sitting}"
                )
            _check_declared(sitting, subject, declared, positions)
            listed = [p for p, seats in positions.items() if seat_name in seats]
            if len(listed) != 1:
                raise ValueError(
                    f"{seat_name} appears in {len(listed)} of the Division's lists on "
                    f"{sitting} ({subject!r}); Hansard's four lists partition the House, "
                    "so exactly one is the only correct answer."
                )
            divisions.append(
                {
                    "sitting_date": sitting,
                    "subject": subject,
                    "vote": listed[0],
                    "hansard_url": f"{HANSARD}/hansard/dewan-rakyat/{sitting}",
                    **declared,
                }
            )
    return sorted(divisions, key=lambda d: d["sitting_date"], reverse=True)


def _check_declared(
    sitting: str,
    subject: str,
    declared: Mapping[str, Any],
    positions: Mapping[str, set[str]],
) -> None:
    """Cross-check a transcribed result against the names Hansard actually lists.

    The four numbers may account for slightly fewer than all 222 Seats — a
    vacancy, or a Member barred from voting under suspension — so only an
    impossible total is an error. What is checked hard is each individual
    number against the names Hansard prints under that heading.
    """
    counts = {position: int(declared[key]) for position, key in TALLY_KEYS.items()}
    total = sum(counts.values())
    if not (TOTAL_SEATS - MAX_UNACCOUNTED <= total <= TOTAL_SEATS):
        raise ValueError(
            f"the transcribed result for {sitting} ({subject!r}) accounts for {total} "
            f"Members, which is not within {MAX_UNACCOUNTED} of the {TOTAL_SEATS} Seats "
            "in the Dewan Rakyat."
        )
    for position, expected in counts.items():
        listed = len(positions.get(position, set()))
        if listed and abs(listed - expected) > LIST_TOLERANCE:
            raise ValueError(
                f"{sitting} ({subject!r}): the Chair declared {expected} {position}, but "
                f"Hansard lists {listed} names there — too far apart to be a "
                "transcription artefact."
            )


def bill_sponsors(client: httpx.Client) -> set[str]:
    """Everyone who tabled a Bill in Parliament's own Bills register.

    Used to check a Member's sponsorships rather than to list them: the
    register names the tabler in prose ("YB Tuan Liew Chin Tong, Timbalan
    Menteri Kewangan"), so what it supports is "this name does not appear",
    which for a backbencher is the answer.
    """
    html = _get(client, BILLS_URL).text
    return {
        re.sub(r"\s+", " ", name).strip()
        for name in re.findall(
            r"Dibentang Oleh[^<]*</[^>]*>\s*<[^>]*>\s*:?\s*</[^>]*>\s*<[^>]*>([^<]{5,160})<",
            html,
        )
    }


def build_profile(
    client: httpx.Client,
    seat_code: str,
    members: Mapping[str, Mapping[str, str]],
    candidates: Sequence[Mapping[str, str]],
    results: Sequence[Mapping[str, str]],
    dates: Sequence[str],
    sponsors: set[str],
    term_start: str,
) -> dict[str, Any]:
    """One Seat's profile, with every field traced to the source it came from."""
    if seat_code not in members:
        raise ValueError(f"{seat_code} is not in Parliament's Members directory")
    member = members[seat_code]
    details = fetch_member_details(client, member["profile_url"])

    ge15, winner_name, ballot_party = ge15_result(candidates, results, seat_code)
    seat_name = _split_seat(
        next(c["parlimen"] for c in candidates if _split_seat(c["parlimen"])[0] == seat_code)
    )[1]

    if _name_key(winner_name) != _name_key(member["name"]):
        raise ValueError(
            f"{seat_code}: Parliament's directory names {member['name']!r} but the GE15 "
            f"winner was {winner_name!r}. A by-election may have changed the Member, in "
            "which case the GE15 result is no longer this Member's own election."
        )

    coalition = details.get("parti")
    if not coalition:
        raise ValueError(f"{seat_code}: Parliament's profile page states no party")
    if coalition not in ballot_party:
        raise ValueError(
            f"{seat_code}: Parliament records {coalition!r} but the GE15 ballot line was "
            f"{ballot_party!r}. The Member may have changed Coalition since GE15."
        )

    unverified = dict(UNVERIFIED)
    bills = sorted(s for s in sponsors if _name_key(member["name"]) in _name_key(s))
    if not bills:
        unverified["bills_sponsored"] = (
            "Checked against Parliament's Bills register "
            f"({BILLS_URL}), where every Bill of this term was tabled by a Minister or "
            "Deputy Minister and this Member appears nowhere. Motions a Member files are "
            "not published as a register at all, so a motion cannot be confirmed either way."
        )

    return {
        "name": member["name"],
        "coalition": coalition,
        "term_start": term_start,
        "ge15": ge15,
        "contact": {
            "address": details.get("alamat surat-menyurat"),
            "phone": details.get("no. telefon"),
            "email": details.get("email"),
            "profile_url": member["profile_url"],
        },
        "divisions": divisions_for_seat(client, seat_name, dates),
        "bills_sponsored": bills,
        "attendance": None,
        "party": None,
        "unverified": unverified,
    }


HONORIFICS = frozenset(
    """yab yb tan sri seri dato datuk datin wira tuan puan dr haji hajah
    prof ir ts dr jeneral kapten komander laksamana brigedier tpr""".split()
)
"""Titles Malaysian sources prefix to a name, dropped before comparing two.

Parliament's directory writes "YB Dato' Seri Amirudin bin Shari" where the
Election Commission writes "AMIRUDIN BIN SHARI", and which titles a source
uses is a matter of that source's house style rather than of identity. Only
a *leading* run is dropped: these words also occur inside given names.
"""


def _name_key(name: str) -> str:
    """A name reduced to a form two sources can be compared on.

    Titles are stripped, then everything but the letters, because Hansard
    also breaks words mid-name ("T uan", "S yahredzan") where the other two
    sources do not.
    """
    tokens = [re.sub(r"[^a-z]", "", t.lower()) for t in name.split()]
    tokens = [t for t in tokens if t]
    while tokens and tokens[0] in HONORIFICS:
        tokens.pop(0)
    return "".join(tokens)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--term-start",
        default=None,
        help="The day the Parliament first sat. Read from the portal's calendar if omitted.",
    )
    args = parser.parse_args()

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        members = fetch_members(client)
        candidates = fetch_csv(client, GE15_CANDIDATES_URL)
        results = fetch_csv(client, GE15_RESULTS_URL)
        dates = sitting_dates(client)
        sponsors = bill_sponsors(client)
        term_start = args.term_start or dates[0]
        profiles = {
            seat: build_profile(
                client, seat, members, candidates, results, dates, sponsors, term_start
            )
            for seat in SEATS
        }

    output = {
        "_comment": [
            "One profile per Seat for PolitikKu's constituency lookup (issue #78).",
            "Pilot slice: P.102 Bangi only — see scripts/build_mp_profiles.py, which",
            "generated this file, and ADR 0009 for what each source does and does not",
            "publish. Every optional field left null is named in that profile's",
            "'unverified' block with the reason; lpa.config.load_mp_profiles refuses to",
            "load a profile that leaves one unexplained, because an unexplained blank is",
            "how an invented value gets in. A Division's subject is Hansard's own",
            "heading, verbatim and in Malay, rather than a translation this pipeline",
            "invented.",
        ],
        "_source": {
            "identity_and_contact": {
                "name": "Parlimen Malaysia — Ahli Dewan Rakyat directory",
                "url": MEMBERS_URL,
            },
            "ge15_result": {
                "name": (
                    "Election Commission GE15 candidate and Seat results, via Thevesh "
                    "Theva's Malaysian election dataset (the Baseline Loader's source)"
                ),
                "candidates_url": GE15_CANDIDATES_URL,
                "results_url": GE15_RESULTS_URL,
            },
            "voting_record": {
                "name": f"Dewan Rakyat Hansard, {TERM}th Parliament, via Digital Hansard",
                "catalogue_url": CATALOGUE_URL,
            },
            "bills": {"name": "Parlimen Malaysia — Rang Undang-Undang register", "url": BILLS_URL},
            "retrieved": date.today().isoformat(),
            "generated_by": "scripts/build_mp_profiles.py",
        },
        "profiles": profiles,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    for seat, profile in profiles.items():
        print(
            f"{seat}: {profile['name']} — {len(profile['divisions'])} Division(s), "
            f"{len(profile['unverified'])} field(s) recorded as unverified"
        )
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
