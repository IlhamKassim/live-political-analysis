"""The public page: one day's Projection, rendered as the Dewan Rakyat.

A static HTML file built from Storage (ADR 0006), not a served app. The daily
Action renders it and publishes it; the database is never touched at request
time. `dashboard.py` remains the internal view and is not what this replaces.

The module is in two halves, and the seam between them is the point:

- `page_model` does every piece of arithmetic the page states, and returns a
  `PageModel` of plain numbers. It reads no files and formats no strings, so
  what the page claims can be tested without going near HTML.
- `render_html` turns that model into markup. It decides nothing; if a number
  appears here that `page_model` did not compute, that is a bug.

The design and the reasoning behind it are `docs/design/HANDOFF.md`. Two
constraints from it bind this file. The register is print, not dashboard —
ruled tables, hairlines, a constrained palette, no cards. And per ADR 0005 a
per-Seat call is arithmetic against GE15 under a Swing that is uniform within
a state, so the page frames it that way and leans on the uncertainty encoding
rather than implying the model knows something about a constituency.

The chamber is emitted as server-rendered SVG rather than drawn by a script on
load. The mockup built it in JavaScript because it was inventing its seats;
here the geometry is known when the file is written, and a page that states an
election projection should not depend on script execution to say anything.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from lpa.domain import (
    Coalition,
    ElectionStatus,
    Projection,
    SeatBaseline,
    SwingModelConfig,
    government_seat_total,
)

TIGHT_MARGIN = 0.06
"""Below this projected lead a Seat is shown as too close to call.

Six points is wide for a margin, deliberately. The Swing Model has no
Seat-specific signal and two uncalibrated constants (ADR 0003), so the band has
to cover the error those imply rather than the error a fitted model would have.
"""

LIKELY_MARGIN = 0.12
"""Below this a Seat is shown at half tone, above it as solid."""

SAFE, LIKELY, TIGHT = "safe", "likely", "tight"


@dataclass(frozen=True)
class ChamberSeat:
    """One Seat as the hemicycle draws it."""

    code: str
    name: str
    state: str
    coalition: Coalition
    margin: float
    """Projected lead over the runner-up, in vote share."""
    tier: str
    government: bool


@dataclass(frozen=True)
class LedgerRow:
    """One Coalition's line in the seat ledger."""

    coalition: Coalition
    name: str
    projected: int
    baseline: int
    too_close: int
    government: bool

    @property
    def swing(self) -> int:
        return self.projected - self.baseline


@dataclass(frozen=True)
class PageModel:
    """Every number the page states, and nothing about how it looks."""

    computed_at: date
    total_seats: int
    majority_threshold: int
    government_seats: int
    government_coalitions: tuple[Coalition, ...]
    seats: tuple[ChamberSeat, ...]
    """All 222, ordered safest-Government first and safest-Opposition last."""
    ledger: tuple[LedgerRow, ...]
    status: ElectionStatus
    sources: tuple[str, ...]
    article_count: int
    state_signals: tuple[tuple[str, int], ...]
    """Each state that has voted since GE15, with how many Seats it moves."""

    @property
    def buffer(self) -> int:
        """Seats clear of a Majority. Negative means short of one."""
        return self.government_seats - self.majority_threshold

    @property
    def government_majority(self) -> bool:
        return self.government_seats >= self.majority_threshold

    @property
    def government_too_close(self) -> int:
        return sum(1 for s in self.seats if s.government and s.tier == TIGHT)

    @property
    def opposition_too_close(self) -> int:
        return sum(1 for s in self.seats if not s.government and s.tier == TIGHT)

    @property
    def if_every_marginal_fell(self) -> int:
        return self.government_seats - self.government_too_close

    @property
    def if_every_marginal_held(self) -> int:
        return self.government_seats + self.opposition_too_close

    @property
    def seats_that_must_move(self) -> int:
        """How many Government Seats would have to change hands to end the Majority.

        One more than the buffer: losing exactly the buffer leaves the
        threshold met, and the threshold is met at equality.
        """
        return max(0, self.buffer + 1)


def tier_for(margin: float) -> str:
    if margin < TIGHT_MARGIN:
        return TIGHT
    if margin < LIKELY_MARGIN:
        return LIKELY
    return SAFE


