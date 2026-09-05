"""PolitikKu: design tokens, self-hosted fonts, and the persistent site shell.

The sidebar and topbar are the chrome every PolitikKu screen shares (#149).
Adopts the unified PolitikMY dark design across the entire site, retiring the
navy/paper shell (#148). The map SPA's sidebar and topbar chrome now frames every
page: Bills, Dewan, Politicians, Projection, Sentiment, and Learn.
"""

from __future__ import annotations

import html
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from lpa.domain import ElectionStatus

POLITIKKU_PREFIX = "/"
"""Where PolitikKu's own pages are served from — the site root."""

PROJECTION_PREFIX = "/projection/"
"""The ported projection detail page route."""

METHODOLOGY_PAGE = "methodology.html"
"""The page path (under POLITIKKU_PREFIX) for methodology."""

MP_PROFILE_DIR = "mp"
"""The directory MP profile pages live in, under POLITIKKU_PREFIX."""

BILLS_PAGE = "bills.html"
"""The legacy bill-tracker redirect path."""

LANDING_PAGE = ""
"""Landing page path (now site root)."""

LANDING_URL = f"{POLITIKKU_PREFIX}{LANDING_PAGE}"
"""The landing page URL."""

HOMEPAGE_PAGE = "home.html"
"""Retired homepage path kept for redirects."""


class Language(StrEnum):
    """The two languages a PolitikKu page can be served in."""

    EN = "en"
    MS = "ms"


def t(language: Language, en: str, ms: str) -> str:
    """Pick en or ms copy for language."""
    return en if language is Language.EN else ms


@dataclass(frozen=True)
class NavLink:
    """One item in the persistent site navigation."""

    label: str
    label_ms: str
    href: str
    key: str
    prefix: str = POLITIKKU_PREFIX
    en_only: bool = False
    external: str | None = None
    icon_svg: str = ""


_DEFAULT_NAV_ICON = (
    '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="12" cy="12" r="9"/></svg>'
)

NAV_LINKS: tuple[NavLink, ...] = (
    NavLink(
        "Map",
        "Peta",
        "",
        "map",
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="m8 4 8-2 5 2.5v15l-5-2.5-8 2-5-2.5v-15z"/><path d="M8 4v15"/><path d="M16 2v15"/>'
            '<path d="M5.7 11.5h4.1"/><path d="M14.2 7.5h4.1"/></svg>'
        ),
    ),
    NavLink(
        "Politicians",
        "Ahli Politik",
        "politicians/",
        "politicians",
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/>'
            '<path d="M16.8 4.4a3.5 3.5 0 0 1 0 5.2"/><path d="M18.7 15.2a6.3 6.3 0 0 1 2.8 5.8"/></svg>'
        ),
    ),
    NavLink(
        "Dewan",
        "Dewan",
        "dewan/",
        "dewan",
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M3 21h18"/><path d="M5 21V10M9.5 21V10M14.5 21V10M19 21V10"/><path d="M3 10h18l-9-6-9 6z"/></svg>'
        ),
    ),
    NavLink(
        "Projection",
        "Unjuran",
        "",
        "projection",
        prefix=PROJECTION_PREFIX,
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M3 13a9 9 0 1 0 18 0"/><path d="M12 13V4"/><path d="m8 8 4-4 4 4"/><circle cx="12" cy="13" r="2"/></svg>'
        ),
    ),
    NavLink(
        "Bills",
        "Rang Undang-Undang",
        "bills/",
        "bills",
        external="/bills/",
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>'
            '<path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>'
        ),
    ),
    NavLink(
        "Sentiment",
        "Sentimen",
        "sentiment/",
        "sentiment",
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>'
        ),
    ),
    NavLink(
        "Methodology",
        "Metodologi",
        METHODOLOGY_PAGE,
        "methodology",
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.2"/><circle cx="12" cy="7.6" r="0.7" fill="currentColor" stroke="none"/></svg>'
        ),
    ),
    NavLink(
        "Glossary",
        "Glosari",
        "learn/glossary.html",
        "glossary",
        en_only=True,
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><path d="M9 7h6M9 11h6"/></svg>'
        ),
    ),
    NavLink(
        "Coalitions",
        "Gabungan",
        "learn/coalitions.html",
        "coalitions",
        en_only=True,
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
        ),
    ),
    NavLink(
        "GE16 Process",
        "Proses PRU16",
        "learn/ge16-process.html",
        "process",
        en_only=True,
        icon_svg=(
            '<svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><path d="m9 16 2 2 4-4"/></svg>'
        ),
    ),
)


def _en_route(page_path: str, prefix: str = POLITIKKU_PREFIX) -> str:
    return f"{prefix}{page_path}"


def _ms_route(page_path: str, prefix: str = POLITIKKU_PREFIX) -> str:
    return f"{prefix}ms/{page_path}"


def route(language: Language, page_path: str, prefix: str = POLITIKKU_PREFIX) -> str:
    """page_path under prefix, in whichever language."""
    return _en_route(page_path, prefix) if language is Language.EN else _ms_route(page_path, prefix)


def methodology_url(language: Language = Language.EN) -> str:
    """Where 'how this works' points."""
    return route(language, METHODOLOGY_PAGE)


def projection_url(language: Language = Language.EN) -> str:
    """Where 'Seat Projection'/'Full projection' point."""
    return route(language, "", PROJECTION_PREFIX)


def landing_url(language: Language = Language.EN) -> str:
    """Where 'What is PolitikKu?' points."""
    return route(language, LANDING_PAGE)


def short_date(day: date) -> str:
    """23 Aug 2026 — abbreviated month."""
    return f"{day.day} {day.strftime('%b %Y')}"


def trust_strip_status_text(status: ElectionStatus, language: Language = Language.EN) -> str:
    """The Election Status as a one-line form."""
    if not status.called:
        deadline = short_date(status.constitutional_deadline)
        return t(
            language,
            f"GE16 not yet called — constitutional deadline {deadline}",
            f"PRU16 belum diisytiharkan — tarikh akhir perlembagaan {deadline}",
        )
    if status.polling_date is None:
        dissolved = short_date(status.dissolved_on)  # type: ignore[arg-type]
        return t(
            language,
            f"GE16 called, dissolved {dissolved} — polling day not yet announced",
            f"PRU16 diisytiharkan, dibubarkan {dissolved} — tarikh mengundi belum diumumkan",
        )
    polling = short_date(status.polling_date)
    return t(
        language, f"GE16 called — polling {polling}", f"PRU16 diisytiharkan — mengundi {polling}"
    )


_ARIA_CURRENT_PAGE = ' aria-current="page"'


def _link(*, href: str, label: str, css_class: str, current: bool, extra: str = "") -> str:
    aria = _ARIA_CURRENT_PAGE if current else ""
    cls = f' class="{css_class}"' if css_class else ""
    extra_attr = f' data-pk-set-lang="{extra}"' if extra else ""
    return f'<a{cls} href="{html.escape(href)}"{aria}{extra_attr}>{html.escape(label)}</a>'


def _lang_toggle(language: Language, page_path: str, prefix: str = POLITIKKU_PREFIX) -> str:
    en_href = _en_route(page_path, prefix)
    ms_href = _ms_route(page_path, prefix)
    en_current = language is Language.EN
    ms_current = language is Language.MS
    en_link = _link(
        href=en_href,
        label="EN",
        css_class="on lang-current" if en_current else "",
        current=en_current,
        extra="en",
    )
    ms_link = _link(
        href=ms_href,
        label="BM",
        css_class="on lang-current" if ms_current else "",
        current=ms_current,
        extra="ms",
    )
    return f'<div class="seg lang-seg sb-lang" role="group" aria-label="Language">{en_link}{ms_link}</div>'


