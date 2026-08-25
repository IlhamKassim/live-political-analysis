"""PolitikKu's seat-projection detail page (#102) — and the methodology page
the rest of the site has been linking at since #72.

ADR 0011 is the reasoning: PolitikKu becomes the site, and the original
dashboard's analytical depth (`public_page.py`) is not dropped with it. That
depth serves `CONTEXT.md`'s **Engaged Reader**, who PolitikKu's own
homepage/landing pages — built for the **Audience** — have no equivalent for.
So it moves here, into PolitikKu's visual register, as one linked detail page
at `/projection/` (`politikku_shell.PROJECTION_PREFIX`), plus the full
methodology/colophon at `/politikku/methodology.html`
(`politikku_shell.METHODOLOGY_PAGE`).

**Two pages, not one.** The ported colophon (Method, Read from, Election
status, Not calibrated, Cite this) is what the header nav's "Methodology"
item, the trust strip's "How this works" and the footer's "Read the full
methodology →" have always meant — links that appear on *every* PolitikKu
page, the Audience-facing homepage and landing included. Landing an Audience
reader who clicked "how this works" halfway down a 222-row projection table
would be against the exact reader split ADR 0011 rests on, so the colophon
gets its own page and `/projection/` links to it. The provenance block
itself (#55's dated permalink) appears on both: it is a claim about the model
run, and both pages state figures from that run.

**No new arithmetic.** `public_page.page_model()` already computes every
number both pages state, so this module reads that same `PageModel` rather
than deriving a second, disagreeing copy of the ledger, the trend, the
sensitivity table or the rollup — the same seam `politikku_landing`/
`politikku_mp_profile` take against it. Several of `public_page`'s own
private helpers are imported directly for the same reason: `_trend_marks`
(the plot's geometry), `_search_blob` (the filter's index), `_long_date`/
`_points`/`_tier_label`/`_coalition_counts`/`_coalition_swings` (formatting
whose BM half was settled in #43) and `_permalink_path` (which must name the
same path `main` writes). Copying them here would be two places for one
answer to drift.

**What is redrawn rather than ported.** The markup and CSS are new. The old
page's register is print — hairline rules, printed party inks, a paper
grain, a light/dark toggle, no cards (`docs/design/HANDOFF.md`) — and
PolitikKu's is not: `paper`/`paper-alt` bands at a fixed gutter, rounded
`--radius-lg` cards on `--white`, mono uppercase micro-labels, one accent,
and, explicitly, *no party colours at all* (`politikku_shell`'s own
docstring). So:

- Every table uses the one table idiom `politikku_homepage`'s sentiment
  table already established (white card, `--line` border, mono uppercase
  headers, `--line-soft` row rules) rather than six new ones.
- `public_page._swatch`'s per-Coalition inks (`--ph`/`--bn`/`--pn`/…) do not
  come across. Rows are marked Government/Non-government with
  `--data-government`/`--data-nongovernment`, the axis
  `politikku_mp_profile._projection_bar` already uses for the same reason.
- The theme toggle and the whole `prefers-color-scheme`/`data-theme` block
  are dropped: the shell has no dark mode, so a theme button here would be a
  control belonging to a different site.
- The chamber is `politikku_hemicycle.render_hemicycle` (#73), PolitikKu's
  own component, not the old page's 222-dot SVG — which means the seat
  filter no longer dims chamber dots (they are aggregate bands here, not
  per-Seat marks). In exchange the full seat table is *visible* rather than
  `visually-hidden`: on the old page it was the keyboard-reachable shadow of
  the hemicycle, and on a page whose whole reason for existing is per-Seat
  depth it is the main event.

**BM copy is reused, never retranslated** (#43/#81): `Language`/`t()` come
from `politikku_shell`, shared vocabulary from `politikku_i18n`, and every
sentence ported from `public_page.py` carries that module's own settled BM
wording verbatim — including the caveats ADR 0005 requires (the tipping
point's "a position in a sort, not a claim about this Seat", the
sensitivity table's "not a range of likely outcomes"), which a fresh
translation could quietly soften.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from datetime import date

from sqlalchemy.engine import Engine

from lpa.domain import Coalition
from lpa.politikku_hemicycle import Palette, render_hemicycle
from lpa.politikku_homepage import hemicycle_counts
from lpa.politikku_i18n import (
    GE16_SEAT_PROJECTION_EN,
    GE16_SEAT_PROJECTION_MS,
    GOVERNMENT_CLEAR_EN,
    GOVERNMENT_CLEAR_MS,
    GOVERNMENT_COALITION_EN,
    GOVERNMENT_COALITION_MS,
    MAJORITY_EN,
    MAJORITY_MS,
    NONGOVERNMENT_CLEAR_EN,
    NONGOVERNMENT_CLEAR_MS,
    WITHIN_MODEL_NOISE_EN,
    WITHIN_MODEL_NOISE_MS,
    not_calibrated_tag,
)
from lpa.politikku_shell import (
    METHODOLOGY_PAGE,
    PROJECTION_PREFIX,
    Language,
    methodology_url,
    projection_url,
    render_shell,
    t,
)
from lpa.public_page import (
    MIN_TREND_READINGS,
    SITE_URL,
    TREND_PAD_Y,
    TREND_VIEW_H,
    TREND_VIEW_W,
    LedgerRow,
    PageModel,
    _against_the_line,
    _coalition_counts,
    _coalition_swings,
    _long_date,
    _permalink_path,
    _plural,
    _points,
    _search_blob,
    _tier_label,
    _trend_marks,
    format_signed,
    lede,
    status_sentence,
)

PROJECTION_PAGE = "index.html"
"""`/projection/` is a directory route, so its file is an `index.html` —
the same shape `politikku_homepage` uses for `/politikku/`. This is the
*filename* `main` writes, and only that: the page's own `page_path` (which
drives the EN/BM toggle) is `""`, the directory route itself, exactly as
`politikku_homepage.render_homepage` passes `""` for `/politikku/`. Spelling
the file name into the toggle instead would give one page two canonical
URLs — `projection_url()` and the header nav both say `/projection/`, and a
toggle saying `/projection/index.html` would quietly disagree with them."""


def _permalink_url(model: PageModel, language: Language) -> str:
    """The dated copy of this exact run (#55), as an absolute URL.

    Under `PROJECTION_PREFIX`, not the site root: `public_page._cite_this`
    builds `SITE_URL + permalink` because its own dated copies are written
    beside `public/index.html`. This page's are written beside
    `public/projection/index.html`, and a citation link that 404s is worse
    than no citation link at all — the permalink is the trust mechanism, not
    decoration.

    Stays in the page's own language, for `_cite_this`'s own reason: the two
    translations are not guaranteed to read identically forever, so a BM
    page citing the EN dated copy would be a claim-changing defect.
    """
    prefix = PROJECTION_PREFIX.strip("/")
    ms = "" if language is Language.EN else "ms/"
    return f"{SITE_URL}{prefix}/{ms}{_permalink_path(model.computed_at)}"


def _coalition_names(model: PageModel) -> Mapping[Coalition, str]:
    """Coalition code → full name, off the ledger the model already carries
    — the same read `public_page._seat_table` makes for `_search_blob`."""
    return {row.coalition: row.name for row in model.ledger}


# ── shared page furniture ─────────────────────────────────────────────────


def _band(css_class: str, inner: str, *, alt: bool = False) -> str:
    """One full-bleed section, in the alternating `paper`/`paper-alt` rhythm
    the homepage and landing page already read in."""
    alt_class = " pk-proj-band-alt" if alt else ""
    return f'<section class="pk-proj-band{alt_class} {css_class}">{inner}</section>'


def _section_head(eyebrow: str, heading: str, note: str = "") -> str:
    note_html = f'<p class="pk-proj-note">{note}</p>' if note else ""
    return (
        f'<div class="pk-proj-section-head"><div class="pk-eyebrow">{eyebrow}</div>'
        f"<h2>{heading}</h2></div>{note_html}"
    )


def _table(headers: tuple[str, ...], rows: str, caption: str = "") -> str:
    """The one table idiom every ported table uses — `politikku_homepage`'s
    sentiment table, generalised. A white card with a `--line` border, mono
    uppercase headers, `--line-soft` row rules, and its own horizontal
    scroll so a wide table narrows without pushing the page sideways
    (HANDOFF defect 4's concern, answered the way PolitikKu already answers
    it rather than by re-deriving the old page's own answer)."""
    caption_html = f"<caption>{caption}</caption>" if caption else ""
    head = "".join(f'<th scope="col">{h}</th>' for h in headers)
    return (
        '<div class="pk-proj-table-wrap"><table class="pk-proj-table">'
        f"{caption_html}<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>"
    )


def _side_dot(government: bool) -> str:
    """Government / Non-government, as the page's one certainty-free colour
    axis. PolitikKu carries no party colours (`politikku_shell`), so the old
    page's per-Coalition ink does not travel with the ledger it belonged to.
    """
    cls = "pk-proj-dot-gov" if government else "pk-proj-dot-nongov"
    return f'<span class="pk-proj-dot {cls}"></span>'


def _swing_text(swing: int) -> tuple[str, str]:
    """A change against GE15, signed — CSS class and text together, the same
    pairing `public_page._swing_value` makes so the wide table and the
    narrow stack cannot state a different swing for one Coalition. The class
    names are PolitikKu's (`--accent` up, `--caution-deep` down, the same
    two the homepage's sentiment deltas already use), not the old page's
    `--ink-pos`/`--ink-neg` printed inks."""
    cls = "pk-proj-up" if swing > 0 else "pk-proj-down" if swing < 0 else "pk-proj-flat"
    return cls, format_signed(swing)


# ── the projection page's own sections ────────────────────────────────────


def _hero(model: PageModel, language: Language) -> str:
    """Headline tally, the chamber, and the standfirst.

    `lede()` is `public_page`'s own, reused rather than reworded — it is
    arithmetic in a sentence, and #43 already settled both languages of it.
    """
    eyebrow = t(language, GE16_SEAT_PROJECTION_EN, GE16_SEAT_PROJECTION_MS).upper()
    of_word = t(language, "of", "daripada")
    to_government = t(
        language,
        f"of {model.total_seats} to the {GOVERNMENT_COALITION_EN}",
        f"daripada {model.total_seats} kepada {GOVERNMENT_COALITION_MS}",
    )
    majority_label = t(
        language,
        f"{MAJORITY_EN} {model.majority_threshold}",
        f"{MAJORITY_MS} {model.majority_threshold}",
    ).upper()
    seats_word = t(language, "seats", "kerusi")
    stats = (
        (
            t(language, "Margin over majority", "Lebihan berbanding majoriti"),
            f"{format_signed(model.buffer)} {seats_word}",
        ),
        (
            t(language, "Seats too close", "Kerusi terlalu rapat"),
            f"{len(model.too_close_seats)} {of_word} {model.total_seats}",
        ),
        (
            t(language, "Seats that must move", "Kerusi yang perlu berpindah"),
            f"{model.seats_that_must_move}",
        ),
        (
            t(language, "Model runs stored", "Larian model disimpan"),
            f"{len(model.trend)}",
        ),
    )
    stat_html = "".join(
        f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>"
        for label, value in stats
    )
    legend = (
        (
            "pk-proj-swatch-gov",
            t(language, GOVERNMENT_CLEAR_EN, GOVERNMENT_CLEAR_MS),
        ),
        (
            "pk-proj-swatch-noise",
            t(language, WITHIN_MODEL_NOISE_EN, WITHIN_MODEL_NOISE_MS),
        ),
        (
            "pk-proj-swatch-nongov",
            t(language, NONGOVERNMENT_CLEAR_EN, NONGOVERNMENT_CLEAR_MS),
        ),
    )
    legend_html = "".join(
        f'<li><span class="pk-proj-swatch {cls}"></span>{html.escape(label)}</li>'
        for cls, label in legend
    )
    chamber = render_hemicycle(
        hemicycle_counts(model), palette=Palette.LIGHT, majority_label=majority_label
    )
    return _band(
        "pk-proj-hero",
        f"""
  <div class="pk-proj-hero-prose">
    <div class="pk-eyebrow">{eyebrow}</div>
    <div class="pk-proj-headline">
      <span class="pk-proj-headline-number">{model.government_seats} {of_word} {model.total_seats}</span>
      <span class="pk-proj-headline-unit">{to_government}</span>
      {not_calibrated_tag(language)}
    </div>
    <p class="pk-proj-lede">{lede(model, language)}</p>
    <dl class="pk-proj-stats">{stat_html}</dl>
  </div>
  <div class="pk-proj-hero-chart">
    {chamber}
    <ul class="pk-proj-legend">{legend_html}</ul>
  </div>
""",
        alt=True,
    )


def _tipping_point(model: PageModel, language: Language) -> str:
    """Where the count crosses the Majority line today (#50).

    Both sentences are `public_page._tipping_point`'s verbatim — including
    the caveat, which ADR 0005 makes load-bearing rather than decorative:
    without it the line reads as a bellwether claim about a named
    constituency, which is precisely what this project does not make.
    """
    seat = model.threshold_seat
    swing = model.threshold_swing
    if seat is None or swing is None:
        return ""
    name = html.escape(seat.name)
    state = html.escape(seat.state)
    points = _points(swing)
    body = t(
        language,
        f"Today, the count crosses {model.majority_threshold} at "
        f"<b>{name}</b> ({state}). A uniform swing of "
        f"<b>{points} points</b> would move the Majority line to "
        "the other side of it.",
        f"Pada hari ini, kiraan melepasi {model.majority_threshold} di "
        f"<b>{name}</b> ({state}). Peralihan seragam sebanyak "
        f"<b>{points} mata</b> akan menggerakkan garis majoriti ke "
        "sebelah lain kerusi ini.",
    )
    caveat = t(
        language,
        f"This states a position in a sort, not a claim about {name} itself "
        "— the same arithmetic applied to any Seat at this position in the "
        "ordering.",
        f"Ini menyatakan kedudukan dalam satu susunan, bukan dakwaan tentang "
        f"{name} itu sendiri — pengiraan yang sama terpakai kepada mana-mana "
        "Kerusi pada kedudukan ini dalam susunan tersebut.",
    )
    eyebrow = t(language, "Tipping point", "Titik penentu")
    return (
        '<div class="pk-proj-card pk-proj-tipping">'
        f'<div class="pk-eyebrow">{eyebrow}</div>'
        f'<p class="pk-proj-tipping-body">{body}</p>'
        f'<p class="pk-proj-caveat">{caveat}</p>'
        "</div>"
    )


def _stress(model: PageModel, language: Language) -> str:
    """The four what-if cells (`public_page._stress`), as PolitikKu cards.

    Every sentence is that function's own, both languages — the arithmetic
    behind them is `PageModel`'s, unchanged.
    """
    signals = ", ".join(f"{state} ({seats})" for state, seats in model.state_signals) or t(
        language, "None yet", "Belum ada"
    )
    cells = (
        (
            t(language, "If every marginal fell", "Jika setiap kerusi genting tumbang"),
            model.if_every_marginal_fell,
            t(
                language,
                f"All {model.government_too_close} Government Seats inside six "
                "points lost, and "
                f"{_against_the_line(model.if_every_marginal_fell, model.majority_threshold)}.",
                f"Kesemua {model.government_too_close} Kerusi Kerajaan dalam lingkungan enam "
                "mata tewas, dan "
                f"{_against_the_line(model.if_every_marginal_fell, model.majority_threshold, Language.MS)}.",
            ),
        ),
        (
            t(language, "If every marginal held", "Jika setiap kerusi genting bertahan"),
            model.if_every_marginal_held,
            t(
                language,
                f"The {model.opposition_too_close} Seats inside six points on the "
                "other side fall to the Government Coalition instead.",
                f"{model.opposition_too_close} Kerusi dalam lingkungan enam mata di pihak "
                "sebelah pula jatuh kepada Gabungan Kerajaan.",
            ),
        ),
        (
            t(language, "Seats that must move", "Kerusi yang perlu berpindah"),
            model.seats_that_must_move,
            t(
                language,
                "Government Seats that would have to change hands before the Majority goes.",
                "Kerusi Kerajaan yang perlu bertukar tangan sebelum majoriti hilang.",
            ),
        ),
        (
            t(
                language,
                "State swing, applied locally",
                "Peralihan negeri, digunakan secara setempat",
            ),
            model.state_signal_seats,
            t(
                language,
                "Seats moved by a state election result rather than by Sentiment "
                f"alone — {signals}. Every other state is untouched by it.",
                "Kerusi yang beralih akibat keputusan pilihan raya negeri, bukan Sentimen "
                f"semata-mata — {signals}. Setiap negeri lain tidak terjejas olehnya.",
            ),
        ),
    )
    return "".join(
        f'<div class="pk-proj-card pk-proj-stress-cell">'
        f'<dt class="pk-eyebrow">{html.escape(title)}</dt>'
        f"<dd>{value}</dd><p>{html.escape(note)}</p></div>"
        for title, value, note in cells
    )


def _ledger_row(row: LedgerRow) -> str:
    cls, swing_text = _swing_text(row.swing)
    return (
        "<tr>"
        f'<td><span class="pk-proj-coalition">{_side_dot(row.government)}'
        f"{html.escape(row.name)} <small>{html.escape(row.coalition)}</small></span></td>"
        f'<td class="pk-proj-figure">{row.projected}</td>'
        f"<td>{row.baseline}</td>"
        f'<td class="{cls}">{swing_text}</td>'
        f"<td>{row.too_close}</td></tr>"
    )


def _ledger_stack_row(row: LedgerRow, language: Language) -> str:
    cls, swing_text = _swing_text(row.swing)
    ge15_h = t(language, "GE15", "PRU15")
    swing_h = t(language, "Swing", "Peralihan")
    too_close_h = t(language, "Too close", "Terlalu rapat")
    return (
        '<div class="pk-proj-stack-row">'
        f'<div class="pk-proj-stack-head"><span class="pk-proj-coalition">'
        f"{_side_dot(row.government)}{html.escape(row.name)} "
        f"<small>{html.escape(row.coalition)}</small></span>"
        f'<span class="pk-proj-figure">{row.projected}</span></div>'
        '<dl class="pk-proj-stack-stats">'
        f"<div><dt>{ge15_h}</dt><dd>{row.baseline}</dd></div>"
        f'<div><dt>{swing_h}</dt><dd class="{cls}">{swing_text}</dd></div>'
        f"<div><dt>{too_close_h}</dt><dd>{row.too_close}</dd></div>"
        "</dl></div>"
    )


_GOV_TOTAL_GE15_NOTE_EN = (
    "The Government Coalition formed after GE15, by agreement. It had no GE15 total."
)
_GOV_TOTAL_GE15_NOTE_MS = (
    "Gabungan Kerajaan terbentuk selepas PRU15, melalui persetujuan. Ia tiada jumlah PRU15."
)
"""`public_page._GOV_TOTAL_GE15_NOTE`/`_MS` verbatim — the reason the ledger's
Government-total row states no GE15 figure and no Swing against one, which is
a category point rather than a missing number."""


def _ledger_section(model: PageModel, language: Language) -> str:
    """The seat ledger, wide and stacked (`_ledger_table`/`_ledger_narrow`).

    Both layouts are rendered and exactly one is shown per breakpoint — the
    same answer HANDOFF defect 4 reached for the old page, since a Coalition
    row read sideways is a Coalition row a phone reader does not read.
    """
    government = [row for row in model.ledger if row.government]
    non_government = [row for row in model.ledger if not row.government]
    gov_total_label = t(language, "Government total", "Jumlah Kerajaan")
    note = html.escape(t(language, _GOV_TOTAL_GE15_NOTE_EN, _GOV_TOTAL_GE15_NOTE_MS))
    ge15_h = t(language, "GE15", "PRU15")
    swing_h = t(language, "Swing", "Peralihan")
    too_close_h = t(language, "Too close", "Terlalu rapat")
    coalition_h = t(language, "Coalition", "Gabungan")
    projected_h = t(language, "Projected", "Diunjurkan")

    total_row = (
        '<tr class="pk-proj-total-row">'
        f'<td><span class="pk-proj-coalition">{gov_total_label}</span></td>'
        f'<td class="pk-proj-figure">{model.government_seats}</td>'
        f'<td class="pk-proj-na" title="{note}">—</td>'
        '<td class="pk-proj-na">—</td>'
        f"<td>{model.government_too_close}</td></tr>"
    )
    rows = (
        "".join(_ledger_row(row) for row in government)
        + total_row
        + "".join(_ledger_row(row) for row in non_government)
    )
    stack_total = (
        '<div class="pk-proj-stack-row pk-proj-total-row">'
        f'<div class="pk-proj-stack-head"><span class="pk-proj-coalition">{gov_total_label}</span>'
        f'<span class="pk-proj-figure">{model.government_seats}</span></div>'
        '<dl class="pk-proj-stack-stats">'
        f'<div><dt>{ge15_h}</dt><dd class="pk-proj-na" title="{note}">—</dd></div>'
        f'<div><dt>{swing_h}</dt><dd class="pk-proj-na">—</dd></div>'
        f"<div><dt>{too_close_h}</dt><dd>{model.government_too_close}</dd></div>"
        "</dl></div>"
    )
    stack = (
        '<div class="pk-proj-ledger-narrow">'
        + "".join(_ledger_stack_row(row, language) for row in government)
        + stack_total
        + "".join(_ledger_stack_row(row, language) for row in non_government)
        + "</div>"
    )
    head = _section_head(
        t(language, "Seat ledger", "Lejar Kerusi"),
        t(language, "Against the GE15 Baseline", "Berbanding Asas PRU15"),
        t(
            language,
            "Government Coalitions first, each side strongest first — the same order "
            "the chamber above reads in.",
            "Gabungan Kerajaan dahulu, setiap pihak yang terkuat dahulu — susunan yang "
            "sama seperti dewan di atas.",
        ),
    )
    wide = _table((coalition_h, projected_h, ge15_h, swing_h, too_close_h), rows)
    return _band(
        "pk-proj-ledger",
        f'{head}<div class="pk-proj-ledger-wide">{wide}</div>{stack}',
    )


def _stress_section(model: PageModel, language: Language) -> str:
    head = _section_head(
        t(language, "Stress test", "Ujian tekanan"),
        t(language, "What the close Seats could do", "Apa yang boleh dilakukan Kerusi rapat"),
    )
    return _band(
        "pk-proj-stress",
        f'{head}<dl class="pk-proj-stress-grid">{_stress(model, language)}</dl>',
        alt=True,
    )


def _trend_plot(model: PageModel, language: Language) -> str:
    """The Majority-margin plot (#45), redrawn.

    Geometry is `public_page._trend_marks` — the horizontal axis is the
    *date*, not the reading's index, which is the whole difference between a
    plot that can be read honestly and one that cannot. What changes here is
    only ink: `--ink` marks and a `--line-strong` dashed Majority rule
    instead of the old page's hairlines. Still straight segments, still only
    between consecutive days, still no fill and no colour sorting movement
    into good and bad (ADR 0003 — the constants are not fitted, so the page
    has no business implying which direction is the real one).
    """
    low, high = model.trend_span
    marks = _trend_marks(model)
    span = high - low
    zero_y = TREND_PAD_Y + (1 - (0 - low) / span) * (TREND_VIEW_H - 2 * TREND_PAD_Y)
    parts = [
        (
            f'<line class="pk-proj-trend-majority" x1="0" y1="{zero_y:.1f}" '
            f'x2="{TREND_VIEW_W:.0f}" y2="{zero_y:.1f}"/>'
        )
    ]
    if model.trend_is_joined:
        for i in range(1, len(model.trend)):
            if (model.trend[i].day - model.trend[i - 1].day).days != 1:
                continue
            (x1, y1), (x2, y2) = marks[i - 1], marks[i]
            parts.append(
                f'<line class="pk-proj-trend-step" x1="{x1:.1f}" y1="{y1:.1f}" '
                f'x2="{x2:.1f}" y2="{y2:.1f}"/>'
            )
    for reading, (x, y) in zip(model.trend, marks):
        title = t(
            language,
            f"{_long_date(reading.day)} — {format_signed(reading.margin)} against the Majority line",
            f"{_long_date(reading.day, Language.MS)} — {format_signed(reading.margin)} "
            "berbanding garis majoriti",
        )
        parts.append(
            f'<circle class="pk-proj-trend-mark" cx="{x:.1f}" cy="{y:.1f}" r="4">'
            f"<title>{html.escape(title)}</title></circle>"
        )
    joined = t(
        language,
        "joined where the runs are on consecutive days"
        if model.trend_is_joined
        else "plotted as separate marks, not joined up",
        "disambungkan apabila larian berlaku pada hari berturutan"
        if model.trend_is_joined
        else "diplot sebagai tanda berasingan, tidak disambungkan",
    )
    date_first = _long_date(model.trend[0].day, language)
    date_last = _long_date(model.trend[-1].day, language)
    summary = t(
        language,
        f"{len(model.trend)} daily model runs, {_long_date(model.trend[0].day)} to "
        f"{_long_date(model.trend[-1].day)}, {joined}. The Government Coalition's "
        f"margin over the {model.majority_threshold}-seat Majority runs from "
        f"{format_signed(min(r.margin for r in model.trend))} to "
        f"{format_signed(max(r.margin for r in model.trend))} across them. "
        "Every reading is also in the table below.",
        f"{len(model.trend)} larian model harian, {_long_date(model.trend[0].day, Language.MS)} "
        f"hingga {_long_date(model.trend[-1].day, Language.MS)}, {joined}. Majoriti Gabungan "
        f"Kerajaan berbanding ambang {model.majority_threshold} kerusi berjulat daripada "
        f"{format_signed(min(r.margin for r in model.trend))} hingga "
        f"{format_signed(max(r.margin for r in model.trend))} sepanjang tempoh ini. "
        "Setiap bacaan turut disenaraikan dalam jadual di bawah.",
    )
    return (
        '<div class="pk-proj-card pk-proj-trend-plot">'
        f'<div class="pk-proj-trend-scale"><span>{format_signed(high)}</span>'
        f"<span>{format_signed(low)}</span></div>"
        f'<svg class="pk-proj-trend-svg" viewBox="0 0 {TREND_VIEW_W:.0f} {TREND_VIEW_H:.0f}" '
        f'role="img" aria-label="{html.escape(summary)}">{"".join(parts)}</svg>'
        '<div class="pk-proj-trend-dates">'
        f"<span>{html.escape(date_first)}</span><span>{html.escape(date_last)}</span>"
        "</div></div>"
    )


def _trend_table(model: PageModel, language: Language) -> str:
    """Every reading as a row (#45) — the plot's numbers rather than a
    summary of them, so a reader who cannot use the picture is not handed a
    shorter, vaguer version of it. Visible here rather than
    `visually-hidden`: this page is the detail page."""
    rows = "".join(
        f"<tr><td>{html.escape(_long_date(reading.day, language))}</td>"
        f'<td class="pk-proj-figure">{reading.government_seats}</td>'
        f"<td>{format_signed(reading.margin)}</td></tr>"
        for reading in model.trend
    )
    caption = t(
        language,
        "The Government Coalition's Seat total on each stored model run, oldest first",
        "Jumlah Kerusi Gabungan Kerajaan pada setiap larian model yang disimpan, "
        "paling lama dahulu",
    )
    return _table(
        (
            t(language, "Model run", "Larian model"),
            t(language, "Government Coalition seats", "Kerusi Gabungan Kerajaan"),
            t(language, "Against the Majority line", "Berbanding garis majoriti"),
        ),
        rows,
        caption=caption,
    )


def _trend_section(model: PageModel, language: Language) -> str:
    """How the Majority margin has moved (#45) — three states, chosen by how
    many runs are stored and never by how the result looks. All three notes
    are `public_page._majority_trend_section`'s own, both languages."""
    readings = len(model.trend)
    basis = t(
        language,
        "Each reading is one daily run of the same model against the same "
        "GE15 Baseline: the Government Coalition's Seats, above or below the "
        f"{model.majority_threshold} a Majority needs. Both Swing Model "
        "constants are judgement rather than fitted (ADR 0003), so a move "
        "here is this model reacting to News Sentiment, not a measurement of "
        "opinion changing.",
        "Setiap bacaan ialah satu larian harian model yang sama berbanding Asas "
        "PRU15 yang sama: Kerusi Gabungan Kerajaan, sama ada melebihi atau kurang "
        f"daripada {model.majority_threshold} yang diperlukan untuk majoriti. Kedua-dua "
        "pemalar Model Peralihan adalah pertimbangan, bukan disuaipadan (ADR 0003), jadi "
        "sebarang pergerakan di sini adalah model ini bertindak balas kepada Sentimen "
        "berita, bukan ukuran perubahan pendapat sebenar.",
    )
    head = _section_head(
        t(language, "Majority margin", "Majoriti"),
        t(
            language,
            "Across the stored model runs",
            "Merentasi larian model yang disimpan",
        ),
        basis,
    )
    if not model.trend_is_plotted:
        only = model.trend[0]
        note = t(
            language,
            f"One run is stored, {_long_date(only.day)}: {only.government_seats} Seats, "
            f"{format_signed(only.margin)} against the Majority line. There is "
            "nothing yet to compare it against, so nothing is plotted — a single "
            "mark on an axis would read as a flat line.",
            f"Satu larian disimpan, {_long_date(only.day, Language.MS)}: "
            f"{only.government_seats} Kerusi, {format_signed(only.margin)} berbanding "
            "garis majoriti. Belum ada apa-apa untuk dibandingkan lagi, jadi tiada "
            "carta diplot — satu tanda sahaja pada paksi akan kelihatan seperti garis "
            "mendatar.",
        )
        return _band(
            "pk-proj-trend",
            f'{head}<p class="pk-proj-note">{html.escape(note)}</p>{_trend_table(model, language)}',
        )
    date_first = _long_date(model.trend[0].day, language)
    date_last = _long_date(model.trend[-1].day, language)
    if model.trend_is_joined:
        note = t(
            language,
            f"{readings} runs are stored, {date_first} "
            f"to {date_last}. Marks are joined only "
            "where two runs are on consecutive days; a gap in the line is a day the "
            "pipeline did not run, never a value between two readings.",
            f"{readings} larian disimpan, {date_first} "
            f"hingga {date_last}. Tanda disambungkan hanya "
            "apabila dua larian berada pada hari berturutan; jurang dalam garis adalah "
            "hari saluran paip tidak berjalan, bukan sekali-kali nilai antara dua bacaan.",
        )
    else:
        note = t(
            language,
            f"{readings} runs are stored, {date_first} "
            f"to {date_last} — plotted as separate "
            "readings and deliberately not joined up. This page draws a line between "
            f"them at {MIN_TREND_READINGS} runs; below that, the distance between two "
            "marks is as much the model's own noise as it is movement.",
            f"{readings} larian disimpan, {date_first} "
            f"hingga {date_last} — diplot sebagai bacaan "
            "berasingan dan sengaja tidak disambungkan. Halaman ini melukis garis "
            f"antara bacaan hanya pada {MIN_TREND_READINGS} larian; di bawah itu, jarak "
            "antara dua tanda adalah sebanyak ralat model itu sendiri seperti mana ia "
            "adalah pergerakan sebenar.",
        )
    low, high = model.trend_span
    seats_word = t(language, "Seats", "Kerusi")
    reading_word = t(language, _plural(readings, "reading", "readings"), "bacaan")
    key_line = t(
        language,
        f"Scale {format_signed(low)} to {format_signed(high)} "
        f"{seats_word} · the dashed rule is the Majority line, {model.majority_threshold} "
        f"{seats_word} · {readings} {reading_word}",
        f"Skala {format_signed(low)} hingga {format_signed(high)} "
        f"{seats_word} · garis putus-putus ialah garis majoriti, {model.majority_threshold} "
        f"{seats_word} · {readings} {reading_word}",
    )
    return _band(
        "pk-proj-trend",
        f'{head}<p class="pk-proj-note">{html.escape(note)}</p>'
        f"{_trend_plot(model, language)}"
        f'<p class="pk-proj-key">{html.escape(key_line)}</p>'
        f"{_trend_table(model, language)}",
    )


def _too_close_section(model: PageModel, language: Language) -> str:
    """The Seats already in the Tight band, by margin (#48).

    Nothing here is a selection: `model.too_close_seats` filters on the tier
    `public_page.tier_for` already assigned, so this section introduces no
    threshold, no cutoff on how many Seats it will show, and no category of
    its own. The note is `public_page._too_close_table`'s own, both
    languages, and says exactly that and nothing more.
    """
    seats = model.too_close_seats
    head_note = (
        t(
            language,
            f"{len(seats)} of {model.total_seats} Seats "
            f"{_plural(len(seats), 'is', 'are')} projected inside six "
            "points — the same Seats the rest of the page marks Too close, "
            "smallest margin first. A Seat is "
            "listed here because of the size of its margin and nothing else: the "
            "Swing is uniform within a state, so this is arithmetic against GE15, "
            "not a claim about any of these Seats.",
            f"{len(seats)} daripada {model.total_seats} Kerusi "
            "diunjurkan dalam lingkungan enam mata — Kerusi yang sama yang "
            "ditandakan Terlalu rapat di tempat lain pada halaman ini, majoriti "
            "terkecil dahulu. Sesuatu Kerusi disenaraikan di sini semata-mata "
            "kerana saiz majoritinya: Peralihan adalah seragam dalam sesebuah "
            "negeri, jadi ini adalah pengiraan berbanding PRU15, bukan dakwaan "
            "tentang mana-mana Kerusi ini.",
        )
        if seats
        else t(
            language,
            "No Seat is projected inside six points.",
            "Tiada Kerusi diunjurkan dalam lingkungan enam mata.",
        )
    )
    head = _section_head(
        t(language, "Too close", "Terlalu rapat"),
        t(
            language,
            "Seats inside six points, by margin",
            "Kerusi dalam lingkungan enam mata, mengikut majoriti",
        ),
        html.escape(head_note),
    )
    if not seats:
        return _band("pk-proj-too-close", head, alt=True)
    rows = "".join(
        f'<tr data-seat="{html.escape(seat.code)}">'
        f'<td>{html.escape(seat.name)} <small class="pk-proj-code">'
        f"{html.escape(seat.code)}</small></td>"
        f"<td>{html.escape(seat.state)}</td>"
        f"<td>{html.escape(seat.coalition)}</td>"
        f'<td class="pk-proj-figure">{_points(seat.margin)}</td>'
        "</tr>"
        for seat in seats
    )
    headers = (
        t(language, "Seat", "Kerusi"),
        t(language, "State", "Negeri"),
        t(language, "Coalition", "Gabungan"),
        t(language, "Margin (points)", "Majoriti (mata)"),
    )
    return _band("pk-proj-too-close", f"{head}{_table(headers, rows)}", alt=True)


def _sensitivity_section(model: PageModel, language: Language) -> str:
    """The Government Coalition total at each alternate constant (#51).

    Row label is "Government Coalition total", never "confidence", and the
    note states plainly this is sensitivity to a judgement call — both
    settled on the issue itself and carried over verbatim, in both
    languages, since a BM copy that dropped the caveat would let this table
    read as the confidence interval the EN one is built not to imply.
    """
    rows = "".join(
        f'<tr><td class="pk-proj-figure">{value:.2f}</td>'
        f'<td class="pk-proj-figure">{total}</td></tr>'
        for value, total in model.sensitivity_table
    )
    head = _section_head(
        t(
            language,
            "Sensitivity to the unfitted constant",
            "Kepekaan terhadap pemalar yang tidak disuaipadan",
        ),
        t(
            language,
            "The same Projection at other constants",
            "Unjuran yang sama pada pemalar lain",
        ),
        html.escape(
            t(
                language,
                "The same Projection, recomputed at other values of an unfitted "
                "model constant — not a range of likely outcomes.",
                "Unjuran yang sama, dikira semula pada nilai lain bagi satu pemalar "
                "model yang tidak disuaipadan — bukan julat kemungkinan hasil.",
            )
        ),
    )
    headers = (
        t(language, "Sentiment sensitivity", "Kepekaan sentimen"),
        t(language, "Government Coalition total", "Jumlah Gabungan Kerajaan"),
    )
    return _band("pk-proj-sensitivity", f"{head}{_table(headers, rows)}")


def _state_rollup_section(model: PageModel, language: Language) -> str:
    """One row per state (#53) — the Swing Model's own unit of variation.

    Never a map: a choropleth would let Sarawak's land area dominate its
    31 Seats against its true 14%-of-the-chamber weight (HANDOFF's settled
    decision, unchanged by the change of register).
    """
    signal_word = t(language, "State result", "Keputusan negeri")
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(row.state)}</td>"
        f'<td class="pk-proj-figure">{row.seats}</td>'
        f'<td class="pk-proj-mono">{html.escape(_coalition_counts(row.baseline_totals))}</td>'
        f'<td class="pk-proj-mono">{html.escape(_coalition_counts(row.projected_totals))}</td>'
        f'<td class="pk-proj-mono">{html.escape(_coalition_swings(row.swing))}</td>'
        f"<td>{signal_word if row.signal_active else '—'}</td>"
        "</tr>"
        for row in model.state_rollup
    )
    head = _section_head(
        t(language, "Per-state rollup", "Rumusan setiap negeri"),
        t(language, "The Swing Model's own unit", "Unit Model Peralihan itu sendiri"),
        html.escape(
            t(
                language,
                "The Swing Model moves each state uniformly "
                "(ADR 0001/0003) — this is that structure, not a claim about any one "
                "Seat, and never drawn as a map (a choropleth would let a state's "
                "land area dominate its actual seat weight).",
                "Model Peralihan menggerakkan setiap negeri secara seragam "
                "(ADR 0001/0003) — ini adalah struktur tersebut, bukan dakwaan "
                "tentang mana-mana satu Kerusi, dan tidak sekali-kali dilukis "
                "sebagai peta (peta koroplet akan membiarkan luas tanah sesebuah "
                "negeri mengatasi berat kerusi sebenarnya).",
            )
        ),
    )
    headers = (
        t(language, "State", "Negeri"),
        t(language, "Seats", "Kerusi"),
        t(language, "GE15", "PRU15"),
        t(language, "Projected", "Diunjurkan"),
        t(language, "Swing", "Peralihan"),
        t(language, "Signal", "Isyarat"),
    )
    return _band("pk-proj-rollup", f"{head}{_table(headers, rows)}", alt=True)


