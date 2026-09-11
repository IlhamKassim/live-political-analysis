"""Exercise real Postgres transactions and JSON/date round trips in an isolated schema."""

import os
from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from fixtures import government_config, two_coalition_seats
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from lpa.aggregate import AggregatedSentiment
from lpa.storage import (
    load_projections,
    load_seat_baselines,
    load_sentiment_snapshots,
    metadata,
    normalise_database_url,
    save_seat_baselines,
    save_snapshot,
)
from lpa.swing_model import swing_model


@pytest.mark.postgres
def test_postgres_round_trip_replacement_and_rollback():
    url = os.environ["TEST_POSTGRES_URL"]
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1"} or parsed.database != "lpa_test":
        pytest.fail("Integration tests require a local lpa_test database")
    schema = "test_" + uuid4().hex
    admin = create_engine(normalise_database_url(url))
    engine = None
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            normalise_database_url(url), connect_args={"options": f"-csearch_path={schema}"}
        )
        metadata.create_all(engine)
        baseline = two_coalition_seats()
        save_seat_baselines(engine, baseline)
        save_seat_baselines(engine, baseline)
        assert list(load_seat_baselines(engine)) == baseline
        # A duplicate key must roll back the delete as well as the failed insert.
        with pytest.raises(IntegrityError):
            save_seat_baselines(engine, [baseline[0], baseline[0]])
        assert list(load_seat_baselines(engine)) == baseline

        day = date(2026, 9, 1)
        projection = swing_model(baseline, {}, [], government_config(), day)
        sentiment = AggregatedSentiment(
            scores={"PH": 0.2}, article_counts={"PH": 3}, total_articles=3, sources=["fixture"]
        )
        save_snapshot(engine, projection, sentiment, {})
        corrected = replace(sentiment, total_articles=4)
        save_snapshot(engine, projection, corrected, {})
        assert list(load_projections(engine)) == [projection]
        snapshots = load_sentiment_snapshots(engine)
        assert len(snapshots) == 1
        assert snapshots[0].sentiment == corrected
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()
