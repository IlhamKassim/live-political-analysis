"""The PolitikKu landing page at the site root (ADR 0017).

Renders `/` (English) and `/ms/` (Bahasa Malaysia) from
`docs/design/landing-page-spec.md`. ADR 0014 made the `mypolitik` SPA the
site root so a visitor got the interactive tool immediately, and named the
loss of a general on-ramp as a deliberate, accepted gap. This page reopens
that gap: a visitor gets a plain-language orientation, a working Seat
lookup, and real projection and Parliament data, with the map one click
away at `/app/` — its first time actually living at that path.

**This is the site's front door, not a one-time gate.** It shows on every
visit to `/`. ADR 0017 originally skipped it for returning visitors via a
`pk-landing-seen` localStorage flag; that was removed (see the ADR's
revision note and `DEEP_LINK_SCRIPT` below). The only client-side
redirect left forwards `/#<hash>` deep links to `/app/#<hash>`.

Decisions here that are easy to undo by accident:

1. **No app chrome.** `render_shell(chrome=False)` — no sidebar, no topbar.
   A visitor who has not entered the app yet should not be framed inside
   the app's internal navigation; with it the page reads as an empty
   dashboard tab. The head, the tokens and the methodology footer still
   come from the shell, so this is a layout opt-out, not a second design
   system (ADR 0015).
2. **Build-time bake-in, not a client fetch.** Every figure on this page is
   read while it renders — `public/projection.json` for the Seat totals,
   `frontend/public/data/bills.json` for the Bills — the way
   `politikku_bills.py` reads its own data, rather than fetched in the
   browser the way `politikku_learn.py`'s `initLiveMajority()` does. It
   removes a first-paint fetch race from the one page a first-time visitor
   sees first, and makes each section's fallback free: a section whose data
   will not read simply does not render.
3. **`pk-not-calibrated`, not `not_calibrated_tag()`.** The helper in
   `politikku_i18n.py` emits `class="pk-tag-modelled"`, which has no CSS
   rule anywhere in this repo and no call sites — it would render the tag
   as unstyled body text. `politikku_shell.py`'s `.pk-not-calibrated`
   (`_CSS_TEMPLATE`, used inline by the methodology footer) is the live
   one. The settled EN/BM wording still comes from `politikku_i18n.py`.
4. **FACT and MODEL are labelled separately, per section.** The Majority
   bar and the Seat-projection teaser are modelled, so each carries the
   NOT CALIBRATED tag inline. The Bill tracker teaser is Parliament's own
   record — factual — and carries no tag. Tagging it would be as wrong as
   leaving the projection untagged.
5. **Coalition colours and Government membership are read, never
   restated.** Colours come from `frontend/public/lib.js` via
   `lpa.coalition_colors.load_coalition_colors()` (the same table the SPA
   draws its map with) and Government Coalition membership from
   `data/coalitions.json`. A hardcoded `{"PH": "#d7263d", ...}` here is how
   the landing page and the map end up disagreeing about what colour PH is.

The Seat lookup is server-rendered markup only. Behaviour comes from
`public/lookup.js` (built from `ts/src/`, loaded by `render_shell` on every
page); this module renders the `data-pk-lookup-*` contract that
`ts/src/dom.ts` mounts onto, and nothing else.
"""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from lpa.bill_tracker import Bill
from lpa.domain import ElectionStatus
from lpa.politikku_i18n import (
    NOT_CALIBRATED_EN,
    NOT_CALIBRATED_MS,
    POSTCODE_OR_CONSTITUENCY_EN,
    POSTCODE_OR_CONSTITUENCY_MS,
    USE_MY_LOCATION_EN,
    USE_MY_LOCATION_MS,
)
from lpa.politikku_shell import (
    APP_URL,
    LANDING_PAGE,
    Language,
    _en_route,
    _ms_route,
    render_shell,
    route,
    t,
)

PAGE_PATH = LANDING_PAGE
"""`""` — `route()` resolves it to `/` (EN) and `/ms/` (BM). Taken from the
shell rather than restated so `landing_url()`, this page's own canonical
URL, and its hreflang alternates cannot drift apart."""

"""`APP_URL` is imported from `politikku_shell` rather than restated here:
the map link on this page and the `map` nav item on every other page must
resolve to the same path, and two copies of "/app/" is how they drift."""

PROJECTION_JSON = Path("public/projection.json")
"""Written by `python -m lpa.public_export` earlier in the same workflow
run."""

BILLS_JSON = Path("frontend/public/data/bills.json")
"""The same file `lpa.bill_tracker` reads and `app.js` fetches — read here
too rather than via Storage, for the identical reason that module gives:
two renderings of the same Bill must not be able to disagree."""

TEASER_BILL_COUNT = 2
"""How many Bills the tracker teaser shows. Two, not five: this is a
pointer at `/bills/`, and a longer list starts competing with the Seat
lookup for the same attention."""

TEASER_COALITIONS: tuple[str, ...] = ("PH", "BN", "PN", "GPS", "GRS")
"""The Seat-projection teaser's rows, in `CONTEXT.md`'s own order — its
`Coalition` entry names exactly these as "the five that matter". Minor
parties and independents still count toward the Majority bar's totals
above; they are simply not given a row of their own here."""

CONTEXT_MD = "https://raw.githubusercontent.com/IlhamKassim/live-political-analysis/main/CONTEXT.md"
"""The glossary's citation target, matching `politikku_learn.py`'s existing
`data-claim`/`data-cite` convention so "sourced from CONTEXT.md" is a
checkable attribute rather than a claim in a comment."""


@dataclass(frozen=True)
class CoalitionRow:
    """One Coalition's projected Seat total, with the colour the map draws
    it in and whether it sits in the Government Coalition."""

    code: str
    seats: int
    color: str
    government: bool


