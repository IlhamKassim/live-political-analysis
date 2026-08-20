"""The shareable Seat Call card, in the register-a content register.

One card renders Sample B of docs/design/seat-call-card-samples.html with real
figures — the settled design for issue #23. The sample's invented figures and
SAMPLE stamp are replaced by figures read from Storage the way public_page
does, and the framing rules from ADR 0003/0005 are applied: a Seat Call is
arithmetic against the seat's GE15 result under a state-uniform Swing.

The module follows public_page's seam, and the seam is the point:

- `card_model` computes everything a card says and returns a `CardModel` of
  plain numbers and prose. It reads no files and formats no markup, so what a
  card claims can be tested without going near SVG.
- `render_card` turns that model into one self-contained SVG. It decides
  nothing; if a figure appears here that `card_model` did not compute, that is
  a bug.

Output is a static SVG, one per Seat Call, written to `public/cards/` by the
same daily run that renders the public page — `daily.yml`'s "Render the
shareable Seat Call cards" step calls `main(--all)`. The Telegram push
channel that will carry a card as a post image is a separate, blocked-by-
this-one ticket (#40); rasterizing SVG to PNG is that ticket's call, not this
one's.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from lpa.domain import Coalition, SeatBaseline, SeatCall
from lpa.public_page import TIER_LABEL, Tier, tier_for

# -- register-a tokens, as hex so the SVG is a free-standing image ----------
# Sample B lifts the dashboard's tokens (see register-a.css); SVG can't read
# the page's CSS custom properties, so the handful the design uses are named
# here as hex.
GROUND = "#E9EAE4"  # --ground: green-grey paper stock
SURFACE = "#F2F3EE"  # --surface: the dot's fill
INK = "#17191A"  # --ink
INK_SOFT = "#55584F"  # --ink-soft: wordmark, footnote
INK_FAINT = "#666960"  # --ink-faint: eyebrow, state, gloss, band caption
RULE = "#C8CAC0"  # --rule: bar track and footnote rule

# The printed coalition inks. A coalition the palette does not name — a minor
# party that keeps its own bracketed code as its Coalition — falls back to
# ink-soft, the same honest answer public_page._swatch gives.
COALITION_INKS: Mapping[Coalition, str] = {
    "PH": "#B23A2E",
    "BN": "#1D4E89",
    "PN": "#2B7A78",
    "GPS": "#8A6D1F",
    "GRS": "#6A4A7C",
}
FALLBACK_INK = INK_SOFT

SERIF = "ui-serif, Georgia, 'Times New Roman', serif"
MONO = "ui-monospace, Menlo, Consolas, monospace"

# -- card and bar geometry: the track is 912 wide inside 84px padding -------
CARD_W = 1080
CARD_H = 1080
PAD_X = 84
TRACK_W = 912
TRACK_H = 24
TRACK_TOP = 300
TRACK_RX = 12
DOT_R = 17


def _coalition_ink(coalition: Coalition) -> str:
    return COALITION_INKS.get(coalition, FALLBACK_INK)


def _points(margin: float) -> str:
    """A vote-share margin as percentage points, which is how it is read."""
    return f"{margin * 100:.1f}"


def wrap_text(text: str, width: int) -> list[str]:
    """Break `text` at spaces so no line exceeds `width` characters.

    Neither SVG nor Pillow wraps text automatically, so the card's
    fixed-width prose lines are broken here. A character count is the
    honest, portable approximation. Public rather than module-private
    (#40): `telegram_card.py`'s PNG renderer wraps the same prose the same
    way, so the wrapping logic lives once rather than being copied.
    """
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


@dataclass(frozen=True)
class CardModel:
    """Everything the card says, and nothing about how it looks.

    Mirrors public_page.PageModel: all the arithmetic is done here, in plain
    numbers and prose, so what a card claims is testable without parsing SVG.
    """

    code: str
    name: str
    state: str
    coalition: Coalition
    """The Coalition projected to take the Seat (the call's winner)."""
    coalition_name: str
    """The winner, written out in full as coalitions.json names it."""
    margin_points: str
    """The projected lead over the runner-up, as formatted percentage points."""
    tier: Tier
    incumbent: Coalition
    """The Coalition that took the Seat at GE15 (from the Baseline)."""
    incumbent_share: float
    """GE15 vote share of the incumbent, as a fraction."""
    opponent_share: float
    """GE15 vote share of the Coalition the call runs against: the runner-up
    when the incumbent holds, the incumbent itself when the seat flips."""
    winner_ink: str
    """The dot's stroke — the projected winner's printed ink."""
    left_ink: str
    right_ink: str
    """The bar segments' inks: incumbent on the left, opponent on the right."""
    left_w: float
    right_w: float
    gap_w: float
    """The bar's three widths, in px within the 912-wide track."""
    dot_x: float
    """The dot's centre x, at the projected winner's leading edge."""
    note: str
    """The plain-language read-out sentence."""
    footnote: str
    """The arithmetic-not-judgement framing, ending in the caveat."""

    @property
    def tier_label(self) -> str:
        return TIER_LABEL[self.tier]

    @property
    def band_caption(self) -> str:
        """The caption under the dot — the winner and the certainty band."""
        return f"{self.coalition} · {self.tier_label.upper()}"


def card_model(call: SeatCall, seat: SeatBaseline, names: Mapping[Coalition, str]) -> CardModel:
    """Work out everything a card says, from one Seat Call and its Baseline.

    The bar is arithmetic against GE15 (ADR 0005): its left segment is the
    GE15 incumbent's vote share and its right segment is the share of the
    Coalition the call runs against — the runner-up when the incumbent holds,
    the incumbent itself when the seat flips. The projected lead is the neutral
    gap between them, so the dot at the winner's leading edge reads as "ahead
    by the gap". The three are drawn to a common scale so any real margin fits
    the track.

    The framed three-way scale (incumbent + contest + margin) is the one choice
    the prototype left open, since its own widths were invented. This keeps the
    settled Sample B visual (two coalition segments, a neutral gap, a dot at
    the winner's edge) while using only figures Storage really holds.
    """
    tier = tier_for(call.margin)
    ranked = sorted(seat.vote_share.items(), key=lambda kv: -kv[1])
    incumbent, incumbent_share = ranked[0]
    # A Seat whose GE15 vote is shared by only one Coalition has no runner-up.
    # The Swing Model never meets one in practice, but a card must not crash
    # if it does — the "contest" then is the whole share and no gap.
    if len(ranked) > 1:
        runner_up, runner_up_share = ranked[1]
    else:
        runner_up, runner_up_share = incumbent, 0.0

    if call.coalition == incumbent:
        # The call holds the GE15 result: the contest is winner vs runner-up.
        opponent = runner_up
        opponent_share = runner_up_share
        left_ink = _coalition_ink(incumbent)
        right_ink = _coalition_ink(runner_up)
        winner_ink = left_ink
    else:
        # The call flips the Seat: the contest is incumbent vs the projected
        # winner, and the winner's own GE15 share fills the right segment.
        opponent = call.coalition
        opponent_share = seat.vote_share.get(opponent, 0.0)
        left_ink = _coalition_ink(incumbent)
        right_ink = _coalition_ink(opponent)
        winner_ink = right_ink

    scale = incumbent_share + opponent_share + call.margin
    left_w = incumbent_share / scale * TRACK_W
    right_w = opponent_share / scale * TRACK_W
    gap_w = call.margin / scale * TRACK_W

    # The dot marks the projected winner's leading edge: the incumbent's right
    # edge when it holds, the opponent's left edge when the seat flips.
    if call.coalition == incumbent:
        dot_x = left_w
    else:
        dot_x = left_w + gap_w

    margin_points = _points(call.margin)
    note = (
        f"The projection puts {seat.name} with "
        f"{names.get(call.coalition, call.coalition)}, ahead by {margin_points} points."
    )
    footnote = (
        f"That is a Seat-Level Projection: arithmetic against the seat's GE15 "
        f"result under a swing that is the same across the whole state — "
        f"not a judgement about {seat.name} itself. Not calibrated."
    )
    return CardModel(
        code=call.code,
        name=seat.name,
        state=seat.state,
        coalition=call.coalition,
        coalition_name=names.get(call.coalition, call.coalition),
        margin_points=margin_points,
        tier=tier,
        incumbent=incumbent,
        incumbent_share=incumbent_share,
        opponent_share=opponent_share,
        winner_ink=winner_ink,
        left_ink=left_ink,
        right_ink=right_ink,
        left_w=left_w,
        right_w=right_w,
        gap_w=gap_w,
        dot_x=dot_x,
        note=note,
        footnote=footnote,
    )


# -- rendering ----------------------------------------------------------------
# The layout reproduces Sample B's composition (large serif heading, italic
# gloss, mono eyebrow, the margin bar, a plain-language note, a ruled foot pinned
# to the bottom) at the card's real 1080x1080. Coordinates are absolute because
# SVG has no auto-flow; they come from the prototype's CSS spacing translated to
# the fixed canvas.


def _bar(model: CardModel) -> str:
    """The margin bar: the incumbent's and opponent's GE15 shares with the
    projected lead as the gap between them, and a dot at the winner's edge."""
    x_left = PAD_X
    x_right = PAD_X + model.left_w + model.gap_w
    dot_x = PAD_X + model.dot_x
    cy = TRACK_TOP + TRACK_H / 2
    return (
        # The full track and the two coalition segments.
        f'<rect x="{PAD_X}" y="{TRACK_TOP}" width="{TRACK_W}" height="{TRACK_H}" '
        f'rx="{TRACK_RX}" fill="{RULE}"/>'
        f'<rect x="{x_left:.1f}" y="{TRACK_TOP}" width="{model.left_w:.1f}" '
        f'height="{TRACK_H}" fill="{model.left_ink}"/>'
        f'<rect x="{x_right:.1f}" y="{TRACK_TOP}" width="{model.right_w:.1f}" '
        f'height="{TRACK_H}" fill="{model.right_ink}"/>'
        # The dot at the winner's leading edge.
        f'<circle cx="{dot_x:.1f}" cy="{cy:.1f}" r="{DOT_R}" fill="{SURFACE}" '
        f'stroke="{model.winner_ink}" stroke-width="4"/>'
        # The margin, read off the dot.
        f'<text x="{dot_x:.1f}" y="372" text-anchor="middle" font-family="{SERIF}" '
        f'font-size="26" fill="{INK}">{model.margin_points} pts</text>'
        f'<text x="{dot_x:.1f}" y="396" text-anchor="middle" font-family="{MONO}" '
        f'font-size="13" letter-spacing=".14em" fill="{INK_FAINT}">'
        f"{model.band_caption}</text>"
    )


def _line(
    x: float, y: float, text: str, font: str, size: float, fill: str, weight: str = "normal"
) -> str:
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" font-family="{font}" font-size="{size:g}" '
        f'fill="{fill}" font-weight="{weight}">{html.escape(text)}</text>'
    )


def render_card(model: CardModel) -> str:
    """One card as a single self-contained SVG. Decides nothing."""
    footnote_lines = wrap_text(model.footnote, 96)
    note_lines = wrap_text(model.note, 78)

    note_text = "".join(
        _line(PAD_X, 458.0 + i * 35, line, SERIF, 23, INK) for i, line in enumerate(note_lines)
    )

    # The footnote's emphasised phrase, then the rest, wrapping as needed.
    foot_baselines = [1006 + i * 24 for i in range(len(footnote_lines))]
    foot_text = ""
    for i, line in enumerate(footnote_lines):
        if "Seat-Level Projection" in line:
            head, _, tail = line.partition("Seat-Level Projection")
            foot_text += (
                f'<text x="{PAD_X}" y="{foot_baselines[i]}" font-family="{SERIF}" '
                f'font-size="14" fill="{INK_SOFT}">{html.escape(head)}'
                f'<tspan fill="{INK}">Seat-Level Projection</tspan>'
                f"{html.escape(tail)}</text>"
            )
        else:
            foot_text += _line(PAD_X, foot_baselines[i], line, SERIF, 14, INK_SOFT)

    # The rule above the footnote.
    rule_y = 986 if len(footnote_lines) <= 2 else 986 + (len(footnote_lines) - 2) * 24

    if model.tier == Tier.TIGHT:
        summary = (
            f"Shareable Seat Call card for {model.name} ({model.state}): "
            f"{model.coalition_name} is projected to take the Seat, ahead by "
            f"{model.margin_points} points ({model.tier_label}, under six points). "
            f"Not calibrated."
        )
    else:
        summary = (
            f"Shareable Seat Call card for {model.name} ({model.state}): "
            f"{model.coalition_name} is projected to take the Seat, ahead by "
            f"{model.margin_points} points ({model.tier_label}). Not calibrated."
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_W}" height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}" role="img" aria-label="{html.escape(summary)}">
  <rect width="{CARD_W}" height="{CARD_H}" fill="{GROUND}"/>
  <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".15" numOctaves="3"/></filter>
  <rect width="{CARD_W}" height="{CARD_H}" filter="url(#grain)" opacity=".035"/>
  <g>
    <text x="{PAD_X}" y="46" font-family="{SERIF}" font-size="15" fill="{INK_SOFT}">Live Political Analysis <tspan fill="{INK}">· reading this site</tspan></text>
    <text x="{PAD_X}" y="118" font-family="{MONO}" font-size="12" letter-spacing=".18em" fill="{INK_FAINT}">Seat-Level Projection · GE16</text>
    <text x="{PAD_X}" y="188" font-family="{SERIF}" font-size="58" letter-spacing="-0.02em" fill="{INK}">{html.escape(model.name)}</text>
    <text x="{PAD_X}" y="212" font-family="{MONO}" font-size="14" letter-spacing=".1em" fill="{INK_FAINT}">{html.escape(model.code)} · {html.escape(model.state.upper())}</text>
    <text x="{PAD_X}" y="262" font-family="{SERIF}" font-size="17" font-style="italic" fill="{INK_FAINT}">one entry in the Seat-Level Projection</text>
    {_bar(model)}
    <g>{note_text}</g>
    <line x1="{PAD_X}" y1="{rule_y}" x2="{PAD_X + TRACK_W}" y2="{rule_y}" stroke="{RULE}" stroke-width="1"/>
    <g>{foot_text}</g>
  </g>
</svg>"""


# -- I/O -----------------------------------------------------------------------
# The whole read half in one place, so the CLI and any future consumer render
# the same cards from the same Storage reads, exactly as public_page.build_page
# does for the page.


def build_card(engine: Engine, code: str, names: Mapping[Coalition, str]) -> str:
    """Render the card for one Seat Call, named by its Baseline code.

    Mirrors public_page.build_page's reads: the latest Projection's Seat Calls
    (Storage keeps one day's per ADR 0005) joined to the Baseline.
    """
    from lpa.storage import load_projections, load_seat_baselines

    projections = load_projections(engine)
    if not projections:
        raise SystemExit("No Projection stored. Run `python -m lpa.pipeline` to compute one.")
    calls = projections[-1].seat_calls
    if not calls:
        raise SystemExit(
            "The latest Projection carries no Seat Calls. Run `python -m lpa.pipeline` "
            "to compute a Seat-Level Projection."
        )
    baseline = {s.code: s for s in load_seat_baselines(engine)}
    call = next((c for c in calls if c.code == code), None)
    if call is None:
        raise SystemExit(f"No Seat Call for {code!r} in the latest Projection.")
    seat = baseline.get(code)
    if seat is None:
        raise SystemExit(f"Seat Call {code!r} has no Baseline Seat.")
    return render_card(card_model(call, seat, names))


def build_all_cards(engine: Engine, names: Mapping[Coalition, str]) -> list[tuple[str, str]]:
    """Render one card per Seat Call, as (code, svg) pairs."""
    from lpa.storage import load_projections, load_seat_baselines

    projections = load_projections(engine)
    if not projections or not projections[-1].seat_calls:
        raise SystemExit(
            "No Seat-Level Projection stored. Run `python -m lpa.pipeline` to compute one."
        )
    baseline = {s.code: s for s in load_seat_baselines(engine)}
    cards: list[tuple[str, str]] = []
    for call in projections[-1].seat_calls:
        seat = baseline.get(call.code)
        if seat is None:
            raise SystemExit(f"Seat Call {call.code!r} has no Baseline Seat.")
        cards.append((call.code, render_card(card_model(call, seat, names))))
    return cards


def main() -> None:
    """Render real Seat Call cards from Storage and write them to disk."""
    import argparse
    from pathlib import Path

    from lpa.config import coalition_names, load_coalition_config
    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seat",
        help="the Seat code (e.g. P.048) to render a card for; omit with --all",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="render one card per Seat Call in the latest Projection",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public/cards"),
        help="where to write cards — a directory for --all, a file for --seat (default: public/cards)",
    )
    args = parser.parse_args()
    if not args.seat and not args.all:
        parser.error("pass --seat <code> or --all")
    if args.seat and args.all:
        parser.error("--seat and --all are mutually exclusive")

    names = coalition_names(load_coalition_config())
    engine = connect()
    if args.all:
        cards = build_all_cards(engine, names)
        args.output.mkdir(parents=True, exist_ok=True)
        for code, svg in cards:
            (args.output / f"{code}.svg").write_text(svg, encoding="utf-8")
        print(f"Wrote {len(cards)} cards to {args.output}")
    else:
        assert args.seat is not None
        svg = build_card(engine, args.seat, names)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        target = args.output if args.output.suffix == ".svg" else args.output / f"{args.seat}.svg"
        target.write_text(svg, encoding="utf-8")
        print(f"Wrote {target}")


if __name__ == "__main__":
    main()
