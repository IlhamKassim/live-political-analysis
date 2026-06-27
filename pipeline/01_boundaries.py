#!/usr/bin/env python3
"""Bake DOSM electoral boundaries -> projected SVG paths for Peta YB.

Two tiers, ONE projection (frozen, copied verbatim from krackedmaps /
maps.krackeddevs.com) so every seat aligns pixel-perfectly with the state map
and could be overlaid on it.

  • Parliament (parlimen)  222 seats   code = P.xxx
  • State assembly (dun)   600 seats   code = {state}_{N.xx}  (N.xx repeats per state)

Source: github.com/dosm-malaysia/data-open (official, WGS84 lng/lat).

    python3 pipeline/01_boundaries.py

Outputs public/data/seats-parlimen.json + seats-dun.json (consumed by app.js,
zero runtime deps).
"""
import json
import math
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "..", "public", "data")
os.makedirs(RAW, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

BASE = "https://raw.githubusercontent.com/dosm-malaysia/data-open/main/datasets/geodata"
SOURCES = {
    "parlimen": f"{BASE}/electoral_0_parlimen.geojson",
    "dun": f"{BASE}/electoral_1_dun.geojson",
}

# --- Frozen projection (verbatim from krackedmaps data/states.js PROJECTION) --
# Reusing the FROZEN constants (not recomputing) guarantees the seat map shares
# the exact viewBox + Mercator + Borneo-shift of maps.krackeddevs.com.
P = {
    "minx": 1.747419824825661, "maxy": 0.12329370352362226,
    "scale": 2848.660976322988, "pad": 24.0, "eastLng": 107.0,
    "shift": 240.0879, "offX": 31.9088, "offY": 5.9369,
    "viewW": 799.85, "viewH": 352.74,
}
D = math.pi / 180.0
VIEWBOX = f"0 0 {P['viewW']} {P['viewH']}"


def project(lng, lat):
    mx = lng * D
    my = math.log(math.tan(math.pi / 4 + (lat * D) / 2))
    x = (mx - P["minx"]) * P["scale"] + P["pad"]
    y = (P["maxy"] - my) * P["scale"] + P["pad"]
    if lng >= P["eastLng"]:
        x -= P["shift"]
    return (x + P["offX"], y + P["offY"])


# --- geometry helpers -------------------------------------------------------
def iter_points(coords):
    if coords and isinstance(coords[0], (int, float)):
        yield coords
    else:
        for c in coords:
            yield from iter_points(c)


def rdp(points, eps):
    """Ramer-Douglas-Peucker on projected (x,y) points; eps in px."""
    if len(points) < 3:
        return points
    ax, ay = points[0]
    bx, by = points[-1]
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    idx, dmax = 0, -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if seg2 == 0:
            d2 = (px - ax) ** 2 + (py - ay) ** 2
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / seg2
            t = max(0.0, min(1.0, t))
            cx, cy = ax + t * dx, ay + t * dy
            d2 = (px - cx) ** 2 + (py - cy) ** 2
        if d2 > dmax:
            idx, dmax = i, d2
    if dmax > eps * eps:
        left = rdp(points[: idx + 1], eps)
        right = rdp(points[idx:], eps)
        return left[:-1] + right
    return [points[0], points[-1]]


EPS = 0.18            # px simplification tolerance (~invisible at 800px wide)
MIN_RING_DIAG = 0.6   # drop slivers smaller than this (px bbox diagonal)


def ring_to_path(ring):
    pts = [project(lng, lat) for lng, lat in ring]
    pts = rdp(pts, EPS)
    # round + drop consecutive dupes
    out = []
    last = None
    for x, y in pts:
        xy = (round(x, 1), round(y, 1))
        if xy != last:
            out.append(xy)
            last = xy
    if len(out) < 4:
        return None
    xs = [p[0] for p in out]
    ys = [p[1] for p in out]
    if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) < MIN_RING_DIAG:
        return None
    d = "".join(("M" if i == 0 else "L") + f"{x} {y}" for i, (x, y) in enumerate(out))
    return d + "Z"