@dataclass(frozen=True)
class LandingModel:
    """The data backing `/` and `/ms/`.

    Every data-bearing field is independently optional, and each section
    renders only if its own data read succeeded. That is deliberate: a day
    when `public_export` fails should cost the Majority bar and the
    projection teaser, not the Bills teaser, the Seat lookup, the glossary
    or the page. `government_majority` being `None` in particular is not an
    error state to report — the spec is explicit that a first-time visitor
    must not be able to tell a fallback is a fallback, so nothing
    downstream may branch on it to render an apology.
    """

    government_majority: bool | None
    coalitions: tuple[CoalitionRow, ...]
    bills: tuple[Bill, ...]
    majority_threshold: int
    total_seats: int
    updated_at: date
    sources_count: int
    status: ElectionStatus

    @property
    def has_live_call(self) -> bool:
        return self.government_majority is not None

    @property
    def has_seat_totals(self) -> bool:
        return bool(self.coalitions)

    @property
    def government_seats(self) -> int:
        return sum(c.seats for c in self.coalitions if c.government)

    @property
    def nongovernment_seats(self) -> int:
        return sum(c.seats for c in self.coalitions if not c.government)

    @property
    def counted_seats(self) -> int:
        """What the Coalition totals actually add up to.

        Used as the bar's denominator instead of `total_seats`, so the
        segments always fill it exactly. If the export ever publishes
        totals that do not sum to 222, the bar stays honest about its own
        arithmetic rather than silently leaving a gap the reader would
        read as "undecided Seats".
        """
        return sum(c.seats for c in self.coalitions)

    def teaser_rows(self) -> tuple[CoalitionRow, ...]:
        """`TEASER_COALITIONS`, in that order, skipping any the export did
        not publish."""
        by_code = {c.code: c for c in self.coalitions}
        return tuple(by_code[code] for code in TEASER_COALITIONS if code in by_code)


# ── Reading the data ──────────────────────────────────────────────────────


def _read_projection(
    path: Path = PROJECTION_JSON,
) -> tuple[bool | None, Mapping[str, int], date | None]:
    """`government_majority`, `coalition_seat_totals` and `computed_at`.

    Returns empty/`None` values for every failure mode — no file,
    unreadable file, invalid JSON, missing or wrongly-typed key. The caller
    has one fallback branch per section, not one per failure mode, because
    the page has one fallback rendering per section.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, {}, None
    if not isinstance(raw, dict):
        return None, {}, None

    majority = raw.get("government_majority")
    if not isinstance(majority, bool):
        majority = None

    totals_raw = raw.get("coalition_seat_totals")
    totals: dict[str, int] = {}
    if isinstance(totals_raw, dict):
        # Zero-seat Coalitions are dropped rather than drawn: the export
        # publishes a row for every party it knows about, most of which win
        # nothing, and a 0px bar segment is noise in the legend.
        totals = {
            str(k): int(v)
            for k, v in totals_raw.items()
            if isinstance(v, int) and not isinstance(v, bool) and v > 0
        }

    computed_at: date | None = None
    try:
        computed_at = date.fromisoformat(str(raw["computed_at"]))
    except (KeyError, TypeError, ValueError):
        computed_at = None

    return majority, totals, computed_at


def _coalition_rows(totals: Mapping[str, int]) -> tuple[CoalitionRow, ...]:
    """Totals as drawable rows: Government Coalitions first, each side
    ordered by Seats descending.

    That order is the bar's reading order — safest-Government on the left
    running to safest Non-government on the right — the same single axis
    `CONTEXT.md`'s `Non-government` entry describes the public chamber as
    having.
    """
    if not totals:
        return ()
    from lpa.coalition_colors import party_color
    from lpa.config import load_coalition_config

    try:
        government = frozenset(load_coalition_config()["government_coalitions"])
    except (OSError, KeyError, TypeError, ValueError):
        government = frozenset()

    rows = [
        CoalitionRow(
            code=code,
            seats=seats,
            color=party_color(code),
            government=code in government,
        )
        for code, seats in totals.items()
    ]
    rows.sort(key=lambda r: (not r.government, -r.seats, r.code))
    return tuple(rows)


def _read_bills(path: Path = BILLS_JSON, limit: int = TEASER_BILL_COUNT) -> tuple[Bill, ...]:
    """The most recent Bills by stage date, newest first.

    Same sort key `bills_page_model` uses, so the teaser's two rows are the
    top two rows of `/bills/` and a reader who follows the link sees the
    same Bills in the same order.
    """
    from lpa.config import load_bills

    try:
        bills = load_bills(path)
    except (OSError, KeyError, TypeError, ValueError):
        return ()
    ordered = sorted(bills.values(), key=lambda b: (b.stage_date, b.code), reverse=True)
    return tuple(ordered[:limit])


def _outlets_count() -> int:
    """How many news outlets the Scraper is configured to read.

    The footer's trust language and this count both describe the site, not
    this page. Counted from `data/outlets.json` — the file `CONTEXT.md`'s
    News Sentiment entry names as the record of which outlets are read —
    because this page reads no database. That is the configured set, not a
    per-run tally, which is why this is a documented function rather than
    an inline `len()` that would read as a stronger claim than it is.
    """
    from lpa.config import load_outlets

    try:
        return len(load_outlets())
    except (OSError, KeyError, TypeError, ValueError):
        return 0


def landing_model(
    government_majority: bool | None = None,
    coalitions: Sequence[CoalitionRow] | None = None,
    bills: Sequence[Bill] | None = None,
    updated_at: date | None = None,
    sources_count: int | None = None,
    status: ElectionStatus | None = None,
) -> LandingModel:
    """Build the model for the landing page.

    Every argument defaults to a real read, so `main()` can call this with
    none of them and a test can pass all of them and touch no file — the
    same shape as `bills_page_model`/`sentiment_page_model`.
    """
    from lpa.config import load_coalition_config, load_election_status
    from lpa.domain import TOTAL_SEATS
    from lpa.pipeline import today_in_malaysia

    computed_at: date | None = None
    if government_majority is None or coalitions is None:
        read_majority, totals, computed_at = _read_projection()
        if government_majority is None:
            government_majority = read_majority
        if coalitions is None:
            coalitions = _coalition_rows(totals)

    if bills is None:
        bills = _read_bills()

    if updated_at is None:
        updated_at = computed_at if computed_at is not None else today_in_malaysia()

    if sources_count is None:
        sources_count = _outlets_count()

    if status is None:
        status = load_election_status()

    try:
        threshold = int(load_coalition_config()["majority_threshold"])
    except (OSError, KeyError, TypeError, ValueError):
        threshold = 112

    return LandingModel(
        government_majority=government_majority,
        coalitions=tuple(coalitions),
        bills=tuple(bills),
        majority_threshold=threshold,
        total_seats=TOTAL_SEATS,
        updated_at=updated_at,
        sources_count=sources_count,
        status=status,
    )


# ── The deep-link forwarder ───────────────────────────────────────────────

DEEP_LINK_SCRIPT = """
<script>
(function () {
  try {
    if (location.hash) { location.replace('__APP_URL__' + location.hash); return; }
  } catch (e) {}
})();
</script>
"""
"""Forwards `/#<hash>` to `/app/#<hash>`, and does nothing else.

