"""One-off ingestion: build `data/postcode_seat_index.json` (issues #76, #107).

Run by hand, not part of the daily pipeline — Malaysian postcodes and the
Election Commission's delimitation both change on the order of years, and
neither publishes a feed to poll for a diff. Re-run after editing
`MANUAL_TOWN_LOCALITIES` below to add more hand-verified localities.

## Why a join, not one dataset

No single source maps a Malaysian postcode straight to a Parlimen. What
exists, and what this script combines:

1. The Election Commission's own "Senarai BPR" (Bahagian Pilihan Raya) —
   every polling district (*daerah mengundi*) with its Parlimen and DUN,
   under the 2018 delimitation review. This is the primary source the issue
   requires: https://opendata.spr.gov.my/katalog?bahagian=persempadanan,
   served as static JSON at https://opendata.spr.gov.my/data/senarai-bpr.json.
2. `AsyrafHussin/malaysia-postcodes` (MIT) — Pos Malaysia postcode-to-town
   names. Pos Malaysia postcodes were never drawn against electoral
   boundaries, so this is a proxy for "which localities does this postcode
   serve", not an authority on it: https://github.com/AsyrafHussin/malaysia-postcodes

## Two tiers of the join, not one

Issue #76's pilot covered 12 postcodes, entirely by hand-curated town ->
locality lookups (see `MANUAL_TOWN_LOCALITIES` below). Issue #107 asks for
nationwide coverage, and hand-curating a per-locality table for every one of
Malaysia's ~2,900 postcodes the way #76 did for 12 does not scale as
search-and-replace — ADR 0008 says so explicitly, and a full fetch of both
sources confirms it empirically (see "What #107 found" below). This script
therefore resolves each town two ways:

1. **Exact match** (`auto_match_localities`): a Pos Malaysia town name that
   is byte-identical to a daerah mengundi string, up to case and whitespace,
   is not a fuzzy guess — it is the same source asserting the same name twice.
   No human curation is needed to trust it, and none can go stale, because it
   is recomputed against a live fetch every run. This is the tier that scales
   mechanically, and it is what extends #76's 2-Seat pilot to nationwide
   coverage in this pass.
2. **Manual curation** (`MANUAL_TOWN_LOCALITIES`): takes precedence over an
   exact match where both exist, and is the only route to a Seat where no
   exact match exists. A town needs curation either because its name does not
   exactly match any daerah mengundi — most commonly because the town is a
   city/district name that spans many daerah mengundi across possibly several
   Parlimen ("Johor Bahru", "Alor Setar"), or because it is a genuine alias
   ("Bandar Baru Bangi" for "SEKSYEN 1 BBB" etc.) — or because it does match
   but a human already found the exact-match set to be over- or
   under-inclusive for that specific town (see "Kajang" in
   `MANUAL_TOWN_LOCALITIES`, curated to exclude "PENJARA KAJANG" even though
   it shares the town name). This script keeps #76's original hand-verified
   Selangor table but does not attempt to extend it: a naive substring or
   fuzzy match here risks exactly the false ambiguity this project has always
   refused to assert (see the docstring on `MANUAL_TOWN_LOCALITIES`), and
   inventing per-city curation for hundreds of towns without the same
   verification #76 did would be guessing, not sourcing.

Towns that fall into neither tier are recorded in
`data/postcode_seat_index_unresolved.json` — not fabricated a Seat, and not
silently dropped either, so the manual-curation follow-up ADR 0008 already
anticipates has a concrete, sourced starting list rather than starting from
zero.

## What #107 found, at full scale

Fetching both sources whole (not just Selangor) and comparing every Pos
Malaysia town name against every daerah mengundi in its own state:

- 7,748 daerah mengundi rows (222 Parlimen) in the Election Commission data,
  matching ADR 0008's figure. 141 daerah mengundi strings, nationwide, are not
  unique within their own state — the same name appears under two or more
  different Parlimen (e.g. Johor's "BUKIT PASIR" under both P.143 Pagoh and
  P.150 Batu Pahat). `fetch_spr_data` keeps every one of those, so a town
  that exact-matches such a daerah correctly comes out multi-Seat rather
  than silently keeping only one. Separately, 4 towns exact-match a daerah
  under one Parlimen while a *different* Parlimen in the same state is
  itself named after the town ("Sungai Buloh", "Ayer Hitam", "Pokok Sena",
  "Ranau") — `auto_match_localities` treats these as unresolved rather than
  asserting the single Seat the daerah match alone would suggest.
- 2,929 unique postcodes across 444 Pos Malaysia towns, 16 states/territories.
- Of those 444 towns, 174 exact-match a daerah mengundi string cleanly (178
  match by name, but 4 of those — see above — collide with a same-named
  Parlimen and are held back as unresolved instead). Combined with #76's
  original 7-town hand-curated Selangor table (4 of which — "Semenyih",
  "Hulu Langat", "Bandar Baru Bangi", "Cheras" — have no exact match at all),
  this pass resolves 339 postcodes (about 12% of the national total) across
  113 distinct Seats, leaving 266 towns (2,594 postcodes, with overlap where
  a postcode also has a resolved town) unresolved.

The unmatched are overwhelmingly town/city names one administrative level up
from a daerah mengundi (e.g. "Johor Bahru", "Kluang", "Alor Setar") rather
than near-misses in spelling — the same shape of gap ADR 0008 predicted when
it said scaling "does not scale by search-and-replace, it needs the same
per-locality verification repeated for every Seat". Resolving them needs a
human checking, per town, which of the (often many) daerah mengundi that
share its city actually correspond to Pos Malaysia's postcode boundary for
that town — exactly #76's original curation step, at roughly 35x the item
count. That is follow-up work, not a decision this script can make
unsupervised.

## Why the town->locality join is curated, not fuzzy-matched

A Pos Malaysia town name ("Bandar Baru Bangi") rarely appears verbatim as a
daerah mengundi ("SEKSYEN 1 BBB", "SEKSYEN 7,8 DAN 9 BBB"); a naive substring
match either misses real matches or pulls in unrelated ones (e.g. matching
bare "Kajang" against "PENJARA KAJANG" — Kajang Prison — would assert an
ambiguity this script has no evidence for). `MANUAL_TOWN_LOCALITIES` below is
a hand-verified table: each town name is mapped to the exact daerah mengundi
strings a human checked against the live SPR dataset. The script's own job is
just to resolve each of those exact strings to its Parlimen and fail loudly
if one no longer exists in the source — so a typo here is caught at build
time, not shipped silently.

## Scope

Nationwide, in two tiers (see above): every exact town/daerah match across
all 16 states/territories, plus #76's original hand-curated Selangor
entries. The ~266 towns that resolve to neither tier are listed, with their
postcode counts, in `data/postcode_seat_index_unresolved.json` for follow-up
curation — see `docs/adr/0008-postcode-seat-index-is-a-join-not-a-single-source.md`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx

SPR_SENARAI_BPR_URL = "https://opendata.spr.gov.my/data/senarai-bpr.json"
POSTCODE_SOURCE_URL = (
    "https://raw.githubusercontent.com/AsyrafHussin/malaysia-postcodes/master/all.json"
)

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "postcode_seat_index.json"
UNRESOLVED_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "postcode_seat_index_unresolved.json"
)

# Pos Malaysia state name (as `all.json` spells it) -> the Election
# Commission's "Negeri" spelling (as `senarai-bpr.json` spells it). Every key
# here is one of the 16 states/territories both sources cover.
POS_MALAYSIA_STATE_TO_NEGERI: dict[str, str] = {
    "Johor": "JOHOR",
    "Kedah": "KEDAH",
    "Kelantan": "KELANTAN",
    "Melaka": "MELAKA",
    "Negeri Sembilan": "NEGERI SEMBILAN",
    "Pahang": "PAHANG",
    "Perak": "PERAK",
    "Perlis": "PERLIS",
    "Pulau Pinang": "PULAU PINANG",
    "Sabah": "SABAH",
    "Sarawak": "SARAWAK",
    "Selangor": "SELANGOR",
    "Terengganu": "TERENGGANU",
    "Wp Kuala Lumpur": "W.P KUALA LUMPUR",
    "Wp Labuan": "W.P LABUAN",
    "Wp Putrajaya": "W.P PUTRAJAYA",
}

# A readable display name for each Negeri, for `_seats[code]["state"]` — the
# SPR spelling above is shouted-caps for exact matching, not for display.
NEGERI_DISPLAY_NAMES: dict[str, str] = {
    "JOHOR": "Johor",
    "KEDAH": "Kedah",
    "KELANTAN": "Kelantan",
    "MELAKA": "Melaka",
    "NEGERI SEMBILAN": "Negeri Sembilan",
    "PAHANG": "Pahang",
    "PERAK": "Perak",
    "PERLIS": "Perlis",
    "PULAU PINANG": "Pulau Pinang",
    "SABAH": "Sabah",
    "SARAWAK": "Sarawak",
    "SELANGOR": "Selangor",
    "TERENGGANU": "Terengganu",
    "W.P KUALA LUMPUR": "W.P. Kuala Lumpur",
    "W.P LABUAN": "W.P. Labuan",
    "W.P PUTRAJAYA": "W.P. Putrajaya",
}

# Pos Malaysia town name -> the exact `DAERAH MENGUNDI` strings (from
# SPR_SENARAI_BPR_URL) verified by hand to be that town, kept verbatim from
# #76's original Selangor pilot (verified 2026-08-24 against a live fetch of
# the source). Of these seven, "Bangi", "Kajang", and "Beranang" happen to
# also exact-match a daerah mengundi (`auto_match_localities` would find
# "Bangi" and "Beranang" on its own), but "Kajang" is deliberately curated to
# a *narrower* set — ["KAJANG", "BANDAR KAJANG"] — than exact match alone
# would give, excluding "PENJARA KAJANG" (Kajang Prison, which SPR's data
# places in a different DUN) even though it shares the town name; auto-match
# cannot tell that apart the way this hand check did. "Semenyih" and "Hulu
# Langat" have *no* exact match at all (their daerah mengundi are compound
# names — "SEMENYIH BARAT" etc., "BATU 14 HULU LANGAT" — never the bare town
# name), and "Bandar Baru Bangi" and "Cheras" likewise don't exact-match.
# This table stays authoritative over the auto-match tier for every key it
# defines (`build_index` prefers it), so none of the seven can be dropped as
# "redundant" with a broader auto-match result — for four of the seven,
# there is no auto-match result to be redundant with.
#
# Extending this table to other states means repeating the same per-locality
# verification against a live fetch of SPR_SENARAI_BPR_URL — see the module
# docstring's "What #107 found" for why that is follow-up work, not done in
# this pass.
MANUAL_TOWN_LOCALITIES: dict[str, dict[str, list[str]]] = {
    "SELANGOR": {
        "Bangi": ["BANGI"],
        "Bandar Baru Bangi": [
            "SEKSYEN 1 BBB",
            "SEKSYEN 2 BBB",
            "SEKSYEN 3 BBB",
            "SEKSYEN 4 BBB",
            "SEKSYEN 5 BBB",
            "SEKSYEN 6 BBB",
            "SEKSYEN 7,8 DAN 9 BBB",
        ],
        # Deliberately excludes "PENJARA KAJANG" (Kajang Prison), which the
        # SPR data places in P.101's Semenyih DUN, not P.102's Kajang DUN:
        # nothing sourced here ties the prison to these postcodes rather than
        # another, so asserting that ambiguity would be a guess, not a
        # finding.
        "Kajang": ["KAJANG", "BANDAR KAJANG"],
        "Semenyih": ["SEMENYIH BARAT", "SEMENYIH SELATAN", "SEMENYIH INDAH", "PEKAN SEMENYIH"],
        "Beranang": ["BERANANG", "KAMPUNG BATU 26 BERANANG"],
        "Hulu Langat": ["BATU 14 HULU LANGAT"],
        # Genuinely ambiguous: "Cheras" daerah mengundi exist under both
        # Seats (P.101's Dusun Tua DUN and P.102's Balakong DUN), and the
        # postcode dataset gives no finer locality than the town name to
        # tell them apart.
        "Cheras": [
            "BATU 9 CHERAS",
            "TAMAN KOTA CHERAS",
            "BATU 10 CHERAS",
            "BATU 11 CHERAS",
            "CHERAS PERDANA",
            "CHERAS JAYA",
        ],
    },
}


def _normalize(name: str) -> str:
    """Case/whitespace-fold a locality name for exact-match comparison."""
    return " ".join(name.strip().upper().split())


def _split_parlimen(label: str) -> tuple[str, str]:
    """Split a "P.102   BANGI" SPR label into its code and title-cased name."""
    code, _, name = label.strip().partition(" ")
    return code, name.strip().title()


def fetch_spr_data(
    client: httpx.Client,
) -> tuple[dict[str, dict[str, list[tuple[str, str]]]], dict[str, dict[str, str]]]:
    """Fetch the Election Commission's data once, indexed two ways by Negeri.

    Returns `(daerah_to_parlimen_by_state, parlimen_code_by_name_by_state)`.

    `daerah_to_parlimen_by_state`: every daerah mengundi -> its (Seat code,
    Seat name). A daerah mengundi string is not always unique within a
    state: 141 of them, nationwide, appear under more than one Parlimen —
    e.g. Johor's "BUKIT PASIR" sits under both P.143 Pagoh and P.150 Batu
    Pahat. That is the same kind of genuine ambiguity the pilot's Cheras
    entry recorded by hand, just visible one level lower (the daerah name
    itself, not only the town name above it), so every match here is kept as
    a list rather than collapsed to one Parlimen by whichever row happened
    to be seen last.

    `parlimen_code_by_name_by_state`: every Parlimen's own (case/whitespace
    folded) name -> its code, used by `auto_match_localities` to catch a
    narrower failure mode of exact matching — see its docstring.
    """
    rows = client.get(SPR_SENARAI_BPR_URL).raise_for_status().json()
    daerah_by_state: dict[str, dict[str, list[tuple[str, str]]]] = {}
    parlimen_by_state: dict[str, dict[str, str]] = {}
    for row in rows:
        code, name = _split_parlimen(row["PARLIMEN"])
        daerah_by_state.setdefault(row["Negeri"], {}).setdefault(
            row["DAERAH MENGUNDI"], []
        ).append((code, name))
        parlimen_by_state.setdefault(row["Negeri"], {})[_normalize(name)] = code
    return daerah_by_state, parlimen_by_state


def fetch_town_postcodes_by_state(client: httpx.Client) -> dict[str, dict[str, list[str]]]:
    """Pos Malaysia town name -> its postcode(s), by Pos Malaysia state name."""
    payload = client.get(POSTCODE_SOURCE_URL).raise_for_status().json()
    return {
        state["name"]: {city["name"]: city["postcode"] for city in state["city"]}
        for state in payload["state"]
    }


def auto_match_localities(
    town_postcodes: dict[str, list[str]],
    daerah_to_parlimen: dict[str, list[tuple[str, str]]],
    parlimen_codes_by_name: dict[str, str],
) -> tuple[dict[str, list[str]], list[str]]:
    """Exact-match (case/whitespace-folded) town names against daerah mengundi.

    A town name that is byte-identical to a daerah mengundi string, once
    case and whitespace are folded, needs no human curation to trust: it is
    the same locality name from two sources agreeing, not a guess — *unless*
    a different Parlimen in the same state is itself named after the town
    (e.g. "Sungai Buloh" exact-matches a daerah under P.106 Damansara, but
    P.107 is named "Sungai Buloh"). Under that condition either the exact
    match latched onto a same-named daerah in the wrong Parlimen, or the town
    genuinely straddles both — neither supports the single Seat an unqualified
    exact match would assert, so these are treated as unmatched rather than
    guessed at, the same as any other town needing hand curation.

    Returns `(town -> matching daerah mengundi strings, towns with no exact
    match)` — the second list is not silently dropped, see `main`.
    """
    daerah_by_normalized: dict[str, list[str]] = {}
    for daerah in daerah_to_parlimen:
        daerah_by_normalized.setdefault(_normalize(daerah), []).append(daerah)

    matched: dict[str, list[str]] = {}
    unmatched: list[str] = []
    for town in town_postcodes:
        town_normalized = _normalize(town)
        localities = daerah_by_normalized.get(town_normalized)
        if not localities:
            unmatched.append(town)
            continue
        matched_codes = {code for loc in localities for code, _ in daerah_to_parlimen[loc]}
        same_named_parlimen = parlimen_codes_by_name.get(town_normalized)
        if same_named_parlimen is not None and same_named_parlimen not in matched_codes:
            unmatched.append(town)
            continue
        matched[town] = localities
    return matched, unmatched


def build_state_index(
    town_localities: dict[str, list[str]],
    town_postcodes: dict[str, list[str]],
    daerah_to_parlimen: dict[str, list[tuple[str, str]]],
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Join one state's town->locality data against its SPR lookup.

    Returns `(postcode -> Seat codes, Seat code -> Seat name)`. Raises if a
    curated locality string is no longer in the SPR data, or a curated town
    is no longer in the postcode data — both mean `town_localities` is stale,
    not that the postcode has no Seat. A locality that resolves to more than
    one Parlimen (see `fetch_daerah_to_parlimen_by_state`) contributes every
    one of them, not just the first.
    """
    postcode_seats: dict[str, set[str]] = {}
    seat_names: dict[str, str] = {}
    for town, localities in town_localities.items():
        if town not in town_postcodes:
            raise ValueError(f"{town!r} is not a town in the fetched postcode data")
        codes: set[str] = set()
        for locality in localities:
            if locality not in daerah_to_parlimen:
                raise ValueError(
                    f"{locality!r} (mapped from {town!r}) is not a daerah mengundi "
                    f"in the fetched SPR data — town_localities may be stale"
                )
            for code, name in daerah_to_parlimen[locality]:
                codes.add(code)
                seat_names[code] = name
        for postcode in town_postcodes[town]:
            postcode_seats.setdefault(postcode, set()).update(codes)

    return postcode_seats, seat_names