def _seat_table_section(model: PageModel, language: Language) -> str:
    """All 222 Seats, filterable (#42/#47).

    Visible, unlike `public_page._seat_table`'s `visually-hidden` copy: there
    the table was the keyboard-reachable shadow of a chamber that carried
    the same detail in hover `<title>`s, and here it is the reason the page
    exists. Each row keeps its `id="seat-{code}"` so a shared Seat Call card
    or Telegram post can still deep-link to one, and its `data-search` index
    (built by `public_page._search_blob`, in the page's own language) so a
    BM reader typing "selamat" finds the rows the column labelled "Selamat".
    """
    names = _coalition_names(model)
    rows = "".join(
        f'<tr id="seat-{html.escape(seat.code)}" data-seat="{html.escape(seat.code)}" '
        f'data-search="{html.escape(_search_blob(seat, names, language))}">'
        f'<td>{html.escape(seat.name)} <small class="pk-proj-code">'
        f"{html.escape(seat.code)}</small></td>"
        f"<td>{html.escape(seat.state)}</td>"
        f"<td>{html.escape(seat.coalition)}</td>"
        f'<td class="pk-proj-figure">{_points(seat.margin)}</td>'
        f"<td>{html.escape(_tier_label(seat.tier, language))}</td>"
        "</tr>"
        for seat in model.seats
    )
    headers = (
        t(language, "Seat", "Kerusi"),
        t(language, "State", "Negeri"),
        t(language, "Coalition", "Gabungan"),
        t(language, "Margin (points)", "Majoriti (mata)"),
        t(language, "Certainty", "Kepastian"),
    )
    caption = t(
        language,
        f"All {model.total_seats} projected Seats, safest Government to safest Non-government",
        f"Semua {model.total_seats} Kerusi yang diunjurkan, daripada Kerusi Kerajaan paling "
        "selamat kepada Kerusi Bukan Kerajaan paling selamat",
    )
    head = _section_head(
        t(language, "Every Seat", "Setiap Kerusi"),
        t(
            language,
            "Safest Government to safest Non-government",
            "Kerusi Kerajaan paling selamat kepada Bukan Kerajaan paling selamat",
        ),
    )
    find_a_seat = t(language, "Find a Seat", "Cari Kerusi")
    placeholder = t(
        language,
        "Name, state, coalition, or certainty",
        "Nama, negeri, gabungan, atau tahap kepastian",
    )
    filter_html = f"""
<div class="pk-proj-filter">
  <label for="pk-proj-seat-filter">{find_a_seat}</label>
  <input type="search" id="pk-proj-seat-filter" autocomplete="off" spellcheck="false"
    placeholder="{placeholder}">
  <p class="pk-proj-filter-count" id="pk-proj-seat-filter-count" aria-live="polite"></p>
</div>
""".strip()
    return _band(
        "pk-proj-seats",
        f"{head}{filter_html}{_table(headers, rows, caption=caption)}",
    )