Every SPA deep link (`politikku.my/#parlimen/parti`, `/#seat-P.102`) was a
root URL until ADR 0017 moved the SPA to `/app/`. Without this the whole
existing set of shared links, bookmarks and indexed results would land on
the landing page carrying a fragment that means nothing here.

Two properties are load-bearing:

- **It runs before `_language_persistence_script`.** That script redirects
  on `location.pathname` alone, so a deep link reaching it first would
  arrive at `/ms/` with the fragment already dropped. See `render_shell`'s
  `extra_head_script` docstring.
- **`location.replace`, never `.href`.** No extra history entry, so Back
  from `/app/` leaves the site rather than bouncing off the landing page —
  matching every other redirect in this codebase.

**This is deliberately not a gate.** ADR 0017 originally shipped a
`pk-landing-seen` flag in `localStorage` that sent a returning visitor
straight to `/app/`, so the landing page was shown exactly once, plus a
`pk-landing-lang-switch` marker to stop that flag hijacking the language
toggle. Both are gone: the landing page is the site's front door and shows
on every visit to `/`. Do not reintroduce a "seen" flag without reading
ADR 0017's revision note first — the skip is what made the language toggle
unusable, and re-adding it re-adds that bug along with a second piece of
storage state to keep in step.

Anything that fails here fails silently into showing the landing page,
which is the correct page for `/` to show.
"""


def deep_link_script(app_url: str = APP_URL) -> str:
    """`DEEP_LINK_SCRIPT` with its redirect target substituted in."""
    return DEEP_LINK_SCRIPT.replace("__APP_URL__", app_url)


# ── Rendering ─────────────────────────────────────────────────────────────

_LANDING_CSS = """
  /* On :root, not on .pk-landing: the page header is a *sibling* of the
     content column, and custom properties only inherit downward — declared
     on .pk-landing it never reached .pk-top, whose max-width then computed
     to `none`. Both share the token from here. */
  :root { --pk-col: 1100px; }

  /* ── Page header (not the app's topbar — see render_shell(chrome=False)) */
  /* Three columns, not space-between: the outer two are equal `1fr`, so the
     wordmark is centred against the *header*, not against whatever is left
     over beside the toggle. The toggle stays pinned right on the same row. */
  .pk-top {
    display: grid; grid-template-columns: 1fr auto 1fr;
    align-items: center; gap: 12px;
    /* width:100% is load-bearing beside `margin: 0 auto`. #app is a column
       flex container, and auto margins on a flex item make it shrink-to-fit
       its content instead of filling to max-width — which collapsed this
       header into a narrow island floating above the content column. */
    width: 100%; max-width: var(--pk-col); margin: 0 auto;
    padding: 18px var(--gutter-mobile);
  }
  .pk-top-word { grid-column: 2; justify-self: center; }
  .pk-top .lang-seg { grid-column: 3; justify-self: end; }
  .pk-top-word {
    font-family: var(--font-display); font-size: 21px; color: var(--ink);
    text-decoration: none;
  }
  .pk-top-word b { font-weight: 400; color: var(--accent); }
  /* The shell sizes its language toggle under `.sb-lang`/`.topbar-lang`,
     both of which are chrome this page does not render — `.seg` alone
     gives a border and no padding, which collapses EN/BM into "ENBM".
     Same visual result, scoped to this page's own header. */
  .pk-top .lang-seg a {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 40px; min-height: 40px; padding: 6px 11px;
    font-family: var(--mono); font-size: 11px; font-weight: 600;
    color: var(--muted); text-decoration: none;
    transition: background .15s ease, color .15s ease;
  }
  .pk-top .lang-seg a:hover:not(.on) { color: var(--ink); background: var(--surface-hover); }
  /* rgba(255,255,255,.15), not --surface-hover-2 (.08): the same overlay
     `.sb-lang a.on` uses. At .08 the selected chip is 1.2:1 against the
     page — legible text, but a selected state a sighted reader has to
     hunt for. aria-current carries it for everyone else. */
  .pk-top .lang-seg a.on {
    background: rgba(255, 255, 255, .15); color: var(--ink); font-weight: 700;
  }
  .pk-top .lang-seg a:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }

  .pk-landing { max-width: var(--pk-col); margin: 0 auto; padding: 8px var(--gutter-mobile) 56px; }
  .pk-landing-section { margin-top: 44px; }
  .pk-landing-section > h2 {
    margin: 0 0 4px; font-size: 22px; line-height: 1.2; color: var(--ink);
  }
  .pk-section-note {
    margin: 0 0 16px; font-size: 13px; line-height: 1.5; color: var(--muted);
  }

  /* ── Hero ─────────────────────────────────────────────────────────── */
  .pk-hero { max-width: 720px; }
  .pk-hero-kicker { display: block; }
  .pk-hero h1 {
    margin: 8px 0 0;
    font-size: var(--text-hero-mobile); line-height: 1.06;
    letter-spacing: -.01em; color: var(--ink); text-wrap: balance;
  }
  .pk-hero-deck {
    margin: 12px 0 0; max-width: 46ch;
    font-size: 15px; line-height: 1.6; color: var(--ink-secondary);
  }

  /* ── Seat lookup ──────────────────────────────────────────────────── */
  .pk-lookup { margin-top: 24px; max-width: 560px; }
  .pk-lookup-label {
    display: block; margin-bottom: 8px;
    font-size: 10.5px; text-transform: uppercase; letter-spacing: .09em;
    font-weight: 600; color: var(--muted);
  }
  .pk-lookup-form { display: flex; flex-wrap: wrap; gap: 8px; }
  .pk-lookup-form input[type="search"] {
    flex: 1 1 220px; min-width: 0; min-height: 48px; padding: 12px 14px;
    background: var(--paper-alt); color: var(--ink);
    border: 1px solid var(--line-strong); border-radius: var(--radius-md);
    font-family: var(--sans); font-size: 16px;
    transition: border-color .15s ease;
  }
  .pk-lookup-form input[type="search"]::placeholder { color: var(--muted); }
  .pk-lookup-form input[type="search"]:hover { border-color: var(--muted); }
  .pk-lookup-form input[type="search"]:focus-visible {
    border-color: var(--accent); outline: 2px solid var(--accent); outline-offset: 1px;
  }
  /* dom.ts flags a typed query the index rejected. Caution, never error-red. */
  .pk-lookup-form input.pk-lookup-input-error { border-color: var(--caution); }
  .pk-search-btn {
    flex: 0 0 auto; min-height: 48px; padding: 12px 22px;
    border: 1px solid var(--accent); border-radius: var(--radius-md);
    background: var(--accent); color: var(--paper);
    font-family: var(--sans); font-size: 15px; font-weight: 600; cursor: pointer;
    transition: background .15s ease, border-color .15s ease, transform .06s ease;
  }
  .pk-search-btn:hover {
    background: color-mix(in oklab, var(--accent) 86%, var(--ink));
    border-color: color-mix(in oklab, var(--accent) 86%, var(--ink));
  }
  .pk-search-btn:active { transform: translateY(1px); }
  .pk-search-btn:focus-visible { outline: 3px solid var(--ink); outline-offset: 3px; }
  .pk-locate-btn {
    flex: 0 0 auto; min-height: 48px; padding: 12px 16px;
    border: 1px solid var(--line-strong); border-radius: var(--radius-md);
    background: transparent; color: var(--ink-secondary);
    font-family: var(--sans); font-size: 14px; cursor: pointer;
    transition: background .15s ease, color .15s ease, border-color .15s ease;
  }
  .pk-locate-btn:hover {
    background: var(--surface-hover); color: var(--ink); border-color: var(--muted);
  }
  .pk-locate-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .pk-lookup-hint { margin: 8px 0 0; font-size: 12.5px; color: var(--muted); }

  /* The results area is the one part of this page Python never renders —
     dom.ts owns its contents. These rules style what it emits. */
  .pk-lookup-results { margin-top: 14px; }
  .pk-lookup-results[hidden] { display: none; }
  .pk-lookup-skeleton, .pk-lookup-ambiguous, .pk-lookup-not-found, .pk-lookup-resolved {
    padding: 14px 16px; background: var(--surface-soft);
    border: 1px solid var(--line); border-radius: 12px;
  }
  .pk-lookup-not-found { border-color: var(--caution-border); background: var(--caution-bg); }
  .pk-lookup-skeleton-bars { display: flex; flex-direction: column; gap: 7px; }
  .pk-lookup-skeleton-bar {
    height: 10px; border-radius: 999px; background: var(--line-strong);
    animation: pk-pulse 1.1s ease-in-out infinite;
  }
  .pk-lookup-skeleton-bar:nth-child(2) { width: 72%; }
  .pk-lookup-skeleton-bar:nth-child(3) { width: 48%; }
  @keyframes pk-pulse { 50% { opacity: .45; } }
  .pk-lookup-status { margin: 10px 0 0; font-size: 13px; color: var(--ink-secondary); }
  .pk-lookup-ambiguous-heading { margin: 0 0 10px; font-size: 14px; color: var(--ink); }
  .pk-lookup-candidate-list { display: flex; flex-direction: column; gap: 6px; }
  .pk-lookup-candidate {
    display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px;
    min-height: 44px; padding: 9px 11px;
    border: 1px solid var(--line); border-radius: 10px;
    color: var(--ink); text-decoration: none;
    transition: background .15s ease, border-color .15s ease;
  }
  .pk-lookup-candidate:hover { background: var(--surface-hover); border-color: var(--line-strong); }
  .pk-lookup-candidate:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .pk-lookup-candidate[aria-disabled="true"] { opacity: .62; cursor: default; }
  .pk-lookup-candidate-code { font-family: var(--mono); font-size: 12px; color: var(--muted); }
  .pk-lookup-candidate-name { font-size: 14.5px; font-weight: 600; }
  .pk-lookup-candidate-mp { font-size: 13px; color: var(--ink-secondary); margin-left: auto; }
  .pk-lookup-no-match-tag {
    display: inline-block; font-family: var(--mono); font-size: 10.5px; font-weight: 600;
    letter-spacing: .06em; text-transform: uppercase; color: var(--caution);
  }
  .pk-lookup-no-match-reason { margin: 6px 0 0; font-size: 13.5px; line-height: 1.55; color: var(--ink); }
  .pk-lookup-routes { margin: 10px 0 0; padding-left: 18px; font-size: 13px; line-height: 1.9; }
  .pk-lookup-footnote { margin: 10px 0 0; font-size: 12px; color: var(--muted); }
  .pk-lookup-resolved-link { font-size: 15px; font-weight: 600; }
  .pk-lookup-resolved-no-profile { margin: 0; font-size: 14px; color: var(--ink-secondary); }

  .pk-hero-secondary {
    display: inline-flex; align-items: center; min-height: 44px; margin-top: 4px;
    font-size: 14px; color: var(--accent);
    border-bottom: 1px solid color-mix(in oklab, var(--accent) 40%, transparent);
    transition: border-bottom-color .15s ease;
  }
  .pk-hero-secondary:hover { border-bottom-color: var(--accent); }

  /* ── The Majority bar ─────────────────────────────────────────────── */
  .pk-maj { margin-top: 40px; gap: 12px; }
  .pk-maj-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; }
  .pk-maj-call { margin: 0; font-size: 17px; line-height: 1.5; color: var(--ink); }
  .pk-maj-tag {
    font-family: var(--mono); font-size: 10.5px; font-weight: 600;
    letter-spacing: .06em; white-space: nowrap;
  }
  /* The clipping lives on the track, not the bar: `overflow: hidden` here
     would cut off both the threshold marker (which deliberately overhangs
     the bar by 5px each way) and its label entirely. */
  .pk-maj-bar { position: relative; width: 100%; height: 34px; }
  .pk-maj-track {
    display: flex; width: 100%; height: 100%;
    border-radius: 6px; overflow: hidden; background: var(--line-soft);
  }
  .pk-maj-seg { height: 100%; box-shadow: inset -1px 0 0 rgba(11, 14, 19, .55); }
  .pk-maj-seg:last-child { box-shadow: none; }
  /* The 112 line sits ON the bar because that is the whole point of the
     graphic: which side of it the Government block ends. */
  .pk-maj-mark {
    position: absolute; top: -5px; bottom: -5px; width: 2px;
    background: var(--ink); border-radius: 1px;
  }
  .pk-maj-mark-label {
    position: absolute; top: 100%; margin-top: 7px; transform: translateX(-50%);
    font-family: var(--mono); font-size: 10.5px; font-weight: 600;
    letter-spacing: .04em; color: var(--ink); white-space: nowrap;
  }
  .pk-maj-sides {
    display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 20px;
    margin-top: 26px;
  }
  .pk-maj-side { display: flex; align-items: baseline; gap: 8px; }
  .pk-maj-side-n { font-family: var(--mono); font-size: 21px; font-weight: 600; color: var(--ink); }
  .pk-maj-side-l { font-size: 12.5px; color: var(--ink-secondary); }
  .pk-maj-legend {
    display: flex; flex-wrap: wrap; gap: 6px 14px;
    margin-top: 4px; padding-top: 12px; border-top: 1px solid var(--line);
  }
  .pk-swatch {
    display: inline-block; width: 10px; height: 10px; border-radius: 2px;
    flex: 0 0 auto;
  }
  .pk-maj-legend-item {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--ink-secondary);
  }
  .pk-maj-legend-item b { font-family: var(--mono); font-weight: 600; color: var(--ink); }

  /* ── Data preview panels ──────────────────────────────────────────── */
  .pk-previews { display: grid; grid-template-columns: 1fr; gap: 14px; }
  .pk-preview { gap: 12px; }
  .pk-preview-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 10px; }
  .pk-preview-head h3 { margin: 0; font-family: var(--sans); font-size: 16px; font-weight: 600; color: var(--ink); }
  .pk-preview-more { font-size: 13px; margin-left: auto; }

  .pk-proj-rows { display: flex; flex-direction: column; gap: 9px; }
  .pk-proj-row { display: grid; grid-template-columns: 10px 46px 1fr auto; align-items: center; gap: 10px; }
  .pk-proj-code { font-family: var(--mono); font-size: 12.5px; color: var(--ink); }
  .pk-proj-track { height: 8px; border-radius: 999px; background: var(--line-soft); overflow: hidden; }
  /* display:block is load-bearing, not tidiness. The track is a grid item
     so it gets blockified for free; the fill inside it is not, and an
     inline span ignores width — every bar rendered at 0px until this line
     existed. */
  .pk-proj-fill { display: block; height: 100%; border-radius: 999px; }
  .pk-proj-n { font-family: var(--mono); font-size: 14px; font-weight: 600; color: var(--ink); }

  .pk-bill-rows { display: flex; flex-direction: column; gap: 10px; }
  .pk-bill-row { display: flex; flex-direction: column; gap: 5px; }
  .pk-bill-row + .pk-bill-row { padding-top: 10px; border-top: 1px solid var(--line); }
  .pk-bill-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .pk-bill-code { font-family: var(--mono); font-size: 12px; color: var(--muted); }
  .pk-bill-date { font-family: var(--mono); font-size: 11.5px; color: var(--muted); margin-left: auto; }
  .pk-bill-title { font-size: 13.5px; line-height: 1.5; color: var(--ink-secondary); }

  .pk-more-links { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-top: 16px; }
  .pk-more-links a {
    display: inline-flex; align-items: center; min-height: 44px; font-size: 13.5px;
  }

  /* ── Glossary ─────────────────────────────────────────────────────── */
  .pk-glossary dt {
    padding: 14px 16px; font-family: var(--sans); font-size: 14px;
    font-weight: 700; color: var(--ink);
  }
  .pk-glossary dd {
    padding: 14px 16px; text-align: left; font-size: 14.5px;
    line-height: 1.6; color: var(--ink-secondary); overflow-wrap: anywhere;
  }
  .pk-landing-more {
    display: inline-flex; align-items: center; min-height: 44px;
    margin-top: 4px; font-size: 13px; color: var(--accent);
    border-bottom: 1px solid color-mix(in oklab, var(--accent) 40%, transparent);
    transition: border-bottom-color .15s ease;
  }
  .pk-landing-more:hover { border-bottom-color: var(--accent); }

  .pk-sr {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
  }

  /* 640px is the shell's own structural breakpoint — no new one here. */
  @media (min-width: 640px) {
    .pk-top { padding: 22px var(--gutter-desktop); }
    .pk-landing { padding: 12px var(--gutter-desktop) 72px; }
    .pk-hero h1 { font-size: var(--text-hero-desktop); }
    .pk-maj-call { font-size: 19px; }
    .pk-previews { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
  }
  @media (max-width: 639px) {
    .pk-glossary { grid-template-columns: 1fr; }
    .pk-glossary dt {
      border-right: 0; border-bottom: 0; padding-bottom: 4px; white-space: normal;
    }
    .pk-glossary dd { padding-top: 0; }
    .pk-lookup-candidate-mp { margin-left: 0; width: 100%; }
  }
  /* The existing small-phone step-down. The headline is the elastic
     element above the fold: the lookup field's 48px target never gives. */
  @media (max-width: 380px) {
    .pk-hero h1 { font-size: 32px; }
    .pk-search-btn, .pk-locate-btn { flex: 1 1 auto; }
  }
  @media (prefers-reduced-motion: reduce) {
    .pk-search-btn, .pk-locate-btn, .pk-lookup-form input[type="search"],
    .pk-lookup-candidate, .pk-hero-secondary, .pk-landing-more { transition: none; }
    .pk-search-btn:active { transform: none; }
    .pk-lookup-skeleton-bar { animation: none; }
  }
"""


def _tag(language: Language) -> str:
    """The NOT CALIBRATED / BELUM DITENTUKUR tag, inline.

    The leading space is real, not decorative: without it the accessible
    name runs the preceding sentence and the tag together as one word.
    """
    return (
        ' <span class="pk-not-calibrated pk-maj-tag">'
        f"{html.escape(t(language, NOT_CALIBRATED_EN, NOT_CALIBRATED_MS))}</span>"
    )


def _cited(text: str, language: Language) -> str:
    """One glossary sentence, carrying `politikku_learn.py`'s citation
    attributes in English only.

    The English definitions are `CONTEXT.md`'s own wording. Their Malay
    counterparts are translations of it, so tagging them
    `data-cite="…/CONTEXT.md"` would assert a verbatim match against an
    English source that `lpa.citation_check` could only ever fail. The
    citation follows the claim it can actually verify.
    """
    escaped = html.escape(text)
    if language is not Language.EN:
        return escaped
    return f'<span data-claim data-cite="{CONTEXT_MD}">{escaped}</span>'


def render_page_header(language: Language) -> str:
    """The landing page's own full-width header.

    Not `render_topbar`: that is the app's internal navigation, and a
    visitor who has not entered the app yet should not be inside it. This
    carries the two things a gate page's header genuinely needs — identity,
    and the language switch — and nothing else. The `data-pk-set-lang`
    attributes are what `_language_persistence_script` reads on click, so
    the choice persists exactly as it does on every other page.
    """
    en_href = html.escape(_en_route(PAGE_PATH))
    ms_href = html.escape(_ms_route(PAGE_PATH))
    home_href = ms_href if language is Language.MS else en_href
    en_on = language is Language.EN
    return f"""<header class="pk-top">
  <a class="pk-top-word" href="{home_href}">Politik<b>Ku</b></a>
  <div class="seg lang-seg" role="group" aria-label="{
        html.escape(t(language, "Language", "Bahasa"))
    }">
    <a class="{"on lang-current" if en_on else ""}" href="{en_href}" data-pk-set-lang="en"{
        ' aria-current="page"' if en_on else ""
    }>EN</a>
    <a class="{"" if en_on else "on lang-current"}" href="{ms_href}" data-pk-set-lang="ms"{
        "" if en_on else ' aria-current="page"'
    }>BM</a>
  </div>