_LANGUAGE_PERSISTENCE_SCRIPT_TEMPLATE = """
<script>
(function () {
  try {
    var stored = window.localStorage.getItem('pk-language');
    if (stored === 'en' || stored === 'ms') {
      var path = location.pathname;
      var current = path.indexOf('__PREFIX__ms/') === 0 ? 'ms' : 'en';
      if (stored !== current) {
        var target = stored === 'ms'
          ? path.replace('__PREFIX__', '__PREFIX__ms/')
          : path.replace('__PREFIX__ms/', '__PREFIX__');
        if (target !== path) { location.replace(target); return; }
      }
    }
  } catch (e) {}
  document.addEventListener('click', function (event) {
    var el = event.target.closest && event.target.closest('[data-pk-set-lang]');
    if (el) {
      try { window.localStorage.setItem('pk-language', el.getAttribute('data-pk-set-lang')); } catch (e) {}
    }
    var col = event.target.closest && event.target.closest('#sb-collapse');
    if (col) {
      document.body.classList.toggle('sb-collapsed');
    }
    var menuBtn = event.target.closest && event.target.closest('#mobile-menu-btn');
    if (menuBtn) {
      var menu = document.getElementById('mobile-menu');
      if (menu) {
        var open = menu.classList.toggle('is-open');
        menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      }
    }
  });
})();
</script>
"""


def _language_persistence_script(prefix: str = POLITIKKU_PREFIX) -> str:
    return _LANGUAGE_PERSISTENCE_SCRIPT_TEMPLATE.replace("__PREFIX__", prefix)


def render_sidebar(
    *, active_nav: str, language: Language, page_path: str, prefix: str = POLITIKKU_PREFIX
) -> str:
    """Render the SPA-matching sidebar navigation aside."""
    home_href = route(language, "")
    about_label = t(language, "About", "Tentang")
    about_href = methodology_url(language)

    def _nav_href(link: NavLink) -> str:
        return (
            link.external if link.external is not None else route(language, link.href, link.prefix)
        )

    items_html: list[str] = []
    for link in NAV_LINKS:
        if link.en_only and language is Language.MS:
            continue
        is_active = (link.key == active_nav) or (link.key == "map" and active_nav == "home")
        href = _nav_href(link)
        label = t(language, link.label, link.label_ms)
        icon = link.icon_svg or _DEFAULT_NAV_ICON
        aria_curr = ' aria-current="page"' if is_active else ""
        cls = "sb-item on" if is_active else "sb-item"
        items_html.append(
            f'<a id="sb-{link.key}" class="{cls}" href="{html.escape(href)}"{aria_curr} '
            f'aria-label="{html.escape(label)}">'
            f'<span class="sb-ic">{icon}</span>'
            f'<span class="sb-label">{html.escape(label)}</span></a>'
        )

    en_href = _en_route(page_path, prefix)
    ms_href = _ms_route(page_path, prefix)
    en_current = language is Language.EN
    ms_current = language is Language.MS
    en_class = "on lang-current" if en_current else ""
    ms_class = "on lang-current" if ms_current else ""
    en_aria = ' aria-current="page"' if en_current else ""
    ms_aria = ' aria-current="page"' if ms_current else ""

    en_link = (
        f'<a class="{en_class}" href="{html.escape(en_href)}" data-pk-set-lang="en"{en_aria}>EN</a>'
    )
    ms_link = (
        f'<a class="{ms_class}" href="{html.escape(ms_href)}" data-pk-set-lang="ms"{ms_aria}>BM</a>'
    )

    nav_aria = t(language, "Navigation", "Navigasi")
    whole_map_label = t(language, "Show the whole map", "Tunjukkan seluruh peta")
    toggle_sb_label = t(language, "Toggle sidebar", "Togol bar sisi")
    lang_aria = t(language, "Language", "Bahasa")

    return f"""<aside id="sidebar" aria-label="{nav_aria}">
  <div class="sb-top">
    <a id="sb-brand" class="sb-brand" href="{html.escape(home_href)}" aria-label="{whole_map_label}">
      <span class="brand-word">Politik<b>Ku</b></span>
    </a>
    <button id="sb-collapse" class="sb-collapse" type="button" aria-label="{toggle_sb_label}" title="{toggle_sb_label}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M9.5 4.5v15"/></svg>
    </button>
  </div>
  <nav class="sb-nav">
    {"".join(items_html)}
  </nav>
  <div class="sb-foot">
    <a id="sb-about" class="sb-item sb-small" href="{html.escape(about_href)}"><span>{html.escape(about_label)}</span></a>
    <div class="seg lang-seg sb-lang" role="group" aria-label="{lang_aria}">
      {en_link}
      {ms_link}
    </div>
  </div>
</aside>"""


def render_topbar(
    *,
    active_nav: str,
    language: Language,
    page_path: str,
    prefix: str = POLITIKKU_PREFIX,
    updated_at: date | None = None,
    sources_count: int | None = None,
    status: ElectionStatus | None = None,
) -> str:
    """Render the SPA-matching topbar header."""
    home_href = route(language, "")
    whole_map_label = t(language, "Show the whole map", "Tunjukkan seluruh peta")
    lang_aria = t(language, "Language", "Bahasa")
    open_menu_label = t(language, "Open menu", "Buka menu")
    mobile_actions_label = t(language, "Mobile actions", "Tindakan mudah alih")

    en_href = _en_route(page_path, prefix)
    ms_href = _ms_route(page_path, prefix)
    en_current = language is Language.EN
    ms_current = language is Language.MS
    en_class = "on lang-current" if en_current else ""
    ms_class = "on lang-current" if ms_current else ""
    en_aria = ' aria-current="page"' if en_current else ""
    ms_aria = ' aria-current="page"' if ms_current else ""

    en_link = (
        f'<a class="{en_class}" href="{html.escape(en_href)}" data-pk-set-lang="en"{en_aria}>EN</a>'
    )
    ms_link = (
        f'<a class="{ms_class}" href="{html.escape(ms_href)}" data-pk-set-lang="ms"{ms_aria}>BM</a>'
    )

    trust_html = ""
    if updated_at is not None and sources_count is not None and status is not None:
        trust_html = render_trust_strip(
            updated_at=updated_at,
            sources_count=sources_count,
            status=status,
            language=language,
        )

    def _nav_href(link: NavLink) -> str:
        return (
            link.external if link.external is not None else route(language, link.href, link.prefix)
        )

    mobile_items: list[str] = []
    for link in NAV_LINKS:
        if link.en_only and language is Language.MS:
            continue
        is_active = (link.key == active_nav) or (link.key == "map" and active_nav == "home")
        href = _nav_href(link)
        label = t(language, link.label, link.label_ms)
        icon = link.icon_svg or _DEFAULT_NAV_ICON
        aria_curr = ' aria-current="page"' if is_active else ""
        cls = "iconbtn on" if is_active else "iconbtn"
        mobile_items.append(
            f'<a id="top-{link.key}" class="{cls}" href="{html.escape(href)}"{aria_curr} '
            f'aria-label="{html.escape(label)}">{icon}<span>{html.escape(label)}</span></a>'
        )

    return f"""<header id="topbar" class="pk-header">
  <a id="brand-home" class="brand brand-home wordmark" href="{html.escape(home_href)}" aria-label="{whole_map_label}" title="{whole_map_label}">
    <span class="mark"><span class="brand-word">Politik<b>Ku</b></span></span>
  </a>
  <div id="topbar-context" class="topbar-context">
    <a id="topbar-title" class="topbar-title" href="{html.escape(home_href)}" aria-label="{whole_map_label}" title="PolitikKu">
      <span class="brand-word">Politik<b>Ku</b></span>
    </a>
  </div>
  {trust_html}
  <div class="topbar-end">
    <div class="seg lang-seg topbar-lang" id="lang" role="group" aria-label="{lang_aria}">
      {en_link}
      {ms_link}
    </div>
    <button id="mobile-menu-btn" class="iconbtn mobile-menu-btn" type="button" aria-label="{open_menu_label}" aria-controls="mobile-menu" aria-expanded="false">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><path d="M5 7h14"/><path d="M5 12h14"/><path d="M5 17h14"/></svg>
    </button>
  </div>
  <div id="mobile-menu" class="mobile-menu">
    <nav class="topicons" role="navigation" aria-label="{mobile_actions_label}">
      {"".join(mobile_items)}
    </nav>
  </div>
</header>"""


