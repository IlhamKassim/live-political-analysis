"""PolitikKu: design tokens, self-hosted fonts, and the persistent site shell.

The header, trust strip, EN/BM toggle and methodology footer are the chrome
every PolitikKu screen shares (#72, part of #69's design handoff). Built once
here so #74 (homepage), #75 (landing page) and #79 (MP profile page) each
wrap their own body content in `render_shell` rather than re-deriving it.

Follows ADR 0006's precedent (`public_page.py`): Python renders static HTML,
no build step. This is a deliberately separate visual identity from the
existing chamber dashboard, not a replacement of it — see #70's resolution.
The dashboard's party-colour tokens (`--ph`/`--pn`/`--bn`/`--gps`/`--grs`)
have no equivalent here; the handoff is explicit that PolitikKu carries no
party colours at all.

Every value below is taken from `design_handoff_politikku/README.md`'s
Design Tokens table and the inline styles in `PolitikKu Homepage.dc.html`
(ids 1a/3a) — this module does not invent a palette. Two deliberate
deviations from the handoff's literal copy, both because the handoff's
sample data is not this repo's real data (README's own "Fidelity" section
says as much for other fields):

- The handoff's trust strip reads "Updated 23 Aug 2026, 06:00 MYT". This
  repo's daily Action actually runs at 23:00 MYT (`pipeline.py`'s
  `MALAYSIA_TIME`), and `PageModel.computed_at`/callers of this module only
  carry a date, not a time. Stating a specific clock time this code cannot
  verify would violate trust rule 2 (every factual figure carries a real
  source) for the sake of matching a mockup's invented timestamp, so the
  strip states the date and timezone and no fabricated clock time.
- Desktop nav is a real link row (`<a href>`), not the mockup's plain
  `<span>` — this is production markup, and the nav needs to actually
  navigate.

Routing (not specified by #72's body — the handoff only tells the toggle to
link to real routes, not what they are — so this is a scoped, reversible
call rather than a mechanical translation of a given value): new pages live
under `/politikku/`, English at `/politikku/<page>` and Bahasa Malaysia at
`/politikku/ms/<page>`, all root-relative (the whole site now serves from
one domain per `public/CNAME`). `public/index.html` — the existing chamber
dashboard — is left untouched at `/`; "Seat Projection" in the nav links
there since that page already *is* the full seat-level projection the
handoff's own "Full projection →" link means. Bills/Sentiment/Methodology
point at pages later tickets have not built yet, same as the handoff itself
asks for ("wired to routes that don't need to exist yet").
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from lpa.domain import ElectionStatus

DASHBOARD_URL = "/"
"""The existing chamber dashboard (`public_page.py`) — unmoved by this
initiative. See #70's "stand alongside" resolution."""

LANDING_URL = "/politikku/landing.html"
"""`politikku_landing.py`'s own page (#75) — not in `NAV_LINKS` (it's a
first-visit door, not a nav destination), so it needs a link from
somewhere. The persistent footer's own "way back to it" link is that
somewhere, per #75's own routing note. Defined here, not on
`politikku_landing`, so both directions of the reference (footer -> landing,
landing -> its own path) read from the one constant rather than two copies
of the same string."""


class Language(StrEnum):
    """The two languages a PolitikKu page can be served in.

    Chrome-only for now (#72's scope excludes translated copy, which is
    #81's job) — this only drives which toggle link is current and which
    route prefix a page's other links resolve under, not the strings shown.
    """

    EN = "en"
    MS = "ms"


@dataclass(frozen=True)
class NavLink:
    """One item in the persistent header nav."""

    label: str
    href: str
    key: str
    """Identifies this link for the `active_nav` comparison — stable even if
    `label` changes once #81 translates it."""


NAV_LINKS: tuple[NavLink, ...] = (
    NavLink("Home", "/politikku/", "home"),
    NavLink("Seat Projection", DASHBOARD_URL, "projection"),
    NavLink("Bills", "/politikku/bills.html", "bills"),
    NavLink("Sentiment", "/politikku/sentiment.html", "sentiment"),
    NavLink("Methodology", "/politikku/methodology.html", "methodology"),
)


