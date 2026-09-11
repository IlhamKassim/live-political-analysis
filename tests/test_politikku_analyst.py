"""Preserve the approved static design while adapting navigation."""

import hashlib
import re
from pathlib import Path

import pytest

from lpa import politikku_analyst as analyst


def test_copy_preserves_every_asset_and_the_approved_main(tmp_path):
    originals = {
        p.relative_to(analyst._ANALYST_PAGE): p.read_bytes()
        for p in analyst._ANALYST_PAGE.rglob("*")
        if p.is_file() and p.name != analyst._MS_SOURCE
    }
    page = analyst.build_and_write_analyst_page(tmp_path)
    for relative, contents in originals.items():
        assert (analyst._ANALYST_PAGE / relative).read_bytes() == contents
        if relative != Path("index.html"):
            assert (page.parent / relative).read_bytes() == contents
    source = originals[Path("index.html")].decode()
    rendered = page.read_text()
    assert (
        re.search(r"<main.*?</main>", source, re.DOTALL).group()
        == re.search(r"<main.*?</main>", rendered, re.DOTALL).group()
    )
    assert "In pilot" in rendered
    for notice in (
        "NO LIVE DATA",
        "This only moves the illustration.",
        "No Projection is calculated.",
        "SOURCE PATH <span>CONCEPT ONLY</span>",
        "Proposed fields. Export format and scope are still being developed.",
    ):
        assert notice in rendered
    assert 'href="/#perspective"' in rendered
    assert 'href="/#chamber"' in rendered
    assert 'href="/#find"' in rendered
    assert not (page.parent / analyst._MS_SOURCE).exists()
    # Internal design labels stay off the published page.
    for label in ("DIRECTION B", "CONCEPT B"):
        assert label not in rendered
    # Copying and adapting again must not accumulate header scripts or styles.
    analyst.build_and_write_analyst_page(tmp_path)
    assert page.read_text() == rendered


def _toggle(page: str) -> dict[str, str]:
    toggle = re.search(r'<div class="obs-lang".*?</div>', page, re.DOTALL)
    assert toggle, "language toggle missing"
    pairs = re.findall(r'href="([^"]+)"[^>]*data-pk-set-lang="(en|ms)"', toggle.group())
    return {lang: href for href, lang in pairs}


def test_bm_page_mirrors_the_en_page_in_malay(tmp_path):
    en = analyst.build_and_write_analyst_page(tmp_path).read_text()
    ms = (tmp_path / "ms" / "analyst" / "index.html").read_text()
    assert '<html lang="ms"' in ms
    # Both pages switch between the two Analyst pages, not the two homepages.
    assert _toggle(en) == _toggle(ms) == {"en": "/analyst/", "ms": "/ms/analyst/"}
    assert 'href="/ms/#perspective"' in ms
    assert 'href="https://politikku.my/ms/methodology.html"' in ms
    assert "Penganalisis" in ms
    # Same structure: every section, chapter and control the EN page has.
    for pattern in (r"<section\b[^>]*>", r'class="chapter chapter-\d"', r'id="[^"]+"'):
        assert re.findall(pattern, en) == re.findall(pattern, ms), pattern
    # The same honesty notices, in Malay.
    for notice in (
        "TIADA DATA LANGSUNG",
        "Ia hanya menggerakkan ilustrasi.",
        "Tiada Unjuran dikira.",
        "Model ini sementara dan belum ditentukur.",
        "bukan pengganti tinjauan pendapat pengundi",
    ):
        assert notice in ms
    for label in ("DIRECTION B", "CONCEPT B"):
        assert label not in ms


def _resource_links(html: str) -> list[str]:
    """Every file a `<script>` or `<link>` loads, including the motion scripts
    `app.js` loads itself from its `data-gsap`/`data-scroll-trigger` attributes."""
    return [
        url
        for tag in re.findall(r"<(?:script|link)\b[^>]*>", html)
        for url in re.findall(r'\b(?:src|href|data-gsap|data-scroll-trigger)="([^"]+)"', tag)
    ]


def test_resources_are_self_hosted_and_exist(tmp_path):
    page = analyst.build_and_write_analyst_page(tmp_path)
    for index, prefix in (
        (page, ""),
        (tmp_path / "ms" / "analyst" / "index.html", "../../analyst/"),
    ):
        html = index.read_text()
        resources = [r.split("?", 1)[0] for r in _resource_links(html)]
        assert f"{prefix}assets/gsap.min.js" in resources
        assert f"{prefix}assets/ScrollTrigger.min.js" in resources
        for resource in resources:
            assert not resource.startswith(("http:", "https:", "//"))
            assert (index.parent / resource).is_file(), (index, resource)
    for css in page.parent.rglob("*.css"):
        for resource in re.findall(r"url\(([^)]+)\)", css.read_text()):
            assert (css.parent / resource.strip("\"'")).is_file()


def test_every_stylesheet_and_script_link_carries_its_files_fingerprint(tmp_path):
    """A browser may reuse a cached file for ten minutes after a deploy. Each
    link names its file's content hash, so new HTML can't pick up old CSS."""
    page = analyst.build_and_write_analyst_page(tmp_path)
    for index in (page, tmp_path / "ms" / "analyst" / "index.html"):
        html = index.read_text()
        links = _resource_links(html)
        checked = 0
        for link in links:
            path, _, query = link.partition("?")
            if path.endswith(".woff2"):
                # left bare so the preload matches the stylesheet's url()
                assert not query, link
                continue
            digest = hashlib.sha256((index.parent / path).read_bytes()).hexdigest()[:10]
            assert query == f"v={digest}", (index, link)
            checked += 1
        # style.css, site-nav.css, mark.svg, app.js, gsap, ScrollTrigger, site-nav.js
        assert checked == 7, (index, links)


def test_arrows_are_drawn_icons_not_text(tmp_path):
    """Phones swap the ↗ character for a coloured emoji, so every arrow is
    the same drawn icon the site header uses."""
    page = analyst.build_and_write_analyst_page(tmp_path)
    for index in (page, tmp_path / "ms" / "analyst" / "index.html"):
        html = index.read_text()
        assert "↗" not in html, index
        assert html.count('class="ico-arrow"') >= 8, index


def test_missing_source_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(analyst, "_ANALYST_PAGE", tmp_path / "missing")
    with pytest.raises(ValueError, match="Missing Analyst page"):
        analyst.build_and_write_analyst_page(tmp_path / "output")