def _cite_this(model: PageModel, language: Language) -> str:
    """The provenance block (#55): what to cite, and against exactly which
    constants and sources.

    A figure quoted from this page today is unverifiable tomorrow once the
    daily render overwrites it, so this states the model-run date, the two
    Swing Model constants actually in force (ADR 0003's "provisional" made
    concrete), which outlets fed News Sentiment, and a dated permalink
    stable against that overwrite. `public_page._cite_this`'s copy, both
    languages, with the URL re-based on this page's own route — see
    `_permalink_url`.
    """
    read_from = ", ".join(html.escape(s) for s in model.sources) or t(
        language, "no outlets read", "tiada portal berita dibaca"
    )
    run_date = html.escape(_long_date(model.computed_at, language))
    body = t(
        language,
        f"Model run {run_date}. Swing Model: "
        f"sentiment sensitivity {model.sentiment_sensitivity:.2f}, state signal "
        f"weight {model.state_signal_weight:.2f}. Read from: {read_from}.",
        f"Larian model {run_date}. Model Peralihan: "
        f"kepekaan sentimen {model.sentiment_sensitivity:.2f}, pemberat isyarat "
        f"negeri {model.state_signal_weight:.2f}. Dibaca daripada: {read_from}.",
    )
    link_text = t(language, "A dated copy of this exact run", "Salinan bertarikh larian ini")
    trailer = t(
        language,
        ", unaffected by tomorrow's overwrite.",
        ", tidak terjejas oleh penulisan ganti esok.",
    )
    url = html.escape(_permalink_url(model, language))
    heading = t(language, "Cite this", "Petik ini")
    return (
        '<div class="pk-proj-card pk-proj-cite">'
        f"<h3>{heading}</h3><p>{body}</p>"
        f'<p><a href="{url}">{link_text}</a>{trailer}</p></div>'
    )


