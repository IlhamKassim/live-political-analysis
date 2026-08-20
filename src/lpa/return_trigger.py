"""Return Trigger detection (#40): decide whether today is worth a push.

CONTEXT.md defines a Return Trigger as a real event that should bring the
Audience back — never a scheduled daily habit. This module is the "did
anything Return-Trigger-worthy happen since yesterday" half of that; the
Telegram post itself is a separate concern. Every function here is pure,
given whatever the caller already read from Storage/config — Storage access
belongs to the caller, the same discipline `changed_seat_calls` (#54) already
follows and that this module reuses directly.

Three trigger types, matching the ticket's own scope — no fourth without the
same "as rare and unambiguous as these three" bar the issue's research
comment sets, not "would this be interesting to post."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from lpa.domain import (
    ElectionStatus,
    Projection,
    SeatCall,
    SwingModelConfig,
    changed_seat_calls,
    government_seat_total,
)

MAJORITY_SWING_THRESHOLD = 5
"""Seats the Government Coalition's total must move, day over day, before a
swing alone is worth a push — separate from the Majority flipping sides,
which always fires regardless of size. Provisional and undocumented against
real data, the same treatment ADR 0003's Swing Model constants get: a
plausible starting number, not a fitted one. Revisit once there is a real
run of daily Projections to check it against (see #40's own "not in scope").
"""


@dataclass(frozen=True)
class PreviousWatch:
    """What `detect_triggers` needs to know about the last run, for the two
    trigger types with no other stored history to read (#40).

    Election Status and which states have a State Election Signal both come
    from hand-maintained config files, not a daily snapshot — nothing else
    in Storage already answers "what was this yesterday," so this is what a
    caller reads back to find out. Not the full `ElectionStatus`: only
    `.called`/`.polling_date` ever change day to day, and Storage has no
    reason to keep a history of `constitutional_deadline`/`source`, which
    don't.
    """

    election_called: bool
    polling_date: date | None
    signal_states: frozenset[str]


@dataclass(frozen=True)
class ElectionStatusTrigger:
    """GE16 was called, or a polling date was set, since the last run."""

    kind: str
    """`"called"` or `"polling_date_set"` — the two sub-events #40's own
    scope folds into one trigger type ("GE16 called, or a polling date
    set")."""
    status: ElectionStatus


@dataclass(frozen=True)
class StateSignalTrigger:
    """One or more states gained a State Election Signal since the last run."""

    states: tuple[str, ...]
    """Newly-appeared states only, alphabetical — never a state that was
    already in play, which would make this a standing "state coverage"
    feed rather than a one-time arrival notice."""


@dataclass(frozen=True)
class MajorityTrigger:
    """The Majority margin moved past the threshold, or flipped sides."""

    older: Projection
    newer: Projection
    changed: tuple[tuple[SeatCall, SeatCall], ...]
    """Seats whose call differs between the two Projections (`changed_seat_calls`).
    Exactly one entry is the one case a Seat-anchored post is honest: the
    Majority can only flip on a single Seat's own flip when the Government
    Coalition sat exactly on the threshold, and a broader swing (the usual
    way `MAJORITY_SWING_THRESHOLD` is cleared) always moves more than one."""
    government_delta: int
    """The Government Coalition's seat-total change, signed."""
    majority_flipped: bool


def election_status_trigger(
    previous: PreviousWatch | None, current: ElectionStatus
) -> ElectionStatusTrigger | None:
    """Whether `current` says something `previous` did not.

    `previous` is `None` on the very first run this trigger has ever been
    checked from — nothing to compare against, so nothing fires, rather than
    treating an already-called election as newly called the first time
    Storage happens to have a row for it.
    """
    if previous is None:
        return None
    if current.called and not previous.election_called:
        return ElectionStatusTrigger(kind="called", status=current)
    if current.polling_date is not None and previous.polling_date is None:
        return ElectionStatusTrigger(kind="polling_date_set", status=current)
    return None


def state_signal_trigger(
    previous_states: frozenset[str], current_states: frozenset[str]
) -> StateSignalTrigger | None:
    """Which states are in `current_states` but were not in `previous_states`.

    Only the arrival is a trigger — a state already counted stays silent on
    every later run, which is what keeps this a one-time notice rather than
    a standing "which states have voted" feed (the habit loop CONTEXT.md's
    Return Trigger definition exists to rule out).
    """
    new_states = tuple(sorted(current_states - previous_states))
    if not new_states:
        return None
    return StateSignalTrigger(states=new_states)


def majority_trigger(
    older: Projection,
    newer: Projection,
    config: SwingModelConfig,
    threshold: int = MAJORITY_SWING_THRESHOLD,
) -> MajorityTrigger | None:
    """Whether the Majority margin moved past `threshold`, or flipped sides.

    `older`/`newer` are two Projections the caller already read (the latest
    two Storage keeps, ADR 0005 extended by #54) — this function reaches
    into neither Storage nor the Swing Model itself.
    """
    older_seats = government_seat_total(older.coalition_seat_totals, config)
    newer_seats = government_seat_total(newer.coalition_seat_totals, config)
    delta = newer_seats - older_seats
    flipped = older.government_majority != newer.government_majority
    if not flipped and abs(delta) < threshold:
        return None
    return MajorityTrigger(
        older=older,
        newer=newer,
        changed=changed_seat_calls(older, newer),
        government_delta=delta,
        majority_flipped=flipped,
    )


Trigger = ElectionStatusTrigger | StateSignalTrigger | MajorityTrigger


def detect_triggers(
    *,
    previous: PreviousWatch | None,
    current_status: ElectionStatus,
    current_signal_states: frozenset[str],
    older_projection: Projection | None,
    newer_projection: Projection,
    config: SwingModelConfig,
) -> tuple[Trigger, ...]:
    """Every trigger that fired since the last run, in a fixed order.

    More than one can fire the same day (GE16 could be called on the same
    run a state result lands, however unlikely) — the caller decides how
    many posts that is, this function only reports what happened.
    `previous` is `None` on the very first run this has ever been checked
    from, which silently skips the Election Status and State Signal
    triggers (see `election_status_trigger`/`state_signal_trigger`).
    `older_projection` is `None` on a Storage with only one Projection so
    far (a fresh database, or the day after `seat_call`'s window shrank
    back to one day) — the Majority trigger has nothing to diff against
    yet, so it is silently skipped rather than raising.
    """
    triggers: list[Trigger] = []
    status_trigger = election_status_trigger(previous, current_status)
    if status_trigger is not None:
        triggers.append(status_trigger)
    if previous is not None:
        signal_trigger = state_signal_trigger(previous.signal_states, current_signal_states)
        if signal_trigger is not None:
            triggers.append(signal_trigger)
    if older_projection is not None:
        gov_trigger = majority_trigger(older_projection, newer_projection, config)
        if gov_trigger is not None:
            triggers.append(gov_trigger)
    return tuple(triggers)
