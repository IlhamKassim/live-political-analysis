"""One-off ingestion: build `data/mp_profiles.json` (issues #78, #105).

Run by hand, not part of the daily pipeline. A Member's contact details, a
term's Divisions and a GE15 result all change on the order of months or
years, and none of the three sources publishes a feed to poll for a diff.
See `## Cadence` below for when it is worth re-running.

## What is read from where

1. **Identity, Coalition and contact** — `parlimen.gov.my`'s own Members
   directory and the per-Member profile page behind it. This is Parliament
   stating who holds a Seat and how to reach them, and it is the only
   official source for either.
2. **GE15 result** — Thevesh Theva's Malaysian election dataset, already the
   Baseline Loader's source (`lpa.sources`), at candidate level plus the
   Election Commission's own per-Seat turnout and elector counts. Fetched
   here rather than read back out of Storage so this script has no database
   dependency, and cross-checked against itself: the candidates' votes must
   reconcile with the official ballot accounting.
3. **Voting record** — the Digital Hansard portal (`hansard.parlimen.gov.my`),
   Parliament's own full-text Hansard, which prints each Division's four
   name lists as structured sections. Every sitting of the term is fetched
   once and every Seat's position read out of the same sweep; see
   `divisions_by_seat`.
4. **Sponsorships** — Parliament's own Bills register, both its default view
   and the Arkib behind it, which together carry every Bill of the term with
   its title, its first reading and who tabled it.

## Why the tallies are curated and the votes are not

A Member's position is read from the primary source and never curated: the
sweep finds the Division's *Ahli-Ahli Yang Bersetuju / Tidak Bersetuju /
Tidak Mengundi / Tidak Hadir* sections and looks for the Seat in them, and a
Seat that lands in none or in more than one gets no position recorded rather
than a guessed one.

The *tallies*, by contrast, live in `DECLARED_RESULTS` below, transcribed by
hand from the Chair's spoken declaration. That declaration is free prose,
phrased differently every time ("Yang tidak mengundi ― seorang", "Tetapi
bersetuju― 146", "Ahli yang tidak hadir mengundi – 14 undi"), and a parser
that guessed at it would fail silently on the next new phrasing. The
transcription is checked rather than trusted: the four numbers must very
nearly account for the whole House (`MAX_UNACCOUNTED`), and each must land
within `LIST_TOLERANCE` of the number of names Hansard actually lists in
that section.

A Division found in Hansard that `DECLARED_RESULTS` does not cover is a
failure, not a skip — otherwise the next sitting's vote would quietly go
missing from a record that claims to be complete.

## How a Seat is read out of a name list

Hansard writes a list entry as a number, the Member's name — often prefixed
by their ministerial portfolio, which has parentheses of its own — and the
Seat in brackets: "3. Menteri Di Jabatan Perdana Menteri (Undang-Undang Dan
Reformasi Institusi), Dato' Sri Azalina Othman Said (Pengerang)". So the
Seat is not "the bracketed part"; it is *the bracketed part that names a
Seat*, and `_seats_in_list` finds it by matching every bracketed group
against the Election Commission's own 222 Seat names. An entry that names no
Seat at all is a parse failure and stops the build, because the alternative
is a Member's vote disappearing silently — which is what happened to Lumut
and Tanjong Karang, whose entries carry a naval rank in brackets before the
Seat.

## Where a Seat gets no position, and why that is recorded

Three (Seat, Division) pairs in this term have no position on the record:
Machang is named in none of the four lists on 17 October 2024, being under
the suspension the House agreed on 18 July, and Kota Bharu and Bagan Serai
are each named in *two* lists on 4 March 2025, which Hansard's own declared
counts show cannot both be right. In all three the Division is left out of
that Member's record and `unverified["divisions"]` says which one and why.
Inferring the position from the arithmetic — the abstention list matches the
Chair's count exactly and the absence list overshoots by exactly two — would
be putting this pipeline's reasoning next to a named person's vote, which is
the thing ADR 0009 exists to prevent.

## What a skipped Seat is

A Seat this pass cannot profile honestly is written to the output's
`_skipped` block with the reason, rather than left silently absent. The four
kinds: Parliament's directory lists no Member for the Seat; the two upstream
GE15 files disagree about it; the Member is not the one who won GE15, so the
GE15 result is somebody else's; or the Member's Coalition today is not the
one they were elected under. See `SkipSeat`.

## Cadence

Manually triggered, and deliberately not wired into `daily.yml` (#105 asks
for the decision). Nothing here changes daily, and every run costs a full
sweep of the term's sittings; a daily job would be several hundred megabytes
of Parliament's bandwidth a day to rewrite a file that changed on none of
them. Re-run when the House rises at the end of a meeting — that is when new
Divisions and new Bills appear — and after a by-election, which is the event
that changes who holds a Seat. Both are events a human notices; neither is a
schedule.
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import time
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterator, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from lpa.baseline_loader import coalition_of, split_seat_label
from lpa.config import load_coalition_config, party_to_coalition
from lpa.mp_profile import ABSENT, ABSTAIN, AYE, NO, TOTAL_SEATS

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "mp_profiles.json"

PARLIMEN = "https://www.parlimen.gov.my"
MEMBERS_URL = f"{PARLIMEN}/ahli-dewan.html?uweb=dr"
BILLS_URL = f"{PARLIMEN}/bills-dewan-rakyat.html?uweb=dr"
BILLS_ARCHIVE_URL = f"{BILLS_URL}&arkib=yes"
HANSARD = "https://hansard.parlimen.gov.my"
CATALOGUE_URL = f"{HANSARD}/katalog/dewan-rakyat"

ELECTION_DATA_BASE = "https://raw.githubusercontent.com/Thevesh/analysis-election-msia/main/data"
GE15_CANDIDATES_URL = f"{ELECTION_DATA_BASE}/candidates_ge15.csv"
GE15_RESULTS_URL = f"{ELECTION_DATA_BASE}/results_parlimen_ge15.csv"

TERM = "15"
"""The Parliament whose record is ingested. Members and Divisions both belong
to a term; a profile that mixed two would attribute a predecessor's votes."""

