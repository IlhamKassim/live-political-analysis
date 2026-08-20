"""Domain-type helpers with real logic of their own, tested in isolation."""

from datetime import date

from lpa.domain import Projection, SeatCall, changed_seat_calls

PH = "PH"
PN = "PN"


def projection(*calls: SeatCall, day: date = date(2026, 8, 6)) -> Projection:
    return Projection(
        coalition_seat_totals={},
        government_majority=True,
        computed_at=day,
        seat_calls=calls,
    )


def test_no_change_is_an_empty_diff():
    older = projection(SeatCall(code="P.001", coalition=PH, margin=0.05))
    newer = projection(SeatCall(code="P.001", coalition=PH, margin=0.04), day=date(2026, 8, 7))

    assert changed_seat_calls(older, newer) == ()


def test_a_seat_that_changed_coalition_is_the_diff():
    older_call = SeatCall(code="P.001", coalition=PH, margin=0.02)
    newer_call = SeatCall(code="P.001", coalition=PN, margin=0.01)
    older = projection(older_call)
    newer = projection(newer_call, day=date(2026, 8, 7))

    assert changed_seat_calls(older, newer) == ((older_call, newer_call),)


def test_only_the_changed_seats_are_reported_not_the_unchanged_ones():
    older = projection(
        SeatCall(code="P.001", coalition=PH, margin=0.02),
        SeatCall(code="P.002", coalition=PN, margin=0.10),
    )
    flipped = SeatCall(code="P.001", coalition=PN, margin=0.01)
    newer = projection(
        flipped,
        SeatCall(code="P.002", coalition=PN, margin=0.09),
        day=date(2026, 8, 7),
    )

    [(old, new)] = changed_seat_calls(older, newer)
    assert old.code == "P.001"
    assert new == flipped


def test_a_seat_missing_from_one_side_is_skipped_not_reported():
    older = projection(SeatCall(code="P.001", coalition=PH, margin=0.02))
    newer = projection(
        SeatCall(code="P.001", coalition=PH, margin=0.02),
        SeatCall(code="P.002", coalition=PN, margin=0.05),
        day=date(2026, 8, 7),
    )

    assert changed_seat_calls(older, newer) == ()
