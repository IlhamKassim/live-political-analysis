"""Stub redirect pages for the four renderers ADR 0014 retired.

GitHub Pages is static-only — there is no server-side redirect layer — so
the standard static-hosting fallback is a stub HTML file at the old path
with a `<meta http-equiv="refresh">` to the new one. This module writes
those stubs at the exact paths `politikku_landing.py`, `politikku_homepage.py`,
`politikku_bills.py`, and `politikku_mp_profile.py` used to render to, so
existing bookmarks, backlinks, and Google's already-indexed results land on
`/app/#...` instead of 404ing.

`politikku_landing.py`'s own output path (`public/index.html`, the site
root) needs no stub here: ADR 0014 has the frontend fold-in step overwrite
that path directly with `/app/`'s own content, so the root just *is* the
new content rather than redirecting to it.

Driven off `load_mp_profiles()` for the MP Profile stubs — the same source
of truth `politikku_mp_profile.py` used to render from — so this stays
correct as profiles are added without a code change here.
"""

from __future__ import annotations

import html
from pathlib import Path

from lpa.config import load_mp_profiles
from lpa.politikku_shell import BILLS_PAGE, HOMEPAGE_PAGE, MP_PROFILE_DIR, SITE_URL

# Static (non-Seat-specific) old path -> new /app/ hash route.
# HOMEPAGE_PAGE was the secondary "Dashboard" nav page (ADR 0011); /app/'s
# own root map view is its closest equivalent, so no hash is needed.
STATIC_REDIRECTS = {
    HOMEPAGE_PAGE: "/app/",
    BILLS_PAGE: "/app/#bills",
}


def _stub_html(target: str) -> str:
    escaped_target = html.escape(target, quote=True)
    absolute = html.escape(f"{SITE_URL.rstrip('/')}{target}", quote=True)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0;url={escaped_target}">\n'
        f'<link rel="canonical" href="{absolute}">\n'
        '<meta name="robots" content="noindex,follow">\n'
        "<title>Moved</title>\n"
        "</head>\n"
        "<body>\n"
        f'This page moved to <a href="{escaped_target}">{escaped_target}</a>.\n'
        "</body>\n"
        "</html>\n"
    )


def _write_stub(public_dir: Path, relative_path: str, target: str) -> None:
    for prefix in ("", "ms/"):
        out = public_dir / prefix / relative_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_stub_html(target), encoding="utf-8")


def mp_profile_redirects() -> dict[str, str]:
    """`{"mp/<code>.html": "/app/#parlimen/parti/<code>", ...}` for every
    Seat `data/mp_profiles.json` has a profile for.

    `#parlimen/parti/<code>` matches `lib.js`'s `encodeHash` field order
    (tier, mode, code) exactly — `parti` is the default mode, included
    explicitly since the code slot only decodes correctly in the third
    position.
    """
    return {
        f"{MP_PROFILE_DIR}/{code}.html": f"/app/#parlimen/parti/{code}"
        for code in load_mp_profiles()
    }


def build_redirects(public_dir: Path) -> int:
    redirects = {**STATIC_REDIRECTS, **mp_profile_redirects()}
    for relative_path, target in redirects.items():
        _write_stub(public_dir, relative_path, target)
    return len(redirects)


def main() -> None:
    count = build_redirects(Path("public"))
    print(f"Wrote {count} redirect stub(s) (EN + BM each) under public/.")


if __name__ == "__main__":
    main()