def _en_route(page_path: str) -> str:
    return f"/politikku/{page_path}"


def _ms_route(page_path: str) -> str:
    return f"/politikku/ms/{page_path}"


def short_date(day: date) -> str:
    """`23 Aug 2026` — the trust strip's date format, abbreviated month."""
    return f"{day.day} {day.strftime('%b %Y')}"


def trust_strip_status_text(status: ElectionStatus) -> str:
    """The Election Status as the trust strip's one-line form.

    A compact sibling of `public_page.status_sentence`, not a reuse of it —
    that function writes a standfirst sentence; this is a strip item a few
    words wide. Same discipline: never guesses a date that is not set.
    """
    if not status.called:
        return f"GE16 not yet called — constitutional deadline {short_date(status.constitutional_deadline)}"
    if status.polling_date is None:
        return f"GE16 called, dissolved {short_date(status.dissolved_on)} — polling day not yet announced"  # type: ignore[arg-type]
    return f"GE16 called — polling {short_date(status.polling_date)}"


_ARIA_CURRENT_PAGE = ' aria-current="page"'


def _link(*, href: str, label: str, css_class: str, current: bool) -> str:
    """One `<a>` tag, escaped, with `aria-current="page"` when it's the
    current page — factored out because pre-3.12 f-strings cannot contain a
    backslash-escaped quote inside a `{}` expression."""
    aria = _ARIA_CURRENT_PAGE if current else ""
    cls = f' class="{css_class}"' if css_class else ""
    return f'<a{cls} href="{html.escape(href)}"{aria}>{html.escape(label)}</a>'


def _lang_toggle(language: Language, page_path: str) -> str:
    en_href = _en_route(page_path)
    ms_href = _ms_route(page_path)
    en_current = language is Language.EN
    ms_current = language is Language.MS
    en_link = _link(
        href=en_href, label="EN", css_class="lang-current" if en_current else "", current=en_current
    )
    ms_link = _link(
        href=ms_href, label="BM", css_class="lang-current" if ms_current else "", current=ms_current
    )
    return f'<div class="lang-toggle" role="group" aria-label="Language">{en_link}{ms_link}</div>'


def render_header(*, active_nav: str, language: Language, page_path: str) -> str:
    """The 56px navy header: wordmark, nav, EN/BM toggle.

    `active_nav` is a `NavLink.key` (e.g. `"home"`) — the current page's nav
    item, underlined per the handoff's id-1a header. Nav collapses to a
    `<details>` disclosure below 900px (`_CSS`) rather than hidden JS: the
    links stay real and reachable with no script, matching this ticket's
    EN/BM-toggle accessibility requirement extended to the rest of the nav.
    """
    links_html = "".join(
        _link(
            href=link.href,
            label=link.label,
            css_class="active" if link.key == active_nav else "",
            current=link.key == active_nav,
        )
        for link in NAV_LINKS
    )
    return f"""
<header class="pk-header">
  <div class="pk-header-left">
    <a class="wordmark" href="/politikku/">PolitikKu</a>
    <nav class="pk-nav" aria-label="Primary">{links_html}</nav>
  </div>
  <details class="pk-nav-mobile">
    <summary aria-label="Menu">
      <span></span><span></span><span></span>
    </summary>
    <nav aria-label="Primary (mobile)">{links_html}</nav>
  </details>
  {_lang_toggle(language, page_path)}
</header>
""".strip()


def render_trust_strip(
    *,
    updated_at: date,
    sources_count: int,
    status: ElectionStatus,
    methodology_href: str = "/politikku/methodology.html",
) -> str:
    """The persistent trust strip — appears on every PolitikKu page.

    Desktop shows all three items; the `<= 900px` rule in `_CSS` condenses
    it to just the date and a "Sources" link, per the handoff's mobile trust
    strip ("Updated 06:00 MYT today" + "Sources").
    """
    updated = html.escape(short_date(updated_at))
    sources_word = "source" if sources_count == 1 else "sources"
    status_text = html.escape(trust_strip_status_text(status))
    methodology = html.escape(methodology_href)
    return f"""
<div class="pk-trust-strip">
  <span class="pk-trust-full">
    <span>Updated {updated}, MYT</span>
    <span class="pk-dot">·</span>
    <span>{sources_count} news {sources_word} read</span>
    <span class="pk-dot">·</span>
    <span>{status_text}</span>
  </span>
  <span class="pk-trust-condensed">Updated {updated}, MYT</span>
  <a class="pk-trust-link" href="{methodology}">How this works</a>
</div>
""".strip()


