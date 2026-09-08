"""Headless Chromium build-time prerenderer for PolitikKu public pages.

Unifies the public pages and interactive SPA (ADR 0018): drives the single-page
app at build-time using headless Chromium to snapshot static HTML for all
content views and MP profiles, injecting exact SEO tags, Open Graph metadata,
and schema.org JSON-LD.
"""

from __future__ import annotations

import argparse
import asyncio
import http.server
import os
import re
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lpa.config import load_mp_profiles
from lpa.pipeline import MALAYSIA_TIME
from lpa.politikku_methodology import render_methodology
from lpa.politikku_seo import RouteMetadata, get_metadata_for_mp, get_metadata_for_section
from lpa.politikku_shell import Language

SECTIONS = ("dewan", "bills", "politicians", "sentiment", "projection")


class StaticPrerenderHandler(http.server.SimpleHTTPRequestHandler):
    """Local HTTP handler for prerendering that avoids reverse DNS lookups."""

    def __init__(self, *args: Any, directory: str, **kwargs: Any) -> None:
        self._root_dir = directory
        super().__init__(*args, directory=directory, **kwargs)

    def address_string(self) -> str:
        # Avoid reverse DNS lookup delay on macOS/Linux
        return self.client_address[0]

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0]
        direct = super().translate_path(clean)
        if os.path.exists(direct):
            return direct
        if clean.startswith("/app/"):
            stripped = super().translate_path(clean[4:])
            if os.path.exists(stripped):
                return stripped
        return direct

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Quiet during build


