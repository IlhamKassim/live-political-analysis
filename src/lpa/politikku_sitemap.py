"""Generates sitemap.xml for all HTML pages in public/."""

from __future__ import annotations

import datetime
from pathlib import Path
from xml.sax.saxutils import escape

SITE_URL = "https://politikku.my/"


def build_sitemap(public_dir: Path) -> str:
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")

    # Collect all HTML files, except noindex redirect stubs (politikku_redirects.py) —
    # Google's own guidance is to leave a redirecting URL out of the sitemap entirely,
    # not list it alongside the canonical page it points to.
    html_files = []
    for path in public_dir.rglob("*.html"):
        if "noindex" in path.read_text(encoding="utf-8"):
            continue
        rel_path = path.relative_to(public_dir).as_posix()
        html_files.append(rel_path)

    # Map EN to MS and MS to EN
    en_to_ms = {}
    ms_to_en = {}

    for file_path in html_files:
        if file_path.startswith("ms/"):
            en_path = file_path[3:]
            if en_path in html_files:
                en_to_ms[en_path] = file_path
                ms_to_en[file_path] = en_path
        elif f"ms/{file_path}" in html_files:
            en_to_ms[file_path] = f"ms/{file_path}"
            ms_to_en[f"ms/{file_path}"] = file_path

    def canonicalize(p: str) -> str:
        p = p.removesuffix("index.html")
        return f"{SITE_URL}{p}"

    urls = []
    for file_path in sorted(html_files):
        loc = canonicalize(file_path)

        alt_en = None
        alt_ms = None

        if file_path in en_to_ms:
            alt_en = canonicalize(file_path)
            alt_ms = canonicalize(en_to_ms[file_path])
        elif file_path in ms_to_en:
            alt_ms = canonicalize(file_path)
            alt_en = canonicalize(ms_to_en[file_path])

        # Build the url node
        xml = [f"  <url>\n    <loc>{escape(loc)}</loc>\n    <lastmod>{today}</lastmod>"]
        if alt_en and alt_ms:
            xml.append(f'    <xhtml:link rel="alternate" hreflang="en" href="{escape(alt_en)}"/>')
            xml.append(f'    <xhtml:link rel="alternate" hreflang="ms" href="{escape(alt_ms)}"/>')
        xml.append("  </url>")
        urls.append("\n".join(xml))

    sitemap = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
        *urls,
        "</urlset>",
    ]
    return "\n".join(sitemap) + "\n"


def main() -> None:
    public_dir = Path("public")
    if not public_dir.exists():
        print("public directory does not exist, skipping sitemap")
        return

    sitemap_xml = build_sitemap(public_dir)
    (public_dir / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")
    print(f"Wrote sitemap.xml to {public_dir}")


if __name__ == "__main__":
    main()