def _cite_section(model: PageModel, language: Language) -> str:
    read_full = t(language, "Read the full methodology →", "Baca metodologi penuh →")
    href = html.escape(methodology_url(language))
    return _band(
        "pk-proj-provenance",
        f'{_cite_this(model, language)}<a class="pk-proj-methodology-link" href="{href}">'
        f"{read_full}</a>",
        # `paper-alt`, so the page closes on a distinct band rather than
        # running on out of the seat table's own `paper` — the same band the
        # methodology page already gives this block, and the alternating
        # rhythm the homepage and landing page read in.
        alt=True,
    )


_SEAT_FILTER_SCRIPT_TEMPLATE = """
(function () {
  var input = document.getElementById("pk-proj-seat-filter");
  var count = document.getElementById("pk-proj-seat-filter-count");
  if (!input || !count) return;
  var rows = Array.prototype.slice.call(
    document.querySelectorAll(".pk-proj-seats .pk-proj-table tbody tr")
  );
  var total = rows.length;

  function apply() {
    var query = input.value.trim().toLowerCase();
    var matched = 0;
    rows.forEach(function (row) {
      var isMatch = row.dataset.search.indexOf(query) !== -1;
      row.hidden = !isMatch;
      if (isMatch) matched += 1;
    });
    count.textContent = query ? __MATCH_TEXT__ : "";
  }

  input.addEventListener("input", apply);
})();
"""
"""Client-side only (#47, ADR 0006), and the page reads correctly without it:
a script-disabled reader keeps a fully populated, unfiltered table, never a
broken or empty one. An empty query matches every row
(`"".indexOf(query)` is always found), so clearing the input is the same code
path as any other query rather than a special case.

Unlike `public_page`'s version this does not also dim chamber dots — the
hemicycle here is `politikku_hemicycle`'s three aggregate bands (#73), which
carry no per-Seat identity to dim.
"""


