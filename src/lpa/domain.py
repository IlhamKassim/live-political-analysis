"""Domain types shared across the pipeline.

Vocabulary follows CONTEXT.md: Coalition, Seat, Baseline, Sentiment,
State Election Signal, Projection, Government Coalition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping

Coalition = str
"""A Coalition's canonical short name, e.g. "PH", "BN", "PN", "GPS", "GRS".

Deliberately a plain string rather than a closed enum: Coalitions are data
loaded from public datasets, and new or realigned ones must not require a
code change.
"""


@dataclass(frozen=True)
class SeatBaseline:
    """One Seat's GE15 result — the fixed starting point for a Projection."""

    code: str
    name: str
    state: str
    vote_share: Mapping[Coalition, float]
    """GE15 vote share per Coalition, as fractions of the valid vote."""

    @property
    def winner(self) -> Coalition:
        return max(self.vote_share, key=lambda c: (self.vote_share[c], c))


@dataclass(frozen=True)
class StateElectionSignal:
    """A state election held after GE15 — a leading indicator for GE16.

    Compared against the Baseline shares of the Seats in the same state to
    derive an observed Swing, so only the raw result needs to be supplied.
    """

    state: str
    held_on: date
    vote_share: Mapping[Coalition, float]


@dataclass(frozen=True)
class SwingModelConfig:
    """Tunables and Government Coalition membership, supplied as data.

    Government Coalition membership lives here rather than in the Swing Model
    so a realignment can be reflected without touching model logic.
    """

    government_coalitions: frozenset[Coalition]
    majority_threshold: int = 112
    sentiment_sensitivity: float = 0.10
    """Vote-share swing, in fractions, produced by a Sentiment score of 1.0."""
    state_signal_weight: float = 0.5
    """Weight given to the State Election Signal where one exists, 0.0-1.0.

    The remaining weight goes to the News/Poll Sentiment swing.
    """


@dataclass(frozen=True)
class Projection:
    """The tool's output: GE16 seat totals per Coalition, and the majority call."""

    coalition_seat_totals: Mapping[Coalition, int]
    government_majority: bool
    computed_at: date
