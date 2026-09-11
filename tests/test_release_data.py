"""Release data must fail closed when dates, totals or exported copies disagree."""

import json

import pytest

from lpa.release_data import check_release, export_release, validate_payloads


def payloads():
    return (
        {
            "computed_at": "2026-09-01",
            "seats": [{"code": "P.107", "coalition": "PH"}],
            "coalition_seat_totals": {"PH": 1, "PN": 0},
        },
        {"computed_at": "2026-09-01"},
    )


def test_rejects_stale_sentiment_and_incorrect_totals():
    projection, sentiment = payloads()
    validate_payloads(projection, sentiment)
    with pytest.raises(ValueError, match="snapshot date"):
        validate_payloads(projection, {"computed_at": "2026-08-31"})
    projection["coalition_seat_totals"]["PH"] = 2
    with pytest.raises(ValueError, match="totals"):
        validate_payloads(projection, sentiment)


def test_exports_identical_copies_and_detects_later_changes(tmp_path, monkeypatch):
    projection, sentiment = payloads()
    monkeypatch.setattr(
        "lpa.release_data.projection_export", lambda _: (json.dumps(projection), "fixture csv")
    )
    monkeypatch.setattr("lpa.release_data.sentiment_export", lambda _: json.dumps(sentiment))
    export_release(None, tmp_path)
    check_release(tmp_path)
    app = tmp_path / "app/data/projection.json"
    app.write_text('{"computed_at": "2026-08-31"}')
    with pytest.raises(ValueError, match="changed"):
        check_release(tmp_path)


def test_invalid_export_does_not_write_files(tmp_path, monkeypatch):
    projection, _ = payloads()
    monkeypatch.setattr(
        "lpa.release_data.projection_export", lambda _: (json.dumps(projection), "fixture csv")
    )
    monkeypatch.setattr(
        "lpa.release_data.sentiment_export", lambda _: '{"computed_at": "2026-08-31"}'
    )
    with pytest.raises(ValueError, match="snapshot date"):
        export_release(None, tmp_path)
    assert not list(tmp_path.iterdir())
