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

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

import altair as alt
import pandas as pd
import streamlit as st

from lpa.config import load_coalition_config, load_election_status, swing_model_config
from lpa.domain import (
    Coalition,
    ElectionStatus,
    government_seat_total,
    Projection,
    SeatBaseline,
    SwingModelConfig,
)
from lpa.pipeline import today_in_malaysia
from lpa.poll_calibration import PollCalibration, coalition_net_approval
from lpa.storage import (
    SentimentSnapshot,
    connect,
    load_poll_calibrations,
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


@dataclass(frozen=True)
class DashboardData:
    """Everything one render of the page reads, fetched in a single pass.

    Held together because the page is meaningless with only part of it, and
    because Streamlit reruns the whole script per interaction — one cached
    read beats three.
    """

    baseline: Sequence[SeatBaseline]
    projections: Sequence[Projection]
    snapshots: Sequence[SentimentSnapshot]
    calibrations: Sequence[PollCalibration]


@st.cache_resource
def _engine():
    """One engine per server process, not one per rerun.

    Streamlit re-executes this module top to bottom on every interaction.
    """
    return connect()


@st.cache_data(ttl=CACHE_SECONDS)
def load_dashboard_data() -> DashboardData:
    engine = _engine()
    return DashboardData(
        baseline=load_seat_baselines(engine),
        projections=load_projections(engine),
        snapshots=load_sentiment_snapshots(engine),
        calibrations=load_poll_calibrations(engine),
    )


def baseline_seat_totals(baseline: Sequence[SeatBaseline]) -> dict[Coalition, int]:
    """Seats each Coalition actually won at GE15 — fact, not estimate."""
    totals: dict[Coalition, int] = {}
    for seat in baseline:
        totals[seat.winner] = totals.get(seat.winner, 0) + 1
    return totals


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
            # CONTEXT.md's glossary has no word for "not in government", and
            # tells us to avoid "bloc" and "opposition"; membership of the
            # Government Coalition is the distinction it does define.
            "Government Coalition": (
                "Member" if coalition in config.government_coalitions else "—"
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


def calibration_points(
    calibrations: Sequence[PollCalibration],
) -> pd.DataFrame:
    """Stored Poll Calibration as one row per report per Coalition.

    Long form and named `Score` to match `sentiment_trend`'s shape, so the two
    can be layered on one chart against one axis. A Coalition the report rated
    no leader of is simply absent, exactly as a Coalition no Article named is
    absent from the trend.
    """
    return pd.DataFrame(
        [
            {
                "Day": report.fieldwork_end,
                "Coalition": coalition,
                "Score": score,
                "Publisher": report.publisher,
                "Report": report.title,
                "Leaders rated": derived.leader_counts[coalition],
                "Sample": report.sample_size,
            }
            for report in calibrations
            for derived in [coalition_net_approval(report.leader_ratings)]
            for coalition, score in sorted(derived.scores.items())
        ],
        columns=[
            "Day",
            "Coalition",
            "Score",
            "Publisher",
            "Report",
            "Leaders rated",
            "Sample",
        ],
    )


def calibrations_within(
    calibrations: Sequence[PollCalibration], snapshots: Sequence[SentimentSnapshot]
) -> list[PollCalibration]:
    """The reports whose fieldwork ended inside the span the trend line covers.

    A poll from months before the stored history would stretch the chart's x
    axis back to meet it and squash the Sentiment line into the right-hand
    edge — the trend, which is the thing the chart is for, would become
    unreadable in order to show one point. Those reports are reported in the
    comparison below instead, where their distance from the history can be
    stated rather than drawn.
    """
    if not snapshots:
        return []
    first, last = snapshots[0].computed_at, snapshots[-1].computed_at
    return [
        report for report in calibrations if first <= report.fieldwork_end <= last
    ]


def nearest_snapshot(
    snapshots: Sequence[SentimentSnapshot], day: date
) -> SentimentSnapshot | None:
    """The stored Sentiment day closest to `day`, or None if there is none.

    Closest rather than same-day: Poll Calibration is periodic and its
    fieldwork usually closed before the daily pipeline was ever running, so
    insisting on an exact date would mean never comparing the two at all. How
    far away it is gets said wherever the comparison is shown.
    """
    if not snapshots:
        return None
    return min(snapshots, key=lambda s: abs((s.computed_at - day).days))


def calibration_comparison(
    report: PollCalibration, snapshot: SentimentSnapshot | None
) -> pd.DataFrame:
    """Poll net approval against News Sentiment, per Coalition.

    Coalitions the poll did not rate are left out rather than shown blank: the
    row would say nothing about the poll, which is what this table is for.
    """
    derived = coalition_net_approval(report.leader_ratings)
    sentiment = snapshot.sentiment.scores if snapshot else {}
    rows = []
    for coalition, score in sorted(derived.scores.items(), key=lambda kv: -kv[1]):
        news = sentiment.get(coalition)
        rows.append(
            {
                "Coalition": coalition,
                "Poll Calibration": score,
                "Leaders rated": derived.leader_counts[coalition],
                "News Sentiment": news,
                # None rather than a difference against a missing number: a
                # Coalition no Article named that day has no Sentiment, and
                # subtracting from nothing would print a value that looks
                # measured.
                "Difference": None if news is None else score - news,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Coalition",
            "Poll Calibration",
            "Leaders rated",
            "News Sentiment",
            "Difference",
        ],
    )


def render_headline(
    projection: Projection, total_seats: int, config: SwingModelConfig
) -> None:
    """The majority call and the seat count behind it, derived together.

    The call is recomputed from the stored Seat totals rather than read from
    `projection.government_majority`, so that the headline and the number
    under it can never disagree. They could otherwise: the stored boolean was
    decided against whatever Government Coalition membership `data/` held when
    the pipeline ran, and that membership is deliberately editable (issue #1,
    story 20 — DAP's congress is the live example). Edit it, and until the
    next run a stored `True` would sit above a seat count well short of the
    threshold. Where the two do diverge the page says so rather than quietly
    picking one.
    """
    seats = government_seat_total(projection.coalition_seat_totals, config)
    threshold = config.majority_threshold
    retains = seats >= threshold

    if retains:
        st.success(
            f"### Government Coalition retains its Majority\n"
            f"Projected **{seats} of {total_seats}** Seats — "
            f"{threshold} needed, a margin of {seats - threshold}."
        )
    else:
        st.error(
            f"### Government Coalition loses its Majority\n"
            f"Projected **{seats} of {total_seats}** Seats — "
            f"{threshold} needed, short by {threshold - seats}."
        )

    if retains != projection.government_majority:
        st.warning(
            "Government Coalition membership has changed since this "
            "Projection was computed. The Seat totals are as the Swing Model "
            "left them; the Majority call above re-counts them under the "
            "current membership. The next pipeline run reconciles the two."
        )


def election_status_statement(status: ElectionStatus, today: date) -> str:
    """Whether GE16 has been called, in one sentence, as of `today`.

    Four states, because the reader's question is different in each: an
    election nobody has called yet, one called with no polling day announced,
    one with a day to count towards, and one already polled. The last matters
    even though this is a forecasting tool — the moment polling passes, the
    page stops being a forecast, and a stale data file must not have it
    counting down to a date in the past.

    `today` is passed in rather than read here so the phrasing has one input
    and can be reasoned about; the Dashboard has no automated tests (issue #1)
    and this is the branchiest thing on the page.
    """
    # The Dewan Rakyat rather than Parliament throughout: dissolution applies
    # to the elected chamber, and the Dewan Negara is not dissolved with it.
    # CONTEXT.md defines the Seats being projected as that chamber's.
    if status.dissolved_on is None:  # i.e. not status.called, and the state
        return (  # a fresh deployment is in until GE16 is finally called.
            "**GE16 has not been called.** The Dewan Rakyat is sitting, and "
            "the election must be held by "
            f"**{status.constitutional_deadline:%-d %B %Y}** at the latest."
        )

    # Every branch below has a dissolution to name, which is what makes this
    # one date safe to format once up here.
    dissolved = f"{status.dissolved_on:%-d %B %Y}"

    if status.polling_date is not None:
        days = (status.polling_date - today).days
        polls = f"{status.polling_date:%-d %B %Y}"
        if days > 0:
            return (
                f"**GE16 has been called.** Polling is on **{polls}**, "
                f"{days} day{'s' if days != 1 else ''} away. The Dewan Rakyat "
                f"was dissolved on {dissolved}."
            )
        if days == 0:
            return (
                f"**GE16 is being held today, {polls}.** The Dewan Rakyat was "
                f"dissolved on {dissolved}."
            )
        return (
            f"**GE16 was held on {polls}.** This page projects an election "
            "that has already happened; it is no longer a forecast."
        )
    return (
        f"**GE16 has been called.** The Dewan Rakyat was dissolved on "
        f"**{dissolved}**. The Election Commission has not yet announced "
        "a polling date."
    )


def render_election_status(status: ElectionStatus, today: date) -> None:
    """The temporal context for the Projection, directly under the headline.

    Placed here rather than in the footer because it changes what the numbers
    above mean: a Projection for an election with a date is a forecast of a
    known event, and one for an election nobody has called is a reading of the
    present (issue #1, story 8).
    """
    st.markdown(election_status_statement(status, today))


def render_summary(
    projection: Projection,
    baseline_totals: Mapping[Coalition, int],
    snapshot: SentimentSnapshot,
    total_seats: int,
    config: SwingModelConfig,
) -> None:
    projected = government_seat_total(projection.coalition_seat_totals, config)
    at_ge15 = government_seat_total(baseline_totals, config)
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
        help=f"More than half of the {total_seats} Seats in the Dewan Rakyat.",
    )
    right.metric(
        "Articles read",
        snapshot.sentiment.total_articles,
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


def render_trend(
    snapshots: Sequence[SentimentSnapshot],
    calibrations: Sequence[PollCalibration],
) -> None:
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

    # Drawn with Altair rather than `st.line_chart` so the Poll Calibration
    # points can sit on the same axes as the line. Both layers carry a column
    # named `Score`, which is what holds the two to one shared y scale.
    line_data = trend.rename(columns={"Sentiment": "Score"})
    plotted = calibrations_within(calibrations, snapshots)
    points = calibration_points(plotted)

    axes = (
        alt.X("Day:T", title=None),
        alt.Color("Coalition:N", title="Coalition"),
    )
    chart = alt.Chart(line_data).mark_line().encode(
        *axes, alt.Y("Score:Q", title="Sentiment (−1 to +1)")
    )
    if not points.empty:
        chart += (
            alt.Chart(points)
            .mark_point(shape="diamond", size=160, filled=True, opacity=1.0)
            .encode(
                *axes,
                alt.Y("Score:Q"),
                tooltip=[
                    "Publisher",
                    "Report",
                    "Coalition",
                    alt.Tooltip("Score:Q", title="Net approval", format="+.2f"),
                    "Leaders rated",
                    "Sample",
                ],
            )
        )
    st.altair_chart(chart, use_container_width=True)

    caption = (
        f"{len(snapshots)} days of history. Sentiment runs from −1 (wholly "
        "negative coverage) to +1 (wholly positive), averaged over the "
        "Articles that named each Coalition that day."
    )
    if not points.empty:
        caption += (
            " Diamonds are Poll Calibration — a published survey's net "
            "approval, plotted at the last day of its fieldwork. It measures "
            "something different from news tone; see below."
        )
    elif calibrations:
        caption += (
            " No Poll Calibration point falls inside this window, so none is "
            "drawn; the latest report is compared below instead."
        )
    st.caption(caption)


def render_calibration(
    calibrations: Sequence[PollCalibration],
    snapshots: Sequence[SentimentSnapshot],
) -> None:
    """The latest published survey, set against the News Sentiment near it.

    Comparison, never correction. Poll Calibration exists to sanity-check News
    Sentiment (CONTEXT.md), and the two are different measurements: one is the
    tone of coverage naming a Coalition, the other is how many people told a
    pollster they approve of that Coalition's leaders. They share a −1..+1
    scale and nothing else, so the page shows both numbers and their gap and
    stops there — it does not blend them, and a wide gap is a prompt to look,
    not a verdict on either.
    """
    st.subheader("Poll Calibration")

    if not calibrations:
        st.info(
            "No Poll Calibration in Storage. Transcribe a published Merdeka "
            "Center report into `data/poll_calibration.json` and run "
            "`python -m lpa.poll_calibration` — see `docs/poll-calibration.md`."
        )
        return

    # Storage orders by fieldwork end, so this is the most recently *fielded*
    # report, not the most recently published one. Deliberate: fieldwork end
    # is the date a poll is plotted at and the date the nearest Sentiment day
    # is measured from, so "latest" has to mean the same thing here as it does
    # on the chart. The two orderings can differ — reports are published two
    # or three months after fieldwork closes, and not always in order.
    report = calibrations[-1]
    error = (
        f", margin of error ±{report.margin_of_error}%"
        if report.margin_of_error is not None
        else ""
    )
    st.caption(
        f"[{report.title}]({report.report_url}) — {report.publisher}. "
        f"Fielded {report.fieldwork_start:%-d %B} to "
        f"{report.fieldwork_end:%-d %B %Y}, {report.sample_size:,} "
        f"respondents{error}. Published "
        f"{report.published_on:%-d %B %Y}."
    )

    snapshot = nearest_snapshot(snapshots, report.fieldwork_end)
    if snapshot is None:
        st.warning(
            "No stored Sentiment to compare this against yet. Run "
            "`python -m lpa.pipeline`."
        )
    else:
        gap = abs((snapshot.computed_at - report.fieldwork_end).days)
        # Said plainly rather than hidden in a column header: the daily
        # pipeline and a quarterly survey rarely land on the same day, and how
        # far apart they are decides how much the comparison is worth.
        if gap == 0:
            st.caption(
                "Compared against the News Sentiment of the same day, "
                f"{snapshot.computed_at:%-d %B %Y}."
            )
        else:
            st.caption(
                f"The nearest stored News Sentiment is "
                f"{snapshot.computed_at:%-d %B %Y}, **{gap} days** from the "
                "close of fieldwork. The further apart they are, the less the "
                "comparison says."
            )

    st.dataframe(
        calibration_comparison(report, snapshot),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Poll Calibration": st.column_config.NumberColumn(
                format="%+.2f",
                help="Mean of (satisfied − dissatisfied) across the "
                "Coalition's leaders the report rated, as a fraction.",
            ),
            "News Sentiment": st.column_config.NumberColumn(
                format="%+.2f",
                help="The model's mean tone of Articles naming the Coalition "
                "on the day above. Blank if none named it.",
            ),
            "Difference": st.column_config.NumberColumn(
                format="%+.2f",
                help="Poll Calibration minus News Sentiment. Positive means "
                "the survey is warmer than the coverage.",
            ),
            "Leaders rated": st.column_config.NumberColumn(
                help="How many of the Coalition's leaders the report rated. "
                "A score from one leader is a thinner signal than one from "
                "three."
            ),
        },
    )

    unattributed = coalition_net_approval(report.leader_ratings).unattributed
    if unattributed:
        st.markdown(
            "**Rated but not attributed to a Coalition.** A leader counts "
            "towards the Coalition their party sat in while the survey was in "
            "the field; where that was none, the rating is reported and left "
            "out of the scores above rather than guessed at (ADR 0004)."
        )
        st.markdown(
            "\n".join(
                f"- {rating.leader} — {rating.satisfied:g}% satisfied, "
                f"{rating.dissatisfied:g}% dissatisfied."
                + (f" {rating.note}" if rating.note else "")
                for rating in unattributed
            )
        )


