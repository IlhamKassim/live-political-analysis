"""The pipeline's seam: outlets in, one day's Projection and Sentiment out.

Every collaborator is injected, so this pins the wiring — that Sentiment
really reaches the Swing Model, that the Baseline really comes from Storage —
without a network or a model. The parts themselves are tested in their own
suites.
"""

from datetime import date, datetime, timezone

from fixtures import PH, PN, government_config, two_coalition_seats
from lpa.domain import Article, Outlet
from lpa.pipeline import run_pipeline
from lpa.storage import (
    connect,
    load_projections,
    load_sentiment_snapshots,
    save_snapshot,
)

ALIASES = {PH: ["PH"], PN: ["PN"]}
OUTLETS = [Outlet("Test Outlet", "https://x/feed/")]


def article(text: str) -> Article:
    return Article(
        source="Test Outlet",
        url="https://x/1",
        published_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        title="Headline",
        text=text,
    )


def fetch(articles):
    return lambda outlets: articles


def classify_by_keyword(sentences):
    return [-0.4 if "criticised" in s else 0.4 for s in sentences]


def test_a_run_turns_scraped_articles_into_a_projection():
    # PH is criticised across the coverage, PN praised. With the fixture's
    # 0.10 sensitivity that is a 4pp swing to PN, which takes the two seats PH
    # holds by 6pp and 4pp — the same arithmetic the Swing Model suite pins.
    result = run_pipeline(
        outlets=OUTLETS,
        fetch=fetch([article("PH was criticised."), article("PN was praised.")]),
        classify=classify_by_keyword,
        aliases=ALIASES,
        baseline=two_coalition_seats(),
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert result.sentiment.scores == {PH: -0.4, PN: 0.4}
    assert result.projection.coalition_seat_totals == {PH: 2, PN: 4}
    assert result.projection.government_majority is False
    assert result.projection.computed_at == date(2026, 8, 6)


def test_a_headline_counts_as_coverage_even_when_the_body_does_not_name_anyone():
    # In Malaysian coverage the Coalition is often named only in the headline.
    result = run_pipeline(
        outlets=OUTLETS,
        fetch=lambda outlets: [
            Article(
                source="Test Outlet",
                url="https://x/1",
                published_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
                title="PN was praised today",
                text="The announcement came late in the afternoon.",
            )
        ],
        classify=classify_by_keyword,
        aliases=ALIASES,
        baseline=two_coalition_seats(),
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert PN in result.sentiment.scores


def test_a_day_with_no_political_coverage_still_produces_a_projection():
    # No Sentiment means no Swing, so the Projection falls back to the
    # Baseline rather than the dashboard going blank.
    result = run_pipeline(
        outlets=OUTLETS,
        fetch=fetch([article("Heavy rain closed several roads.")]),
        classify=classify_by_keyword,
        aliases=ALIASES,
        baseline=two_coalition_seats(),
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert result.sentiment.scores == {}
    assert result.projection.coalition_seat_totals == {PH: 4, PN: 2}
    assert result.projection.government_majority is True


def test_a_run_stores_one_projection_and_one_sentiment_snapshot():
    engine = connect("sqlite+pysqlite:///:memory:")
    result = run_pipeline(
        outlets=OUTLETS,
        fetch=fetch([article("PH was criticised.")]),
        classify=classify_by_keyword,
        aliases=ALIASES,
        baseline=two_coalition_seats(),
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    save_snapshot(engine, result.projection, result.sentiment)

    assert len(load_projections(engine)) == 1
    assert len(load_sentiment_snapshots(engine)) == 1
    assert load_projections(engine)[0].computed_at == date(2026, 8, 6)


def test_re_running_a_day_corrects_it_rather_than_recording_it_twice():
    engine = connect("sqlite+pysqlite:///:memory:")

    def run(text):
        return run_pipeline(
            outlets=OUTLETS,
            fetch=fetch([article(text)]),
            classify=classify_by_keyword,
            aliases=ALIASES,
            baseline=two_coalition_seats(),
            state_election_signals=[],
            config=government_config(),
            computed_at=date(2026, 8, 6),
        )

    first, second = run("PH was criticised."), run("PH was praised.")
    save_snapshot(engine, first.projection, first.sentiment)
    save_snapshot(engine, second.projection, second.sentiment)

    stored = load_sentiment_snapshots(engine)
    assert len(stored) == 1
    assert stored[0].scores == {PH: 0.4}  # the second run's answer, not the first


def test_snapshots_from_different_days_both_survive_for_the_trend_line():
    # User story 3: the dashboard shows Sentiment over time.
    engine = connect("sqlite+pysqlite:///:memory:")
    for day in (date(2026, 8, 5), date(2026, 8, 6)):
        result = run_pipeline(
            outlets=OUTLETS,
            fetch=fetch([article("PH was criticised.")]),
            classify=classify_by_keyword,
            aliases=ALIASES,
            baseline=two_coalition_seats(),
            state_election_signals=[],
            config=government_config(),
            computed_at=day,
        )
        save_snapshot(engine, result.projection, result.sentiment)

    assert [p.computed_at for p in load_projections(engine)] == [
        date(2026, 8, 5),
        date(2026, 8, 6),
    ]


def test_the_sentiment_snapshot_records_what_it_was_built_from():
    engine = connect("sqlite+pysqlite:///:memory:")
    result = run_pipeline(
        outlets=OUTLETS,
        fetch=fetch([article("PH was criticised."), article("Rain closed roads.")]),
        classify=classify_by_keyword,
        aliases=ALIASES,
        baseline=two_coalition_seats(),
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    save_snapshot(engine, result.projection, result.sentiment)
    stored = load_sentiment_snapshots(engine)[0]

    assert stored.total_articles == 2
    assert stored.article_counts == {PH: 1}
    assert stored.sources == ["Test Outlet"]


def test_snapshots_are_dated_by_the_malaysian_day_not_utc():
    # 00:30 on 7 August in Kuala Lumpur is still 6 August in UTC. Dating by UTC
    # would file a Malaysian day's coverage under the day before.
    from lpa.pipeline import MALAYSIA_TIME

    just_after_midnight = datetime(2026, 8, 7, 0, 30, tzinfo=MALAYSIA_TIME)

    assert just_after_midnight.date() == date(2026, 8, 7)
    assert just_after_midnight.astimezone(timezone.utc).date() == date(2026, 8, 6)
