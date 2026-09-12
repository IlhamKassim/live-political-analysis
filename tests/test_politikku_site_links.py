"""The surviving PolitikKu pages rendered to disk, with every internal link
followed.

#104's cutover moved PolitikKu from the `/politikku/` staging prefix to the
site root, which is the kind of change that breaks links rather than tests:
each page still renders, each `href` is still well-formed, and every one of
them points at a directory that no longer exists. So this module does what a
reader would — renders every page at the path its own `main()` writes it to,
walks every `href`/`src` on each one, and resolves it against that rendered
tree.

ADR 0014 retired the old `politikku_homepage.py` surface. Its legacy routes
remain outside this renderer sweep as redirect stubs. ADR 0017 restored
`politikku_landing.py` as the orientation page at `/` and `/ms/`, while the
Bills and MP-profile renderers use their current directory routes. Those
paths are covered here: they are the pages every other page's wordmark and
methodology footer point at, and the sweep follows the map link, the two data
panels' "full ledger"/"all Bills" links, the Sentiment/Dewan/Politicians link
row and the glossary link on each.

Still excluded, for `GENERATED_BY_ANOTHER_BUILD_STEP`'s own reason — nothing
here can render them to check, not that nothing points at them: `/app/...`
(the frontend fold-in step's plain `cp -r` in `daily.yml`) and the retired
pages' old paths (`politikku_redirects.py` stubs).

Fixture data throughout, reusing the models the per-page test modules
already build, so this needs no Storage — it is a check on routing, not on
figures.
"""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

import pytest
from test_politikku_methodology import _projection_model

from lpa.bill_tracker import Bill
from lpa.politikku_analyst import build_and_write_analyst_page
from lpa.politikku_landing import (
    CoalitionRow,
    LandingModel,
    _copy_observatory_assets,
    render_landing_page,
)
from lpa.politikku_methodology import render_methodology
from lpa.politikku_shell import (
    METHODOLOGY_PAGE,
    NAV_LINKS,
    POLITIKKU_PREFIX,
    PROJECTION_PREFIX,
    Language,
    _en_route,
    _ms_route,
)

