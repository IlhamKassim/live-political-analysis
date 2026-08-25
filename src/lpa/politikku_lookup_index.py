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
keys, not hardcoded: the postcode pilot (#76, Selangor P.101/P.102) and the
MP-profile pilot (#78, Bangi/P.102 only) cover different Seats, so a
lookup can genuinely resolve to a Seat with no profile page built yet
(P.101 today). `ts/src/dom.ts` reads this flag to degrade gracefully
instead of linking to a page that doesn't exist.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from lpa.domain import SeatBaseline


@dataclass(frozen=True)
class LookupSeat:
    """One Seat as the client-side lookup index states it."""

    code: str
    name: str
    state: str
    has_profile: bool
    """Whether `/politikku/mp/<code>.html` was actually built this run."""
    mp_name: str | None
    """The sitting Member's name, where a profile exists — `None` (not an
    empty string) when it doesn't, so the client can tell "no data" from
    "MP profile publishes no name", which cannot currently happen but
    shouldn't be conflated with this if it ever does."""


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

    Raises `ValueError` if a postcode names a Seat with no Baseline, or if
    `mp_names` names a Seat the postcode index never mentions — either
    would mean the published index quietly promised more than it can back
    up.
    """
    by_code = {seat.code: seat for seat in baseline}
    referenced_codes = {code for codes in postcode_index.values() for code in codes}
    for code in referenced_codes:
        if code not in by_code:
            raise ValueError(f"postcode index names Seat {code!r}, which has no Seat Baseline")
    for code in mp_names:
        if code not in referenced_codes:
            raise ValueError(
                f"MP Profile {code!r} is not reachable from the postcode index — "
                "the client index would ship it with no way to look it up"
            )

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


def build_and_write_client_index(engine: Engine, output_path: str) -> int:
    """Read Storage/config and write the client index to `output_path`.

    Returns the byte length written, so a caller (`main`) can report it —
    the size claim is exactly what ADR 0008's sizing argument depends on
    staying true as the pilot grows past two Seats.
    """
    from pathlib import Path

    from lpa.config import load_mp_profiles, load_postcode_seat_index
    from lpa.storage import load_seat_baselines

    baseline = load_seat_baselines(engine)
    raw_postcode_index = load_postcode_seat_index()
    postcode_index = {
        postcode: tuple(m.seat_code for m in matches)
        for postcode, matches in raw_postcode_index.items()
    }
    mp_names = {code: profile.name for code, profile in load_mp_profiles().items()}

    payload = build_client_index_json(baseline, postcode_index, mp_names)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return len(payload.encode("utf-8"))


def main() -> None:
    """Write the client lookup index to `public/politikku/data/lookup-index.json`."""
    import argparse

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="public/politikku/data/lookup-index.json",
        help="where to write the client index",
    )
    args = parser.parse_args()

    engine = connect()
    size = build_and_write_client_index(engine, args.output)
    print(f"Wrote {args.output} ({size:,} bytes)")


if __name__ == "__main__":
    main()
