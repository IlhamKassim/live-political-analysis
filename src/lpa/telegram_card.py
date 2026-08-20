"""PNG rendering of the Telegram post images (#40).

Two cards, both raster images: the Seat Call card (Sample B register,
`docs/design/telegram-post-samples.html`) for a Seat-anchored post, and the
aggregate card (Sample C: a timeline over a thin whole-chamber bar) for a
post with no single Seat to point at. Two timeline stops here, not the
mockup's three — see `_draw_timeline`'s own docstring for why.

`render_aggregate_card_png` is trigger-agnostic on purpose: its
`AggregateCardModel` takes the headline/gloss/caption prose as plain
strings rather than deciding them from a trigger type itself, since #40's
three trigger types (Election Status, State Election Signal, a chamber-wide
Majority swing) each need different wording and only one of them
(`election_status_aggregate_model`, for Election Status) has copy the
approved mockup already settles — composing the other two belongs to the
pipeline-wiring batch that actually calls `detect_triggers`, not to this
renderer.

Unlike Sample C's own markup — ordinary CSS flow with margins, not the
absolute SVG coordinates Sample B/`seat_call_card.py` use — there is no
existing numeric layout to copy for this card. The positions below are an
original computation, not a reproduction of a source of truth, adapted
from `seat_call_card.py`'s own proven spacing rhythm (same `PAD_X`, similar
line heights) rather than invented independently, and checked by actually
rendering the card and looking at it (see the commit this landed in).

Rendered with Pillow rather than rasterizing the existing SVG cards
(`seat_call_card.py`): Telegram's post image needs a raster format, and a
reliable SVG-to-PNG conversion needs a system Cairo library (`cairosvg`
was tried and confirmed to require `libcairo` at import time, not just
`pip install`) — a new failure mode this project's unattended daily
pipeline (ADR 0002: "must not need a human on a good day") has no reason
to take on. Pillow is a pure-pip, no-system-deps dependency instead,
already precedented by this project's own `og-image.png` authoring script
this session.

The Seat-anchored card reuses `seat_call_card.card_model()`'s output
directly rather than recomputing any figure — only the drawing technology
differs (raster pixels here, SVG markup there), the same "every published
figure traces to stored arithmetic, never re-derived" discipline #51 and
#53a already follow for the public page. Geometry constants (`PAD_X`,
`TRACK_W`, ...) are imported from `seat_call_card.py` rather than re-typed,
and every text element uses Pillow's baseline `anchor` so the same x/y the
SVG states can be copied directly — code review, 20 Aug 2026, after an
earlier version re-typed the geometry by eye and drifted from the SVG by
18px on the bar alone, plus a structural mismatch: SVG text is
baseline-positioned and Pillow's default `draw.text` is top-left-positioned,
so eyeballed y-values were never actually going to match.

Deliberate simplification against the SVG version: no grain texture. The
SVG's `feTurbulence` noise is a decorative touch at 3.5% opacity, invisible
at the thumbnail size a Telegram post is actually read at (the same
"survives being forwarded" bar `docs/design/telegram-post-samples.html`
judges its samples against) — reproducing it in Pillow needs per-pixel
noise generation with no clean built-in, and nothing load-bearing rides on
it, so it is left out rather than adding complexity for an effect nobody
will see.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from lpa.domain import ElectionStatus
from lpa.return_trigger import ElectionStatusTriggerKind
from lpa.seat_call_card import (
    CARD_W,
    DOT_R,
    GROUND,
    INK,
    INK_FAINT,
    INK_SOFT,
    PAD_X,
    RULE,
    SURFACE,
    TRACK_H,
    TRACK_RX,
    TRACK_TOP,
    TRACK_W,
    CardModel,
    wrap_text,
)

if TYPE_CHECKING:
    from PIL import ImageDraw, ImageFont

CARD_SIZE = CARD_W

# DejaVu's standard Debian/Ubuntu package path (`fonts-dejavu-core`) — the
# CI workflow and daily.yml both install this explicitly rather than
# relying on whatever a runner image happens to ship, which GitHub can
# change without notice. A couple of other common locations are tried
# after it purely so this module doesn't hard-fail in local development on
# a machine that has DejaVu somewhere else.
_DEJAVU_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/dejavu"),
    Path("/opt/homebrew/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / "Library/Fonts",  # macOS, e.g. `brew install --cask font-dejavu`
    Path("/Library/Fonts"),
)


def _font_dir() -> Path:
    for candidate in _DEJAVU_CANDIDATES:
        if (candidate / "DejaVuSerif.ttf").exists():
            return candidate
    raise SystemExit(
        "No DejaVu fonts found (looked in "
        f"{', '.join(str(c) for c in _DEJAVU_CANDIDATES)}). "
        "Install the fonts-dejavu-core package (apt) or equivalent."
    )


class _Fonts:
    """The faces the card needs, loaded once per render call.

    Not a module-level singleton: `ImageFont.truetype` needs Pillow
    imported first, and importing Pillow at module load would defeat the
    point of keeping it a lazy, optional dependency (`pyproject.toml`'s
    `telegram` extra) — a caller that never renders a card should not need
    Pillow installed just to import this module.
    """

    def __init__(self) -> None:
        from PIL import ImageFont

        d = _font_dir()
        self.serif_15 = ImageFont.truetype(str(d / "DejaVuSerif.ttf"), 15)
        self.serif_58 = ImageFont.truetype(str(d / "DejaVuSerif.ttf"), 58)
        self.serif_23 = ImageFont.truetype(str(d / "DejaVuSerif.ttf"), 23)
        self.serif_26 = ImageFont.truetype(str(d / "DejaVuSerif.ttf"), 26)
        self.serif_14 = ImageFont.truetype(str(d / "DejaVuSerif.ttf"), 14)
        self.serif_italic_17 = ImageFont.truetype(str(d / "DejaVuSerif-Italic.ttf"), 17)
        self.mono_12 = ImageFont.truetype(str(d / "DejaVuSansMono.ttf"), 12)
        self.mono_14 = ImageFont.truetype(str(d / "DejaVuSansMono.ttf"), 14)
        self.mono_13 = ImageFont.truetype(str(d / "DejaVuSansMono.ttf"), 13)
        # Sizes only the aggregate card (Sample C) uses.
        self.serif_52 = ImageFont.truetype(str(d / "DejaVuSerif.ttf"), 52)
        self.serif_italic_19 = ImageFont.truetype(str(d / "DejaVuSerif-Italic.ttf"), 19)
        self.serif_22 = ImageFont.truetype(str(d / "DejaVuSerif.ttf"), 22)
        self.serif_italic_22 = ImageFont.truetype(str(d / "DejaVuSerif-Italic.ttf"), 22)
        self.serif_21 = ImageFont.truetype(str(d / "DejaVuSerif.ttf"), 21)
        self.mono_11 = ImageFont.truetype(str(d / "DejaVuSansMono.ttf"), 11)


def _tracked_width(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, em: float
) -> float:
    """How wide `text` renders under `_tracked_text` at the same `em`."""
    tracking = font.size * em
    return float(draw.textlength(text, font=font) + tracking * len(text))


def _tracked_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    em: float,
    *,
    center: bool = False,
) -> None:
    """Baseline text with letter-spacing, in em (a fraction of the font's
    own size) — Pillow has no letter-spacing of its own, so each character
    is placed by hand, the same technique this project's `og-image.png`
    authoring script already used. `center=True` matches SVG's
    `text-anchor="middle"`, which per-character drawing has no other way
    to express."""
    x, y = xy
    if center:
        x -= _tracked_width(draw, text, font, em) / 2
    tracking = font.size * em
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += draw.textlength(ch, font=font) + tracking


def render_seat_card_png(model: CardModel) -> bytes:
    """The Seat Call card (Sample B) as PNG bytes, at its real 1080x1080.

    Decides nothing `card_model` did not already decide — every figure,
    colour, and width drawn here comes from `model`, the same seam
    `seat_call_card.render_card` (the SVG version) already follows. Every
    coordinate below is copied directly from that SVG's own x/y values
    (`anchor="ls"`/`"ms"` make Pillow's text baseline-positioned like SVG's,
    so the same numbers place the same glyph in the same spot).
    """
    from PIL import Image, ImageDraw

    fonts = _Fonts()
    img = Image.new("RGB", (CARD_SIZE, CARD_SIZE), GROUND)
    draw = ImageDraw.Draw(img)

    draw.text(
        (PAD_X, 46), "Live Political Analysis ", font=fonts.serif_15, fill=INK_SOFT, anchor="ls"
    )
    wordmark_w = draw.textlength("Live Political Analysis ", font=fonts.serif_15)
    draw.text(
        (PAD_X + wordmark_w, 46), "· reading this site", font=fonts.serif_15, fill=INK, anchor="ls"
    )

    _tracked_text(
        draw, (PAD_X, 118), "Seat-Level Projection · GE16", fonts.mono_12, INK_FAINT, 0.18
    )
    draw.text((PAD_X, 188), model.name, font=fonts.serif_58, fill=INK, anchor="ls")
    _tracked_text(
        draw, (PAD_X, 212), f"{model.code} · {model.state.upper()}", fonts.mono_14, INK_FAINT, 0.1
    )
    draw.text(
        (PAD_X, 262),
        "one entry in the Seat-Level Projection",
        font=fonts.serif_italic_17,
        fill=INK_FAINT,
        anchor="ls",
    )

    _draw_bar(draw, model, fonts)

    note_lines = wrap_text(model.note, 78)
    for i, line in enumerate(note_lines):
        draw.text((PAD_X, 458.0 + i * 35), line, font=fonts.serif_23, fill=INK, anchor="ls")

    footnote_lines = wrap_text(model.footnote, 96)
    rule_y = 986 if len(footnote_lines) <= 2 else 986 + (len(footnote_lines) - 2) * 24
    draw.line([(PAD_X, rule_y), (PAD_X + TRACK_W, rule_y)], fill=RULE, width=1)
    for i, line in enumerate(footnote_lines):
        baseline = 1006 + i * 24
        if "Seat-Level Projection" in line:
            head, _, tail = line.partition("Seat-Level Projection")
            x = PAD_X
            draw.text((x, baseline), head, font=fonts.serif_14, fill=INK_SOFT, anchor="ls")
            x += draw.textlength(head, font=fonts.serif_14)
            draw.text(
                (x, baseline), "Seat-Level Projection", font=fonts.serif_14, fill=INK, anchor="ls"
            )
            x += draw.textlength("Seat-Level Projection", font=fonts.serif_14)
            draw.text((x, baseline), tail, font=fonts.serif_14, fill=INK_SOFT, anchor="ls")
        else:
            draw.text((PAD_X, baseline), line, font=fonts.serif_14, fill=INK_SOFT, anchor="ls")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _draw_bar(draw: ImageDraw.ImageDraw, model: CardModel, fonts: _Fonts) -> None:
    """The margin bar: copies `seat_call_card._bar`'s geometry exactly."""
    x_left = PAD_X
    x_right = PAD_X + model.left_w + model.gap_w
    dot_x = PAD_X + model.dot_x
    cy = TRACK_TOP + TRACK_H / 2

    draw.rounded_rectangle(
        [PAD_X, TRACK_TOP, PAD_X + TRACK_W, TRACK_TOP + TRACK_H], radius=TRACK_RX, fill=RULE
    )
    draw.rectangle(
        [x_left, TRACK_TOP, x_left + model.left_w, TRACK_TOP + TRACK_H], fill=model.left_ink
    )
    draw.rectangle(
        [x_right, TRACK_TOP, x_right + model.right_w, TRACK_TOP + TRACK_H], fill=model.right_ink
    )
    draw.ellipse(
        [dot_x - DOT_R, cy - DOT_R, dot_x + DOT_R, cy + DOT_R],
        fill=SURFACE,
        outline=model.winner_ink,
        width=4,
    )

    margin_text = f"{model.margin_points} pts"
    draw.text((dot_x, 372), margin_text, font=fonts.serif_26, fill=INK, anchor="ms")
    _tracked_text(
        draw, (dot_x, 396), model.band_caption, fonts.mono_13, INK_FAINT, 0.14, center=True
    )


