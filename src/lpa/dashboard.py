"""The Dashboard: a Streamlit app rendering the latest stored Projection.

Read-only. It never scrapes, scores or projects — it reads what the daily
pipeline left in Storage (issue #8). Anything it cannot read, it says so about
rather than inventing: an empty database gets instructions, not a blank page.

Two presentation rules the page is built around:

Baseline and Projection are never shown as the same kind of number. The
Baseline is GE15 fact; the Projection is an uncalibrated model estimate
(ADR 0003). They sit in adjacent columns of one table so the change between
them is legible, but every label, caption and caveat keeps the distinction —
user story 7.

Thin history is stated, not drawn. A trend line needs at least
`MINIMUM_TREND_DAYS` days; below that the page shows the single day's scores
as bars and says how many days it has. This matters because the pipeline
writes one row per day, so a freshly deployed instance genuinely has one
point, and a one-point line chart renders as an empty plot that reads as
"no data" or, worse, as a flat trend.

Run it with `streamlit run src/lpa/dashboard.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

import pandas as pd
import streamlit as st

from lpa.config import load_coalition_config, swing_model_config
from lpa.domain import Coalition, Projection, SeatBaseline, SwingModelConfig
from lpa.storage import (
    SentimentSnapshot,
    connect,
    load_projections,
    load_seat_baselines,
    load_sentiment_snapshots,
)

# Commented rather than given the attribute docstrings the rest of the package
# uses: Streamlit's "magic" renders a bare string literal at module level onto
# the page, so a docstring here would print itself above the title.

# Days of history a Sentiment trend line needs before it means anything.
MINIMUM_TREND_DAYS = 2

# How long a read is reused. The pipeline writes once a day, so this only
# decides how quickly a fresh run reaches an already-open browser tab.
CACHE_SECONDS = 900

TOTAL_SEATS = 222


@st.cache_resource
def _engine():
    """One engine per server process, not one per rerun.

    Streamlit re-executes this module top to bottom on every interaction.
    """
    return connect()


@st.cache_data(ttl=CACHE_SECONDS)
def _stored() -> tuple[
    Sequence[SeatBaseline], Sequence[Projection], Sequence[SentimentSnapshot]
]:
    engine = _engine()
    return (
        load_seat_baselines(engine),
        load_projections(engine),
        load_sentiment_snapshots(engine),
    )


def baseline_seat_totals(baseline: Sequence[SeatBaseline]) -> dict[Coalition, int]:
    """Seats each Coalition actually won at GE15 — fact, not estimate."""
    totals: dict[Coalition, int] = {}
    for seat in baseline:
        totals[seat.winner] = totals.get(seat.winner, 0) + 1
    return totals


def government_seats(
    totals: Mapping[Coalition, int], config: SwingModelConfig
) -> int:
    return sum(
        seats
        for coalition, seats in totals.items()
        if coalition in config.government_coalitions
    )


def seat_breakdown(
    baseline_totals: Mapping[Coalition, int],
    projection: Projection,
    config: SwingModelConfig,
) -> pd.DataFrame:
    """Baseline against Projection, per Coalition, strongest projection first.

    Coalitions that hold nothing under either number are dropped: the Swing
    Model tallies every Coalition that stood anywhere, and a dozen 0-vs-0 rows
    bury the ones the reader came for.
    """
    projected = projection.coalition_seat_totals
    rows = [
        {
            "Coalition": coalition,
            "Bloc": (
                "Government"
                if coalition in config.government_coalitions
                else "Opposition"
            ),
            "Baseline (GE15)": baseline_totals.get(coalition, 0),
            "Projected (GE16)": projected.get(coalition, 0),
            "Change": projected.get(coalition, 0) - baseline_totals.get(coalition, 0),
        }
        for coalition in set(baseline_totals) | set(projected)
        if baseline_totals.get(coalition, 0) or projected.get(coalition, 0)
    ]
    return pd.DataFrame(rows).sort_values(
        ["Projected (GE16)", "Coalition"], ascending=[False, True]
    )


def sentiment_trend(snapshots: Sequence[SentimentSnapshot]) -> pd.DataFrame:
    """Stored Sentiment as one long-form row per day per Coalition.

    Long form rather than a column per Coalition so a day that scored a
    Coalition no coverage names is simply absent from the line, instead of
    being filled in as a zero the model never produced.
    """
    return pd.DataFrame(
        [
            {"Day": snapshot.computed_at, "Coalition": coalition, "Sentiment": score}
            for snapshot in snapshots
            for coalition, score in sorted(snapshot.sentiment.scores.items())
        ]
    )


def render_headline(projection: Projection, config: SwingModelConfig) -> None:
    seats = government_seats(projection.coalition_seat_totals, config)
    threshold = config.majority_threshold
    if projection.government_majority:
        st.success(
            f"### Government Coalition retains its Majority\n"
            f"Projected **{seats} of {TOTAL_SEATS}** Seats — "
            f"{threshold} needed, a margin of {seats - threshold}."
        )
    else:
        st.error(
            f"### Government Coalition loses its Majority\n"
            f"Projected **{seats} of {TOTAL_SEATS}** Seats — "
            f"{threshold} needed, short by {threshold - seats}."
        )


def render_summary(
    projection: Projection,
    baseline_totals: Mapping[Coalition, int],
    sentiment: SentimentSnapshot,
    config: SwingModelConfig,
) -> None:
    projected = government_seats(projection.coalition_seat_totals, config)
    at_ge15 = government_seats(baseline_totals, config)
    left, middle, right = st.columns(3)
    left.metric(
        "Government Coalition Seats",
        projected,
        delta=projected - at_ge15,
        help="Projected for GE16. The change is against its GE15 Baseline.",
    )
    middle.metric(
        "Majority threshold",
        config.majority_threshold,
        help=f"More than half of the {TOTAL_SEATS} Seats in the Dewan Rakyat.",
    )
    right.metric(
        "Articles read",
        sentiment.sentiment.total_articles,
        help="Coverage behind the latest Sentiment score. A Projection built "
        "on a handful of articles is a weaker signal than one built on many.",
    )


def render_breakdown(
    baseline_totals: Mapping[Coalition, int],
    projection: Projection,
    config: SwingModelConfig,
) -> None:
    st.subheader("Seats per Coalition")
    st.caption(
        "**Baseline (GE15)** is historical fact — what each Coalition won in "
        "2022. **Projected (GE16)** is the Swing Model's estimate, and is not "
        "calibrated. The two are different kinds of number."
    )
    st.dataframe(
        seat_breakdown(baseline_totals, projection, config),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Change": st.column_config.NumberColumn(
                "Change", format="%+d", help="Projected Seats minus GE15 Seats."
            )
        },
    )


def render_trend(snapshots: Sequence[SentimentSnapshot]) -> None:
    st.subheader("Sentiment over time")
    trend = sentiment_trend(snapshots)

    if len(snapshots) < MINIMUM_TREND_DAYS:
        st.info(
            f"Only **{len(snapshots)} day** of history so far. A trend needs at "
            f"least {MINIMUM_TREND_DAYS} days, so today's Sentiment is shown on "
            "its own below; the line appears once the daily pipeline has run "
            "again."
        )
        st.bar_chart(trend, x="Coalition", y="Sentiment", horizontal=True)
        return

    st.line_chart(trend, x="Day", y="Sentiment", color="Coalition")
    st.caption(
        f"{len(snapshots)} days of history. Sentiment runs from −1 (wholly "
        "negative coverage) to +1 (wholly positive), averaged over the "
        "Articles that named each Coalition that day."
    )


def render_sources(sentiment: SentimentSnapshot, updated: date) -> None:
    st.subheader("Sources and method")
    st.caption(f"Last updated **{updated:%-d %B %Y}** (Malaysian date).")

    sources = sentiment.sentiment.sources
    counts = sentiment.sentiment.article_counts
    left, right = st.columns(2)
    with left:
        st.markdown("**Outlets read**")
        st.markdown(
            "\n".join(f"- {source}" for source in sources)
            or "- _no outlet reported for this day_"
        )
    with right:
        st.markdown("**Articles naming each Coalition**")
        st.markdown(
            "\n".join(
                f"- {coalition}: {count}"
                for coalition, count in sorted(counts.items(), key=lambda kv: -kv[1])
            )
            or "- _no Coalition was named_"
        )

    st.markdown(
        """
