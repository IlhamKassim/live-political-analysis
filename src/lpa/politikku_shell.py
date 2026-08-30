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

`render_shell` also loads `{POLITIKKU_PREFIX}lookup.js` — the compiled output
of `ts/src/` (issue #77), the one piece of PolitikKu with real client-side
state (#70). It is a static module script, harmless on a page with no
`[data-pk-lookup-form]` (`mountAllLookups()` is a no-op then), so it is
loaded on every page rather than conditionally per template. Like every
other PolitikKu page, `public/lookup.js` is generated, not
committed — `ts/README.md` (or `ts/package.json`'s `build` script) is
what produces it, run alongside the Python pages' own build step.

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
call rather than a mechanical translation of a given value): PolitikKu's
pages live under `POLITIKKU_PREFIX`, English at `/<page>` and Bahasa
Malaysia at `/ms/<page>`, all root-relative (the whole site serves from one
domain per `public/CNAME`). Bills/Sentiment point at pages later tickets
have not built yet, same as the handoff itself asks for ("wired to routes
that don't need to exist yet").

Two of those routes stopped being placeholders in #102 (ADR 0011), which is
also why the routing helpers below take a `prefix` rather than hardcoding
one: "Seat Projection" points at `politikku_projection.py`'s own page at
`/projection/` (and `/projection/ms/`) rather than at the old chamber
dashboard, and "Methodology" has a real page behind it.

#104 finished the cutover ADR 0011 describes by flipping `POLITIKKU_PREFIX`
from the staging `/politikku/` to `/`: `politikku_homepage` now owns
`public/index.html`, the old chamber dashboard (`public_page.py`) is no
longer rendered or published at all, and its analytical depth lives at
`/projection/`. `public_page.py` itself stays — every number on both
`/` and `/projection/` is still computed by its `page_model()`.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from lpa.domain import ElectionStatus

POLITIKKU_PREFIX = "/"
"""Where PolitikKu's own pages are served from — the site root since #104's
cutover (ADR 0011). Every route below is built from a prefix plus a page
path, so a page living outside this family (see `PROJECTION_PREFIX`) still
gets the same EN/`ms/` pairing rather than a second, hand-written routing
scheme.

Until #104 this was the staging prefix `/politikku/`, and flipping this one
constant is the whole of the cutover for every link in the shell: the nav
(`NAV_LINKS` -> `route`), the wordmark, the EN/BM toggle, the
language-persistence script's route-family detection, `LANDING_URL`,
`methodology_url`, and the self-hosted font/`lookup.js` asset URLs in
`render_shell`/`_CSS` all read it rather than spelling a prefix themselves.
The page-writing side follows the same constant, though which page owns
`public/index.html` changed again at the landing-page cutover below:
`politikku_landing`'s `--output` default is `public/index.html` now,
`politikku_homepage`'s is `public/home.html` (`HOMEPAGE_PAGE`), and
`ts/build.mjs` writes `public/lookup.js`."""

PROJECTION_PREFIX = "/projection/"
"""The ported projection detail page (#102, ADR 0011) — the old dashboard's
analytical depth redrawn in PolitikKu's register. It sits at its own
top-level route rather than under `POLITIKKU_PREFIX` because ADR 0011 has
PolitikKu becoming the site itself: with #104's cutover done,
`POLITIKKU_PREFIX` *is* `/`, so the projection page needs a route of its own
to live at rather than sharing the root with the homepage."""

METHODOLOGY_PAGE = "methodology.html"
"""The page path (under `POLITIKKU_PREFIX`) the header nav, the trust strip
and the footer all link "how this works" at. Built by
`politikku_projection.build_methodology`; before #102 this link target did
not exist anywhere — see that module's docstring."""

MP_PROFILE_DIR = "mp"
"""The directory MP profile pages live in, under `POLITIKKU_PREFIX` — one
`<seat-code>.html` per Seat (`politikku_mp_profile`), so `/mp/P.102.html` in
English and `/ms/mp/P.102.html` in BM. Named here because three places have
to agree on it: the pages' own `page_path` (which drives their EN/BM
toggle), `politikku_mp_profile.main`'s `--output-dir` default, and
`ts/src/dom.ts`'s `mpProfileUrl()`, which builds the same href in the
browser and cannot import this constant."""

BILLS_PAGE = "bills.html"
"""The bill-tracker page path — still one of the routes "wired to routes that
don't need to exist yet" (no ticket has built it). Named here rather than
spelled twice because `politikku_homepage`'s "All bills →" link points at the
same page the nav does, and #104 found that second copy still carrying the
pre-cutover `/politikku/` prefix."""

LANDING_PAGE = ""
"""`politikku_landing.py`'s own page (#75), as a page path under
`POLITIKKU_PREFIX` — the same shape as `METHODOLOGY_PAGE`, so `route()`
turns it into a real href in whichever language rather than a hand-written
string. Defined here, not on `politikku_landing`, so both directions of the
reference (footer -> landing, landing -> its own output path) read from the
one constant rather than two copies of the same string.

Empty since the site-root cutover below: the landing page IS `/` now, not a
page linked from it. Until that cutover this was `"landing.html"` — a real,
separate route reached only via a CTA, with the homepage at `/`."""

LANDING_URL = f"{POLITIKKU_PREFIX}{LANDING_PAGE}"
"""The English landing page's URL — what `politikku_landing.main` derives its
`--output` default from, and nothing else (link *targets* go through
`landing_url` below, which is language-aware). Until #104 this was a
hardcoded `/politikku/landing.html`: a stale prefix that would have survived
the cutover, which is exactly why it is now built from `POLITIKKU_PREFIX`.
With `LANDING_PAGE` now empty, this collapses to `POLITIKKU_PREFIX` itself
(`"/"`) — the landing-page cutover, second verse."""

HOMEPAGE_PAGE = "home.html"
"""`politikku_homepage.py`'s own page (#74) — the returning-visitor
dashboard (hemicycle, headline figures, bill tracker and sentiment digest
snippets) — moved off the site root to make room for the landing page
above. Before this cutover, `politikku_homepage.py` hardcoded `page_path=""`
directly rather than reading a constant, because it *was* the root; now it
needs a real page path like every other non-root page."""

HOMEPAGE_URL = f"{POLITIKKU_PREFIX}{HOMEPAGE_PAGE}"
"""The English dashboard page's URL, same shape as `LANDING_URL`."""


class Language(StrEnum):
    """The two languages a PolitikKu page can be served in.

    Originally chrome-only (#72's scope excluded translated copy); #81 wires
    this to real BM strings throughout the shell and every page built on it,
    via `t()` below.
    """

    EN = "en"
    MS = "ms"


def t(language: Language, en: str, ms: str) -> str:
    """Pick `en` or `ms` copy for `language` — the one primitive every
    PolitikKu page's rendering function calls at each point bilingual text
    appears (#81). Lives here, next to `Language`, rather than in
    `politikku_i18n` so that module (shared vocabulary built out of this
    same primitive) can import both from one place without a circular
    import back to itself.
    """
    return en if language is Language.EN else ms


@dataclass(frozen=True)
class NavLink:
    """One item in the persistent header nav."""

    label: str
    label_ms: str
    """BM copy for `label`. No settled source (the design handoff's bilingual
    table covers homepage copy, not shell nav) — plain, low-risk cognates/
    translations, listed in #81's PR description for a native-BM check."""
    href: str
    """The page-path fragment `_en_route`/`_ms_route` take (e.g.
    `"bills.html"`, `""` for a directory index) — routed through whichever
    language the current page is in, so clicking a nav item from a BM page
    stays in BM (#81's own "persisted... drives /ms/ routes" requirement
    extends to in-site navigation, not just the toggle itself)."""
    key: str
    """Identifies this link for the `active_nav` comparison — stable even if
    `label`/`label_ms` change."""
    prefix: str = POLITIKKU_PREFIX
    """Which route family this link's `href` hangs off. Every link was
    `POLITIKKU_PREFIX` until #102 gave "Seat Projection" a real page of its
    own at `PROJECTION_PREFIX`. It replaces the old `localized: bool` flag,
    which existed solely so that one item could point at the un-translated
    chamber dashboard at `/` — that page now has a BM sibling
    (`/projection/ms/`), so there is no longer any nav item that has to opt
    out of language routing."""
    en_only: bool = False
    """If True, this link is omitted when the site is viewed in BM."""


NAV_LINKS: tuple[NavLink, ...] = (
    NavLink("Home", "Utama", "", "home"),
    NavLink("Dashboard", "Papan Pemuka", HOMEPAGE_PAGE, "dashboard"),
    NavLink("Seat Projection", "Unjuran Kerusi", "", "projection", prefix=PROJECTION_PREFIX),
    NavLink("Bills", "Rang Undang-Undang", BILLS_PAGE, "bills"),
    NavLink("Sentiment", "Sentimen", "sentiment.html", "sentiment"),
    NavLink("Methodology", "Metodologi", METHODOLOGY_PAGE, "methodology"),
    NavLink("Glossary", "Glosari", "learn/glossary.html", "glossary", en_only=True),
    NavLink("Coalitions", "Gabungan", "learn/coalitions.html", "coalitions", en_only=True),
    NavLink("GE16 Process", "Proses PRU16", "learn/ge16-process.html", "process", en_only=True),
)


def _en_route(page_path: str, prefix: str = POLITIKKU_PREFIX) -> str:
    return f"{prefix}{page_path}"


def _ms_route(page_path: str, prefix: str = POLITIKKU_PREFIX) -> str:
    return f"{prefix}ms/{page_path}"


def route(language: Language, page_path: str, prefix: str = POLITIKKU_PREFIX) -> str:
    """`page_path` under `prefix`, in whichever language — the one place a
    caller outside this module turns "which page, which language" into a
    real href, rather than each page reassembling `/ms/…` itself."""
    return _en_route(page_path, prefix) if language is Language.EN else _ms_route(page_path, prefix)


def methodology_url(language: Language = Language.EN) -> str:
    """Where "how this works" points. Language-aware since #102: the BM
    footer previously linked the English methodology page, a leak nobody
    could see while the target did not exist at all."""
    return route(language, METHODOLOGY_PAGE)


def projection_url(language: Language = Language.EN) -> str:
    """Where "Seat Projection"/"Full projection →" point (#102)."""
    return route(language, "", PROJECTION_PREFIX)


def landing_url(language: Language = Language.EN) -> str:
    """Where the footer's "What is PolitikKu? →" points. Language-aware for
    `methodology_url`'s own reason (#102): a BM page linking the English
    landing page is a leak, and `politikku_landing.main` writes a BM variant
    at `ms/landing.html` for it to link."""
    return route(language, LANDING_PAGE)


def short_date(day: date) -> str:
    """`23 Aug 2026` — the trust strip's date format, abbreviated month."""
    return f"{day.day} {day.strftime('%b %Y')}"


def trust_strip_status_text(status: ElectionStatus, language: Language = Language.EN) -> str:
    """The Election Status as the trust strip's one-line form.

    A compact sibling of `public_page.status_sentence`, not a reuse of it —
    that function writes a standfirst sentence; this is a strip item a few
    words wide. Same discipline: never guesses a date that is not set.

    The BM sentences have no settled source (design handoff's table covers
    homepage copy, not the election-status strip text) — original
    translations, listed in #81's PR description for a native-BM check.
    """
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
    """One `<a>` tag, escaped, with `aria-current="page"` when it's the
    current page — factored out because pre-3.12 f-strings cannot contain a
    backslash-escaped quote inside a `{}` expression.

    `extra`, when set, adds `data-pk-set-lang="{extra}"` — read by
    `_LANGUAGE_PERSISTENCE_SCRIPT`'s click listener, not a navigation
    handler, so the link stays a real `<a href>` either way."""
    aria = _ARIA_CURRENT_PAGE if current else ""
    cls = f' class="{css_class}"' if css_class else ""
    extra_attr = f' data-pk-set-lang="{extra}"' if extra else ""
    return f'<a{cls} href="{html.escape(href)}"{aria}{extra_attr}>{html.escape(label)}</a>'


def _lang_toggle(language: Language, page_path: str, prefix: str = POLITIKKU_PREFIX) -> str:
    en_href = _en_route(page_path, prefix)
    ms_href = _ms_route(page_path, prefix)
    en_current = language is Language.EN
    ms_current = language is Language.MS
    # `data-pk-set-lang` (via `_link`'s `extra` param) is read by
    # `_LANGUAGE_PERSISTENCE_SCRIPT` below, not a click handler that
    # intercepts navigation — the link's own `href` is what actually moves
    # the visitor, matching this ticket's "a pair of links to the localised
    # routes, not a JS-only control" requirement.
    en_link = _link(
        href=en_href,
        label="EN",
        css_class="lang-current" if en_current else "",
        current=en_current,
        extra="en",
    )
    ms_link = _link(
        href=ms_href,
        label="BM",
        css_class="lang-current" if ms_current else "",
        current=ms_current,
        extra="ms",
    )
    return f'<div class="lang-toggle" role="group" aria-label="Language">{en_link}{ms_link}</div>'


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
    if (!el) return;
    try { window.localStorage.setItem('pk-language', el.getAttribute('data-pk-set-lang')); } catch (e) {}
  });
})();
</script>
"""
"""#81's own requirement: `language` "persisted (cookie or localStorage),
drives /ms/ routes" — a static site with no server has nowhere but the
browser to keep that, so this is unavoidably a small script, the same
progressive-enhancement shape #77's "Recently looked up" chips already use
(a real link/feature works with no script; this only remembers the choice
for next time). Placed early in `<head>` (see `render_shell`) so a stored
preference redirects before the wrong-language page paints, rather than
flashing it first.