def page_model(
    projection: Projection,
    baseline: Sequence[SeatBaseline],
    status: ElectionStatus,
    config: SwingModelConfig,
    names: Mapping[Coalition, str],
    sources: Sequence[str],
    article_count: int,
    state_signal_states: Sequence[str],
    total_seats: int,
) -> PageModel:
    """Work out everything the page says, from one day's Projection.

    Raises `ValueError` on a Projection with no Seat Calls. The chamber is the
    page, and rendering 222 blanks would look like a result rather than like a
    Projection that has not been computed yet.
    """
    if not projection.seat_calls:
        raise ValueError(
            "Projection carries no Seat Calls — nothing to draw the chamber "
            "from. Run `python -m lpa.pipeline` to compute one."
        )

    by_code = {seat.code: seat for seat in baseline}
    seats = _ordered_seats(projection, by_code, config)
    return PageModel(
        computed_at=projection.computed_at,
        total_seats=total_seats,
        majority_threshold=config.majority_threshold,
        government_seats=government_seat_total(
            projection.coalition_seat_totals, config
        ),
        government_coalitions=tuple(sorted(config.government_coalitions)),
        seats=seats,
        ledger=_ledger(projection, baseline, config, names),
        status=status,
        sources=tuple(sources),
        article_count=article_count,
        state_signals=tuple(
            (state, sum(1 for s in baseline if s.state == state))
            for state in sorted(set(state_signal_states))
        ),
    )


def _ordered_seats(
    projection: Projection,
    by_code: Mapping[str, SeatBaseline],
    config: SwingModelConfig,
) -> tuple[ChamberSeat, ...]:
    """The chamber's left-to-right order: safest Government to safest Opposition.

    Sorted on margin across the whole Government side rather than bloc by bloc.
    The mockup grouped blocs first, which put a marginal BN Seat well to the
    left of a safe PH one and made the caption false; the axis the reader is
    told to read is how safe a Seat is, so that is what the axis is. Blocs stop
    being contiguous, which the colours carry anyway.

    The order matters beyond tidiness: the Majority line is drawn at the 112th
    seat, so the Government block only overruns it — the whole point of the
    image — if every Government Seat sits to the left of every other one.
    """
    seats = []
    for call in projection.seat_calls:
        seat = by_code.get(call.code)
        if seat is None:
            # A call for a Seat absent from the Baseline cannot be placed or
            # named. It should be impossible — the Swing Model derives its
            # calls from the Baseline — so this is a broken read, not a case
            # to paper over with a blank dot.
            raise ValueError(f"Seat Call {call.code!r} has no Baseline Seat")
        seats.append(
            ChamberSeat(
                code=call.code,
                name=seat.name,
                state=seat.state,
                coalition=call.coalition,
                margin=call.margin,
                tier=tier_for(call.margin),
                government=call.coalition in config.government_coalitions,
            )
        )
    government = sorted(
        (s for s in seats if s.government), key=lambda s: (-s.margin, s.code)
    )
    opposition = sorted(
        (s for s in seats if not s.government), key=lambda s: (s.margin, s.code)
    )
    return tuple(government + opposition)


def _ledger(
    projection: Projection,
    baseline: Sequence[SeatBaseline],
    config: SwingModelConfig,
    names: Mapping[Coalition, str],
) -> tuple[LedgerRow, ...]:
    """One row per Coalition holding something under either number.

    Coalitions on nothing at GE15 and nothing now are dropped: the Swing Model
    tallies every Coalition that stood anywhere, and a dozen 0-against-0 rows
    bury the ones a reader came for. Government Coalitions come first, each
    side strongest first, so the ledger reads in the same order as the chamber.
    """
    at_baseline: dict[Coalition, int] = {}
    for seat in baseline:
        at_baseline[seat.winner] = at_baseline.get(seat.winner, 0) + 1

    too_close: dict[Coalition, int] = {}
    for call in projection.seat_calls:
        if tier_for(call.margin) == TIGHT:
            too_close[call.coalition] = too_close.get(call.coalition, 0) + 1

    rows = [
        LedgerRow(
            coalition=coalition,
            name=names.get(coalition, coalition),
            projected=projection.coalition_seat_totals.get(coalition, 0),
            baseline=at_baseline.get(coalition, 0),
            too_close=too_close.get(coalition, 0),
            government=coalition in config.government_coalitions,
        )
        for coalition in set(projection.coalition_seat_totals) | set(at_baseline)
    ]
    live = [row for row in rows if row.projected or row.baseline]
    return tuple(
        sorted(live, key=lambda r: (not r.government, -r.projected, r.coalition))
    )


# ── the chamber's geometry ────────────────────────────────────────────────
#
# Ported from the mockup so the drawing is unchanged: ten arced rows between
# an inner and an outer radius, each row given seats in proportion to its
# length, then every slot sorted by angle so seat 1 is hard left and seat 222
# hard right.

CX, CY = 500.0, 496.0
R_INNER, R_OUTER = 196.0, 452.0
ROWS = 10
END_PAD = 0.055
"""Fraction of the half-circle left empty at each end, so the outermost seats
sit inside the frame rather than on it."""

BRACE_RADIUS = R_OUTER + 52
BRACE_LABEL_RADIUS = BRACE_RADIUS + 20