def _seat_filter_script(language: Language) -> str:
    """The filter script with its live match-count text in whichever
    language (#43) — a BM reader's live region must not announce an English
    sentence while every other word on the page is BM."""
    match_text = t(
        language,
        'matched + " of " + total + " Seats match"',
        'matched + " daripada " + total + " Kerusi sepadan"',
    )
    return _SEAT_FILTER_SCRIPT_TEMPLATE.replace("__MATCH_TEXT__", match_text)


def render_projection_body(model: PageModel, language: Language = Language.EN) -> str:
    """The projection page's `body_html`, without the persistent shell.

    `_tipping_point` returns `""` where the Majority line falls outside the
    chamber (`PageModel.threshold_seat` is `None` there, deliberately) — the
    band around it is skipped rather than emitted empty, since a bordered
    52px-tall section with nothing in it reads as a section that failed to
    load rather than as one the page had nothing to say in.
    """
    tipping = _tipping_point(model, language)
    tipping_band = _band("pk-proj-tipping-band", tipping) if tipping else ""
    return (
        f"<style>{_CSS}</style>"
        f"{_hero(model, language)}" + tipping_band + f"{_ledger_section(model, language)}"
        f"{_stress_section(model, language)}"
        f"{_trend_section(model, language)}"
        f"{_too_close_section(model, language)}"
        f"{_sensitivity_section(model, language)}"
        f"{_state_rollup_section(model, language)}"
        f"{_seat_table_section(model, language)}"
        f"{_cite_section(model, language)}"
        f"<script>{_seat_filter_script(language)}</script>"
    )


