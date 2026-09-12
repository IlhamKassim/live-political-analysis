"""The daily pipeline: scrape -> score -> aggregate -> project -> store.

One pass, no manual steps in between. Every collaborator is a parameter, so
the wiring can be exercised without a network or a model; `main` supplies the
real ones.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from lpa.aggregate import AggregatedSentiment, aggregate_sentiment
from lpa.domain import (
    Article,
    Coalition,
    Outlet,
    Projection,
    SeatBaseline,
    StateElectionSignal,
    SwingModelConfig,
)
from lpa.sentiment import Classifier, score_article
from lpa.swing_model import state_swing, swing_model

MALAYSIA_TIME = timezone(timedelta(hours=8))

DISSOLUTION_SIGNALS = Path("dissolution-signals.json")
"""Where this run writes what the coverage claimed, for the alert step to
read. Deliberately not under `public/`: it is a note to the people who
maintain the data, not something the site publishes."""
"""Snapshots are dated by the Malaysian day, not UTC.

A run just after midnight in Kuala Lumpur is still yesterday in UTC, which
would file the day's coverage under the wrong date and put two Malaysian days
into one row of the dashboard's trend line.
"""


def today_in_malaysia(now: Callable[[timezone], datetime] = datetime.now) -> date:
    return now(MALAYSIA_TIME).date()


@dataclass(frozen=True)
class PipelineResult:
    """What one run produced, for the caller to store or report on."""

    projection: Projection
    sentiment: AggregatedSentiment
    state_swing: Mapping[str, Mapping[Coalition, float]]
    """The Swing actually applied in each state (#53a) — `swing_model` used
    this to call every Seat, but discards it once it has. Kept here so a
    per-state rollup (#53) can publish the real figure rather than
    reconstructing an approximation of it from the Seat Calls."""
    articles: tuple[Article, ...] = ()
    """The coverage this run read, kept so `dissolution_watch` can look for a
    dissolution in it. Fetching is rate-limited and robots-checked, so a
    second pass over the outlets to ask a different question of the same
    stories would be both slower and ruder than carrying them out of here."""


def run_pipeline(
    *,
    outlets: Iterable[Outlet],
    fetch: Callable[[Iterable[Outlet]], Sequence[Article]],
    classify: Classifier,
    aliases: Mapping[Coalition, Sequence[str]],
    baseline: Sequence[SeatBaseline],
    state_election_signals: Sequence[StateElectionSignal],
    config: SwingModelConfig,
    computed_at: date,
) -> PipelineResult:
    """Run the whole pipeline once and return the day's Projection.

    The Article's title is scored along with its body: a headline carries the
    framing, and in Malaysian coverage it is often where the Coalition is
    named at all.
    """
    articles = list(fetch(outlets))
    scored = [
        (article, score_article(f"{article.title}. {article.text}", classify, aliases))
        for article in articles
    ]
    sentiment = aggregate_sentiment(scored)
    projection = swing_model(
        baseline,
        sentiment.scores,
        state_election_signals,
        config,
        computed_at,
    )
    swing_by_state = state_swing(baseline, sentiment.scores, state_election_signals, config)
    return PipelineResult(
        projection=projection,
        sentiment=sentiment,
        state_swing=swing_by_state,
        articles=tuple(articles),
    )


def main() -> None:
    """Run the pipeline against the real world and store the day's snapshot."""
    from lpa.config import (
        coalition_aliases,
        load_coalition_config,
        load_election_status,
        load_outlets,
        load_state_election_signals,
        swing_model_config,
    )
    from lpa.scraper import Scraper
    from lpa.sentiment import TransformerClassifier
    from lpa.storage import connect, load_seat_baselines, save_snapshot

    engine = connect()
    baseline = load_seat_baselines(engine)
    if not baseline:
        raise SystemExit("No Seat Baseline in Storage. Run `python -m lpa.baseline_loader` first.")

    config = load_coalition_config()
    with Scraper() as scraper:
        result = run_pipeline(
            outlets=load_outlets(),
            fetch=scraper.fetch_all,
            classify=TransformerClassifier(),
            aliases=coalition_aliases(config),
            baseline=baseline,
            state_election_signals=load_state_election_signals(),
            config=swing_model_config(config),
            computed_at=today_in_malaysia(),
        )

    projection, sentiment = result.projection, result.sentiment
    if sentiment.total_articles == 0:
        raise SystemExit(
            "No Articles scraped — refusing to store. Writing this run would "
            "replace today's real snapshot with an empty one built from the "
            "State Election Signal alone."
        )
    status = load_election_status()
    save_snapshot(engine, projection, sentiment, result.state_swing, status=status)

    # Detection here, delivery in its own step: this writes down what the
    # coverage claims and sends nothing. Nothing reaches the site from it
    # either — a human reads the alert and edits election_status.json.
    from lpa.dissolution_watch import scan, write_signals

    signals = scan(result.articles, status)
    write_signals(signals, DISSOLUTION_SIGNALS)
    if signals:
        print(f"\n{len(signals)} Article(s) claim a status change — see {DISSOLUTION_SIGNALS}")

    print(f"Read {sentiment.total_articles} Articles from {', '.join(sentiment.sources)}")
    print("\nSentiment per Coalition:")
    for coalition, score in sorted(sentiment.scores.items(), key=lambda kv: -kv[1]):
        print(f"  {coalition:5s} {score:+.3f}  ({sentiment.article_counts[coalition]} articles)")
    print(f"\nProjection for {projection.computed_at}:")
    for coalition, seats in sorted(projection.coalition_seat_totals.items(), key=lambda kv: -kv[1]):
        print(f"  {coalition:8s} {seats:4d}")
    held = "retains" if projection.government_majority else "loses"
    print(f"\nGovernment Coalition {held} its Majority.")


if __name__ == "__main__":
    main()
