"""PolitikKu's hemicycle: a 222-dot Dewan Rakyat diagram, drawn not animated.

Part of #69's design handoff (#73). A different component from the live
chamber dashboard's own hemicycle (`public_page._hemicycle`, built for #17) —
checked that one first, per #73's "check for reuse" instruction, and the two
diverge in every dimension that matters: this one is a fixed 7-row, 222-seat,
`0 0 400 214` diagram coloured by a caller-supplied 3-way certainty split
(Government clear / within model noise / Non-government clear, ink vs slate,
no party colours — the design system's "single axis of certainty" per
CONTEXT.md's Non-government entry), where the dashboard's is a 10-row,
generic-total diagram coloured per-Seat by party ink with individual
tooltips and a computed buffer brace. Only the *technique* carries over
(radius-proportional row seat counts, angle-sorted left-to-right placement)
— the row math itself is re-derived here because the two diagrams disagree
on a real detail: this one puts 100% of the rounding remainder on the
outermost row (the handoff's own words), where the dashboard spreads it by
largest-remainder across whichever rows round down the least.

Server-rendered SVG with a fixed `viewBox`, so it is scale-free by
construction — sizing at the three places it's reused (homepage projection
panel, landing-page hero texture, and wherever else a page wants it) is a
caller-side CSS/width concern, per #73's "not in scope: wiring into a
specific page." No script, no CSS transition or animation, matching the
handoff's explicit "do not animate the hemicycle... on load."
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from enum import StrEnum

from lpa.public_page import PageModel, Tier

TOTAL_SEATS = 222
MAJORITY_THRESHOLD = 112

_ROWS = 7
_R_INNER, _R_OUTER = 84.0, 176.0
_CX, _CY = 200.0, 196.0
_DOT_RADIUS = 3.5
VIEW_BOX = "0 0 400 214"

_THRESHOLD_STROKE = "var(--line-strong)"
_THRESHOLD_LABEL_FILL = "var(--muted)"


class Palette(StrEnum):
    """Which of the handoff's two recolourings to draw the dots in.

    `LIGHT` is the normal on-paper reading (homepage projection panel);
    `DARK_BAND` is the muted recolouring reused as hero texture on a navy
    band, per the handoff's "dark-band variant... reused at opacity .14–.16
    as hero texture on the landing page." That opacity, and the absolute
    positioning it's shown at, are the caller's job — see the module
    docstring.
    """

    LIGHT = "light"
    DARK_BAND = "dark_band"


_FILL: dict[Palette, dict[str, str]] = {
    Palette.LIGHT: {
        "government": "var(--data-government)",
        "noise": "var(--data-noise)",
        "nongovernment": "var(--data-nongovernment)",
    },
    Palette.DARK_BAND: {
        "government": "var(--data-government)",
        "noise": "var(--data-noise)",
        "nongovernment": "var(--data-nongovernment)",
    },
}


@dataclass(frozen=True)
class HemicycleCounts:
    """The 222-seat split this render draws — supplied by the caller.

    Not wired to a real Projection here (#73's scope is the component, not
    the data) — #74/#75/#79 each compute these three numbers from whatever
    the page is actually showing and pass them in.
    """

    government_clear: int
    noise: int
    nongovernment_clear: int

    def __post_init__(self) -> None:
        total = self.government_clear + self.noise + self.nongovernment_clear
        if total != TOTAL_SEATS:
            raise ValueError(
                f"HemicycleCounts must sum to {TOTAL_SEATS} seats, got {total} "
                f"({self.government_clear} + {self.noise} + {self.nongovernment_clear})"
            )


def hemicycle_counts(page: PageModel) -> HemicycleCounts:
    """The dashboard's per-Seat tiers, tallied into the Government clear /
    within model noise / Non-government clear split this module draws.

    Moved here from `politikku_homepage.py` when ADR 0014 retired that
    module — `politikku_projection.py` (which survives) shared this exact
    computation via import rather than a second copy, so it needed a
    surviving home too."""
    government_clear = sum(1 for s in page.seats if s.government and s.tier != Tier.TIGHT)
    nongovernment_clear = sum(1 for s in page.seats if not s.government and s.tier != Tier.TIGHT)
    noise = sum(1 for s in page.seats if s.tier == Tier.TIGHT)
    return HemicycleCounts(
        government_clear=government_clear, noise=noise, nongovernment_clear=nongovernment_clear
    )


def _row_radii() -> list[float]:
    """7 rows, radii linear from 84 to 176 — the handoff's own numbers."""
    return [_R_INNER + (_R_OUTER - _R_INNER) * i / (_ROWS - 1) for i in range(_ROWS)]


