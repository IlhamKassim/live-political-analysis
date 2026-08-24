"""Postcode -> Seat lookup, and the shipped pilot slice (issue #76).

`load_postcode_seat_index` and `lookup_postcode` are checked separately: the
loader against synthetic fixtures (so a malformed file fails loudly), the
shipped file against the two real cases the Election Commission source
actually gives — an unambiguous postcode and the one genuinely ambiguous one
in the pilot slice (Cheras, split between P.101 and P.102). See
`scripts/build_postcode_seat_index.py` for how the shipped file was built.
"""

import json

import pytest

from lpa.config import load_postcode_seat_index
from lpa.postcode_index import SeatMatch, lookup_postcode

BANGI = SeatMatch(seat_code="P.102", seat_name="Bangi", state="Selangor")
HULU_LANGAT = SeatMatch(seat_code="P.101", seat_name="Hulu Langat", state="Selangor")


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
    # and simply outside the pilot slice's two Seats.
    assert lookup_postcode("99999", {}) == ()


@pytest.mark.parametrize("bad", ["4365", "436500", "ABCDE", "43-650", ""])
def test_lookup_rejects_anything_that_is_not_a_five_digit_postcode(bad):
    with pytest.raises(ValueError):
        lookup_postcode(bad, {})


def test_the_loader_reads_a_postcode_with_one_seat(tmp_path):
    index = load_postcode_seat_index(
        write_index(
            tmp_path, {"43650": [{"seat_code": "P.102", "seat_name": "Bangi", "state": "Selangor"}]}
        )
    )

    assert index["43650"] == (BANGI,)


def test_the_loader_rejects_a_postcode_with_no_seats(tmp_path):
    with pytest.raises(ValueError):
        load_postcode_seat_index(write_index(tmp_path, {"43650": []}))


SHIPPED_INDEX = load_postcode_seat_index()


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
