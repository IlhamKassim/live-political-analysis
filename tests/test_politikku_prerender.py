"""Tests for the build-time prerenderer (src/lpa/politikku_prerender.py)."""

import pytest

from lpa.politikku_prerender import (
    inject_metadata,
    verify_content_assertions,
)
from lpa.politikku_seo import get_metadata_for_mp, get_metadata_for_section
from lpa.politikku_shell import Language


def test_inject_metadata_replaces_head_and_sets_lang():
    raw_html = (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8" />\n'
        "<title>Generic Title</title>\n"
        '<meta name="description" content="Generic description" />\n'
        '<link rel="stylesheet" href="/app/styles.css" />\n'
        '</head>\n<body><div id="app">Content</div></body>\n</html>'
    )
    meta = get_metadata_for_section("dewan", Language.MS)
    injected = inject_metadata(raw_html, meta)

    assert '<html lang="ms">' in injected
    assert f"<title>{meta.title}</title>" in injected
    assert f'<meta name="description" content="{meta.description}">' in injected
    assert f'<link rel="canonical" href="{meta.canonical_url}">' in injected
    assert f'<link rel="alternate" hreflang="en" href="{meta.alternate_en_url}">' in injected
    assert f'<link rel="alternate" hreflang="ms" href="{meta.alternate_ms_url}">' in injected
    assert '<script type="application/ld+json">' in injected
    assert "Generic Title" not in injected
    assert "Generic description" not in injected
    assert '<link rel="stylesheet" href="/app/styles.css" />' in injected


import html


def test_inject_metadata_for_mp_profile():
    raw_html = (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8" />\n'
        "<title>Generic Title</title>\n"
        '</head>\n<body><dialog id="cand-modal">Modal</dialog></body>\n</html>'
    )
    meta = get_metadata_for_mp("P.107", Language.EN)
    injected = inject_metadata(raw_html, meta)

    assert '<html lang="en">' in injected
    assert html.escape(meta.title) in injected
    assert meta.canonical_url in injected
    assert '"@type": "Person"' in injected


def test_verify_content_assertions_rejects_empty():
    with pytest.raises(ValueError, match="suspiciously small"):
        verify_content_assertions("<html><body>tiny</body></html>", "dewan")


def test_verify_content_assertions_validates_markers():
    long_html = "x" * 6000 + '<div class="dewan-view">table</div>'
    verify_content_assertions(long_html, "dewan")

    long_html_missing = "x" * 6000
    with pytest.raises(ValueError, match="Missing Dewan elements"):
        verify_content_assertions(long_html_missing, "dewan")


def test_start_prerender_server_serves_files(tmp_path):
    import urllib.request

    from lpa.politikku_prerender import start_prerender_server

    (tmp_path / "test.txt").write_text("hello world", encoding="utf-8")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "styles.css").write_text("body { color: red; }", encoding="utf-8")

    server, port = start_prerender_server(tmp_path)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/test.txt") as resp:
            assert resp.read().decode() == "hello world"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/app/styles.css") as resp:
            assert "color: red" in resp.read().decode()
    finally:
        server.shutdown()
