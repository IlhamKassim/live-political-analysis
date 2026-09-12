"""A phone-layout sweep: no page scrolls sideways at the widths people hold.

Most of PolitikKu's readers arrive on a phone, and horizontal overflow is the
layout bug no unit test can see: the markup is correct, the CSS is valid, and
the page still runs past the right edge so part of it cannot be reached. That
is what happened to the shared topbar, where the menu button ended up off a
320px screen. This renders the real pages, serves them, and measures them in a
browser.

The sweep covers one page from each of the site's two layers: the hand-written
landing and Analyst pages, and a `render_shell` page, which shares its header
and footer with every other page on the site — so a shell regression is caught
once here rather than separately on each page.

Text size is checked on the pages that pass it today: the landing page and the
shell. Analyst is not in that list — it is the pilot page, and it still has
roughly thirty rules between 8px and 10px, so adding it here would land a red
test. Add it to FONT_CHECKED_PAGES once those are raised.

The third phone check, no standalone control smaller than 44px, is not asserted
anywhere yet: footer links are 16px tall and the landing's "Explore the map" is
19px. The helper that measures it is kept below, unused, so the check can be
switched on the same way once the controls are resized.
"""

from __future__ import annotations

import contextlib
import http.server
import threading
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from lpa.config import load_election_status
from lpa.politikku_analyst import build_and_write_analyst_page
from lpa.politikku_landing import build_and_write_landing_pages
from lpa.politikku_learn import build_process_page
from lpa.politikku_pru16 import pru16_model, render_pru16_page
from lpa.politikku_shell import Language

playwright = pytest.importorskip("playwright.sync_api")

# The narrowest phone still in real use, the two common iPhone widths, and a
# large phone.
VIEWPORTS = ((320, 700), (375, 667), (390, 844), (430, 932))
PAGES = ("/", "/analyst/", "/learn/ge16-process.html", "/pru16/")
# The pages whose text sizes are clean today — see the module docstring.
FONT_CHECKED_PAGES = ("/", "/learn/ge16-process.html", "/pru16/")
# Same, for the size of the things you tap. Analyst qualifies here even though
# its text sizes do not, so it is checked for one and not the other.
TARGET_CHECKED_PAGES = PAGES