HEADROOM = 52
"""Space above the arc, in user units, for the buffer brace and its label.

The brace is drawn outside the outermost row, and when the Government block
ends near the top of the arc its label sits above the circle's centre by more
than the centre's own height — off the top of a viewBox that started at zero.
The mockup never hit this because its Government block ended further round.
"""


def _rows_for(total: int) -> int:
    """How many arced rows to draw. Fewer than `ROWS` only for a tiny chamber.

    Every row must hold at least one seat, so a chamber smaller than `ROWS`
    gets one row per seat. The real one has 222 and always uses all ten; this
    exists so the geometry is total-agnostic and the tests can work at a size
    a person can check by hand.
    """
    return max(1, min(ROWS, total))


def _row_counts(total: int) -> list[int]:
    """How many seats each row holds — longer rows hold more.

    Largest-remainder rather than rounding each row and pushing the drift
    around: rounding can leave a remainder that no row can absorb without
    emptying, and the loop that walked the rows looking for one that could
    never terminated when every row was already down to its last seat.
    """
    rows = _rows_for(total)
    if total <= rows:
        return [1] * total
    radii = _row_radii(rows)
    weight = sum(radii)
    # One seat per row first, so no row is ever empty, then the rest by length.
    spare = total - rows
    exact = [spare * radius / weight for radius in radii]
    counts = [1 + math.floor(e) for e in exact]
    for row in sorted(
        range(rows), key=lambda i: -(exact[i] - math.floor(exact[i]))
    )[: total - sum(counts)]:
        counts[row] += 1
    return counts


def _row_radii(rows: int) -> list[float]:
    if rows == 1:
        return [R_INNER]
    return [
        R_INNER + (R_OUTER - R_INNER) * (r / (rows - 1)) for r in range(rows)
    ]


def _slots(total: int) -> list[tuple[float, float]]:
    """Every seat position as (angle, radius), ordered left to right."""
    slots: list[tuple[float, float]] = []
    radii = _row_radii(_rows_for(total))
    for radius, count in zip(radii, _row_counts(total)):
        for i in range(count):
            t = 0.5 if count == 1 else i / (count - 1)
            angle = math.pi * (1 - END_PAD) - t * math.pi * (1 - 2 * END_PAD)
            slots.append((angle, radius))
    slots.sort(key=lambda s: -s[0])
    return slots


def _point(angle: float, radius: float) -> tuple[float, float]:
    return CX + math.cos(angle) * radius, CY - math.sin(angle) * radius


def _dot_radius(total: int) -> float:
    """Dot size, from the spacing between rows, capped so it stays a dot."""
    rows = _rows_for(total)
    gap = (R_OUTER - R_INNER) / (rows - 1) if rows > 1 else R_OUTER - R_INNER
    return min(gap * 0.34, 9.4)


# ── prose the numbers imply ───────────────────────────────────────────────


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _long_date(day: date) -> str:
    return f"{day.day} {day.strftime('%B %Y')}"


def _points(margin: float) -> str:
    """A vote-share margin as percentage points, which is how it is read."""
    return f"{margin * 100:.1f}"


def status_sentence(status: ElectionStatus) -> str:
    """The Election Status in a sentence, for all three states it can be in.

    Never guesses. `data/election_status.json` is maintained by hand and a
    dissolution with no polling day yet is a real state, not a half-filled
    record — so it gets its own sentence rather than being smoothed over.
    """
    if not status.called:
        return (
            "GE16 has not been called. The Dewan Rakyat is sitting, and the "
            f"election must be held by {_long_date(status.constitutional_deadline)} "
            "at the latest."
        )
    dissolved = _long_date(status.dissolved_on)  # type: ignore[arg-type]
    if status.polling_date is None:
        return (
            f"GE16 has been called — the Dewan Rakyat was dissolved on {dissolved}. "
            "The Election Commission has not yet announced a polling day."
        )
    return (
        f"GE16 has been called. The Dewan Rakyat was dissolved on {dissolved}, "
        f"and polling is on {_long_date(status.polling_date)}."
    )


