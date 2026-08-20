"""Return Trigger detection (#40): pure functions, tested away from Storage."""

from datetime import date

from fixtures import BN, GPS, PH, PN, government_config

from lpa.domain import ElectionStatus, Projection, SeatCall
from lpa.return_trigger import (
    ElectionStatusTrigger,
    ElectionStatusTriggerKind,
    MajorityTrigger,
    PreviousWatch,
    StateSignalTrigger,
    detect_triggers,
    election_status_trigger,
    majority_trigger,
    state_signal_trigger,
)

DEADLINE = date(2028, 2, 17)


def status(**overrides) -> ElectionStatus:
    defaults = {"constitutional_deadline": DEADLINE, "source": "x"}
    defaults.update(overrides)
    return ElectionStatus(**defaults)


def watch(**overrides) -> PreviousWatch:
    defaults = {"election_called": False, "polling_date": None, "signal_states": frozenset()}
    defaults.update(overrides)
    return PreviousWatch(**defaults)


def projection(
    *calls: SeatCall,
    seats: dict[str, int] | None = None,
    majority: bool = True,
    day: date = date(2026, 8, 6),
) -> Projection:
    return Projection(
        coalition_seat_totals=seats or {},
        government_majority=majority,
        computed_at=day,
        seat_calls=calls,
    )


# ── election_status_trigger ─────────────────────────────────────────────


def test_no_previous_status_fires_nothing():
    # The first run this trigger has ever been checked from — nothing to
    # compare against, not an already-called election read as newly called.
    called = status(dissolved_on=date(2026, 8, 1))
    assert election_status_trigger(None, called) is None


def test_a_fresh_dissolution_fires_the_called_trigger():
    not_called = watch(election_called=False)
    called = status(dissolved_on=date(2026, 8, 1))

    trigger = election_status_trigger(not_called, called)
    assert trigger == ElectionStatusTrigger(kind=ElectionStatusTriggerKind.CALLED, status=called)


def test_a_newly_set_polling_date_fires_its_own_trigger():
    called_no_date = watch(election_called=True, polling_date=None)
    dated = status(dissolved_on=date(2026, 8, 1), polling_date=date(2026, 9, 20))

    trigger = election_status_trigger(called_no_date, dated)
    assert trigger == ElectionStatusTrigger(
        kind=ElectionStatusTriggerKind.POLLING_DATE_SET, status=dated
    )


def test_no_change_in_status_fires_nothing():
    called = status(dissolved_on=date(2026, 8, 1))
    assert election_status_trigger(watch(election_called=True), called) is None
    assert election_status_trigger(watch(), status()) is None


# ── state_signal_trigger ────────────────────────────────────────────────


def test_a_newly_arrived_state_fires_the_trigger():
    trigger = state_signal_trigger(frozenset(), frozenset({"Johor"}))
    assert trigger == StateSignalTrigger(states=("Johor",))


def test_an_already_counted_state_does_not_refire():
    assert state_signal_trigger(frozenset({"Johor"}), frozenset({"Johor"})) is None


def test_only_the_newly_arrived_states_are_reported():
    trigger = state_signal_trigger(frozenset({"Johor"}), frozenset({"Johor", "Selangor"}))
    assert trigger == StateSignalTrigger(states=("Selangor",))


# ── majority_trigger ─────────────────────────────────────────────────────


def test_no_seat_movement_fires_nothing():
    config = government_config()
    older = projection(seats={PH: 4, PN: 2}, majority=True)
    newer = projection(seats={PH: 4, PN: 2}, majority=True, day=date(2026, 8, 7))

    assert majority_trigger(older, newer, config) is None


def test_a_swing_below_the_threshold_fires_nothing():
    config = government_config()  # PH + GPS govern, threshold 4
    older = projection(seats={PH: 5, PN: 1}, majority=True)
    newer = projection(seats={PH: 6, PN: 0}, majority=True, day=date(2026, 8, 7))

    assert majority_trigger(older, newer, config, threshold=5) is None


def test_a_swing_at_the_threshold_fires():
    config = government_config()
    older = projection(seats={PH: 5, PN: 5}, majority=True)
    newer = projection(seats={PH: 10, PN: 0}, majority=True, day=date(2026, 8, 7))

    trigger = majority_trigger(older, newer, config, threshold=5)
    assert trigger is not None
    assert trigger.government_delta == 5
    assert trigger.majority_flipped is False


def test_a_flip_fires_regardless_of_size():
    # A one-seat swing that crosses the Majority line matters more than its
    # raw size — the flip itself is the trigger, not the threshold.
    config = government_config()
    older = projection(seats={PH: 4, PN: 2}, majority=True)
    newer = projection(seats={PH: 3, PN: 3}, majority=False, day=date(2026, 8, 7))

    trigger = majority_trigger(older, newer, config, threshold=5)
    assert trigger is not None
    assert trigger.majority_flipped is True
    assert trigger.government_delta == -1


def test_a_flip_driven_by_one_seat_carries_exactly_that_seat():
    # The one case a Seat-anchored post is honest: the Majority sat exactly
    # on the threshold, and a single Seat's own flip crossed it.
    config = government_config()
    older_call = SeatCall(code="P001", coalition=PH, margin=0.01)
    newer_call = SeatCall(code="P001", coalition=PN, margin=0.01)
    older = projection(older_call, seats={PH: 4, PN: 2}, majority=True)
    newer = projection(newer_call, seats={PH: 3, PN: 3}, majority=False, day=date(2026, 8, 7))

    trigger = majority_trigger(older, newer, config, threshold=5)
    assert trigger.changed == ((older_call, newer_call),)
    assert trigger.government_relevant_changed == ((older_call, newer_call),)


