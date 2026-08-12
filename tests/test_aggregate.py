"""Aggregation's seam: per-Article Sentiment -> one Sentiment per Coalition.

Pure — the scores are given, so no model runs here.
"""

from datetime import UTC, datetime

from pytest import approx

from lpa.aggregate import aggregate_sentiment
from lpa.domain import Article

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def article(hours_old: float = 0.0, source: str = "FMT") -> Article:
    return Article(
        source=source,
        url=f"https://x/{hours_old}",
        published_at=NOW,
        title="t",
        text="body",
    )


def test_a_coalitions_sentiment_is_the_mean_across_the_articles_scoring_it():
    scored = [
        (article(), {"PH": 0.6}),
        (article(), {"PH": 0.2}),
    ]

    assert aggregate_sentiment(scored).scores == {"PH": approx(0.4)}


def test_each_coalition_is_averaged_over_only_its_own_articles():
    scored = [
        (article(), {"PH": 1.0}),
        (article(), {"PH": 0.0, "PN": -0.5}),
    ]

    aggregated = aggregate_sentiment(scored)

    assert aggregated.scores["PH"] == approx(0.5)
    assert aggregated.scores["PN"] == approx(-0.5)  # only one article named PN


def test_articles_naming_no_coalition_do_not_drag_scores_towards_zero():
    # A None score means "no Coalition mentioned", not "neutral about everyone".
    scored = [
        (article(), {"PH": 0.8}),
        (article(), None),
        (article(), None),
    ]

    assert aggregate_sentiment(scored).scores == {"PH": approx(0.8)}


def test_the_article_count_behind_each_coalition_is_reported():
    # The dashboard has to be able to say how thin a number is.
    scored = [
        (article(), {"PH": 0.5, "PN": 0.1}),
        (article(), {"PH": -0.5}),
        (article(), None),
    ]

    aggregated = aggregate_sentiment(scored)

    assert aggregated.article_counts == {"PH": 2, "PN": 1}
    assert aggregated.total_articles == 3


def test_the_sources_behind_the_score_are_reported():
    # User story 5: a visitor wants to see which sources feed the Sentiment.
    scored = [
        (article(source="FMT"), {"PH": 0.5}),
        (article(source="Malay Mail"), {"PH": 0.1}),
        (article(source="FMT"), None),
    ]

    assert aggregate_sentiment(scored).sources == ["FMT", "Malay Mail"]


def test_a_day_with_no_coalition_coverage_aggregates_to_nothing():
    aggregated = aggregate_sentiment([(article(), None)])

    assert aggregated.scores == {}
    assert aggregated.total_articles == 1