def start_prerender_server(root_dir: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        lambda *args, **kwargs: StaticPrerenderHandler(*args, directory=str(root_dir), **kwargs),
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def inject_metadata(html_doc: str, metadata: RouteMetadata) -> str:
    """Inject canonical SEO, Open Graph, hreflang and JSON-LD tags into snapshot HTML."""
    # Set html lang attribute
    html_doc = re.sub(
        r'<html\s+lang="[^"]*"',
        f'<html lang="{metadata.language.value}"',
        html_doc,
        count=1,
    )

    head_match = re.search(r"<head>(.*?)</head>", html_doc, re.DOTALL)
    if not head_match:
        raise ValueError("No <head> tag found in HTML document")
    head_content = head_match.group(1)

    # Strip existing generic title and meta tags
    head_content = re.sub(r"<title>.*?</title>\s*", "", head_content, flags=re.DOTALL)
    head_content = re.sub(
        r'<meta\s+(?:name|property|data-i18n-content)="[^"]*"\s*(?:name|property|data-i18n-content)="[^"]*"\s*content="[^"]*"\s*/?>\s*',
        "",
        head_content,
    )
    head_content = re.sub(
        r'<meta\s+(?:name|property)="[^"]*"\s*content="[^"]*"\s*/?>\s*',
        "",
        head_content,
    )
    head_content = re.sub(r'<link\s+rel="canonical"[^>]*>\s*', "", head_content)
    head_content = re.sub(r'<link\s+rel="alternate"[^>]*>\s*', "", head_content)
    head_content = re.sub(
        r'<script\s+type="application/ld\+json"[^>]*>.*?</script>\s*',
        "",
        head_content,
        flags=re.DOTALL,
    )

    new_head_content = f"\n{metadata.head_html()}\n{head_content.lstrip()}"
    return html_doc[: head_match.start(1)] + new_head_content + html_doc[head_match.end(1) :]


def verify_content_assertions(html_doc: str, route_key: str) -> None:
    """Ensure prerendered HTML contains required content elements and sufficient body."""
    if len(html_doc) < 5000:
        raise ValueError(f"Snapshot for {route_key} is suspiciously small: {len(html_doc)} bytes")

    if route_key == "dewan":
        if "dewan-view" not in html_doc and "pol-dir" not in html_doc:
            raise ValueError(f"Missing Dewan elements in {route_key} snapshot")
    elif route_key == "bills":
        if "bills-view" not in html_doc and "pol-dir" not in html_doc:
            raise ValueError(f"Missing Bills elements in {route_key} snapshot")
    elif route_key == "politicians":
        if "politicians-view" not in html_doc and "pol-card" not in html_doc:
            raise ValueError(f"Missing Politicians elements in {route_key} snapshot")
    elif route_key == "sentiment":
        if "sentiment-view" not in html_doc and "pol-dir" not in html_doc:
            raise ValueError(f"Missing Sentiment elements in {route_key} snapshot")
    elif route_key == "projection":
        if "projection-view" not in html_doc and "pol-dir" not in html_doc:
            raise ValueError(f"Missing Projection elements in {route_key} snapshot")
    elif (
        route_key.startswith("mp/")
        and "cand-modal-shell" not in html_doc
        and "cand-hero" not in html_doc
    ):
        raise ValueError(f"Missing MP bento elements in {route_key} snapshot")


async def prerender_all_routes(
    output_dir: Path,
    frontend_dir: Path,
    computed_at: date | None = None,
) -> int:
    """Drive Playwright headless Chromium to render all routes and save to output_dir."""
    from playwright.async_api import async_playwright

    if computed_at is None:
        computed_at = datetime.now(MALAYSIA_TIME).date()

    server, port = start_prerender_server(frontend_dir)
    app_url = f"http://127.0.0.1:{port}/index.html"
    rendered_count = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Abort external requests so pipeline stays zero-cost and hermetic
            await page.route(
                lambda url: not url.startswith(f"http://127.0.0.1:{port}"),
                lambda route: route.abort(),
            )

            # Boot the app
            await page.goto(app_url)
            await page.wait_for_function(
                "() => document.documentElement.getAttribute('data-render-complete') !== null",
                timeout=30000,
            )

            # 1. Prerender top-level sections (EN and MS)
            for section in SECTIONS:
                for lang in (Language.EN, Language.MS):
                    is_ms = lang is Language.MS
                    metadata = get_metadata_for_section(section, lang)

                    await page.evaluate(
                        "({path, lang}) => window.__renderRoute(path, lang)",
                        {"path": section, "lang": lang.value},
                    )
                    await page.wait_for_function(
                        f"() => document.documentElement.getAttribute('data-render-complete') === '{section}'",
                        timeout=5000,
                    )

                    raw_html = await page.content()
                    verify_content_assertions(raw_html, section)
                    processed_html = inject_metadata(raw_html, metadata)

                    dest_file = output_dir / ("ms" if is_ms else "") / section / "index.html"
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_text(processed_html, encoding="utf-8")
                    rendered_count += 1

                    # For projection, copy dated permalink
                    if section == "projection":
                        permalink_dest = (
                            output_dir
                            / ("ms" if is_ms else "")
                            / "projection"
                            / f"{computed_at.year}"
                            / f"{computed_at.month:02d}"
                            / f"{computed_at.day:02d}.html"
                        )
                        permalink_dest.parent.mkdir(parents=True, exist_ok=True)
                        permalink_dest.write_text(processed_html, encoding="utf-8")
                        rendered_count += 1

            # 2. Prerender all MP profile pages (EN and MS)
            mp_profiles = load_mp_profiles()
            for code in sorted(mp_profiles.keys()):
                for lang in (Language.EN, Language.MS):
                    is_ms = lang is Language.MS
                    metadata = get_metadata_for_mp(code, lang)

                    await page.evaluate(
                        "({path, lang}) => window.__renderRoute(path, lang)",
                        {"path": f"mp/{code}", "lang": lang.value},
                    )
                    await page.wait_for_function(
                        f"() => document.documentElement.getAttribute('data-render-complete') === 'mp/{code}'",
                        timeout=5000,
                    )

                    raw_html = await page.content()
                    verify_content_assertions(raw_html, f"mp/{code}")
                    processed_html = inject_metadata(raw_html, metadata)

                    dest_file = output_dir / ("ms" if is_ms else "") / "mp" / code / "index.html"
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_text(processed_html, encoding="utf-8")
                    rendered_count += 1

            await browser.close()
    finally:
        server.shutdown()

    # 3. Render methodology pages (EN and MS)
    try:
        from lpa.public_page import load_projection_page_model
        from lpa.storage import connect

        engine = connect()
        model = load_projection_page_model(engine)
        for lang in Language:
            is_ms = lang is Language.MS
            meth_dest = output_dir / ("ms" if is_ms else "") / "methodology.html"
            meth_dest.parent.mkdir(parents=True, exist_ok=True)
            meth_content = render_methodology(model, language=lang)
            meth_dest.write_text(meth_content, encoding="utf-8")
            rendered_count += 1
    except Exception as e:  # noqa: BLE001
        print(f"Warning: Could not render methodology page from storage: {e}")

    return rendered_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("public"),
        help="Where to write the prerendered HTML hierarchy (default: public).",
    )
    parser.add_argument(
        "--frontend-dir",
        type=Path,
        default=Path("frontend/public"),
        help="Path to frontend static root (default: frontend/public).",
    )
    args = parser.parse_args()

    t0 = time.perf_counter()
    print(f"Prerendering PolitikKu routes from {args.frontend_dir} to {args.output_dir}...")
    count = asyncio.run(prerender_all_routes(args.output_dir, args.frontend_dir))
    elapsed = time.perf_counter() - t0
    print(f"Successfully prerendered {count} pages in {elapsed:.2f}s.")


if __name__ == "__main__":
    main()