</header>"""


def render_hero(language: Language) -> str:
    """Kicker, headline, deck, and the Seat lookup as the primary action.

    The lookup markup is exactly `ts/src/dom.ts`'s mount contract —
    `data-pk-lookup-scope` wrapping `data-pk-lookup-form`,
    `data-pk-lookup-input`, `data-pk-locate` and `data-pk-lookup-results`.
    Rendered server-side and progressively enhanced: with JS off the form
    is still a labelled, submittable field rather than dead markup.

    The map link below it is a text link, not a second filled button. The
    lookup is this page's primary action now, and two competing primary
    CTAs above the fold is the exact anti-pattern the spec names.
    """
    kicker = t(language, "Live GE16 seat projection", "Unjuran kerusi PRU16 secara langsung")
    headline = t(
        language,
        "Malaysia's next election, projected seat by seat.",
        "Pilihan raya Malaysia seterusnya, diunjur kerusi demi kerusi.",
    )
    deck = t(
        language,
        "Every one of the 222 seats in the Dewan Rakyat, projected daily from its 2022 result "
        "and the political mood measured that day. Start with your own.",
        "Kesemua 222 kerusi Dewan Rakyat, diunjur setiap hari daripada keputusan 2022 dan "
        "suasana politik yang diukur pada hari itu. Mulakan dengan kerusi anda sendiri.",
    )
    label = t(language, "Find your Seat", "Cari kerusi anda")
    placeholder = t(language, POSTCODE_OR_CONSTITUENCY_EN, POSTCODE_OR_CONSTITUENCY_MS)
    search = t(language, "Search", "Cari")
    locate = t(language, USE_MY_LOCATION_EN, USE_MY_LOCATION_MS)
    hint = t(
        language,
        "A postcode can straddle two Seats — you will be shown every one it could fall in.",
        "Satu poskod boleh merentasi dua kerusi — anda akan ditunjukkan setiap kerusi yang "
        "mungkin.",
    )
    map_link = t(language, "Or explore the interactive map", "Atau terokai peta interaktif")

    return f"""
    <section class="pk-hero" aria-labelledby="pk-hero-h">
      <span class="bento-kicker pk-hero-kicker">{html.escape(kicker)}</span>
      <h1 id="pk-hero-h">{html.escape(headline)}</h1>
      <p class="pk-hero-deck">{html.escape(deck)}</p>

      <div class="pk-lookup" data-pk-lookup-scope>
        <label class="pk-lookup-label" for="pk-lookup-q">{html.escape(label)}</label>
        <form class="pk-lookup-form" data-pk-lookup-form role="search">
          <input id="pk-lookup-q" name="q" type="search" autocomplete="postal-code"
                 spellcheck="false" placeholder="{html.escape(placeholder)}"
                 data-pk-lookup-input>
          <button type="submit" class="pk-search-btn">{html.escape(search)}</button>
          <button type="button" class="pk-locate-btn" data-pk-locate>{html.escape(locate)}</button>
        </form>
        <p class="pk-lookup-hint">{html.escape(hint)}</p>
        <div class="pk-lookup-results" data-pk-lookup-results hidden></div>
      </div>

      <a class="pk-hero-secondary" href="{html.escape(APP_URL)}">{html.escape(map_link)} &rarr;</a>
    </section>"""


def render_majority_bar(model: LandingModel, language: Language) -> str:
    """The 112 bar: one stacked 222-seat axis, Government to Non-government,
    with the Majority threshold marked on it.

    Renders nothing at all when the Seat totals could not be read. That is
    the fallback: a bar with no data is not a bar, and an empty-looking
    panel would tell a first-time visitor the site is broken. The
    majority-call sentence survives on its own in that case (see
    `render_landing_body`).
    """
    if not model.has_seat_totals:
        return ""

    counted = model.counted_seats
    segments = "".join(
        f'<span class="pk-maj-seg" style="width:{c.seats / counted * 100:.4f}%;'
        f'background:{html.escape(c.color)}" title="{html.escape(c.code)}: {c.seats}"></span>'
        for c in model.coalitions
    )
    mark_pct = model.majority_threshold / counted * 100
    legend = "".join(
        f'<span class="pk-maj-legend-item">'
        f'<span class="pk-swatch" style="background:{html.escape(c.color)}"></span>'
        f"{html.escape(c.code)} <b>{c.seats}</b></span>"
        for c in model.coalitions
    )
    gov_label = t(language, "Government Coalition", "Gabungan Kerajaan")
    non_label = t(language, "Non-government", "Bukan kerajaan")
    majority_word = t(language, "Majority", "Majoriti")

    call = (
        t(
            language,
            "The Government Coalition is projected to hold its Majority.",
            "Gabungan Kerajaan diunjur mengekalkan Majoritinya.",
        )
        if model.government_majority
        else t(
            language,
            "The Government Coalition is projected to fall short of a Majority.",
            "Gabungan Kerajaan diunjur gagal mencapai Majoriti.",
        )
    )
    call_html = f'<p class="pk-maj-call">{html.escape(call)}{_tag(language)}</p>'

    bar_label = t(
        language,
        f"Projected seats: {gov_label} {model.government_seats}, "
        f"{non_label} {model.nongovernment_seats}, of {counted}.",
        f"Kerusi diunjur: {gov_label} {model.government_seats}, "
        f"{non_label} {model.nongovernment_seats}, daripada {counted}.",
    )

    return f"""
      <div class="bento-tile pk-maj">
        <div class="pk-maj-head">{call_html if model.has_live_call else ""}</div>
        <div class="pk-maj-bar" role="img" aria-label="{html.escape(bar_label)}">
          <div class="pk-maj-track">{segments}</div>
          <span class="pk-maj-mark" style="left:{mark_pct:.4f}%" aria-hidden="true"></span>
          <span class="pk-maj-mark-label" style="left:{mark_pct:.4f}%" aria-hidden="true">{
        html.escape(majority_word)
    } {model.majority_threshold}</span>
        </div>
        <div class="pk-maj-sides">
          <span class="pk-maj-side">
            <span class="pk-maj-side-n">{model.government_seats}</span>
            <span class="pk-maj-side-l">{html.escape(gov_label)}</span>
          </span>
          <span class="pk-maj-side">
            <span class="pk-maj-side-n">{model.nongovernment_seats}</span>
            <span class="pk-maj-side-l">{html.escape(non_label)}</span>
          </span>
        </div>
        <div class="pk-maj-legend">{legend}</div>
      </div>"""


def _projection_preview(model: LandingModel, language: Language) -> str:
    """The five Coalitions that matter, as coloured bars against the
    largest of them."""
    rows = model.teaser_rows()
    if not rows:
        return ""
    widest = max(r.seats for r in rows) or 1
    body = "".join(
        f'<div class="pk-proj-row">'
        f'<span class="pk-swatch" style="background:{html.escape(r.color)}"></span>'
        f'<span class="pk-proj-code">{html.escape(r.code)}</span>'
        f'<span class="pk-proj-track">'
        f'<span class="pk-proj-fill" style="width:{r.seats / widest * 100:.2f}%;'
        f'background:{html.escape(r.color)}"></span></span>'
        f'<span class="pk-proj-n">{r.seats}</span>'
        f"</div>"
        for r in rows
    )
    heading = t(language, "Seat projection", "Unjuran kerusi")
    note = t(language, "Projected seats, GE16", "Kerusi diunjur, PRU16")
    more = t(language, "Full ledger", "Lejar penuh")
    href = route(language, "", "/projection/")
    return f"""
      <article class="bento-tile pk-preview">
        <div class="pk-preview-head">
          <h3>{html.escape(heading)}</h3>
          <a class="pk-preview-more" href="{html.escape(href)}">{html.escape(more)} &rarr;</a>
        </div>
        <span class="bento-kicker">{html.escape(note)}{_tag(language)}</span>
        <div class="pk-proj-rows">{body}</div>
      </article>"""


def _bills_preview(model: LandingModel, language: Language) -> str:
    """The two most recent Bills, with Parliament's own stage label.

    No NOT CALIBRATED tag: this is Parliament's own register, factual, and
    tagging it would be as wrong as leaving the projection above untagged.
    `stage` is displayed verbatim in both languages — ADR 0010 — because it
    is Parliament's literal status word, not a category this pipeline
    invented an English gloss for.
    """
    if not model.bills:
        return ""
    from lpa.bill_tracker import bill_stage_style

    body = "".join(
        f'<div class="pk-bill-row">'
        f'<div class="pk-bill-meta">'
        f'<span class="pk-bill-code">{html.escape(b.code)}</span>'
        f'<span class="pill" style="{bill_stage_style(b.stage)}">{html.escape(b.stage)}</span>'
        f'<span class="pk-bill-date">{html.escape(b.stage_date.isoformat())}</span>'
        f"</div>"
        f'<span class="pk-bill-title">{html.escape(b.title)}</span>'
        f"</div>"
        for b in model.bills
    )
    heading = t(language, "Bill tracker", "Penjejak RUU")
    note = t(language, "Most recent in the Dewan Rakyat", "Terkini di Dewan Rakyat")
    more = t(language, "All Bills", "Semua RUU")
    href = route(language, "bills/")
    return f"""
      <article class="bento-tile pk-preview">
        <div class="pk-preview-head">
          <h3>{html.escape(heading)}</h3>
          <a class="pk-preview-more" href="{html.escape(href)}">{html.escape(more)} &rarr;</a>
        </div>
        <span class="bento-kicker">{html.escape(note)}</span>
        <div class="pk-bill-rows">{body}</div>
      </article>"""


def render_previews(model: LandingModel, language: Language) -> str:
    """The two data panels, plus a plain link row for the destinations that
    do not get one.

    Sentiment has no panel because it has no export to build one from — the
    figures live in Storage and reach the SPA through
    `politikku_sentiment.py` only (`mypolitik-new-views-spec.md` names this
    as the missing piece). A panel faked from nothing would be exactly the
    vanity metric the spec forbids, so it stays a link until the export
    exists.
    """
    panels = _projection_preview(model, language) + _bills_preview(model, language)
    if not panels:
        return ""
    heading = t(language, "What the site is tracking", "Apa yang dijejaki laman ini")
    note = t(
        language,
        "Projections updated daily. Parliamentary records reflect official sittings.",
        "Unjuran dikemas kini setiap hari. Rekod parlimen mencerminkan persidangan rasmi.",
    )
    links = (
        (route(language, "sentiment/"), t(language, "Sentiment", "Sentimen")),
        (route(language, "dewan/"), t(language, "Dewan", "Dewan")),
        (route(language, "politicians/"), t(language, "Politicians", "Ahli Politik")),
    )
    link_html = "".join(
        f'<a href="{html.escape(href)}">{html.escape(label)} &rarr;</a>' for href, label in links
    )
    return f"""
    <section class="pk-landing-section" aria-labelledby="pk-previews-h">
      <h2 id="pk-previews-h">{html.escape(heading)}</h2>
      <p class="pk-section-note">{html.escape(note)}</p>
      <div class="pk-previews">{panels}</div>
      <div class="pk-more-links">{link_html}</div>
    </section>"""


def render_glossary(language: Language) -> str:
    """Four terms, as a ruled definition list.

    `.rows`, not four more tiles: four tiles in a row read as a feature
    grid, and this is reference material. The English wording is
    `CONTEXT.md`'s own `## Language` entries, carried through `_cited()`.
    """
    heading = t(
        language,
        "Four words this site uses precisely",
        "Empat istilah yang digunakan dengan tepat di sini",
    )
    terms = (
        (
            t(language, "Seat", "Kerusi"),
            t(
                language,
                "One of the 222 parliamentary constituencies in the Dewan Rakyat. The unit an "
                "election is actually won or lost in.",
                "Satu daripada 222 kawasan parlimen di Dewan Rakyat. Unit sebenar tempat "
                "pilihan raya dimenangi atau tewas.",
            ),
        ),
        (
            t(language, "Coalition", "Gabungan"),
            t(
                language,
                "A group of parties that contests and governs together. The five that matter: "
                "PH, BN, PN, GPS, GRS.",
                "Kumpulan parti yang bertanding dan memerintah bersama. Lima yang penting: "
                "PH, BN, PN, GPS, GRS.",
            ),
        ),
        (
            t(language, "Majority", "Majoriti"),
            t(
                language,
                "Holding more than half of the 222 seats (112+). The threshold a Coalition "
                "needs to form government alone.",
                "Menguasai lebih separuh daripada 222 kerusi (112+). Ambang yang diperlukan "
                "sesebuah Gabungan untuk membentuk kerajaan sendirian.",
            ),
        ),
        (
            t(language, "Projection", "Unjuran"),
            t(
                language,
                "A seat-count estimate per Coalition for GE16, and whether the Government "
                "Coalition retains its Majority.",
                "Anggaran jumlah kerusi bagi setiap Gabungan untuk PRU16, dan sama ada "
                "Gabungan Kerajaan mengekalkan Majoritinya.",
            ),
        ),
    )
    rows = "".join(
        f"<dt>{html.escape(term)}</dt><dd>{_cited(definition, language)}</dd>"
        for term, definition in terms
    )
    more = (
        '\n      <a class="pk-landing-more" href="/learn/glossary.html">'
        "The full glossary &rarr;</a>"
        if language is Language.EN
        else ""
    )
    return f"""
    <section class="pk-landing-section" aria-labelledby="pk-glossary-h">
      <h2 id="pk-glossary-h">{html.escape(heading)}</h2>
      <dl class="rows pk-glossary">{rows}</dl>{more}
    </section>"""


def render_landing_body(model: LandingModel, language: Language = Language.EN) -> str:
    """The landing page's body HTML without the outer shell.

    No `<header>`/`<main>`/`<footer>` here: `render_shell` emits the `<main>`
    this sits inside and the `<footer>` below it, and the page's own
    `<header>` goes in through `header_html`. A second one of any of them
    would break the landmark structure for a screen reader.
    """
    bar = render_majority_bar(model, language)
    # The bar owns the majority-call sentence when it renders. With no Seat
    # totals there is no bar, so the sentence falls back to its own tile —
    # the reader still gets the one fact, just without the graphic.
    orphan_call = ""
    if not bar and model.has_live_call:
        call = (
            t(
                language,
                "The Government Coalition is projected to hold its Majority.",
                "Gabungan Kerajaan diunjur mengekalkan Majoritinya.",
            )
            if model.government_majority
            else t(
                language,
                "The Government Coalition is projected to fall short of a Majority.",
                "Gabungan Kerajaan diunjur gagal mencapai Majoriti.",
            )
        )
        orphan_call = (
            '\n      <div class="bento-tile pk-maj">'
            f'<p class="pk-maj-call">{html.escape(call)}{_tag(language)}</p></div>'
        )

    return f"""
