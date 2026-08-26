"""The constituency lookup's client-side data (issue #77).

The design handoff's privacy promise — "Location is read in your browser
and never sent to us" — extends to postcode/name lookup too (README's
"State Management": "The lookup itself needs a postcode → Seat index
shipped to the client... plus one MP-profile document per Seat"): resolving
a postcode to a Seat happens entirely in the browser, against a small
static JSON this module builds, never a server round-trip. ADR 0008 already
sized the postcode→Seat payload alone at ~22 bytes/postcode; this module
adds just enough Seat identity (name, state) and MP-profile availability for
`ts/src/`'s lookup module to render a candidate row and route a resolved
match, without shipping anything Storage doesn't already hold.

`code`/`name`/`state` are read from `SeatBaseline` (Storage), not
`data/postcode_seat_index.json`'s own `_seats` block — that block is a
convenience for the file's own readability (see `lpa.postcode_index`'s
module docstring), and `SeatBaseline` is the one place those three facts
are guaranteed to agree with every other page built from the same
Baseline.

`has_profile` is computed from `lpa.config.load_mp_profiles()`'s actual
keys, not hardcoded. #105 took profiles from one Seat to most of the House,
so today every Seat the postcode pilot (#76, Selangor P.101/P.102) can
return does have one — but the flag stays, and stays computed, because the
two slices are still independent: profiles stop at the Seats Parliament's
own sources support (see `data/mp_profiles.json`'s `_skipped`), and the
postcode index will grow past them. `ts/src/dom.ts` reads this flag to
degrade gracefully instead of linking to a page that doesn't exist.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from lpa.domain import SeatBaseline


@dataclass(frozen=True)
class LookupSeat:
    """One Seat as the client-side lookup index states it."""

    code: str
    name: str
    state: str
    has_profile: bool
    """Whether `/mp/<code>.html` was actually built this run."""
    mp_name: str | None
    """The sitting Member's name, where a profile exists — `None` (not an
    empty string) when it doesn't, so the client can tell "no data" from
    "MP profile publishes no name", which cannot currently happen but
    shouldn't be conflated with this if it ever does."""


DEFAULT_OUTPUT_PATH = "public/data/lookup-index.json"
DEFAULT_UNRESOLVED_PATH = "data/lookup_index_unresolved_profiles.json"


@dataclass(frozen=True)
class LookupIndexBuildResult:
    """Summary of client lookup index generation."""

    size_bytes: int
    total_mp_profiles: int
    reachable_mp_profiles: int
    excluded_mp_profiles: int


def compute_unresolved_mp_profiles(
    mp_names: Mapping[str, str],
    client_index_seats: Mapping[str, object],
) -> dict[str, str]:
    """Return `{code: member_name}` for all MP profiles omitted from the client index."""
    return {code: mp_names[code] for code in sorted(mp_names) if code not in client_index_seats}


def build_client_index(
    baseline: Sequence[SeatBaseline],
    postcode_index: Mapping[str, Sequence[str]],
    mp_names: Mapping[str, str],
) -> dict[str, object]:
    """Everything `ts/src/index-data.ts` needs, as one small JSON-able dict.

    `postcode_index` is postcode -> Seat code(s), already the shape
    `lpa.postcode_index`/`lpa.config.load_postcode_seat_index` produce (the
    caller flattens `SeatMatch` to bare codes — this module states data,
    not the domain types that describe how it's found). `mp_names` is Seat
    code -> the sitting Member's name, from `lpa.config.load_mp_profiles()`
    (only codes with an actual profile are present).

    Raises `ValueError` if a postcode names a Seat with no Baseline.
    """
    by_code = {seat.code: seat for seat in baseline}
    referenced_codes = {code for codes in postcode_index.values() for code in codes}
    for code in referenced_codes:
        if code not in by_code:
            raise ValueError(f"postcode index names Seat {code!r}, which has no Seat Baseline")

    seats = {
        code: LookupSeat(
            code=code,
            name=by_code[code].name,
            state=by_code[code].state,
            has_profile=code in mp_names,
            mp_name=mp_names.get(code),
        )
        for code in sorted(referenced_codes)
    }
    return {
        "seats": {
            code: {
                "code": seat.code,
                "name": seat.name,
                "state": seat.state,
                "hasProfile": seat.has_profile,
                "mpName": seat.mp_name,
            }
            for code, seat in seats.items()
        },
        "postcodes": {postcode: list(codes) for postcode, codes in postcode_index.items()},
    }


