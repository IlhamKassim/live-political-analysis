"""Storage: the per-Seat Baseline table and its reads and writes.

One schema over SQLAlchemy Core, so the same code runs against the free-tier
Postgres the pipeline uses (ADR 0002) and against a local SQLite file for
development. Point `DATABASE_URL` at whichever is wanted. Per-Coalition vote
share and the census profile are JSON columns rather than encoded strings, so
they stay queryable in SQL on either backend.

The Baseline is a one-time load, not daily data (ADR 0001), so writes replace
the stored snapshot wholesale inside one transaction. Running the loader twice
therefore leaves 222 rows, not 444.
"""

from __future__ import annotations

import os
from typing import Iterable, Sequence

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    select,
)
from sqlalchemy.engine import Engine

from lpa.aggregate import AggregatedSentiment
from lpa.domain import Projection, SeatBaseline

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///lpa.db"

metadata = MetaData()

seat_baseline = Table(
    "seat_baseline",
    metadata,
    Column("code", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("state", String, nullable=False),
    Column("vote_share", JSON, nullable=False),
    Column("margin", Float, nullable=False),
    Column("demographics", JSON, nullable=False),
)


projection_snapshot = Table(
    "projection_snapshot",
    metadata,
    # One row per day: the pipeline is a daily batch, and re-running it
    # corrects the day rather than adding a second answer for it.
    Column("computed_at", Date, primary_key=True),
    Column("coalition_seat_totals", JSON, nullable=False),
    Column("government_majority", Boolean, nullable=False),
)

sentiment_snapshot = Table(
    "sentiment_snapshot",
    metadata,
    Column("computed_at", Date, primary_key=True),
    Column("scores", JSON, nullable=False),
    Column("article_counts", JSON, nullable=False),
    Column("total_articles", Integer, nullable=False),
    Column("sources", JSON, nullable=False),
)


def connect(database_url: str | None = None) -> Engine:
    """Open the database named by `database_url`, or by `DATABASE_URL`."""
    url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    engine = create_engine(url)
    metadata.create_all(engine)
    return engine


def save_seat_baselines(engine: Engine, baselines: Iterable[SeatBaseline]) -> int:
    """Replace the stored Baseline with `baselines`. Returns the row count.

    Refuses to write an empty Baseline: a fetch that comes back empty would
    otherwise destroy the stored snapshot and leave nothing to serve.
    """
    rows = [
        {
            "code": b.code,
            "name": b.name,
            "state": b.state,
            "vote_share": dict(b.vote_share),
            "margin": b.margin,
            "demographics": dict(b.demographics),
        }
        for b in baselines
    ]
    if not rows:
        raise ValueError("refusing to replace the stored Baseline with nothing")
    with engine.begin() as connection:
        connection.execute(delete(seat_baseline))
        connection.execute(seat_baseline.insert(), rows)
    return len(rows)


def load_seat_baselines(engine: Engine) -> Sequence[SeatBaseline]:
    """Read the stored Baseline back, ordered by Seat code."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(seat_baseline).order_by(seat_baseline.c.code)
        ).mappings()
        return [
            SeatBaseline(
                code=row["code"],
                name=row["name"],
                state=row["state"],
                vote_share=row["vote_share"],
                margin=row["margin"],
                demographics=row["demographics"],
            )
            for row in rows
        ]


def save_snapshot(
    engine: Engine,
    projection: Projection,
    sentiment: AggregatedSentiment,
) -> None:
    """Record one day's Projection and Sentiment, replacing that day if present.

    Keyed on the date rather than appended, so a re-run corrects the day
    instead of leaving two answers for it. History across days is what the
    dashboard's trend line reads (issue #1, story 15).
    """
    day = projection.computed_at
    with engine.begin() as connection:
        for table, row in (
            (
                projection_snapshot,
                {
                    "computed_at": day,
                    "coalition_seat_totals": dict(projection.coalition_seat_totals),
                    "government_majority": projection.government_majority,
                },
            ),
            (
                sentiment_snapshot,
                {
                    "computed_at": day,
                    "scores": dict(sentiment.scores),
                    "article_counts": dict(sentiment.article_counts),
                    "total_articles": sentiment.total_articles,
                    "sources": list(sentiment.sources),
                },
            ),
        ):
            connection.execute(
                delete(table).where(table.c.computed_at == day)
            )
            connection.execute(table.insert(), row)


def load_projections(engine: Engine) -> Sequence[Projection]:
    """Every stored Projection, oldest first."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(projection_snapshot).order_by(projection_snapshot.c.computed_at)
        ).mappings()
        return [
            Projection(
                coalition_seat_totals=row["coalition_seat_totals"],
                government_majority=row["government_majority"],
                computed_at=row["computed_at"],
            )
            for row in rows
        ]


def load_sentiment_snapshots(engine: Engine) -> Sequence[AggregatedSentiment]:
    """Every stored Sentiment snapshot, oldest first."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(sentiment_snapshot).order_by(sentiment_snapshot.c.computed_at)
        ).mappings()
        return [
            AggregatedSentiment(
                scores=row["scores"],
                article_counts=row["article_counts"],
                total_articles=row["total_articles"],
                sources=row["sources"],
            )
            for row in rows
        ]
