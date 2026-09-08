"""Coalition and party color definitions and loading utilities.

Single source of truth is parsed from frontend/public/lib.js.
Extracted from politikku_politicians.py to decouple shared pipeline utilities
(such as politikku_landing.py) from page-rendering logic.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

_LIB_JS_PATH = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "lib.js"


@functools.lru_cache(maxsize=4)
def load_coalition_colors(lib_path: Path | str | None = None) -> dict[str, str]:
    """Parse COALITION_COLORS from frontend/public/lib.js (single source of truth)."""
    if lib_path is not None:
        p = Path(lib_path)
    else:
        p = _LIB_JS_PATH
        if not p.exists():
            p = Path("frontend/public/lib.js")

    if not p.exists():
        raise FileNotFoundError(f"Cannot find frontend/public/lib.js at {p}")

    text = p.read_text(encoding="utf-8")
    m = re.search(r"export\s+const\s+COALITION_COLORS\s*=\s*\{([^}]+)\}", text, re.MULTILINE)
    if not m:
        raise ValueError(f"Could not find COALITION_COLORS block in {p}")

    block = m.group(1)
    colors = dict(re.findall(r"(\w+)\s*:\s*[\"'](#[0-9a-fA-F]+)[\"']", block))
    return {k.upper(): v for k, v in colors.items()}


COALITION_COLORS: dict[str, str] = load_coalition_colors()

COALITION_ORDER: tuple[str, ...] = (
    "PH",
    "PN",
    "BN",
    "GPS",
    "GRS",
    "WARISAN",
    "KDM",
    "PBM",
    "STAR",
    "UPKO",
    "PSB",
    "BEBAS",
)


def party_color(p: str | None) -> str:
    """Map coalition or party name to swatch color, mirroring lib.js partyColor()."""
    colors = load_coalition_colors()
    return colors.get((p or "").strip().upper(), "#5d6b7d")


def hex_to_rgb(hex_code: str) -> tuple[int, int, int] | None:
    if not isinstance(hex_code, str):
        return None
    s = hex_code.strip().removeprefix("#")
    if len(s) == 3:
        s = "".join(c + c for c in s)
    if len(s) != 6:
        return None
    try:
        n = int(s, 16)
        return ((n >> 16) & 255, (n >> 8) & 255, n & 255)
    except ValueError:
        return None


def rel_lum(rgb: tuple[int, int, int]) -> float:
    channels = []
    for v in rgb:
        c = v / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
