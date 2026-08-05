"""The Swing Model: Baseline + Sentiment + State Election Signal -> Projection.

A pure function. No database access, no network calls, no model inference.

Method — uniform national swing, per ADR 0001:

1. Sentiment becomes a vote-share Swing per Coalition, scaled by a configured
   sensitivity: a Sentiment of 1.0 is worth `sentiment_sensitivity` of share.
2. Where a State Election Signal exists, its observed Swing (the state result
   measured against the Baseline shares of that same state's Seats) is blended
   with the Sentiment Swing at `state_signal_weight`.
3. That single national Swing is applied uniformly to every Seat's Baseline
   shares, and each Seat is called for whichever Coalition leads afterwards.
4. Seats are tallied per Coalition; the Government Coalition holds a Majority
   if its combined total clears `majority_threshold`.

Step 3 re-calls Seats internally but only Coalition-level totals are published;
Seat-Level Projection is deferred until the model is validated (ADR 0001).
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Mapping, Sequence

from lpa.domain import (
    Coalition,
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
    swing = _national_swing(baseline, sentiment, state_election_signals, config)
    totals: Counter[Coalition] = Counter(
        {coalition: 0 for seat in baseline for coalition in seat.vote_share}
    )
    totals.update(_projected_winner(seat, swing) for seat in baseline)
    government_seats = sum(
        count for c, count in totals.items() if c in config.government_coalitions
    )
    return Projection(
        coalition_seat_totals=dict(totals),
        government_majority=government_seats >= config.majority_threshold,
        computed_at=computed_at,
    )


def _national_swing(
    baseline: Sequence[SeatBaseline],
    sentiment: Mapping[Coalition, float],
    state_election_signals: Sequence[StateElectionSignal],
    config: SwingModelConfig,
) -> dict[Coalition, float]:
    """Blend the Sentiment-implied Swing with any observed State Election Swing.

    Where no State Election Signal is available the Sentiment Swing carries
    full weight, so an empty signal list leaves the Sentiment Swing untouched.
    """
    sentiment_swing = {
        coalition: score * config.sentiment_sensitivity
        for coalition, score in sentiment.items()
    }
    if not state_election_signals:
        return sentiment_swing

    state_swing = _observed_state_swing(baseline, state_election_signals)
    weight = config.state_signal_weight
    coalitions = set(sentiment_swing) | set(state_swing)
    return {
        coalition: (1 - weight) * sentiment_swing.get(coalition, 0.0)
        + weight * state_swing[coalition]
        if coalition in state_swing
        else sentiment_swing.get(coalition, 0.0)
        for coalition in coalitions
    }


def _observed_state_swing(
    baseline: Sequence[SeatBaseline],
    state_election_signals: Sequence[StateElectionSignal],
) -> dict[Coalition, float]:
    """Mean Swing across state elections, each measured against its own state's
    Baseline shares. Signals for states absent from the Baseline are ignored."""
    swings: dict[Coalition, list[float]] = {}
    for signal in state_election_signals:
        state_seats = [seat for seat in baseline if seat.state == signal.state]
        if not state_seats:
            continue
        for coalition, share in signal.vote_share.items():
            baseline_share = sum(
                seat.vote_share.get(coalition, 0.0) for seat in state_seats
            ) / len(state_seats)
            swings.setdefault(coalition, []).append(share - baseline_share)
    return {c: sum(values) / len(values) for c, values in swings.items()}


def _projected_winner(
    seat: SeatBaseline, swing: Mapping[Coalition, float]
) -> Coalition:
    """Apply the national Swing uniformly to one Seat and call the winner."""
    projected = {
        coalition: share + swing.get(coalition, 0.0)
        for coalition, share in seat.vote_share.items()
    }
    return max(projected, key=lambda c: (projected[c], c))
