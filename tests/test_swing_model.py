from collections import Counter
from copy import deepcopy
from datetime import date

from fixtures import (
    BN,
    PH,
    PN,
    government_config,
    one_seat_with_a_small_third_coalition,
    partially_reported_signal_seats,
    three_coalition_seats,
    two_coalition_seats,
    two_state_seats,
)
from pytest import approx

from lpa.domain import StateElectionSignal
from lpa.swing_model import state_swing, swing_model


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
    # PH to PN, so the seats PH held by 6pp and 4pp fall and the rest hold:
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
    inputs = {
        "baseline": three_coalition_seats(),
        "sentiment": {},
        "state_election_signals": [],
        "computed_at": date(2026, 8, 6),
    }

    together = swing_model(
        config=government_config(government_coalitions=frozenset({PH, BN}), majority_threshold=6),
        **inputs,
    )
    after_realignment = swing_model(
        config=government_config(government_coalitions=frozenset({PH}), majority_threshold=6),
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
        config=government_config(government_coalitions=frozenset({PH, BN}), majority_threshold=6),
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

    first = swing_model(baseline, sentiment, signals, government_config(), date(2026, 8, 6))
    second = swing_model(baseline, sentiment, signals, government_config(), date(2026, 8, 6))

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


def test_a_coalition_the_state_result_omits_is_still_weighted_the_same_way():
    # The Selangor result reports only PH and PN, so BN has no observed state
    # Swing. BN's Sentiment Swing must still be halved by state_signal_weight,
    # exactly as PH's and PN's are — otherwise BN would move twice as far as
    # its rivals for a purely structural reason. Selangor's Baseline means are
    # PH 0.40 / PN 0.25, so the reported 0.32 / 0.32 is -8pp PH, +7pp PN.
    # Blended half-and-half with a -4pp / +4pp / 0 Sentiment Swing that gives
    # PH -6pp, BN +2pp, PN +3.5pp, and S002 stays PH at 39 to BN's 38.
    projection = swing_model(
        baseline=partially_reported_signal_seats(),
        sentiment={PH: -0.4, BN: 0.4, PN: 0.0},
        state_election_signals=[
            StateElectionSignal(
                state="Selangor",
                held_on=date(2026, 3, 1),
                vote_share={PH: 0.32, PN: 0.32},
            )
        ],
        config=government_config(majority_threshold=3),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 2, BN: 2, PN: 0}


def test_an_exact_tie_is_held_by_the_baseline_winner_not_decided_by_name():
    # A 2pp Swing lands P004 (52/48 at Baseline) on exactly 50/50. A dead heat
    # is not evidence the Seat changed hands, so the Baseline holder keeps it —
    # the alternative, ordering by Coalition name, would hand PN a Seat and with
    # it the Majority call, on nothing but the alphabet.
    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: -0.2, PN: 0.2},
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 4, PN: 2}
    assert projection.government_majority is True


def test_a_state_election_moves_only_that_states_seats():
    # Johor's 2026 result cannot tell you what Sarawak will do. Selangor's
    # Baseline averages PH 0.50 and Johor's PH 0.40, so a Selangor result of
    # 0.28 is -22pp there and a Johor result of 0.62 is +22pp there. Halved by
    # the weighting each applies to its own state alone: Selangor's four seats
    # all fall to PN at -11pp, while Johor's swing the other way and three of
    # its four go to PH.
    selangor = StateElectionSignal(
        state="Selangor", held_on=date(2026, 3, 1), vote_share={PH: 0.28, PN: 0.72}
    )
    johor = StateElectionSignal(
        state="Johor", held_on=date(2026, 4, 1), vote_share={PH: 0.62, PN: 0.38}
    )

    projection = swing_model(
        baseline=two_state_seats(),
        sentiment={},
        state_election_signals=[selangor, johor],
        config=government_config(majority_threshold=5),
        computed_at=date(2026, 8, 6),
    )

    assert projection.coalition_seat_totals == {PH: 3, PN: 5}


def test_a_state_with_no_election_of_its_own_is_left_to_sentiment_alone():
    # Only Selangor voted, so Johor's Seats must move on Sentiment only —
    # a 4pp swing to PN, which takes P205 (48/52 at Baseline) and no more.
    selangor = StateElectionSignal(
        state="Selangor", held_on=date(2026, 3, 1), vote_share={PH: 0.28, PN: 0.72}
    )

    projection = swing_model(
        baseline=two_state_seats(),
        sentiment={PH: -0.4, PN: 0.4},
        state_election_signals=[selangor],
        config=government_config(majority_threshold=5),
        computed_at=date(2026, 8, 6),
    )

    # Selangor: all four to PN at -11pp - 2pp = -13pp. Johor: PH loses none it
    # held (it held none) and takes nothing, so all four stay PN.
    assert projection.coalition_seat_totals == {PH: 0, PN: 8}


def test_every_seat_is_called_by_name_with_the_lead_it_is_called_on():
    # Neutral Sentiment, so each Seat's call and margin is its Baseline
    # unchanged: PH ahead by 20, 10, 6 and 4 points, PN by 10 and 30.
    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: 0.0, PN: 0.0},
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    assert [(call.code, call.coalition) for call in projection.seat_calls] == [
        ("P001", PH),
        ("P002", PH),
        ("P003", PH),
        ("P004", PH),
        ("P005", PN),
        ("P006", PN),
    ]
    assert [call.margin for call in projection.seat_calls] == approx(
        [0.20, 0.10, 0.06, 0.04, 0.10, 0.30]
    )


