"""Postcode -> Seat lookup, and the shipped index (issues #76, #107).

`load_postcode_seat_index` and `lookup_postcode` are checked separately: the
loader against synthetic fixtures (so a malformed file fails loudly), the
shipped file against real cases the Election Commission source actually
gives — an unambiguous postcode and a genuinely ambiguous one (Cheras, split
between P.101 and P.102) from #76's original hand-curated Selangor pilot,
plus the invariant that #107's nationwide exact-match extension only ever
adds to that pilot, never narrows or drops it. See
`scripts/build_postcode_seat_index.py` for how the shipped file was built.
"""

import json

import pytest

from lpa.config import load_postcode_seat_index
from lpa.postcode_index import SeatMatch, lookup_postcode

BANGI = SeatMatch(seat_code="P.102")
HULU_LANGAT = SeatMatch(seat_code="P.101")


def write_index(tmp_path, postcodes):
    path = tmp_path / "postcode_seat_index.json"
    path.write_text(json.dumps({"postcodes": postcodes}))
    return path


def test_lookup_returns_the_single_seat_for_an_unambiguous_postcode():
    index = {"43650": (BANGI,)}

    assert lookup_postcode("43650", index) == (BANGI,)


def test_lookup_returns_every_candidate_for_an_ambiguous_postcode():
    index = {"43200": (HULU_LANGAT, BANGI)}

    assert lookup_postcode("43200", index) == (HULU_LANGAT, BANGI)


def test_lookup_returns_nothing_for_a_postcode_not_in_the_index():
    # The no-match state (#77), not an error: a postcode can be well-formed
    # and simply not yet in the index.
    assert lookup_postcode("99999", {}) == ()


@pytest.mark.parametrize("bad", ["4365", "436500", "ABCDE", "43-650", ""])
def test_lookup_rejects_anything_that_is_not_a_five_digit_postcode(bad):
    with pytest.raises(ValueError):
        lookup_postcode(bad, {})


def test_the_loader_reads_a_postcode_with_one_seat(tmp_path):
    index = load_postcode_seat_index(write_index(tmp_path, {"43650": ["P.102"]}))

    assert index["43650"] == (BANGI,)


def test_the_loader_rejects_a_postcode_with_no_seats(tmp_path):
    with pytest.raises(ValueError):
        load_postcode_seat_index(write_index(tmp_path, {"43650": []}))


# #76's original hand-curated Selangor pilot, exactly as shipped before
# #107's nationwide exact-match extension. #107 must only ever add to this —
# never drop a postcode or narrow its Seat set — because every one of these
# was verified by a human against the live SPR data, and #107's automation
# was never asked to re-verify them.
PILOT_INDEX = {
    "43000": {"P.102"},
    "43007": {"P.102"},
    "43009": {"P.102"},
    "43100": {"P.101"},
    "43200": {"P.101", "P.102"},
    "43207": {"P.101", "P.102"},
    "43500": {"P.101"},
    "43558": {"P.102"},
    "43600": {"P.102"},
    "43650": {"P.102"},
    "43700": {"P.101"},
    "43701": {"P.101"},
}

SHIPPED_INDEX = load_postcode_seat_index()


def test_the_shipped_index_never_narrows_the_original_pilot_slice():
    # Issue #107 extends #76's pilot with a nationwide exact-match tier; it
    # must be additive only. A postcode disappearing or losing a Seat here
    # would mean #107's automation overrode a human-verified #76 entry.
    for postcode, seat_codes in PILOT_INDEX.items():
        assert postcode in SHIPPED_INDEX, postcode
        assert seat_codes <= {m.seat_code for m in SHIPPED_INDEX[postcode]}, postcode


def test_the_shipped_index_resolves_bandar_baru_bangi_unambiguously():
    # Bandar Baru Bangi's daerah mengundi (SPR "Senarai BPR") sit entirely
    # inside P.102's Sungai Ramal DUN — no real ambiguity here, unlike the
    # design handoff's illustrative (unsourced) example for this postcode.
    assert lookup_postcode("43650", SHIPPED_INDEX) == (BANGI,)


def test_the_shipped_index_flags_cheras_as_genuinely_ambiguous():
    # "Cheras" daerah mengundi exist under both P.101's Dusun Tua DUN and
    # P.102's Balakong DUN; the postcode data gives no finer locality to
    # split them, so both Seats are real candidates, not a bug.
    matches = lookup_postcode("43200", SHIPPED_INDEX)

    assert {m.seat_code for m in matches} == {"P.101", "P.102"}


def test_every_shipped_postcode_is_five_digits_and_names_at_least_one_seat():
    for postcode, matches in SHIPPED_INDEX.items():
        assert len(postcode) == 5 and postcode.isdigit()
        assert len(matches) >= 1
        assert len({m.seat_code for m in matches}) == len(matches)
