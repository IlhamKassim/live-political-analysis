"""Sentiment page data models and data-reading helpers.

Extracted from politikku_sentiment.py so that machine-readable export utilities
(such as sentiment_export.py) and pipeline jobs can read sentiment data
without depending on the HTML page renderer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.engine import Engine

from lpa.domain import Coalition, ElectionStatus
from lpa.storage import SentimentSnapshot

DELTA_WINDOW = timedelta(days=7)
DELTA_TOLERANCE = timedelta(days=1)


@dataclass(frozen=True)
class SentimentPageRow:
    """One Coalition's score and coverage in the latest sentiment snapshot."""

    coalition: Coalition
    name: str
    article_count: int
    score: float
    delta: float | None


@dataclass(frozen=True)
class HistoricalSentimentPoint:
    """One day's aggregated sentiment scores for historical trend rendering."""

    computed_at: date
    total_articles: int
    scores: Mapping[Coalition, float]


@dataclass(frozen=True)
class SentimentPageModel:
    """Data backing sentiment analysis and exports."""

    updated_at: date
    sources_count: int
    status: ElectionStatus
    total_articles: int
    rows: tuple[SentimentPageRow, ...]
    history: tuple[HistoricalSentimentPoint, ...]
    sources: tuple[str, ...]


def sentiment_rows(
    history: Sequence[SentimentSnapshot],
    names: Mapping[Coalition, str],
) -> tuple[SentimentPageRow, ...]:
    """Compute per-Coalition sentiment rows ordered by coverage volume."""
    if not history:
        return ()
    latest = history[-1].sentiment
    target = history[-1].computed_at - DELTA_WINDOW
    eligible = [snap for snap in history[:-1] if abs(snap.computed_at - target) <= DELTA_TOLERANCE]
    earlier_snap = (
        min(
            eligible,
            key=lambda s: (abs(s.computed_at - target), -s.computed_at.toordinal()),
        )
        if eligible
        else None
    )
    earlier = earlier_snap.sentiment if earlier_snap is not None else None
    coalitions = sorted(latest.article_counts, key=lambda c: (-latest.article_counts[c], c))
    rows = []
    for coalition in coalitions:
        score = latest.scores.get(coalition, 0.0)
        delta = (
            score - earlier.scores[coalition] if earlier and coalition in earlier.scores else None
        )
        rows.append(
            SentimentPageRow(
                coalition=coalition,
                name=names.get(coalition, coalition),
                article_count=latest.article_counts[coalition],
                score=score,
                delta=delta,
            )
        )
    return tuple(rows)


def sentiment_page_model(
    engine: Engine | None = None,
    snapshots: Sequence[SentimentSnapshot] | None = None,
    names: Mapping[Coalition, str] | None = None,
    status: ElectionStatus | None = None,
) -> SentimentPageModel:
    """Build the model for the sentiment analysis page from Storage and configuration."""
    from lpa.config import coalition_names, load_coalition_config, load_election_status
    from lpa.pipeline import today_in_malaysia
    from lpa.storage import load_sentiment_snapshots

    if snapshots is None:
        if engine is None:
            from lpa.storage import connect

            engine = connect()
        snapshots = load_sentiment_snapshots(engine)

    if names is None:
        config = load_coalition_config()
        names = coalition_names(config)

    if status is None:
        status = load_election_status()

    if snapshots:
        latest = snapshots[-1]
        updated_at = latest.computed_at
        total_articles = latest.sentiment.total_articles
        sources = tuple(latest.sentiment.sources)
        sources_count = len(sources)
    else:
        updated_at = today_in_malaysia()
        total_articles = 0
        sources = ()
        sources_count = 0

    rows = sentiment_rows(snapshots, names)

    history_points = tuple(
        HistoricalSentimentPoint(
            computed_at=snap.computed_at,
            total_articles=snap.sentiment.total_articles,
            scores=snap.sentiment.scores,
        )
        for snap in snapshots
    )

    return SentimentPageModel(
        updated_at=updated_at,
        sources_count=sources_count,
        status=status,
        total_articles=total_articles,
        rows=rows,
        history=history_points,
        sources=sources,
    )