`__PREFIX__` is substituted per page (#102) rather than hardcoded: a page
served from `PROJECTION_PREFIX` has to compare its own route family, or a
stored BM preference would silently no-op there while working everywhere
else. Both substitutions are prefix-shaped on purpose — with
`POLITIKKU_PREFIX` now `/` (#104), `path.replace('/', '/ms/')` rewrites the
*leading* slash (`String.replace` with a string pattern replaces the first
occurrence only), so `/mp/P.102.html` becomes `/ms/mp/P.102.html` and `/`
becomes `/ms/`, which are the paths `politikku_mp_profile.main` and
`politikku_homepage.main` actually write."""


def _language_persistence_script(prefix: str = POLITIKKU_PREFIX) -> str:
    """`_LANGUAGE_PERSISTENCE_SCRIPT_TEMPLATE` bound to one route family — a
    `.replace` substitution rather than an f-string, since the template is
    brace-dense JS (the same call `public_page._theme_script` makes)."""
    return _LANGUAGE_PERSISTENCE_SCRIPT_TEMPLATE.replace("__PREFIX__", prefix)


def render_header(
    *, active_nav: str, language: Language, page_path: str, prefix: str = POLITIKKU_PREFIX
) -> str:
    """The 56px navy header: wordmark, nav, EN/BM toggle.

    `active_nav` is a `NavLink.key` (e.g. `"home"`) — the current page's nav
    item, underlined per the handoff's id-1a header. Nav collapses to a
    `<details>` disclosure below 900px (`_CSS`) rather than hidden JS: the
    links stay real and reachable with no script, matching this ticket's
    EN/BM-toggle accessibility requirement extended to the rest of the nav.
    """

    def _nav_href(link: NavLink) -> str:
        return route(language, link.href, link.prefix)

    links_html = "".join(
        _link(
            href=_nav_href(link),
            label=t(language, link.label, link.label_ms),
            css_class="active" if link.key == active_nav else "",
            current=link.key == active_nav,
        )
        for link in NAV_LINKS
        if not (link.en_only and language is Language.MS)
    )
    menu_label = t(language, "Menu", "Menu")  # "menu" is standard BM too
    primary_label = t(language, "Primary", "Utama")
    primary_mobile_label = t(language, "Primary (mobile)", "Utama (mudah alih)")
    home_href = route(language, "")
    return f"""
<header class="pk-header">
  <div class="pk-header-left">
    <a class="wordmark" href="{html.escape(home_href)}">PolitikKu</a>
    <nav class="pk-nav" aria-label="{primary_label}">{links_html}</nav>
  </div>
  <details class="pk-nav-mobile">
    <summary aria-label="{menu_label}">
      <span></span><span></span><span></span>
    </summary>
    <nav aria-label="{primary_mobile_label}">{links_html}</nav>
  </details>
  {_lang_toggle(language, page_path, prefix)}
</header>
""".strip()


def render_trust_strip(
    *,
    updated_at: date,
    sources_count: int,
    status: ElectionStatus,
    language: Language = Language.EN,
    methodology_href: str | None = None,
) -> str:
    """The persistent trust strip — appears on every PolitikKu page.

    Desktop shows all three items; the `<= 900px` rule in `_CSS` condenses
    it to just the date and a "Sources" link, per the handoff's mobile trust
    strip ("Updated 06:00 MYT today" + "Sources").

    "Updated" translates from the settled `Updated … today` row (dropping
    "hari ini"/"today" — this strip states a real date, never a fabricated
    "today", per its own docstring above). "{n} news source(s) read" and
    "How this works" have no settled source — original translations, listed
    in #81's PR description.
    """
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
    return f"""
<div class="pk-trust-strip">
  <span class="pk-trust-full">
    <span>{updated_word} {updated}, MYT</span>
    <span class="pk-dot">·</span>
    <span>{sources_text}</span>
    <span class="pk-dot">·</span>
    <span>{status_text}</span>
  </span>
  <span class="pk-trust-condensed">{updated_word} {updated}, MYT</span>
  <a class="pk-trust-link" href="{methodology}">{how_it_works}</a>
</div>
""".strip()


@dataclass(frozen=True)
class SourceGroup:
    """One column of the methodology footer's source lists."""

    heading: str
    heading_ms: str
    sources: Sequence[str]
    """Source names/citations — kept identical in both languages (mostly
    proper institutional names, several already part-BM, e.g. "Dewan Rakyat
    Hansard"; see `render_methodology_footer`'s docstring)."""


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
"""`MODELLED_SOURCES`' first line drops the handoff's hardcoded "9" (outlet
count) — that number belongs to whichever page wires in real data (#74),
not this static footer, and going stale the day an outlet is added or
dropped from `data/outlets.json` would itself be a trust-rule violation."""


def render_methodology_footer(
    *,
    language: Language = Language.EN,
    methodology_href: str | None = None,
    factual: SourceGroup = FACTUAL_SOURCES,
    modelled: SourceGroup = MODELLED_SOURCES,
) -> str:
    """The navy 3-column footer: methodology statement, factual sources,
    modelled sources. Persistent chrome, same as the header.

    The heading is the settled `Methodology & sources` -> `Metodologi &
    sumber` row. The disclaimer paragraph and the two footer links have no
    settled source — original translations, listed in #81's PR description.
    Source names/citations (`factual.sources`/`modelled.sources`) are left
    untranslated in both languages — see `SourceGroup.sources`'s docstring.
    """
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
    return f"""
<footer class="pk-footer">
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
</footer>
""".strip()


SITE_URL = "https://politikku.my/"
"""The published site's real address — `public/CNAME`'s custom domain.

Duplicated from `public_page.py` rather than imported: `public_page.py`
already imports `Language`/`t` from this module, so importing `SITE_URL`
back the other way would be circular. `telegram_post.py` already carries
its own copy of this same constant for the same reason."""


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
    """Wrap `body_html` in the full PolitikKu page: head, header, trust
    strip, `body_html` untouched, methodology footer.

    `body_html` is the one thing this function does not decide — #74/#75/#79
    each render their own body and pass it straight through, per #72's
    "not in scope: actual page content."

    `prefix` is the route family this particular page is served from, and
    only the EN/BM toggle and the language-persistence script read it (the
    nav's own links each carry their own `NavLink.prefix`). It defaults to
    `POLITIKKU_PREFIX`, so every page that existed before #102 is unchanged.

    `description` backs both `<meta name="description">` and the og:/
    twitter: tags — required, not defaulted, the same discipline #41 used
    for `public_page.py`'s own version of this block: every caller states
    real, page-specific copy rather than a generic fallback that reads the
    same on every page a reader shares.
    """
    header = render_header(
        active_nav=active_nav, language=language, page_path=page_path, prefix=prefix
    )
    trust_strip = render_trust_strip(
        updated_at=updated_at, sources_count=sources_count, status=status, language=language
    )
    footer = render_methodology_footer(language=language)
    lang_attr = "ms" if language is Language.MS else "en"
    escaped_title = html.escape(title)
    escaped_description = html.escape(description)
    og_url = html.escape(f"{SITE_URL.rstrip('/')}{route(language, page_path, prefix)}")

    en_url = html.escape(f"{SITE_URL.rstrip('/')}{_en_route(page_path, prefix)}")
    ms_url = html.escape(f"{SITE_URL.rstrip('/')}{_ms_route(page_path, prefix)}")

    og_image = html.escape(f"{SITE_URL}og-image.png")

    import json

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
<link rel="preload" href="{POLITIKKU_PREFIX}fonts/newsreader-variable.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{POLITIKKU_PREFIX}fonts/ibm-plex-sans-variable.woff2" as="font" type="font/woff2" crossorigin>
<link rel="icon" href="{POLITIKKU_PREFIX}favicon.ico">
<style>{_CSS}</style>
<script type="application/ld+json">
{website_ld}
</script>
<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "5eadc388fb2a4518b8e846b059fb102c"}}'></script><!-- End Cloudflare Web Analytics --> <!-- gitleaks:allow -->
</head>
<body>
{header}
{trust_strip}
<main id="main-content">
{body_html}
</main>
{footer}
<script type="module" src="{POLITIKKU_PREFIX}lookup.js"></script>
</body>
</html>
"""


_CSS_TEMPLATE = """
  @font-face {
    font-family: 'Newsreader';
    font-style: normal;
    font-weight: 400 600;
    font-display: swap;
    src: url('__PREFIX__fonts/newsreader-variable.woff2') format('woff2');
    unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC,
      U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
  }
  @font-face {
    font-family: 'IBM Plex Sans';
    font-style: normal;
    font-weight: 400 600;
    font-display: swap;
    src: url('__PREFIX__fonts/ibm-plex-sans-variable.woff2') format('woff2');
    unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC,
      U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
  }
  @font-face {
    font-family: 'IBM Plex Mono';
    font-style: normal;
    font-weight: 400;
    font-display: swap;
    src: url('__PREFIX__fonts/ibm-plex-mono-400.woff2') format('woff2');
  }
  @font-face {
    font-family: 'IBM Plex Mono';
    font-style: normal;
    font-weight: 500;
    font-display: swap;
    src: url('__PREFIX__fonts/ibm-plex-mono-500.woff2') format('woff2');
  }

  :root {
    /* Design tokens — design_handoff_politikku/README.md, "Design Tokens" */
    --ink:            #14203a;
    --ink-secondary:  #5f6773;
    --muted:          #6b7280;
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
    --on-dark-muted:  #8a94a6;
    --nav-active-rule: #7fa8a4;

    --serif: 'Newsreader', ui-serif, Georgia, 'Times New Roman', serif;
    --sans:  'IBM Plex Sans', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
    --mono:  'IBM Plex Mono', ui-monospace, Menlo, Monaco, Consolas, 'Courier New', monospace;

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
  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .pk-header :focus-visible, .pk-footer :focus-visible, .pk-landing-hero :focus-visible {
    outline-color: var(--accent-on-dark);
  }
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
  .pk-nav a, .pk-nav-mobile nav a { color: inherit; transition: color .15s ease, border-bottom-color .15s ease; }
  .pk-nav a:hover:not(.active) { color: var(--paper); }
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
  .lang-toggle a {
    padding: 5px 10px;
    color: var(--on-dark-body);
    transition: background .15s ease, color .15s ease;
  }
  .lang-toggle a:hover:not(.lang-current) {
    color: var(--paper);
    background: rgba(251, 250, 247, .12);
  }
  .lang-toggle a.lang-current { background: var(--paper); color: var(--ink); font-weight: 500; }

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
  .pk-dot { color: var(--line-strong); }
  .pk-trust-condensed { display: none; }
  .pk-trust-link {
    margin-left: auto;
    color: var(--accent);
    border-bottom: 1px solid rgba(31, 92, 88, .4);
    transition: border-bottom-color .15s ease, color .15s ease;
  }
  .pk-trust-link:hover {
    border-bottom-color: var(--accent);
    color: var(--accent);
  }

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
    transition: border-bottom-color .15s ease;
  }
  .pk-footer-link:hover { border-bottom-color: var(--accent-on-dark); }
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

  /* Screen-reader-only label text, shared by any page's lookup form —
     kept here rather than redefined per page (a duplication #74's own
     review already caught once for a different utility). */
  .pk-visually-hidden {
    position: absolute; width: 1px; height: 1px; overflow: hidden;
    clip: rect(0 0 0 0); white-space: nowrap;
  }

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

  /* The lookup's dynamic results states (#77) — ts/src/dom.ts populates
     `[data-pk-lookup-results]` (built empty/hidden by #74/#75's own
     markup) with exactly one of these per `LookupState`. Shared here
     rather than duplicated per page, the same call already made for
     `.pk-visually-hidden` above. */
  .pk-lookup-results { margin-top: 14px; max-width: 490px; }
  .pk-lookup-skeleton { display: flex; flex-direction: column; gap: 8px; }
  .pk-lookup-skeleton-bars { display: flex; flex-direction: column; gap: 6px; }
  .pk-lookup-skeleton-bar {
    height: 14px; border-radius: var(--radius-sm);
    background: #e2ded4;
  }
  .pk-lookup-skeleton-bar:nth-child(2) { background: #e8e4da; width: 80%; }
  .pk-lookup-skeleton-bar:nth-child(3) { width: 60%; }
  .pk-lookup-status { margin: 0; font-size: 12.5px; color: var(--muted); }

  .pk-lookup-ambiguous-heading { margin: 0 0 8px; font-size: 13.5px; color: var(--ink-secondary); }
  .pk-lookup-candidate-list { display: flex; flex-direction: column; gap: 8px; }
  .pk-lookup-candidate {
    display: flex; flex-direction: column; gap: 2px; padding: 10px 14px;
    border: 1px solid var(--line); border-radius: var(--radius-md);
    background: var(--white); text-decoration: none;
    transition: border-color .15s ease, box-shadow .15s ease;
  }
  .pk-lookup-candidate:hover { border-color: var(--line-strong); box-shadow: 0 2px 6px rgba(0,0,0,.03); }
  .pk-lookup-candidate[aria-disabled="true"] { cursor: default; opacity: .75; }
  .pk-lookup-candidate-code { font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
  .pk-lookup-candidate-name { font-size: 14px; color: var(--ink); }
  .pk-lookup-candidate-mp { font-size: 12.5px; color: var(--ink-secondary); }
  .pk-lookup-footnote { margin: 8px 0 0; font-family: var(--mono); font-size: 10.5px; color: var(--muted); }

  .pk-lookup-not-found { padding: 12px 14px; border: 1px solid #c9a86a; border-radius: var(--radius-md); }
  /* README: "the input border turns #c9a86a" for a text-query no-match —
     the field itself, not just the results area below it. Higher
     specificity than each page's own `.pk-lookup-form input` rule so the
     colour wins regardless of source order. */
  .pk-lookup-form input.pk-lookup-input-error { border-color: #c9a86a; }
  .pk-lookup-no-match-tag {
    display: inline-block; font-family: var(--mono); font-size: 10px; letter-spacing: .07em;
    text-transform: uppercase; color: var(--caution-deep); background: var(--caution-bg);
    border: 1px solid var(--caution-border); border-radius: var(--radius-sm); padding: 2px 6px;
  }
  .pk-lookup-no-match-reason { margin: 8px 0; font-size: 13px; color: var(--ink-secondary); }
  .pk-lookup-routes { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; }
  .pk-lookup-routes a { font-size: 13px; }

  .pk-lookup-resolved-link { display: inline-block; font-size: 14.5px; color: var(--accent); }
  .pk-lookup-resolved-no-profile { margin: 0; font-size: 13.5px; color: var(--ink-secondary); }

  .pk-recent-chip {
    font-family: var(--sans); font-size: 11.5px; font-weight: 500; color: var(--ink-secondary);
    background: var(--white); border: 1px solid var(--line-strong); border-radius: var(--radius-sm);
    padding: 3px 8px; cursor: pointer; transition: border-color .15s ease, color .15s ease;
  }
  .pk-recent-chip:hover { border-color: var(--accent); color: var(--accent); }

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

_CSS = _CSS_TEMPLATE.replace("__PREFIX__", POLITIKKU_PREFIX)
"""`_CSS_TEMPLATE` bound to the one route family PolitikKu's self-hosted
fonts are served from — the same `.replace` substitution
`_language_persistence_script` makes, and for the same reason: the stylesheet
is brace-dense, so an f-string is not available. The fonts are PolitikKu's
own assets rather than any one page's, so this is `POLITIKKU_PREFIX` and not
the per-page `prefix` — a `/projection/` page loads the same
`{POLITIKKU_PREFIX}fonts/...` files the homepage does."""