def lede(model: PageModel) -> str:
    """The standfirst: the buffer, then what the close Seats do to it.

    Both sentences are arithmetic. The mockup's version named Johor and
    Malacca and a seat cost that no data supports — Malacca has not voted —
    so nothing here is written by hand about a particular contest.
    """
    clear = abs(model.buffer)
    if model.government_majority:
        first = (
            f"The Government Coalition is projected <b>{clear} "
            f"{_plural(clear, 'seat', 'seats')} clear</b> of a Majority."
            if clear
            else "The Government Coalition is projected <b>exactly to a Majority</b>."
        )
    else:
        first = (
            f"The Government Coalition is projected <b>{clear} "
            f"{_plural(clear, 'seat', 'seats')} short</b> of a Majority."
        )

    tight = model.government_too_close
    if not tight:
        return f"{first} Not one of the Seats it holds is inside six points."

    gap = model.if_every_marginal_fell - model.majority_threshold
    if gap > 0:
        outcome = f"would still hold a Majority, leaving it {gap} clear"
    elif gap == 0:
        outcome = "would leave it exactly at the line"
    else:
        outcome = f"would take it {-gap} below the line"
    return (
        f'{first} <span class="buffer">{tight}</span> of the Seats it holds '
        f'{_plural(tight, "is", "are")} inside six points; losing every one '
        f"{outcome}."
    )


# ── rendering ─────────────────────────────────────────────────────────────


def _swatch(coalition: Coalition) -> str:
    """A Coalition's ink, falling back for one the palette does not name.

    The Baseline gives a minor party with no bloc its own code as its
    Coalition, so new codes appear without warning. A neutral tone is the
    honest answer: inventing a sixth and seventh colour would imply the page
    knows something about them that it does not.
    """
    token = "".join(c for c in coalition.lower() if c.isalnum() or c == "-")
    return f"var(--{token}, var(--ink-soft))"


def _hemicycle(model: PageModel) -> str:
    """The chamber, as SVG computed here rather than drawn by a script."""
    total = len(model.seats)
    slots = _slots(total)
    dot = _dot_radius(total)
    parts: list[str] = []

    threshold = model.majority_threshold
    if 0 < threshold < total:
        t_angle = (slots[threshold - 1][0] + slots[threshold][0]) / 2
        ax, ay = _point(t_angle, R_INNER - 34)
        bx, by = _point(t_angle, R_OUTER + 26)
        parts.append(
            f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
            'class="thresh-line"/>'
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="3" class="thresh-cap"/>'
            f'<text x="{bx + 10:.1f}" y="{by + 4:.1f}" class="thresh-label">'
            f"{threshold} — majority</text>"
        )

        # The brace spans the Majority line to the Government block's edge, so
        # the buffer is a distance on the page rather than a number to read.
        edge = model.government_seats
        if 0 < edge < total and edge != threshold:
            e_angle = (slots[edge - 1][0] + slots[edge][0]) / 2
            bax, bay = _point(t_angle, BRACE_RADIUS)
            bbx, bby = _point(e_angle, BRACE_RADIUS)
            sweep = 1 if e_angle < t_angle else 0
            parts.append(
                f'<path class="buffer-brace" d="M{bax:.1f} {bay:.1f} '
                f"A {BRACE_RADIUS} {BRACE_RADIUS} 0 0 {sweep} "
                f'{bbx:.1f} {bby:.1f}"/>'
            )
            mx, my = _point((t_angle + e_angle) / 2, BRACE_LABEL_RADIUS)
            spare = abs(model.buffer)
            word = "to spare" if model.government_majority else "short"
            parts.append(
                f'<text x="{mx:.1f}" y="{my:.1f}" class="buffer-text" '
                f'text-anchor="middle">{spare} {_plural(spare, "seat", "seats")} '
                f"{word}</text>"
            )

    parts.append('<text x="6" y="534" class="side-label">Government</text>')
    parts.append(
        '<text x="994" y="534" class="side-label" text-anchor="end">'
        "Non-government</text>"
    )

    for seat, (angle, radius) in zip(model.seats, slots):
        x, y = _point(angle, radius)
        ink = _swatch(seat.coalition)
        if seat.tier == TIGHT:
            paint = f'fill="none" stroke="{ink}" stroke-width="1.9"'
        else:
            opacity = "1" if seat.tier == SAFE else "0.42"
            paint = f'fill="{ink}" fill-opacity="{opacity}"'
        close = " — too close to call" if seat.tier == TIGHT else ""
        tip = (
            f"{seat.name} ({seat.state}) — {seat.coalition} "
            f"by {_points(seat.margin)} points{close}"
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{dot:.1f}" class="seat-dot" '
            f"{paint}><title>{html.escape(tip)}</title></circle>"
        )

    held = "holds" if model.government_majority else "is projected"
    summary = (
        f"Hemicycle of {total} projected Dewan Rakyat Seats. The Government "
        f"Coalition {held} {model.government_seats}, against a "
        f"{threshold}-seat Majority."
    )
    return (
        f'<svg class="hemicycle" viewBox="0 {-HEADROOM} 1000 {560 + HEADROOM}" '
        f'role="img" aria-label="{html.escape(summary)}">{"".join(parts)}</svg>'
    )


