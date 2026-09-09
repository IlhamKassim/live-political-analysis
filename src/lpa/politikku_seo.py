"""Canonical SEO and structured metadata definitions for PolitikKu content pages.

Ensures 100% parity with the former Python page renderers for titles, meta
descriptions, Open Graph tags, Twitter cards, canonical links, hreflang alternates,
and schema.org JSON-LD structured data (Dataset, Person, WebSite).
"""

from __future__ import annotations

import functools
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lpa.config import load_mp_profiles
from lpa.politikku_shell import Language

SITE_URL = "https://politikku.my/"
OG_IMAGE = f"{SITE_URL}og-image.png"

WEBSITE_LD: dict[str, Any] = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": "PolitikKu",
    "url": SITE_URL,
    "description": "A public reference for Malaysian politics",
    "inLanguage": ["en", "ms"],
}


@dataclass(frozen=True)
class RouteMetadata:
    """Complete metadata set for a single prerendered route."""

    route_path: str  # e.g. "dewan/", "ms/dewan/", "mp/P.102/"
    language: Language
    title: str
    description: str
    canonical_url: str
    alternate_en_url: str
    alternate_ms_url: str
    json_ld: tuple[dict[str, Any], ...]

    def head_html(self) -> str:
        """Render standard head tags and JSON-LD scripts to inject into snapshot."""
        esc_title = html.escape(self.title)
        esc_desc = html.escape(self.description)
        esc_canonical = html.escape(self.canonical_url)
        esc_en = html.escape(self.alternate_en_url)
        esc_ms = html.escape(self.alternate_ms_url)
        esc_og_image = html.escape(OG_IMAGE)

        scripts = [
            f'<script type="application/ld+json">\n{json.dumps(ld, indent=2)}\n</script>'
            for ld in self.json_ld
        ]
        ld_markup = "\n".join(scripts)

        return (
            f"<title>{esc_title}</title>\n"
            f'<meta name="description" content="{esc_desc}">\n'
            f'<meta property="og:title" content="{esc_title}">\n'
            f'<meta property="og:description" content="{esc_desc}">\n'
            f'<meta property="og:url" content="{esc_canonical}">\n'
            f'<meta property="og:type" content="website">\n'
            f'<meta property="og:image" content="{esc_og_image}">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n'
            f'<meta name="twitter:title" content="{esc_title}">\n'
            f'<meta name="twitter:description" content="{esc_desc}">\n'
            f'<meta name="twitter:image" content="{esc_og_image}">\n'
            f'<link rel="canonical" href="{esc_canonical}">\n'
            f'<link rel="alternate" hreflang="en" href="{esc_en}">\n'
            f'<link rel="alternate" hreflang="ms" href="{esc_ms}">\n'
            f"{ld_markup}"
        )


def _urls_for(base_path: str) -> tuple[str, str]:
    """Return (canonical_en, canonical_ms)."""
    clean = base_path.strip("/")
    if clean.endswith(".html"):
        en_url = f"{SITE_URL}{clean}"
        ms_url = f"{SITE_URL}ms/{clean}"
    elif clean:
        en_url = f"{SITE_URL}{clean}/"
        ms_url = f"{SITE_URL}ms/{clean}/"
    else:
        en_url = f"{SITE_URL}"
        ms_url = f"{SITE_URL}ms/"
    return en_url, ms_url


