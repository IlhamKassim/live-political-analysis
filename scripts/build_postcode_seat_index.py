"""One-off ingestion: build `data/postcode_seat_index.json` (issue #76).

Run by hand, not part of the daily pipeline — Malaysian postcodes and the
Election Commission's delimitation both change on the order of years, and
neither publishes a feed to poll for a diff. Re-run after editing
`TOWN_LOCALITIES` below to extend the pilot slice to more Seats.

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

## Why the town→locality join is curated, not fuzzy-matched

A Pos Malaysia town name ("Bandar Baru Bangi") rarely appears verbatim as a
daerah mengundi ("SEKSYEN 1 BBB", "SEKSYEN 7,8 DAN 9 BBB"); a naive substring
match either misses real matches or pulls in unrelated ones (e.g. matching
bare "Kajang" against "PENJARA KAJANG" — Kajang Prison — would assert an
ambiguity this script has no evidence for). `TOWN_LOCALITIES` below is a
hand-verified table: each town name is mapped to the exact daerah mengundi
strings a human checked against the live SPR dataset. The script's own job is
just to resolve each of those exact strings to its Parlimen and fail loudly
if one no longer exists in the source — so a typo here is caught at build
time, not shipped silently.

## Scope

Pilot slice only: Selangor's P.101 Hulu Langat and P.102 Bangi, the two Seats
`#78`'s MP-profile pilot already scopes to. Scaling to all 222 Seats is
follow-up work (see the module docstring on `lpa.postcode_index` and ADR
0008) — the curation step above does not scale by search-and-replace, it
needs the same per-locality verification repeated for every Seat.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx

SPR_SENARAI_BPR_URL = "https://opendata.spr.gov.my/data/senarai-bpr.json"
POSTCODE_SOURCE_URL = (
    "https://raw.githubusercontent.com/AsyrafHussin/malaysia-postcodes/master/selangor.json"
)

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "postcode_seat_index.json"

# Pos Malaysia town name -> the exact `DAERAH MENGUNDI` strings (from
# SPR_SENARAI_BPR_URL) verified by hand to be that town, restricted to the
# pilot's two Seats. Verified 2026-08-24 against a live fetch of the source.
TOWN_LOCALITIES: dict[str, list[str]] = {
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
    # Deliberately excludes "PENJARA KAJANG" (Kajang Prison), which the SPR
    # data places in P.101's Semenyih DUN, not P.102's Kajang DUN: nothing
    # sourced here ties the prison to these postcodes rather than another, so
    # asserting that ambiguity would be a guess, not a finding.
    "Kajang": ["KAJANG", "BANDAR KAJANG"],
    "Semenyih": ["SEMENYIH BARAT", "SEMENYIH SELATAN", "SEMENYIH INDAH", "PEKAN SEMENYIH"],
    "Beranang": ["BERANANG", "KAMPUNG BATU 26 BERANANG"],
    "Hulu Langat": ["BATU 14 HULU LANGAT"],
    # Genuinely ambiguous: "Cheras" daerah mengundi exist under both Seats
    # (P.101's Dusun Tua DUN and P.102's Balakong DUN), and the postcode
    # dataset gives no finer locality than the town name to tell them apart.
    "Cheras": [
        "BATU 9 CHERAS",
        "TAMAN KOTA CHERAS",
        "BATU 10 CHERAS",
        "BATU 11 CHERAS",
        "CHERAS PERDANA",
        "CHERAS JAYA",
    ],
}


def _split_parlimen(label: str) -> tuple[str, str]:
    """Split a "P.102   BANGI" SPR label into its code and title-cased name."""
    code, _, name = label.strip().partition(" ")
    return code, name.strip().title()


def fetch_daerah_to_parlimen(client: httpx.Client, state: str) -> dict[str, tuple[str, str]]:
    """Every daerah mengundi in `state`, mapped to its (Seat code, Seat name)."""
    rows = client.get(SPR_SENARAI_BPR_URL).raise_for_status().json()
    return {
        row["DAERAH MENGUNDI"]: _split_parlimen(row["PARLIMEN"])
        for row in rows
        if row["Negeri"] == state
    }


def fetch_town_postcodes(client: httpx.Client, state_json_url: str) -> dict[str, list[str]]:
    """Pos Malaysia town name -> its postcode(s), for one state file."""
    payload = client.get(state_json_url).raise_for_status().json()
    return {city["name"]: city["postcode"] for city in payload["city"]}


def build_index(
    town_localities: dict[str, list[str]],
    town_postcodes: dict[str, list[str]],
    daerah_to_parlimen: dict[str, tuple[str, str]],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Join curated town->locality data against the live SPR lookup.

    Returns `(postcode -> sorted Seat codes, Seat code -> Seat name)`. Seat
    name is returned once per code, not per postcode: a postcode's own entry
    only needs `seat_code` (see `lpa.postcode_index.SeatMatch`), the same way
    `SeatCall` carries a Seat's `code` alone rather than copying its name
    everywhere it appears.

    Raises if a curated locality string is no longer in the SPR data, or a
    curated town is no longer in the postcode data — both mean
    `TOWN_LOCALITIES` is stale, not that the postcode has no Seat.
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
                    f"in the fetched SPR data — TOWN_LOCALITIES may be stale"
                )
            code, name = daerah_to_parlimen[locality]
            codes.add(code)
            seat_names[code] = name
        for postcode in town_postcodes[town]:
            postcode_seats.setdefault(postcode, set()).update(codes)

    index = {postcode: sorted(codes) for postcode, codes in postcode_seats.items()}
    return index, seat_names


def main() -> None:
    state = "Selangor"
    with httpx.Client(timeout=30.0) as client:
        daerah_to_parlimen = fetch_daerah_to_parlimen(client, state=state.upper())
        town_postcodes = fetch_town_postcodes(client, POSTCODE_SOURCE_URL)

    index, seat_names = build_index(TOWN_LOCALITIES, town_postcodes, daerah_to_parlimen)

    output = {
        "_comment": [
            "Postcode -> candidate Seat code(s), for the constituency lookup",
            "(issue #76). Pilot slice: Selangor P.101 Hulu Langat and P.102 Bangi",
            "only — see scripts/build_postcode_seat_index.py, which generated this",
            "file, for the method and TOWN_LOCALITIES for exactly which sources",
            "justify each entry. A postcode with more than one Seat is genuinely",
            "ambiguous: Malaysian postcodes were not drawn against electoral",
            "boundaries, so a single postcode can serve localities that fall in",
            "different Seats. `_seats` names each code once; a postcode entry",
            "carries the code alone so the two cannot disagree.",
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
        "_seats": {
            code: {"name": name, "state": state} for code, name in sorted(seat_names.items())
        },
        "postcodes": dict(sorted(index.items())),
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(index)} postcodes across {len(seat_names)} Seats to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