def _row_counts() -> list[int]:
    """Seats per row, proportional to each row's radius, remainder on the
    outer row — the handoff's allocation rule, not the dashboard's
    largest-remainder one (see module docstring)."""
    radii = _row_radii()
    weight = sum(radii)
    counts = [math.floor(TOTAL_SEATS * r / weight) for r in radii]
    counts[-1] += TOTAL_SEATS - sum(counts)
    return counts


def _slots() -> list[tuple[float, float]]:
    """Every seat's (angle, radius), sorted so the sequence runs left→right.

    `a = π − t·π` for `t` evenly across each row (the handoff's formula
    verbatim) — `t=0` is the row's leftmost seat (`a=π`), `t=1` its
    rightmost (`a=0`). Sorting all rows together by descending angle then
    interleaves every row into one left-to-right sequence, which is what the
    fill bands in `render_hemicycle` walk.
    """
    slots: list[tuple[float, float]] = []
    for radius, count in zip(_row_radii(), _row_counts()):
        for i in range(count):
            t = 0.5 if count == 1 else i / (count - 1)
            angle = math.pi - t * math.pi
            slots.append((angle, radius))
    slots.sort(key=lambda s: -s[0])
    return slots


def _point(angle: float, radius: float) -> tuple[float, float]:
    return _CX + math.cos(angle) * radius, _CY - math.sin(angle) * radius


def render_hemicycle(
    counts: HemicycleCounts,
    *,
    palette: Palette = Palette.LIGHT,
    show_threshold: bool = True,
    majority_label: str = "MAJORITY 112",
    css_class: str = "pk-hemicycle",
) -> str:
    """The hemicycle as one `<svg>` string.

    `show_threshold`/`majority_label` are independent of `palette`: the
    handoff's own hero-texture instances draw `DARK_BAND` dots with no
    threshold line at all, while the homepage panel draws `LIGHT` dots with
    one — a caller picks both, this function does not infer one from the
    other. `majority_label` defaults to the handoff's exact copy
    ("MAJORITY 112") but is a parameter rather than a constant since #81
    will need "MAJORITI 112" for the Bahasa Malaysia route.
    """
    fills = _FILL[palette]
    bands = (
        (counts.government_clear, fills["government"]),
        (counts.noise, fills["noise"]),
        (counts.nongovernment_clear, fills["nongovernment"]),
    )
    dot_fills: list[str] = []
    for n, color in bands:
        dot_fills.extend([color] * n)

    circles = "".join(
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{_DOT_RADIUS}" fill="{fill}"></circle>'
        for (angle, radius), fill in zip(_slots(), dot_fills)
        for x, y in (_point(angle, radius),)
    )

    threshold = ""
    if show_threshold:
        threshold = (
            f'<line x1="{_CX:.0f}" y1="16" x2="{_CX:.0f}" y2="200" '
            f'stroke="{_THRESHOLD_STROKE}" stroke-width="1" stroke-dasharray="3 3"></line>'
            f'<text x="{_CX:.0f}" y="211" text-anchor="middle" '
            'font-family="var(--mono, monospace)" font-size="9.5" '
            f'fill="{_THRESHOLD_LABEL_FILL}" letter-spacing="0.06em">'
            f"{html.escape(majority_label)}</text>"
        )

    summary = (
        f"Hemicycle of {TOTAL_SEATS} Dewan Rakyat Seats: "
        f"{counts.government_clear} clear for the Government Coalition, "
        f"{counts.noise} within model noise, "
        f"{counts.nongovernment_clear} clear for Non-government, "
        f"against a {MAJORITY_THRESHOLD}-seat Majority."
    )
    return (
        f'<svg class="{html.escape(css_class)}" viewBox="{VIEW_BOX}" role="img" '
        f'aria-label="{html.escape(summary)}">{circles}{threshold}</svg>'
    )
