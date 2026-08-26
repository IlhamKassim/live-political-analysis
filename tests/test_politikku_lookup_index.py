"""The constituency lookup's client-side data export (#77)."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_every_baseline_seat_is_searchable_by_name():
    index = build_client_index(
        [P101, P102],
        {"43000": ("P.102",)},
        {"P.101": "Someone", "P.102": "Syahredzan Johan"},
    )
    assert "P.102" in index["seats"]
    assert "P.101" in index["seats"]
    assert index["seats"]["P.101"]["hasProfile"] is True
    assert index["seats"]["P.101"]["mpName"] == "Someone"


def test_compute_unresolved_mp_profiles_identifies_omitted_members():
    from lpa.politikku_lookup_index import compute_unresolved_mp_profiles

    mp_names = {"P.002": "Shahidan Kassim", "P.102": "Syahredzan Johan"}
    referenced_postcode_seats = {"P.102"}
    unresolved = compute_unresolved_mp_profiles(mp_names, referenced_postcode_seats)
    assert unresolved == {"P.002": "Shahidan Kassim"}


def test_the_json_form_round_trips_to_the_same_shape():
    payload = json.loads(build_client_index_json([P101, P102], POSTCODE_INDEX, {}))
    assert payload == build_client_index([P101, P102], POSTCODE_INDEX, {})


def test_build_and_write_client_index_writes_payload_and_unresolved_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from unittest.mock import MagicMock

    from lpa.politikku_lookup_index import build_and_write_client_index
    from lpa.postcode_index import SeatMatch

    output_path = tmp_path / "lookup-index.json"
    unresolved_path = tmp_path / "unresolved.json"

    monkeypatch.setattr("lpa.storage.load_seat_baselines", lambda engine: [P101, P102])
    monkeypatch.setattr(
        "lpa.config.load_postcode_seat_index",
        lambda: {"43000": (SeatMatch(seat_code="P.102"),)},
    )

    class DummyProfile:
        def __init__(self, name: str):
            self.name = name

    monkeypatch.setattr(
        "lpa.config.load_mp_profiles",
        lambda: {"P.101": DummyProfile("Member 1"), "P.102": DummyProfile("Member 2")},
    )

    result = build_and_write_client_index(MagicMock(), output_path, unresolved_path)
    assert result.total_mp_profiles == 2
    assert result.reachable_mp_profiles == 1
    assert result.excluded_mp_profiles == 1

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "P.102" in payload["seats"]
    assert "P.101" in payload["seats"]

    unresolved_data = json.loads(unresolved_path.read_text(encoding="utf-8"))
    assert unresolved_data["total_mp_profiles"] == 2
    assert unresolved_data["reachable_mp_profiles"] == 1
    assert unresolved_data["excluded_count"] == 1
    assert unresolved_data["unresolved_mp_profiles"] == {"P.101": "Member 1"}
