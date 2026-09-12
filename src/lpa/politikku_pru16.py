"""PolitikKu's GE16 page (/pru16/ and /ms/pru16/).

One address that follows GE16 from "not called" to polling day: the
Election Status with a day count, the four dates that mark the way, where
the Projection stands, the Seat lookup, and a way to follow along.

Everything shown is read, not written by hand. The status and dates come
from `data/election_status.json`, and the page derives which of its three
states to draw from which dates are present — the same rule `CONTEXT.md`'s
Election Status entry gives. The Projection comes from
`public/projection.json`, the file the landing page also reads, so the two
pages cannot disagree about the Seat totals.

The count is written at build time and then run live in the browser against
midnight in Malaysia on the target date, so a page built yesterday is never
out of date. The wording around it stays plain — the numbers move, the page
does not tell anyone to hurry.
"""

from __future__ import annotations

import argparse
import html
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from lpa.domain import ElectionStatus
from lpa.politikku_landing import (
    PROJECTION_JSON,
    CoalitionRow,
    _coalition_rows,
    _outlets_count,
    _read_projection,
)
from lpa.politikku_shell import Language, projection_url, render_shell, route, t
from lpa.public_page import _long_date

PAGE_PATH = "pru16/"
"""`route()` resolves it to `/pru16/` (EN) and `/ms/pru16/` (BM). One slug in
both languages, because the sitemap and the language switch pair pages by
identical paths."""

TELEGRAM_URL = "https://t.me/REPLACE_ME"
"""The public Telegram channel. REPLACE_ME: the channel's public link is not
recorded anywhere in this repository yet; set it here before this page is
linked from the site. Do not guess a handle."""

PROCESS_PAGE = "learn/ge16-process.html"
"""The explainer for how dissolution, nomination and polling work."""


@dataclass(frozen=True)
class Pru16Model:
    """The data backing `/pru16/` and `/ms/pru16/`.

    `coalitions` empty means the Projection could not be read; the page then
    says so in that one section and renders everything else as normal.
    """

    status: ElectionStatus
    today: date
    now: datetime
    coalitions: tuple[CoalitionRow, ...]
    computed_at: date | None
    majority_threshold: int
    total_seats: int
    sources_count: int
    art: str = "skyline"
    """Which hero artwork to draw: "skyline", "arc", "both" or "none".
    An experiment switch, not a setting we mean to keep forever."""


def pru16_model(
    *,
    status: ElectionStatus | None = None,
    now: datetime | None = None,
    coalitions: Sequence[CoalitionRow] | None = None,
    computed_at: date | None = None,
    projection_path: Path = PROJECTION_JSON,
    art: str = "skyline",
) -> Pru16Model:
    """Build the model. Every argument defaults to a real read, so a test can
    pass them all and touch no file."""
    from lpa.config import load_coalition_config, load_election_status
    from lpa.domain import TOTAL_SEATS
    from lpa.pipeline import MALAYSIA_TIME

    if status is None:
        status = load_election_status()
    if now is None:
        now = datetime.now(MALAYSIA_TIME)
    today = now.astimezone(MALAYSIA_TIME).date()
    if coalitions is None:
        _, totals, read_computed_at = _read_projection(projection_path)
        coalitions = _coalition_rows(totals)
        if computed_at is None:
            computed_at = read_computed_at
    try:
        threshold = int(load_coalition_config()["majority_threshold"])
    except (OSError, KeyError, TypeError, ValueError):
        threshold = 112
    return Pru16Model(
        status=status,
        today=today,
        now=now,
        coalitions=tuple(coalitions),
        computed_at=computed_at,
        majority_threshold=threshold,
        total_seats=TOTAL_SEATS,
        sources_count=_outlets_count(),
        art=art,
    )


def days_until(target: date, today: date) -> int:
    """Whole days from `today` to `target`; negative once `target` has passed."""
    return (target - today).days


def _days_word(n: int, language: Language) -> str:
    # BM does not inflect "hari" for number.
    return t(language, "day" if n == 1 else "days", "hari")


# ── Icons ─────────────────────────────────────────────────────────────────
# Drawn, never text glyphs: an arrow as text falls back to the emoji font on
# phones and draws a colour icon instead of a line.