def build_index(
    town_postcodes_by_state: dict[str, dict[str, list[str]]],
    daerah_to_parlimen_by_state: dict[str, dict[str, list[tuple[str, str]]]],
    parlimen_codes_by_name_by_state: dict[str, dict[str, str]],
    manual_town_localities: dict[str, dict[str, list[str]]],
) -> tuple[dict[str, list[str]], dict[str, dict[str, str]], dict[str, dict[str, int]]]:
    """Join every state's postcode data against its SPR lookup.

    Returns `(postcode -> sorted Seat codes, Seat code -> {name, state},
    Negeri -> {unresolved town -> its postcode count})`. A postcode's own
    entry only needs `seat_code` (see `lpa.postcode_index.SeatMatch`), the
    same way `SeatCall` carries a Seat's `code` alone rather than copying its
    name everywhere it appears.

    Raises if a state `POS_MALAYSIA_STATE_TO_NEGERI` names is missing from
    the fetched SPR data — that means the mapping has gone stale (the
    Election Commission's Negeri spelling changed, or a territory dropped
    out of the feed), not that the state simply has no data this run.
    """
    postcode_seats: dict[str, set[str]] = {}
    seats: dict[str, dict[str, str]] = {}
    unresolved_by_state: dict[str, dict[str, int]] = {}

    for pos_malaysia_state, negeri in POS_MALAYSIA_STATE_TO_NEGERI.items():
        town_postcodes = town_postcodes_by_state[pos_malaysia_state]
        if negeri not in daerah_to_parlimen_by_state:
            raise ValueError(
                f"{negeri!r} (mapped from {pos_malaysia_state!r}) is not a Negeri in the "
                f"fetched SPR data — POS_MALAYSIA_STATE_TO_NEGERI may be stale"
            )
        daerah_to_parlimen = daerah_to_parlimen_by_state[negeri]
        parlimen_codes_by_name = parlimen_codes_by_name_by_state.get(negeri, {})

        auto_localities, unmatched = auto_match_localities(
            town_postcodes, daerah_to_parlimen, parlimen_codes_by_name
        )
        town_localities = {**auto_localities, **manual_town_localities.get(negeri, {})}
        unmatched = [town for town in unmatched if town not in town_localities]

        state_postcode_seats, seat_names = build_state_index(
            town_localities, town_postcodes, daerah_to_parlimen
        )
        for postcode, codes in state_postcode_seats.items():
            postcode_seats.setdefault(postcode, set()).update(codes)
        for code, name in seat_names.items():
            seats[code] = {"name": name, "state": NEGERI_DISPLAY_NAMES[negeri]}
        if unmatched:
            unresolved_by_state[NEGERI_DISPLAY_NAMES[negeri]] = {
                town: len(town_postcodes[town]) for town in sorted(unmatched)
            }

    index = {postcode: sorted(codes) for postcode, codes in postcode_seats.items()}
    return index, seats, unresolved_by_state


