"""What the Sentiment JSON export says, tested away from file I/O.

`export_model` does every piece of shaping the export claims, so this file
is about the payload's shape and content, not disk writes — the same split
`test_public_export.py` uses for the Projection export.
"""

import json
from datetime import date

from lpa.domain import ElectionStatus
from lpa.politikku_sentiment import HistoricalSentimentPoint, SentimentPageModel, SentimentPageRow
from lpa.sentiment_export import HISTORY_LIMIT, SCHEMA_VERSION, export_model, to_json

PH = "PH"
PN = "PN"

NAMES = {PH: "Pakatan Harapan", PN: "Perikatan Nasional"}

STATUS = ElectionStatus(constitutional_deadline=date(2028, 2, 20), source="test fixture")


def model(
    rows: tuple[SentimentPageRow, ...] = (),
    history: tuple[HistoricalSentimentPoint, ...] = (),
    updated_at: date = date(2026, 8, 20),
    total_articles: int = 0,
    sources: tuple[str, ...] = (),
) -> SentimentPageModel:
    return SentimentPageModel(
        updated_at=updated_at,
        sources_count=len(sources),
        status=STATUS,
        total_articles=total_articles,
        rows=rows,
        history=history,
        sources=sources,
    )


def test_the_export_carries_the_schema_version_and_run_date():
    payload = export_model(model(updated_at=date(2026, 8, 20)), NAMES)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["computed_at"] == "2026-08-20"


def test_a_coalition_row_carries_its_score_articles_and_delta():
    rows = (SentimentPageRow(coalition=PH, name="unused", article_count=12, score=0.31, delta=0.04),)
    payload = export_model(model(rows=rows), NAMES)
    [row] = payload["coalitions"]
    assert row == {
        "coalition": PH,
        "coalition_name": "Pakatan Harapan",
        "article_count": 12,
        "score": 0.31,
        "delta": 0.04,
    }


def test_a_coalition_the_names_map_does_not_know_falls_back_to_its_code():
    rows = (SentimentPageRow(coalition="IND", name="unused", article_count=1, score=0.0, delta=None),)
    payload = export_model(model(rows=rows), NAMES)
    assert payload["coalitions"][0]["coalition_name"] == "IND"


def test_a_fresh_delta_with_no_prior_snapshot_is_null_not_zero():
    rows = (SentimentPageRow(coalition=PH, name="unused", article_count=3, score=0.1, delta=None),)
    payload = export_model(model(rows=rows), NAMES)
    assert payload["coalitions"][0]["delta"] is None


def test_history_points_carry_the_day_total_articles_and_per_coalition_scores():
    history = (
        HistoricalSentimentPoint(computed_at=date(2026, 8, 19), total_articles=8, scores={PH: 0.2}),
    )
    payload = export_model(model(history=history), NAMES)
    assert payload["history"] == [
        {"computed_at": "2026-08-19", "total_articles": 8, "scores": {PH: 0.2}}
    ]


def test_history_is_capped_to_the_most_recent_readings_oldest_first():
    history = tuple(
        HistoricalSentimentPoint(computed_at=date(2026, 7, 1 + i), total_articles=i, scores={})
        for i in range(HISTORY_LIMIT + 5)
    )
    payload = export_model(model(history=history), NAMES)
    assert len(payload["history"]) == HISTORY_LIMIT
    got_days = [point["computed_at"] for point in payload["history"]]
    expected_days = [p.computed_at.isoformat() for p in history[-HISTORY_LIMIT:]]
    assert got_days == expected_days
    # oldest-first ordering is preserved, not reversed by the slice/cap
    assert got_days == sorted(got_days)


def test_shorter_history_than_the_limit_is_carried_in_full():
    history = (
        HistoricalSentimentPoint(computed_at=date(2026, 8, 18), total_articles=1, scores={}),
        HistoricalSentimentPoint(computed_at=date(2026, 8, 19), total_articles=2, scores={}),
    )
    payload = export_model(model(history=history), NAMES)
    assert len(payload["history"]) == 2


def test_sources_and_counts_are_carried_verbatim():
    payload = export_model(
        model(sources=("The Star", "Malaysiakini"), total_articles=42), NAMES
    )
    assert payload["sources"] == ["The Star", "Malaysiakini"]
    assert payload["sources_count"] == 2
    assert payload["total_articles"] == 42


def test_the_json_export_round_trips_the_payload():
    rows = (SentimentPageRow(coalition=PH, name="unused", article_count=5, score=0.2, delta=None),)
    history = (
        HistoricalSentimentPoint(computed_at=date(2026, 8, 20), total_articles=5, scores={PH: 0.2}),
    )
    payload = export_model(model(rows=rows, history=history), NAMES)
    assert json.loads(to_json(payload)) == payload
