"""Storage: the per-Seat Baseline table and its reads and writes.

One schema over SQLAlchemy Core, so the same code runs against the free-tier
Postgres the pipeline uses (ADR 0002) and against a local SQLite file for
development. Point `DATABASE_URL` at whichever is wanted.

The Baseline is a one-time load, not daily data (ADR 0001), so writes replace
the stored snapshot wholesale inside one transaction. Running the loader twice
therefore leaves 222 rows, not 444.
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Sequence

from sqlalchemy import (
    Column,
    Float,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    select,
)
from sqlalchemy.engine import Engine

from lpa.domain import SeatBaseline

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///lpa.db"

metadata = MetaData()

seat_baseline = Table(
    "seat_baseline",
    metadata,
    Column("code", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("state", String, nullable=False),
    Column("vote_share", String, nullable=False),
    Column("margin", Float, nullable=False),
    Column("demographics", String, nullable=False),
)


def connect(database_url: str | None = None) -> Engine:
    """Open the database named by `database_url`, or by `DATABASE_URL`."""
    url = database_url or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    engine = create_engine(url)
    metadata.create_all(engine)
    return engine


def save_seat_baselines(engine: Engine, baselines: Iterable[SeatBaseline]) -> int:
    """Replace the stored Baseline with `baselines`. Returns the row count."""
    rows = [
        {
            "code": b.code,
            "name": b.name,
            "state": b.state,
            "vote_share": json.dumps(dict(b.vote_share)),
            "margin": b.margin,
            "demographics": json.dumps(dict(b.demographics)),
        }
        for b in baselines
    ]
    with engine.begin() as connection:
        connection.execute(delete(seat_baseline))
        if rows:
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
                vote_share=json.loads(row["vote_share"]),
                margin=row["margin"],
                demographics=json.loads(row["demographics"]),
            )
            for row in rows
        ]
