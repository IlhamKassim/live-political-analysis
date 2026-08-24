"""What a Seat Call card says, tested away from how it looks.

`card_model` does every piece of arithmetic a card claims, so this file is
about numbers and prose. The SVG is covered only where a rendering bug would
put a wrong claim on a card — an unescaped Seat name, a SAMPLE stamp, or a
"prediction"/"forecast" slipping past the ADR 0003/0005 framing.
"""

from pytest import approx

from lpa.domain import SeatBaseline, SeatCall
from lpa.public_page import Tier, tier_for
from lpa.seat_call_card import (
    CardModel,
    _coalition_ink,
    card_model,
    render_card,
)

PH = "PH"
BN = "BN"
PN = "PN"
GPS = "GPS"
GRS = "GRS"

NAMES = {PH: "Pakatan Harapan", BN: "Barisan Nasional", PN: "Perikatan Nasional"}


def seat(code: str, name: str, state: str, **votes: float) -> SeatBaseline:
    return SeatBaseline(code=code, name=name, state=state, vote_share=votes)


def call(code: str, coalition: str, margin: float) -> SeatCall:
    return SeatCall(code=code, coalition=coalition, margin=margin)


def holding_model(*, margin: float = 0.034) -> CardModel:
    """A GE15 PH seat the call holds — the settled Sample B case."""
    s = seat("P.100", "Bandar", "Selangor", PH=0.53, PN=0.47)
    return card_model(call("P.100", PH, margin), s, NAMES)


def flip_model(*, margin: float = 0.05) -> CardModel:
    """A GE15 PH seat (PH the GE15 incumbent) the call flips to PN."""
    s = seat("P.101", "Luar", "Selangor", PH=0.56, PN=0.44)
    return card_model(call("P.101", PN, margin), s, NAMES)


def test_a_call_inside_six_points_is_too_close_and_outside_is_not():
    assert tier_for(0.034) == Tier.TIGHT
    assert tier_for(0.06) == Tier.LIKELY
    assert holding_model(margin=0.034).tier == Tier.TIGHT
    assert holding_model(margin=0.09).tier == Tier.LIKELY
    assert holding_model(margin=0.15).tier == Tier.SAFE


def test_the_margin_is_formatted_as_percentage_points():
    assert holding_model().margin_points == "3.4"
    m = holding_model(margin=0.076)
    assert m.margin_points == "7.6"


def test_a_held_seat_draws_winner_vs_runner_up():
    m = holding_model()
    assert m.incumbent == PH
    assert m.coalition == PH
    # The bar's left is the incumbent, the contest's opponent is the runner-up.
    assert m.left_ink == _coalition_ink(PH)
    assert m.right_ink == _coalition_ink(PN)
    assert m.incumbent_share == approx(0.53)
    assert m.opponent == PN
    assert m.opponent_share == approx(0.47)
    # The dot sits at the winner's (incumbent's) leading edge, no gap left.
    assert m.dot_x == approx(m.left_w)
    assert m.gap_w > 0


def test_a_flipped_seat_draws_incumbent_vs_projected_winner():
    m = flip_model()
    assert m.incumbent == PH
    assert m.coalition == PN
    assert m.incumbent_share == approx(0.56)
    assert m.opponent == PN
    assert m.opponent_share == approx(0.44)
    # The winner is the flipper, so its ink is on the right and the dot is
    # beyond the gap.
    assert m.right_ink == _coalition_ink(PN)
    assert m.winner_ink == _coalition_ink(PN)
    assert m.dot_x == approx(m.left_w + m.gap_w)


def test_the_bar_widths_are_a_common_scale_and_sum_to_the_track():
    m = holding_model()
    total = m.left_w + m.right_w + m.gap_w
    # Within rounding of the 912 track.
    assert total == approx(912, abs=0.5)


def test_the_note_and_caveat_carry_the_arithmetic_framing():
    m = holding_model()
    assert "with Pakatan Harapan" in m.note
    assert "ahead by 3.4 points" in m.note
    assert "arithmetic against the seat's GE15 result" in m.footnote
    assert "state" in m.footnote
    assert "Not calibrated" in m.footnote


def test_a_seat_with_a_single_ge15_coalition_does_not_crash():
    # A seat whose GE15 vote is all one coalition has no runner-up; the card
    # must still render rather than divide by nothing.
    s = seat("P.200", "Solo", "Sabah", GRS=1.0)
    m = card_model(call("P.200", GRS, 0.01), s, NAMES)
    assert m.incumbent == GRS
    assert m.opponent_share == 0.0
    assert m.gap_w > 0


def test_the_card_carries_no_sample_stamp_and_no_prediction_language():
    svg = render_card(holding_model())
    assert "SAMPLE" not in svg
    assert "prediction" not in svg.lower()
    assert "forecast" not in svg.lower()
    assert "Seat-Level Projection" in svg


def test_the_card_carries_the_not_calibrated_caveat():
    svg = render_card(holding_model())
    assert "Not calibrated" in svg


def test_the_card_says_the_real_margin_and_coalition():
    svg = render_card(holding_model())
    assert "3.4 pts" in svg
    assert "PH · TOO CLOSE" in svg
    assert "Pakatan Harapan" in svg
    assert "Bandar" in svg


def test_a_seat_name_carrying_markup_cannot_break_out_of_the_svg():
    s = seat("P.100", 'Bagan <script>alert("x")</script>', "Selangor", PH=0.5, PN=0.5)
    m = card_model(call("P.100", PH, 0.03), s, NAMES)
    svg = render_card(m)
    assert "<script>alert" not in svg
    assert "&lt;script&gt;" in svg


def test_the_card_is_a_self_contained_svg_with_an_aria_label():
    svg = render_card(holding_model())
    assert svg.strip().startswith("<svg")
    assert 'role="img"' in svg
    assert 'aria-label="' in svg
    assert "Not calibrated" in svg.split('aria-label="')[1].split('"')[0]


def test_the_wordmark_and_register_markers_survive():
    svg = render_card(holding_model())
    assert "Live Political Analysis" in svg
    assert "reading this site" in svg
    assert "one entry in the Seat-Level Projection" in svg