def geom_to_d(geom):
    polys = geom["coordinates"]
    if geom["type"] == "Polygon":
        polys = [polys]
    parts = []
    for poly in polys:
        for ring in poly:                # outer + holes (SVG even-odd handles holes)
            d = ring_to_path(ring)
            if d:
                parts.append(d)
    return "".join(parts)


def centroid_and_bbox(geom):
    xs, ys = [], []
    # area-weighted centroid over outer rings (visual centre, not point-cloud mean)
    cx = cy = area = 0.0
    polys = geom["coordinates"]
    if geom["type"] == "Polygon":
        polys = [polys]
    for poly in polys:
        ring = [project(lng, lat) for lng, lat in poly[0]]
        a = 0.0
        for i in range(len(ring) - 1):
            x0, y0 = ring[i]
            x1, y1 = ring[i + 1]
            cross = x0 * y1 - x1 * y0
            a += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        area += a
    for lng, lat in iter_points(geom["coordinates"]):
        x, y = project(lng, lat)
        xs.append(x)
        ys.append(y)
    if abs(area) > 1e-6:
        cen = {"x": round(cx / (3 * area), 1), "y": round(cy / (3 * area), 1)}
    else:
        cen = {"x": round(sum(xs) / len(xs), 1), "y": round(sum(ys) / len(ys), 1)}
    bbox = {"x": round(min(xs), 1), "y": round(min(ys), 1),
            "w": round(max(xs) - min(xs), 1), "h": round(max(ys) - min(ys), 1)}
    pts = list(iter_points(geom["coordinates"]))
    ll = {"lng": round(sum(p[0] for p in pts) / len(pts), 4),
          "lat": round(sum(p[1] for p in pts) / len(pts), 4)}
    return cen, bbox, ll


def fetch(tier):
    path = os.path.join(RAW, f"{tier}.geojson")
    if not os.path.exists(path):
        print(f"  downloading {tier} …")
        urllib.request.urlretrieve(SOURCES[tier], path)
    return json.load(open(path))


def bake_parlimen():
    fc = fetch("parlimen")["features"]
    seats = []
    for f in fc:
        pr = f["properties"]
        code = pr["code_parlimen"]                      # P.001
        name = pr["parlimen"].split(" ", 1)[1].strip()  # "P.001 Padang Besar" -> "Padang Besar"
        cen, bbox, ll = centroid_and_bbox(f["geometry"])
        seats.append({
            "code": code, "name": name, "state": pr["state"],
            "state_code": pr["code_state"],
            "d": geom_to_d(f["geometry"]),
            "centroid": cen, "bbox": bbox, "ll": ll,
        })
    seats.sort(key=lambda s: s["code"])
    return {"tier": "parlimen", "viewBox": VIEWBOX, "count": len(seats), "seats": seats}


def bake_dun():
    fc = fetch("dun")["features"]
    seats = []
    for f in fc:
        pr = f["properties"]
        code = pr["code_state_dun"]                      # 1_N.01 (globally unique)
        name = pr["dun"].split(" ", 1)[1].strip()        # "N.01 Buloh Kasap" -> "Buloh Kasap"
        cen, bbox, ll = centroid_and_bbox(f["geometry"])
        seats.append({
            "code": code, "dun_code": pr["code_dun"], "name": name,
            "state": pr["state"], "state_code": pr["code_state"],
            "parlimen": pr["code_parlimen"],             # parent P-seat for drill-down
            "d": geom_to_d(f["geometry"]),
            "centroid": cen, "bbox": bbox, "ll": ll,
        })
    seats.sort(key=lambda s: s["code"])
    return {"tier": "dun", "viewBox": VIEWBOX, "count": len(seats), "seats": seats}


def write(name, data):
    path = os.path.join(OUT, name)
    with open(path, "w") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(path) / 1024
    print(f"  → {name}  ({data['count']} seats, {kb:.0f} KB)")


if __name__ == "__main__":
    print("Baking electoral boundaries (frozen krackedmaps projection)…")
    write("seats-parlimen.json", bake_parlimen())
    write("seats-dun.json", bake_dun())
    print("Done.")