# ── the aggregate card (Sample C) ──────────────────────────────────────────

AGGREGATE_CARD_H = 720
"""The card's real height — wide, not square, matching Sample C's own
`.card-wide` (the timeline reads better wide, and there is no dot needing a
square frame the way the Seat Call card's bar has)."""

MAJORITY_LINE_INK = "#B23A2E"
"""The Majority line's accent colour, copied from the approved mockup. Not
a Coalition's ink reused by accident — it marks a position on the bar, not
any one of the four Coalitions the Government Coalition fill (below)
deliberately avoids naming."""


@dataclass(frozen=True)
class AggregateCardModel:
    """Everything the aggregate card says, and nothing about how it looks.

    Trigger-agnostic (#40): `eyebrow`/`headline`/`gloss`/`caption` arrive as
    plain strings rather than being decided from a trigger type here, since
    each of #40's three trigger types needs different wording and only
    Election Status has copy the approved mockup already settles
    (`election_status_aggregate_model`, below). The rest — the timeline
    dates and the chamber-bar figures — are the same regardless of which
    trigger produced the post.
    """

    eyebrow: str
    headline: str
    gloss: str
    caption: str
    dissolved_on: date | None
    polling_date: date | None
    government_seats: int
    total_seats: int
    majority_threshold: int


