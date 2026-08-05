"""The Swing Model: Baseline + Sentiment + State Election Signal -> Projection.

A pure function. No database access, no network calls, no model inference.

Method — uniform national swing, per ADR 0001:

1. Sentiment becomes a vote-share Swing per Coalition, scaled by a configured
   sensitivity: a Sentiment of 1.0 is worth `sentiment_sensitivity` of share.
2. Where a state has held an election, its observed Swing (that result
   measured against the Baseline shares of that same state's Seats) is blended
   with the Sentiment Swing at `state_signal_weight` — and applied to that
   state's Seats only. A Johor result is evidence about Johor; it says nothing
   about Sarawak, and projecting it nationally would let one state's contest
   swing all 222 Seats. Seats in states that have not voted move on Sentiment
   alone.
3. The resulting Swing is applied uniformly to each Seat's Baseline shares
   within its state, and each Seat is called for whichever Coalition leads.
4. Seats are tallied per Coalition; the Government Coalition holds a Majority
   if its combined total clears `majority_threshold`.

Step 3 re-calls Seats internally but only Coalition-level totals are published;
Seat-Level Projection is deferred until the model is validated (ADR 0001).

Known limitation: projected shares are not clamped or renormalised, so a large
Swing can drive a trailing Coalition below zero. That cannot affect which
Coalition leads a Seat, and so cannot affect a Projection — but it must be
addressed before any projected margin is published.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Mapping, Sequence

from lpa.domain import (
    Coalition,
    leading_coalition,
    Projection,
    SeatBaseline,
    StateElectionSignal,
    SwingModelConfig,
)


def swing_model(
    baseline: Sequence[SeatBaseline],
    sentiment: Mapping[Coalition, float],
    state_election_signals: Sequence[StateElectionSignal],
    config: SwingModelConfig,
    computed_at: date,
) -> Projection:
    """Project GE16 Coalition seat totals from fixed Baseline data and current signals.

    `config` carries Government Coalition membership and the model's tunables;
    `computed_at` is passed in rather than read from the clock so the function
    stays pure and its output reproducible.
    """
    swing_by_state = _swing_by_state(baseline, sentiment, state_election_signals, config)
    totals: Counter[Coalition] = Counter(
        {coalition: 0 for seat in baseline for coalition in seat.vote_share}
    )
    totals.update(
        _projected_winner(seat, swing_by_state[seat.state]) for seat in baseline
    )
    government_seats = sum(
        count for c, count in totals.items() if c in config.government_coalitions
    )
    return Projection(
        coalition_seat_totals=dict(totals),
        government_majority=government_seats >= config.majority_threshold,
        computed_at=computed_at,
    )


def _swing_by_state(
    baseline: Sequence[SeatBaseline],
    sentiment: Mapping[Coalition, float],
    state_election_signals: Sequence[StateElectionSignal],
    config: SwingModelConfig,
) -> dict[str, Mapping[Coalition, float]]:
    """The Swing to apply in each state.

    Sentiment is national and reaches every state. A state election's observed
    Swing is blended in for that state alone, at `state_signal_weight`; where a
    state has not voted, Sentiment carries full weight there. Inside the states
    that did vote the weighting applies to every Coalition alike — one the
    result omits is read as having no observed Swing, not as exempt from the
    blend.
    """
    sentiment_swing = {
        coalition: score * config.sentiment_sensitivity
        for coalition, score in sentiment.items()
    }
    observed = _observed_state_swings(baseline, state_election_signals)
    weight = config.state_signal_weight

    swings: dict[str, Mapping[Coalition, float]] = {}
    for state in {seat.state for seat in baseline}:
        state_swing = observed.get(state)
        if not state_swing:
            swings[state] = sentiment_swing
            continue
        swings[state] = {
            coalition: (1 - weight) * sentiment_swing.get(coalition, 0.0)
            + weight * state_swing.get(coalition, 0.0)
            for coalition in set(sentiment_swing) | set(state_swing)
        }
    return swings


def _observed_state_swings(
    baseline: Sequence[SeatBaseline],
    state_election_signals: Sequence[StateElectionSignal],
) -> dict[str, dict[Coalition, float]]:
    """Each state's observed Swing, measured against its own Baseline shares.

    Where a state has voted more than once since GE15 its results are averaged.
    Signals for states absent from the Baseline are ignored — there is nothing
    to measure them against.
    """
    baseline_by_state: dict[str, list[SeatBaseline]] = {}
    for seat in baseline:
        baseline_by_state.setdefault(seat.state, []).append(seat)

    collected: dict[str, dict[Coalition, list[float]]] = {}
    for signal in state_election_signals:
        state_seats = baseline_by_state.get(signal.state)
        if not state_seats:
            continue
        for coalition, share in signal.vote_share.items():
            baseline_share = sum(
                seat.vote_share.get(coalition, 0.0) for seat in state_seats
            ) / len(state_seats)
            collected.setdefault(signal.state, {}).setdefault(coalition, []).append(
                share - baseline_share
            )

    return {
        state: {c: sum(values) / len(values) for c, values in by_coalition.items()}
        for state, by_coalition in collected.items()
    }


def _projected_winner(
    seat: SeatBaseline, swing: Mapping[Coalition, float]
) -> Coalition:
    """Apply the national Swing uniformly to one Seat and call the winner."""
    projected = {
        coalition: share + swing.get(coalition, 0.0)
        for coalition, share in seat.vote_share.items()
    }
    return leading_coalition(projected, tie_break=seat.winner)
