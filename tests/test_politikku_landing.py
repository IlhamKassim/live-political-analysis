"""Tests for the Observatory landing page integration."""

import hashlib
import re
from datetime import date

from lpa.bill_tracker import Bill
from lpa.domain import ElectionStatus
from lpa.politikku_landing import (
    APP_URL,
    CoalitionRow,
    LandingModel,
    build_and_write_landing_pages,
    deep_link_script,
    render_landing_body,
    render_landing_page,
)
from lpa.politikku_shell import Language

STATUS = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="test")
ROWS = (
    CoalitionRow("PH", 75, "#d7263d", True),
    CoalitionRow("BN", 41, "#1f9bd6", True),
    CoalitionRow("GPS", 23, "#b8332e", True),
    CoalitionRow("GRS", 7, "#e8772e", True),
    CoalitionRow("PN", 69, "#15387c", False),
)
BILLS = (
    Bill(
        code="D.R.22/2026",
        title="RUU Kumpulan Wang Amanah Negara 2026",
        year=2026,
        stage="Lulus",
        stage_date=date(2026, 7, 16),
        summary="Summary",
        summary_source_url="https://example.com/bill.pdf",
    ),
)


def model() -> LandingModel:
    return LandingModel(
        government_majority=True,
        coalitions=ROWS,
        bills=BILLS,
        majority_threshold=112,
        total_seats=222,
        updated_at=date(2026, 9, 9),
        sources_count=7,
        status=STATUS,
    )


def test_observatory_body_uses_the_reference_scenes():
    body = render_landing_body(model())
    assert "A nation." in body
    assert "In perspective." in body
    assert "Many places." in body
    assert "One Parliament." in body
    assert "Follow the source." in body
    assert "The bigger picture" in body
    assert body.count('class="seat-dot"') == 222


def test_observatory_body_keeps_the_platform_lookup_contract():
    body = render_landing_body(model())
    for attr in (
        "data-pk-lookup-scope",
        "data-pk-lookup-form",
        "data-pk-lookup-input",
        "data-pk-locate",
        "data-pk-lookup-results",
    ):
        assert attr in body
    assert 'data-pk-lookup-results role="status" aria-live="polite" hidden' in body
    assert 'for="pk-lookup-q"' in body
    assert 'id="pk-lookup-q"' in body


def test_observatory_page_is_a_standalone_landing_document():
    page = render_landing_page(model())
    assert page.count("<main") == 1
    assert page.count("<header") == 1
    assert page.count("<footer") == 1
    assert 'id="sidebar"' not in page
    assert 'id="topbar"' not in page
    assert 'href="/assets/observatory/style.css?v=' in page
    assert 'src="/lookup.js"' in page


def test_observatory_css_and_js_links_carry_their_files_fingerprint(tmp_path):
    """A browser may reuse a cached file for ten minutes after a deploy; each
    link names the published file's content hash, so new HTML can't pick up
    old CSS. Checked against the files the build actually writes."""
    build_and_write_landing_pages(tmp_path)
    for index in (tmp_path / "index.html", tmp_path / "ms" / "index.html"):
        links = re.findall(r'(?:href|src)="(/assets/observatory/[^"]+)"', index.read_text())
        tagged = [link for link in links if not link.endswith((".woff2", ".png"))]
        assert len(tagged) == 5, tagged
        for link in tagged:
            path, _, query = link.partition("?")
            published = tmp_path / path.lstrip("/")
            digest = hashlib.sha256(published.read_bytes()).hexdigest()[:10]
            assert query == f"v={digest}", link


def test_observatory_links_into_the_current_platform():
    page = render_landing_page(model())
    assert f'href="{APP_URL}"' in page
    assert 'href="/bills/"' in page
    assert 'href="/methodology.html"' in page
    assert "Explore Suara" not in page


def test_observatory_has_bilingual_root_documents():
    en = render_landing_page(model(), Language.EN)
    ms = render_landing_page(model(), Language.MS)
    assert '<html lang="en">' in en
    assert '<html lang="ms">' in ms
    assert 'href="/" aria-current="page" data-pk-set-lang="en"' in en
    assert 'href="/ms/" aria-current="page" data-pk-set-lang="ms"' in ms
    assert "Sebuah negara." in ms
    assert "Dalam perspektif." in ms
    assert "Cari kerusi anda" in ms


def test_local_observatory_hashes_are_not_forwarded_to_the_map():
    script = deep_link_script()
    assert "location.hash" in script
    assert "#(?:top|perspective|chamber|evidence|find)" in script
    assert "location.replace('/app/' + location.hash)" in script


def test_build_copies_the_observatory_runtime_and_image(tmp_path):
    build_and_write_landing_pages(tmp_path)
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "ms" / "index.html").is_file()
    for name in (
        "base.css",
        "style.css",
        "scrollcraft.css",
        "scrollcraft.js",
        "integrated.js",
        "skyline.png",
        "icon.svg",
    ):
        assert (tmp_path / "assets" / "observatory" / name).is_file(), name