def _long_date(day: date) -> str:
    return f"{day.day} {day.strftime('%B %Y')}"


def election_status_aggregate_model(
    kind: ElectionStatusTriggerKind,
    status: ElectionStatus,
    government_seats: int,
    total_seats: int,
    majority_threshold: int,
) -> AggregateCardModel:
    """The aggregate card for trigger 1 (#40): GE16 called, or a polling
    date newly set. Copy matches Sample C's approved wording for the
    "called" case verbatim; the "polling date set" case follows the same
    voice, since the mockup itself has no sample for it."""
    if kind == ElectionStatusTriggerKind.CALLED:
        headline = "GE16 has been called."
        gloss = "the Dewan Rakyat was dissolved — a polling date has not been set yet"
    else:
        assert status.polling_date is not None  # the trigger only fires once it is
        headline = f"Polling day is {_long_date(status.polling_date)}."
        gloss = "the Election Commission has set the date"
    return AggregateCardModel(
        eyebrow="Election Status · GE16",
        headline=headline,
        gloss=gloss,
        caption=(
            "Election Status is context for reading a Projection, not an "
            "input to one — dissolution starts the clock, it does not move "
            "the arithmetic."
        ),
        dissolved_on=status.dissolved_on,
        polling_date=status.polling_date,
        government_seats=government_seats,
        total_seats=total_seats,
        majority_threshold=majority_threshold,
    )