**How the Projection is built.** Each day the pipeline reads the outlets
above, scores every Article per Coalition with a self-hosted multilingual
sentiment model, and averages those scores into one Sentiment per Coalition.
The Swing Model turns that Sentiment into a vote-share Swing, blends in the
result of any state election held since GE15 for that state's Seats only,
applies the Swing to each Seat's GE15 Baseline share, and tallies the Seats.

**What it is not.** The Projection is model-driven and **not an official
forecast**. Two constants in the Swing Model — how much Swing a unit of
Sentiment buys, and how heavily a state election counts — were chosen by
judgement rather than fitted to polling data, so treat the seat totals as an
indication of direction, not a prediction. Sentiment is an unweighted mean
over Articles, so a prolific outlet counts for more than a quiet one. Only
Coalition-level totals are published; individual Seats are not called.

Baseline data comes from the published GE15 result and the parliamentary
census. Vocabulary is defined in `CONTEXT.md`; the decisions behind the model
are recorded in `docs/adr/`.
        """
    )


def main() -> None:
    st.set_page_config(page_title="GE16 Projection", page_icon="🇲🇾", layout="wide")
    st.title("GE16 Projection")
    st.caption(
        "Malaysian political sentiment, tracked daily, projected onto the "
        "222 Seats of the Dewan Rakyat. A model estimate, not an official "
        "forecast."
    )

    baseline, projections, snapshots = _stored()
    if not baseline:
        st.warning(
            "No Seat Baseline in Storage. Run `python -m lpa.baseline_loader` "
            "to load the GE15 result, then `python -m lpa.pipeline`."
        )
        return
    if not projections or not snapshots:
        st.warning(
            "No Projection stored yet. Run `python -m lpa.pipeline` to compute "
            "today's, then reload this page."
        )
        return

    latest, sentiment = projections[-1], snapshots[-1]
    baseline_totals = baseline_seat_totals(baseline)
    config = swing_model_config(load_coalition_config())

    render_headline(latest, config)
    render_summary(latest, baseline_totals, sentiment, config)
    st.divider()
    render_breakdown(baseline_totals, latest, config)
    st.divider()
    render_trend(snapshots)
    st.divider()
    render_sources(sentiment, latest.computed_at)


# Called at import, not under an `if __name__ == "__main__"` guard as the other
# modules here are: Streamlit executes this file as the page itself on every
# rerun, and does not give it `__main__` as its module name, so a guard would
# render an empty page. Nothing else imports this module.
main()
