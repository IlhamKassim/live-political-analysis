"""The constituency lookup's client-side data export (#77)."""

from __future__ import annotations

import json

import pytest

from lpa.domain import SeatBaseline
from lpa.politikku_lookup_index import build_client_index, build_client_index_json

P101 = SeatBaseline(code="P.101", name="Hulu Langat", state="Selangor", vote_share={"PH": 0.5})
P102 = SeatBaseline(code="P.102", name="Bangi", state="Selangor", vote_share={"PH": 0.58})

POSTCODE_INDEX = {
    "43000": ("P.102",),
    "43100": ("P.101",),
    "43200": ("P.101", "P.102"),
}


def test_a_seat_with_a_profile_carries_its_mp_name_and_the_flag():
    index = build_client_index([P101, P102], POSTCODE_INDEX, {"P.102": "Syahredzan Johan"})
    assert index["seats"]["P.102"] == {
        "code": "P.102",
        "name": "Bangi",
        "state": "Selangor",
        "hasProfile": True,
        "mpName": "Syahredzan Johan",
    }


def test_a_seat_with_no_profile_states_the_gap_not_a_missing_key():
    index = build_client_index([P101, P102], POSTCODE_INDEX, {"P.102": "Syahredzan Johan"})
    assert index["seats"]["P.101"] == {
        "code": "P.101",
        "name": "Hulu Langat",
        "state": "Selangor",
        "hasProfile": False,
        "mpName": None,
    }


def test_every_seat_carries_its_own_code_not_just_the_dict_key():
    # A real bug this suite once missed: the client (ts/src/resolve.ts)
    # reads `seat.code` off the value itself, not the `seats` object's
    # key — a payload that only carried the code as a key produced a
    # working-looking JSON that silently resolved to `undefined` client
    # side. Assert every seat's own `code` field explicitly.
    index = build_client_index([P101, P102], POSTCODE_INDEX, {})
    for code, seat in index["seats"].items():
        assert seat["code"] == code


def test_postcodes_are_carried_through_verbatim():
    index = build_client_index([P101, P102], POSTCODE_INDEX, {})
    assert index["postcodes"] == {
        "43000": ["P.102"],
        "43100": ["P.101"],
        "43200": ["P.101", "P.102"],
    }


def test_a_postcode_naming_a_seat_with_no_baseline_is_rejected():
    with pytest.raises(ValueError, match="no Seat Baseline"):
        build_client_index([P102], POSTCODE_INDEX, {})  # P.101 missing from baseline


def test_mp_profiles_for_unreferenced_seats_are_omitted_from_client_index():
    index = build_client_index(
        [P101, P102],
        {"43000": ("P.102",)},
        {"P.101": "Someone", "P.102": "Syahredzan Johan"},
    )
    assert "P.102" in index["seats"]
    assert "P.101" not in index["seats"]


def test_the_json_form_round_trips_to_the_same_shape():
    payload = json.loads(build_client_index_json([P101, P102], POSTCODE_INDEX, {}))
    assert payload == build_client_index([P101, P102], POSTCODE_INDEX, {})