def render_aggregate_card_png(model: AggregateCardModel) -> bytes:
    """The aggregate card (Sample C) as PNG bytes, at its real 1080x720.

    Decides nothing `model` did not already decide. Unlike
    `render_seat_card_png`, these coordinates are an original layout (see
    the module docstring) rather than a copy of an existing SVG's own
    values — Sample C's markup is ordinary CSS flow, not absolute
    positioning, so there was no source of truth to copy from.
    """
    from PIL import Image, ImageDraw

    fonts = _Fonts()
    img = Image.new("RGB", (CARD_W, AGGREGATE_CARD_H), GROUND)
    draw = ImageDraw.Draw(img)

    draw.text(
        (PAD_X, 46), "Live Political Analysis ", font=fonts.serif_15, fill=INK_SOFT, anchor="ls"
    )
    wordmark_w = draw.textlength("Live Political Analysis ", font=fonts.serif_15)
    draw.text(
        (PAD_X + wordmark_w, 46), "· reading this site", font=fonts.serif_15, fill=INK, anchor="ls"
    )

    _tracked_text(draw, (PAD_X, 118), model.eyebrow, fonts.mono_12, INK_FAINT, 0.18)
    headline_lines = wrap_text(model.headline, 40)
    for i, line in enumerate(headline_lines):
        draw.text((PAD_X, 186.0 + i * 58), line, font=fonts.serif_52, fill=INK, anchor="ls")
    gloss_y = 186 + len(headline_lines) * 58 - 58 + 44
    gloss_lines = wrap_text(model.gloss, 62)
    for i, line in enumerate(gloss_lines):
        draw.text(
            (PAD_X, gloss_y + i * 26), line, font=fonts.serif_italic_19, fill=INK_FAINT, anchor="ls"
        )

    timeline_top = gloss_y + len(gloss_lines) * 26 + 44
    _draw_timeline(draw, model, fonts, timeline_top)

    standing_top = timeline_top + 148
    _tracked_text(
        draw,
        (PAD_X, standing_top),
        "Where the Projection stands today",
        fonts.mono_11,
        INK_FAINT,
        0.13,
    )
    _draw_chamber_bar(draw, model, fonts, standing_top + 30)

    footer_top = standing_top + 110
    draw.line([(PAD_X, footer_top), (PAD_X + TRACK_W, footer_top)], fill=RULE, width=1)
    caption_lines = wrap_text(model.caption, 96)
    for i, line in enumerate(caption_lines):
        draw.text(
            (PAD_X, footer_top + 24 + i * 22),
            line,
            font=fonts.serif_14,
            fill=INK_SOFT,
            anchor="ls",
        )

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _draw_timeline(
    draw: ImageDraw.ImageDraw, model: AggregateCardModel, fonts: _Fonts, top: float
) -> None:
    """Two stops (Dissolution, Polling) — deliberately not the approved
    mockup's three. `ElectionStatus` has no `nomination_date` field to draw
    a real third stop from, and a permanently-hollow "not set" stop that
    could never fill in once nomination day is actually announced would be
    worse than honest — it would look like live-tracked information this
    project never actually tracks. Two real, tracked stops instead of three,
    one of which would always lie by omission."""
    spine_y = top + 40
    stop1_x = PAD_X + 60
    stop2_x = PAD_X + TRACK_W - 60
    dot_r = 12

    both_known = model.dissolved_on is not None and model.polling_date is not None
    draw.line(
        [(stop1_x, spine_y), (stop2_x, spine_y)],
        fill=INK_SOFT if both_known else RULE,
        width=2,
    )

    for x, label, day in (
        (stop1_x, "DISSOLUTION", model.dissolved_on),
        (stop2_x, "POLLING", model.polling_date),
    ):
        _tracked_text(draw, (x, top), label, fonts.mono_14, INK_FAINT, 0.13, center=True)
        if day is not None:
            draw.ellipse([x - dot_r, spine_y - dot_r, x + dot_r, spine_y + dot_r], fill=INK)
            draw.text(
                (x, spine_y + 44), _long_date(day), font=fonts.serif_22, fill=INK, anchor="ms"
            )
        else:
            draw.ellipse(
                [x - dot_r, spine_y - dot_r, x + dot_r, spine_y + dot_r],
                fill=GROUND,
                outline=RULE,
                width=3,
            )
            draw.text(
                (x, spine_y + 44),
                "not set",
                font=fonts.serif_italic_22,
                fill=INK_FAINT,
                anchor="ms",
            )


