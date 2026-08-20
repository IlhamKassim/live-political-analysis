"""What the JSON/CSV export says, tested away from file I/O.

`export_model` does every piece of shaping the export claims, so this file is
about the payload's shape and content, not disk writes — the same split
`test_seat_call_card.py` uses for `card_model`.
"""

import csv
import io
import json
from datetime import date

import pytest

from lpa.domain import Projection, SeatBaseline, SeatCall
from lpa.public_export import CAVEAT, SCHEMA_VERSION, export_model, to_csv, to_json

PH = "PH"
PN = "PN"

NAMES = {PH: "Pakatan Harapan", PN: "Perikatan Nasional"}


def seat(code: str, name: str, state: str, **votes: float) -> SeatBaseline:
    return SeatBaseline(code=code, name=name, state=state, vote_share=votes)


def projection(*calls: SeatCall, computed_at: date = date(2026, 8, 20)) -> Projection:
    totals = {PH: 2, PN: 1}
    return Projection(
        coalition_seat_totals=totals,
        government_majority=False,
        computed_at=computed_at,
        seat_calls=calls,
    )


BASELINE = [
    seat("P.001", "Bandar", "Selangor", PH=0.53, PN=0.47),
    seat("P.002", "Luar", "Johor", PH=0.44, PN=0.56),
]


def test_the_export_carries_the_schema_version_and_run_date():
    payload = export_model(projection(), BASELINE, NAMES)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["computed_at"] == "2026-08-20"


def test_the_export_carries_the_same_caveat_the_page_shows():
    payload = export_model(projection(), BASELINE, NAMES)
    assert payload["caveat"] == CAVEAT
    assert "not fitted to" in payload["caveat"]


def test_a_seat_carries_its_baseline_facts_alongside_its_call():
    call = SeatCall(code="P.001", coalition=PH, margin=0.06)
    payload = export_model(projection(call), BASELINE, NAMES)
    [row] = payload["seats"]
    assert row == {
        "code": "P.001",
        "name": "Bandar",
        "state": "Selangor",
        "coalition": PH,
        "coalition_name": "Pakatan Harapan",
        "margin": 0.06,
    }


def test_a_coalition_the_names_map_does_not_know_falls_back_to_its_code():
    call = SeatCall(code="P.001", coalition="IND", margin=0.02)
    payload = export_model(projection(call), BASELINE, NAMES)
    assert payload["seats"][0]["coalition_name"] == "IND"


def test_a_call_for_a_seat_the_baseline_does_not_have_is_an_error():
    call = SeatCall(code="P.404", coalition=PH, margin=0.02)
    with pytest.raises(ValueError, match="P.404"):
        export_model(projection(call), BASELINE, NAMES)


def test_the_json_export_round_trips_the_payload():
    payload = export_model(projection(), BASELINE, NAMES)
    assert json.loads(to_json(payload)) == payload


def test_the_csv_export_has_one_row_per_seat_with_a_header():
    calls = (
        SeatCall(code="P.001", coalition=PH, margin=0.06),
        SeatCall(code="P.002", coalition=PN, margin=0.12),
    )
    payload = export_model(projection(*calls), BASELINE, NAMES)
    rows = list(csv.DictReader(io.StringIO(to_csv(payload))))
    assert [row["code"] for row in rows] == ["P.001", "P.002"]
    assert rows[0]["coalition_name"] == "Pakatan Harapan"


def test_the_csv_export_omits_whole_projection_fields():
    payload = export_model(projection(), BASELINE, NAMES)
    body = to_csv(payload)
    assert "schema_version" not in body
    assert CAVEAT not in body