_ICON_ARROW = (
    '<svg class="pk-ge-ico" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
    '<path d="M4.5 11.5l7-7M6 4.5h5.5V10" fill="none" stroke="currentColor" '
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_ICON_SEND = (
    '<svg class="pk-ge-ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
    '<path d="M21.5 3.5 2.8 10.7c-.9.4-.9 1.6.1 1.9l4.6 1.5 1.8 5.6c.3.9 1.4 1.1 2 .4l2.6-2.9 '
    '4.8 3.5c.7.5 1.7.1 1.9-.7L23 4.8c.2-.9-.7-1.6-1.5-1.3z" fill="none" stroke="currentColor" '
    'stroke-width="1.6" stroke-linejoin="round"/><path d="m7.5 14.1 11-7.6-8.2 9.4" '
    'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>'
)
_ICON_SEARCH = (
    '<svg class="pk-ge-ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
    '<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/>'
    '<path d="m15.5 15.5 5 5" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round"/></svg>'
)


# ── Sections ──────────────────────────────────────────────────────────────


def time_left(target: date, now: datetime) -> tuple[int, int, int, int]:
    """Days, hours, minutes and seconds from `now` to midnight on `target` in
    Malaysia, never below zero.

    The target is a date, and a Malaysian polling day starts at midnight local
    time, so the clock runs to `00:00` MYT on that date — not to whatever hour
    the page happened to be built at.
    """
    from lpa.pipeline import MALAYSIA_TIME

    deadline = datetime.combine(target, time.min, tzinfo=MALAYSIA_TIME)
    remaining = int((deadline - now.astimezone(MALAYSIA_TIME)).total_seconds())
    if remaining < 0:
        return 0, 0, 0, 0
    return remaining // 86400, remaining % 86400 // 3600, remaining % 3600 // 60, remaining % 60


def _count_block(target: date, now: datetime, caption: str, language: Language) -> str:
    """The big day count, the running hours/minutes/seconds under it, and what
    the browser needs to keep them moving."""
    days, hours, minutes, seconds = time_left(target, now)
    units = (
        (hours, t(language, "hours", "jam"), "h"),
        (minutes, t(language, "minutes", "minit"), "m"),
        (seconds, t(language, "seconds", "saat"), "s"),
    )
    clock = "".join(
        f'<span class="pk-ge-unit"><b data-pk-count-{key}>{value:02d}</b>'
        f"<small>{label}</small></span>"
        for value, label, key in units
    )
    return (
        f'<div class="pk-ge-count" data-pk-countdown data-target="{target.isoformat()}" '
        f'data-word-one="{t(language, "day", "hari")}" '
        f'data-word-many="{t(language, "days", "hari")}">'
        f'<span class="pk-ge-count-n" data-pk-count-n>{days}</span>'
        f'<span class="pk-ge-count-unit" data-pk-count-unit>{_days_word(days, language)}</span>'
        f'<div class="pk-ge-clock" role="timer" aria-live="off">{clock}</div>'
        f'<p class="pk-ge-count-cap">{caption}</p></div>'
    )


def _hero(model: Pru16Model, language: Language) -> str:
    status = model.status
    eyebrow = t(language, "GE16 · Election Status", "PRU16 · Status pilihan raya")

    if not status.called:
        state = "not-called"
        chip = t(language, "Not called", "Belum diisytiharkan")
        heading = t(language, "GE16 has not been called.", "PRU16 belum diisytiharkan.")
        deadline = html.escape(_long_date(status.constitutional_deadline, language))
        count = _count_block(
            status.constitutional_deadline,
            model.now,
            t(
                language,
                f"until the latest possible polling date, <b>{deadline}</b>.",
                f"lagi sebelum tarikh mengundi paling lewat, <b>{deadline}</b>.",
            ),
            language,
        )
        note = t(
            language,
            "This is the legal limit, not a forecast. The Dewan Rakyat is usually "
            "dissolved before its term runs out, and the count switches to polling "
            "day once the Election Commission sets one.",
            "Ini had undang-undang, bukan ramalan. Dewan Rakyat biasanya dibubarkan "
            "sebelum tempohnya tamat, dan kiraan akan bertukar kepada hari mengundi "
            "sebaik Suruhanjaya Pilihan Raya menetapkannya.",
        )
    elif status.polling_date is None:
        state = "called"
        dissolved = html.escape(_long_date(status.dissolved_on, language))  # type: ignore[arg-type]
        chip = t(language, "Called", "Diisytiharkan")
        heading = t(language, "GE16 has been called.", "PRU16 telah diisytiharkan.")
        waiting = t(language, "Polling day not yet announced", "Tarikh mengundi belum diumumkan")
        count = f'<div class="pk-ge-waiting"><p class="pk-ge-waiting-big">{waiting}</p></div>'
        note = t(
            language,
            f"The Dewan Rakyat was dissolved on {dissolved}. The Election Commission "
            "sets nomination day and polling day together, usually a week or two "
            "after dissolution. The count starts here once it does.",
            f"Dewan Rakyat telah dibubarkan pada {dissolved}. Suruhanjaya Pilihan Raya "
            "menetapkan hari penamaan calon dan hari mengundi serentak, biasanya "
            "seminggu dua selepas pembubaran. Kiraan bermula di sini sebaik ia "
            "ditetapkan.",
        )
    else:
        state = "polling"
        polling = html.escape(_long_date(status.polling_date, language))
        chip = t(language, "Called", "Diisytiharkan")
        n = days_until(status.polling_date, model.today)
        if n > 0:
            heading = t(language, "GE16 polling day is set.", "Tarikh mengundi PRU16 ditetapkan.")
        elif n == 0:
            heading = t(language, "GE16 polling day is today.", "Hari ini hari mengundi PRU16.")
        else:
            heading = t(
                language, "GE16 polling has taken place.", "Pengundian PRU16 telah berlangsung."
            )
        count = _count_block(
            status.polling_date,
            model.now,
            t(
                language,
                f"to polling day, <b>{polling}</b>.",
                f"lagi ke hari mengundi, <b>{polling}</b>.",
            ),
            language,
        )
        note = t(
            language,
            "Polling day as announced by the Election Commission.",
            "Tarikh mengundi seperti yang diumumkan oleh Suruhanjaya Pilihan Raya.",
        )

    return (
        f'<section class="pk-ge-hero" data-state="{state}" aria-labelledby="pk-ge-h1">'
        '<div class="pk-ge-wrap pk-ge-hero-grid">'
        '<div class="pk-ge-hero-copy">'
        f'<p class="pk-ge-eyebrow">{eyebrow}</p>'
        f'<p class="pk-ge-chip pk-ge-chip-{state}">'
        f'<span class="pk-ge-dot" aria-hidden="true"></span>{chip}</p>'
        f'<h1 id="pk-ge-h1">{heading}</h1>'
        f"{count}"
        f'<p class="pk-ge-note">{note}</p></div>'
        f"{_art(model, language)}"
        "</div></section>"
    )


# ── The hero artwork ──────────────────────────────────────────────────────
#
# Three experiments, chosen by `Pru16Model.art`:
#   "skyline" — Merdeka 118 drawn in line art, lit slowly.
#   "arc"     — this Parliament's five-year term as an arc, which is data.
#   "both"    — the arc behind the tower.
# All of it is drawn here in SVG rather than photographed: a photograph of
# Merdeka 118 belongs to whoever took it, and a flat drawing is what the rest
# of the site looks like. It is decoration, labelled as such, and it never
# encodes a number the reader could misread as a Seat count.

TERM_FIRST_SITTING = date(2022, 12, 19)
"""When this Dewan Rakyat first sat, which starts its five-year term.

The same date `data/election_status.json`'s notes give when they derive the
constitutional deadline, restated here because the arc needs the start of the
term and the file records only its end.
"""


_ART_DEFS = (
    "<defs>"
    # the light that passes up the tower
    '<linearGradient id="pk-sweep-grad" x1="0" y1="1" x2="0.6" y2="0">'
    '<stop offset="0%" stop-color="#d6ed9a" stop-opacity="0"/>'
    '<stop offset="55%" stop-color="#d6ed9a" stop-opacity=".22"/>'
    '<stop offset="100%" stop-color="#d6ed9a" stop-opacity="0"/>'
    "</linearGradient>"
    # the pulse the clock sends up on every tick
    '<linearGradient id="pk-pulse-grad" x1="0" y1="1" x2="0" y2="0">'
    '<stop offset="0%" stop-color="#d6ed9a" stop-opacity="0"/>'
    '<stop offset="50%" stop-color="#eaf7c4" stop-opacity=".55"/>'
    '<stop offset="100%" stop-color="#d6ed9a" stop-opacity="0"/>'
    "</linearGradient>"
    "</defs>"
)
"""Gradients the artwork's animations move through."""


def _art_tower() -> str:
    """Merdeka 118: a tapering, faceted tower with a spire, in line art.

    Drawn from its published proportions — a slim, stepped, diamond-faceted
    shaft under a long spire — not traced from a photograph.
    """
    facets = "".join(
        f'<path class="pk-facet" style="animation-delay:{i * 0.55:.2f}s" '
        f'd="M{144 - i * 1.9},{176 + i * 34} L158,{160 + i * 34} '
        f'L{172 + i * 1.9},{176 + i * 34} L158,{192 + i * 34} Z"/>'
        for i in range(9)
    )
    windows = "".join(
        f'<rect class="pk-win" style="animation-delay:{(i % 7) * 0.9 + 0.3:.2f}s" '
        f'x="{138 + (i % 3) * 14}" y="{206 + (i // 3) * 44}" width="6" height="3"/>'
        for i in range(18)
    )
    return (
        '<g class="pk-tower">'
        '<path class="pk-city" d="M28,470 L28,392 L66,392 L66,470 Z"/>'
        '<path class="pk-city" d="M72,470 L72,352 L102,352 L102,470 Z"/>'
        '<path class="pk-city" d="M206,470 L206,366 L234,366 L234,470 Z"/>'
        '<path class="pk-city" d="M240,470 L240,406 L282,406 L282,470 Z"/>'
        '<path class="pk-shaft" d="M128,470 L140,150 L176,150 L188,470 Z"/>'
        '<path class="pk-spire" d="M158,26 L162,150 L154,150 Z"/>'
        '<path class="pk-shaft-edge" d="M158,150 L158,470"/>'
        f"{facets}{windows}"
        '<path class="pk-sweep" d="M128,470 L140,150 L176,150 L188,470 Z"/>'
        '<path class="pk-pulse" data-pk-pulse d="M128,470 L140,150 L176,150 L188,470 Z"/>'
        '<circle class="pk-beacon-glow" cx="158" cy="24" r="7"/>'
        '<circle class="pk-beacon" cx="158" cy="24" r="2.6"/>'
        '<line class="pk-ground" x1="0" y1="470" x2="320" y2="470"/>'
        "</g>"
    )


def _term_elapsed(model: Pru16Model, language: Language) -> str:
    """How much of this Parliament's five-year term has run, as a percentage."""
    start, end = TERM_FIRST_SITTING, model.status.constitutional_deadline
    span = (end - start).days or 1
    gone = min(max((model.today - start).days, 0), span)
    return t(
        language,
        f"{gone * 100 // span}% of the term elapsed",
        f"{gone * 100 // span}% penggal berlalu",
    )


def _art_arc(model: Pru16Model, language: Language, *, horizon: bool = False) -> str:
    """The five-year term as an arc: how much has run, how much is left.

    `horizon=True` is the version that sits behind the tower — larger, fainter
    and unlabelled, so it reads as a ring of light rather than a chart set
    beside one.
    """
    start, end = TERM_FIRST_SITTING, model.status.constitutional_deadline
    span = (end - start).days or 1
    gone = min(max((model.today - start).days, 0), span)
    # A 240° arc, drawn as a dashed circle so one number sets how far it fills.
    radius = 150 if horizon else 118
    circumference = 2 * 3.14159 * radius
    sweep = circumference * (240 / 360)
    filled = sweep * gone / span
    # `--pk-arc-len` is what the draw-in animates from, so the arc sweeps to
    # today's share once, on load.
    body = (
        f'<circle class="pk-arc-track" r="{radius}" '
        f'stroke-dasharray="{sweep:.1f} {circumference:.1f}" transform="rotate(150)"/>'
        f'<circle class="pk-arc-run" r="{radius}" style="--pk-arc-len:{filled:.1f}px" '
        f'stroke-dasharray="{filled:.1f} {circumference:.1f}" transform="rotate(150)"/>'
    )
    if horizon:
        return f'<g class="pk-arc is-horizon" transform="translate(158,300)">{body}</g>'

    label_start = t(language, "TERM BEGAN", "PENGGAL BERMULA")
    label_end = t(language, "LATEST POSSIBLE", "PALING LEWAT")
    pct = _term_elapsed(model, language)
    return (
        '<g class="pk-arc" transform="translate(158,250)">'
        + body
        + f'<text class="pk-arc-pct" x="0" y="150" text-anchor="middle">{html.escape(pct)}</text>'
        + '<text class="pk-arc-k" x="-104" y="86" text-anchor="middle">'
        + f"{html.escape(label_start)}</text>"
        + '<text class="pk-arc-v" x="-104" y="102" text-anchor="middle">'
        + f"{html.escape(_long_date(start, language))}</text>"
        + '<text class="pk-arc-k" x="104" y="86" text-anchor="middle">'
        + f"{html.escape(label_end)}</text>"
        + '<text class="pk-arc-v" x="104" y="102" text-anchor="middle">'
        + f"{html.escape(_long_date(end, language))}</text></g>"
    )


def _art(model: Pru16Model, language: Language) -> str:
    """The hero artwork, with the state and the time of day it reacts to.

    `data-state` is what the scene reads on dissolution day: the arc turns to
    the caution colour and the beacon quickens, so the page looks different
    the moment GE16 is actually called. `data-tod` is set by the browser from
    the hour in Malaysia; it starts at "night", which is when the drawing
    looks its best, so a reader with no JavaScript still gets a lit tower.
    """
    if model.art == "none":
        return ""
    decorative = t(language, "Decorative artwork", "Karya hiasan")
    state = "called" if model.status.called else "not-called"
    if model.art == "arc":
        inner = _art_arc(model, language)
        caption = t(language, "This Parliament's five-year term", "Penggal lima tahun Parlimen ini")
    elif model.art == "both":
        # The percentage moves into the caption: behind the tower there is no
        # room to read it.
        inner = _art_arc(model, language, horizon=True) + _art_tower()
        caption = f"{_term_elapsed(model, language)} · Merdeka 118, {decorative.lower()}"
    else:
        inner = _art_tower()
        caption = f"Merdeka 118 · {decorative.lower()}"
    return (
        f'<div class="pk-ge-art pk-art-{model.art}" data-pk-art data-state="{state}" '
        'data-tod="night" aria-hidden="true">'
        f'<svg viewBox="0 0 320 500" preserveAspectRatio="xMidYMax meet">{_ART_DEFS}{inner}</svg>'
        f'<p class="pk-art-cap">{html.escape(caption)}</p></div>'
    )


def _dates(model: Pru16Model, language: Language) -> str:
    """Dissolved, Nomination, Polling, Deadline — each a date or "Not yet"."""
    status = model.status
    not_yet = t(language, "Not yet", "Belum")

    def step(label: str, day: date | None, *, limit: bool = False) -> str:
        value = html.escape(_long_date(day, language)) if day is not None else not_yet
        if limit:
            cls = "is-limit"
        elif day is not None:
            cls = "is-done"
        else:
            cls = "is-pending"
        return (
            f'<li class="pk-ge-step {cls}"><span class="pk-ge-step-mark" aria-hidden="true"></span>'
            f'<span class="pk-ge-step-label">{label}</span>'
            f'<span class="pk-ge-step-date">{value}</span></li>'
        )

    steps = "".join(
        (
            step(
                t(language, "Dewan Rakyat dissolved", "Dewan Rakyat dibubarkan"),
                status.dissolved_on,
            ),
            step(t(language, "Nomination day", "Hari penamaan calon"), status.nomination_date),
            step(t(language, "Polling day", "Hari mengundi"), status.polling_date),
            step(
                t(language, "Latest possible polling date", "Tarikh mengundi paling lewat"),
                status.constitutional_deadline,
                limit=True,
            ),
        )
    )
    heading = t(language, "The road to GE16", "Perjalanan ke PRU16")
    sub = t(
        language,
        "Each date is filled in only once it is officially announced. We never guess one.",
        "Setiap tarikh diisi hanya selepas ia diumumkan secara rasmi. Kami tidak meneka.",
    )
    return (
        '<section class="pk-ge-band" aria-labelledby="pk-ge-dates-h">'
        f'<div class="pk-ge-wrap"><h2 id="pk-ge-dates-h">{heading}</h2>'
        f'<p class="pk-ge-sub">{sub}</p>'
        f"{_pipeline(model, language)}"
        f'<ol class="pk-ge-steps">{steps}</ol></div></section>'
    )


# ── The pipeline card ─────────────────────────────────────────────────────
#
# The same four dates as the list above, drawn as a signal path: four nodes,
# dashed connectors with packets running along them, and a stats strip. It is
# the wide-screen rendering; the list is the narrow one, and each is hidden
# where the other shows, so neither is ever read twice.

_NODE_W = 112
_NODE_X = (64, 196, 328, 460)
_NODE_Y = 46
_NODE_H = 58


def _pipeline_node(
    x: int, eyebrow: str, value: str, foot: str, state: str, escape_value: bool = True
) -> str:
    mid = x + _NODE_W // 2
    shown = html.escape(value) if escape_value else value
    return (
        f'<g class="pk-node is-{state}">'
        f'<rect x="{x}" y="{_NODE_Y}" width="{_NODE_W}" height="{_NODE_H}" rx="9"/>'
        f'<circle class="pk-node-led" cx="{x + _NODE_W - 13}" cy="{_NODE_Y + 13}" r="3"/>'
        f'<text class="pk-node-eyebrow" x="{mid}" y="{_NODE_Y + 17}" text-anchor="middle">'
        f"{html.escape(eyebrow)}</text>"
        f'<text class="pk-node-value" x="{mid}" y="{_NODE_Y + 37}" text-anchor="middle">'
        f"{shown}</text>"
        f'<text class="pk-node-foot" x="{mid}" y="{_NODE_Y + 51}" text-anchor="middle">'
        f"{html.escape(foot)}</text></g>"
    )


def _pipeline_link(index: int, live: bool) -> str:
    """One dashed connector, with three packets running along it when the
    stage it leads to is the one being waited on."""
    x1 = _NODE_X[index] + _NODE_W
    x2 = _NODE_X[index + 1]
    y = _NODE_Y + _NODE_H // 2
    dots = ""
    if live:
        dots = "".join(
            f'<circle class="pk-packet" cx="{x1}" cy="{y}" r="{r}" '
            f'style="--pk-run:{x2 - x1}px;animation-delay:{delay}s"/>'
            for r, delay in ((2.5, 0), (1.8, 0.35), (1.3, 0.7))
        )
    return (
        f'<g class="pk-link{" is-live" if live else ""}"><path d="M{x1},{y} L{x2},{y}"/>{dots}</g>'
    )


def _pipeline(model: Pru16Model, language: Language) -> str:
    status = model.status
    not_yet = t(language, "Not yet", "Belum")
    awaiting = t(language, "awaiting announcement", "menunggu pengumuman")
    announced = t(language, "announced", "diumumkan")
    fixed = t(language, "constitutional limit", "had perlembagaan")

    stages = (
        (
            t(language, "DISSOLUTION", "PEMBUBARAN"),
            status.dissolved_on,
            t(language, "Dewan Rakyat dissolved", "Dewan Rakyat dibubarkan"),
        ),
        (
            t(language, "NOMINATION", "PENAMAAN"),
            status.nomination_date,
            t(language, "Nomination day", "Hari penamaan calon"),
        ),
        (
            t(language, "POLLING", "MENGUNDI"),
            status.polling_date,
            t(language, "Polling day", "Hari mengundi"),
        ),
    )
    # The first stage with no date is the one the country is waiting on; the
    # packets run into it, and nothing runs past it, because nothing has.
    waiting_on = next((i for i, (_, day, _) in enumerate(stages) if day is None), None)

    nodes = ""
    for i, (eyebrow, day, _) in enumerate(stages):
        if day is not None:
            state, value, foot = "done", _long_date(day, language), announced
        elif i == waiting_on:
            state, value, foot = "waiting", not_yet, awaiting
        else:
            state, value, foot = "pending", not_yet, awaiting
        nodes += _pipeline_node(_NODE_X[i], eyebrow, value, foot, state)
    nodes += _pipeline_node(
        _NODE_X[3],
        t(language, "DEADLINE", "TARIKH AKHIR"),
        _long_date(status.constitutional_deadline, language),
        fixed,
        "limit",
    )

    links = "".join(
        _pipeline_link(i, live=(waiting_on is not None and i == waiting_on - 1)) for i in range(3)
    )
    # Nothing has been announced yet: the packets run into the first stage.
    if waiting_on == 0:
        y = _NODE_Y + _NODE_H // 2
        packets = "".join(
            f'<circle class="pk-packet" cx="4" cy="{y}" r="{r}" '
            f'style="--pk-run:{_NODE_X[0] - 4}px;animation-delay:{delay}s"/>'
            for r, delay in ((2.5, 0), (1.8, 0.35), (1.3, 0.7))
        )
        links = (
            packets + f'<g class="pk-link is-live"><path d="M4,{_NODE_Y + _NODE_H // 2} '
            f'L{_NODE_X[0]},{_NODE_Y + _NODE_H // 2}"/></g>' + links
        )

    set_count = sum(1 for _, day, _ in stages if day is not None)
    header_right = t(
        language,
        f"{set_count} of 3 dates announced",
        f"{set_count} daripada 3 tarikh diumumkan",
    )
    if waiting_on is None:
        line = t(
            language,
            "All three dates are set. Polling day is fixed.",
            "Ketiga-tiga tarikh telah ditetapkan. Hari mengundi sudah muktamad.",
        )
    else:
        waits = (
            t(
                language,
                "Waiting on the Dewan Rakyat to be dissolved.",
                "Menunggu Dewan Rakyat dibubarkan.",
            ),
            t(
                language,
                "Waiting on the Election Commission to set nomination day.",
                "Menunggu Suruhanjaya Pilihan Raya menetapkan hari penamaan calon.",
            ),
            t(
                language,
                "Waiting on the Election Commission to set polling day.",
                "Menunggu Suruhanjaya Pilihan Raya menetapkan hari mengundi.",
            ),
        )
        line = waits[waiting_on]
    stats = (
        (t(language, "DATES SET", "TARIKH DITETAPKAN"), f"{set_count}/3"),
        (
            t(language, "LATEST POSSIBLE", "PALING LEWAT"),
            _long_date(status.constitutional_deadline, language),
        ),
        (t(language, "SOURCE", "SUMBER"), "parlimen.gov.my"),
    )
    stats_html = "".join(
        f'<div><span class="pk-stat-k">{html.escape(k)}</span>'
        f'<span class="pk-stat-v">{html.escape(v)}</span></div>'
        for k, v in stats
    )
    live_label = t(language, "THE ROAD TO GE16 · TRACKING", "PERJALANAN KE PRU16 · DIPANTAU")

    return (
        '<div class="pk-pipe" aria-hidden="true">'
        '<div class="pk-pipe-head"><span class="pk-pipe-live">'
        f'<span class="pk-pipe-led"></span>{html.escape(live_label)}</span>'
        f'<span class="pk-pipe-count">{html.escape(header_right)}</span></div>'
        f'<svg viewBox="0 0 580 128" class="pk-pipe-svg">{links}{nodes}</svg>'
        f'<div class="pk-pipe-line"><span>&rsaquo;</span>{html.escape(line)}</div>'
        f'<div class="pk-pipe-stats">{stats_html}</div></div>'
    )


def _majority_lede(gov: int, threshold: int, language: Language) -> str:
    gap = gov - threshold
    if gap > 0:
        return t(
            language,
            f"The Government Coalition is projected to win <b>{gov} Seats</b>, "
            f"{gap} more than the {threshold} needed for a Majority.",
            f"Gabungan Kerajaan diunjurkan memenangi <b>{gov} kerusi</b>, "
            f"{gap} lebih daripada {threshold} yang diperlukan untuk Majoriti.",
        )
    if gap == 0:
        return t(
            language,
            f"The Government Coalition is projected to win <b>{gov} Seats</b>, "
            f"exactly the {threshold} needed for a Majority.",
            f"Gabungan Kerajaan diunjurkan memenangi <b>{gov} kerusi</b>, "
            f"tepat {threshold} yang diperlukan untuk Majoriti.",
        )
    return t(
        language,
        f"The Government Coalition is projected to win <b>{gov} Seats</b>, "
        f"{-gap} short of the {threshold} needed for a Majority.",
        f"Gabungan Kerajaan diunjurkan memenangi <b>{gov} kerusi</b>, "
        f"kurang {-gap} daripada {threshold} yang diperlukan untuk Majoriti.",
    )


def _legend_group(rows: Sequence[CoalitionRow], title: str) -> str:
    if not rows:
        return ""
    seats = sum(r.seats for r in rows)
    items = "".join(
        f'<li><span class="pk-ge-sw" style="background:{html.escape(r.color)}"></span>'
        f"<span>{html.escape(r.code)}</span><b>{r.seats}</b></li>"
        for r in rows
    )
    return (
        f'<div class="pk-ge-legend-group"><p class="pk-ge-legend-title">{title}'
        f" <b>{seats}</b></p><ul>{items}</ul></div>"
    )


def _projection(model: Pru16Model, language: Language) -> str:
    heading = t(language, "Where the Projection stands", "Kedudukan Unjuran")
    full_link = (
        f'<a class="pk-ge-link" href="{html.escape(projection_url(language))}">'
        f"{t(language, 'See the full Projection', 'Lihat Unjuran penuh')} {_ICON_ARROW}</a>"
    )
    open_band = (
        '<section class="pk-ge-band pk-ge-band-alt" aria-labelledby="pk-ge-proj-h">'
        f'<div class="pk-ge-wrap"><h2 id="pk-ge-proj-h">{heading}</h2>'
    )
    if not model.coalitions:
        unavailable = t(
            language,
            "The Projection is not available right now. The full page has the latest run.",
            "Unjuran tidak tersedia buat masa ini. Halaman penuh mempunyai larian terkini.",
        )
        return f'{open_band}<p class="pk-ge-sub">{unavailable}</p>{full_link}</div></section>'

    total = model.total_seats
    threshold = model.majority_threshold
    government = [r for r in model.coalitions if r.government]
    others = [r for r in model.coalitions if not r.government]
    gov = sum(r.seats for r in government)

    segments = "".join(
        f'<span class="pk-ge-seg" style="flex:{r.seats} 0 0;background:{html.escape(r.color)}" '
        f'title="{html.escape(r.code)}: {r.seats}"></span>'
        for r in model.coalitions
    )
    bar_label = t(
        language,
        f"Government Coalition {gov} of {total} Seats; a Majority is {threshold}.",
        f"Gabungan Kerajaan {gov} daripada {total} kerusi; Majoriti ialah {threshold}.",
    )
    majority_label = t(language, f"Majority · {threshold}", f"Majoriti · {threshold}")
    bar = (
        f'<div class="pk-ge-bar-wrap" role="img" aria-label="{html.escape(bar_label)}">'
        f'<div class="pk-ge-bar">{segments}</div>'
        f'<span class="pk-ge-maj" style="left:{threshold / total * 100:.3f}%">'
        f"<span>{majority_label}</span></span></div>"
    )
    legend = _legend_group(
        government, t(language, "Government Coalition", "Gabungan Kerajaan")
    ) + _legend_group(others, t(language, "Others", "Lain-lain"))

    run = ""
    if model.computed_at is not None:
        run_date = html.escape(_long_date(model.computed_at, language))
        run = t(language, f"Model run {run_date}. ", f"Larian model {run_date}. ")
    caveat = run + t(
        language,
        "A Projection is an estimate from GE15 results and daily News Sentiment, not "
        "calibrated against survey data. It is not an election result.",
        "Unjuran ialah anggaran daripada keputusan PRU15 dan Sentimen berita harian, "
        "belum ditentukur dengan data tinjauan. Ia bukan keputusan pilihan raya.",
    )
    return (
        f"{open_band}"
        f'<p class="pk-ge-lede">{_majority_lede(gov, threshold, language)}</p>{bar}'
        f'<div class="pk-ge-legend">{legend}</div>'
        f'<p class="pk-ge-caveat">{caveat}</p>{full_link}</div></section>'
    )


def _lookup(language: Language) -> str:
    """The same form contract `/lookup.js` mounts on the landing page."""
    heading = t(language, "Find your Seat", "Cari kerusi anda")
    sub = t(
        language,
        "Enter your postcode to see your Seat, its Projection and your MP.",
        "Masukkan poskod anda untuk melihat kerusi, Unjuran dan Ahli Parlimen anda.",
    )
    label = t(language, "Your Malaysian postcode", "Poskod Malaysia anda")
    placeholder = t(language, "e.g. 06050", "cth. 06050")
    locate = t(language, "Use my location", "Guna lokasi saya")
    hint = t(
        language,
        "A postcode can cross Seat boundaries. We'll show every possible match in the "
        "verified index.",
        "Satu poskod boleh merentasi sempadan kerusi. Kami akan tunjukkan semua padanan "
        "yang mungkin dalam indeks yang disahkan.",
    )
    return f"""<section class="pk-ge-band" id="find" aria-labelledby="pk-ge-find-h">
<div class="pk-ge-wrap pk-ge-find">
<div><h2 id="pk-ge-find-h">{heading}</h2><p class="pk-ge-sub">{sub}</p></div>
<div class="lookup" data-pk-lookup-scope>
<form class="lookup pk-ge-form" data-pk-lookup-form role="search" novalidate>
<label class="pk-ge-label" for="pk-lookup-q">{html.escape(label)}</label>
<div class="pk-ge-input-row">
<input id="pk-lookup-q" name="q" type="search" autocomplete="postal-code" spellcheck="false" maxlength="5" inputmode="numeric" placeholder="{html.escape(placeholder)}" data-pk-lookup-input aria-describedby="pk-lookup-note">
<button class="pk-ge-submit" type="submit" aria-label="{html.escape(heading)}">{_ICON_SEARCH}</button>
</div>
<button class="pk-ge-locate" type="button" data-pk-locate>{html.escape(locate)}</button>
<p class="pk-ge-hint" id="pk-lookup-note">{html.escape(hint)}</p>
<div class="results pk-lookup-results" data-pk-lookup-results role="status" aria-live="polite" hidden></div>
</form>
</div>
</div></section>"""


def _follow(language: Language) -> str:
    heading = t(language, "Follow GE16 on Telegram", "Ikuti PRU16 di Telegram")
    body = t(
        language,
        "One message when something actually changes: the Dewan Rakyat is dissolved, "
        "polling day is set, or the Projection moves across the Majority line. "
        "No daily noise.",
        "Satu mesej apabila sesuatu benar-benar berubah: Dewan Rakyat dibubarkan, "
        "tarikh mengundi ditetapkan, atau Unjuran melintasi garis Majoriti. "
        "Tiada gangguan harian.",
    )
    cta = t(language, "Join the channel", "Sertai saluran")
    return (
        '<section class="pk-ge-band pk-ge-band-alt" aria-labelledby="pk-ge-follow-h">'
        '<div class="pk-ge-wrap pk-ge-follow">'
        f'<div><h2 id="pk-ge-follow-h">{heading}</h2><p class="pk-ge-sub">{body}</p></div>'
        f'<a class="pk-ge-btn" href="{html.escape(TELEGRAM_URL)}" rel="noopener">'
        f"{_ICON_SEND}<span>{cta}</span></a></div></section>"
    )


def _sources(model: Pru16Model, language: Language) -> str:
    source = html.escape(model.status.source)
    process = html.escape(route(language, PROCESS_PAGE))
    source_label = t(language, "Source", "Sumber")
    learn_label = t(language, "Learn more", "Ketahui lanjut")
    source_text = t(
        language,
        "Dates are entered by hand from official announcements, on the day they are made.",
        "Tarikh dimasukkan secara manual daripada pengumuman rasmi, pada hari ia dibuat.",
    )
    learn_text = t(
        language,
        "How dissolution, nomination and polling fit together, and why an election "
        "can be called before its date is known.",
        "Bagaimana pembubaran, penamaan calon dan pengundian berkait, dan mengapa "
        "pilihan raya boleh diisytiharkan sebelum tarikhnya diketahui.",
    )
    process_label = t(language, "The GE16 process", "Proses PRU16")
    return (
        '<section class="pk-ge-band pk-ge-foot"><div class="pk-ge-wrap pk-ge-foot-grid">'
        f'<div><p class="pk-ge-eyebrow">{source_label}</p><p>{source_text} '
        f'<a class="pk-ge-link" href="{source}" rel="noopener">{source} {_ICON_ARROW}</a></p></div>'
        f'<div><p class="pk-ge-eyebrow">{learn_label}</p><p>{learn_text} '
        f'<a class="pk-ge-link" href="{process}">{process_label} {_ICON_ARROW}</a></p></div>'
        "</div></section>"
    )


_SCRIPT = """
<script>
(function () {
  var el = document.querySelector('[data-pk-countdown]');
  if (!el) return;
  var target = Date.parse(el.getAttribute('data-target') + 'T00:00:00+08:00');
  if (isNaN(target)) return;
  var n = el.querySelector('[data-pk-count-n]');
  var unit = el.querySelector('[data-pk-count-unit]');
  var h = el.querySelector('[data-pk-count-h]');
  var m = el.querySelector('[data-pk-count-m]');
  var s = el.querySelector('[data-pk-count-s]');
  var art = document.querySelector('[data-pk-art]');
  var pulse = document.querySelector('[data-pk-pulse]');
  var calm = window.matchMedia('(prefers-reduced-motion: reduce)');
  var pad = function (v) { return v < 10 ? '0' + v : '' + v; };
  function tick() {
    var left = Math.max(Math.floor((target - Date.now()) / 1000), 0);
    var days = Math.floor(left / 86400);
    n.textContent = days;
    unit.textContent = el.getAttribute(days === 1 ? 'data-word-one' : 'data-word-many');
    h.textContent = pad(Math.floor(left % 86400 / 3600));
    m.textContent = pad(Math.floor(left % 3600 / 60));
    s.textContent = pad(left % 60);
    if (pulse && !calm.matches) {
      pulse.classList.remove('is-tick');
      void pulse.getBoundingClientRect();
      pulse.classList.add('is-tick');
    }
  }
  tick();
  setInterval(tick, 1000);

  // The scene follows the hour in Malaysia, not the reader's own time zone:
  // the tower is in Kuala Lumpur, whoever is looking at it.
  if (art) {
    var setHour = function () {
      try {
        var hour = +new Intl.DateTimeFormat('en-GB', {
          timeZone: 'Asia/Kuala_Lumpur', hour: '2-digit', hour12: false
        }).format(new Date());
        art.setAttribute(
          'data-tod', hour >= 7 && hour < 18 ? 'day' : (hour < 20 && hour >= 18 ? 'dusk' : 'night')
        );
      } catch (e) {}
    };
    setHour();
    setInterval(setHour, 600000);
  }
})();
</script>
"""
"""Runs the count from the reader's own clock, against midnight in Malaysia
on the target date, so a page built yesterday is never out of date. The
values written at build time stay if this fails."""


_CSS = """
  .pk-ge-wrap { max-width: 960px; margin: 0 auto; padding: 0 var(--gutter-desktop, 30px); }
  .pk-ge-ico { display: inline-block; width: .9em; height: .9em; flex: none; vertical-align: -.1em; }
  .pk-ge-eyebrow {
    font-family: var(--mono); font-size: 12px; letter-spacing: .14em;
    text-transform: uppercase; color: var(--muted); margin: 0 0 .6rem;
  }
  .pk-ge-hero {
    padding: 64px 0 56px; border-bottom: 1px solid var(--line-soft);
    background:
      radial-gradient(ellipse 60% 80% at 85% 0%, rgba(214, 237, 154, .09), transparent 70%),
      var(--paper);
  }
  .pk-ge-chip {
    display: inline-flex; align-items: center; gap: 8px; margin: 0 0 18px;
    padding: 6px 12px; border: 1px solid var(--line); border-radius: 999px;
    font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase;
    color: var(--ink-secondary);
  }
  .pk-ge-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
  .pk-ge-chip-called, .pk-ge-chip-polling { border-color: var(--positive-border); color: var(--accent); }
  .pk-ge-chip-called .pk-ge-dot, .pk-ge-chip-polling .pk-ge-dot { background: var(--accent); }
  .pk-ge-hero h1 {
    font-size: var(--text-h1-desktop, 44px); line-height: 1.08; letter-spacing: -.025em;
    margin: 0 0 28px; color: var(--ink); max-width: 18ch;
  }
  .pk-ge-count { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 16px; }
  .pk-ge-count-n {
    font-family: var(--font-display); font-weight: 700; color: var(--accent);
    font-size: clamp(88px, 16vw, 168px); line-height: .9; letter-spacing: -.05em;
    font-variant-numeric: tabular-nums;
  }
  .pk-ge-count-unit {
    font-family: var(--font-display); font-weight: 600; font-size: clamp(24px, 3.4vw, 36px);
    color: var(--ink);
  }
  .pk-ge-clock { flex-basis: 100%; display: flex; gap: 26px; margin: 14px 0 0; }
  .pk-ge-unit { display: flex; flex-direction: column; gap: 2px; }
  .pk-ge-unit b {
    font-family: var(--mono); font-size: 28px; font-weight: 500; line-height: 1;
    color: var(--ink); font-variant-numeric: tabular-nums;
  }
  .pk-ge-unit small {
    font-family: var(--mono); font-size: 12px; letter-spacing: .1em; text-transform: uppercase;
    color: var(--muted);
  }
  .pk-ge-count-cap {
    flex-basis: 100%; margin: 18px 0 0; font-size: 18px; line-height: 1.45; color: var(--ink-secondary);
  }
  .pk-ge-count-cap b { color: var(--ink); font-weight: 600; }
  .pk-ge-waiting-big {
    margin: 0; font-family: var(--font-display); font-weight: 600; color: var(--accent);
    font-size: clamp(30px, 5vw, 48px); line-height: 1.1; letter-spacing: -.02em;
  }
  .pk-ge-note {
    max-width: 62ch; margin: 24px 0 0; padding-left: 14px; border-left: 2px solid var(--line-strong);
    font-size: 15px; line-height: 1.6; color: var(--muted);
  }
  /* Hero artwork (experiment): Merdeka 118 in line art, the term as an arc,
     or both. Decoration, labelled as such; it never encodes a number. The
     scene follows the hour in Malaysia (data-tod) and the Election Status
     (data-state), and every animation stops under prefers-reduced-motion. */
  .pk-ge-hero-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 40px; align-items: end; }
  .pk-ge-hero-copy { min-width: 0; }
  /* The sky is a glow behind the tower, not a panel: it fades to nothing at
     the edges, so there is no card outline against the page. */
  .pk-ge-art { position: relative; align-self: end; }
  .pk-ge-art::before {
    content: ""; position: absolute; inset: -6% -12% -4%; pointer-events: none;
    transition: background 1.2s ease;
    background:
      radial-gradient(ellipse 62% 48% at 50% 78%, rgba(28, 62, 74, .85) 0%, rgba(20, 44, 54, .45) 42%, rgba(16, 30, 35, 0) 72%),
      radial-gradient(ellipse 40% 60% at 50% 40%, rgba(24, 54, 62, .55) 0%, rgba(16, 30, 35, 0) 70%);
  }
  .pk-ge-art[data-tod="day"]::before {
    background:
      radial-gradient(ellipse 62% 48% at 50% 78%, rgba(52, 92, 98, .75) 0%, rgba(30, 58, 64, .4) 42%, rgba(16, 30, 35, 0) 72%),
      radial-gradient(ellipse 40% 60% at 50% 40%, rgba(44, 80, 86, .45) 0%, rgba(16, 30, 35, 0) 70%);
  }
  .pk-ge-art[data-tod="dusk"]::before {
    background:
      radial-gradient(ellipse 62% 48% at 50% 78%, rgba(86, 68, 44, .6) 0%, rgba(44, 46, 44, .35) 42%, rgba(16, 30, 35, 0) 72%),
      radial-gradient(ellipse 40% 60% at 50% 40%, rgba(60, 54, 42, .4) 0%, rgba(16, 30, 35, 0) 70%);
  }
  .pk-ge-art svg, .pk-art-cap { position: relative; }
  .pk-ge-art svg { display: block; width: 100%; height: auto; max-height: 460px; overflow: visible; }
  .pk-art-cap {
    margin: 10px 0 0; text-align: center;
    font-family: var(--mono); font-size: 10px; letter-spacing: .1em; text-transform: uppercase;
    color: var(--muted); opacity: .55;
  }
  .pk-shaft { fill: #16282d; stroke: var(--line-strong); stroke-width: 1; }
  .pk-city { fill: none; stroke: var(--line); stroke-width: 1; }
  .pk-spire { fill: var(--line-strong); stroke: none; }
  .pk-shaft-edge { stroke: var(--line); stroke-width: .8; }
  .pk-ground { stroke: var(--line); stroke-width: 1; }
  .pk-facet {
    fill: none; stroke: var(--accent); stroke-width: .9; opacity: .18;
    animation: pk-facet 7s ease-in-out infinite;
  }
  @keyframes pk-facet { 0%, 100% { opacity: .12 } 45% { opacity: .5 } }
  .pk-win { fill: var(--accent); opacity: .25; animation: pk-win 5.5s ease-in-out infinite; }
  @keyframes pk-win { 0%, 100% { opacity: .12 } 40% { opacity: .75 } }
  /* Fewer lights burn in daylight. */
  .pk-ge-art[data-tod="day"] .pk-win { animation-duration: 9s; opacity: .08; }
  .pk-ge-art[data-tod="day"] .pk-facet { opacity: .1; }
  .pk-sweep {
    fill: url(#pk-sweep-grad); stroke: none; opacity: 0;
    animation: pk-sweep 9s ease-in-out infinite;
  }
  @keyframes pk-sweep { 0%, 100% { opacity: 0 } 40% { opacity: .5 } 60% { opacity: .35 } }
  /* The spire beacon, as a real tower carries. */
  .pk-beacon { fill: #ff6b5e; animation: pk-beacon 2.6s ease-in-out infinite; }
  .pk-beacon-glow { fill: #ff6b5e; opacity: .12; animation: pk-beacon-glow 2.6s ease-in-out infinite; }
  @keyframes pk-beacon { 0%, 62%, 100% { opacity: .22 } 72% { opacity: 1 } }
  @keyframes pk-beacon-glow { 0%, 62%, 100% { opacity: 0 } 72% { opacity: .3 } }
  .pk-ge-art[data-tod="day"] .pk-beacon-glow { opacity: 0; }
  /* One pulse up the shaft per tick of the clock: the class is re-added by
     the countdown script, which restarts the animation. */
  .pk-pulse { fill: url(#pk-pulse-grad); stroke: none; opacity: 0; }
  .pk-pulse.is-tick { animation: pk-tick .9s ease-out 1; }
  @keyframes pk-tick {
    from { opacity: .5; transform: translateY(70px) }
    to { opacity: 0; transform: translateY(-30px) }
  }
  .pk-arc-track, .pk-arc-run { fill: none; stroke-linecap: round; }
  .pk-arc-track { stroke: var(--line); stroke-width: 6; }
  .pk-arc-run {
    stroke: var(--accent); stroke-width: 6; opacity: .85;
    animation: pk-arc-draw 1.4s cubic-bezier(.22, .8, .28, 1) 1 both;
  }
  @keyframes pk-arc-draw {
    from { stroke-dashoffset: var(--pk-arc-len) }
    to { stroke-dashoffset: 0 }
  }
  .pk-arc.is-horizon .pk-arc-track { stroke-width: 2; opacity: .5; }
  .pk-arc.is-horizon .pk-arc-run { stroke-width: 2.5; opacity: .4; }
  .pk-arc-pct, .pk-arc-k, .pk-arc-v { font-family: var(--mono); }
  .pk-arc-pct { font-size: 12px; fill: var(--ink-secondary); letter-spacing: .04em; }
  .pk-arc-k { font-size: 8px; fill: var(--muted); letter-spacing: .1em; }
  .pk-arc-v { font-size: 10px; fill: var(--ink-secondary); }
  /* Dissolution day: the scene changes with the Election Status. */
  .pk-ge-art[data-state="called"] .pk-arc-run { stroke: var(--caution); }
  .pk-ge-art[data-state="called"] .pk-facet,
  .pk-ge-art[data-state="called"] .pk-win { stroke: var(--caution); fill: var(--caution); }
  .pk-ge-art[data-state="called"] .pk-beacon,
  .pk-ge-art[data-state="called"] .pk-beacon-glow { animation-duration: 1.3s; }
  @media (prefers-reduced-motion: reduce) {
    .pk-facet, .pk-win, .pk-sweep, .pk-beacon, .pk-beacon-glow, .pk-arc-run, .pk-pulse.is-tick {
      animation: none;
    }
    .pk-sweep, .pk-pulse { opacity: 0; }
    .pk-beacon { opacity: .6; }
  }
  .pk-ge-band { padding: 52px 0; border-bottom: 1px solid var(--line-soft); }
  .pk-ge-band-alt { background: var(--paper-alt); }
  .pk-ge-band h2 { font-size: 28px; line-height: 1.15; letter-spacing: -.015em; margin: 0 0 8px; color: var(--ink); }
  .pk-ge-sub { margin: 0 0 24px; font-size: 16px; line-height: 1.55; color: var(--ink-secondary); max-width: 60ch; }
  /* The pipeline card: the wide-screen rendering of the same four dates. */
  .pk-pipe {
    border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
    background: #0c1a1e;
  }
  .pk-pipe-head {
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 11px 18px; border-bottom: 1px solid var(--line-soft);
  }
  .pk-pipe-live, .pk-pipe-count {
    font-family: var(--mono); font-size: 10px; letter-spacing: .1em; color: var(--muted);
  }
  .pk-pipe-live { display: inline-flex; align-items: center; gap: 7px; }
  .pk-pipe-led {
    width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
    animation: pk-led 2s ease-in-out infinite;
  }
  @keyframes pk-led { 0%, 100% { opacity: 1 } 50% { opacity: .2 } }
  .pk-pipe-svg { display: block; width: 100%; height: auto; }
  .pk-link path { fill: none; stroke: rgba(214, 237, 154, .2); stroke-width: 1.5; stroke-dasharray: 3 5; }
  .pk-link.is-live path { stroke: rgba(214, 237, 154, .34); }
  .pk-packet {
    fill: var(--accent);
    animation: pk-run 1.15s linear infinite;
  }
  @keyframes pk-run {
    from { transform: translateX(0); opacity: 0 }
    12% { opacity: 1 }
    to { transform: translateX(var(--pk-run)); opacity: 0 }
  }
  .pk-node rect { fill: #13252a; stroke: var(--line-soft); stroke-width: 1; }
  .pk-node-eyebrow {
    font-family: var(--mono); font-size: 8.5px; letter-spacing: .09em; fill: var(--muted);
  }
  .pk-node-value { font-family: var(--font-display); font-size: 13px; font-weight: 600; fill: var(--ink); }
  .pk-node-foot { font-family: var(--mono); font-size: 8px; fill: var(--muted); opacity: .7; }
  .pk-node-led { fill: var(--line-strong); }
  .pk-node.is-pending .pk-node-value { fill: var(--muted); font-weight: 500; }
  .pk-node.is-waiting rect { fill: #10222a; stroke: var(--accent); }
  .pk-node.is-waiting .pk-node-value { fill: var(--ink); }
  .pk-node.is-waiting .pk-node-led { fill: var(--accent); animation: pk-led 1.9s ease-in-out infinite; }
  .pk-node.is-done .pk-node-led { fill: var(--accent); }
  .pk-node.is-limit rect { stroke: var(--caution); stroke-dasharray: 4 4; }
  .pk-node.is-limit .pk-node-value { fill: var(--caution); font-size: 12px; }
  /* No status light on the limit: it is a fixed date, not a stage waiting to happen. */
  .pk-node.is-limit .pk-node-led { display: none; }
  .pk-pipe-line {
    display: flex; gap: 8px; align-items: baseline;
    padding: 10px 18px; border-top: 1px solid var(--line-soft);
    font-family: var(--mono); font-size: 12px; color: var(--ink-secondary);
  }
  .pk-pipe-line span { color: var(--accent); }
  .pk-pipe-stats {
    display: flex; flex-wrap: wrap; gap: 8px 28px;
    padding: 11px 18px; border-top: 1px solid var(--line-soft);
  }
  .pk-pipe-stats div { display: flex; flex-direction: column; gap: 3px; }
  .pk-stat-k { font-family: var(--mono); font-size: 9px; letter-spacing: .09em; color: var(--muted); }
  .pk-stat-v { font-family: var(--mono); font-size: 14px; color: var(--ink-secondary); }
  @media (prefers-reduced-motion: reduce) {
    .pk-packet, .pk-pipe-led, .pk-node.is-waiting .pk-node-led { animation: none; }
    .pk-packet { opacity: 0; }
  }
  .pk-ge-steps {
    list-style: none; margin: 0; padding: 0; display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr)); position: relative;
  }
  .pk-ge-steps::before {
    content: ""; position: absolute; left: 7px; right: 7px; top: 7px; height: 2px; background: var(--line);
  }
  .pk-ge-step { position: relative; display: flex; flex-direction: column; gap: 6px; padding-right: 14px; }
  .pk-ge-step-mark {
    width: 16px; height: 16px; border-radius: 50%; background: var(--paper);
    border: 2px solid var(--line-strong); margin-bottom: 10px; position: relative;
  }
  .pk-ge-step.is-done .pk-ge-step-mark { background: var(--accent); border-color: var(--accent); }
  .pk-ge-step.is-limit .pk-ge-step-mark { border-color: var(--caution); border-style: dashed; }
  .pk-ge-step-label { font-size: 14px; color: var(--muted); }
  .pk-ge-step-date { font-family: var(--font-display); font-size: 20px; font-weight: 600; color: var(--ink); }
  .pk-ge-step.is-pending .pk-ge-step-date { color: var(--muted); font-weight: 500; }
  .pk-ge-step.is-limit .pk-ge-step-date { color: var(--caution); }
  .pk-ge-lede { font-size: 19px; line-height: 1.5; color: var(--ink-secondary); margin: 0 0 28px; max-width: 56ch; }
  .pk-ge-lede b { color: var(--ink); }
  .pk-ge-bar-wrap { position: relative; padding-top: 30px; }
  .pk-ge-bar { display: flex; height: 26px; border-radius: 4px; overflow: hidden; gap: 2px; background: var(--line-soft); }
  .pk-ge-seg { min-width: 2px; }
  .pk-ge-maj { position: absolute; top: 0; bottom: -6px; width: 0; border-left: 2px dashed var(--ink); }
  .pk-ge-maj span {
    position: absolute; top: 0; left: 8px; white-space: nowrap;
    font-family: var(--mono); font-size: 12px; letter-spacing: .06em; color: var(--ink);
  }
  .pk-ge-legend { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; margin: 26px 0 0; }
  .pk-ge-legend-title { margin: 0 0 10px; font-size: 14px; color: var(--muted); }
  .pk-ge-legend-title b { color: var(--ink); margin-left: 4px; }
  .pk-ge-legend ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px 18px; }
  .pk-ge-legend li { display: inline-flex; align-items: center; gap: 7px; font-size: 14px; color: var(--ink-secondary); }
  .pk-ge-legend li b { color: var(--ink); font-variant-numeric: tabular-nums; }
  .pk-ge-sw { width: 10px; height: 10px; border-radius: 2px; }
  .pk-ge-caveat { margin: 26px 0 8px; font-size: 14px; line-height: 1.55; color: var(--muted); max-width: 70ch; }
  .pk-ge-link {
    display: inline-flex; align-items: center; gap: 6px; min-height: 44px;
    color: var(--accent); font-weight: 600; text-decoration: none; overflow-wrap: anywhere;
  }
  .pk-ge-link:hover { text-decoration: underline; }
  .pk-ge-link:focus-visible, .pk-ge-btn:focus-visible, .pk-ge-submit:focus-visible,
  .pk-ge-locate:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
  .pk-ge-find { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 40px; align-items: start; }
  .pk-ge-label { display: block; font-size: 14px; color: var(--muted); margin-bottom: 6px; }
  .pk-ge-input-row { display: flex; align-items: center; gap: 12px; border-bottom: 2px solid var(--ink); }
  .pk-ge-input-row input {
    flex: 1; min-width: 0; border: 0; background: transparent; color: var(--ink); outline: 0;
    padding: 10px 0; font-family: var(--font-display); font-size: 34px; letter-spacing: .04em;
  }
  .pk-ge-input-row input::placeholder { color: var(--muted); opacity: .7; }
  .pk-ge-submit {
    display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px;
    border: 0; border-radius: 50%; background: var(--accent); color: #172324; cursor: pointer; font-size: 20px;
  }
  .pk-ge-locate {
    margin-top: 12px; min-height: 44px; padding: 0 16px; border: 1px solid var(--line-strong);
    border-radius: 999px; background: transparent; color: var(--ink); font: inherit; font-size: 14px; cursor: pointer;
  }
  .pk-ge-locate:hover { border-color: var(--accent); }
  .pk-ge-hint { margin: 12px 0 0; font-size: 13px; line-height: 1.5; color: var(--muted); }
  .pk-ge-form .pk-lookup-results { margin-top: 16px; color: #172324; }
  .pk-ge-form .pk-lookup-results[hidden] { display: none; }
  .pk-ge-form .pk-lookup-skeleton, .pk-ge-form .pk-lookup-ambiguous,
  .pk-ge-form .pk-lookup-not-found, .pk-ge-form .pk-lookup-resolved {
    padding: 14px 16px; border-radius: 8px; background: var(--accent);
  }
  .pk-ge-form .pk-lookup-not-found { background: #e4efb2; }
  .pk-ge-form .pk-lookup-candidate {
    display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; min-height: 44px;
    padding: 9px 11px; border-bottom: 1px solid #20312b55; color: inherit;
  }
  .pk-ge-form .pk-lookup-candidate:last-child { border-bottom: 0; }
  .pk-ge-form .pk-lookup-candidate-code { font-family: var(--mono); font-size: 12px; opacity: .7; }
  .pk-ge-form .pk-lookup-candidate-name { font-size: 15px; font-weight: 600; }
  .pk-ge-form .pk-lookup-candidate-mp { width: 100%; font-size: 13px; opacity: .8; }
  .pk-ge-form .pk-lookup-ambiguous-heading, .pk-ge-form .pk-lookup-no-match-reason,
  .pk-ge-form .pk-lookup-status, .pk-ge-form .pk-lookup-footnote { font-size: 14px; line-height: 1.55; }
  .pk-ge-form .pk-lookup-routes { margin: 10px 0 0; padding-left: 18px; line-height: 1.9; font-size: 14px; }
  .pk-ge-form .pk-lookup-results a { color: inherit; }
  .pk-ge-follow { display: flex; align-items: center; justify-content: space-between; gap: 28px; }
  .pk-ge-follow .pk-ge-sub { margin-bottom: 0; }
  .pk-ge-btn {
    display: inline-flex; align-items: center; gap: 10px; min-height: 52px; padding: 0 24px; flex: none;
    border-radius: 999px; background: var(--accent); color: #172324; font-weight: 700; font-size: 16px;
    text-decoration: none;
  }
  .pk-ge-btn .pk-ge-ico { width: 20px; height: 20px; }
  .pk-ge-btn:hover { filter: brightness(1.06); }
  .pk-ge-foot { border-bottom: 0; }
  .pk-ge-foot-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 40px; }
  .pk-ge-foot p { margin: 0; font-size: 15px; line-height: 1.6; color: var(--ink-secondary); }
  .pk-ge-foot p.pk-ge-eyebrow { margin-bottom: 8px; font-size: 12px; color: var(--muted); }
  /* Below 1001px the card's own labels would scale under 9px, so the plain
     list takes over there and the card takes over above it. */
  @media (max-width: 1000px) { .pk-pipe, .pk-ge-art { display: none; } .pk-ge-hero-grid { grid-template-columns: minmax(0, 1fr); } }
  @media (min-width: 1001px) { .pk-ge-steps { display: none; } }
  @media (max-width: 760px) {
    .pk-ge-wrap { padding: 0 var(--gutter-mobile, 18px); }
    .pk-ge-hero { padding: 40px 0; }
    .pk-ge-hero h1 { font-size: var(--text-h1-mobile, 34px); margin-bottom: 20px; }
    .pk-ge-count-cap { font-size: 16px; }
    .pk-ge-clock { gap: 18px; }
    .pk-ge-unit b { font-size: 24px; }
    .pk-ge-band { padding: 40px 0; }
    .pk-ge-band h2 { font-size: 24px; }
    .pk-ge-lede { font-size: 17px; }
    .pk-ge-steps { grid-template-columns: minmax(0, 1fr); gap: 22px; }
    .pk-ge-steps::before { left: 7px; right: auto; top: 8px; bottom: 8px; width: 2px; height: auto; }
    .pk-ge-step { display: grid; grid-template-columns: 16px minmax(0, 1fr); column-gap: 16px; row-gap: 2px; padding: 0; }
    .pk-ge-step-mark { grid-row: 1 / span 2; margin: 3px 0 0; }
    .pk-ge-step-date { font-size: 18px; }
    .pk-ge-legend, .pk-ge-find, .pk-ge-foot-grid { grid-template-columns: minmax(0, 1fr); gap: 24px; }
    .pk-ge-follow { flex-direction: column; align-items: stretch; }
    .pk-ge-btn { justify-content: center; }
    .pk-ge-input-row input { font-size: 28px; }
  }
"""


def render_pru16_body(model: Pru16Model, language: Language = Language.EN) -> str:
    """The page's `body_html`, without the shell."""
    return (
        f"<style>{_CSS}</style>"
        f"{_hero(model, language)}"
        f"{_dates(model, language)}"
        f"{_projection(model, language)}"
        f"{_lookup(language)}"
        f"{_follow(language)}"
        f"{_sources(model, language)}"
        f"{_SCRIPT}"
    )


def render_pru16_page(model: Pru16Model, language: Language = Language.EN) -> str:
    """The page as one full HTML document, shell included."""
    title = t(
        language,
        "GE16: has it been called? Countdown and key dates | PolitikKu",
        "PRU16: sudah diisytiharkan? Kiraan hari dan tarikh penting | PolitikKu",
    )
    description = t(
        language,
        "Whether GE16 has been called, how many days are left, the key dates, and "
        "where the Seat Projection stands. Updated from official announcements.",
        "Sama ada PRU16 sudah diisytiharkan, berapa hari lagi, tarikh penting, dan "
        "kedudukan Unjuran kerusi. Dikemas kini daripada pengumuman rasmi.",
    )
    return render_shell(
        title=title,
        description=description,
        active_nav="pru16",
        language=language,
        page_path=PAGE_PATH,
        updated_at=model.computed_at or model.today,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_pru16_body(model, language),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the GE16 page")
    parser.add_argument("--output-dir", type=Path, default=Path("public"))
    parser.add_argument(
        "--art",
        choices=("skyline", "arc", "both", "none"),
        default="skyline",
        help="Which hero artwork to draw (an experiment switch).",
    )
    parser.add_argument(
        "--page-dir",
        default="pru16",
        help="Folder name under the output directory, so variants can sit side by side.",
    )
    args = parser.parse_args()

    model = pru16_model(art=args.art)
    for language in Language:
        base = args.output_dir if language is Language.EN else args.output_dir / "ms"
        target = base / args.page_dir / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = render_pru16_page(model, language)
        target.write_text(content, encoding="utf-8")
        print(f"Wrote {target} ({len(content):,} bytes)")


if __name__ == "__main__":
    main()