def render_header(
    *,
    active_nav: str,
    language: Language,
    page_path: str,
    prefix: str = POLITIKKU_PREFIX,
    updated_at: date | None = None,
    sources_count: int | None = None,
    status: ElectionStatus | None = None,
) -> str:
    """The persistent shell chrome: sidebar + topbar."""
    sidebar = render_sidebar(
        active_nav=active_nav, language=language, page_path=page_path, prefix=prefix
    )
    topbar = render_topbar(
        active_nav=active_nav,
        language=language,
        page_path=page_path,
        prefix=prefix,
        updated_at=updated_at,
        sources_count=sources_count,
        status=status,
    )
    return f"{sidebar}\n{topbar}"


def render_trust_strip(
    *,
    updated_at: date,
    sources_count: int,
    status: ElectionStatus,
    language: Language = Language.EN,
    methodology_href: str | None = None,
) -> str:
    """The persistent trust strip — appears inside the topbar."""
    updated = html.escape(short_date(updated_at))
    updated_word = t(language, "Updated", "Dikemas kini")
    sources_text = t(
        language,
        f"{sources_count} news source{'' if sources_count == 1 else 's'} read",
        f"{sources_count} sumber berita dibaca",
    )
    status_text = html.escape(trust_strip_status_text(status, language))
    methodology = html.escape(methodology_href or methodology_url(language))
    how_it_works = t(language, "How this works", "Cara ini berfungsi")
    return f"""<div class="topbar-trust">
  <span class="trust-full">
    <span class="trust-updated">{updated_word} {updated}, MYT</span>
    <span class="topbar-dot">·</span>
    <span class="trust-sources">{sources_text}</span>
    <span class="topbar-dot">·</span>
    <span class="trust-status">{status_text}</span>
  </span>
  <span class="trust-condensed">{updated_word} {updated}, MYT</span>
  <a class="trust-link" href="{methodology}">{how_it_works}</a>
</div>""".strip()


@dataclass(frozen=True)
class SourceGroup:
    """One column of the methodology footer's source lists."""

    heading: str
    heading_ms: str
    sources: Sequence[str]


FACTUAL_SOURCES = SourceGroup(
    "Factual data",
    "Data faktual",
    ("Election Commission (SPR)", "Dewan Rakyat Hansard", "parlimen.gov.my"),
)
MODELLED_SOURCES = SourceGroup(
    "Modelled inputs",
    "Input model",
    ("News outlets, EN + BM", "Merdeka Center polling", "GE15 Baseline + state results"),
)


def render_methodology_footer(
    *,
    language: Language = Language.EN,
    methodology_href: str | None = None,
    factual: SourceGroup = FACTUAL_SOURCES,
    modelled: SourceGroup = MODELLED_SOURCES,
) -> str:
    """Methodology statements and sources."""
    factual_items = "".join(f"<span>{html.escape(s)}</span>" for s in factual.sources)
    modelled_items = "".join(f"<span>{html.escape(s)}</span>" for s in modelled.sources)
    href = html.escape(methodology_href or methodology_url(language))
    landing_href = html.escape(landing_url(language))
    heading = t(language, "Methodology &amp; sources", "Metodologi &amp; sumber")
    statement = t(
        language,
        'Seat Calls are model-driven and <span class="pk-not-calibrated">not calibrated</span>'
        " against survey data. MP records, GE15 results and bill status are factual and sourced"
        " below. Everything here is open source.",
        'Keputusan Kerusi dijana oleh model dan <span class="pk-not-calibrated">'
        "belum ditentukur</span> terhadap data tinjauan. Rekod Ahli Parlimen, keputusan"
        " PRU15 dan status rang undang-undang adalah fakta dan disumberkan di bawah."
        " Semuanya di sini adalah sumber terbuka.",
    )
    read_methodology = t(language, "Read the full methodology →", "Baca metodologi penuh →")
    what_is_politikku = t(language, "What is PolitikKu? →", "Apakah itu PolitikKu? →")

    if language is Language.EN:
        learn_links = (
            '\n    <a class="pk-footer-link" href="/learn/glossary.html">Glossary →</a>'
            '\n    <a class="pk-footer-link" href="/learn/coalitions.html">Coalitions →</a>'
            '\n    <a class="pk-footer-link" href="/learn/ge16-process.html">GE16 Process →</a>'
        )
    else:
        learn_links = ""

    factual_heading = html.escape(t(language, factual.heading, factual.heading_ms))
    modelled_heading = html.escape(t(language, modelled.heading, modelled.heading_ms))
    return f"""<footer class="pk-footer">
  <div class="pk-footer-statement">
    <div class="pk-footer-heading">{heading}</div>
    <p>{statement}</p>
    <a class="pk-footer-link" href="{href}">{read_methodology}</a>
    <a class="pk-footer-link" href="{landing_href}">{what_is_politikku}</a>{learn_links}
  </div>
  <div class="pk-footer-col">
    <div class="pk-footer-label">{factual_heading}</div>
    <div class="pk-footer-list">{factual_items}</div>
  </div>
  <div class="pk-footer-col">
    <div class="pk-footer-label">{modelled_heading}</div>
    <div class="pk-footer-list">{modelled_items}</div>
  </div>
</footer>""".strip()


SITE_URL = "https://politikku.my/"


def render_shell(
    *,
    title: str,
    description: str,
    active_nav: str,
    language: Language,
    page_path: str,
    updated_at: date,
    sources_count: int,
    status: ElectionStatus,
    body_html: str,
    prefix: str = POLITIKKU_PREFIX,
) -> str:
    """Wrap body_html in the full PolitikKu page shell."""
    sidebar = render_sidebar(
        active_nav=active_nav, language=language, page_path=page_path, prefix=prefix
    )
    topbar = render_topbar(
        active_nav=active_nav,
        language=language,
        page_path=page_path,
        prefix=prefix,
        updated_at=updated_at,
        sources_count=sources_count,
        status=status,
    )
    lang_attr = "ms" if language is Language.MS else "en"
    escaped_title = html.escape(title)
    escaped_description = html.escape(description)
    og_url = html.escape(f"{SITE_URL.rstrip('/')}{route(language, page_path, prefix)}")

    en_url = html.escape(f"{SITE_URL.rstrip('/')}{_en_route(page_path, prefix)}")
    ms_url = html.escape(f"{SITE_URL.rstrip('/')}{_ms_route(page_path, prefix)}")

    og_image = html.escape(f"{SITE_URL}og-image.png")

    website_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "PolitikKu",
            "url": SITE_URL,
            "description": "A public reference for Malaysian politics",
            "inLanguage": ["en", "ms"],
        }
    )

    footer = render_methodology_footer(language=language)

    return f"""<!doctype html>
<html lang="{lang_attr}">
<head>
<meta charset="utf-8">
{_language_persistence_script(prefix)}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escaped_title}</title>
<meta name="description" content="{escaped_description}">
<meta property="og:title" content="{escaped_title}">
<meta property="og:description" content="{escaped_description}">
<meta property="og:url" content="{og_url}">
<meta property="og:type" content="website">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escaped_title}">
<meta name="twitter:description" content="{escaped_description}">
<meta name="twitter:image" content="{og_image}">
<link rel="canonical" href="{og_url}">
<link rel="alternate" hreflang="en" href="{en_url}">
<link rel="alternate" hreflang="ms" href="{ms_url}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="icon" href="{POLITIKKU_PREFIX}favicon.ico">
<style>{_CSS}</style>
<script type="application/ld+json">
{website_ld}
</script>
<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "5eadc388fb2a4518b8e846b059fb102c"}}'></script><!-- End Cloudflare Web Analytics --> <!-- gitleaks:allow -->
</head>
<body>
{sidebar}
<div id="app">
{topbar}
<main id="main-content">
{body_html}
</main>
{footer}
</div>
<script type="module" src="{POLITIKKU_PREFIX}lookup.js"></script>
</body>
</html>
"""