PROJECTION_PAGE = "index.html"

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
        "/bills/",
        "/ms/bills/",
        "/politicians/",
        "/dewan/",
        "/ms/politicians/",
        "/ms/dewan/",
    }
)
_APP_ROOTED_PREFIXES = ("/app/", "/mp/")
"""Routes no page renderer in this fixture writes: the Bills page
(`"/bills/"` — `politikku_bills.py` renders it, but from
`frontend/public/data/bills.json`, which this routing-only fixture does not
load), the Politicians and Dewan directory routes, and every `/app/#...` or
`/mp/<code>/` link. Excluded from link resolution below for
`GENERATED_BY_ANOTHER_BUILD_STEP`'s own reason — nothing here can render
them to check.

`"/"` and `"/ms/"` came off this list with ADR 0017: `politikku_landing.py`
renders them again, the fixture below writes them, and their links are now
followed like any other page's."""


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
    _copy_observatory_assets(root)
    build_and_write_analyst_page(root)
    tools_dir = REPO_ROOT / "public" / "analyst" / "tools"
    if tools_dir.is_dir():
        shutil.copytree(tools_dir, root / "analyst" / "tools")
    frontend_public = REPO_ROOT / "frontend" / "public"
    for name in ("styles.css", "lib.js", "lib-swing.js", "analyst-tools.js"):
        src = frontend_public / name
        if src.is_file():
            shutil.copy2(src, root / name)
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

    for language in Language:
        ms = "" if language is Language.EN else "ms/"
        sentiment_path = (
            "sentiment/index.html" if language is Language.EN else "ms/sentiment/index.html"
        )
        _write(root, sentiment_path, render_methodology(page, language=language))
        _write(root, f"{ms}{METHODOLOGY_PAGE}", render_methodology(page, language=language))
        _write(
            root,
            f"{ms}{projection_dir}/{PROJECTION_PAGE}",
            render_methodology(page, language=language),
        )
        # ADR 0017's orientation gate at `/` and `/ms/`. Fixture model, so
        # nothing here reads `public/projection.json` or `bills.json` —
        # this sweep checks routing, and no figure on the page changes a
        # single href. The Coalition rows and Bills are non-empty on
        # purpose, though: an empty model would drop the two data panels
        # and take their `/projection/` and `/bills/` links out of the
        # sweep along with them.
        _write(
            root,
            f"{ms}index.html",
            render_landing_page(
                LandingModel(
                    government_majority=True,
                    coalitions=(
                        CoalitionRow("PH", 75, "#d7263d", True),
                        CoalitionRow("PN", 69, "#15387c", False),
                    ),
                    bills=(
                        Bill(
                            code="D.R.22/2026",
                            title="RUU Contoh 2026",
                            year=2026,
                            stage="Lulus",
                            stage_date=date(2026, 7, 16),
                            summary="Petikan.",
                            summary_source_url="https://www.parlimen.gov.my/x.pdf",
                        ),
                    ),
                    majority_threshold=112,
                    total_seats=222,
                    updated_at=date(2026, 1, 1),
                    sources_count=7,
                    status=page.status,
                ),
                language=language,
            ),
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


def test_spa_sidebar_content_fetches_use_published_root_paths():
    """Sidebar clicks fetch pages from the site root, not below ``/app/``.

    The app intercepts these links and hydrates their content in place. Relative
    URLs resolve below ``/app/`` on the map, where these pages do not exist.
    """
    app_js = (REPO_ROOT / "frontend" / "public" / "app.js").read_text(encoding="utf-8")

    assert 'input.startsWith("learn/")' not in app_js
    assert 'lang === "ms" ? "/ms/methodology.html" : "/methodology.html"' in app_js
    assert 'fetch("/learn/glossary.html")' in app_js
    assert 'fetch("/learn/coalitions.html")' in app_js
    assert 'fetch("/learn/ge16-process.html")' in app_js


def test_every_page_is_written_under_the_site_root_not_a_sub_prefix(rendered_site):
    # The cutover itself, stated as file paths: PolitikKu's own pages sit at
    # the root of the published directory. A `politikku/` directory here
    # would mean a page's `main()` still writes the staging prefix. Since
    # ADR 0017 the site root's own `index.html` is in scope again —
    # `politikku_landing.build_and_write_landing_pages` writes it, not the
    # frontend fold-in's `cp -r`.
    assert POLITIKKU_PREFIX == "/"
    assert not (rendered_site / "politikku").exists()
    assert (rendered_site / "index.html").is_file()
    assert (rendered_site / "ms" / "index.html").is_file()


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
    #
    # Four toggle links on a chrome-bearing page: EN and BM, rendered once
    # in the sidebar and again in the topbar. The landing page renders
    # `chrome=False` (ADR 0017) and carries the pair once, in its own
    # header — one toggle, still both languages, which is the property this
    # test is actually about.
    for page_path in sorted(rendered_site.rglob("*.html")):
        if page_path.parent.name == "learn":
            continue
        page = page_path.read_text(encoding="utf-8")
        toggles = re.findall(r'href="([^"]+)" (?:aria-current="page" )?data-pk-set-lang=', page)
        if page_path.parent.name == "analyst":
            # Its own header, like the landing page: one EN/BM pair, to the
            # two Analyst pages.
            assert set(toggles) == {"/analyst/", "/ms/analyst/"}, page_path
            for link in toggles:
                assert _resolve(rendered_site, link).is_file(), (page_path, link)
            continue
        if "tools" in page_path.parts and "analyst" in page_path.parts:
            # Workbench uses minimal chrome — no language toggle.
            continue
        bare = 'class="pk-bare"' in page
        assert len(toggles) == (2 if bare else 4), page_path
        assert set(toggles) == {_en_route(""), _ms_route("")} if bare else True
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


def test_the_seat_url_the_browser_builds_matches_the_apps_own_hash_route():
    # `ts/src/dom.ts` builds the postcode-lookup widget's Seat href
    # client-side, from a route it cannot import — so nothing but this
    # comparison keeps that destination in step with the map's hash router.
    # The router (`frontend/public/lib.js` decodeHash) reads
    # `#<tier>/<mode>/<code>`; the lookup links to the Parliament layer
    # coloured by Coalition. (The old `/mp/<code>.html` target is gone from
    # dom.ts; `politikku_redirects.py` still stubs it for old links.)
    dom = (REPO_ROOT / "ts" / "src" / "dom.ts").read_text(encoding="utf-8")
    assert "`/app/#parlimen/parti/${encodeURIComponent(code)}`" in dom

    lib = (REPO_ROOT / "frontend" / "public" / "lib.js").read_text(encoding="utf-8")
    assert "const [tier, mode, third] = toks;" in lib
    assert "const parts = [state.tier, state.mode];" in lib
