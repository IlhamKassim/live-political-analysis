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
class ElectionStatus:
    """Whether GE16 has been called, and the dates that say when it lands.

    The Projection is an estimate of an election that may or may not have been
    scheduled yet, and those are very different things to be reading (issue
    #1, story 8). Nothing else in the package derives from this — it is
    context for the reader, not an input to the Swing Model.

    "Called" means the Dewan Rakyat has been dissolved, the act that starts a
    Malaysian general election. The Election Commission sets the polling day
    afterwards, so `dissolved_on` set with `polling_date` still `None` is a
    real state and not a half-filled record. Both are `None` until a
    dissolution happens.
    """

    constitutional_deadline: date
    """The last day GE16 can be held if the Dewan Rakyat is never dissolved
    early.

    A fixed consequence of GE15 rather than a projection of when the election
    will be: dissolving early is the ordinary case, and that is `dissolved_on`.
    """
    source: str
    """Where the dates were taken from, so a reader can check them."""
    dissolved_on: date | None = None
    """When the Dewan Rakyat was dissolved, which is what calling an election
    means here. `None` until it happens, and the field `called` reads."""
    polling_date: date | None = None
    """When polling is held. `None` while the Election Commission has not
    announced it — including in the interval after dissolution, which is why
    it is not derived from `dissolved_on`."""

    @property
    def called(self) -> bool:
        """Whether GE16 has been called.

        Derived from the dissolution rather than stored beside it, so a record
        cannot say it has been called and carry no date for when.
        """
        return self.dissolved_on is not None


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
class SeatCall:
    """One Seat's entry in the Seat-Level Projection (ADR 0005).

    Identified by `code` alone: `SeatBaseline` already holds the Seat's name,
    state and GE15 result, and a caller rendering a call wants those anyway.
    Copying them here would make a Seat's identity two facts that can disagree.
    """

    code: str
    """The Seat's official code, matching its `SeatBaseline`."""
    coalition: Coalition
    """The Coalition projected to take the Seat."""
    margin: float
    """The projected lead over the runner-up, in vote share.

    Taken after the Swing, from shares that have been floored at zero and
    rescaled (ADR 0005), so it is always a real share of the vote. Zero means
    a dead heat — including the case where the Swing left nothing above zero
    and the Seat was held on its Baseline. Where a Seat's Baseline names only
    one Coalition there is no runner-up to lead, and the margin is that
    Coalition's whole share.

    Small is the interesting case, and the Swing Model has no Seat-specific
    signal to resolve it with: a call inside a few points is arithmetic that
    could as easily have landed the other way, and must be presented that way.
    """


@dataclass(frozen=True)
class Projection:
    """The tool's output: GE16 seat totals per Coalition, and the majority call."""

    coalition_seat_totals: Mapping[Coalition, int]
    government_majority: bool
    computed_at: date
    seat_calls: tuple[SeatCall, ...] = ()
    """The Seat-Level Projection the totals are the tally of.

    Empty is a real state and not a missing one: Storage keeps per-Seat rows
    for the latest Projection only (ADR 0005), so every earlier day in a
    history read carries totals alone.
    """


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
    published_at: datetime | None
    """When the outlet published it, where the feed says so.

    Optional because some feeds carry no date at all — Bernama's is one, and
    it is the national news agency, too central to drop over a missing field.
    `None` means unknown and is never a guess: an invented date would be worse
    than no date, since it would be indistinguishable from a real one.
    """
    title: str
    text: str
    """The article body as plain text, ready for the Sentiment Scorer."""


@dataclass(frozen=True)
class Outlet:
    """A news outlet and the feed the Scraper reads it from."""

    name: str
    feed_url: str
