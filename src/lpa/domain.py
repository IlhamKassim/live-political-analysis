"""Domain types shared across the pipeline.

Vocabulary follows CONTEXT.md: Coalition, Seat, Baseline, Sentiment,
State Election Signal, Projection, Government Coalition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
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
    """The Seat's official code, e.g. "P.001"."""
    name: str
    state: str
    vote_share: Mapping[Coalition, float]
    """GE15 vote share per Coalition, as fractions of the valid vote."""
    margin: float = 0.0
    """The winner's GE15 lead over the runner-up, in vote share."""
    demographics: Mapping[str, float] = field(default_factory=dict)
    """Census profile of the Seat — ethnicity, age and income proportions.

    Carried for the Seat-Level Projection deferred by ADR 0001; the current
    Coalition-level Swing Model does not read it.
    """

    @property
    def winner(self) -> Coalition:
        """The Coalition that took this Seat at GE15."""
        return leading_coalition(self.vote_share)


def leading_coalition(
    vote_share: Mapping[Coalition, float],
    tie_break: Coalition | None = None,
) -> Coalition:
    """The Coalition leading a Seat, with exact ties resolved deterministically.

    `tie_break` — normally the Seat's Baseline winner — keeps a Seat that lands
    on a dead heat, since a tie is no evidence it changed hands. Ties among
    Coalitions that includes no `tie_break` fall back to name order so the
    result never depends on dict insertion order.
    """
    lead = max(vote_share.values())
    tied = sorted(c for c, share in vote_share.items() if share == lead)
    return tie_break if tie_break in tied else tied[0]


@dataclass(frozen=True)
class StateElectionSignal:
    """A state election held after GE15 — a leading indicator for GE16.

    Compared against the Baseline shares of the Seats in the same state to
    derive an observed Swing, so only the raw result needs to be supplied.
    """

    state: str
    held_on: date
    """When the election was held. Recorded for provenance; the Swing Model
    weighs every signal equally rather than by recency."""
    vote_share: Mapping[Coalition, float]
    """Result per Coalition. May omit Coalitions the result does not report."""


@dataclass(frozen=True)
class SwingModelConfig:
    """Tunables and Government Coalition membership, supplied as data.

    Government Coalition membership lives here rather than in the Swing Model
    so a realignment can be reflected without touching model logic.
    """

    government_coalitions: frozenset[Coalition]
    majority_threshold: int = 112
    sentiment_sensitivity: float = 0.10
    """Vote-share swing, in fractions, produced by a Sentiment score of 1.0.

    Provisional and uncalibrated — see ADR 0003.
    """
    state_signal_weight: float = 0.5
    """Weight given to the State Election Signal within the state that voted,
    0.0-1.0. The remaining weight goes to the News/Poll Sentiment swing.

    Provisional and uncalibrated — see ADR 0003.
    """


@dataclass(frozen=True)
class Projection:
    """The tool's output: GE16 seat totals per Coalition, and the majority call."""

    coalition_seat_totals: Mapping[Coalition, int]
    government_majority: bool
    computed_at: date


def government_seat_total(
    coalition_seat_totals: Mapping[Coalition, int], config: SwingModelConfig
) -> int:
    """Seats held between them by the Coalitions that form the government.

    Lives here rather than in either caller because both the Swing Model
    deciding the Majority and the Dashboard reporting it must count the same
    Seats — and which Coalitions those are is config that can change under
    them (issue #1, story 20).
    """
    return sum(
        seats
        for coalition, seats in coalition_seat_totals.items()
        if coalition in config.government_coalitions
    )


@dataclass(frozen=True)
class Article:
    """One piece of coverage, as the Scraper produces it."""

    source: str
    """The outlet's name, e.g. "Free Malaysia Today"."""
    url: str
    published_at: datetime
    title: str
    text: str
    """The article body as plain text, ready for the Sentiment Scorer."""


@dataclass(frozen=True)
class Outlet:
    """A news outlet and the feed the Scraper reads it from."""

    name: str
    feed_url: str