def build_client_index_json(
    baseline: Sequence[SeatBaseline],
    postcode_index: Mapping[str, Sequence[str]],
    mp_names: Mapping[str, str],
) -> str:
    """`build_client_index`'s result, serialised compactly (this ships to
    every visitor's browser on every page load, per ADR 0008's size math)."""
    return json.dumps(build_client_index(baseline, postcode_index, mp_names), separators=(",", ":"))


# ── I/O ───────────────────────────────────────────────────────────────────


def build_and_write_client_index(
    engine: Engine,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    unresolved_path: str | Path | None = DEFAULT_UNRESOLVED_PATH,
) -> LookupIndexBuildResult:
    """Read Storage/config and write the client index and unresolved report.

    Writes the client index to `output_path` and durable unresolved profiles
    report to `unresolved_path` (issue #118), so exclusions are visible to
    maintainers without diffing raw data files.
    """
    from lpa.config import load_mp_profiles, load_postcode_seat_index
    from lpa.storage import load_seat_baselines

    baseline = load_seat_baselines(engine)
    raw_postcode_index = load_postcode_seat_index()
    postcode_index = {
        postcode: tuple(m.seat_code for m in matches)
        for postcode, matches in raw_postcode_index.items()
    }
    mp_names = {code: profile.name for code, profile in load_mp_profiles().items()}

    index_data = build_client_index(baseline, postcode_index, mp_names)
    payload = json.dumps(index_data, separators=(",", ":"))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")

    client_seats = index_data.get("seats", {})
    assert isinstance(client_seats, dict)
    excluded_profiles = compute_unresolved_mp_profiles(mp_names, client_seats)
    total_profiles = len(mp_names)
    reachable_profiles = total_profiles - len(excluded_profiles)

    if unresolved_path is not None:
        unresolved_file = Path(unresolved_path)
        unresolved_file.parent.mkdir(parents=True, exist_ok=True)
        unresolved_report = {
            "_comment": [
                "MP Profiles (from data/mp_profiles.json) whose Seats are not reachable from",
                "the postcode index (data/postcode_seat_index.json) and are therefore omitted",
                "from the client-side lookup index (public/data/lookup-index.json).",
                "Generated automatically on every build of lpa.politikku_lookup_index (issue #118).",
            ],
            "total_mp_profiles": total_profiles,
            "reachable_mp_profiles": reachable_profiles,
            "excluded_count": len(excluded_profiles),
            "unresolved_mp_profiles": excluded_profiles,
        }
        unresolved_file.write_text(
            json.dumps(unresolved_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return LookupIndexBuildResult(
        size_bytes=len(payload.encode("utf-8")),
        total_mp_profiles=total_profiles,
        reachable_mp_profiles=reachable_profiles,
        excluded_mp_profiles=len(excluded_profiles),
    )


def main() -> None:
    """Write the client lookup index and report reachability metrics."""
    import argparse

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help=f"where to write the client index (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--unresolved-output",
        default=DEFAULT_UNRESOLVED_PATH,
        help=f"where to write the unresolved MP profiles report (default: {DEFAULT_UNRESOLVED_PATH})",
    )
    args = parser.parse_args()

    engine = connect()
    result = build_and_write_client_index(engine, args.output, args.unresolved_output)
    print(
        f"Wrote {args.output} ({result.size_bytes:,} bytes) — "
        f"{result.reachable_mp_profiles}/{result.total_mp_profiles} MP Profiles reachable "
        f"({result.excluded_mp_profiles} excluded)"
    )


if __name__ == "__main__":
    main()
