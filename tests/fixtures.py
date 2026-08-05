"""Synthetic fixtures for Swing Model tests.

Deliberately small and hand-checkable: every expected Projection in the test
suite is worked out by hand from these numbers, never recomputed by calling
the model's own arithmetic.
"""

from lpa.domain import SeatBaseline, SwingModelConfig

PH = "PH"
BN = "BN"
PN = "PN"
GPS = "GPS"


def seat(code: str, state: str, **vote_share: float) -> SeatBaseline:
    return SeatBaseline(code=code, name=code, state=state, vote_share=vote_share)


def two_coalition_seats() -> list[SeatBaseline]:
    """Six Selangor seats: PH wins four, PN wins two.

    Margins are staggered so a known swing flips a known number of seats:
    PH leads by 20pp, 10pp, 6pp and 4pp in its four; PN leads by 10pp and 30pp.
    Shares are chosen so the state-wide mean is exactly PH 0.50 / PN 0.50,
    which keeps State Election Signal swings hand-checkable.
    """
    return [
        seat("P001", "Selangor", PH=0.60, PN=0.40),
        seat("P002", "Selangor", PH=0.55, PN=0.45),
        seat("P003", "Selangor", PH=0.53, PN=0.47),
        seat("P004", "Selangor", PH=0.52, PN=0.48),
        seat("P005", "Selangor", PH=0.45, PN=0.55),
        seat("P006", "Selangor", PH=0.35, PN=0.65),
    ]


def partially_reported_signal_seats() -> list[SeatBaseline]:
    """Four Selangor seats whose state-wide means are PH 0.40 / BN 0.35 / PN 0.25.

    S002's 9pp PH-over-BN margin sits inside the gap between a correctly and an
    incorrectly weighted blend, so it flips only if BN escapes the weighting.
    """
    return [
        seat("S001", "Selangor", PH=0.50, BN=0.30, PN=0.20),
        seat("S002", "Selangor", PH=0.45, BN=0.36, PN=0.19),
        seat("S003", "Selangor", PH=0.29, BN=0.40, PN=0.31),
        seat("S004", "Selangor", PH=0.36, BN=0.38, PN=0.26),
    ]


def two_state_seats() -> list[SeatBaseline]:
    """Eight seats over two states, for signals from more than one state election.

    Selangor's four average PH 0.50 / PN 0.50 and split PH 2 / PN 2; Johor's four
    average PH 0.40 / PN 0.60 and all go PN. Baseline totals: PH 2, PN 6.
    """
    return [
        seat("P201", "Selangor", PH=0.60, PN=0.40),
        seat("P202", "Selangor", PH=0.56, PN=0.44),
        seat("P203", "Selangor", PH=0.44, PN=0.56),
        seat("P204", "Selangor", PH=0.40, PN=0.60),
        seat("P205", "Johor", PH=0.48, PN=0.52),
        seat("P206", "Johor", PH=0.44, PN=0.56),
        seat("P207", "Johor", PH=0.40, PN=0.60),
        seat("P208", "Johor", PH=0.28, PN=0.72),
    ]


def three_coalition_seats() -> list[SeatBaseline]:
    """Ten seats across two states: PH wins five, BN two, PN three.

    Enough to tell a Government Coalition of PH + BN (seven seats) apart from
    PH standing alone (five) against a six-seat majority bar.
    """
    return [
        seat("P101", "Selangor", PH=0.50, BN=0.30, PN=0.20),
        seat("P102", "Selangor", PH=0.45, BN=0.35, PN=0.20),
        seat("P103", "Selangor", PH=0.40, BN=0.35, PN=0.25),
        seat("P104", "Johor", PH=0.40, BN=0.30, PN=0.30),
        seat("P105", "Johor", PH=0.38, BN=0.32, PN=0.30),
        seat("P106", "Johor", BN=0.45, PH=0.30, PN=0.25),
        seat("P107", "Johor", BN=0.50, PH=0.25, PN=0.25),
        seat("P108", "Selangor", PN=0.45, PH=0.35, BN=0.20),
        seat("P109", "Johor", PN=0.50, PH=0.30, BN=0.20),
        seat("P110", "Johor", PN=0.55, PH=0.25, BN=0.20),
    ]


def government_config(**overrides: object) -> SwingModelConfig:
    """Config whose Government Coalition is PH + GPS, with a 4-seat majority bar."""
    defaults: dict[str, object] = {
        "government_coalitions": frozenset({PH, GPS}),
        "majority_threshold": 4,
        "sentiment_sensitivity": 0.10,
        "state_signal_weight": 0.5,
    }
    defaults.update(overrides)
    return SwingModelConfig(**defaults)  # type: ignore[arg-type]