def render_projection(model: PageModel, *, language: Language = Language.EN) -> str:
    """The projection page as one full HTML document, shell included."""
    title = t(
        language,
        "GE16 Seat Projection — PolitikKu",
        "Unjuran kerusi PRU16 — PolitikKu",
    )
    return render_shell(
        title=title,
        active_nav="projection",
        language=language,
        page_path="",
        updated_at=model.computed_at,
        sources_count=len(model.sources),
        status=model.status,
        body_html=render_projection_body(model, language),
        prefix=PROJECTION_PREFIX,
    )


# ── the methodology page ──────────────────────────────────────────────────


def _article_counts_line(model: PageModel, language: Language) -> str:
    """The per-Coalition article-count sentence (#52) — counts only, nothing
    about which articles or what they said (the ticket's own guardrail)."""
    if not model.article_counts:
        return ""
    parts = " · ".join(f"{html.escape(name)} {count}" for name, count in model.article_counts)
    return t(language, f" By Coalition: {parts}.", f" Mengikut Gabungan: {parts}.")


def _colophon(model: PageModel, language: Language) -> str:
    """Method, Read from, Election status, Not calibrated — the old page's
    colophon, every sentence carried over in both languages."""
    read_from = " · ".join(html.escape(s) for s in model.sources) or t(
        language, "No outlets read", "Tiada portal berita dibaca"
    )
    articles_in_latest = t(
        language,
        f"{model.article_count} articles in the latest run.",
        f"{model.article_count} artikel dalam larian terkini.",
    )
    cards = (
        (
            t(language, "Method", "Kaedah"),
            t(
                language,
                "A Swing from each Seat's GE15 result, moved by daily News Sentiment "
                "and blended, state by state, with any state election held since. The "
                "Swing is uniform within a state, so a Seat's call is arithmetic against "
                "GE15.",
                "Peralihan daripada keputusan PRU15 setiap Kerusi, digerakkan oleh "
                "Sentimen berita harian dan digabungkan, negeri demi negeri, dengan "
                "mana-mana pilihan raya negeri yang diadakan sejak itu. Peralihan "
                "adalah seragam dalam sesebuah negeri, jadi keputusan sesuatu Kerusi "
                "adalah pengiraan berbanding PRU15.",
            ),
            False,
        ),
        (
            t(language, "Read from", "Dibaca daripada"),
            f"{read_from}. {articles_in_latest}{_article_counts_line(model, language)}",
            False,
        ),
        (
            t(language, "Election status", "Status pilihan raya"),
            html.escape(status_sentence(model.status, language)),
            False,
        ),
        (
            t(language, "Not calibrated", "Belum ditentukur"),
            t(
                language,
                "Two constants in the Swing Model were set by judgement, not fitted to "
                "data. Treat every figure here as a direction, not a forecast.",
                "Dua pemalar dalam Model Peralihan ditetapkan melalui pertimbangan, "
                "bukan disuaipadan kepada data. Anggap setiap angka di sini sebagai "
                "arah, bukan ramalan.",
            ),
            True,
        ),
    )
    return "".join(
        f'<div class="pk-proj-card{" pk-proj-caution" if caution else ""}">'
        f"<h3>{heading}</h3><p>{body}</p></div>"
        for heading, body, caution in cards
    )


def render_methodology_body(model: PageModel, language: Language = Language.EN) -> str:
    """The methodology page's `body_html`, without the persistent shell.

    The link target the header nav, the trust strip and the footer have
    pointed at since #72, and which existed nowhere until #102.
    """
    heading = t(
        language,
        "How this projection is built",
        "Bagaimana unjuran ini dibina",
    )
    lede_text = t(
        language,
        "Everything on PolitikKu is either a matter of record with a source beside it, or "
        "the output of an open model that has never been calibrated against survey data. "
        "This page says which is which, and states the exact constants and sources behind "
        "the run currently published.",
        "Semua yang ada di PolitikKu sama ada fakta rasmi dengan sumbernya, atau hasil "
        "model terbuka yang tidak pernah ditentukur terhadap data tinjauan. Halaman ini "
        "menyatakan yang mana satu, serta pemalar dan sumber tepat di sebalik larian yang "
        "diterbitkan sekarang.",
    )
    see_projection = t(
        language,
        "See the full seat projection →",
        "Lihat unjuran kerusi penuh →",
    )
    href = html.escape(projection_url(language))
    hero = _band(
        "pk-proj-methodology-hero",
        f'<div class="pk-eyebrow">{t(language, "Methodology", "Metodologi")}</div>'
        f"<h1>{heading}</h1><p>{lede_text}</p>"
        f'<a class="pk-proj-methodology-link" href="{href}">{see_projection}</a>',
        alt=True,
    )
    colophon = _band(
        "pk-proj-colophon",
        f'<div class="pk-proj-colophon-grid">{_colophon(model, language)}</div>',
    )
    provenance = _band("pk-proj-provenance", _cite_this(model, language), alt=True)
    return f"<style>{_CSS}</style>{hero}{colophon}{provenance}"