@dataclass(frozen=True)
class SourceGroup:
    """One column of the methodology footer's source lists."""

    heading: str
    sources: Sequence[str]


FACTUAL_SOURCES = SourceGroup(
    "Factual data",
    ("Election Commission (SPR)", "Dewan Rakyat Hansard", "parlimen.gov.my"),
)
MODELLED_SOURCES = SourceGroup(
    "Modelled inputs",
    ("News outlets, EN + BM", "Merdeka Center polling", "GE15 Baseline + state results"),
)
"""`MODELLED_SOURCES`' first line drops the handoff's hardcoded "9" (outlet
count) — that number belongs to whichever page wires in real data (#74),
not this static footer, and going stale the day an outlet is added or
dropped from `data/outlets.json` would itself be a trust-rule violation."""


def render_methodology_footer(
    *,
    methodology_href: str = "/politikku/methodology.html",
    factual: SourceGroup = FACTUAL_SOURCES,
    modelled: SourceGroup = MODELLED_SOURCES,
) -> str:
    """The navy 3-column footer: methodology statement, factual sources,
    modelled sources. Persistent chrome, same as the header."""
    factual_items = "".join(f"<span>{html.escape(s)}</span>" for s in factual.sources)
    modelled_items = "".join(f"<span>{html.escape(s)}</span>" for s in modelled.sources)
    href = html.escape(methodology_href)
    landing_href = html.escape(LANDING_URL)
    return f"""
<footer class="pk-footer">
  <div class="pk-footer-statement">
    <div class="pk-footer-heading">Methodology &amp; sources</div>
    <p>Seat Calls are model-driven and <span class="pk-not-calibrated">not calibrated</span>
    against survey data. MP records, GE15 results and bill status are factual and sourced
    below. Everything here is open source.</p>
    <a class="pk-footer-link" href="{href}">Read the full methodology →</a>
    <a class="pk-footer-link" href="{landing_href}">What is PolitikKu? →</a>
  </div>
  <div class="pk-footer-col">
    <div class="pk-footer-label">{html.escape(factual.heading)}</div>
    <div class="pk-footer-list">{factual_items}</div>
  </div>
  <div class="pk-footer-col">
    <div class="pk-footer-label">{html.escape(modelled.heading)}</div>
    <div class="pk-footer-list">{modelled_items}</div>
  </div>
</footer>
""".strip()


def render_shell(
    *,
    title: str,
    active_nav: str,
    language: Language,
    page_path: str,
    updated_at: date,
    sources_count: int,
    status: ElectionStatus,
    body_html: str,
) -> str:
    """Wrap `body_html` in the full PolitikKu page: head, header, trust
    strip, `body_html` untouched, methodology footer.

    `body_html` is the one thing this function does not decide — #74/#75/#79
    each render their own body and pass it straight through, per #72's
    "not in scope: actual page content."
    """
    header = render_header(active_nav=active_nav, language=language, page_path=page_path)
    trust_strip = render_trust_strip(
        updated_at=updated_at, sources_count=sources_count, status=status
    )
    footer = render_methodology_footer()
    lang_attr = "ms" if language is Language.MS else "en"
    return f"""<!doctype html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preload" href="/politikku/fonts/newsreader-variable.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/politikku/fonts/ibm-plex-sans-variable.woff2" as="font" type="font/woff2" crossorigin>
<style>{_CSS}</style>
</head>
<body>
{header}
{trust_strip}
{body_html}
{footer}
</body>
</html>
"""


