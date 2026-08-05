from copy import deepcopy
from datetime import date

from fixtures import (
    BN,
    PH,
    PN,
    government_config,
    three_coalition_seats,
    two_coalition_seats,
)
from lpa.domain import StateElectionSignal
from lpa.swing_model import swing_model


def test_neutral_sentiment_and_no_state_signal_reproduces_the_baseline():
    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: 0.0, PN: 0.0},
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 4, PN: 2}
    assert projection.government_majority is True
    assert projection.computed_at == date(2026, 8, 6)


def test_sentiment_against_the_government_flips_the_marginal_seats():
    # Sensitivity 0.10 turns a -0.4 / +0.4 Sentiment split into a 4pp swing from
    # PH to PN, so the seats PH held by 6pp and 2pp fall and the rest hold:
    # P001 56/44 PH, P002 51/49 PH, P003 49/51 PN, P004 48/52 PN, P005 and P006 PN.
    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: -0.4, PN: 0.4},
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 2, PN: 4}
    assert projection.government_majority is False


def test_a_state_election_loss_deepens_the_swing_beyond_sentiment_alone():
    # Selangor's GE15 Baseline averages PH 0.50 / PN 0.50, so a state election
    # returning PH 0.42 / PN 0.58 is an 8pp State Election Signal swing to PN.
    # Blended 50/50 with the 4pp Sentiment swing that gives a 6pp swing overall:
    # only P001 (60/40 at Baseline) survives for PH, at 54/46.
    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: -0.4, PN: 0.4},
        state_election_signals=[
            StateElectionSignal(
                state="Selangor",
                held_on=date(2026, 3, 1),
                vote_share={PH: 0.42, PN: 0.58},
            )
        ],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 1, PN: 5}
    assert projection.government_majority is False


def test_the_majority_call_follows_government_coalition_membership_config():
    # Identical inputs, two Government Coalition compositions: PH + BN holds
    # seven of these ten seats and clears the six-seat bar; PH alone holds five
    # and does not. Nothing about the seat totals themselves changes.
    inputs = dict(
        baseline=three_coalition_seats(),
        sentiment={},
        state_election_signals=[],
        computed_at=date(2026, 8, 6),
    )

    together = swing_model(
        config=government_config(
            government_coalitions=frozenset({PH, BN}), majority_threshold=6
        ),
        **inputs,
    )
    after_realignment = swing_model(
        config=government_config(
            government_coalitions=frozenset({PH}), majority_threshold=6
        ),
        **inputs,
    )

    assert together.coalition_seat_totals == {PH: 5, BN: 2, PN: 3}
    assert together.government_majority is True
    assert after_realignment.coalition_seat_totals == {PH: 5, BN: 2, PN: 3}
    assert after_realignment.government_majority is False


def test_a_coalition_absent_from_sentiment_takes_no_swing_but_can_still_gain():
    # A 6pp PH -> PN swing, with BN absent from Sentiment and so unmoved.
    # P103 (PH 40 / BN 35) tips to BN purely because PH falls past it, while
    # P104 and P105 tip to PN. Totals go from 5/2/3 at Baseline to 2/3/5.
    projection = swing_model(
        baseline=three_coalition_seats(),
        sentiment={PH: -0.6, PN: 0.6},
        state_election_signals=[],
        config=government_config(
            government_coalitions=frozenset({PH, BN}), majority_threshold=6
        ),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 2, BN: 3, PN: 5}
    assert projection.government_majority is False


def test_a_coalition_that_wins_nothing_is_reported_as_zero_not_omitted():
    # A wipeout is a number the dashboard has to render, not a missing key.
    projection = swing_model(
        baseline=three_coalition_seats(),
        sentiment={PH: -1.0, BN: -1.0, PN: 1.0},
        state_election_signals=[],
        config=government_config(
            government_coalitions=frozenset({PH, BN}),
            majority_threshold=6,
            sentiment_sensitivity=0.30,
        ),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 0, BN: 0, PN: 10}
    assert projection.government_majority is False


def test_is_repeatable_and_leaves_its_inputs_untouched():
    baseline = two_coalition_seats()
    sentiment = {PH: -0.4, PN: 0.4}
    signals = [
        StateElectionSignal(
            state="Selangor", held_on=date(2026, 3, 1), vote_share={PH: 0.42, PN: 0.58}
        )
    ]
    before = deepcopy((baseline, sentiment, signals))

    first = swing_model(
        baseline, sentiment, signals, government_config(), date(2026, 8, 6)
    )
    second = swing_model(
        baseline, sentiment, signals, government_config(), date(2026, 8, 6)
    )

    assert first == second
    assert (baseline, sentiment, signals) == before


def test_a_state_election_signal_with_no_baseline_seats_is_ignored():
    # Sarawak isn't in this Baseline, so there is nothing to measure a Swing
    # against and the result must match Sentiment acting alone.
    signals = [
        StateElectionSignal(
            state="Sarawak", held_on=date(2026, 3, 1), vote_share={PH: 0.10, PN: 0.90}
        )
    ]

    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: -0.4, PN: 0.4},
        state_election_signals=signals,
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 2, PN: 4}