def _swing_cell(swing: int) -> str:
    """A change against GE15, signed and coloured. A true zero is neither."""
    if swing > 0:
        return f'<td class="swing-pos">+{swing}</td>'
    if swing < 0:
        return f'<td class="swing-neg">−{abs(swing)}</td>'
    return '<td class="swing-nil">±0</td>'


def _ledger_row(row: LedgerRow) -> str:
    return (
        f'<tr style="--swatch: {_swatch(row.coalition)}">'
        f'<td><span class="party">{html.escape(row.name)} '
        f"<small>{html.escape(row.coalition)}</small></span></td>"
        f'<td class="seats-cell">{row.projected}</td>'
        f"<td>{row.baseline}</td>"
        f"{_swing_cell(row.swing)}"
        f"<td>{row.too_close}</td></tr>"
    )


def _ledger_table(model: PageModel) -> str:
    """The ledger, with the Government total ruled in under its members.

    `model.ledger` is already Government-first, so the total goes after that
    run rather than being sought by index.
    """
    government = [row for row in model.ledger if row.government]
    at_baseline = sum(row.baseline for row in government)
    total_row = (
        '<tr class="gov-row">'
        '<td><span class="party">Government total</span></td>'
        f'<td class="seats-cell">{model.government_seats}</td>'
        f"<td>{at_baseline}</td>"
        f"{_swing_cell(model.government_seats - at_baseline)}"
        f"<td>{model.government_too_close}</td></tr>"
    )
    body = (
        [_ledger_row(row) for row in government]
        + [total_row]
        + [_ledger_row(row) for row in model.ledger if not row.government]
    )
    return (
        "<table><thead><tr>"
        '<th scope="col">Coalition</th><th scope="col">Projected</th>'
        '<th scope="col">GE15</th><th scope="col">Swing</th>'
        '<th scope="col">Too close</th>'
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )


def _against_the_line(seats: int, threshold: int) -> str:
    """Where a hypothetical total leaves the Government against the Majority."""
    if seats > threshold:
        return f"still {seats - threshold} clear of the Majority line"
    if seats == threshold:
        return "exactly on the Majority line"
    return f"{threshold - seats} below the Majority line"


def _stress(model: PageModel) -> str:
    signals = (
        ", ".join(f"{state} ({seats})" for state, seats in model.state_signals)
        or "None yet"
    )
    moved = sum(seats for _, seats in model.state_signals)
    cells = [
        (
            "If every marginal fell",
            model.if_every_marginal_fell,
            f"All {model.government_too_close} Government Seats inside six "
            f"points lost, and {_against_the_line(model.if_every_marginal_fell, model.majority_threshold)}.",
        ),
        (
            "If every marginal held",
            model.if_every_marginal_held,
            f"The {model.opposition_too_close} Seats inside six points on the "
            "other side fall to the Government Coalition instead.",
        ),
        (
            "Seats that must move",
            model.seats_that_must_move,
            "Government Seats that would have to change hands before the "
            "Majority goes.",
        ),
        (
            "State swing, applied locally",
            moved,
            f"Seats moved by a state election result rather than by Sentiment "
            f"alone — {signals}. Every other state is untouched by it.",
        ),
    ]
    return "".join(
        f'<div class="cell"><dt>{html.escape(title)}</dt><dd>{value}</dd>'
        f"<p>{html.escape(note)}</p></div>"
        for title, value, note in cells
    )