_CSS_TEMPLATE = """
  @font-face {
    font-family: "Space Grotesk";
    font-style: normal;
    font-weight: 300 700;
    font-display: swap;
    src: url(/fonts/space-grotesk-latin.woff2) format("woff2");
  }
  @font-face {
    font-family: "Space Grotesk";
    font-style: normal;
    font-weight: 300 700;
    font-display: swap;
    src: url(/fonts/space-grotesk-latinext.woff2) format("woff2");
    unicode-range: U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF;
  }
  @font-face {
    font-family: "Redaction 20";
    font-style: normal;
    font-weight: 400;
    font-display: swap;
    src: url(/fonts/redaction-20-latin.woff2) format("woff2");
  }
  @font-face {
    font-family: "Redaction 20";
    font-style: normal;
    font-weight: 700;
    font-display: swap;
    src: url(/fonts/redaction-20-bold-latin.woff2) format("woff2");
  }

  :root {
    --paper: #0b0e13;
    --paper-alt: #11151d;
    --white: #0e1219;
    --ink: #e7edf4;
    --ink-secondary: #93a1b3;
    --muted: #708096;
    --line: #1d2733;
    --line-soft: #161e28;
    --line-strong: #2a3645;
    --accent: #4dd6c1;
    --accent-on-dark: #4dd6c1;
    --caution: #ffd166;
    --caution-deep: #ffd166;
    --caution-bg: rgba(255, 209, 102, .12);
    --caution-border: rgba(255, 209, 102, .35);
    --positive-bg: rgba(77, 214, 193, .12);
    --positive-border: rgba(77, 214, 193, .35);
    --data-government: #e7edf4;
    --data-noise: #3a4757;
    --data-nongovernment: #7d8fa3;
    --on-dark-body: #93a1b3;
    --on-dark-muted: #708096;
    --nav-active-rule: #4dd6c1;

    --serif: var(--font-display);
    --sans: "Space Grotesk", system-ui, -apple-system, sans-serif;
    --font-display: "Redaction 20", Georgia, "Times New Roman", serif;
    --mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;

    --radius-sm: 3px;
    --radius-md: 4px;
    --radius-lg: 5px;

    --space-unit: 4px;
    --gutter-desktop: 30px;
    --gutter-mobile:  18px;

    --text-hero-desktop: 58px;
    --text-hero-mobile:  38px;
    --text-h1-desktop:   44px;
    --text-h1-mobile:    34px;

    --surface-soft: var(--paper-alt);
    --surface-hover: rgba(255, 255, 255, .06);
    --surface-hover-2: rgba(255, 255, 255, .08);
  }

  * { box-sizing: border-box; }
  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  body {
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--sans);
    -webkit-font-smoothing: antialiased;
  }
  h1, h2, h3, p { text-wrap: pretty; }
  h1, h2 { font-family: var(--font-display); }
  a { color: var(--accent); text-decoration: none; }

  /* Shell chrome: sidebar & topbar */
  #sidebar { display: none; }
  @media (min-width: 640px) {
    #sidebar {
      position: fixed; inset: 0 auto 0 0; width: 232px; z-index: 60;
      display: flex; flex-direction: column; gap: 2px;
      padding: 14px 12px 12px;
      background: var(--paper-alt);
      border-right: 1px solid var(--line);
      transition: width .12s ease, padding .12s ease;
    }
    #app { margin-left: 232px; transition: margin-left .12s ease; }
    #topbar { left: 232px; transition: left .12s ease; }
    #topbar .brand-home { display: none; }
  }
  .sb-top { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding-bottom: 8px; }
  .sb-brand {
    display: flex; align-items: center; gap: 6px;
    font-family: var(--sans); font-size: 19px; font-weight: 700; color: var(--ink);
    min-height: 44px; background: none; border: 0; cursor: pointer; padding: 6px 10px 14px; text-align: left;
    text-decoration: none;
  }
  .sb-brand .brand-word b { font-weight: 800; color: var(--accent); }
  .sb-collapse {
    flex: 0 0 auto; width: 44px; height: 44px; display: grid; place-items: center;
    border: 0; border-radius: var(--radius-md); background: none; color: var(--muted); cursor: pointer;
    transition: background .12s, color .12s;
  }
  .sb-collapse svg { width: 22px; height: 22px; }
  .sb-collapse:hover { background: rgba(255, 255, 255, .06); color: var(--ink); }
  .sb-nav { display: flex; flex-direction: column; gap: 2px; overflow-y: auto; flex: 1; }
  .sb-item {
    display: flex; align-items: center; gap: 10px; width: 100%;
    min-height: 44px; padding: 9px 10px; border-radius: 9px; border: 0; background: none;
    font: inherit; font-size: 13.5px; color: var(--ink-secondary); text-align: left; cursor: pointer;
    text-decoration: none;
    transition: background .12s, color .12s;
  }
  .sb-item:hover { background: rgba(255, 255, 255, .06); color: var(--ink); text-decoration: none; }
  .sb-item.on { background: rgba(255, 255, 255, .1); color: var(--ink); font-weight: 600; }
  .sb-ic { width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; }
  .sb-ic .nav-icon { width: 22px; height: 22px; }
  .sb-foot { margin-top: auto; padding-top: 10px; border-top: 1px solid var(--line); display: flex; align-items: center; gap: 2px; }
  .sb-small { width: auto; font-size: 12.5px; padding: 7px 9px; }
  .sb-lang { margin-left: auto; display: flex; border: 1px solid var(--line-strong); border-radius: var(--radius-md); overflow: hidden; }
  .sb-lang a, .sb-lang button {
    font: inherit; font-family: var(--mono); font-size: 11px; font-weight: 600; padding: 6px 9px; min-width: 36px; min-height: 36px;
    display: inline-flex; align-items: center; justify-content: center;
    border: 0; background: none; color: var(--muted); border-radius: 0; cursor: pointer; text-decoration: none;
    transition: background .15s ease, color .15s ease;
  }
  .sb-lang a:hover:not(.on):not(.lang-current) { color: var(--ink); background: rgba(255, 255, 255, .06); }
  .sb-lang a.on, .sb-lang a.lang-current { background: rgba(255, 255, 255, .15); color: var(--ink); font-weight: 700; }

  @media (min-width: 640px) {
    body.sb-collapsed #sidebar { width: 60px; padding: 14px 8px 12px; }
    body.sb-collapsed #app { margin-left: 60px; }
    body.sb-collapsed #topbar { left: 60px; }
    body.sb-collapsed .sb-brand,
    body.sb-collapsed .sb-label,
    body.sb-collapsed .sb-foot { display: none; }
    body.sb-collapsed .sb-top { justify-content: center; padding-bottom: 10px; }
    body.sb-collapsed .sb-item { justify-content: center; padding: 10px 0; }
  }

  #topbar {
    position: fixed; top: 0; right: 0; z-index: 50;
    display: flex; align-items: center; gap: 12px;
    padding: 8px 18px;
    background: rgba(9, 11, 15, .94);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--line);
    min-height: 56px;
  }
  @media (max-width: 639px) {
    #topbar { left: 0; }
  }
  .brand-home {
    display: flex; align-items: center;
    text-decoration: none; color: var(--ink);
  }
  .brand-home .mark { font-family: var(--sans); font-size: 18px; font-weight: 700; }
  .brand-home .mark b { color: var(--accent); }
  .topbar-context { display: flex; align-items: center; }
  .topbar-title {
    background: none; border: 0; color: var(--ink); font-family: var(--sans);
    font-size: 16px; font-weight: 600; text-decoration: none;
  }
  .topbar-title .brand-word b { color: var(--accent); }
  .topbar-trust {
    display: flex; align-items: center; gap: 10px;
    font-family: var(--mono); font-size: 11px; color: var(--ink-secondary);
    margin-left: 12px;
  }
  .topbar-trust .trust-full { display: flex; align-items: center; gap: 10px; }
  .topbar-trust .topbar-dot { color: var(--line-strong); }
  .topbar-trust .trust-condensed { display: none; }
  .topbar-trust .trust-link, .topbar-trust a {
    color: var(--accent); border-bottom: 1px solid rgba(77, 214, 193, .4);
    text-decoration: none;
  }
  .topbar-trust .trust-link:hover, .topbar-trust a:hover { border-bottom-color: var(--accent); }
  .topbar-end {
    margin-left: auto; display: inline-flex; align-items: center; gap: 8px; flex: 0 0 auto;
  }
  .topbar-lang {
    display: inline-flex; background: rgba(17, 21, 29, .85); border: 1px solid var(--line);
    border-radius: var(--radius-md); overflow: hidden;
  }
  .topbar-lang a, .topbar-lang button {
    font-family: var(--mono); font-size: 11px; font-weight: 600; padding: 5px 10px;
    color: var(--ink-secondary); text-decoration: none; background: transparent; border: 0; cursor: pointer;
  }
  .topbar-lang a.on, .topbar-lang a.lang-current { background: rgba(255, 255, 255, .15); color: var(--ink); }
  .mobile-menu-btn {
    display: none; width: 44px; height: 44px; border-radius: var(--radius-md); border: 0;
    background: none; color: var(--muted); cursor: pointer; align-items: center; justify-content: center;
  }
  .mobile-menu-btn svg { width: 22px; height: 22px; }
  .mobile-menu { display: none; }
  @media (max-width: 639px) {
    .mobile-menu-btn { display: inline-flex; }
    .topbar-trust .trust-full { display: none; }
    .topbar-trust .trust-condensed { display: inline; }
    .topbar-trust { font-size: 10px; gap: 6px; }
    .mobile-menu.is-open {
      display: block; position: fixed; top: 56px; left: 0; right: 0; bottom: 0;
      background: var(--paper); z-index: 99; padding: 16px; overflow-y: auto;
    }
    .mobile-menu .topicons {
      display: grid; grid-template-columns: 1fr; gap: 8px;
    }
    .mobile-menu .iconbtn {
      display: flex; align-items: center; gap: 12px; padding: 12px 14px;
      border-radius: var(--radius-md); background: var(--paper-alt); color: var(--ink);
      text-decoration: none; font-size: 14px; font-weight: 500;
    }
    .mobile-menu .iconbtn.on { background: rgba(255, 255, 255, .15); font-weight: 700; }
  }
  @media (max-width: 900px) {
    .topbar-trust .trust-full { display: none; }
    .topbar-trust .trust-condensed { display: inline; }
  }

  #app {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  #main-content {
    flex: 1;
    padding-top: 56px;
  }

  /* Ported page primitives */
.seg button:focus-visible {
  outline-offset: -2px;
}
.seg {
  display: inline-flex; background: var(--paper); border: 1px solid var(--line); border-radius: 8px; overflow: hidden;
}
.seg button {
  font-family: var(--mono); font-size: 12px; letter-spacing: .03em;
  color: var(--ink-secondary); background: transparent; border: 0; padding: 7px 13px;
  cursor: pointer; transition: background .15s, color .15s;
}
.seg button:hover:not(:disabled) {
  color: var(--ink); background: var(--paper-alt);
}
.seg button.on {
  color: var(--paper); background: var(--accent); font-weight: 600;
}
.seg button:disabled {
  color: var(--muted); cursor: not-allowed; opacity: .55;
}
.seg button[data-after]::after {
  content: attr(data-after);
  margin-left: 6px; vertical-align: middle;
  font-size: 8.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  padding: 1px 5px; border-radius: 999px;
  background: var(--caution); color: var(--paper);
}
#tooltip .pill {
  font-size: 10px; padding: 1px 6px;
}
.muted {
  color: var(--ink-secondary);
}
.rows {
  display: grid; grid-template-columns: auto 1fr;
  border: 1px solid var(--line); border-radius: 10px; overflow: hidden;
}
.rows dt, .rows dd {
  padding: 10px 12px; border-bottom: 1px solid var(--line); min-width: 0;
}
.rows dt {
  color: var(--ink-secondary); font-size: 12.5px; white-space: nowrap; border-right: 1px solid var(--line);
}
.rows dd {
  margin: 0; text-align: right; font-size: 14px; overflow-wrap: anywhere;
}
.rows dd.mono {
  font-family: var(--mono);
}
.rows .bloc-unit {
  white-space: nowrap;
}
.rows dt:last-of-type, .rows dd:last-of-type {
  border-bottom: 0;
}
.pill {
  display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 600;
  font-family: var(--mono); color: #0b0e13;
}
.pill-model {
  font-size: 10px;
  padding: 1px 7px;
  letter-spacing: .05em;
  text-transform: uppercase;
  background: color-mix(in oklab, #ffd166 18%, transparent);
  color: #ffd166;
  border: 1px solid color-mix(in oklab, #ffd166 40%, transparent);
  vertical-align: middle;
}
.note {
  margin-top: 18px; padding: 11px 12px; background: var(--paper); border: 1px solid var(--line);
  border-radius: 8px; font-size: 12px; color: var(--ink-secondary); line-height: 1.5;
}
.note b {
  color: var(--ink);
}
.top-controls .seg.chip {
  background: rgba(17, 21, 29, .85);
  border-color: var(--line);
  backdrop-filter: blur(8px);
}
.top-controls .seg.chip button {
  min-height: 44px;
  padding: 8px 14px;
}
.state-h .muted {
  font-size: 12px;
}
.seat-tab.on {
  color: var(--paper); background: var(--accent); border-color: var(--accent);
}
.dewan-coverage + .note {
  margin-top: 8px;
}
.dewan-page {
  max-width: 900px; margin: 0 auto;
}
.dewan-tiles {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 14px 0 4px;
}
.dewan-tile {
  display: flex; flex-direction: column; gap: 2px;
  padding: 12px 14px; background: var(--paper-alt); border: 1px solid var(--line); border-radius: 12px;
}
.dewan-tile .muted {
  font-size: 10.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
}
.dewan-tile b {
  font-size: 16px; line-height: 1.25;
}
.bento-tile, .dewan-tile {
  background: var(--surface-soft); border: 1px solid var(--line); border-radius: 16px;
  padding: 15px 16px; min-width: 0; display: flex; flex-direction: column; gap: 9px;
}
.bento-kicker {
  font-size: 10.5px; text-transform: uppercase; letter-spacing: .09em; color: var(--muted); font-weight: 600;
}
.dewan-controls {
  flex-wrap: wrap;
}
.dewan-sorts {
  flex: 0 0 auto;
}
.dewan-table {
  margin-top: 8px; border: 1px solid var(--line); border-radius: 12px; overflow: hidden;
}
.dewan-tr {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 64px 70px 70px 64px 96px;
  gap: 8px; align-items: center;
  width: 100%; padding: 9px 12px; margin: 0; border: 0; text-align: left;
  background: transparent; color: var(--ink); font: inherit; cursor: pointer;
  border-bottom: 1px solid color-mix(in oklab, var(--line) 60%, transparent);
}
.dewan-tr:last-child {
  border-bottom: 0;
}
button.dewan-tr:hover {
  background: var(--surface-hover, var(--paper-alt));
}
.dewan-th {
  cursor: default; font-size: 10px; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; color: var(--muted); background: var(--paper-alt);
}
.dewan-rank {
  color: var(--muted); font-size: 11px;
}
.dewan-mp {
  display: flex; flex-direction: column; gap: 1px; min-width: 0;
}
.dewan-mp b {
  font-size: 13px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dewan-mp .muted {
  font-size: 10.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dewan-coal {
  display: flex; justify-content: flex-start;
}
.dewan-num {
  text-align: right; font-size: 12px;
}
.dewan-th .dewan-num {
  font-size: 10px;
}
.dewan-page-note {
  margin-top: 14px;
}
.bills-page {
  max-width: 900px; margin: 0 auto;
}
.bills-controls {
  flex-wrap: wrap;
}
.bills-sorts {
  flex: 0 0 auto;
}
.bills-table.rows {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  margin-top: 8px;
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
}
.bills-table.rows dt,
.bills-table.rows dd {
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  min-width: 0;
}
.bills-table.rows dt {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  border-right: 1px solid var(--line);
  color: var(--ink-secondary);
  font-size: 11.5px;
  background: var(--surface-soft, var(--paper));
}
.bills-table.rows dd {
  margin: 0;
  text-align: left;
  font-size: 13.5px;
}
.bills-table.rows dt:last-of-type,
.bills-table.rows dd:last-of-type {
  border-bottom: 0;
}
.bill-code {
  font-size: 12px;
  font-weight: 700;
  color: var(--ink);
}
.bill-date {
  font-size: 11px;
}
.bill-expandable {
  width: 100%;
}
.bill-summary-trigger {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  user-select: none;
  list-style: none;
}
.bill-summary-trigger::-webkit-details-marker {
  display: none;
}
.bill-title-text {
  font-weight: 600;
  line-height: 1.35;
  color: var(--ink);
}
.bill-toggle-indicator {
  font-size: 11px;
  color: var(--ink-secondary);
  transition: transform .15s ease;
  flex-shrink: 0;
  padding-top: 2px;
}
.bill-expandable[open] .bill-toggle-indicator {
  transform: rotate(180deg);
}
.bill-expanded-content {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid color-mix(in oklab, var(--line) 60%, transparent);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.bill-huraian {
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--ink-secondary);
}
.bill-huraian-p {
  margin: 0 0 6px;
  color: var(--ink);
}
.bill-source-p {
  margin: 0;
  font-size: 11px;
}
.bill-source-p a {
  color: var(--caution);
  text-decoration: none;
}
.bill-source-p a:hover {
  text-decoration: underline;
}
.bill-division-box {
  margin-top: 2px;
}
.bill-division-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 6px;
}
.bill-division-rows.rows {
  margin-top: 4px;
}
.bill-division-rows.rows dt {
  font-size: 11.5px;
  background: transparent;
}
.bill-division-rows.rows dd {
  font-size: 12.5px;
  text-align: right;
}
.bill-voice-vote-note {
  font-size: 12px;
  line-height: 1.45;
  margin: 0;
}
.sentiment-table.rows {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  margin-top: 8px;
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
}
.sentiment-table.rows dt,
.sentiment-table.rows dd {
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
  min-width: 0;
}
.sentiment-table.rows dt {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  border-right: 1px solid var(--line);
  background: var(--surface-soft, var(--paper));
}
.sentiment-table.rows dd {
  margin: 0;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 10px;
  justify-content: center;
}
.sentiment-table.rows dt:last-of-type,
.sentiment-table.rows dd:last-of-type {
  border-bottom: 0;
}
.rows.seat-score-row {
  margin-top: 10px;
}
.find-actions .seg.chip {
  border-radius: 12px;
}
.find-actions .seg.chip button {
  min-height: 48px; padding: 10px 17px; font-size: 13px;
}
.seg.chip {
  background: var(--paper-alt); border: 1px solid var(--line); border-radius: var(--radius-md);
}
.seg.chip button {
  min-height: 44px; padding: 8px 13px; font-size: 12px;
}
.seg.chip button.on {
  background: var(--accent); color: var(--paper); font-weight: 600;
}
.seg.chip button:hover:not(:disabled):not(.on) {
  background: rgba(255, 255, 255, .06); color: var(--ink);
}
.seg button, .lang-seg button, .brand-home, .iconbtn, .share-btn, .share-icon, .card-back, .seat-tab, .map-inspect-details, .map-inspect-more, .map-inspect-select-button, .map-inspect-option,
.card-preview-close, .preview-download, .find-loc {
  transition-property: background, color, border-color, transform;
  transition-duration: .12s;
  transition-timing-function: ease;
}
.seg button:focus-visible, .lang-seg button:focus-visible, .brand-home:focus-visible, .iconbtn:focus-visible,
.card-back:focus-visible, .share-btn:focus-visible, .share-icon:focus-visible, .seat-tab:focus-visible, .map-inspect-details:focus-visible, .map-inspect-more:focus-visible, .map-inspect-select-button:focus-visible,
.card-preview-close:focus-visible, .preview-download:focus-visible, .loc-fab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.seg button:active:not(:disabled), .lang-seg button:active, .brand-home:active, .card-back:active, .seat-tab:active,
.share-icon:active, .map-inspect-details:active, .map-inspect-more:active, .map-inspect-select-button:active, .map-inspect-option:active, .card-preview-close:active {
  transform: scale(.94);
}
.state-h .muted {
  font-size: clamp(12px, 0.95vw, 15px);
}
.rows dt {
  font-size: clamp(12.5px, 1.02vw, 15.5px);
}
.rows dd {
  font-size: clamp(14px, 1.18vw, 18px);
}
.rows dt, .rows dd {
  padding-block: clamp(10px, 0.95vw, 16px);
}
.bento-runners-grid .prn-cc.is-compact .prn-cc-head .pill {
  align-self: center;
  flex: 0 0 auto;
}
.bento-runners-grid .prn-cc.is-compact .pol-photo.prn-profile-photo,
.bento-runners-grid .prn-cc.is-compact .pol-photo {
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
}
.prn-cand .pill {
  flex: 0 0 auto;
}
.pol-photo {
  width: 72px; height: 72px; aspect-ratio: 1 / 1; box-sizing: border-box; overflow: hidden;
  border-radius: 12px; object-fit: cover; flex: 0 0 auto;
  background: var(--line); display: grid; place-items: center;
}
.pol-monogram {
  font-family: var(--sans); font-weight: 700; font-size: 26px; line-height: 1; color: #fff; letter-spacing: .02em;
}
.pol-socials { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.pol-socials-compact { gap: 5px; margin-top: 8px; }
.pol-soc-icon {
  display: inline-grid; place-items: center; width: 34px; height: 34px; border-radius: 9px;
  border: 1px solid var(--line); background: var(--paper-alt); color: var(--ink-secondary);
  transition: color .12s, border-color .12s;
}
.pol-soc-icon:hover {
  color: var(--ink); border-color: var(--line-strong);
}
.pol-soc-icon:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.pol-soc-icon svg {
  width: 17px; height: 17px; display: block;
}
.pol-socials-compact .pol-soc-icon {
  width: 26px; height: 26px; border-radius: 7px;
}
.pol-socials-compact .pol-soc-icon svg {
  width: 14px; height: 14px;
}
.pol-socials-unverified .pol-soc-icon {
  border-style: dashed;
}
.pol-dir {
  position: fixed; inset: 0; z-index: 6;
  overflow-y: auto; overscroll-behavior: contain;
  padding: clamp(22px, 5vw, 72px) clamp(14px, 4vw, 40px) 60px;
}
.pol-dir-head {
  max-width: 1100px; margin: 0 auto 16px;
}
.pol-dir-head h1 {
  font-family: var(--sans); font-size: clamp(24px, 4vw, 40px); margin: 0;
}
.pol-dir-head .pol-dir-sub {
  color: var(--ink-secondary); font-size: 13px; margin: 4px 0 0;
}
.pol-dir-controls {
  max-width: 1100px; margin: 0 auto 16px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
}
.pol-dir-controls input, .pol-dir-controls select {
  background: var(--paper-alt); border: 1px solid var(--line); border-radius: 12px;
  padding: 11px 13px; font-size: 16px; font-family: var(--sans); color: var(--ink); min-height: 44px;
}
.pol-dir-search {
  flex: 1 1 220px; min-width: 0;
}
.pol-dir-count {
  max-width: 1100px; margin: 0 auto 10px; color: var(--muted); font-size: 12px; font-family: var(--mono);
}
.pol-grid {
  max-width: 1100px; margin: 0 auto;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px;
}
.pol-card {
  display: grid; gap: 6px; padding: 10px; border: 1px solid var(--line); border-radius: 14px;
  background: var(--paper-alt); text-align: left; cursor: pointer; color: inherit; font: inherit;
  align-content: start;
}
.pol-card:hover {
  border-color: var(--line-strong); background: rgba(255, 255, 255, .06);
}
.pol-card:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.pol-card-photo {
  position: relative; line-height: 0;
}
.pol-card .pol-photo {
  width: 100%; height: auto; aspect-ratio: 1; border-radius: 10px;
}
.pol-card .pol-monogram {
  font-size: 40px;
}
.pol-card-badge {
  position: absolute; top: 7px; right: 7px; font-size: 10.5px; font-weight: 700;
  /* the photo wrapper is line-height:0 to kill the img gap — restore it here or
     the badge text ("PAS") collapses to a squeezed sliver. */
  line-height: 1.5; padding: 2px 8px; white-space: nowrap;
  box-shadow: 0 1px 6px rgba(0,0,0,.45);
}
.pol-card-name {
  font-family: var(--sans); font-weight: 700; font-size: 15px; line-height: 1.2;
  color: var(--ink); margin-top: 2px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  min-height: 2.4em;
}
.pol-card-seat {
  font-size: 11px; color: var(--ink-secondary); font-family: var(--mono); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pol-card .pol-socials-compact {
  margin-top: 2px; min-height: 26px; flex-wrap: nowrap; overflow: hidden;
}
.pol-card-socials-spacer {
  min-height: 26px; margin-top: 2px;
}
.pol-soc-more {
  display: inline-grid; place-items: center; min-width: 26px; height: 26px; padding: 0 5px;
  border-radius: 7px; border: 1px dashed var(--line); color: var(--muted);
  font-family: var(--mono); font-size: 11px; flex: 0 0 auto;
}
.pol-dir-src {
  max-width: 1100px; margin: 20px auto 0; color: var(--muted); font-size: 11px; line-height: 1.5;
}
.pol-dir-empty {
  max-width: 1100px; margin: 30px auto; color: var(--ink-secondary); text-align: center;
}
.pol-party-grid {
  max-width: 1100px; margin: 0 auto;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px;
}
.pol-party-card {
  min-height: 44px; display: grid; gap: 12px; padding: 14px;
  border: 1px solid var(--line); border-radius: 14px;
  background: var(--paper-alt); color: inherit; font: inherit; text-align: left; cursor: pointer;
  transition: background .12s, border-color .12s, transform .04s;
}
.pol-party-card:hover {
  border-color: var(--line-strong); background: rgba(255, 255, 255, .06);
}
.pol-party-card:active {
  transform: translateY(1px);
}
.pol-party-card:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.pol-party-top {
  display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0;
}
.pol-party-mark {
  min-width: 52px; max-width: 100%; min-height: 44px; padding: 0 13px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 12px; color: #fff; font-family: var(--sans); font-size: 20px; font-weight: 800;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.14), 0 8px 22px rgba(0,0,0,.28);
}
.pol-party-stats {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
}
.pol-party-stats span {
  min-width: 0; padding: 9px 10px; border: 1px solid var(--line); border-radius: 10px;
  background: var(--white);
}
.pol-party-stats small {
  display: block; color: var(--muted); font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
}
.pol-party-stats b {
  display: block; margin-top: 3px; font-size: 20px; line-height: 1;
}
.pol-party-meta {
  display: grid; gap: 4px;
}
.pol-party-meta span {
  color: var(--muted); font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
}
.pol-party-meta b {
  color: var(--ink-secondary); font-size: 12.5px; line-height: 1.35; font-weight: 600;
}
.pol-party-samples {
  list-style: none; display: grid; gap: 6px; margin: 0; padding: 0;
}
.pol-party-samples li {
  min-width: 0; display: grid; gap: 1px;
}
.pol-party-samples b, .pol-party-samples span {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pol-party-samples b {
  font-size: 13px;
}
.pol-party-samples span {
  color: var(--muted); font-family: var(--mono); font-size: 10.5px;
}
.pol-party-open {
  align-self: end; color: var(--ink); font-size: 12px; font-weight: 700;
}
.pol-modal-photo.pol-monogram {
  font-size: 34px;
}
.cand-modal-photo.pol-monogram {
  font-size: 34px;
  font-weight: 800;
  color: #fff;
  text-shadow: 0 1px 0 rgba(0,0,0,.25);
}
.cand-pill-row .pill {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .02em;
  padding: 6px 12px;
  border-radius: 999px;
  box-shadow: 0 4px 14px color-mix(in oklab, var(--accent) 30%, transparent);
}
.prn-all-cand .pill {
  flex: 0 0 auto;
}
.bento-cr-cap .muted {
  font-size: 11.5px;
}
.prn-cc-head .pill {
  flex: 0 0 auto; align-self: flex-start;
}
.prn-cc.has-profile .prn-cc-head .pill {
  max-width: 112px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.bento-cand-row .prn-cc.is-compact .prn-cc-head .pill {
  align-self: center; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; padding: 3px 8px;
}
.bento-cand-row .prn-cc.is-compact .pol-photo.prn-profile-photo {
  width: 32px; height: 32px;
}
.prn-pl-tab.on {
  color: var(--ink); border-color: var(--accent); background: color-mix(in oklab, var(--accent) 22%, var(--paper-alt));
}
.bento-prn-toggle.on {
  color: var(--ink); border-color: var(--accent); background: color-mix(in oklab, var(--accent) 16%, var(--paper-alt));
}
.bento-live-strip-title .muted {
  font-size: 12px;
}
.bento-live-metric .muted {
  font-size: 10.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
}
.bento-live-chip.on {
  background: color-mix(in oklab, var(--accent) 18%, var(--paper-alt)); border-color: color-mix(in oklab, var(--accent) 40%, var(--line)); color: var(--ink);
}
.pol-photo.bento-gov-photo {
  width: 84px; height: 84px; border-radius: 16px; flex: 0 0 auto; object-fit: cover; object-position: center 12%; font-size: 22px;
}
.pol-photo.prn-inc-photo {
  width: 52px; height: 52px; border-radius: 11px; flex: 0 0 auto; object-fit: cover; object-position: center 12%; font-size: 16px;
}
.pol-dir-tabs-wrap {
  max-width: 1100px;
  margin: 0 auto 18px;
  overflow-x: auto;
  scrollbar-width: none;
}
.pol-dir-tabs-wrap::-webkit-scrollbar {
  display: none;
}
.pol-dir-tabs {
  display: inline-flex;
  max-width: 100%;
  vertical-align: top;
}
.seg.chip.bento-map-seg button {
  min-height: 44px; padding: 0 13px; font-size: 10.5px; letter-spacing: .02em; white-space: nowrap;
}
.sb-item.on {
  background: rgba(255, 255, 255, .06); color: var(--ink); font-weight: 600;
}
.sb-state.is-election.on,
.sb-state.is-election.is-prn-on {
  background: color-mix(in oklab, #f87171 42%, transparent);
  border-color: color-mix(in oklab, #f87171 80%, transparent);
  font-weight: 650;
}
.sb-lang button.on {
  background: rgba(255, 255, 255, .06); color: var(--ink);
}
.bento-cr-count .bento-count-big span, .bento-cr-cap .muted {
  color: rgba(20,22,26,.7);
}
.bento-tier-chip.on {
  background: rgba(255, 255, 255, .15); color: var(--ink);
}
.bento-prn-toggle.on {
  background: color-mix(in oklab, rgba(77, 214, 193, .15) 52%, rgba(255, 255, 255, .08)); color: var(--ink);
}
.pol-card-vacant {
  display: inline-block; margin-left: 6px; padding: 1px 5px; border-radius: 5px;
  border: 1px solid rgba(210, 162, 76, .55); color: #d2a24c; background: rgba(210, 162, 76, .1);
  font-family: var(--mono); font-size: 8.5px; font-weight: 700;
  letter-spacing: .05em; text-transform: uppercase; vertical-align: 2px;
}
.seat-legislative .rows {
  margin-top: 6px;
}
.pol-card-leg {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-secondary);
  min-height: 16px;
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pol-card-leg-spacer {
  min-height: 16px;
  margin-top: 1px;
}
.pol-card-coal-diff {
  font-size: 9.5px;
  font-family: var(--mono);
  color: var(--caution);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
@media (max-width: 639px) {
  .mobile-menu .top-controls .seg.chip,
  .mobile-menu .menu-map-controls .seg.chip {
    width: 100%;
  }
  .mobile-menu .top-controls .seg.chip button,
  .mobile-menu .menu-map-controls .seg.chip button {
    flex: 1 1 0;
      min-width: 0;
  }
}
@media (max-width: 430px) {
  .mobile-menu .top-controls .seg.chip button,
  .mobile-menu .menu-map-controls .seg.chip button {
    padding: 8px 10px;
      font-size: 11px;
  }
}
@media (max-width: 680px) {
  .dewan-tr {
    grid-template-columns: 26px minmax(0, 1fr) 52px 58px 52px; padding: 9px 10px;
  }
  .dewan-col-qa, .dewan-col-last {
    display: none;
  }
  .dewan-tiles {
    grid-template-columns: 1fr 1fr;
  }
  .dewan-tile:first-child {
    display: none;
  }
  .bills-table.rows {
    grid-template-columns: 1fr;
  }
  .bills-table.rows dt {
    border-right: 0;
      border-bottom: 0;
      padding-bottom: 4px;
      flex-direction: row;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
  }
  .bills-table.rows dd {
    padding-top: 4px;
  }
  .sentiment-table.rows {
    grid-template-columns: 1fr;
  }
  .sentiment-table.rows dt {
    border-right: 0;
      border-bottom: 0;
      padding-bottom: 4px;
      flex-direction: row;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
  }
  .sentiment-table.rows dd {
    padding-top: 4px;
  }
}
@media (max-width: 860px) {
  body.map-inspect #panel-state .state-h .muted {
    font-size: 11px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .seg button:active, .lang-seg button:active, .brand-home:active, .iconbtn:active,
  .share-btn:active, .card-back:active, .share-icon:active, .seat-tab:active, .map-inspect-details:active, .map-inspect-more:active, .map-inspect-select-button:active, .map-inspect-option:active,
  .card-preview-close:active, .preview-download:active, .find-loc:active {
    transform: none;
  }
}
@media (max-width: 380px) {
  .seg.chip button {
    padding: 8px 10px; font-size: 11px;
  }
}
@media (min-aspect-ratio: 1/1) and (max-height: 700px) {
  #panel.seat-detail .rows dt,
  #panel.seat-detail .rows dd {
    padding-block: 5px;
  }
}
@media (max-width: 760px) {
  .cand-modal-photo, .cand-modal-photo.pol-monogram {
    border-radius: 15px; font-size: 26px;
  }
}
@media (max-width: 1100px) {
  .pol-photo.bento-gov-photo {
    width: 76px; height: 76px;
  }
}
@media (min-width: 640px) {
  body.politicians-open .pol-dir {
    left: 232px;
  }
  body.dewan-open .pol-dir, body.bills-open .pol-dir, body.sentiment-open .pol-dir {
    left: 232px;
  }
  body.sb-collapsed.politicians-open .pol-dir {
    left: 60px;
  }
  body.sb-collapsed.dewan-open .pol-dir, body.sb-collapsed.bills-open .pol-dir, body.sb-collapsed.sentiment-open .pol-dir {
    left: 60px;
  }
  .sb-item.on {
    background: rgba(255, 255, 255, .15);
  }
  .sb-lang button.on {
    background: rgba(255, 255, 255, .15);
  }
}


  .pol-dir {
    position: relative;
    max-width: 1100px;
    margin: 0 auto;
    padding: 24px clamp(14px, 4vw, 40px) 60px;
  }
  .pk-hemicycle { display: block; width: 100%; height: auto; }

  /* Methodology footer & legacy components */
  .pk-footer {
    background: var(--paper-alt);
    color: var(--on-dark-body);
    padding: var(--gutter-desktop);
    display: grid;
    grid-template-columns: 1.4fr 1fr 1fr;
    gap: 36px;
    border-top: 1px solid var(--line);
  }
  .pk-footer-heading {
    font-family: var(--sans);
    font-size: 18px;
    color: var(--ink);
    margin-bottom: 8px;
  }
  .pk-footer-statement p { margin: 0; font-size: 12.5px; line-height: 1.6; }
  .pk-not-calibrated { color: var(--caution); }
  .pk-footer-link {
    display: inline-block;
    margin-top: 12px;
    margin-right: 18px;
    font-size: 12.5px;
    color: var(--accent);
    border-bottom: 1px solid rgba(77, 214, 193, .4);
    transition: border-bottom-color .15s ease;
  }
  .pk-footer-link:hover { border-bottom-color: var(--accent); }
  .pk-footer-label {
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 9px;
  }
  .pk-footer-list { display: flex; flex-direction: column; gap: 5px; font-size: 12.5px; }
  @media (max-width: 900px) {
    .pk-footer {
      grid-template-columns: 1fr;
      gap: 24px;
      padding: 22px var(--gutter-mobile);
    }
  }
"""

_CSS = _CSS_TEMPLATE
