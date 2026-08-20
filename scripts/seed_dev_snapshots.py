"""Fill a local database with synthetic back-history, for development only.

The pipeline writes one snapshot a day, so a fresh checkout has a single day
of history and the dashboard's Sentiment trend has nothing to draw a line
between. This backfills the preceding days so that view can actually be
looked at.

The Sentiment scores are invented — a seeded random walk, so runs are
reproducible — but everything downstream of them is real: the Projections are
computed by the actual Swing Model against the actual stored Baseline, so the
seat totals move the way the model really moves them.

Two guards keep this out of anywhere it does not belong. It refuses to run
against anything but SQLite, and it never overwrites a day that already has a
snapshot, so a real pipeline run is never replaced by invented numbers.

    python scripts/seed_dev_snapshots.py [--days 14]
"""

from __future__ import annotations

import argparse
import random
from datetime import date, timedelta

from lpa.aggregate import AggregatedSentiment
from lpa.config import (
    load_coalition_config,
    load_outlets,
    load_state_election_signals,
    swing_model_config,
)
from lpa.pipeline import today_in_malaysia
from lpa.storage import (
    connect,
    load_seat_baselines,
    load_sentiment_snapshots,
    save_snapshot,
)
from lpa.swing_model import state_swing, swing_model

SEED = 20260816
"""Fixed, so two developers looking at the dashboard see the same history."""

DAILY_STEP = 0.04
"""How far a Coalition's Sentiment can drift in a day. Small enough that the
trend line wanders rather than jumps, large enough to be visible over a
fortnight."""

SENTIMENT_LIMIT = 0.6
"""Scores stay well inside the model's -1..+1 range: real aggregated
Sentiment is an average over many Articles and rarely approaches the ends."""

ARTICLES_PER_COALITION = 5
"""Roughly what a real day's scrape yields per Coalition, so the dashboard's
"Articles read" metric shows a plausible number rather than a suspicious one."""


def seeded_sentiment_history(
    coalitions: list[str], days: list[date], rng: random.Random
) -> dict[date, dict[str, float]]:
    """A random walk per Coalition, one point per day, oldest first."""
    scores = {coalition: rng.uniform(-0.2, 0.2) for coalition in coalitions}
    history: dict[date, dict[str, float]] = {}
    for day in days:
        for coalition in coalitions:
            drifted = scores[coalition] + rng.uniform(-DAILY_STEP, DAILY_STEP)
            scores[coalition] = max(-SENTIMENT_LIMIT, min(SENTIMENT_LIMIT, drifted))
        history[day] = dict(scores)
    return history


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14, help="days of back-history to seed")
    args = parser.parse_args()

    # Resolved by `connect` from DATABASE_URL, then checked — rather than
    # reading the environment here, which would be a second place for the two
    # to disagree about which database is being written to.
    engine = connect()
    if engine.dialect.name != "sqlite":
        raise SystemExit(
            f"Refusing to seed invented Sentiment into {engine.dialect.name}. "
            "This script is for a local SQLite database only."
        )

    baseline = load_seat_baselines(engine)
    if not baseline:
        raise SystemExit("No Seat Baseline in Storage. Run `python -m lpa.baseline_loader` first.")

    config = load_coalition_config()
    coalitions = sorted(config["coalition_aliases"])
    sources = sorted(outlet.name for outlet in load_outlets())
    # The same State Election Signal the real pipeline uses, so a seeded day
    # and a real one differ only in where their Sentiment came from.
    signals = load_state_election_signals()

    stored = {snapshot.computed_at for snapshot in load_sentiment_snapshots(engine)}
    today = today_in_malaysia()
    days = [today - timedelta(days=n) for n in range(args.days, 0, -1)]
    history = seeded_sentiment_history(coalitions, days, random.Random(SEED))

    written = 0
    for day, scores in history.items():
        if day in stored:
            continue
        sentiment = AggregatedSentiment(
            scores=scores,
            article_counts={coalition: ARTICLES_PER_COALITION for coalition in scores},
            total_articles=ARTICLES_PER_COALITION * len(scores),
            sources=sources,
        )
        save_snapshot(
            engine,
            swing_model(baseline, scores, signals, swing_model_config(config), day),
            sentiment,
            state_swing(baseline, scores, signals, swing_model_config(config)),
        )
        written += 1

    skipped = len(history) - written
    print(f"Seeded {written} synthetic day(s) of history.")
    if skipped:
        print(f"Left {skipped} existing day(s) untouched.")


if __name__ == "__main__":
    main()