def test_government_relevant_changed_excludes_a_same_side_reshuffle():
    # Code review, 20 Aug 2026: `changed_seat_calls` reports every Coalition
    # change, including one that never crosses the Majority line — a
    # reshuffle between two Non-government Coalitions (PN to BN, here)
    # alongside the one genuine Government-crossing flip must not inflate
    # the count `government_relevant_changed` exists to keep accurate.
    config = government_config()  # Government: PH + GPS
    crossing_older = SeatCall(code="P001", coalition=PH, margin=0.01)
    crossing_newer = SeatCall(code="P001", coalition=PN, margin=0.01)
    reshuffle_older = SeatCall(code="P002", coalition=PN, margin=0.02)
    reshuffle_newer = SeatCall(code="P002", coalition=BN, margin=0.02)
    older = projection(crossing_older, reshuffle_older, seats={PH: 4, PN: 2}, majority=True)
    newer = projection(
        crossing_newer, reshuffle_newer, seats={PH: 3, PN: 3}, majority=False, day=date(2026, 8, 7)
    )

    trigger = majority_trigger(older, newer, config, threshold=5)
    assert len(trigger.changed) == 2
    assert trigger.government_relevant_changed == ((crossing_older, crossing_newer),)


def test_government_relevant_changed_excludes_a_government_side_reshuffle():
    # The mirror case: PH to GPS is still Government on both sides, so it
    # must not count as a Majority-relevant flip either. Totals carry the
    # separate genuine swing that actually clears the threshold — a
    # reshuffle within the Government side moves no Government seats on its
    # own, so it cannot be what fires this trigger.
    config = government_config()  # Government: PH + GPS
    reshuffle_older = SeatCall(code="P002", coalition=PH, margin=0.02)
    reshuffle_newer = SeatCall(code="P002", coalition=GPS, margin=0.02)
    older = projection(reshuffle_older, seats={PH: 10, PN: 0}, majority=True)
    newer = projection(
        reshuffle_newer, seats={PH: 4, GPS: 1, PN: 5}, majority=True, day=date(2026, 8, 7)
    )

    trigger = majority_trigger(older, newer, config, threshold=5)
    assert trigger is not None
    assert (reshuffle_older, reshuffle_newer) not in trigger.government_relevant_changed


def test_a_broad_swing_carries_every_seat_that_moved():
    config = government_config()
    calls = [
        (
            SeatCall(code=f"P00{i}", coalition=PH, margin=0.01),
            SeatCall(code=f"P00{i}", coalition=PN, margin=0.01),
        )
        for i in range(1, 6)
    ]
    older = projection(*[c[0] for c in calls], seats={PH: 10, PN: 0}, majority=True)
    newer = projection(
        *[c[1] for c in calls], seats={PH: 5, PN: 5}, majority=True, day=date(2026, 8, 7)
    )

    trigger = majority_trigger(older, newer, config, threshold=5)
    assert len(trigger.changed) == 5


# ── detect_triggers ──────────────────────────────────────────────────────


def test_detect_triggers_reports_every_trigger_that_fired():
    config = government_config()
    older = projection(seats={PH: 4, PN: 2}, majority=True)
    newer = projection(seats={PH: 3, PN: 3}, majority=False, day=date(2026, 8, 7))

    triggers = detect_triggers(
        previous=watch(),
        current_status=status(dissolved_on=date(2026, 8, 7)),
        current_signal_states=frozenset({"Johor"}),
        older_projection=older,
        newer_projection=newer,
        config=config,
    )

    kinds = {type(t) for t in triggers}
    assert kinds == {ElectionStatusTrigger, StateSignalTrigger, MajorityTrigger}


def test_detect_triggers_reports_nothing_on_an_ordinary_day():
    config = government_config()
    older = projection(seats={PH: 4, PN: 2}, majority=True)
    newer = projection(seats={PH: 4, PN: 2}, majority=True, day=date(2026, 8, 7))

    triggers = detect_triggers(
        previous=watch(),
        current_status=status(),
        current_signal_states=frozenset(),
        older_projection=older,
        newer_projection=newer,
        config=config,
    )

    assert triggers == ()


def test_detect_triggers_skips_the_majority_check_with_no_older_projection():
    # A fresh Storage, or the day after seat_call's two-day window shrank
    # back to one — nothing to diff the Majority against yet.
    config = government_config()
    newer = projection(seats={PH: 4, PN: 2}, majority=True)

    triggers = detect_triggers(
        previous=watch(),
        current_status=status(),
        current_signal_states=frozenset(),
        older_projection=None,
        newer_projection=newer,
        config=config,
    )

    assert triggers == ()


def test_detect_triggers_fires_nothing_on_the_very_first_run():
    # No watch row exists yet — an already-called election or an
    # already-counted state must not read as newly arrived just because
    # this is the first time anyone checked.
    config = government_config()
    older = projection(seats={PH: 4, PN: 2}, majority=True)
    newer = projection(seats={PH: 4, PN: 2}, majority=True, day=date(2026, 8, 7))

    triggers = detect_triggers(
        previous=None,
        current_status=status(dissolved_on=date(2026, 8, 1)),
        current_signal_states=frozenset({"Johor"}),
        older_projection=older,
        newer_projection=newer,
        config=config,
    )

    assert triggers == ()
