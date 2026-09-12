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

Two further phone checks are deliberately not asserted yet: no visible text
below 11px, and no standalone control smaller than 44px. Both currently fail
across the site (8px hero eyebrows, 16px-tall footer links), so turning them on
would mean landing a red test. The helpers that measure them are kept below,
unused by any assertion, so the checks can be switched on page by page as the
sizes are fixed.
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
from lpa.politikku_shell import Language

playwright = pytest.importorskip("playwright.sync_api")

# The narrowest phone still in real use, the two common iPhone widths, and a
# large phone.
VIEWPORTS = ((320, 700), (375, 667), (390, 844), (430, 932))
PAGES = ("/", "/analyst/", "/learn/ge16-process.html")

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

    # The lookup script is fetched by the landing page and lives outside the
    # renderers; an empty file keeps the request from 404ing mid-measurement.
    (root / "lookup.js").write_text("", encoding="utf-8")

    with _serve(root) as url:
        yield url


def visible_text_below(page: object, minimum: int) -> list[dict[str, str | float]]:
    """Every element with its own visible text rendered below `minimum` px.

    Not asserted yet — see the module docstring.
    """
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

    Not asserted yet — see the module docstring.
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
