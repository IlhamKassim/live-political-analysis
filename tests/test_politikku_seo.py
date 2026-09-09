"""Tests for PolitikKu SEO metadata generation."""

from __future__ import annotations

from lpa.politikku_seo import (
    SITE_URL,
    get_metadata_for_mp,
    get_metadata_for_section,
)
from lpa.politikku_shell import Language


def test_dewan_seo_metadata() -> None:
    en = get_metadata_for_section("dewan", Language.EN)
    assert "Dewan Rakyat" in en.title
    assert en.canonical_url == f"{SITE_URL}dewan/"
    assert en.alternate_ms_url == f"{SITE_URL}ms/dewan/"
    assert 'rel="alternate" hreflang="en"' in en.head_html()

    ms = get_metadata_for_section("dewan", Language.MS)
    assert "Aktiviti Dewan Rakyat" in ms.title
    assert ms.canonical_url == f"{SITE_URL}ms/dewan/"
    assert ms.alternate_en_url == f"{SITE_URL}dewan/"


def test_projection_dataset_json_ld() -> None:
    en = get_metadata_for_section("projection", Language.EN)
    assert en.canonical_url == f"{SITE_URL}projection/"
    types = [ld.get("@type") for ld in en.json_ld]
    assert "Dataset" in types
    assert "WebSite" in types
    html = en.head_html()
    assert "projection.json" in html
    assert "projection.csv" in html


def test_mp_profile_person_json_ld() -> None:
    en = get_metadata_for_mp("P.102", Language.EN)
    assert en.canonical_url == f"{SITE_URL}mp/P.102/"
    assert en.alternate_ms_url == f"{SITE_URL}ms/mp/P.102/"
    types = [ld.get("@type") for ld in en.json_ld]
    assert "Person" in types
    html = en.head_html()
    assert "Bangi" in html
    assert "Member of Parliament" in html


def test_politicians_seo_metadata_uses_seat() -> None:
    en = get_metadata_for_section("politicians", Language.EN)
    assert "Seat" in en.description
    assert "constituency" not in en.description.lower()