def get_metadata_for_section(section: str, language: Language) -> RouteMetadata:
    """Return metadata for a top-level section: dewan, bills, politicians, sentiment, projection, methodology."""
    is_ms = language is Language.MS
    if section == "dewan":
        en_url, ms_url = _urls_for("dewan")
        title = (
            "Aktiviti Dewan Rakyat — Giliran Ucapan Hansard Rasmi | PolitikKu"
            if is_ms
            else "Dewan Rakyat Activity — Official Hansard Speech Turns | PolitikKu"
        )
        description = (
            "Siapa bersuara di Parlimen — setiap giliran ucapan yang direkodkan dalam Hansard rasmi."
            if is_ms
            else "Who speaks in Parliament — every recorded speech turn in the official Hansard."
        )
        return RouteMetadata(
            route_path="ms/dewan/" if is_ms else "dewan/",
            language=language,
            title=title,
            description=description,
            canonical_url=ms_url if is_ms else en_url,
            alternate_en_url=en_url,
            alternate_ms_url=ms_url,
            json_ld=(WEBSITE_LD,),
        )

    if section == "bills":
        en_url, ms_url = _urls_for("bills")
        title = (
            "Penjejak Rang Undang-Undang Parlimen | PolitikKu"
            if is_ms
            else "Parliament Bills Tracker | PolitikKu"
        )
        description = (
            "Jejak rang undang-undang di Dewan Rakyat dengan huraian asal daripada dokumen rasmi Parlimen dan rekod undian belah bahagian."
            if is_ms
            else "Track active and passed Bills before the Dewan Rakyat with verbatim summaries from Parliament's official PDFs and recorded Division votes."
        )
        return RouteMetadata(
            route_path="ms/bills/" if is_ms else "bills/",
            language=language,
            title=title,
            description=description,
            canonical_url=ms_url if is_ms else en_url,
            alternate_en_url=en_url,
            alternate_ms_url=ms_url,
            json_ld=(WEBSITE_LD,),
        )

    if section == "politicians":
        en_url, ms_url = _urls_for("politicians")
        title = (
            "Direktori Ahli Politik — Wakil Rakyat Parlimen & DUN | PolitikKu"
            if is_ms
            else "Politicians Directory — Parliament & State Assembly Representatives | PolitikKu"
        )
        description = (
            "Direktori 222 Ahli Parlimen Malaysia dan wakil Dewan Undangan Negeri (DUN). Tapis mengikut parti, gabungan, negeri, atau cari mengikut nama dan kawasan."
            if is_ms
            else "Directory of Malaysia's 222 Members of Parliament and state assembly (DUN) representatives. Filter by party, coalition, state, or search by name and Seat."
        )
        return RouteMetadata(
            route_path="ms/politicians/" if is_ms else "politicians/",
            language=language,
            title=title,
            description=description,
            canonical_url=ms_url if is_ms else en_url,
            alternate_en_url=en_url,
            alternate_ms_url=ms_url,
            json_ld=(WEBSITE_LD,),
        )

    if section == "sentiment":
        en_url, ms_url = _urls_for("sentiment")
        title = (
            "Analisis Sentimen Berita — PolitikKu"
            if is_ms
            else "News Sentiment Analysis — PolitikKu"
        )
        description = (
            "Penjejak sentimen berita harian untuk gabungan politik Malaysia: nada liputan, tren sejarah, dan pecahan media."
            if is_ms
            else "Daily news sentiment tracker for Malaysian political coalitions: coverage tone, historical trends, and media breakdown."
        )
        return RouteMetadata(
            route_path="ms/sentiment/" if is_ms else "sentiment/",
            language=language,
            title=title,
            description=description,
            canonical_url=ms_url if is_ms else en_url,
            alternate_en_url=en_url,
            alternate_ms_url=ms_url,
            json_ld=(WEBSITE_LD,),
        )

    if section == "projection":
        en_url, ms_url = _urls_for("projection")
        title = (
            "Unjuran Kerusi demi Kerusi — 222 Kerusi Parlimen | PolitikKu"
            if is_ms
            else "Seat-by-Seat Projection — 222 Parliamentary Seats | PolitikKu"
        )
        description = (
            "Unjuran PRU16 kerusi demi kerusi secara penuh: 222 Kerusi, ledger, tren jidar majoriti, dan ringkasan mengikut negeri — dijana oleh model dan belum ditentukur terhadap data tinjauan."
            if is_ms
            else "Full Seat-by-Seat GE16 projection: 222 Seats, ledger, Majority-margin trend, and per-state rollup — model-driven and not calibrated against survey data."
        )
        dataset_ld = {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": "GE16 Seat-by-Seat Projection",
            "description": "Daily seat-level projection for all 222 Malaysian Parliamentary seats based on sentiment swing and baseline election results.",
            "license": "https://creativecommons.org/licenses/by/4.0/",
            "distribution": [
                {
                    "@type": "DataDownload",
                    "encodingFormat": "application/json",
                    "contentUrl": f"{SITE_URL}projection.json",
                },
                {
                    "@type": "DataDownload",
                    "encodingFormat": "text/csv",
                    "contentUrl": f"{SITE_URL}projection.csv",
                },
            ],
        }
        return RouteMetadata(
            route_path="ms/projection/" if is_ms else "projection/",
            language=language,
            title=title,
            description=description,
            canonical_url=ms_url if is_ms else en_url,
            alternate_en_url=en_url,
            alternate_ms_url=ms_url,
            json_ld=(WEBSITE_LD, dataset_ld),
        )

    if section == "methodology":
        en_url, ms_url = _urls_for("methodology.html")
        title = (
            "Metodologi — Cara Unjuran Kerusi PRU16 Berfungsi | PolitikKu"
            if is_ms
            else "Methodology — How the GE16 Seat Projection Works | PolitikKu"
        )
        description = (
            "Ketahui cara model unjuran kerusi Parlimen PRU16 PolitikKu berfungsi: andaian ayunan, penentukuran tinjauan, dan had model."
            if is_ms
            else "How the PolitikKu GE16 parliamentary seat projection model works: swing assumptions, poll calibration, and model limits."
        )
        return RouteMetadata(
            route_path="ms/methodology.html" if is_ms else "methodology.html",
            language=language,
            title=title,
            description=description,
            canonical_url=ms_url if is_ms else en_url,
            alternate_en_url=en_url,
            alternate_ms_url=ms_url,
            json_ld=(WEBSITE_LD,),
        )

    raise ValueError(f"Unknown section: {section}")


