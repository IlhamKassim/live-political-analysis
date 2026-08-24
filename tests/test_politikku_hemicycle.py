"""The PolitikKu hemicycle: 222 dots, exactly, in the right bands.

Per #73's own model/effort note — "verify the seat counts and angle math
actually produce 222 dots in the right bands before calling it done" — this
file is mostly arithmetic checks, plus the same escaping/XSS discipline as
`test_public_page.py` and `test_politikku_shell.py`.
"""

import math
import re

from pytest import raises

from lpa.politikku_hemicycle import (
    MAJORITY_THRESHOLD,
    TOTAL_SEATS,
    HemicycleCounts,
    Palette,
    _row_counts,
    _slots,
    render_hemicycle,
)

EVEN_SPLIT = HemicycleCounts(government_clear=92, noise=72, nongovernment_clear=58)


def test_the_row_counts_sum_to_222_and_every_row_has_at_least_one_seat():
    counts = _row_counts()
    assert len(counts) == 7
    assert sum(counts) == TOTAL_SEATS
    assert all(c >= 1 for c in counts)
    # The outer row (last, largest radius) absorbs the rounding remainder,
    # per the handoff's rule — it should be at least as large as an even
    # split would give it, not smaller.
    assert counts[-1] >= TOTAL_SEATS // 7


def test_the_slots_run_left_to_right_and_number_222():
    slots = _slots()
    assert len(slots) == TOTAL_SEATS
    angles = [angle for angle, _radius in slots]
    assert angles == sorted(angles, reverse=True)
    assert angles[0] == math.pi
    assert angles[-1] == 0.0


def test_a_split_that_does_not_sum_to_222_is_refused():
    with raises(ValueError, match="222"):
        HemicycleCounts(government_clear=92, noise=72, nongovernment_clear=57)


def test_the_dots_are_filled_in_three_contiguous_bands_left_to_right():
    svg = render_hemicycle(EVEN_SPLIT, show_threshold=False)
    fills = re.findall(r'fill="(#[0-9a-f]{6})"', svg)
    assert len(fills) == TOTAL_SEATS
    assert fills[:92] == ["#14203a"] * 92
    assert fills[92:164] == ["#d6d1c6"] * 72
    assert fills[164:] == ["#93a0ac"] * 58


def test_the_dark_band_palette_recolours_without_changing_the_split():
    svg = render_hemicycle(EVEN_SPLIT, palette=Palette.DARK_BAND, show_threshold=False)
    fills = re.findall(r'fill="(#[0-9a-f]{6})"', svg)
    assert fills[:92] == ["#fbfaf7"] * 92
    assert fills[92:164] == ["#3d4a63"] * 72
    assert fills[164:] == ["#8792a6"] * 58


def test_the_threshold_line_and_label_are_present_only_when_asked_for():
    with_threshold = render_hemicycle(EVEN_SPLIT)
    assert "MAJORITY 112" in with_threshold
    assert "stroke-dasharray" in with_threshold

    without_threshold = render_hemicycle(EVEN_SPLIT, show_threshold=False)
    assert "MAJORITY 112" not in without_threshold
    assert "stroke-dasharray" not in without_threshold


def test_the_majority_label_is_a_parameter_not_a_constant_and_gets_escaped():
    svg = render_hemicycle(EVEN_SPLIT, majority_label="MAJORITI 112")
    assert "MAJORITI 112" in svg
    assert "MAJORITY 112" not in svg

    hostile = render_hemicycle(EVEN_SPLIT, majority_label="</svg><script>alert(1)</script>")
    assert "<script>" not in hostile
    assert "&lt;script&gt;" in hostile


def test_the_aria_label_states_the_real_split_and_the_majority_threshold():
    lopsided = HemicycleCounts(government_clear=100, noise=50, nongovernment_clear=72)
    svg = render_hemicycle(lopsided, show_threshold=False)
    assert f"{MAJORITY_THRESHOLD}-seat Majority" in svg
    assert "100 clear for the Government Coalition" in svg
    assert "50 within model noise" in svg
    assert "72 clear for Non-government" in svg


def test_no_animation_or_script_is_ever_emitted():
    svg = render_hemicycle(EVEN_SPLIT)
    assert "<script" not in svg
    assert "animat" not in svg.lower()
