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
from dataclasses import dataclass
from datetime import date
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
from lpa.poll_calibration import LeaderRating, PollCalibration

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


poll_calibration_snapshot = Table(
    "poll_calibration_snapshot",
    metadata,
    # Keyed on the last day of fieldwork rather than on publication: that is
    # the day the poll measures and the day it is plotted at, and re-ingesting
    # a corrected transcription of the same survey should replace it rather
    # than leave two answers for one poll. Two surveys by one publisher do not
    # share a fieldwork end date; two publishers might, so the publisher is
    # part of the key.
    Column("publisher", String, primary_key=True),
    Column("fieldwork_end", Date, primary_key=True),
    Column("title", String, nullable=False),
    Column("report_url", String, nullable=False),
    Column("published_on", Date, nullable=False),
    Column("fieldwork_start", Date, nullable=False),
    Column("sample_size", Integer, nullable=False),
    Column("margin_of_error", Float, nullable=True),
    # The published figures verbatim, not the per-Coalition scores derived
    # from them. The derivation is this project's interpretation (ADR 0004)
    # and can be revisited; the percentages Merdeka Center printed cannot.
    Column("leader_ratings", JSON, nullable=False),
)


@dataclass(frozen=True)
class SentimentSnapshot:
    """One stored day of Sentiment: the aggregate plus the day it belongs to.

    `AggregatedSentiment` is the pure result of aggregating a day's Articles
    and carries no date of its own; a Projection does. The date is added back
    on read because a trend line is exactly the pairing of the two.
    """

    computed_at: date
    sentiment: AggregatedSentiment


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


def save_poll_calibrations(
    engine: Engine, reports: Iterable[PollCalibration]
) -> int:
    """Store `reports` as Poll Calibration points. Returns the count written.

    Each report replaces any stored one for the same publisher and fieldwork
    end date, so re-ingesting a report after fixing a transcription error
    corrects it. Unlike the Baseline this is not a wholesale replacement:
    reports accumulate over the years, and the data file being edited down to
    one report must not delete the history already ingested from it.
    """
    written = 0
    with engine.begin() as connection:
        for report in reports:
            connection.execute(
                delete(poll_calibration_snapshot).where(
                    poll_calibration_snapshot.c.publisher == report.publisher,
                    poll_calibration_snapshot.c.fieldwork_end
                    == report.fieldwork_end,
                )
            )
            connection.execute(
                poll_calibration_snapshot.insert(),
                {
                    "publisher": report.publisher,
                    "fieldwork_end": report.fieldwork_end,
                    "title": report.title,
                    "report_url": report.report_url,
                    "published_on": report.published_on,
                    "fieldwork_start": report.fieldwork_start,
                    "sample_size": report.sample_size,
                    "margin_of_error": report.margin_of_error,
                    "leader_ratings": [
                        rating.as_mapping() for rating in report.leader_ratings
                    ],
                },
            )
            written += 1
    return written


def load_poll_calibrations(engine: Engine) -> Sequence[PollCalibration]:
    """Every stored Poll Calibration point, oldest fieldwork first."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(poll_calibration_snapshot).order_by(
                poll_calibration_snapshot.c.fieldwork_end,
                poll_calibration_snapshot.c.publisher,
            )
        ).mappings()
        return [
            PollCalibration(
                publisher=row["publisher"],
                title=row["title"],
                report_url=row["report_url"],
                published_on=row["published_on"],
                fieldwork_start=row["fieldwork_start"],
                fieldwork_end=row["fieldwork_end"],
                sample_size=row["sample_size"],
                margin_of_error=row["margin_of_error"],
                leader_ratings=tuple(
                    LeaderRating.from_mapping(rating)
                    for rating in row["leader_ratings"]
                ),
            )
            for row in rows
        ]


def load_sentiment_snapshots(engine: Engine) -> Sequence[SentimentSnapshot]:
    """Every stored Sentiment snapshot, oldest first."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(sentiment_snapshot).order_by(sentiment_snapshot.c.computed_at)
        ).mappings()
        return [
            SentimentSnapshot(
                computed_at=row["computed_at"],
                sentiment=AggregatedSentiment(
                    scores=row["scores"],
                    article_counts=row["article_counts"],
                    total_articles=row["total_articles"],
                    sources=row["sources"],
                ),
            )
            for row in rows
        ]