def main() -> None:
    with httpx.Client(timeout=30.0) as client:
        daerah_to_parlimen_by_state, parlimen_codes_by_name_by_state = fetch_spr_data(client)
        town_postcodes_by_state = fetch_town_postcodes_by_state(client)

    index, seats, unresolved_by_state = build_index(
        town_postcodes_by_state,
        daerah_to_parlimen_by_state,
        parlimen_codes_by_name_by_state,
        MANUAL_TOWN_LOCALITIES,
    )

    output = {
        "_comment": [
            "Postcode -> candidate Seat code(s), for the constituency lookup",
            "(issues #76, #107). See scripts/build_postcode_seat_index.py, which",
            "generated this file, for the two-tier join method (exact match plus",
            "hand-curated aliases) and for exactly which sources justify each",
            "entry. A postcode with more than one Seat is genuinely ambiguous:",
            "Malaysian postcodes were not drawn against electoral boundaries, so a",
            "single postcode can serve localities that fall in different Seats.",
            "`_seats` names each code once; a postcode entry carries the code",
            "alone so the two cannot disagree. Towns this pass could not resolve",
            "(no exact match and no hand-curated entry) are listed, with their",
            "postcode counts, in postcode_seat_index_unresolved.json alongside",
            "this file — not fabricated a Seat, and not silently dropped either.",
        ],
        "_source": {
            "delimitation": {
                "name": (
                    "Suruhanjaya Pilihan Raya (SPR) — Senarai Bahagian Pilihan Raya "
                    "(BPR), 2018 delimitation review"
                ),
                "portal_url": "https://opendata.spr.gov.my/katalog?bahagian=persempadanan",
                "dataset_url": SPR_SENARAI_BPR_URL,
            },
            "postcode_locality": {
                "name": "AsyrafHussin/malaysia-postcodes (MIT)",
                "url": "https://github.com/AsyrafHussin/malaysia-postcodes",
                "dataset_url": POSTCODE_SOURCE_URL,
            },
            "retrieved": date.today().isoformat(),
            "generated_by": "scripts/build_postcode_seat_index.py",
        },
        "_seats": dict(sorted(seats.items())),
        "postcodes": dict(sorted(index.items())),
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    total_unresolved_towns = sum(len(towns) for towns in unresolved_by_state.values())
    total_unresolved_postcodes = sum(
        count for towns in unresolved_by_state.values() for count in towns.values()
    )
    unresolved_output = {
        "_comment": [
            "Pos Malaysia town names that neither exact-matched a daerah mengundi",
            "(cleanly, or without colliding with a same-named Parlimen — see",
            "auto_match_localities) nor have a hand-curated entry in",
            "MANUAL_TOWN_LOCALITIES, as of the last run of",
            "scripts/build_postcode_seat_index.py (issue #107). Not a bug: most of",
            "these are city/district names one level up from a daerah mengundi",
            "(e.g. 'Johor Bahru' spans many daerah, likely across several",
            "Parlimen), and asserting a Seat for them without the same",
            "per-locality verification issue #76 did for its pilot would be a",
            "guess, not a finding. Follow-up curation work — see ADR 0008 and the",
            "'What #107 found' section of the build script's docstring — starts",
            "from this list rather than from zero. Each town's value is its own",
            "postcode count, from the Pos Malaysia source, not a Seat count.",
        ],
        "retrieved": date.today().isoformat(),
        "town_count": total_unresolved_towns,
        "postcode_count": total_unresolved_postcodes,
        "by_state": dict(sorted(unresolved_by_state.items())),
    }
    UNRESOLVED_PATH.write_text(
        json.dumps(unresolved_output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        f"wrote {len(index)} postcodes across {len(seats)} Seats to {OUTPUT_PATH}\n"
        f"wrote {total_unresolved_towns} unresolved towns across "
        f"{len(unresolved_by_state)} states to {UNRESOLVED_PATH}"
    )


if __name__ == "__main__":
    main()
