"""The whole site rendered to disk, with every internal link followed.

#104's cutover moved PolitikKu from the `/politikku/` staging prefix to the
site root, which is the kind of change that breaks links rather than tests:
each page still renders, each `href` is still well-formed, and every one of
them points at a directory that no longer exists. So this module does what a
reader would — renders every page at the path its own `main()` writes, walks
every `href`/`src` on each one, and resolves it against that rendered tree.

Deliberately not a unit test of any one module: the two halves this checks
(what a page links to, and where the page it links to is written) live in
different modules, and each half is individually self-consistent whichever
prefix is in force. Nothing but rendering the tree catches a disagreement.

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
from test_politikku_homepage import NAMES, _bill, _page_model
from test_politikku_landing import BANGI, FEATURED_BILL, _history
from test_politikku_mp_profile import _baseline, _call, _profile

from lpa.politikku_bills import BillsPageModel, render_bills_page
from lpa.politikku_homepage import homepage_model, render_homepage
from lpa.politikku_landing import landing_model, render_landing
from lpa.politikku_mp_profile import mp_profile_page_model, render_mp_profile
from lpa.politikku_projection import (
    METHODOLOGY_PAGE,
    PROJECTION_PAGE,
    PROJECTION_PREFIX,
    render_methodology,
    render_projection,
)
from lpa.politikku_sentiment import render_sentiment_page, sentiment_page_model
from lpa.politikku_shell import (
    MP_PROFILE_DIR,
    POLITIKKU_PREFIX,
    Language,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

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

_LINK = re.compile(r'(?:href|src)="([^"]+)"')


def _write(root: Path, path: str, page: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")


@pytest.fixture(scope="module")
def rendered_site(tmp_path_factory) -> Path:
    """Every PolitikKu page, in both languages, at the path its own `main()`
    writes it to — `public/` with the repo's real committed assets in it."""
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
    shutil.copytree(REPO_ROOT / "public" / "learn", root / "learn")

    page = _page_model()
    bills = {"D.R.1/2026": _bill("D.R.1/2026", 2026, "Lulus", date(2026, 8, 1))}
    homepage = homepage_model(page, [], NAMES, bills)
    landing = landing_model(page, _history(), NAMES, BANGI, FEATURED_BILL)
    profile = mp_profile_page_model(page, _profile(), _baseline(), _call(), NAMES)
    projection_dir = PROJECTION_PREFIX.strip("/")

    bills_model = BillsPageModel(
        bills=tuple(bills.values()),
        updated_at=page.computed_at,
        sources_count=len(page.sources),
        status=page.status,
    )
    sentiment_model = sentiment_page_model(
        snapshots=[],
        names=NAMES,
        status=page.status,
    )

    for language in Language:
        ms = "" if language is Language.EN else "ms/"
        _write(root, f"{ms}index.html", render_homepage(homepage, language=language))
        _write(root, f"{ms}landing.html", render_landing(landing, language=language))
        _write(root, f"{ms}bills.html", render_bills_page(bills_model, language=language))
        _write(
            root, f"{ms}sentiment.html", render_sentiment_page(sentiment_model, language=language)
        )
        _write(root, f"{ms}{METHODOLOGY_PAGE}", render_methodology(page, language=language))
        _write(
            root,
            f"{ms}{MP_PROFILE_DIR}/{profile.seat_code}.html",
            render_mp_profile(profile, language=language),
        )
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
        and link not in GENERATED_BY_ANOTHER_BUILD_STEP
    }


def test_every_page_is_written_under_the_site_root_not_a_sub_prefix(rendered_site):
    # The cutover itself, stated as file paths: PolitikKu's own pages sit at
    # the root of the published directory. A `politikku/` directory here
    # would mean a page's `main()` still writes the staging prefix.
    assert POLITIKKU_PREFIX == "/"
    assert (rendered_site / "index.html").is_file()
    assert (rendered_site / "ms" / "index.html").is_file()
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
    assert checked > 40


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
        assert len(toggles) == 2, page_path
        for link in toggles:
            assert _resolve(rendered_site, link).is_file(), (page_path, link)


def test_the_pages_the_shell_links_on_every_page_are_all_real(rendered_site):
    # Named individually rather than left to the sweep above, because these
    # four are the links that appear on *every* page — a broken one is a
    # broken site, not a broken page.
    home = (rendered_site / "index.html").read_text(encoding="utf-8")
    for link in ("/", "/ms/", "/methodology.html", "/landing.html", "/projection/"):
        assert _resolve(rendered_site, link).is_file()
    assert '/methodology.html"' in home
    assert '/landing.html"' in home
    assert '/projection/"' in home


def test_the_assets_no_page_renderer_writes_are_named_by_the_step_that_does(rendered_site):
    # `/lookup.js` and `/data/lookup-index.json` are part of every page but
    # written by the TypeScript build and the lookup-index module — neither
    # of which can be exercised from here. So this checks the one thing that
    # can go wrong: the file that decides each path disagreeing with the URL
    # that actually asks for it.
    home = (rendered_site / "index.html").read_text(encoding="utf-8")
    build = (REPO_ROOT / GENERATED_BY_ANOTHER_BUILD_STEP["/lookup.js"]).read_text(encoding="utf-8")
    assert '"/lookup.js"' in home
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

    # The fonts, by contrast, are committed — so their real path is checkable.
    fonts = re.findall(r"[\w/.-]*\.woff2", home)
    assert fonts
    for font in fonts:
        assert (REPO_ROOT / "public" / font.lstrip("/")).is_file(), font


def test_the_mp_profile_url_the_browser_builds_is_the_path_the_pages_are_written_at(
    rendered_site,
):
    # `ts/src/dom.ts` builds this href client-side, from a constant it cannot
    # import — so nothing but this comparison keeps the constituency lookup's
    # one destination in step with where the profiles are actually written.
    dom = (REPO_ROOT / "ts" / "src" / "dom.ts").read_text(encoding="utf-8")
    assert f"`/{MP_PROFILE_DIR}/${{encodeURIComponent(code)}}.html`" in dom
    written = sorted(p.name for p in (rendered_site / MP_PROFILE_DIR).iterdir())
    assert written and all(name.endswith(".html") for name in written)