_CSS = """
  :root {
    /* paper + ink — a green-grey stock, not cream */
    --ground:      #E9EAE4;
    --surface:     #F2F3EE;
    --ink:         #17191A;
    --ink-soft:    #55584F;
    /* #8A8D83 in the mockup: 2.79:1 on --ground, and it carries every
       eyebrow, label and key. Darkened to clear 4.5:1. */
    --ink-faint:   #6C6F66;
    --rule:        #C8CAC0;
    --rule-hair:   #D8DAD1;

    /* coalitions — printed inks, not screen neons */
    --ph:  #B23A2E;
    --bn:  #1D4E89;
    --pn:  #2B7A78;
    --gps: #8A6D1F;
    --grs: #6A4A7C;

    --serif: ui-serif, "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif;
    --sans:  ui-sans-serif, system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    --mono:  ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;

    --gutter: clamp(20px, 5vw, 72px);
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --ground:    #15161A;
      --surface:   #1C1E23;
      --ink:       #E7E8E2;
      --ink-soft:  #A6A9A0;
      --ink-faint: #8B8E85;
      --rule:      #33363C;
      --rule-hair: #26292E;
      --ph:  #E0705F;
      --bn:  #5D93D8;
      --pn:  #4FB3AF;
      --gps: #C9A542;
      --grs: #A886C2;
    }
  }

  :root[data-theme="dark"] {
    --ground:    #15161A;
    --surface:   #1C1E23;
    --ink:       #E7E8E2;
    --ink-soft:  #A6A9A0;
    --ink-faint: #8B8E85;
    --rule:      #33363C;
    --rule-hair: #26292E;
    --ph:  #E0705F;
    --bn:  #5D93D8;
    --pn:  #4FB3AF;
    --gps: #C9A542;
    --grs: #A886C2;
  }

  :root[data-theme="light"] {
    --ground:    #E9EAE4;
    --surface:   #F2F3EE;
    --ink:       #17191A;
    --ink-soft:  #55584F;
    --ink-faint: #6C6F66;
    --rule:      #C8CAC0;
    --rule-hair: #D8DAD1;
    --ph:  #B23A2E;
    --bn:  #1D4E89;
    --pn:  #2B7A78;
    --gps: #8A6D1F;
    --grs: #6A4A7C;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--ground);
    color: var(--ink);
    font-family: var(--sans);
    -webkit-font-smoothing: antialiased;
    position: relative;
  }

  /* faint press grain — sits above ground, below everything */
  body::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    opacity: .035;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E");
  }

  .sheet {
    position: relative;
    z-index: 1;
    max-width: 1180px;
    margin: 0 auto;
    padding: 0 var(--gutter) 96px;
  }

  .masthead {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px 32px;
    padding: 22px 0 14px;
    border-bottom: 2px solid var(--ink);
  }
  .wordmark { font-family: var(--serif); font-size: 15px; letter-spacing: .02em; }
  .wordmark em { font-style: normal; color: var(--ink-faint); }
  .stamp {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: .04em;
    color: var(--ink-soft);
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .theme-btn {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--ink-soft);
    background: none;
    border: 1px solid var(--rule);
    padding: 4px 9px;
    cursor: pointer;
  }
  .theme-btn:hover { color: var(--ink); border-color: var(--ink-faint); }
  .theme-btn:focus-visible { outline: 2px solid var(--pn); outline-offset: 2px; }

  .verdict {
    display: grid;
    grid-template-columns: minmax(0, auto) minmax(0, 1fr);
    gap: clamp(24px, 5vw, 64px);
    align-items: end;
    padding: clamp(36px, 6vw, 68px) 0 clamp(28px, 4vw, 44px);
    border-bottom: 1px solid var(--rule);
  }
  .tally { line-height: .82; }
  .tally-eyebrow {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: .18em;
    text-transform: uppercase;
    color: var(--ink-faint);
    margin-bottom: 18px;
    line-height: 1.4;
  }
  .tally-figure {
    font-family: var(--serif);
    font-size: clamp(84px, 15vw, 168px);
    letter-spacing: -.035em;
    font-variant-numeric: tabular-nums lining-nums;
    display: block;
  }
  .tally-of {
    font-family: var(--serif);
    font-size: clamp(17px, 2.4vw, 24px);
    color: var(--ink-faint);
    letter-spacing: -.01em;
    margin-top: 14px;
    display: block;
  }
  .lede {
    font-family: var(--serif);
    font-size: clamp(19px, 2.35vw, 29px);
    line-height: 1.36;
    letter-spacing: -.012em;
    text-wrap: balance;
    max-width: 24ch;
    padding-bottom: 6px;
    margin: 0;
  }
  .lede b {
    font-weight: inherit;
    box-shadow: inset 0 -.34em 0 color-mix(in srgb, var(--pn) 22%, transparent);
  }
  .lede .buffer { font-variant-numeric: tabular-nums; }

  .chamber { padding: clamp(30px, 5vw, 52px) 0 0; }
  .strip {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px 28px;
    margin-bottom: clamp(14px, 3vw, 26px);
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: .18em;
    text-transform: uppercase;
    color: var(--ink-faint);
  }
  .strip p {
    font-family: var(--serif);
    font-size: 14.5px;
    color: var(--ink-soft);
    max-width: 46ch;
    line-height: 1.5;
    margin: 0;
  }

  .hemicycle-wrap { overflow-x: auto; }
  svg.hemicycle { width: 100%; min-width: 460px; height: auto; display: block; }

  .seat-dot { transition: transform .18s ease; transform-box: fill-box; transform-origin: center; }
  .hemicycle:hover .seat-dot { opacity: .35; }
  .hemicycle .seat-dot:hover { opacity: 1; transform: scale(2.1); }

  .thresh-line { stroke: var(--ink); stroke-width: 1.6; stroke-dasharray: 3 3.5; }
  .thresh-cap  { fill: var(--ink); }
  .thresh-label { font-family: var(--mono); font-size: 12px; letter-spacing: .1em; fill: var(--ink); }
  .buffer-brace { stroke: var(--ink-faint); stroke-width: 1; fill: none; }
  .buffer-text { font-family: var(--mono); font-size: 11.5px; letter-spacing: .08em; fill: var(--ink-soft); }
  .side-label {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: .16em;
    fill: var(--ink-faint);
    text-transform: uppercase;
  }

  .key {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 26px;
    margin-top: 22px;
    padding-top: 16px;
    border-top: 1px solid var(--rule-hair);
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: .03em;
    color: var(--ink-soft);
  }
  .key span { display: inline-flex; align-items: center; gap: 7px; }
  .key i { width: 11px; height: 11px; border-radius: 50%; display: inline-block; background: var(--ink-soft); }
  .key i.mid { opacity: .48; }
  .key i.hollow { background: none; border: 1.6px solid var(--ink-soft); }

  .ledger { padding: clamp(46px, 7vw, 80px) 0 0; }
  .ledger-scroll { overflow-x: auto; }
  table {
    width: 100%;
    min-width: 540px;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums lining-nums;
  }
  thead th {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .14em;
    text-transform: uppercase;
    color: var(--ink-faint);
    font-weight: 400;
    text-align: right;
    padding: 0 0 11px;
    border-bottom: 1px solid var(--ink);
  }
  thead th:first-child { text-align: left; }
  tbody td {
    padding: 15px 0;
    border-bottom: 1px solid var(--rule-hair);
    text-align: right;
    font-family: var(--mono);
    font-size: 14px;
    color: var(--ink);
  }
  tbody td:first-child { text-align: left; }
  tbody tr:last-child td { border-bottom: 1px solid var(--ink); }

  .party {
    display: flex;
    align-items: baseline;
    gap: 11px;
    font-family: var(--serif);
    font-size: 17px;
    letter-spacing: -.01em;
  }
  .party::before {
    content: "";
    width: 9px; height: 9px;
    flex: 0 0 9px;
    border-radius: 50%;
    background: var(--swatch);
    transform: translateY(-1px);
  }
  .party small {
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: .06em;
    color: var(--ink-faint);
  }
  .seats-cell { font-size: 20px; }
  .swing-pos { color: var(--pn); }
  .swing-neg { color: var(--ph); }
  .swing-nil { color: var(--ink-faint); }
  .gov-row td { background: color-mix(in srgb, var(--ink) 4%, transparent); font-weight: 600; }
  .gov-row .party { font-weight: 600; }
  .gov-row .party::before { background: none; }

  .stress {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 1px;
    margin: clamp(46px, 7vw, 78px) 0 0;
    background: var(--rule-hair);
    border: 1px solid var(--rule-hair);
  }
  .cell { background: var(--ground); padding: 24px 22px 26px; }
  .cell dt {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .15em;
    text-transform: uppercase;
    color: var(--ink-faint);
    margin-bottom: 14px;
  }
  .cell dd {
    font-family: var(--serif);
    font-size: 42px;
    letter-spacing: -.03em;
    font-variant-numeric: tabular-nums;
    line-height: 1;
    margin: 0 0 11px;
  }
  .cell p { font-family: var(--serif); font-size: 13.5px; line-height: 1.5; color: var(--ink-soft); margin: 0; }

  .colophon {
    margin-top: clamp(52px, 8vw, 90px);
    padding-top: 22px;
    border-top: 2px solid var(--ink);
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 30px 44px;
  }
  .colophon h3 {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .15em;
    text-transform: uppercase;
    color: var(--ink-faint);
    font-weight: 400;
    margin: 0 0 10px;
  }
  .colophon p { font-family: var(--serif); font-size: 13.5px; line-height: 1.55; color: var(--ink-soft); margin: 0; }
  .caveat { border-left: 2px solid var(--ph); padding-left: 14px; }
  .caveat p { color: var(--ink); }

  @media (max-width: 720px) {
    .verdict { grid-template-columns: 1fr; align-items: start; gap: 22px; }
    .lede { max-width: none; }
  }

  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
  }
"""

