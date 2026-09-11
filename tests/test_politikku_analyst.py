"""Preserve the approved static design while adapting navigation."""

import re
from pathlib import Path

import pytest

from lpa import politikku_analyst as analyst


def test_copy_preserves_every_asset_and_the_approved_main(tmp_path):
    originals = {
        p.relative_to(analyst._ANALYST_PAGE): p.read_bytes()
        for p in analyst._ANALYST_PAGE.rglob("*")
        if p.is_file()
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
    assert "data-pk-set-lang" not in rendered
    assert 'href="/#perspective"' in rendered
    assert 'href="/#chamber"' in rendered
    assert 'href="/#find"' in rendered
    assert not (tmp_path / "ms" / "analyst").exists()
    # Copying and adapting again must not accumulate header scripts or styles.
    analyst.build_and_write_analyst_page(tmp_path)
    assert page.read_text() == rendered


def test_resources_are_self_hosted_and_exist(tmp_path):
    page = analyst.build_and_write_analyst_page(tmp_path)
    html = page.read_text()
    resources = re.findall(r'<(?:script|link)\b[^>]*(?:src|href)="([^"]+)"', html)
    assert "assets/gsap.min.js" in resources
    assert "assets/ScrollTrigger.min.js" in resources
    for resource in resources:
        assert not resource.startswith(("http:", "https:", "//"))
        assert (page.parent / resource).is_file()
    for css in page.parent.rglob("*.css"):
        for resource in re.findall(r"url\(([^)]+)\)", css.read_text()):
            assert (css.parent / resource.strip("\"'")).is_file()


def test_missing_source_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(analyst, "_ANALYST_PAGE", tmp_path / "missing")
    with pytest.raises(ValueError, match="Missing Analyst page"):
        analyst.build_and_write_analyst_page(tmp_path / "output")
