"""Analyst export payload shape, away from file I/O."""

from datetime import date

from fixtures import PH, PN, government_config, two_coalition_seats

from lpa.aggregate import AggregatedSentiment
from lpa.analyst_export import (
    SCHEMA_VERSION,
    export_baseline,
    export_current_inputs,
    export_methodology,
    export_model_config,
    export_state_signals,
    to_json,
)
from lpa.storage import connect, save_snapshot
from lpa.swing_model import state_swing, swing_model


def test_baseline_export_carries_every_seat():
    baseline = two_coalition_seats()
    payload = export_baseline(baseline)
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "FACT"
    assert len(payload["seats"]) == 6
    assert payload["seats"][0]["code"] == "P001"
    assert "vote_share" in payload["seats"][0]


def test_model_config_export_carries_tunables():
    config = government_config()
    payload = export_model_config(config, {PH: "Pakatan Harapan", PN: "Perikatan Nasional"})
    assert payload["kind"] == "MODEL"
    assert payload["sentiment_sensitivity"] == 0.10
    assert PH in payload["government_coalitions"]


def test_state_signals_export_is_a_list():
    payload = export_state_signals()
    assert "signals" in payload
    assert isinstance(payload["signals"], list)


def test_methodology_export_has_url():
    payload = export_methodology()
    assert "methodology_url" in payload
    assert payload["labels"]["FACT"]


def test_current_inputs_reads_latest_snapshot(tmp_path):
    engine = connect(f"sqlite+pysqlite:///{tmp_path / 'test.db'}")
    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: 0.1, PN: -0.1},
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 20),
    )
    sentiment = AggregatedSentiment(
        scores={PH: 0.1, PN: -0.1},
        article_counts={PH: 3, PN: 2},
        total_articles=5,
        sources=["FMT"],
    )
    swings = state_swing(
        two_coalition_seats(),
        sentiment.scores,
        [],
        government_config(),
    )
    save_snapshot(
        engine,
        projection,
        sentiment,
        swings,
        scored_articles=(),
    )
    payload = export_current_inputs(engine)
    assert payload["computed_at"] == "2026-08-20"
    assert payload["scores"][PH] == 0.1


def test_to_json_is_newline_terminated():
    assert to_json({"a": 1}).endswith("\n")