# Apple and Google both put the minimum comfortable tap target at 44px, and
# text below 11px is where phone browsers start offering to zoom.
MIN_TAP_TARGET = 44
MIN_FONT_SIZE = 11


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextlib.contextmanager
def _serve(directory: Path) -> Iterator[str]:
    """Serve a directory on a spare port for the length of the block."""

    def handler(*args: object, **kwargs: object) -> _QuietHandler:
        return _QuietHandler(*args, directory=str(directory), **kwargs)  # type: ignore[arg-type]

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture(scope="module")
def mobile_site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Build the pages once, then serve them for every viewport in the sweep."""
    root = tmp_path_factory.mktemp("mobile-site")
    build_and_write_landing_pages(root)
    build_and_write_analyst_page(root)

    learn = root / "learn"
    learn.mkdir(parents=True, exist_ok=True)
    process = build_process_page(Language.EN, date.today(), load_election_status())  # noqa: DTZ011
    (learn / "ge16-process.html").write_text(process, encoding="utf-8")

    pru16 = root / "pru16"
    pru16.mkdir(parents=True, exist_ok=True)
    (pru16 / "index.html").write_text(
        render_pru16_page(pru16_model(), Language.EN), encoding="utf-8"
    )

    # The lookup script is fetched by the landing page and lives outside the
    # renderers; an empty file keeps the request from 404ing mid-measurement.
    (root / "lookup.js").write_text("", encoding="utf-8")

    with _serve(root) as url:
        yield url


def visible_text_below(page: object, minimum: int) -> list[dict[str, str | float]]:
    """Every element with its own visible text rendered below `minimum` px."""
    return page.evaluate(  # type: ignore[attr-defined]
        """minimum => [...document.querySelectorAll('body *')]
          .filter(el => {
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            if (el.closest('[aria-hidden="true"]')) return false;
            const ownText = [...el.childNodes]
              .filter(node => node.nodeType === Node.TEXT_NODE)
              .map(node => node.textContent.trim()).join(' ');
            return ownText && el.getClientRects().length && parseFloat(style.fontSize) > 0;
          })
          .filter(el => parseFloat(getComputedStyle(el).fontSize) < minimum)
          .map(el => ({
            tag: el.tagName.toLowerCase(),
            className: String(el.className),
            text: el.textContent.trim().slice(0, 80),
            size: parseFloat(getComputedStyle(el).fontSize),
          }))""",
        minimum,
    )


def small_targets(page: object, minimum: int) -> list[dict[str, str | float]]:
    """Every standalone control whose box is smaller than `minimum` px.

    Links sitting inline in a sentence are skipped: WCAG 2.5.8 exempts them,
    and sizing them to 44px would wreck the line spacing of running text.
    """
    return page.evaluate(  # type: ignore[attr-defined]
        """minimum => [...document.querySelectorAll('a[href], button, input, summary')]
          .filter(el => {
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            if (!el.getClientRects().length || el.closest('[aria-hidden="true"]')) return false;
            // Inline in running text: the parent is a text block and carries
            // words of its own alongside the link.
            const parent = el.parentElement;
            if (parent && /^(P|LI|SPAN|SMALL|TD|DD|FIGCAPTION)$/.test(parent.tagName)) {
              const around = [...parent.childNodes]
                .filter(node => node.nodeType === Node.TEXT_NODE)
                .map(node => node.textContent.trim()).join('');
              if (around) return false;
            }
            return true;
          })
          .map(el => {
            const rect = el.getBoundingClientRect();
            return {tag: el.tagName.toLowerCase(), className: String(el.className),
              text: (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 80),
              width: rect.width, height: rect.height};
          })
          .filter(item => item.width < minimum || item.height < minimum)""",
        minimum,
    )


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
@pytest.mark.parametrize("path", PAGES)
def test_mobile_pages_do_not_scroll_sideways(
    mobile_site: str, path: str, width: int, height: int
) -> None:
    with playwright.sync_playwright() as manager:
        browser = manager.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(mobile_site + path, wait_until="networkidle")

        # One pixel of slack: sub-pixel rounding can report a hairline of
        # overflow on a layout that is actually flush.
        overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
        assert overflow <= 1, f"{path} scrolls sideways by {overflow}px at {width}px"
        browser.close()


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
@pytest.mark.parametrize("path", FONT_CHECKED_PAGES)
def test_mobile_pages_keep_their_text_readable(
    mobile_site: str, path: str, width: int, height: int
) -> None:
    with playwright.sync_playwright() as manager:
        browser = manager.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(mobile_site + path, wait_until="networkidle")

        assert visible_text_below(page, MIN_FONT_SIZE) == []
        browser.close()


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
@pytest.mark.parametrize("path", TARGET_CHECKED_PAGES)
def test_mobile_pages_keep_their_controls_big_enough_to_tap(
    mobile_site: str, path: str, width: int, height: int
) -> None:
    with playwright.sync_playwright() as manager:
        browser = manager.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(mobile_site + path, wait_until="networkidle")

        assert small_targets(page, MIN_TAP_TARGET) == []
        browser.close()


@pytest.mark.browser
@pytest.mark.parametrize(("width", "height"), VIEWPORTS)
def test_the_landing_wordmark_is_not_covered_by_the_language_switch(
    mobile_site: str, width: int, height: int
) -> None:
    """Two boxes can overlap without the page overflowing, so the sweep above
    cannot see this: at 320px the language pill sat on top of "PolitikKu" and
    cut it in half."""
    with playwright.sync_playwright() as manager:
        browser = manager.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(mobile_site + "/", wait_until="networkidle")

        brand = page.locator("header.nav .brand").bounding_box()
        lang = page.locator("header.nav .obs-lang").bounding_box()
        assert brand is not None and lang is not None
        assert brand["x"] + brand["width"] <= lang["x"], (
            f"the wordmark runs to {brand['x'] + brand['width']}px at {width}px, "
            f"under a language switch starting at {lang['x']}px"
        )
        browser.close()