_THEME_SCRIPT = """
(function () {
  var btn = document.getElementById("themeBtn");
  function dark() {
    var set = document.documentElement.getAttribute("data-theme");
    return set ? set === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function label() { btn.textContent = dark() ? "Light" : "Dark"; }
  btn.addEventListener("click", function () {
    document.documentElement.setAttribute("data-theme", dark() ? "light" : "dark");
    label();
  });
  label();
})();
"""


def render_html(model: PageModel) -> str:
    """The whole page as one self-contained document.

    Decides nothing. Every figure here comes from `model`, so a claim on the
    page can be traced to the arithmetic that produced it — and the only
    script is the theme toggle, which the page reads correctly without.
    """
    read_from = " · ".join(html.escape(s) for s in model.sources) or "No outlets read"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GE16 Projection — the Dewan Rakyat, projected</title>
<meta name="description" content="{html.escape(
    f'Projection of the {model.total_seats} Seats of the Dewan Rakyat at GE16, '
    f'computed {_long_date(model.computed_at)}. Model-driven and not calibrated.'
)}">
<style>{_CSS}</style>
</head>
<body>
<div class="sheet">

  <header class="masthead">
    <div class="wordmark">Live Political Analysis <em>— Projeksi Kerusi GE16</em></div>
    <div class="stamp">
      <span>MODEL RUN {model.computed_at.strftime('%d %b %Y').upper()}</span>
      <button class="theme-btn" id="themeBtn" type="button">Dark</button>
    </div>
  </header>

  <section class="verdict">
    <div class="tally">
      <div class="tally-eyebrow">Government coalition<br>{' · '.join(
          html.escape(c) for c in model.government_coalitions)}</div>
      <span class="tally-figure">{model.government_seats}</span>
      <span class="tally-of">of {model.total_seats} seats — {model.majority_threshold} needed</span>
    </div>
    <p class="lede">{lede(model)}</p>
  </section>

  <section class="chamber">
    <div class="strip">
      <div class="eyebrow">The Dewan Rakyat, projected</div>
      <p>
        Seats run safest-government at the left to safest-opposition at the right.
        Hollow rings are seats inside six points — too close to call. Each is where
        a uniform swing puts that seat against its GE15 result, not a judgement
        about the constituency.
      </p>
    </div>

    <div class="hemicycle-wrap">{_hemicycle(model)}</div>

    <div class="key">
      <span><i></i> Safe — over 12 points</span>
      <span><i class="mid"></i> Likely — 6 to 12 points</span>
      <span><i class="hollow"></i> Too close — under 6 points</span>
    </div>
  </section>

  <section class="ledger">
    <div class="strip"><div class="eyebrow">Seat ledger — against the GE15 baseline</div></div>
    <div class="ledger-scroll">{_ledger_table(model)}</div>
    <dl class="stress">{_stress(model)}</dl>
  </section>

  <footer class="colophon">
    <div>
      <h3>Method</h3>
      <p>A swing from each seat's GE15 result, moved by daily news sentiment and
      blended, state by state, with any state election held since. The swing is
      uniform within a state, so a seat's call is arithmetic against GE15.</p>
    </div>
    <div>
      <h3>Read from</h3>
      <p>{read_from}. {model.article_count} articles in the latest run,
      sanity-checked against Merdeka Center survey reports.</p>
    </div>
    <div>
      <h3>Election status</h3>
      <p>{html.escape(status_sentence(model.status))}</p>
    </div>
    <div class="caveat">
      <h3>Not calibrated</h3>
      <p>Two constants in the swing model were set by judgement, not fitted to
      data. Treat every figure here as a direction, not a forecast.</p>
    </div>
  </footer>