TERM_FIRST_YEAR = 2022
"""The earliest year the Bills Arkib is fetched for.

The 15th Parliament first sat on 19 December 2022, so 2022 is the first year
that can hold one of its Bills. The Arkib's root goes back to 2007 and every
year of it is a request; `main` then filters on the actual term start, which
is the check that matters — this only keeps the sweep from fetching fifteen
years of a previous Parliament's legislation to throw away.
"""

LIST_TOLERANCE = 6
"""How far a Hansard name list may differ from the Chair's declared count.

Since `_seats_in_list` reads the Seat rather than the first bracketed group,
nine of this term's ten Divisions reconcile with the declaration exactly and
the tenth is one name out. The tolerance is kept because Hansard's lists do
carry transcription artefacts — a name run together with the one before it,
a missing bracket — and because on 28 August 2025 the Chair's own four
numbers come to 221 with no reason given.

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
# Matched through `_heading`, not compared raw: the same section is written
# "Ahli-Ahli Yang Tidak Hadir:" in most sittings and "AHLI-AHLI YANG TIDAK
# HADIR" in the one on 26 June 2024, and a raw comparison silently lost the
# whole 66-name absence list there.
VOTE_SECTIONS = {
    "ahli-ahli yang bersetuju": AYE,
    "ahli-ahli yang tidak bersetuju": NO,
    "ahli-ahli yang tidak mengundi": ABSTAIN,
    "ahli-ahli yang tidak hadir": ABSENT,
}

# Position -> the `DECLARED_RESULTS` key holding its count, which is also the
# field name on `lpa.mp_profile.Division`.
TALLY_KEYS = {AYE: "ayes", NO: "noes", ABSTAIN: "abstentions", ABSENT: "absent"}

# (sitting date, Hansard heading) -> the Chair's declared result, transcribed
# by hand from the sitting's Hansard. `ayes`/`noes`/`abstentions`/`absent`
# are the numbers announced to the House; `outcome` is what the Chair
# declared them to have decided. Verified against the linked Hansard on
# 2026-08-24, and re-checked against the name lists on 2026-08-26, when a
# sweep of all 265 sittings of the term found these ten Divisions and no
# eleventh. See the module docstring for why this is curated.
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
        # under the suspension agreed on 18 July 2024. That Member is
        # Machang, and Hansard's lists bear the declaration out — they name
        # 221 Seats and Machang is not among them.
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
        # Hansard names Kota Bharu and Bagan Serai in both the abstention
        # list and the absence list here. The declaration is what settles
        # that the lists are wrong rather than the transcription — see the
        # module docstring — and both Seats have this Division left out of
        # their record rather than resolved by arithmetic.
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

# Why each optional field is unset on every profile. Every entry is a
# statement about what was checked, not a note to fill this in later — see
# `lpa.mp_profile.MPProfile.unverified` and ADR 0009. Fields that are unset
# for some Members and not others (a telephone number, a Division) get their
# reason built per profile instead; see `_contact_reasons` and
# `_divisions_reason`.
UNVERIFIED: dict[str, str] = {
    "party": (
        "Not published as a statement of this Member's party today. Parliament's "
        "Members directory publishes the Coalition ('PH', 'PN', 'GPS') in its Parti "
        "field and nothing narrower. The Election Commission's GE15 record gives the "
        "ballot line, which for most Seats is also the Coalition and for some — the "
        "PAS and DAP Seats — is the component party, but that is the party the Member "
        "stood for in November 2022, not a source for what they belong to now. Four "
        "Seats in this term changed hands at a by-election and two Members changed "
        "Coalition, so a 2022 ballot line is exactly the kind of fact that goes stale "
        "silently, and it is not published here as a current one."
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

_ENTRY = re.compile(r"\d{1,3}\.\s*[,;]?\s*(.*?)(?=\s*\d{1,3}\.\s*[,;]?\s|$)", re.S)
"""One numbered entry in a Hansard name list.