def render_methodology(model: PageModel, *, language: Language = Language.EN) -> str:
    """The methodology page as one full HTML document, shell included."""
    title = t(
        language,
        "Methodology & sources — PolitikKu",
        "Metodologi & sumber — PolitikKu",
    )
    return render_shell(
        title=title,
        active_nav="methodology",
        language=language,
        page_path=METHODOLOGY_PAGE,
        updated_at=model.computed_at,
        sources_count=len(model.sources),
        status=model.status,
        body_html=render_methodology_body(model, language),
    )


_CSS = """
  /* `.pk-eyebrow` is defined in `politikku_homepage`'s own page CSS, not the
     shell's, so a page that does not load the homepage cannot inherit it —
     defined here rather than assumed. */
  .pk-eyebrow {
    font-family: var(--mono); font-size: 11px; letter-spacing: .1em;
    text-transform: uppercase; color: var(--ink-secondary);
  }

  /* The alternating paper/paper-alt band rhythm the homepage and landing
     page already read in, at the shell's own gutter. */
  .pk-proj-band { background: var(--paper); padding: 42px var(--gutter-desktop); }
  .pk-proj-band-alt { background: var(--paper-alt); }
  .pk-proj-band + .pk-proj-band { border-top: 1px solid var(--line-soft); }

  .pk-proj-section-head { margin-bottom: 6px; }
  .pk-proj-section-head h2 {
    font-family: var(--serif); font-weight: 500; font-size: 26px; letter-spacing: -.015em;
    color: var(--ink); margin: 8px 0 0;
  }
  .pk-proj-note {
    font-size: 13.5px; line-height: 1.6; color: var(--ink-secondary);
    max-width: 74ch; margin: 10px 0 18px;
  }
  .pk-proj-key {
    font-family: var(--mono); font-size: 10.5px; color: var(--muted); margin: 10px 0 18px;
  }
  .pk-proj-card {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    padding: 18px 20px;
  }
  .pk-proj-card h3 {
    font-family: var(--serif); font-weight: 500; font-size: 19px; color: var(--ink);
    margin: 0 0 8px;
  }
  .pk-proj-card p { font-size: 13.5px; line-height: 1.6; color: var(--ink-secondary); margin: 0; }
  .pk-proj-caution { border-color: var(--caution-border); background: var(--caution-bg); }
  .pk-proj-caution p { color: var(--caution-deep); }

  /* Hero */
  .pk-proj-hero { display: grid; grid-template-columns: 1.05fr .95fr; gap: 44px; align-items: start; }
  .pk-proj-headline { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin: 14px 0 16px; }
  .pk-proj-headline-number {
    font-family: var(--serif); font-size: var(--text-h1-desktop); line-height: 1;
    letter-spacing: -.025em; color: var(--ink);
  }
  .pk-proj-headline-unit { font-size: 14px; color: var(--ink-secondary); }
  .pk-proj-lede {
    font-family: var(--serif); font-size: 21px; line-height: 1.42; letter-spacing: -.012em;
    color: var(--ink); margin: 0 0 22px; max-width: 40ch;
  }
  /* `public_page.lede()` is reused verbatim, so its own two hooks (`<b>` for
     the headline clause, `.buffer` for the tight-seat count) are styled here
     in PolitikKu's own ink rather than the old page's printed-inks
     underline. */
  .pk-proj-lede b { font-weight: 500; box-shadow: inset 0 -.3em 0 var(--positive-bg); }
  .pk-proj-lede .buffer { font-variant-numeric: tabular-nums; }
  .pk-proj-stats {
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 24px;
    margin: 0; padding-top: 18px; border-top: 1px solid var(--line);
  }
  .pk-proj-stats dt {
    font-family: var(--mono); font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase;
    color: var(--muted); margin: 0 0 4px;
  }
  .pk-proj-stats dd { margin: 0; font-family: var(--serif); font-size: 20px; color: var(--ink); }
  .pk-proj-hero-chart .pk-hemicycle { max-width: 420px; margin: 0 auto; }
  .pk-proj-legend {
    list-style: none; display: flex; gap: 18px; flex-wrap: wrap; justify-content: center;
    margin: 14px 0 0; padding: 0; font-size: 12px; color: var(--ink-secondary);
  }
  .pk-proj-legend li { display: flex; align-items: center; gap: 6px; }
  .pk-proj-swatch { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .pk-proj-swatch-gov { background: var(--data-government); }
  .pk-proj-swatch-noise { background: var(--data-noise); }
  .pk-proj-swatch-nongov { background: var(--data-nongovernment); }

  /* Tipping point sits in its own thin band between the hero and the ledger. */
  .pk-proj-tipping-band { padding-top: 26px; padding-bottom: 26px; }
  .pk-proj-tipping { max-width: 78ch; }
  .pk-proj-tipping-body {
    font-family: var(--serif); font-size: 18px; line-height: 1.5; color: var(--ink);
    margin: 8px 0 0;
  }
  .pk-proj-tipping-body b { font-weight: 500; }
  .pk-proj-caveat { font-size: 12.5px; color: var(--muted); margin: 10px 0 0; }

  /* The one table idiom, shared by all six ported tables. */
  .pk-proj-table-wrap {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    overflow: hidden; overflow-x: auto;
  }
  .pk-proj-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  .pk-proj-table caption {
    text-align: left; padding: 12px 14px 0; font-size: 12px; color: var(--muted);
  }
  .pk-proj-table th {
    font-family: var(--mono); font-size: 10px; letter-spacing: .06em; text-transform: uppercase;
    color: var(--muted); text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--line);
    white-space: nowrap;
  }
  .pk-proj-table td {
    padding: 10px 14px; border-bottom: 1px solid var(--line-soft); color: var(--ink);
  }
  .pk-proj-table tbody tr:last-child td { border-bottom: none; }
  .pk-proj-figure { font-variant-numeric: tabular-nums; }
  .pk-proj-mono { font-family: var(--mono); font-size: 11.5px; color: var(--ink-secondary); }
  .pk-proj-code { font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
  .pk-proj-na { color: var(--muted); }
  .pk-proj-total-row td, .pk-proj-total-row .pk-proj-stack-head { font-weight: 500; }
  .pk-proj-total-row td { border-top: 1px solid var(--line); }

  .pk-proj-coalition { display: inline-flex; align-items: center; gap: 8px; }
  .pk-proj-coalition small { font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
  /* Government / Non-government, the page's one colour axis — PolitikKu
     carries no party colours, so the ledger's old per-Coalition ink does not
     travel with it (see `_side_dot`). */
  .pk-proj-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }
  .pk-proj-dot-gov { background: var(--data-government); }
  .pk-proj-dot-nongov { background: var(--data-nongovernment); }
  .pk-proj-up { color: var(--accent); }
  .pk-proj-down { color: var(--caution-deep); }
  .pk-proj-flat { color: var(--muted); }

  /* Ledger: wide table on desktop, one card per Coalition below 700px. */
  .pk-proj-ledger-narrow { display: none; }
  .pk-proj-stack-row {
    background: var(--white); border: 1px solid var(--line); border-radius: var(--radius-lg);
    padding: 14px 16px; margin-bottom: 10px;
  }
  .pk-proj-stack-head {
    display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
    font-size: 14px;
  }
  .pk-proj-stack-head .pk-proj-figure { font-family: var(--serif); font-size: 22px; }
  .pk-proj-stack-stats {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 12px 0 0;
    padding-top: 10px; border-top: 1px solid var(--line-soft);
  }
  .pk-proj-stack-stats dt {
    font-family: var(--mono); font-size: 10px; letter-spacing: .06em; text-transform: uppercase;
    color: var(--muted);
  }
  .pk-proj-stack-stats dd { margin: 3px 0 0; font-size: 14px; font-variant-numeric: tabular-nums; }

  /* Stress test */
  .pk-proj-stress-grid {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 18px 0 0;
  }
  .pk-proj-stress-cell dd {
    margin: 8px 0 0; font-family: var(--serif); font-size: 32px; line-height: 1; color: var(--ink);
  }
  .pk-proj-stress-cell p { margin-top: 10px; font-size: 12.5px; }

  /* Majority-margin plot */
  .pk-proj-trend-plot {
    display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 0 10px;
    max-width: 700px; margin-bottom: 4px;
  }
  .pk-proj-trend-scale {
    display: flex; flex-direction: column; justify-content: space-between;
    font-family: var(--mono); font-size: 10px; color: var(--muted); text-align: right;
    padding: 10px 0;
  }
  .pk-proj-trend-svg { width: 100%; height: auto; }
  .pk-proj-trend-majority {
    stroke: var(--line-strong); stroke-width: 1; stroke-dasharray: 3 3;
  }
  .pk-proj-trend-step { stroke: var(--ink); stroke-width: 1.4; }
  .pk-proj-trend-mark { fill: var(--ink); }
  .pk-proj-trend-dates {
    grid-column: 2; display: flex; justify-content: space-between;
    font-family: var(--mono); font-size: 10px; color: var(--muted);
  }

  /* Seat filter */
  .pk-proj-filter {
    display: flex; align-items: center; flex-wrap: wrap; gap: 10px 14px; margin: 4px 0 16px;
  }
  .pk-proj-filter label {
    font-family: var(--mono); font-size: 10px; letter-spacing: .1em; text-transform: uppercase;
    color: var(--muted);
  }
  .pk-proj-filter input {
    font-family: var(--sans); font-size: 14px; color: var(--ink); background: var(--white);
    border: 1px solid var(--line-strong); border-radius: var(--radius-md);
    padding: 9px 12px; min-width: 280px;
  }
  .pk-proj-filter-count {
    font-family: var(--mono); font-size: 10px; color: var(--muted); margin: 0;
  }
  /* 222 rows is a page of its own — the table scrolls inside its card
     rather than pushing every other section below the fold. */
  .pk-proj-seats .pk-proj-table-wrap { max-height: 620px; overflow-y: auto; }
  .pk-proj-seats .pk-proj-table thead th {
    position: sticky; top: 0; background: var(--white); z-index: 1;
  }

  /* Provenance + methodology page */
  .pk-proj-provenance { display: flex; flex-direction: column; align-items: flex-start; gap: 14px; }
  .pk-proj-cite { max-width: 78ch; }
  .pk-proj-cite p + p { margin-top: 8px; }
  .pk-proj-methodology-link { font-size: 13.5px; color: var(--accent); }
  .pk-proj-methodology-hero h1 {
    font-family: var(--serif); font-weight: 500; font-size: var(--text-h1-desktop);
    line-height: 1.08; letter-spacing: -.02em; color: var(--ink); margin: 12px 0 14px;
    max-width: 22ch;
  }
  .pk-proj-methodology-hero p {
    font-size: 15px; line-height: 1.6; color: var(--ink-secondary); max-width: 62ch;
    margin: 0 0 18px;
  }
  .pk-proj-colophon-grid {
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px;
  }

  @media (max-width: 900px) {
    .pk-proj-band { padding: 24px var(--gutter-mobile); }
    .pk-proj-hero { grid-template-columns: 1fr; gap: 26px; }
    .pk-proj-headline-number { font-size: var(--text-h1-mobile); }
    .pk-proj-lede { font-size: 18px; }
    .pk-proj-section-head h2 { font-size: 22px; }
    .pk-proj-methodology-hero h1 { font-size: var(--text-h1-mobile); }
    .pk-proj-stress-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .pk-proj-colophon-grid { grid-template-columns: 1fr; }
    .pk-proj-filter input { min-width: 0; flex: 1; }
  }

  @media (max-width: 700px) {
    /* HANDOFF defect 4: the wide ledger measured 205px of columns
       off-screen at 375px, taking the "Too close" column with it. Exactly
       one of the two layouts is shown at a time, never both. */
    .pk-proj-ledger-wide { display: none; }
    .pk-proj-ledger-narrow { display: block; }
    .pk-proj-stress-grid { grid-template-columns: 1fr; }
    .pk-proj-stats { grid-template-columns: 1fr; }
  }
"""


