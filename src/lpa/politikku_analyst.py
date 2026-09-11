"""Copy the approved Analyst concept and adapt only its site navigation.

Run explicitly when the design or shared navigation changes. The resulting
public/analyst tree is committed for deployment; it needs no daily render.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from lpa.politikku_landing import _OBSERVATORY_ROOT, _observatory_header
from lpa.politikku_shell import Language, route

PAGE_PATH = "analyst/"
_ANALYST_PAGE = _OBSERVATORY_ROOT / "analyst-b"
_MS_SOURCE = "index.ms.html"
"""The hand-translated BM page, kept beside the EN one it mirrors. Built to
`ms/analyst/`, never copied into `analyst/`."""

# Scoped additions for the shared header. The approved concept CSS/JS stay intact.
_HEADER_CSS = """
.site-header .brand-small{font:9px/1.5 Plex,sans-serif;max-width:100px;
 letter-spacing:.14em;border-left:1px solid var(--line);padding-left:20px;margin-left:13px}
.site-header .nav-links{display:flex;align-items:center;gap:28px;font-size:12px}
.site-header .nav-links a{white-space:nowrap}
.site-header .ico-arrow{display:inline-block;width:.85em;height:.85em;flex:none;vertical-align:-.08em}
.site-header .nav-cta{border:1px solid var(--line);border-radius:40px;
 padding:12px 18px;display:flex;gap:20px}
.site-header .menu-toggle{display:none;color:var(--paper);background:transparent;
 border:1px solid var(--line);border-radius:30px;padding:10px 16px;min-height:44px}
.site-header .obs-lang{display:flex;border:1px solid var(--line);border-radius:999px;
 overflow:hidden;margin-left:24px}
.site-header .obs-lang a{display:inline-flex;align-items:center;justify-content:center;
 min-width:40px;min-height:40px;padding:6px 10px;font:10px Plex,sans-serif;
 letter-spacing:.08em;color:#acbcb7}
.site-header .obs-lang a:hover,.site-header .obs-lang a.on{background:var(--lime);color:#172324}
.site-header .obs-lang a:focus-visible{outline:3px solid var(--lime);outline-offset:3px}
@media(max-width:1100px){.site-header .brand-small{display:none}}
@media(max-width:900px){
 .site-header .obs-lang{margin-left:auto;margin-right:10px}
 .site-header .obs-lang a{min-width:34px}
 .site-header .menu-toggle{display:block}
 .site-header .nav-links{display:none}
 .site-header .nav-links.is-open{display:flex;position:absolute;top:81px;left:0;
 right:0;flex-direction:column;align-items:stretch;gap:8px;background:var(--ink);
 padding:20px;border:1px solid var(--line);box-shadow:0 20px 40px #0005}
 .site-header .nav-links a{min-height:44px;padding:12px}
}
""".strip()

_HEADER_JS = """
(() => {
 const button = document.querySelector('.site-header .menu-toggle');
 const nav = document.querySelector('.site-header .nav-links');
 if (!button || !nav) return;
 const close = () => {
   nav.classList.remove('is-open');
   button.setAttribute('aria-expanded', 'false');
 };
 button.addEventListener('click', () => {
   const open = button.getAttribute('aria-expanded') !== 'true';
   nav.classList.toggle('is-open', open);
   button.setAttribute('aria-expanded', String(open));
 });
 nav.addEventListener('click', event => { if (event.target.closest('a')) close(); });
 document.addEventListener('keydown', event => {
   if (event.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') {
     close(); button.focus();
   }
 });
})();
""".strip()


def _analyst_header(language: Language) -> str:
    """Reuse the homepage header: home anchors, and an EN/BM toggle that
    switches between the two Analyst pages rather than the two homepages."""
    header = _observatory_header(language)
    home = route(language, "")

    def to_analyst(match: re.Match[str]) -> str:
        toggle = match.group(0)
        for lang in Language:
            old = f'href="{route(lang, "")}"'
            if toggle.count(old) != 1:
                raise ValueError("Expected one EN and one BM link in the language toggle")
            toggle = toggle.replace(old, f'href="{route(lang, PAGE_PATH)}"')
        return toggle

    header, count = re.subn(
        r'<div class="obs-lang"[^>]*>.*?</div>', to_analyst, header, flags=re.DOTALL
    )
    if count != 1:
        raise ValueError("Expected one language toggle in the Observatory header")
    return header.replace('class="nav wrap"', 'class="site-header wrap"').replace(
        'href="#', f'href="{home}#'
    )


def _copy_analyst_assets(output_dir: Path) -> Path:
    """Copy every source file, preserving its relative path and metadata."""
    if not (_ANALYST_PAGE / "index.html").is_file():
        raise ValueError(f"Missing Analyst page: {_ANALYST_PAGE / 'index.html'}")
    target = output_dir / PAGE_PATH
    for source in sorted(_ANALYST_PAGE.rglob("*")):
        if source.is_file() and source.name != _MS_SOURCE:
            destination = target / source.relative_to(_ANALYST_PAGE)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return target


def _adapt(source: str, language: Language, asset_root: str) -> str:
    """Swap in the shared header and hook up the header's CSS/JS. `asset_root`
    prefixes the page's own relative asset paths — the BM page reuses the EN
    page's copies instead of duplicating them."""
    page, count = re.subn(
        r'<header class="site-header wrap">.*?</header>',
        lambda _: _analyst_header(language),
        source,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("Expected one site header in the approved Analyst page")
    if asset_root:
        page = re.sub(
            r'((?:src|href)=")((?:assets/|style\.css|app\.js)[^"]*")',
            rf"\1{asset_root}\2",
            page,
        )
    return page.replace(
        "</head>",
        f'<link rel="stylesheet" href="{asset_root}site-nav.css">\n'
        f'<script defer src="{asset_root}site-nav.js"></script>\n</head>',
        1,
    )


def build_and_write_analyst_page(output_dir: Path | str = "public") -> Path:
    """Prepare both static pages without reading Storage or rewriting the design.
    Returns the EN page; the BM page is written to `ms/analyst/index.html`."""
    output_dir = Path(output_dir)
    ms_source = _ANALYST_PAGE / _MS_SOURCE
    if not ms_source.is_file():
        raise ValueError(f"Missing Analyst page: {ms_source}")
    target = _copy_analyst_assets(output_dir)
    index = target / "index.html"
    index.write_text(_adapt(index.read_text(encoding="utf-8"), Language.EN, ""), encoding="utf-8")
    ms_index = output_dir / "ms" / PAGE_PATH / "index.html"
    ms_index.parent.mkdir(parents=True, exist_ok=True)
    ms_index.write_text(
        _adapt(ms_source.read_text(encoding="utf-8"), Language.MS, "../../analyst/"),
        encoding="utf-8",
    )
    (target / "site-nav.css").write_text(_HEADER_CSS + "\n", encoding="utf-8")
    (target / "site-nav.js").write_text(_HEADER_JS + "\n", encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the static Analyst page")
    parser.add_argument("--output-dir", default="public")
    args = parser.parse_args()
    print(f"Wrote {build_and_write_analyst_page(args.output_dir)}")


if __name__ == "__main__":
    main()