The separator tolerates the stray punctuation the transcript occasionally
carries between the number and the name ("22.," on 2 March 2026, which ran
two Members into one entry and lost both from the abstention list).
"""

_BRACKETED = re.compile(r"\(([^()]{1,80})\)")


class SkipSeat(Exception):
    """This Seat cannot be profiled honestly from the sources consulted.

    Raised rather than returned so every check in `build_profile` reads as a
    refusal at the point the refusal is decided. `main` records the reason in
    the output's `_skipped` block: a Seat that is simply absent from the file
    looks like one nobody got to, and the whole discipline of ADR 0009 is
    that absence has to say why.
    """


def fetch_csv(client: httpx.Client, url: str) -> list[dict[str, str]]:
    text = _get(client, url).text
    return list(csv.DictReader(io.StringIO(text)))


def _next_payload(client: httpx.Client, url: str) -> Any:
    """The whole Next.js payload embedded in a Digital Hansard page.

    The portal renders server-side and exposes no API, so its own embedded
    payload is the structured form of what it displays — the same data the
    page shows, not a scrape of the rendered HTML.
    """
    body = _get(client, url).text
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if not match:
        raise ValueError(f"no Next.js payload at {url} — the portal's markup may have changed")
    return json.loads(match.group(1))


def _next_data(client: httpx.Client, url: str) -> Any:
    """The page props behind a Digital Hansard page."""
    payload = _next_payload(client, url)
    try:
        return payload["props"]["pageProps"]
    except KeyError as error:
        raise ValueError(
            f"no props.pageProps in the Next.js payload at {url} — the portal's shape "
            "may have changed"
        ) from error


def _get(client: httpx.Client, url: str, attempts: int = 4) -> httpx.Response:
    """Fetch `url`, retrying a transport failure or a 5xx with a widening pause.

    The sweep below makes a request per sitting day of the term, and over a
    few hundred of them the portal will stall on one or two — a timeout, or
    a connection Parliament's server closes without answering. Without this
    the whole build is lost to a single bad response near the end. A 4xx is
    not retried: the URL is wrong, and asking again more slowly will not
    make it right.
    """
    for attempt in range(attempts):
        try:
            return client.get(url).raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
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
    """Seat code -> the sitting Member's name, Coalition and profile URL.

    Parliament writes a Seat as "P102" in this listing and "P.102" everywhere
    else, including its own profile pages; normalised here so a caller never
    has to know which spelling it is holding.

    The Coalition comes from this listing's own `caucus` field, which is
    Parliament stating it in the same breath as who holds the Seat.
    `build_profile` requires it to agree with the Parti field on the
    Member's own page wherever that page has one, so it is corroborated
    rather than merely convenient — and it is left empty here, not guessed
    at, for the six Members whose Seat the listing leaves blank.

    The listing also carries the Speaker and Deputy Speaker, who are
    appointed from outside the House and hold no Seat; they have no
    constituency in the markup and so are skipped here, which is part of why
    this returns fewer than `TOTAL_SEATS` entries.
    """
    body = _get(client, MEMBERS_URL).text
    members = {}
    for block in re.findall(r"<li>.*?</li>", body, re.S):
        href = re.search(r'href="(profile-ahli\.html\?[^"]+)"', block)
        name = re.search(r'<span class="first-name">([^<]+)</span>', block)
        seat = re.search(r'<div class="constituency">(P\d+)</div>', block)
        caucus = re.search(r'<div class="caucus">([^<]*)</div>', block)
        if not (href and name and seat):
            continue
        code = f"P.{seat.group(1)[1:]}"
        members[code] = {
            "name": html.unescape(name.group(1)).strip(),
            "coalition": html.unescape(caucus.group(1)).strip() if caucus else "",
            "profile_url": f"{PARLIMEN}/{html.unescape(href.group(1))}",
        }
    if not members:
        raise ValueError(f"no Members parsed from {MEMBERS_URL} — its markup may have changed")
    return members


def fetch_member_details(client: httpx.Client, profile_url: str) -> dict[str, str]:
    """The labelled fields on a Member's own page in Parliament's directory.

    Returned as the page's own Malay labels ("No. Telefon", "Alamat
    Surat-menyurat"), lower-cased. Restricted to a fixed set of known labels
    deliberately: the extraction below is a naive zip of every text cell on
    the page with the one after it, and without the filter it would pick up
    nav links and page furniture as spurious label/value pairs. A field the
    page renders as "-" is omitted: that is the page saying it has none.
    """
    raw = _get(client, profile_url).text
    body = re.sub(r"<(script|style)\b.*?</\1>", "", raw, flags=re.S | re.I)
    cells = [html.unescape(re.sub(r"\s+", " ", c)).strip() for c in re.split(r"<[^>]+>", body)]
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


def seat_names(candidates: Sequence[Mapping[str, str]]) -> dict[str, str]:
    """Seat code -> Seat name, from the Election Commission's own labels.

    The authority for both throughout this script: Hansard's name lists are
    matched against these names, and the Seats profiled are these Seats.
    """
    names = {}
    for row in candidates:
        code, name = split_seat_label(row["parlimen"])
        names[code] = name
    if len(names) != TOTAL_SEATS:
        raise ValueError(
            f"the GE15 candidate file names {len(names)} Seats, not the {TOTAL_SEATS} in "
            "the Dewan Rakyat — the upstream file may have changed shape"
        )
    return names


def _seat_index(names: Mapping[str, str]) -> dict[str, str]:
    """Normalised Seat name -> Seat code, for reading Hansard's brackets.

    Normalised only by case and punctuation, never by dropping words: two
    Seats' names differing by a word are two different Seats, and a lookup
    that blurred them would put one Member's vote on another's record.
    """
    index: dict[str, str] = {}
    for code, name in names.items():
        key = _letters(name)
        if key in index:
            raise ValueError(
                f"{index[key]} ({names[index[key]]}) and {code} ({name}) normalise to the "
                f"same key {key!r}; Hansard's brackets could not tell them apart"
            )
        index[key] = code
    return index


def _letters(value: str) -> str:
    return re.sub(r"[^a-z]", "", value.lower())


def ge15_result(
    candidates: Sequence[Mapping[str, str]],
    results: Sequence[Mapping[str, str]],
    seat_code: str,
    party_to_coalition_map: Mapping[str, str],
) -> tuple[dict[str, Any], str, str]:
    """The winning candidate's GE15 result for one Seat, and who won it.

    Returns `(result fields, winner's name, ballot party)`.

    The two files are reconciled rather than merged on trust. The Election
    Commission's ballot accounting (`undi_dalam_peti` less `undi_tolak`) must
    equal the votes the candidate rows add up to; if it does not, one of the
    two has changed shape upstream and every figure derived from them is
    suspect, which is worth refusing the Seat for rather than publishing.
    """
    rows = [c for c in candidates if split_seat_label(c["parlimen"])[0] == seat_code]
    if not rows:
        raise SkipSeat(f"the GE15 candidate file has no rows for {seat_code}")
    summary = next((r for r in results if split_seat_label(r["parlimen"])[0] == seat_code), None)
    if summary is None:
        raise SkipSeat(f"the GE15 Seat-results file has no row for {seat_code}")

    by_votes = sorted(rows, key=lambda r: -int(r["votes"]))
    winner, runner_up = by_votes[0], by_votes[1]
    valid_votes = sum(int(r["votes"]) for r in rows)

    accounted = int(summary["undi_dalam_peti"]) - int(summary["undi_tolak"])
    if accounted != valid_votes:
        raise SkipSeat(
            "the Election Commission's ballot accounting gives "
            f"{accounted} valid votes but the candidate rows add up to {valid_votes}. "
            "The two upstream GE15 files disagree about this Seat, so every figure "
            "derived from them is suspect and none is published."
        )
    majority = int(winner["votes"]) - int(runner_up["votes"])
    if majority != int(summary["majoriti"]):
        raise SkipSeat(
            f"the candidate rows give a majority of {majority}, but the official "
            f"result states {summary['majoriti']}."
        )

    return (
        {
            "votes": int(winner["votes"]),
            "majority": majority,
            "vote_share": int(winner["votes"]) / valid_votes,
            "valid_votes": valid_votes,
            "runner_up_votes": int(runner_up["votes"]),
            "runner_up_coalition": coalition_of(runner_up["party"], party_to_coalition_map),
            "electors": int(summary["pengundi_jumlah"]),
            "turnout": float(summary["peratus_keluar"]) / 100.0,
            "source_url": GE15_RESULTS_URL,
        },
        winner["name"],
        winner["party"],
    )


def sitting_dates(client: httpx.Client) -> list[str]:
    """Every Dewan Rakyat sitting day of `TERM`, oldest first.

    From the portal's own catalogue rather than a date range: the House sits
    in irregular blocks, and a range would either miss sittings or fetch
    hundreds of days that never happened.
    """
    catalogue = _next_data(client, CATALOGUE_URL)
    try:
        archive = catalogue["archive"][TERM]
    except KeyError as error:
        raise ValueError(
            f"no archive for Parliament {TERM} at {CATALOGUE_URL} — the portal's shape "
            "may have changed, or the term number needs updating"
        ) from error
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


def _heading(value: str) -> str:
    """A Hansard heading in the form `VOTE_SECTIONS` is keyed on."""
    return re.sub(r"\s+", " ", value).strip().rstrip(":").strip().lower()


def _seats_in_list(block: str, index: Mapping[str, str], where: str) -> set[str]:
    """The Seats named in one Hansard name list.

    Each numbered entry contributes the Seats among its bracketed groups —
    plural, because the transcript occasionally runs two Members into one
    entry, and both of them voted. An entry naming no Seat at all raises:
    see the module docstring for the Members that silently went missing when
    it did not.
    """
    seats: set[str] = set()
    for entry in _ENTRY.findall(block):
        found = {
            index[_letters(group)]
            for group in _BRACKETED.findall(entry)
            if _letters(group) in index
        }
        if not found:
            raise ValueError(
                f"{where}: no Seat name in the Hansard list entry {entry.strip()[:120]!r}. "
                "Every entry names the Member's Seat in brackets; one that appears not "
                "to is a Member whose vote would otherwise vanish from the record."
            )
        seats |= found
    return seats


def _divisions_in_sitting(
    page: Mapping[str, Any], index: Mapping[str, str], sitting: str
) -> dict[str, dict[str, set[str]]]:
    """Every Division in one sitting: subject -> position -> the Seats listed.

    Only blocks with no `author` count as name lists. Hansard's tree puts the
    debate that follows a Division under the same heading, so a speech by a
    Member for a Seat would otherwise read as that Seat being listed in it —
    the transcript's structure is loose in a way its authorship is not.

    One entry per question, not per vote: a Bill read a second and a third
    time in the same sitting divides twice under one heading, and the two are
    the same question put to the same House minutes apart. Positions are
    therefore sets — on 17 October 2024 both readings' lists are printed in
    full and the union of them is one Division's record, not two.

    A section heading is recorded even when it names nobody — a genuinely
    empty position (nobody voted no) looks the same as a name-list format
    this pipeline can no longer parse, and `_check_declared` is what tells
    the two apart: it checks the declared count for the same position, so a
    real 0 passes and a parse failure against a nonzero declared count does
    not silently disappear here.
    """
    found: dict[str, dict[str, set[str]]] = {}
    for path, speech in _walk(page["speeches"]):
        if not path or speech.get("author") is not None or speech.get("is_annotation"):
            continue
        position = VOTE_SECTIONS.get(_heading(path[-1]))
        if position is None:
            continue
        seats = _seats_in_list(
            speech.get("speech") or "", index, f"{sitting} ({_heading(path[-1])})"
        )
        subject = " > ".join(path[:-1])
        found.setdefault(subject, {}).setdefault(position, set()).update(seats)
    return _attach_stray_sections(found, sitting)


def _attach_stray_sections(
    found: dict[str, dict[str, set[str]]], sitting: str
) -> dict[str, dict[str, set[str]]]:
    """Re-file a vote section Hansard filed one heading too shallow.

    On 26 June 2024 the absence list sits directly under "RANG
    UNDANG-UNDANG" rather than under the Bill, so it reads as a Division of
    its own with 66 absentees and no other position — and the Bill's own
    Division reads as 156 Members out of 222. The stray section is attached
    to the Division whose subject it is a prefix of, which on that sitting is
    exactly one; where it is not exactly one the attachment would be a guess,
    and this stops instead.
    """
    known = [subject for subject in found if (sitting, subject) in DECLARED_RESULTS]
    for subject in [s for s in found if s not in known]:
        hosts = [host for host in known if host.startswith(subject + " > ")]
        if len(hosts) != 1:
            raise ValueError(
                f"{sitting}: Hansard files a Division name list under {subject!r}, which "
                f"is not a Division this script knows and is a prefix of {len(hosts)} that "
                "are. Which Division those names belong to cannot be settled from the "
                f"transcript's structure: {HANSARD}/hansard/dewan-rakyat/{sitting}"
            )
        for position, seats in found.pop(subject).items():
            found[hosts[0]].setdefault(position, set()).update(seats)
    return found


def divisions_by_seat(
    client: httpx.Client, dates: Sequence[str], index: Mapping[str, str]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[tuple[str, str, list[str]]]]]:
    """Every Seat's voting record for the term, from one sweep of the sittings.

    Returns `(Seat code -> its Divisions newest first, Seat code -> the
    (sitting, subject, positions) it has no single position in)`.

    One sweep rather than one per Seat: the portal offers no search across
    sittings, so finding Divisions means fetching every one of the term's
    265, and doing that once per Seat would be 222 times the traffic for the
    same answer. Expect this to take several minutes and a few hundred
    megabytes.

    Hansard's four lists partition the House, so exactly one of them is the
    only correct answer for a Seat. Where that does not hold the Division is
    reported as a problem rather than resolved — the caller records it on the
    profile as a gap with a reason.
    """
    build = portal_build(client)
    records: dict[str, list[dict[str, Any]]] = {code: [] for code in index.values()}
    problems: dict[str, list[tuple[str, str, list[str]]]] = {}
    for sitting in dates:
        page = _sitting_props(client, build, sitting)
        for subject, positions in _divisions_in_sitting(page, index, sitting).items():
            declared = DECLARED_RESULTS.get((sitting, subject))
            if declared is None:
                raise ValueError(
                    f"Hansard records a Division on {sitting} under {subject!r} that "
                    "DECLARED_RESULTS does not cover. Transcribe the Chair's declared "
                    "result from that sitting and add it, rather than letting a vote "
                    f"go missing: {HANSARD}/hansard/dewan-rakyat/{sitting}"
                )
            _check_declared(sitting, subject, declared, positions)
            for code in records:
                listed = [p for p, seats in positions.items() if code in seats]
                if len(listed) == 1:
                    records[code].append(
                        {
                            "sitting_date": sitting,
                            "subject": subject,
                            "vote": listed[0],
                            "hansard_url": f"{HANSARD}/hansard/dewan-rakyat/{sitting}",
                            **declared,
                        }
                    )
                else:
                    problems.setdefault(code, []).append((sitting, subject, sorted(listed)))
    return (
        {
            code: sorted(rows, key=lambda d: d["sitting_date"], reverse=True)
            for code, rows in records.items()
        },
        problems,
    )


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
        if abs(listed - expected) > LIST_TOLERANCE:
            raise ValueError(
                f"{sitting} ({subject!r}): the Chair declared {expected} {position}, but "
                f"Hansard lists {listed} names there — too far apart to be a "
                "transcription artefact. A declared 0 correctly needs 0 names listed, so "
                "this also catches a list Hansard's markup changed too much to parse."
            )


_REGISTER_ROW = '<tr class="maintable">'
_REGISTER_CELL = re.compile(r'<td[^>]*class="maintd"[^>]*>(.*?)</td>', re.S)
_REGISTER_FIELD = (
    r"{}</td>\s*<td[^>]*>\s*:?\s*</td>\s*<td[^>]*>([^<]{{1,200}})</td>"
)
_ARCHIVE_BILL = re.compile(r"^(D\.R\.?\s*\d+/\d{4})\s*-\s*(.*?)(?:\s*\([^()]*\)\s*)?$", re.S)
_DMY = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def bills_tabled(client: httpx.Client) -> list[dict[str, Any]]:
    """Every Bill in Parliament's Bills register, with its title and tabler.

    Both halves of the register are read. Its default view carries the Bills
    of the current few years as an HTML table; the Arkib behind it carries
    the older ones as a per-year XML tree for a JavaScript widget, with the
    same four facts in it. Reading only the default view — as this script
    did while it profiled one Seat — covers 2024 onwards and silently misses
    everything the House passed in the term's first year, which is a claim
    about a named person's record that would have been wrong.

    `first_reading` is carried so a caller can keep the Bills of this term
    and drop the previous Parliament's, which share the register.
    """
    bills = {bill["code"]: bill for bill in _archive_bills(client)}
    bills.update({bill["code"]: bill for bill in _register_bills(_get(client, BILLS_URL).text)})
    if not bills:
        raise ValueError(f"no Bills parsed from {BILLS_URL} — its markup may have changed")
    return sorted(bills.values(), key=lambda b: b["code"])


def _register_bills(body: str) -> Iterator[dict[str, Any]]:
    """The register's default view: one Bill per `maintable` row.

    Split on the row marker rather than matched as `<tr>...</tr>`, because
    each row embeds a whole second table of dates and tablers and a
    non-greedy match ends at that inner table's first `</tr>`.
    """
    for chunk in body.split(_REGISTER_ROW)[1:]:
        cells = _REGISTER_CELL.findall(chunk)
        if len(cells) < 3:
            continue
        tablers = re.findall(_REGISTER_FIELD.format("Dibentang Oleh"), chunk, re.S)
        first = re.search(_REGISTER_FIELD.format("Bacaan Pertama Pada"), chunk, re.S)
        yield {
            "code": _plain(cells[0]),
            "title": _plain(cells[2]),
            "tablers": sorted({_plain(t) for t in tablers}),
            "first_reading": _as_date(first.group(1) if first else ""),
        }


def _archive_bills(client: httpx.Client) -> Iterator[dict[str, Any]]:
    """The register's Arkib, a per-year XML tree of the same four facts.

    Only years the 15th Parliament could have sat in are fetched. The tree's
    root lists every year back to 2007, and the Bills of a Parliament that
    rose before this one began are not this term's record.
    """
    root = ElementTree.fromstring(_get(client, f"{BILLS_ARCHIVE_URL}&ajx=0").text)
    years = [item.get("id", "") for item in root.findall("item")]
    for year_id in years:
        year = year_id.rpartition("_")[2]
        if not (year.isdigit() and int(year) >= TERM_FIRST_YEAR):
            continue
        tree = ElementTree.fromstring(
            _get(client, f"{BILLS_ARCHIVE_URL}&ajx=1&id={year_id}").text
        )
        for item in tree.findall("item"):
            match = _ARCHIVE_BILL.match(_plain(item.get("text", "")))
            if not match:
                continue
            fields: dict[str, list[str]] = {}
            for child in item.findall("item"):
                label, _, value = _plain(child.get("text", "")).partition(":")
                fields.setdefault(label.strip(), []).append(value.strip())
            yield {
                "code": match.group(1),
                "title": match.group(2).strip(),
                "tablers": sorted(set(fields.get("Dibentang Oleh", ()))),
                "first_reading": _as_date(next(iter(fields.get("Bacaan Pertama Pada", ())), "")),
            }


def _plain(fragment: str) -> str:
    """A markup fragment as the text it renders to.

    Unescaped repeatedly: the Arkib's own XML carries entities that were
    escaped twice on the way in ("&amp;amp;amp;ndash;"), so one pass leaves
    an ampersand sequence in the middle of a Minister's title.
    """
    text = re.sub(r"<[^>]+>", " ", fragment)
    for _ in range(4):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return re.sub(r"\s+", " ", text).strip()


def _as_date(value: str) -> str | None:
    match = _DMY.search(value)
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


HONORIFICS = frozenset(
    """yab yb tan sri seri dato datuk datin wira tuan puan dr haji hajah hajjah
    prof ir ts jeneral kapten komander laksamana brigedier tpr indera amar
    panglima utama setia bersara tldm tudm td b""".split()
)
"""Titles Malaysian sources prefix and infix to a name, dropped before
comparing two.