# ── I/O ───────────────────────────────────────────────────────────────────


def _projection_page_model(engine: Engine) -> PageModel:
    """One Storage read behind both pages.

    Mirrors `public_page.build_page` rather than the shorter read
    `politikku_homepage`/`_landing`/`_mp_profile` make: those pass no
    `history`, which leaves `PageModel.trend` holding today's run alone and
    the Majority-margin section (#45) permanently stuck on its "one run is
    stored" sentence. This page *is* the trend's home, so it passes the same
    `projections` list the latest Projection came out of — one read, never a
    second that could pick up a day written in between and plot a right-hand
    end the rest of the page does not state.
    """
    from lpa.config import (
        coalition_names,
        load_coalition_config,
        load_election_status,
        load_state_election_signals,
        swing_model_config,
    )
    from lpa.public_page import page_model
    from lpa.storage import (
        load_projections,
        load_seat_baselines,
        load_sentiment_snapshots,
        load_state_swing,
    )

    projections = load_projections(engine)
    if not projections:
        raise SystemExit("No Projection stored. Run `python -m lpa.pipeline` to compute one.")
    baseline = load_seat_baselines(engine)
    if not baseline:
        raise SystemExit("No Seat Baseline in Storage. Run `python -m lpa.baseline_loader` first.")

    config = load_coalition_config()
    snapshots = load_sentiment_snapshots(engine)
    latest = snapshots[-1].sentiment if snapshots else None
    return page_model(
        projection=projections[-1],
        baseline=baseline,
        status=load_election_status(),
        config=swing_model_config(config),
        names=coalition_names(config),
        sentiment=latest,
        state_election_signals=load_state_election_signals(),
        total_seats=config["total_seats"],
        state_swing=load_state_swing(engine, projections[-1].computed_at),
        history=projections,
    )


def build_projection(engine: Engine, *, language: Language = Language.EN) -> tuple[str, date]:
    """Read Storage and render the projection page. The whole I/O half."""
    model = _projection_page_model(engine)
    return render_projection(model, language=language), model.computed_at


def build_methodology(engine: Engine, *, language: Language = Language.EN) -> tuple[str, date]:
    """Read Storage and render the methodology page. The whole I/O half."""
    model = _projection_page_model(engine)
    return render_methodology(model, language=language), model.computed_at


def build_all_projection_languages(engine: Engine) -> list[tuple[Language, str, date]]:
    """`build_projection`, once per `Language` — matching
    `politikku_landing.build_all_landing_languages`'s own naming.

    One Storage read behind both languages, not one per language: two reads
    could straddle a pipeline write and publish an EN and a BM page stating
    different days' figures under the same "updated" date.
    """
    model = _projection_page_model(engine)
    return [
        (language, render_projection(model, language=language), model.computed_at)
        for language in Language
    ]


def build_all_methodology_languages(engine: Engine) -> list[tuple[Language, str, date]]:
    """`build_methodology`, once per `Language` — one Storage read behind
    both, for `build_all_projection_languages`' own reason."""
    model = _projection_page_model(engine)
    return [
        (language, render_methodology(model, language=language), model.computed_at)
        for language in Language
    ]


def main() -> None:
    """Render both pages from Storage, in both languages, and write them.

    Four pages plus one dated copy per language (#55): `index.html` is
    overwritten every day, so a figure quoted from the projection page today
    is otherwise unverifiable tomorrow. The dated copy is written under this
    page's own route, which is the path `_permalink_url` states on the page
    itself — the link and the file it names cannot disagree.

    Renders from one `PageModel` directly rather than through
    `build_all_projection_languages`/`build_all_methodology_languages`: those
    are the two-line API #104's `daily.yml` wiring will call for one page at
    a time, and using both here would put two Storage reads behind four
    pages that all cite one model run.
    """
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("public") / PROJECTION_PREFIX.strip("/") / PROJECTION_PAGE,
        help="where to write the English projection page "
        "(default: public/projection/index.html); the BM variant is written alongside it "
        "at <output-dir>/ms/<output-name>, matching `politikku_shell._ms_route`'s own "
        "path convention",
    )
    parser.add_argument(
        "--methodology-output",
        type=Path,
        default=Path("public/politikku") / METHODOLOGY_PAGE,
        help="where to write the English methodology page "
        "(default: public/politikku/methodology.html); the BM variant is written "
        "alongside it at <output-dir>/ms/<output-name>",
    )
    args = parser.parse_args()

    # One Storage read behind all four pages, not one per page: the
    # methodology page's own "cite this" block links the projection page's
    # dated permalink, and that file is written by the loop below from *this*
    # run's `computed_at`. A second read that picked up a day written in
    # between would have the methodology page printing a citation link to a
    # dated file nothing ever wrote — a 404 citation, which `_permalink_url`
    # rightly calls worse than no citation link at all.
    model = _projection_page_model(connect())
    computed_at = model.computed_at

    def _target(output: Path, language: Language) -> Path:
        return output if language is Language.EN else output.parent / "ms" / output.name

    def _write(target: Path, page: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        print(f"Wrote {target} ({len(page):,} bytes), computed {computed_at}")

    for language in Language:
        page = render_projection(model, language=language)
        target = _target(args.output, language)
        _write(target, page)
        _write(target.parent / _permalink_path(computed_at), page)

        _write(
            _target(args.methodology_output, language), render_methodology(model, language=language)
        )


if __name__ == "__main__":
    main()