_CSS = """
  @font-face {
    font-family: 'Newsreader';
    font-style: normal;
    font-weight: 400 600;
    font-display: swap;
    src: url('/politikku/fonts/newsreader-variable.woff2') format('woff2');
    unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC,
      U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
  }
  @font-face {
    font-family: 'IBM Plex Sans';
    font-style: normal;
    font-weight: 400 600;
    font-display: swap;
    src: url('/politikku/fonts/ibm-plex-sans-variable.woff2') format('woff2');
    unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC,
      U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
  }
  @font-face {
    font-family: 'IBM Plex Mono';
    font-style: normal;
    font-weight: 400;
    font-display: swap;
    src: url('/politikku/fonts/ibm-plex-mono-400.woff2') format('woff2');
  }
  @font-face {
    font-family: 'IBM Plex Mono';
    font-style: normal;
    font-weight: 500;
    font-display: swap;
    src: url('/politikku/fonts/ibm-plex-mono-500.woff2') format('woff2');
  }

  :root {
    /* Design tokens — design_handoff_politikku/README.md, "Design Tokens" */
    --ink:            #14203a;
    --ink-secondary:  #5f6773;
    --muted:          #8a9099;
    --paper:          #fbfaf7;
    --paper-alt:      #f4f2ec;
    --white:          #ffffff;
    --line:           #dcd8cf;
    --line-soft:      #ece8df;
    --line-strong:    #c9c4b8;
    --accent:         #1f5c58;
    --accent-on-dark: #a9cdc9;
    --caution:        #8a6a2f;
    --caution-deep:   #7a5c1e;
    --caution-bg:     #f0e6d2;
    --caution-border: #e0d2b4;
    --positive-bg:     #eef3f0;
    --positive-border: #cfe0da;
    --data-government:    #14203a;
    --data-noise:          #d6d1c6;
    --data-nongovernment:  #93a0ac;
    --on-dark-body:   #b9c0cc;
    --on-dark-muted:  #7d8697;
    --nav-active-rule: #7fa8a4;

    --serif: 'Newsreader', ui-serif, Georgia, 'Times New Roman', serif;
    --sans:  'IBM Plex Sans', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
    --mono:  'IBM Plex Mono', ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace;

    --radius-sm: 3px;
    --radius-md: 4px;
    --radius-lg: 5px;

    /* Spacing — README's "Spacing" section. Only the two constants this
       ticket's own components actually need are promoted to tokens: the
       horizontal gutter, held constant across every band regardless of
       section (only the vertical padding varies 38–46px/22–28px per
       section, which is a per-section design call, not a shared constant),
       and the 4px base unit, named here for later pages to build multiples
       of rather than inventing their own increment. */
    --space-unit: 4px;
    --gutter-desktop: 30px;
    --gutter-mobile:  18px;

    /* Typography — README's "Typography" role table. Only the two roles
       given as an exact desktop/mobile pair are promoted (Landing hero,
       Page h1) — #74/#75 will use these directly. The other roles (Section
       h2, Card h3, Body, Caption) are given as ranges (e.g. 13.5–15px),
       and this ticket's own header/trust-strip/footer sizes are drawn from
       the id=1a inline styles, not from that range table, and don't map
       onto it cleanly (the footer statement paragraph is 12.5px, smaller
       than the Body role's own stated 13.5–15px floor) — turning an
       inconsistent source into one false-precise token per role would
       assert a system the handoff itself doesn't have, so those stay as
       literal values at their point of use. */
    --text-hero-desktop: 58px;
    --text-hero-mobile:  38px;
    --text-h1-desktop:   44px;
    --text-h1-mobile:    34px;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--sans);
    -webkit-font-smoothing: antialiased;
  }
  h1, h2, h3, p { text-wrap: pretty; }
  a { color: var(--accent); text-decoration: none; }

  /* Header */
  .pk-header {
    position: relative;
    background: var(--ink);
    color: var(--paper);
    height: 56px;
    padding: 0 var(--gutter-desktop);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
  }
  .pk-header-left { display: flex; align-items: baseline; gap: 26px; }
  .pk-header .wordmark {
    font-family: var(--serif);
    font-size: 21px;
    font-weight: 600;
    letter-spacing: -.01em;
    color: var(--paper);
  }
  .pk-nav { display: flex; gap: 20px; font-size: 13px; color: var(--on-dark-body); }
  .pk-nav a, .pk-nav-mobile nav a { color: inherit; }
  .pk-nav a.active {
    color: var(--paper);
    border-bottom: 2px solid var(--nav-active-rule);
    padding-bottom: 2px;
  }
  .pk-nav-mobile { display: none; }

  .lang-toggle {
    display: flex;
    border: 1px solid rgba(251, 250, 247, .28);
    border-radius: var(--radius-md);
    overflow: hidden;
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: .06em;
  }
  .lang-toggle a { padding: 5px 10px; color: var(--on-dark-body); }
  .lang-toggle a.lang-current { background: var(--paper); color: var(--ink); }

  /* Trust strip */
  .pk-trust-strip {
    background: var(--paper-alt);
    border-bottom: 1px solid var(--line);
    padding: 9px var(--gutter-desktop);
    display: flex;
    gap: 22px;
    align-items: center;
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink-secondary);
  }
  .pk-trust-full { display: flex; gap: 22px; align-items: center; }
  .pk-dot { color: #c6c1b6; }
  .pk-trust-condensed { display: none; }
  .pk-trust-link { margin-left: auto; color: var(--accent); border-bottom: 1px solid rgba(31, 92, 88, .4); }
  .pk-trust-link:hover { border-bottom-color: var(--accent); }

  /* Methodology footer */
  .pk-footer {
    background: var(--ink);
    color: var(--on-dark-body);
    padding: var(--gutter-desktop);
    display: grid;
    grid-template-columns: 1.4fr 1fr 1fr;
    gap: 36px;
  }
  .pk-footer-heading {
    font-family: var(--serif);
    font-size: 18px;
    color: var(--paper);
    margin-bottom: 8px;
  }
  .pk-footer-statement p { margin: 0; font-size: 12.5px; line-height: 1.6; }
  .pk-not-calibrated { color: #e3d3ac; }
  .pk-footer-link {
    display: inline-block;
    margin-top: 12px;
    margin-right: 18px;
    font-size: 12.5px;
    color: var(--accent-on-dark);
    border-bottom: 1px solid rgba(169, 205, 201, .4);
  }
  .pk-footer-label {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--on-dark-muted);
    margin-bottom: 9px;
  }
  .pk-footer-list { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; }

  /* Hemicycle (#73) — scale-free by its own viewBox; a page sets its own
     max-width/position/opacity for whichever of the three contexts it's
     reused in (this is just a sane block-level default, not a size). */
  .pk-hemicycle { display: block; width: 100%; height: auto; }

  /* NOT CALIBRATED tag, reused by any page built on this shell */
  .pk-tag-modelled {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .07em;
    text-transform: uppercase;
    color: var(--caution-deep);
    background: var(--caution-bg);
    border: 1px solid var(--caution-border);
    border-radius: var(--radius-sm);
    padding: 2px 6px;
  }

  @media (max-width: 900px) {
    .pk-header { padding: 0 var(--gutter-mobile); height: 52px; }
    .pk-header-left { gap: 12px; }
    .pk-nav { display: none; }
    .pk-nav-mobile { display: block; }
    .pk-nav-mobile summary {
      list-style: none;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 4px;
      width: 20px;
    }
    .pk-nav-mobile summary::-webkit-details-marker { display: none; }
    .pk-nav-mobile summary span { height: 1.5px; background: var(--paper); display: block; }
    .pk-nav-mobile nav {
      position: absolute;
      right: var(--gutter-mobile);
      top: 52px;
      background: var(--ink);
      border: 1px solid rgba(251, 250, 247, .18);
      border-radius: var(--radius-md);
      padding: 10px 0;
      display: flex;
      flex-direction: column;
      z-index: 10;
    }
    .pk-nav-mobile nav a { padding: 10px var(--gutter-mobile); font-size: 13px; }

    .pk-trust-strip { padding: 8px var(--gutter-mobile); font-size: 10.5px; }
    .pk-trust-full { display: none; }
    .pk-trust-condensed { display: inline; }
    .pk-trust-link { margin-left: auto; }

    .pk-footer {
      grid-template-columns: 1fr;
      gap: 24px;
      padding: 22px var(--gutter-mobile);
    }
  }
"""
