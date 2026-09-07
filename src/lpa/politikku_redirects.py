"""Stub redirect pages for retired legacy file routes.

GitHub Pages is static-only — there is no server-side redirect layer — so
the standard static-hosting fallback is a stub HTML file at the old path
with a `<meta http-equiv="refresh">` to the new one. This module writes
those stubs at the exact paths `politikku_homepage.py` used to render and the
active Bills and MP-profile renderers replaced with directory routes, so
existing bookmarks, backlinks, and Google's already-indexed results land on
real root-relative paths (`/app/`, `/bills/`, `/mp/<code>/`) instead of 404ing.

`politikku_landing.py`'s own output path (`public/index.html`, the site
root) needs no stub here — but the reason changed with ADR 0017. Under ADR
0014 it was that the frontend fold-in overwrote the root with the app's
content, so the root just *was* the new content. `politikku_landing.py` is
no longer retired: it renders that path again, as the orientation gate, and
forwards on to `/app/` client-side. Either way there is nothing at the old
path to redirect *from*, so this module stays correct and unchanged.

Driven off `load_mp_profiles()` for the MP Profile stubs — the same source
of truth `politikku_mp_profile.py` used to render from — so this stays
correct as profiles are added without a code change here.
"""

from __future__ import annotations

import html
from pathlib import Path

from lpa.config import load_mp_profiles
from lpa.politikku_shell import APP_URL, BILLS_PAGE, HOMEPAGE_PAGE, MP_PROFILE_DIR, SITE_URL

# Static (non-Seat-specific) old path -> new root-relative real paths.
# HOMEPAGE_PAGE was the secondary "Dashboard" nav page (ADR 0011); the map
# view is its closest equivalent, so it redirects there. That was "/" until
# ADR 0017 moved the map to /app/ and gave "/" to the landing page — the
# reasoning is unchanged, the address is not.
STATIC_REDIRECTS = {
    HOMEPAGE_PAGE: APP_URL,
    # Trailing slash matters: GitHub Pages resolves the extensionless
    # request "/bills" to this stub file (`bills.html`) in preference over
    # the real `bills/index.html` directory it now shadows. A target of
    # "/bills" would make the stub redirect to itself instead of the real
    # page; "/bills/" is a distinct path GH Pages actually serves content
    # for (matching how mp_profile_redirects() already targets "/mp/<code>/").
    BILLS_PAGE: "/bills/",
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
    """`{"mp/<code>.html": f"/mp/{code}/", ...}` for every
    Seat `data/mp_profiles.json` has a profile for.
    """
    return {f"{MP_PROFILE_DIR}/{code}.html": f"/mp/{code}/" for code in load_mp_profiles()}


# `ms_landing_redirect()` was removed by ADR 0017. It wrote a stub at
# `public/ms/index.html` pointing back at `/`, which was correct under ADR
# 0014: the root was the SPA, a single client-side bilingual page with no
# `/ms/` twin, so `/ms/` had nothing real to serve.
#
# `politikku_landing.py` now renders a real Bahasa Malaysia page at exactly
# that path, and this module's step runs *after* it in `daily.yml` — so the
# stub silently clobbered the BM landing page on every deploy. It survived
# the smoke-check because a stub is a file, and `[ -f ... ]` cannot tell a
# page from a redirect; the check now asserts `lang="ms"` in the file's
# content for that reason.
#
# Do not reinstate this without first confirming nothing renders `/ms/`.


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