def test_a_margin_is_measured_after_the_swing_not_at_the_baseline():
    # The 4pp swing to PN narrows PH's leads and widens PN's. P002 survives on
    # 2 points and P003 falls by 2 — the Seats the uncertainty encoding has to
    # mark, and the reason the margin is published at all.
    projection = swing_model(
        baseline=two_coalition_seats(),
        sentiment={PH: -0.4, PN: 0.4},
        state_election_signals=[],
        config=government_config(),
        computed_at=date(2026, 8, 6),
    )

    called = {call.code: call for call in projection.seat_calls}
    assert (called["P002"].coalition, called["P002"].margin) == (PH, approx(0.02))
    assert (called["P003"].coalition, called["P003"].margin) == (PN, approx(0.02))
    assert called["P006"].margin == approx(0.38)


def test_the_seat_calls_are_what_the_coalition_totals_count():
    # The totals must be the tally of the published calls and not a second,
    # separately-derived answer — a page showing both would otherwise be able
    # to contradict itself.
    projection = swing_model(
        baseline=three_coalition_seats(),
        sentiment={PH: -0.6, PN: 0.6},
        state_election_signals=[],
        config=government_config(government_coalitions=frozenset({PH, BN}), majority_threshold=6),
        computed_at=date(2026, 8, 6),
    )

    tallied = Counter(call.coalition for call in projection.seat_calls)
    assert tallied == Counter({c: n for c, n in projection.coalition_seat_totals.items() if n})
    assert len(projection.seat_calls) == 10


def test_a_share_swung_below_zero_is_floored_before_the_margin_is_taken():
    # A 30pp swing puts PH on -5pp, which is not a share of anything. Floored
    # at zero the three come to 1.05, so they rescale to the 1.00 they started
    # at: PN 17/21, BN 4/21, and a lead of 13/21 rather than the 0.65 the raw
    # arithmetic would have printed.
    projection = swing_model(
        baseline=one_seat_with_a_small_third_coalition(),
        sentiment={PH: -1.0, PN: 1.0},
        state_election_signals=[],
        config=government_config(majority_threshold=1, sentiment_sensitivity=0.30),
        computed_at=date(2026, 8, 6),
    )

    (call,) = projection.seat_calls
    assert call.coalition == PN
    assert call.margin == approx(13 / 21)


def test_a_seat_swung_below_zero_on_every_side_is_held_by_its_baseline_winner():
    # A 60pp swing against all three leaves no share above zero and so no
    # evidence about who leads. Reading the least-negative number as a winner
    # would be reading rounding noise; the Seat holds, on nothing changing.
    projection = swing_model(
        baseline=one_seat_with_a_small_third_coalition(),
        sentiment={PH: -1.0, PN: -1.0, BN: -1.0},
        state_election_signals=[],
        config=government_config(majority_threshold=1, sentiment_sensitivity=0.60),
        computed_at=date(2026, 8, 6),
    )

    (call,) = projection.seat_calls
    assert call.coalition == PN
    assert call.margin == 0.0


def test_the_baseline_winner_holds_even_when_a_rival_is_the_least_negative():
    # The one case where flooring changes a call and not just a margin, pinned
    # deliberately (ADR 0005). PN 55 / PH 25 / BN 20 swung by -100 / -30 / -30
    # points leaves PN on -45 and PH on -5, so the old unfloored arithmetic
    # would have handed the Seat to PH — third place at Baseline, and ahead
    # here only by being least far outside the vote. All three are floored to
    # nothing, and PN holds.
    projection = swing_model(
        baseline=one_seat_with_a_small_third_coalition(),
        sentiment={PN: -1.0, PH: -0.3, BN: -0.3},
        state_election_signals=[],
        config=government_config(majority_threshold=1, sentiment_sensitivity=1.0),
        computed_at=date(2026, 8, 6),
    )

    (call,) = projection.seat_calls
    assert (call.coalition, call.margin) == (PN, 0.0)
    assert projection.coalition_seat_totals == {PN: 1, PH: 0, BN: 0}


def test_state_swing_is_the_same_figure_swing_model_calls_every_seat_with():
    # #53a: state_swing is public so a per-state rollup (#53) can publish the
    # actual figure the model applied, not reconstruct one. Pinning that it
    # is exactly the value from Sentiment alone where no state has voted —
    # two_state_seats() has none — matching how every Seat there gets called.
    swings = state_swing(
        baseline=two_state_seats(),
        sentiment={PH: -0.4, PN: 0.4},
        state_election_signals=[],
        config=government_config(),
    )

    assert swings == {
        "Selangor": {PH: approx(-0.04), PN: approx(0.04)},
        "Johor": {PH: approx(-0.04), PN: approx(0.04)},
    }


def test_state_swing_blends_the_observed_result_only_for_the_state_that_voted():
    # Johor's Baseline average is PH 0.40 / PN 0.60 (two_state_seats()); a
    # state result of PH 0.30 / PN 0.70 is an observed swing of -10pp/+10pp
    # there. Blended 50/50 (government_config()'s default weight) with the
    # 4pp Sentiment swing: Johor gets -7pp/+7pp. Selangor never voted, so it
    # stays on Sentiment alone, at -4pp/+4pp — the two states must disagree,
    # or this is reading the same number for both rather than a genuine
    # per-state figure.
    swings = state_swing(
        baseline=two_state_seats(),
        sentiment={PH: -0.4, PN: 0.4},
        state_election_signals=[
            StateElectionSignal(
                state="Johor", held_on=date(2026, 3, 1), vote_share={PH: 0.30, PN: 0.70}
            )
        ],
        config=government_config(),
    )

    assert swings["Selangor"] == {PH: approx(-0.04), PN: approx(0.04)}
    assert swings["Johor"] == {PH: approx(-0.07), PN: approx(0.07)}
