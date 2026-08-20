"""Storage: the Baseline, the daily snapshots, and their reads and writes.

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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

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
from lpa.domain import Coalition, ElectionStatus, Projection, SeatBaseline, SeatCall
from lpa.poll_calibration import LeaderRating, PollCalibration
from lpa.return_trigger import PreviousWatch

DEFAULT_DATABASE_URL = "sqlite+pysqlite:///lpa.db"

POSTGRES_DRIVER = "postgresql+psycopg"
"""The driver the `postgres` extra installs, named explicitly in the URL.

SQLAlchemy reads a bare `postgresql://` as psycopg2, which this project does
not depend on, so the URL every hosted Postgres hands out would fail on a
missing driver rather than on anything true about the database.
"""


def normalise_database_url(url: str) -> str:
    """Name the driver in a Postgres URL that does not name one.

    Hosted Postgres providers hand out `postgresql://…` (Neon, Supabase) or
    the older `postgres://…` (Heroku's scheme, which SQLAlchemy 2 rejects
    outright). Both are pasted straight from a dashboard into a secret by a
    human who has no reason to know this project's driver, so the URL is
    corrected here rather than in the instructions — the alternative is a
    hand-edited connection string, which is one more thing to get wrong at
    the exact moment nothing else is working yet.

    Anything already naming a driver, SQLite included, is returned untouched.
    """
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            return f"{POSTGRES_DRIVER}://{url[len(scheme) :]}"
    return url


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

seat_call = Table(
    "seat_call",
    metadata,
    # The latest two Projections' Seat Calls and no others — ADR 0005 keeps a
    # short window (~444 rows) rather than ~81k a year against a free-tier
    # Postgres, extended from one day to two (#54) so an overnight diff (which
    # Seats crossed the Majority line since yesterday) is computable. Two, not
    # more: the diff is the only consumer, and it never needs a third day.
    # `computed_at` is stored so a read can tell which Projection these belong
    # to, not to key a history that is deliberately not kept in full.
    Column("computed_at", Date, primary_key=True),
    Column("code", String, primary_key=True),
    Column("coalition", String, nullable=False),
    Column("margin", Float, nullable=False),
)

frozen_projection = Table(
    "frozen_projection",
    metadata,
    # Permanent, unlike projection_snapshot: one row per day the pipeline ran
    # while Election Status was "called" (#54). A batch pipeline cannot know
    # in advance which day will turn out to be the last one before polling —
    # the campaign period's length is not known ahead of time, and a run can
    # fail or be skipped — so every called day is archived rather than
    # guessing which one is "the" final day; the final pre-poll Projection is
    # simply whichever archived row has the latest `computed_at` at or before
    # polling day, read back after the fact. Never pruned by ordinary
    # retention; a same-day rerun replaces its own row rather than doubling
    # it, the same as `projection_snapshot`.
    Column("computed_at", Date, primary_key=True),
    Column("coalition_seat_totals", JSON, nullable=False),
    Column("government_majority", Boolean, nullable=False),
)

frozen_seat_call = Table(
    "frozen_seat_call",
    metadata,
    # The Seat-Level half of `frozen_projection`, split out the same way
    # `seat_call` is split from `projection_snapshot`.
    Column("computed_at", Date, primary_key=True),
    Column("code", String, primary_key=True),
    Column("coalition", String, nullable=False),
    Column("margin", Float, nullable=False),
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

state_swing_snapshot = Table(
    "state_swing_snapshot",
    metadata,
    # A new table, not a new column on `projection_snapshot` (#53a): `connect`
    # only ever runs `metadata.create_all`, which creates a table that does
    # not exist yet but never alters one that already does. A new column on
    # an already-deployed table would silently never reach the live
    # database, and the next `save_snapshot` call against it would fail on
    # an unknown column. One row per state per day, kept forever like
    # `projection_snapshot` rather than pruned like `seat_call` — roughly a
    # dozen states, not 222 Seats, so a year of history is a few thousand
    # rows, not tens of thousands.
    Column("computed_at", Date, primary_key=True),
    Column("state", String, primary_key=True),
    # The Swing applied to this state's Seats, per Coalition:
    # Mapping[Coalition, float].
    Column("swing", JSON, nullable=False),
)

trigger_watch = Table(
    "trigger_watch",
    metadata,
    # #40's Return Trigger detection needs "what was this yesterday" for
    # Election Status and which states have a State Election Signal — both
    # come from hand-maintained config files, not a daily snapshot, so
    # nothing else in Storage already answers that. One row per day the
    # pipeline ran, kept forever like `projection_snapshot` — a few hundred
    # bytes a day, not worth pruning.
    Column("computed_at", Date, primary_key=True),
    Column("election_called", Boolean, nullable=False),
    Column("polling_date", Date, nullable=True),
    # Sorted list[str] — every state with a State Election Signal in play
    # as of this run.
    Column("state_signal_states", JSON, nullable=False),
)

trigger_post_log = Table(
    "trigger_post_log",
    metadata,
    # A permanent log of every Return Trigger post composed (#40), for the
    # RSS/Atom feed — the feed has to accumulate history across days, and
    # nothing else in Storage keeps a record of what fired and when. Logged
    # once per composed post regardless of whether the Telegram send itself
    # succeeds: the feed is a record of what happened, not of the delivery
    # channel's uptime. Autoincrementing rather than `computed_at` alone,
    # since more than one trigger can fire the same day.
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("computed_at", Date, nullable=False),
    Column("title", String, nullable=False),
    Column("caption", String, nullable=False),
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
    engine = create_engine(normalise_database_url(url))
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
        rows = connection.execute(select(seat_baseline).order_by(seat_baseline.c.code)).mappings()
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
    state_swing: Mapping[str, Mapping[Coalition, float]],
    *,
    status: ElectionStatus | None = None,
) -> None:
    """Record one day's Projection, Sentiment, and per-state Swing (#53a),
    replacing that day if present.

    Keyed on the date rather than appended, so a re-run corrects the day
    instead of leaving two answers for it. History across days is what the
    dashboard's trend line reads (issue #1, story 15). `state_swing` is
    required rather than defaulted to `{}`: a caller that forgot to wire it
    up would otherwise silently persist an empty per-state Swing for that
    day forever, rather than failing loudly at the call site.

    Seat Calls are the exception. Storage keeps the latest two Projections'
    (ADR 0005, extended by #54) — the newest that came with any, plus the one
    immediately before it — so a write replaces/extends them only if it is at
    least as new as what is already there *and* has calls of its own. Both
    halves matter:

    - Only accepting a day at least as new keeps the write order-independent.
      `scripts/seed_dev_snapshots.py` backfills days behind today, and running
      it after a real run must not leave the current Projection showing a
      seeded day's calls, nor evict a kept day the seeded one is older than.
    - Only replacing when there are calls to put there means a Projection
      carrying none cannot empty the table. `load_projections` hands back every
      day but the newest with `seat_calls` empty, so a round-tripped Projection
      re-saved under a later day would otherwise silently destroy the only
      per-Seat rows in Storage.

    `status`: when supplied and `status.called`, this day's full Seat-Level
    Projection is additionally archived into `frozen_projection`/
    `frozen_seat_call` — permanent, never pruned by the two-day window above.
    See those tables' comments for why every called day is archived rather
    than only the one that turns out to be last before polling.
    """
    day = projection.computed_at
    with engine.begin() as connection:
        # Ordered rather than `max()`, so the value comes back through the
        # column's Date type: SQLite stores dates as text, and an aggregate
        # over them returns the text.
        newest_calls_day = connection.execute(
            select(seat_call.c.computed_at).order_by(seat_call.c.computed_at.desc()).limit(1)
        ).scalar()
        if projection.seat_calls and (newest_calls_day is None or day >= newest_calls_day):
            # A same-day rerun replaces only that day's rows. A genuinely new
            # day becomes the newest of the two kept days, which evicts
            # anything older than the *previous* newest — leaving exactly the
            # new day and the one before it.
            connection.execute(delete(seat_call).where(seat_call.c.computed_at == day))
            if newest_calls_day is not None and day > newest_calls_day:
                connection.execute(
                    delete(seat_call).where(seat_call.c.computed_at < newest_calls_day)
                )
            connection.execute(
                seat_call.insert(),
                [
                    {
                        "computed_at": day,
                        "code": call.code,
                        "coalition": call.coalition,
                        "margin": call.margin,
                    }
                    for call in projection.seat_calls
                ],
            )
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
            connection.execute(delete(table).where(table.c.computed_at == day))
            connection.execute(table.insert(), row)

        # One row per state, like `seat_call` — outside the single-row loop
        # above, which only fits a table with exactly one row per day.
        connection.execute(
            delete(state_swing_snapshot).where(state_swing_snapshot.c.computed_at == day)
        )
        if state_swing:
            connection.execute(
                state_swing_snapshot.insert(),
                [
                    {"computed_at": day, "state": state, "swing": dict(swing)}
                    for state, swing in state_swing.items()
                ],
            )

        if status is not None and status.called:
            connection.execute(
                delete(frozen_projection).where(frozen_projection.c.computed_at == day)
            )
            connection.execute(
                frozen_projection.insert(),
                {
                    "computed_at": day,
                    "coalition_seat_totals": dict(projection.coalition_seat_totals),
                    "government_majority": projection.government_majority,
                },
            )
            if projection.seat_calls:
                connection.execute(
                    delete(frozen_seat_call).where(frozen_seat_call.c.computed_at == day)
                )
                connection.execute(
                    frozen_seat_call.insert(),
                    [
                        {
                            "computed_at": day,
                            "code": call.code,
                            "coalition": call.coalition,
                            "margin": call.margin,
                        }
                        for call in projection.seat_calls
                    ],
                )


def load_projections(engine: Engine) -> Sequence[Projection]:
    """Every stored Projection, oldest first.

    Only the latest two carry Seat Calls — Storage keeps that two-day window
    alone (ADR 0005, extended by #54). They are attached here, to the
    Projection whose day they were computed on, rather than handed back
    separately: a caller that had to pair them up itself could pair them
    wrongly, and a Seat Call shown under the wrong date is indistinguishable
    from a right one.
    """
    with engine.connect() as connection:
        calls_by_day: dict[date, list[SeatCall]] = {}
        for row in connection.execute(select(seat_call).order_by(seat_call.c.code)).mappings():
            calls_by_day.setdefault(row["computed_at"], []).append(
                SeatCall(
                    code=row["code"],
                    coalition=row["coalition"],
                    margin=row["margin"],
                )
            )
        rows = connection.execute(
            select(projection_snapshot).order_by(projection_snapshot.c.computed_at)
        ).mappings()
        return [
            Projection(
                coalition_seat_totals=row["coalition_seat_totals"],
                government_majority=row["government_majority"],
                computed_at=row["computed_at"],
                seat_calls=tuple(calls_by_day.get(row["computed_at"], ())),
            )
            for row in rows
        ]


def load_frozen_projections(engine: Engine) -> Sequence[Projection]:
    """Every permanently archived day (#54), oldest first — see `frozen_projection`.

    Every day the pipeline ran while Election Status was "called," not only
    the eventual last one; a caller after polling day wanting *the* final
    pre-poll Projection reads the last entry with `computed_at` at or before
    polling day. Shaped exactly like `load_projections`'s return, for the
    same reason: a caller pairing calls to totals itself could pair them
    wrongly.
    """
    with engine.connect() as connection:
        calls_by_day: dict[date, list[SeatCall]] = {}
        for row in connection.execute(
            select(frozen_seat_call).order_by(frozen_seat_call.c.code)
        ).mappings():
            calls_by_day.setdefault(row["computed_at"], []).append(
                SeatCall(
                    code=row["code"],
                    coalition=row["coalition"],
                    margin=row["margin"],
                )
            )
        rows = connection.execute(
            select(frozen_projection).order_by(frozen_projection.c.computed_at)
        ).mappings()
        return [
            Projection(
                coalition_seat_totals=row["coalition_seat_totals"],
                government_majority=row["government_majority"],
                computed_at=row["computed_at"],
                seat_calls=tuple(calls_by_day.get(row["computed_at"], ())),
            )
            for row in rows
        ]


def load_state_swing(engine: Engine, computed_at: date) -> Mapping[str, Mapping[Coalition, float]]:
    """One day's Swing per state (#53a) — empty for a day nothing was stored for.

    Parameterized on the day rather than returning full history: a caller
    already knows which Projection it is pairing this with (its own
    `computed_at`), the same way `load_projections` pairs Seat Calls to a
    Projection internally rather than handing the caller two lists to match
    up itself — except here the caller, not this function, already holds
    the day, so there is nothing to mismatch.
    """
    with engine.connect() as connection:
        rows = connection.execute(
            select(state_swing_snapshot).where(state_swing_snapshot.c.computed_at == computed_at)
        ).mappings()
        return {row["state"]: row["swing"] for row in rows}


def save_trigger_watch(
    engine: Engine,
    computed_at: date,
    status: ElectionStatus,
    signal_states: Iterable[str],
) -> None:
    """Record today's Election-Status/State-Signal watch state (#40).

    Keyed on the date, replacing that day if present, the same "a re-run
    corrects the day" pattern every other snapshot table in this module
    follows.
    """
    with engine.begin() as connection:
        connection.execute(delete(trigger_watch).where(trigger_watch.c.computed_at == computed_at))
        connection.execute(
            trigger_watch.insert(),
            {
                "computed_at": computed_at,
                "election_called": status.called,
                "polling_date": status.polling_date,
                "state_signal_states": sorted(signal_states),
            },
        )


def load_previous_trigger_watch(engine: Engine, before: date) -> PreviousWatch | None:
    """The most recent watch row strictly before `before`, or `None`.

    Strictly before rather than "yesterday" by calendar subtraction: a
    skipped day (a failed run, a quiet stretch) must not make `detect_
    triggers` compare today against a day that never happened, and reading
    the latest row before today already does the right thing whether the
    gap is one day or ten.
    """
    with engine.connect() as connection:
        row = (
            connection.execute(
                select(trigger_watch)
                .where(trigger_watch.c.computed_at < before)
                .order_by(trigger_watch.c.computed_at.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
    if row is None:
        return None
    return PreviousWatch(
        election_called=row["election_called"],
        polling_date=row["polling_date"],
        signal_states=frozenset(row["state_signal_states"]),
    )


def trigger_watch_exists(engine: Engine, computed_at: date) -> bool:
    """Whether a Return Trigger watch row already exists for `computed_at` (#40).

    Read before evaluating a day's triggers, unlike every other snapshot
    table here where a same-day rerun correcting the row is exactly right:
    a Telegram post is public and cannot be unsent, so a rerun after a day
    already has a watch row must skip evaluation entirely rather than
    re-detect (and re-post) the same trigger a second time. A rerun after a
    failure that happened *before* the watch row was written still retries
    normally, since no row exists yet to skip on.
    """
    with engine.connect() as connection:
        row = connection.execute(
            select(trigger_watch.c.computed_at).where(trigger_watch.c.computed_at == computed_at)
        ).first()
    return row is not None


def save_trigger_posts(engine: Engine, computed_at: date, posts: Iterable[tuple[str, str]]) -> None:
    """Append this day's composed Return Trigger posts to the permanent log (#40).

    `posts` is `(title, caption)` pairs, in the order they were composed.
    Appends rather than replacing what a same-day rerun already logged:
    `trigger_watch_exists` (above) is what stops a rerun from reaching this
    function a second time in the first place, so there is nothing here to
    deduplicate against.
    """
    rows = [
        {"computed_at": computed_at, "title": title, "caption": caption} for title, caption in posts
    ]
    if not rows:
        return
    with engine.begin() as connection:
        connection.execute(trigger_post_log.insert(), rows)


@dataclass(frozen=True)
class LoggedTriggerPost:
    """One historical Return Trigger post, for the RSS/Atom feed (#40)."""

    id: int
    computed_at: date
    title: str
    caption: str


def load_trigger_posts(engine: Engine) -> Sequence[LoggedTriggerPost]:
    """Every logged Return Trigger post, oldest first — the feed's full history."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(trigger_post_log).order_by(trigger_post_log.c.id)
        ).mappings()
        return [
            LoggedTriggerPost(
                id=row["id"],
                computed_at=row["computed_at"],
                title=row["title"],
                caption=row["caption"],
            )
            for row in rows
        ]


def save_poll_calibrations(engine: Engine, reports: Iterable[PollCalibration]) -> int:
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
                    poll_calibration_snapshot.c.fieldwork_end == report.fieldwork_end,
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
                    "leader_ratings": [rating.as_mapping() for rating in report.leader_ratings],
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
                    LeaderRating.from_mapping(rating) for rating in row["leader_ratings"]
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