@functools.lru_cache(maxsize=1)
def _load_parlimen_seats() -> dict[str, dict[str, Any]]:
    p = Path("frontend/public/data/seats-parlimen.json")
    if not p.exists():
        p = Path("public/app/data/seats-parlimen.json")
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {s["code"]: s for s in data.get("seats", [])}


def get_metadata_for_mp(code: str, language: Language) -> RouteMetadata:
    """Return metadata for an individual MP profile route /mp/<code>/."""
    is_ms = language is Language.MS
    profiles = load_mp_profiles()
    profile = profiles.get(code)
    seats = _load_parlimen_seats()
    seat = seats.get(code, {})

    mp_name = profile.name if profile else code
    seat_name = seat.get("name", code)
    seat_state = seat.get("state", "")
    coalition = profile.coalition if profile else ""

    en_url, ms_url = _urls_for(f"mp/{code}")
    title = f"{mp_name} — {seat_name} | PolitikKu"

    if is_ms:
        description = (
            f"{mp_name}, {coalition} — Ahli Parlimen bagi {seat_name}, {seat_state}. "
            f"Rekod undi, kehadiran, dan butiran hubungan."
        )
    else:
        description = (
            f"{mp_name}, {coalition} — the Member of Parliament for {seat_name}, {seat_state}. "
            f"Voting record, attendance, and contact details."
        )

    person_ld = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": mp_name,
        "jobTitle": "Member of Parliament",
        "worksFor": {"@type": "Organization", "name": "Dewan Rakyat"},
        "description": f"MP for {seat_name} ({code})",
    }

    return RouteMetadata(
        route_path=f"ms/mp/{code}/" if is_ms else f"mp/{code}/",
        language=language,
        title=title,
        description=description,
        canonical_url=ms_url if is_ms else en_url,
        alternate_en_url=en_url,
        alternate_ms_url=ms_url,
        json_ld=(WEBSITE_LD, person_ld),
    )