def freshness(updated: date, today: date) -> str:
    """How stale the last run is, in words.

    Snapshots are dated to the day and carry no clock time, so "today" is the
    most precise thing that can honestly be said of a fresh one. Days elapsed
    is what story 4 actually wants from a daily pipeline anyway: it answers
    whether a run has been missed.
    """
    days = (today - updated).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def render_sources(snapshot: SentimentSnapshot) -> None:
    st.subheader("Sources and method")
    # Dated from the Sentiment snapshot itself, not from the Projection: these
    # are the outlets that snapshot was built from, and mislabelling them with
    # another day's date would be worse than showing no date at all.
    st.caption(
        f"Last updated **{snapshot.computed_at:%-d %B %Y}** "
        f"({freshness(snapshot.computed_at, today_in_malaysia())}, "
        "by the Malaysian day)."
    )

    sources = snapshot.sentiment.sources
    counts = snapshot.sentiment.article_counts
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

    data = load_dashboard_data()
    baseline, projections, snapshots = data.baseline, data.projections, data.snapshots
    calibrations = data.calibrations

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

    # The Seats counted, taken from the Baseline rather than written as 222:
    # the Baseline is one row per Seat, and the Election Commission redraws
    # the boundaries. A future redelineation should move this number by
    # reloading the Baseline, not by editing the Dashboard.
    total_seats = len(baseline)
    st.caption(
        f"Malaysian political sentiment, tracked daily, projected onto the "
        f"{total_seats} Seats of the Dewan Rakyat. A model estimate, not an "
        "official forecast."
    )

    latest, snapshot = projections[-1], snapshots[-1]
    baseline_totals = baseline_seat_totals(baseline)
    config = swing_model_config(load_coalition_config())
    # Read outside the cached Storage pass on purpose: it is one small file,
    # and the day it changes is the day it most needs to reach the page —
    # not up to CACHE_SECONDS later.
    status = load_election_status()

    render_headline(latest, total_seats, config)
    render_election_status(status, today_in_malaysia())
    render_summary(latest, baseline_totals, snapshot, total_seats, config)
    st.divider()
    render_breakdown(baseline_totals, latest, config)
    st.divider()
    render_trend(snapshots, calibrations)
    st.divider()
    render_calibration(calibrations, snapshots)
    st.divider()
    render_sources(snapshot)


# Called at import, not under an `if __name__ == "__main__"` guard as the other
# modules here are: Streamlit executes this file as the page itself on every
# rerun, and does not give it `__main__` as its module name, so a guard would
# render an empty page. Nothing else imports this module.
main()