<style>{_LANDING_CSS}</style>
<div class="pk-landing">
{render_hero(language)}
{bar}{orphan_call}
{render_previews(model, language)}
{render_glossary(language)}
</div>
""".strip()


def render_landing_page(model: LandingModel, language: Language = Language.EN) -> str:
    """Render the full HTML document for `/` / `/ms/`."""
    title = t(
        language,
        "PolitikKu — Malaysia's next election, projected seat by seat",
        "PolitikKu — Pilihan raya Malaysia seterusnya, diunjur kerusi demi kerusi",
    )
    description = t(
        language,
        "Find your Seat, then see how all 222 are projected for Malaysia's next general "
        "election — updated daily, with every modelled number labelled as modelled.",
        "Cari kerusi anda, kemudian lihat unjuran kesemua 222 kerusi untuk pilihan raya umum "
        "Malaysia yang seterusnya — dikemas kini setiap hari, dengan setiap angka model "
        "dilabel sebagai angka model.",
    )
    return render_shell(
        title=title,
        description=description,
        # Irrelevant with chrome=False (nothing renders a nav item to mark),
        # but render_shell still requires it.
        active_nav="home",
        language=language,
        page_path=PAGE_PATH,
        updated_at=model.updated_at,
        sources_count=model.sources_count,
        status=model.status,
        body_html=render_landing_body(model, language),
        extra_head_script=deep_link_script(),
        chrome=False,
        header_html=render_page_header(language),
    )


def build_and_write_landing_pages(output_dir: Path | str = "public") -> tuple[int, int]:
    """Render and write both languages: `public/index.html` (the site root)
    and `public/ms/index.html`. Both paths are already in `.gitignore`,
    named against this module — the Action publishes them, the repo does
    not carry them."""
    model = landing_model()
    out = Path(output_dir)

    en_html = render_landing_page(model, Language.EN)
    en_path = out / "index.html"
    en_path.parent.mkdir(parents=True, exist_ok=True)
    en_path.write_text(en_html, encoding="utf-8")

    ms_html = render_landing_page(model, Language.MS)
    ms_path = out / "ms" / "index.html"
    ms_path.parent.mkdir(parents=True, exist_ok=True)
    ms_path.write_text(ms_html, encoding="utf-8")

    return len(en_html.encode("utf-8")), len(ms_html.encode("utf-8"))


def main() -> None:
    """CLI entry point to render the landing page."""
    parser = argparse.ArgumentParser(description="Render the PolitikKu landing page.")
    parser.add_argument(
        "--output-dir",
        default="public",
        help="Directory to write output files (default: public)",
    )
    args = parser.parse_args()

    en_size, ms_size = build_and_write_landing_pages(args.output_dir)
    print(
        f"Wrote {args.output_dir}/index.html ({en_size:,} bytes) and "
        f"{args.output_dir}/ms/index.html ({ms_size:,} bytes)"
    )


if __name__ == "__main__":
    main()
