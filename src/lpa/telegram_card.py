"""PNG rendering of the Telegram post images (#40).

Two cards, both raster images: the Seat Call card (Sample B register,
`docs/design/telegram-post-samples.html`) for a Seat-anchored post, and a
separate aggregate card (Sample C) for a post with no single Seat to point
at — not yet built here, a follow-up batch.

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
#53a already follow for the public page.

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

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from lpa.seat_call_card import (
    GROUND,
    INK,
    INK_FAINT,
    INK_SOFT,
    RULE,
    SURFACE,
    CardModel,
    wrap_text,
)

if TYPE_CHECKING:
    from PIL import ImageDraw

CARD_SIZE = 1080

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
    """The four faces the card needs, loaded once per render call.

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


def render_seat_card_png(model: CardModel) -> bytes:
    """The Seat Call card (Sample B) as PNG bytes, at its real 1080x1080.

    Decides nothing `card_model` did not already decide — every figure,
    colour, and width drawn here comes from `model`, the same seam
    `seat_call_card.render_card` (the SVG version) already follows.
    """
    from PIL import Image, ImageDraw

    fonts = _Fonts()
    img = Image.new("RGB", (CARD_SIZE, CARD_SIZE), GROUND)
    draw = ImageDraw.Draw(img)
    pad_x = 84

    draw.text((pad_x, 32), "Live Political Analysis", font=fonts.serif_15, fill=INK_SOFT)
    wordmark_w = draw.textlength("Live Political Analysis ", font=fonts.serif_15)
    draw.text((pad_x + wordmark_w, 32), "· reading this site", font=fonts.serif_15, fill=INK)

    draw.text((pad_x, 104), "SEAT-LEVEL PROJECTION · GE16", font=fonts.mono_12, fill=INK_FAINT)
    draw.text((pad_x, 148), model.name, font=fonts.serif_58, fill=INK)
    draw.text(
        (pad_x, 200), f"{model.code} · {model.state.upper()}", font=fonts.mono_14, fill=INK_FAINT
    )
    draw.text(
        (pad_x, 244),
        "one entry in the Seat-Level Projection",
        font=fonts.serif_italic_17,
        fill=INK_FAINT,
    )

    _draw_bar(draw, model, fonts, pad_x)

    note_lines = wrap_text(model.note, 78)
    for i, line in enumerate(note_lines):
        draw.text((pad_x, 440.0 + i * 35), line, font=fonts.serif_23, fill=INK)

    footnote_lines = wrap_text(model.footnote, 96)
    rule_y = 968 if len(footnote_lines) <= 2 else 968 + (len(footnote_lines) - 2) * 24
    draw.line([(pad_x, rule_y), (pad_x + 912, rule_y)], fill=RULE, width=1)
    for i, line in enumerate(footnote_lines):
        baseline = 988 + i * 24
        if "Seat-Level Projection" in line:
            head, _, tail = line.partition("Seat-Level Projection")
            x = pad_x
            draw.text((x, baseline), head, font=fonts.serif_14, fill=INK_SOFT)
            x += draw.textlength(head, font=fonts.serif_14)
            draw.text((x, baseline), "Seat-Level Projection", font=fonts.serif_14, fill=INK)
            x += draw.textlength("Seat-Level Projection", font=fonts.serif_14)
            draw.text((x, baseline), tail, font=fonts.serif_14, fill=INK_SOFT)
        else:
            draw.text((pad_x, baseline), line, font=fonts.serif_14, fill=INK_SOFT)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _draw_bar(draw: ImageDraw.ImageDraw, model: CardModel, fonts: _Fonts, pad_x: int) -> None:
    """The margin bar: mirrors `seat_call_card._bar`'s geometry exactly."""
    track_top = 282
    track_h = 24
    dot_r = 17
    x_left = pad_x
    x_right = pad_x + model.left_w + model.gap_w
    dot_x = pad_x + model.dot_x
    cy = track_top + track_h / 2

    draw.rounded_rectangle(
        [pad_x, track_top, pad_x + 912, track_top + track_h], radius=12, fill=RULE
    )
    draw.rectangle(
        [x_left, track_top, x_left + model.left_w, track_top + track_h], fill=model.left_ink
    )
    draw.rectangle(
        [x_right, track_top, x_right + model.right_w, track_top + track_h], fill=model.right_ink
    )
    draw.ellipse(
        [dot_x - dot_r, cy - dot_r, dot_x + dot_r, cy + dot_r],
        fill=SURFACE,
        outline=model.winner_ink,
        width=4,
    )

    margin_text = f"{model.margin_points} pts"
    margin_w = draw.textlength(margin_text, font=fonts.serif_26)
    draw.text((dot_x - margin_w / 2, 350), margin_text, font=fonts.serif_26, fill=INK)
    band_w = draw.textlength(model.band_caption, font=fonts.mono_13)
    draw.text((dot_x - band_w / 2, 382), model.band_caption, font=fonts.mono_13, fill=INK_FAINT)