Parliament's directory writes "YB Dato' Seri Amirudin bin Shari" where the
Election Commission writes "AMIRUDIN BIN SHARI", and "YB Komander Nordin bin
Ahmad Ismail TLDM (B)" for a name the Commission gives as "Nordin Bin Ahmad
Ismail". Which titles a source uses, and where it puts them, is a matter of
that source's house style rather than of identity — so they are dropped
wherever they occur, and `_name_key`'s caller checks that no two Members
collapse together as a result.
"""

CONNECTORS = frozenset("bin binti binte bte bt ibni anak ak al ap".split())
"""Patronymic particles, which the two sources punctuate differently.

"Mohamad Alamin" in Parliament's directory is "Mohamad Bin Alamin" at the
Election Commission, and "a/l" survives normalisation as "al". None of them
distinguishes one Member from another.
"""


def _name_key(name: str) -> str:
    """A name reduced to a form two sources can be compared on.

    Bracketed asides, titles and patronymic particles are dropped, then
    everything but the letters, because Hansard also breaks words mid-name
    ("T uan", "S yahredzan") where the other two sources do not.

    Deliberately not fuzzy beyond that. Where Parliament and the Election
    Commission genuinely write different names for a Seat — an extra given
    name, an alias, a Member returned at a by-election — this returns two
    different keys and `build_profile` refuses the Seat. A false match here
    would put a predecessor's election result under a successor's name.
    """
    without_brackets = re.sub(r"\([^()]*\)", " ", name)
    tokens = [re.sub(r"[^a-z]", "", token.lower()) for token in without_brackets.split()]
    return "".join(t for t in tokens if t and t not in HONORIFICS and t not in CONNECTORS)


def _contact_reasons(contact: Mapping[str, Any], profile_url: str) -> dict[str, str]:
    """Why each contact field this Member has no value for is unset.

    Built per Member rather than taken from `UNVERIFIED`: 55 of the 219
    Members listed have no telephone number on their page and the rest do,
    so a single fixed reason would be asserting something false about one
    group or the other.
    """
    published = "Parliament's own profile page for this Member ({}) carries no {} field."
    labels = {
        "address": "Alamat Surat-menyurat (correspondence address)",
        "phone": "No. Telefon (telephone)",
        "email": "Email",
    }
    return {
        f"contact.{field}": published.format(profile_url, label)
        for field, label in labels.items()
        if not contact.get(field)
    }


def _divisions_reason(problems: Sequence[tuple[str, str, list[str]]]) -> str:
    """Why this Member's voting record is short of the term's ten Divisions."""
    parts = []
    for sitting, _subject, listed in problems:
        if not listed:
            parts.append(
                f"on {sitting} Hansard names this Seat in none of the Division's four "
                "lists, so no position was recorded for it"
            )
        else:
            parts.append(
                f"on {sitting} Hansard names this Seat in {len(listed)} of the Division's "
                f"four lists ({', '.join(listed)}), which cannot both be right"
            )
    return (
        "This Member's voting record leaves out "
        f"{len(problems)} of the term's Divisions: "
        + "; ".join(parts)
        + ". The four lists partition the House, so a Seat in none or in two of them has "
        "no position on the record, and inferring one from the Chair's declared counts "
        "would put this pipeline's arithmetic next to a named person's vote."
    )


def build_profile(
    seat_code: str,
    members: Mapping[str, Mapping[str, str]],
    details: Mapping[str, str],
    candidates: Sequence[Mapping[str, str]],
    results: Sequence[Mapping[str, str]],
    divisions: Sequence[Mapping[str, Any]],
    problems: Sequence[tuple[str, str, list[str]]],
    bills: Sequence[Mapping[str, Any]],
    term_start: str,
    party_to_coalition_map: Mapping[str, str],
) -> dict[str, Any]:
    """One Seat's profile, with every field traced to the source it came from.

    Raises `SkipSeat` where a check fails, rather than stopping the build:
    one Seat the sources disagree about must not cost the other 221 their
    profiles, and the reason is published alongside them.
    """
    if seat_code not in members:
        raise SkipSeat(
            f"Parliament's Members directory ({MEMBERS_URL}) lists no Member for this "
            "Seat, so there is no official statement of who holds it, what Coalition "
            "they sit for, or how to reach them."
        )
    member = members[seat_code]
    ge15, winner_name, ballot_party = ge15_result(
        candidates, results, seat_code, party_to_coalition_map
    )

    if _name_key(winner_name) != _name_key(member["name"]):
        raise SkipSeat(
            f"Parliament's directory names {member['name']!r} but the GE15 winner was "
            f"{winner_name!r}. Either a by-election has changed the Member — in which "
            "case the GE15 result belongs to their predecessor and must not be shown "
            "under their name — or the two sources write the same person's name "
            "differently enough that this script cannot tell which it is."
        )

    coalition = member["coalition"] or details.get("parti", "")
    page_party = details.get("parti")
    if not coalition:
        raise SkipSeat(
            "Parliament states no Coalition for this Member anywhere: the Members "
            f"directory ({MEMBERS_URL}) leaves this Seat's caucus blank and the "
            f"Member's own profile page ({member['profile_url']}) carries no Parti "
            "field. `MPProfile.coalition` is not optional and nothing else consulted "
            "here is authoritative for it — the GE15 ballot line says what they stood "
            "for in 2022, not what they sit for now."
        )
    if page_party and page_party != coalition:
        raise SkipSeat(
            f"Parliament's Members directory lists this Seat's Coalition as "
            f"{coalition!r} but the Member's own profile page states {page_party!r}. "
            "Parliament disagrees with itself about a named person's Coalition."
        )
    ballot_coalition = coalition_of(ballot_party, party_to_coalition_map)
    if ballot_coalition != coalition:
        raise SkipSeat(
            f"Parliament records this Member's Coalition as {coalition!r}, but they were "
            f"elected in 2022 on the {ballot_party!r} ballot line, which belongs to "
            f"{ballot_coalition!r}. The Member has changed Coalition since GE15, so "
            "their current Coalition and their election result are facts about "
            "different allegiances and are not published side by side as one."
        )

    contact = {
        "address": details.get("alamat surat-menyurat"),
        "phone": details.get("no. telefon"),
        "email": details.get("email"),
        "profile_url": member["profile_url"],
    }

    tabled = sorted(
        {
            bill["title"]
            for bill in bills
            if any(_name_key(member["name"]) in _name_key(tabler) for tabler in bill["tablers"])
        }
    )

    unverified = dict(UNVERIFIED)
    unverified.update(_contact_reasons(contact, member["profile_url"]))
    if problems:
        unverified["divisions"] = _divisions_reason(problems)
    if not tabled:
        unverified["bills_sponsored"] = (
            "Checked against every Bill of this term in Parliament's own Bills register "
            f"({BILLS_URL} and the Arkib behind it) — {len(bills)} Bills first read on or "
            f"after {term_start} — where this Member is named as the tabler of none. "
            "Every one of them was tabled by a Minister, a Deputy Minister or a Senator, "
            "which is a finding rather than a gap: Malaysia has no working private "
            "member's Bill route. Two things the register does not cover, and this cannot "
            "therefore rule out: a Bill withdrawn before its first reading, for which it "
            "publishes neither a date nor a tabler, and Motions a Member files, which it "
            "does not list at all."
        )

    return {
        "name": member["name"],
        "coalition": coalition,
        "term_start": term_start,
        "ge15": ge15,
        "contact": contact,
        "divisions": list(divisions),
        "bills_sponsored": tabled,
        "attendance": None,
        "party": None,
        "unverified": unverified,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--term-start",
        default=None,
        help="The day the Parliament first sat. Read from the portal's calendar if omitted.",
    )
    args = parser.parse_args()

    party_to_coalition_map = party_to_coalition(load_coalition_config())

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        members = fetch_members(client)
        candidates = fetch_csv(client, GE15_CANDIDATES_URL)
        results = fetch_csv(client, GE15_RESULTS_URL)
        names = seat_names(candidates)
        index = _seat_index(names)
        dates = sitting_dates(client)
        term_start = args.term_start or dates[0]
        bills = [
            bill
            for bill in bills_tabled(client)
            if bill["first_reading"] and bill["first_reading"] >= term_start
        ]
        details = {
            code: fetch_member_details(client, member["profile_url"])
            for code, member in sorted(members.items())
        }
        records, problems = divisions_by_seat(client, dates, index)

    profiles: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    for seat_code in sorted(names):
        try:
            profile = build_profile(
                seat_code,
                members,
                details.get(seat_code, {}),
                candidates,
                results,
                records.get(seat_code, ()),
                problems.get(seat_code, ()),
                bills,
                term_start,
                party_to_coalition_map,
            )
        except SkipSeat as reason:
            skipped[seat_code] = f"{names[seat_code]}: {reason}"
            continue
        profiles[seat_code] = profile

    output = {
        "_comment": [
            "One profile per Seat for PolitikKu's constituency lookup (issues #78, #105).",
            f"{len(profiles)} of the {TOTAL_SEATS} Seats; the other {len(skipped)} are in",
            "'_skipped' with the reason each could not be built honestly. See",
            "scripts/build_mp_profiles.py, which generated this file, and ADR 0009 for",
            "what each source does and does not publish. Every optional field left null",
            "is named in that profile's 'unverified' block with the reason;",
            "lpa.config.load_mp_profiles refuses to load a profile that leaves one",
            "unexplained, because an unexplained blank is how an invented value gets in.",
            "A Division's subject is Hansard's own heading, verbatim and in Malay,",
            "rather than a translation this pipeline invented.",
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
                "sittings_swept": len(dates),
            },
            "bills": {
                "name": "Parlimen Malaysia — Rang Undang-Undang register and its Arkib",
                "url": BILLS_URL,
                "archive_url": BILLS_ARCHIVE_URL,
                "bills_this_term": len(bills),
            },
            "retrieved": date.today().isoformat(),
            "generated_by": "scripts/build_mp_profiles.py",
        },
        "_skipped": skipped,
        "profiles": profiles,
    }
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for seat, reason in skipped.items():
        print(f"skipped {seat} — {reason}")
    short = {s: p for s, p in profiles.items() if len(p["divisions"]) != len(DECLARED_RESULTS)}
    for seat, profile in short.items():
        print(f"{seat}: {len(profile['divisions'])} of {len(DECLARED_RESULTS)} Divisions")
    print(
        f"wrote {OUTPUT_PATH}: {len(profiles)} of {TOTAL_SEATS} Seats profiled, "
        f"{len(skipped)} skipped"
    )


if __name__ == "__main__":
    main()
