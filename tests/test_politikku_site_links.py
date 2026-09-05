"""The surviving PolitikKu pages rendered to disk, with every internal link
followed.

#104's cutover moved PolitikKu from the `/politikku/` staging prefix to the
site root, which is the kind of change that breaks links rather than tests:
each page still renders, each `href` is still well-formed, and every one of
them points at a directory that no longer exists. So this module does what a
reader would — renders every page at the path its own `main()` writes it to,
walks every `href`/`src` on each one, and resolves it against that rendered
tree.

ADR 0014 (the mypolitik-frontend root swap) retired `politikku_landing.py`,
`politikku_homepage.py`, `politikku_bills.py` and `politikku_mp_profile.py`
together — this module used to render all seven PolitikKu pages and follow
links between them; now it renders the four that survive
(`politikku_projection`, `politikku_sentiment`, `politikku_learn`'s three
pages) plus the hand-authored `learn/` pages. `/`, `/app/...` and the old
retired-page paths are no longer written by any Python renderer at all — the
site root and `/app/` come from the frontend fold-in step in `daily.yml`
(a plain file copy, nothing this suite can exercise), and the retired pages'
old paths are `politikku_redirects.py` stubs. Both are excluded from the
link-resolution sweep below, the same way `GENERATED_BY_ANOTHER_BUILD_STEP`
already excludes `/lookup.js` and friends — not because nothing points at
them, but because nothing here can render them to check.

Fixture data throughout, reusing the models the per-page test modules
already build, so this needs no Storage — it is a check on routing, not on
figures.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from test_politikku_projection import NAMES, _projection_model

from lpa.politikku_projection import (
    METHODOLOGY_PAGE,
    PROJECTION_PAGE,
    PROJECTION_PREFIX,
    render_methodology,
    render_projection,
)
from lpa.politikku_sentiment import render_sentiment_page, sentiment_page_model
from lpa.politikku_shell import NAV_LINKS, POLITIKKU_PREFIX, Language

REPO_ROOT = Path(__file__).resolve().parent.parent

# IDs inside `.sb-nav` that are UI controls rather than NAV_LINKS destinations.
# The SPA's other sidebar-only chrome (`sb-brand`, `sb-collapse`, `sb-states`,
# `sb-state-hover-label`, `sb-about`, and `sb-share`) lives outside this nav block.
SIDEBAR_IDS_WITHOUT_A_NAV_LINK: frozenset[str] = frozenset()

UNBUILT_ROUTES: frozenset[str] = frozenset()
"""The nav items the design handoff itself asks to be "wired to routes
that don't need to exist yet" — none remaining. Listed explicitly rather than
skipped by pattern so that adding a route has to come through here."""

GENERATED_BY_ANOTHER_BUILD_STEP = {
    "/lookup.js": "ts/build.mjs",
    "/data/lookup-index.json": "src/lpa/politikku_lookup_index.py",
    "/projection.csv": "src/lpa/public_export.py",
    "/projection.json": "src/lpa/public_export.py",
}
"""Real published files that no Python page renderer writes, so they cannot
be in the rendered tree. The value is the file that decides their path, and
the test below asserts that file actually names it — the same disagreement
this module exists to catch, one build step over."""

_APP_ROOTED_EXACT = frozenset(
    {
        "/",
        "/ms/",
        "/bills/",
        "/politicians/",
        "/dewan/",
        "/ms/politicians/",
        "/ms/dewan/",
    }
)
_APP_ROOTED_PREFIXES = ("/app/", "/mp/")
"""What the frontend fold-in step (`daily.yml`'s plain `cp -r`, not a Python
renderer) is responsible for, post-ADR-0014: the site root itself (`"/"`, the
Home nav item's href — every root-*relative* link starts with `/` too, so
this is an exact match, not a prefix), the Bills page (`"/bills/"`),
Politicians and Dewan directory routes, and
every `/app/#...` or `/mp/<code>/` link. Excluded from link resolution below for
`GENERATED_BY_ANOTHER_BUILD_STEP`'s own reason — nothing here can render
them to check."""


def _is_app_rooted(link: str) -> bool:
    return link in _APP_ROOTED_EXACT or link.startswith(_APP_ROOTED_PREFIXES)


_LINK = re.compile(r'(?:href|src)="([^"]+)"')


def _write(root: Path, path: str, page: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")


@pytest.fixture(scope="module")
def rendered_site(tmp_path_factory) -> Path:
    """Every surviving PolitikKu page, in both languages, at the path its own
    `main()` writes it to."""
    root = tmp_path_factory.mktemp("public")
    # The committed, non-generated part of `public/`: the self-hosted fonts
    # the shell preloads (mirrored by name — symlinking is not portable
    # here), and `learn/`'s hand-authored civic-education pages, copied in
    # whole. Those are deployed by the same step as everything else and link
    # into the pages below, so leaving them out would mean the sweep
    # "passed" while a real published page pointed at the retired URL.
    for font in (REPO_ROOT / "public" / "fonts").iterdir():
        _write(root, f"fonts/{font.name}", "")
    _write(root, "favicon.ico", "")
    from lpa.config import load_election_status
    from lpa.politikku_learn import build_coalitions_page, build_glossary_page, build_process_page

    status = load_election_status()
    for lang in [Language.EN, Language.MS]:
        lang_prefix = "ms/" if lang == Language.MS else ""
        _write(
            root,
            f"{lang_prefix}learn/glossary.html",
            build_glossary_page(lang, date(2026, 1, 1), status),
        )
        _write(
            root,
            f"{lang_prefix}learn/coalitions.html",
            build_coalitions_page(lang, date(2026, 1, 1), status),
        )
        _write(
            root,
            f"{lang_prefix}learn/ge16-process.html",
            build_process_page(lang, date(2026, 1, 1), status),
        )

    # Still need to copy the static JS for the learn pages that we haven't touched
    _write(
        root,
        "learn/live-figures.js",
        (REPO_ROOT / "public" / "learn" / "live-figures.js").read_text(),
    )

    page = _projection_model()
    projection_dir = PROJECTION_PREFIX.strip("/")

    sentiment_model = sentiment_page_model(
        snapshots=[],
        names=NAMES,
        status=page.status,
    )

    for language in Language:
        ms = "" if language is Language.EN else "ms/"
        sentiment_path = (
            "sentiment/index.html" if language is Language.EN else "ms/sentiment/index.html"
        )
        _write(root, sentiment_path, render_sentiment_page(sentiment_model, language=language))
        _write(root, f"{ms}{METHODOLOGY_PAGE}", render_methodology(page, language=language))
        _write(
            root,
            f"{projection_dir}/{ms}{PROJECTION_PAGE}",
            render_projection(page, language=language),
        )
    return root


EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:")


def _resolve(root: Path, link: str, *, page_dir: Path | None = None) -> Path:
    """The file a link names — a directory route (`/`, `/projection/ms/`,
    `../projection/`) resolving to its `index.html`, the same way a static
    host serves it. `page_dir` is what a *relative* link resolves against:
    the hand-authored `public/learn/` pages link that way, the rendered
    PolitikKu pages are root-relative throughout."""
    path = link.split("#", 1)[0].split("?", 1)[0]
    if path.startswith("/"):
        base, relative = root, path.removeprefix("/")
    else:
        base, relative = page_dir or root, path
    if relative == "" or relative.endswith("/"):
        relative += "index.html"
    return (base / relative).resolve()


def _internal_links(page: str) -> set[str]:
    return {
        link
        for link in _LINK.findall(page)
        if link
        and not link.startswith(EXTERNAL_SCHEMES)
        and not link.startswith("#")
        and not _is_app_rooted(link)
        and link not in GENERATED_BY_ANOTHER_BUILD_STEP
    }


def test_the_spa_sidebar_and_nav_links_agree_on_which_destinations_exist():
    """Four NAV_LINKS destinations once became unreachable from the map homepage.
    Keep later additions from silently disappearing from either sidebar again.
    """
    expected = {link.key for link in NAV_LINKS}
    index_html = (REPO_ROOT / "frontend" / "public" / "index.html").read_text(encoding="utf-8")
    nav_match = re.search(r'<nav class="sb-nav">(.*?)</nav>', index_html, flags=re.DOTALL)
    assert nav_match is not None, "the SPA sidebar's .sb-nav block is missing"
    extracted = set(re.findall(r'id="sb-([a-z0-9-]+)"', nav_match.group(1)))
    extracted -= SIDEBAR_IDS_WITHOUT_A_NAV_LINK

    assert extracted == expected, (
        "SPA sidebar and NAV_LINKS destinations differ: "
        f"symmetric difference={sorted(extracted ^ expected)}; "
        f"SPA only={sorted(extracted - expected)}; NAV_LINKS only={sorted(expected - extracted)}"
    )


def test_every_page_is_written_under_the_site_root_not_a_sub_prefix(rendered_site):
    # The cutover itself, stated as file paths: PolitikKu's own pages sit at
    # the root of the published directory. A `politikku/` directory here
    # would mean a page's `main()` still writes the staging prefix. The site
    # root's own `index.html` is out of scope for this assertion since ADR
    # 0014: it is the frontend fold-in step's `cp -r`, not any Python
    # renderer's `main()`, that writes it now.
    assert POLITIKKU_PREFIX == "/"
    assert not (rendered_site / "politikku").exists()


def test_every_internal_link_on_every_page_resolves_to_a_rendered_file(rendered_site):
    unresolved: list[tuple[str, str]] = []
    checked = 0
    for page_path in sorted(rendered_site.rglob("*.html")):
        page = page_path.read_text(encoding="utf-8")
        for link in sorted(_internal_links(page)):
            if link in UNBUILT_ROUTES:
                continue
            checked += 1
            if not _resolve(rendered_site, link, page_dir=page_path.parent).is_file():
                unresolved.append((str(page_path.relative_to(rendered_site)), link))

    assert not unresolved, f"internal links pointing at nothing: {unresolved}"
    # Guards against the loop above silently checking nothing at all (an
    # empty tree, or a regex that stopped matching).
    assert checked > 20


def test_the_language_toggle_on_every_page_reaches_the_other_language(rendered_site):
    # The one link a reader is most likely to notice broken, and the one the
    # cutover was most likely to break: it is built from the page's own
    # `prefix`, not from a nav table. Every page built on the PolitikKu
    # shell, which is every page here except the hand-authored `learn/`
    # ones (they predate PolitikKu and carry no shell — #26/#27/#28).
    for page_path in sorted(rendered_site.rglob("*.html")):
        if page_path.parent.name == "learn":
            continue
        page = page_path.read_text(encoding="utf-8")
        toggles = re.findall(r'href="([^"]+)" (?:aria-current="page" )?data-pk-set-lang=', page)
        assert len(toggles) == 4, page_path
        for link in toggles:
            assert _resolve(rendered_site, link).is_file(), (page_path, link)


def test_the_pages_the_shell_links_on_every_page_are_all_real(rendered_site):
    # Named individually rather than left to the sweep above, because these
    # are links that appear on *every* PolitikKu-shell page — a broken one
    # is a broken site, not a broken page. Checked off the sentiment page's
    # own outbound links, which still exercises the persistent nav/footer
    # every other shell page also carries. ADR 0014 dropped `/home.html`
    # (the "Dashboard" nav item merged into `/app/`, which this module
    # cannot render — see `APP_ROOTED_LINKS`) from this list.
    sentiment = (rendered_site / "sentiment" / "index.html").read_text(encoding="utf-8")
    for link in ("/methodology.html", "/projection/"):
        assert _resolve(rendered_site, link).is_file()
    assert '/methodology.html"' in sentiment
    assert '/projection/"' in sentiment
    # "Bills" is the nav item pointing to `/bills/` (politikku_shell.NavLink.external),
    # checked directly since _resolve can't follow it (see _APP_ROOTED_EXACT).
    assert '/bills/"' in sentiment


def test_the_assets_no_page_renderer_writes_are_named_by_the_step_that_does(rendered_site):
    # `/lookup.js` and `/data/lookup-index.json` are part of every page but
    # written by the TypeScript build and the lookup-index module — neither
    # of which can be exercised from here. So this checks the one thing that
    # can go wrong: the file that decides each path disagreeing with the URL
    # that actually asks for it.
    sentiment = (rendered_site / "sentiment" / "index.html").read_text(encoding="utf-8")
    build = (REPO_ROOT / GENERATED_BY_ANOTHER_BUILD_STEP["/lookup.js"]).read_text(encoding="utf-8")
    assert '"/lookup.js"' in sentiment
    assert "public/lookup.js" in build

    # The lookup index is fetched by the bundle at runtime, so it never
    # appears in the HTML at all — the two ends that have to agree are
    # `index-data.ts`'s default URL and the module that writes the file.
    fetched_by = (REPO_ROOT / "ts" / "src" / "index-data.ts").read_text(encoding="utf-8")
    written_by = (REPO_ROOT / GENERATED_BY_ANOTHER_BUILD_STEP["/data/lookup-index.json"]).read_text(
        encoding="utf-8"
    )
    assert '"/data/lookup-index.json"' in fetched_by
    assert '"public/data/lookup-index.json"' in written_by

    # The projection data exports are written by public_export.py.
    export_written = (REPO_ROOT / GENERATED_BY_ANOTHER_BUILD_STEP["/projection.json"]).read_text(
        encoding="utf-8"
    )
    assert '"projection.json"' in export_written
    assert '"projection.csv"' in export_written

    # JetBrains Mono and Space Grotesk are self-hosted.
    assert "fonts.googleapis.com" not in sentiment
    assert "/fonts/jetbrains-mono-latin.woff2" in sentiment
    assert "Space+Grotesk" not in sentiment
    assert "/fonts/space-grotesk-latin.woff2" in sentiment


def test_the_mp_profile_url_the_browser_builds_matches_the_apps_own_hash_route(rendered_site):
    # `ts/src/dom.ts` builds the postcode-lookup widget's MP-profile href
    # client-side, from a constant it cannot import — so nothing but this
    # comparison keeps that destination in step with where a Seat actually
    # resolves. ADR 0014 retired the `/mp/<code>.html` pages themselves (now
    # a `politikku_redirects.py` stub); `ts/src/dom.ts` still builds that
    # same old URL, which is fine (the stub exists precisely so old
    # links keep working) but means this check only guards against that URL
    # drifting from the one `politikku_redirects.py` actually writes, not
    # against a page this suite renders.
    from lpa.politikku_shell import MP_PROFILE_DIR

    dom = (REPO_ROOT / "ts" / "src" / "dom.ts").read_text(encoding="utf-8")
    assert f"`/{MP_PROFILE_DIR}/${{encodeURIComponent(code)}}.html`" in dom

    redirects_module = (REPO_ROOT / "src" / "lpa" / "politikku_redirects.py").read_text(
        encoding="utf-8"
    )
    assert "{MP_PROFILE_DIR}/{code}.html" in redirects_module
