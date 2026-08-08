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
   within its state, and each Seat is called for whichever Coalition leads, by
   whatever margin.
4. Seats are tallied per Coalition; the Government Coalition holds a Majority
   if its combined total clears `majority_threshold`.

Both the per-Seat calls and the totals are published, the totals being the
tally of the calls (ADR 0005, superseding ADR 0001). The Swing is uniform
within a state, so a Seat's call is its GE15 margin measured against one
state-level figure and nothing else — see ADR 0005 for what that means for how
a call may be presented.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Mapping, Sequence

from lpa.domain import (
    Coalition,
    government_seat_total,
    leading_coalition,
    Projection,
    SeatBaseline,
    SeatCall,
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
    calls = tuple(
        _call_seat(seat, swing_by_state[seat.state]) for seat in baseline
    )
    totals: Counter[Coalition] = Counter(
        {coalition: 0 for seat in baseline for coalition in seat.vote_share}
    )
    totals.update(call.coalition for call in calls)
    return Projection(
        coalition_seat_totals=dict(totals),
        government_majority=(
            government_seat_total(totals, config) >= config.majority_threshold
        ),
        computed_at=computed_at,
        seat_calls=calls,
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


def _call_seat(seat: SeatBaseline, swing: Mapping[Coalition, float]) -> SeatCall:
    """Apply the Swing uniformly to one Seat, and call it with its margin."""
    projected = _projected_shares(seat, swing)
    coalition = leading_coalition(projected, tie_break=seat.winner)
    runner_up = max(
        (share for c, share in projected.items() if c != coalition), default=0.0
    )
    return SeatCall(
        code=seat.code,
        coalition=coalition,
        margin=projected[coalition] - runner_up,
    )


def _projected_shares(
    seat: SeatBaseline, swing: Mapping[Coalition, float]
) -> dict[Coalition, float]:
    """One Seat's Baseline shares after the Swing, kept inside the vote.

    A large Swing can carry a trailing Coalition below zero, which is not a
    share of anything. Shares are floored at zero and rescaled to the total
    they had at Baseline — that total, rather than 1.0, because a Baseline may
    exclude minor parties and independents and the projection should be
    measured on the same basis it started from.

    Neither step can change which Coalition leads: flooring only touches shares
    already behind every non-negative one, and rescaling multiplies them all by
    the same positive number. So this affects margins, and Projections made
    before margins were published still hold. The exception is a Swing that
    puts *every* share at or below zero, where the model has run out of
    anything to say and the Seat falls to `leading_coalition`'s tie-break — its
    Baseline winner, on a margin of zero.
    """
    floored = {
        coalition: max(0.0, share + swing.get(coalition, 0.0))
        for coalition, share in seat.vote_share.items()
    }
    total = sum(floored.values())
    if total == 0.0:
        return floored
    scale = sum(seat.vote_share.values()) / total
    return {coalition: share * scale for coalition, share in floored.items()}
