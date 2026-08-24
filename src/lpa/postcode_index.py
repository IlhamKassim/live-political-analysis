"""Postcode -> Seat: which Seat(s) a Malaysian postcode falls in (issue #76).

A Malaysian postcode is a Pos Malaysia delivery area, not an Election
Commission unit, so it does not nest cleanly inside a single Seat — some
postcodes serve localities split across two Seats. This module represents
that honestly: a lookup returns every candidate Seat, never a single guessed
answer, and an empty result means the postcode is not in the index (the
lookup UI's no-match state, #77), not that it has no Seat.

The index itself (`data/postcode_seat_index.json`) is a pilot slice — Selangor
P.101 Hulu Langat and P.102 Bangi only, the same Seats #78's MP-profile pilot
scopes to — built by joining the Election Commission's own delimitation data
against a Pos Malaysia postcode reference; see
`scripts/build_postcode_seat_index.py` for the method and ADR 0008 for why a
join was necessary and what scaling to all 222 Seats will take.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_POSTCODE = re.compile(r"^\d{5}$")


@dataclass(frozen=True)
class SeatMatch:
    """One candidate Seat for a postcode.

    Identified by `seat_code` alone, the way `SeatCall` is identified by
    `code` alone: `SeatBaseline` already holds a Seat's name and state for
    all 222 Seats, and a caller resolving a match wants those anyway.
    Copying them here would make a Seat's identity two facts that can
    disagree — `data/postcode_seat_index.json`'s `_seats` block carries them
    once, for the file's own readability, not as a second source of truth.
    """

    seat_code: str
    """The Seat's official code, e.g. "P.102"."""


def lookup_postcode(postcode: str, index: Mapping[str, Sequence[SeatMatch]]) -> Sequence[SeatMatch]:
    """Candidate Seat(s) for `postcode`.

    Zero matches means "not in the index" (#77's no-match state); more than
    one means the postcode is genuinely ambiguous (#77's disambiguation
    state) — never collapsed to a single guess.
    """
    if not _POSTCODE.match(postcode):
        raise ValueError(f"not a 5-digit Malaysian postcode: {postcode!r}")
    return index.get(postcode, ())
