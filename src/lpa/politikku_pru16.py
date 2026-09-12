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


def pru16_model(
    *,
    status: ElectionStatus | None = None,
    now: datetime | None = None,
    coalitions: Sequence[CoalitionRow] | None = None,
    computed_at: date | None = None,
    projection_path: Path = PROJECTION_JSON,
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
        '<div class="pk-ge-wrap">'
        f'<p class="pk-ge-eyebrow">{eyebrow}</p>'
        f'<p class="pk-ge-chip pk-ge-chip-{state}">'
        f'<span class="pk-ge-dot" aria-hidden="true"></span>{chip}</p>'
        f'<h1 id="pk-ge-h1">{heading}</h1>'
        f"{count}"
        f'<p class="pk-ge-note">{note}</p>'
        "</div></section>"
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
        f'<ol class="pk-ge-steps">{steps}</ol></div></section>'
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
  var pad = function (v) { return v < 10 ? '0' + v : '' + v; };
  function tick() {
    var left = Math.max(Math.floor((target - Date.now()) / 1000), 0);
    var days = Math.floor(left / 86400);
    n.textContent = days;
    unit.textContent = el.getAttribute(days === 1 ? 'data-word-one' : 'data-word-many');
    h.textContent = pad(Math.floor(left % 86400 / 3600));
    m.textContent = pad(Math.floor(left % 3600 / 60));
    s.textContent = pad(left % 60);
  }
  tick();
  setInterval(tick, 1000);
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
  .pk-ge-band { padding: 52px 0; border-bottom: 1px solid var(--line-soft); }
  .pk-ge-band-alt { background: var(--paper-alt); }
  .pk-ge-band h2 { font-size: 28px; line-height: 1.15; letter-spacing: -.015em; margin: 0 0 8px; color: var(--ink); }
  .pk-ge-sub { margin: 0 0 24px; font-size: 16px; line-height: 1.55; color: var(--ink-secondary); max-width: 60ch; }
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
    args = parser.parse_args()

    model = pru16_model()
    for language in Language:
        base = args.output_dir if language is Language.EN else args.output_dir / "ms"
        target = base / "pru16" / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = render_pru16_page(model, language)
        target.write_text(content, encoding="utf-8")
        print(f"Wrote {target} ({len(content):,} bytes)")


if __name__ == "__main__":
    main()