</div>
<script>{_THEME_SCRIPT}</script>
</body>
</html>
"""


def build_page(engine) -> str:
    """Read Storage and render the page. The whole I/O half, in one place.

    Separate from `main` so the preview server in `scripts/` can render
    exactly what the Action publishes, rather than a second wiring of the
    same parts that can drift from it.
    """
    from lpa.config import (
        coalition_names,
        load_coalition_config,
        load_election_status,
        load_state_election_signals,
        swing_model_config,
    )
    from lpa.storage import (
        load_projections,
        load_seat_baselines,
        load_sentiment_snapshots,
    )

    projections = load_projections(engine)
    if not projections:
        raise SystemExit(
            "No Projection stored. Run `python -m lpa.pipeline` to compute one."
        )
    baseline = load_seat_baselines(engine)
    if not baseline:
        raise SystemExit(
            "No Seat Baseline in Storage. Run `python -m lpa.baseline_loader` first."
        )

    config = load_coalition_config()
    snapshots = load_sentiment_snapshots(engine)
    latest = snapshots[-1].sentiment if snapshots else None
    model = page_model(
        projection=projections[-1],
        baseline=baseline,
        status=load_election_status(),
        config=swing_model_config(config),
        names=coalition_names(config),
        # What was actually read on the latest run, not the outlets the
        # Scraper was pointed at: an outlet that answered 500 or was refused
        # by robots.txt did not contribute and must not be credited (#16).
        sources=latest.sources if latest else (),
        article_count=latest.total_articles if latest else 0,
        state_signal_states=[s.state for s in load_state_election_signals()],
        total_seats=config["total_seats"],
    )
    return render_html(model)


def main() -> None:
    """Render the public page from Storage and write it to disk."""
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public/index.html"),
        help="where to write the page (default: public/index.html)",
    )
    args = parser.parse_args()

    page = build_page(connect())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(f"Wrote {args.output} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
