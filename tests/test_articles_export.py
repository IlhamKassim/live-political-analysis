"""Articles export for Analyst drill-down."""

from datetime import date

from fixtures import PH, PN, government_config, two_coalition_seats

from lpa.aggregate import AggregatedSentiment
from lpa.articles_export import build_export, dominant_coalition, export_articles
from lpa.domain import Article
from lpa.storage import connect, save_snapshot
from lpa.swing_model import state_swing, swing_model


def test_dominant_coalition_picks_the_highest_score():
    assert dominant_coalition({PH: 0.2, PN: -0.1}) == PH
    assert dominant_coalition(None) is None


def test_export_articles_carries_deltas_and_rows():
    payload = export_articles(
        computed_at=date(2026, 8, 20),
        articles=[
            {
                "url": "https://example.test/a",
                "title": "Economy grows",
                "source": "FMT",
                "scores": {PH: 0.3},
                "dominant_coalition": PH,
                "topics": ["economy"],
            }
        ],
        sentiment_deltas={PH: 0.05, PN: None},
        coalition_names_map={PH: "Pakatan Harapan"},
    )
    assert payload["computed_at"] == "2026-08-20"
    assert payload["articles"][0]["topics"] == ["economy"]
    assert payload["coalition_deltas"][PN] is None


def test_build_export_from_storage(tmp_path):
    engine = connect(f"sqlite+pysqlite:///{tmp_path / 'articles.db'}")
    day = date(2026, 8, 21)
    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: 0.0, PN: 0.0},
        state_election_signals=[],
        config=government_config(),
        computed_at=day,
    )
    article = Article(
        source="FMT",
        url="https://example.test/story",
        published_at=None,
        title="Budget debate in Parliament",
        text="Parliament discussed the belanjawan and inflation.",
    )
    save_snapshot(
        engine,
        projection,
        AggregatedSentiment(
            scores={PH: 0.1, PN: -0.1},
            article_counts={PH: 1, PN: 1},
            total_articles=2,
            sources=["FMT"],
        ),
        state_swing(
            two_coalition_seats(),
            {PH: 0.1, PN: -0.1},
            [],
            government_config(),
        ),
        scored_articles=((article, {PH: 0.4, PN: -0.2}),),
    )
    body = build_export(engine)
    assert "https://example.test/story" in body
    assert "economy" in body or "trust_in_institutions" in body
