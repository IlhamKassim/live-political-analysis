// MyPolitik — pure, DOM-free logic shared by the app and the test suite.
// Everything here must run unchanged in the browser AND under `node --test`,
// so: no `document`, no `window`, no `location` — inputs in, values out.

// ---- shareable URL state  (#tier/mode[/code]) ----
// encodeHash builds the location hash from app state; decodeHash parses one
// back. Faithful extraction of app.js's old writeHash/parseHash internals —
// same encoding, same field order, same null-on-empty contract.

export function encodeHash(state) {
  const parts = [state.tier, state.mode];
  if (state.selected) parts.push(state.selected);
  return "#" + parts.map(encodeURIComponent).join("/");
}

export function decodeHash(hash) {
  const raw = String(hash == null ? "" : hash).replace(/^#/, "");
  if (!raw) return null;
  const [tier, mode, code] = raw.split("/").map((s) => decodeURIComponent(s || ""));
  return { tier, mode, code };
}

// ---- initial language pick ----
// BM-first with a browser override. Precedence:
//   1. an explicit saved preference ("ms" | "en") always wins;
//   2. otherwise the first recognised browser language tag decides
//      (e.g. "en-GB" → en, "ms-MY" → ms);
//   3. otherwise default to Bahasa Melayu ("ms").
// Ships the MECHANISM only — the final default taste is Danial's call.
export function pickInitialLang(saved, navLanguages) {
  if (saved === "ms" || saved === "en") return saved;
  const langs = Array.isArray(navLanguages) ? navLanguages : [];
  for (const l of langs) {
    if (typeof l !== "string") continue;
    const tag = l.toLowerCase();
    if (tag === "ms" || tag.startsWith("ms-") || tag.startsWith("ms_")) return "ms";
    if (tag === "en" || tag.startsWith("en-") || tag.startsWith("en_")) return "en";
  }
  return "ms";
}

// ---- geolocation: lng/lat → seat ----
// The seat `d` paths are baked in projected SVG-viewBox px (pipeline/01_boundaries.py).
// So "which seat is this GPS point in?" = project the point with the SAME frozen
// projection, then point-in-polygon against the seat path. FROZEN PROJECTION —
// copied faithfully from pipeline/01_boundaries.py, including the lng>=107 Borneo
// shift. Do NOT "improve" these constants; the path coords were baked with them.

const PROJ = {
  minx: 1.747419824825661, maxy: 0.12329370352362226,
  scale: 2848.660976322988, pad: 24.0, eastLng: 107.0,
  shift: 240.0879, offX: 31.9088, offY: 5.9369,
};
const D = Math.PI / 180;

// Faithful port of project(lng, lat) — returns [x, y] in viewBox px.
export function project(lng, lat) {
  const mx = lng * D;
  const my = Math.log(Math.tan(Math.PI / 4 + (lat * D) / 2));
  let x = (mx - PROJ.minx) * PROJ.scale + PROJ.pad;
  let y = (PROJ.maxy - my) * PROJ.scale + PROJ.pad;
  if (lng >= PROJ.eastLng) x -= PROJ.shift;     // Borneo shift (frozen)
  return [x + PROJ.offX, y + PROJ.offY];
}

// Parse a baked SVG path ("Mx yLx y…ZMx y…Z") into rings of [x, y] points.
// Each "M" opens a new ring; "Z" closes the current one. Tolerant of missing
// trailing "Z" and of "," or whitespace between numbers.
export function parsePathRings(d) {
  const rings = [];
  let cur = null;
  const re = /([MLZ])([^MLZ]*)/gi;
  let m;
  while ((m = re.exec(String(d || ""))) !== null) {
    const cmd = m[1].toUpperCase();
    if (cmd === "Z") {
      if (cur && cur.length) rings.push(cur);
      cur = null;
      continue;
    }
    const n = m[2].trim().split(/[\s,]+/).filter(Boolean).map(Number);
    if (n.length < 2 || !Number.isFinite(n[0]) || !Number.isFinite(n[1])) continue;
    if (cmd === "M") {
      if (cur && cur.length) rings.push(cur);
      cur = [[n[0], n[1]]];
    } else {
      if (!cur) cur = [];
      cur.push([n[0], n[1]]);
    }
  }
  if (cur && cur.length) rings.push(cur);
  return rings;
}

// Even-odd point-in-polygon across ALL rings (holes handled by parity), matching
// the SVG even-odd fill the seat paths are rendered with. (x, y) in viewBox px.
export function pointInRings(x, y, rings) {
  let inside = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1];
      const xj = ring[j][0], yj = ring[j][1];
      const intersect = ((yi > y) !== (yj > y)) &&
        (x < ((xj - xi) * (y - yi)) / (yj - yi) + xi);
      if (intersect) inside = !inside;
    }
  }
  return inside;
}

// Which seat contains (lat, lng)? Project once, bbox-prefilter, then PIP.
// Returns the seat object or null. seats: the .seats array from a tier file.
export function findSeatForLocation(lat, lng, seats) {
  if (!Array.isArray(seats)) return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  const [x, y] = project(lng, lat);
  for (const seat of seats) {
    const b = seat && seat.bbox;
    if (b && (x < b.x || y < b.y || x > b.x + b.w || y > b.y + b.h)) continue;
    if (pointInRings(x, y, parsePathRings(seat.d))) return seat;
  }
  return null;
}

// Great-circle distance in km (haversine). lat/lng in degrees.
export function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * D;
  const dLng = (lng2 - lng1) * D;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * D) * Math.cos(lat2 * D) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

// Fallback when PIP finds nothing (offshore points, simplification gaps):
// the seat whose representative point (seat.ll) is closest. null if no usable data.
export function nearestSeat(lat, lng, seats) {
  if (!Array.isArray(seats) || !Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  let best = null, bestD = Infinity;
  for (const seat of seats) {
    const ll = seat && seat.ll;
    if (!ll || !Number.isFinite(ll.lat) || !Number.isFinite(ll.lng)) continue;
    const dkm = haversine(lat, lng, ll.lat, ll.lng);
    if (dkm < bestD) { bestD = dkm; best = seat; }
  }
  return best;
}
