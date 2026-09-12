"""Analyst export payload shape, away from file I/O."""

from datetime import date

from fixtures import PH, PN, government_config, two_coalition_seats

from lpa.aggregate import AggregatedSentiment
from lpa.analyst_export import (
    SCHEMA_VERSION,
    _csv_escape,
    export_baseline,
    export_current_inputs,
    export_methodology,
    export_model_config,
    export_state_signals,
    to_json,
)
from lpa.domain import SeatBaseline
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
    assert "demographics" in payload["seats"][0]
    assert payload["source"]["url"] == "https://electiondata.my/"


def test_baseline_export_keeps_census_demographics():
    seat = SeatBaseline(
        code="P001",
        name="Test",
        state="Selangor",
        vote_share={PH: 0.6, PN: 0.4},
        margin=0.2,
        demographics={"ethnicity_proportion_bumi": 89.8, "income_median": 4075.0},
    )
    payload = export_baseline([seat])
    assert payload["seats"][0]["demographics"]["ethnicity_proportion_bumi"] == 89.8
    assert payload["seats"][0]["winner"] == PH


def test_methodology_export_cites_meco():
    payload = export_methodology()
    assert payload["sources"]["baseline"]["name"] == "Malaysian Election Corpus (MECo)"
    assert "Scientific Data" in payload["sources"]["baseline"]["citation"]


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


def test_the_articles_csv_leaves_an_unscored_article_cell_empty():
    """The nightly bundle crashed on an article with no coalition scores:
    `articles_export.dominant_coalition` returns None for it, and the CSV
    writer tried to search that None for a comma. An empty cell is the answer.
    """
    assert _csv_escape(None) == ""
    assert _csv_escape("PH") == "PH"
    assert _csv_escape('a,b"c') == '"a,b""c"'