def _draw_chamber_bar(
    draw: ImageDraw.ImageDraw, model: AggregateCardModel, fonts: _Fonts, top: float
) -> None:
    """The whole-chamber bar: the Government Coalition's share in a neutral
    ink (never one Coalition's — that block is four Coalitions), with the
    Majority line marked. Deliberately a ruled bar, never a map (HANDOFF's
    settled decisions already rejected a choropleth of Malaysia)."""
    bar_h = 22
    government_w = TRACK_W * model.government_seats / model.total_seats
    threshold_x = PAD_X + TRACK_W * model.majority_threshold / model.total_seats

    draw.rectangle([PAD_X, top, PAD_X + TRACK_W, top + bar_h], fill=RULE)
    draw.rectangle([PAD_X, top, PAD_X + government_w, top + bar_h], fill=INK_SOFT)
    draw.line(
        [(threshold_x, top - 12), (threshold_x, top + bar_h + 12)], fill=MAJORITY_LINE_INK, width=2
    )
    _tracked_text(
        draw,
        (threshold_x + 8, top - 16),
        f"{model.majority_threshold} — MAJORITY",
        fonts.mono_13,
        MAJORITY_LINE_INK,
        0.1,
    )

    non_government = model.total_seats - model.government_seats
    draw.text(
        (PAD_X, top + bar_h + 34),
        f"Government Coalition {model.government_seats}",
        font=fonts.serif_21,
        fill=INK,
        anchor="ls",
    )
    non_gov_text = f"Non-government {non_government}"
    non_gov_w = draw.textlength(non_gov_text, font=fonts.serif_21)
    draw.text(
        (PAD_X + TRACK_W - non_gov_w, top + bar_h + 34),
        non_gov_text,
        font=fonts.serif_21,
        fill=INK_FAINT,
        anchor="ls",
    )
