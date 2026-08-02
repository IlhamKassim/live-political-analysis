#!/usr/bin/env python3
"""Generate the full-map Open Graph card from the baked Parliament data."""
import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
seats = json.loads((ROOT / "public/data/seats-parlimen.json").read_text()) ["seats"]
results = json.loads((ROOT / "public/data/results-ge15.json").read_text())
colors = {
    "PH": "#d7263d", "PN": "#15387c", "BN": "#1f9bd6", "GPS": "#b8332e",
    "GRS": "#f0b429", "WARISAN": "#7a5cc7", "KDM": "#22a06b", "PBM": "#8b5e34",
}
paths = []
for seat in seats:
    result = results.get(seat["code"], {})
    coalition = str(result.get("coalition") or "").upper()
    fill = colors.get(coalition, "#5d6b7d")
    paths.append(
        f'<path d="{escape(seat["d"], quote=True)}" fill="{fill}" '
        'stroke="#0b0e13" stroke-width="0.7" vector-effect="non-scaling-stroke"/>'
    )

legend = "".join(
    f'<g transform="translate({x} 590)"><rect width="14" height="14" rx="3" fill="{c}"/>'
    f'<text x="22" y="12" fill="#b9c3d0" font-family="Arial, sans-serif" font-size="16">{label}</text></g>'
    for x, (label, c) in zip(range(130, 1080, 155), colors.items())
)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="MyPolitik Parliament map coloured by GE15 coalition">
  <defs><style>@font-face {{ font-family: "Redaction 20"; font-weight: 700; src: url("../fonts/redaction-20-bold-latin.woff2") format("woff2"); }}</style></defs>
  <rect width="1200" height="630" fill="#0b0e13"/>
  <rect width="1200" height="8" fill="#4dd6c1"/>
  <g transform="translate(34 56) scale(1.42)">{''.join(paths)}</g>
  <text x="52" y="44" fill="#e7edf4" font-family="'Redaction 20', Georgia, serif" font-size="30" font-weight="700">MyPolitik</text>
  <text x="1148" y="42" text-anchor="end" fill="#7f8da0" font-family="Arial, sans-serif" font-size="16">Parliament · GE15</text>
  <g>{legend}</g>
</svg>'''
(ROOT / "public/assets/og-card.svg").write_text(svg, encoding="utf-8")
