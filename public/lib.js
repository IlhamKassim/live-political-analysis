// MyPolitik — pure, DOM-free logic shared by the app and the test suite.
// Everything here must run unchanged in the browser AND under `node --test`,
// so: no `document`, no `window`, no `location` — inputs in, values out.

// ---- coalition palette ----
// The GE15 coalition → swatch colour table (legend bars, bloc pills, the seat
// fill, the share card). Kept here so it ships WITH unit tests and the app, the
// legend and the share-card all read ONE source of truth. Byte-identical to the
// table that was inline in app.js.
export const COALITION_COLORS = {
  PH: "#d7263d", PN: "#15387c", BN: "#1f9bd6", GPS: "#b8332e",
  GRS: "#e8772e", WARISAN: "#16a085", KDM: "#8e44ad", PBM: "#6c7a89",
  BEBAS: "#8a97a6",
  // Sabah/Sarawak parties that win seats running outside a formal coalition
  STAR: "#b08a1f", UPKO: "#2e8b57", PSB: "#9b4d8a",
};

// Map a coalition code to its colour, case-insensitively. Unknown / empty /
// non-string input falls back to the neutral grey #5d6b7d.
export function partyColor(p) {
  return COALITION_COLORS[(typeof p === "string" ? p : "").toUpperCase()] || "#5d6b7d";
}

// Map a 0..100 performance score to a red→yellow→green ramp. Faithful
// extraction of app.js's old inline seatValueColor math: 0 → hue 0 (red),
// 100 → hue 130 (green), clamped at both ends. Non-finite / non-number input
// (NaN, null, undefined, strings) falls back to the neutral grey #5d6b7d
// rather than emitting a malformed `hsl(NaN …)`.
export function scoreColor(score) {
  if (typeof score !== "number" || !Number.isFinite(score)) return "#5d6b7d";
  const t = Math.max(0, Math.min(1, score / 100));
  const h = Math.round(t * 130); // 0 red -> 130 green
  return `hsl(${h} 60% 45%)`;
}

// ---- shareable URL state  (#tier/mode[/code]) ----
// encodeHash builds the location hash from app state; decodeHash parses one
// back. Faithful extraction of app.js's old writeHash/parseHash internals —
// same encoding, same field order, same null-on-empty contract.

export function encodeHash(state) {
  const parts = [state.tier, state.mode];
  if (state.selected) parts.push(state.selected);
  if (state.prnMode) parts.push("prn");   // live-election view (e.g. PRN Johor 2026)
  return "#" + parts.map(encodeURIComponent).join("/");
}

export function decodeHash(hash) {
  const raw = String(hash == null ? "" : hash).replace(/^#/, "");
  if (!raw) return null;
  const toks = raw.split("/").map((s) => decodeURIComponent(s || ""));
  let prn = false;
  if (toks.length > 2 && toks[toks.length - 1] === "prn") {
    prn = true;
    toks.pop();
  }
  const [tier, mode, code] = toks;
  return { tier, mode, code, prn };
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

// Filter seats for the search dropdown. Case-insensitive substring match on the
// citizen-visible fields — `name`, `code`, `state` for every tier, PLUS a DUN
// seat's visible `dun_code` and its parent `parlimen` code (so a citizen can
// find a DUN by its parliamentary constituency). Same predicate the app used
// inline; app.js still slices the result for the dropdown / map highlight.
// Non-array seats or a null / blank / non-string query → [] (never throws).
export function searchSeats(seats, query, tier) {
  if (!Array.isArray(seats)) return [];
  const q = (typeof query === "string" ? query : "").trim().toLowerCase();
  if (!q) return [];
  const hit = (v) => typeof v === "string" && v.toLowerCase().includes(q);
  return seats.filter((s) =>
    !!s && (hit(s.name) || hit(s.code) || hit(s.state) ||
      (tier === "dun" && (hit(s.dun_code) || hit(s.parlimen))))
  );
}

// ---- seat join / display keys ----
// ONE source of truth for the two tier-dependent seat codes, which were each
// duplicated inline across app.js. Both treat any non-"parlimen" tier as DUN,
// matching app.js's existing `=== "parlimen"` checks.
//
// resultKey: the key a seat joins the RESULTS table on — a parlimen seat keys on
// its own `code` (P.xxx); a DUN seat keys on its parent `parlimen` code.
export function resultKey(seat, tier) {
  if (!seat || typeof seat !== "object") return undefined;
  return tier === "parlimen" ? seat.code : seat.parlimen;
}

// displayCode: the citizen-visible code shown on the card / dropdown — a parlimen
// seat shows its `code` (P.xxx); a DUN seat shows its own `dun_code` (N.xx).
export function displayCode(seat, tier) {
  if (!seat || typeof seat !== "object") return undefined;
  return tier === "parlimen" ? seat.code : seat.dun_code;
}

// ---- coalition tally (legend bloc bar) ----
// Count seats won per coalition from the RESULTS table — `{coalition: count}`.
// Faithful extraction of renderSummary's old inline counter. Null / non-object
// input → `{}`; rows with a missing/blank/non-string coalition are skipped (so a
// future partial row can never seed an `undefined`/empty bloc in the legend).
export function tallyCoalitions(results) {
  const counts = {};
  if (!results || typeof results !== "object") return counts;
  for (const v of Object.values(results)) {
    const c = v && typeof v.coalition === "string" ? v.coalition.trim() : "";
    if (c) counts[c] = (counts[c] || 0) + 1;
  }
  return counts;
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
// `maxKm` bounds the match so far-away/out-of-country points (e.g. abroad) return
// null instead of snapping to a random border seat; default Infinity = no bound.
export function nearestSeat(lat, lng, seats, maxKm = Infinity) {
  if (!Array.isArray(seats) || !Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  let best = null, bestD = Infinity;
  for (const seat of seats) {
    const ll = seat && seat.ll;
    if (!ll || !Number.isFinite(ll.lat) || !Number.isFinite(ll.lng)) continue;
    const dkm = haversine(lat, lng, ll.lat, ll.lng);
    if (dkm < bestD) { bestD = dkm; best = seat; }
  }
  return bestD <= maxKm ? best : null;
}

// ---- seat-card formatting ----
// Pure shapers that turn a raw GE15 result row into display-ready values for the
// seat card. They surface fields the panel didn't previously show — `party_full`,
// `n_candidates`, `runner_up.votes` — and guard every edge (missing runner-up,
// 0 votes, 100% turnout, single-candidate seats). NO HTML here: callers render,
// we only shape. Every numeric field passes through a Number.isFinite guard so a
// legitimate 0 (0 votes, 0% majority) survives where a falsy check would drop it.

const str = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
const num = (v) => (Number.isFinite(v) ? v : null);

// Full party name + abbreviation. `party_full` is the human label ("Perikatan
// Nasional"); `party` is the code ("PN"). Returns {abbr, full, label} or null when
// neither is present. label = "Perikatan Nasional (PN)" when both exist and differ,
// otherwise whichever single value we have.
export function formatParty(r) {
  if (!r || typeof r !== "object") return null;
  const abbr = str(r.party);
  const full = str(r.party_full);
  if (!abbr && !full) return null;
  const label = abbr && full && abbr !== full ? `${full} (${abbr})` : (full || abbr);
  return { abbr, full, label };
}

// Number of candidates who contested. Returns the integer (>= 1) or null when
// absent/invalid. 1 marks a single-candidate seat — callers can word that specially.
export function candidateCount(r) {
  const n = r && r.n_candidates;
  return Number.isFinite(n) && n >= 1 ? Math.trunc(n) : null;
}

// Runner-up summary, surfacing `runner_up.votes` (the panel previously showed only
// the name + party). Returns {name, party, votes} with per-field guards, or null
// when there is no runner-up (e.g. a single-candidate seat).
export function formatRunnerUp(r) {
  const ru = r && r.runner_up;
  if (!ru || typeof ru !== "object") return null;
  return { name: str(ru.name), party: str(ru.party), votes: num(ru.votes) };
}

// ---- share-image geometry ----
// Fit a seat's bbox into a target rectangle, preserving aspect ratio and centering.
// Returns {scale, dx, dy} such that a seat point (px, py) maps to canvas coords
// (px*scale + dx, py*scale + dy) — i.e. translate(dx,dy)+scale(scale) before
// filling new Path2D(seat.d). `pad` is the inner margin on every side (px of the
// TARGET box). Returns null for a missing/degenerate bbox or non-positive target.
// Pure geometry so the share-card thumbnail transform is unit-testable headless.
export function fitBox(bbox, targetW, targetH, pad = 0) {
  if (!bbox || typeof bbox !== "object") return null;
  const { x, y, w, h } = bbox;
  if (![x, y, w, h, targetW, targetH, pad].every(Number.isFinite)) return null;
  if (w <= 0 || h <= 0) return null;
  const innerW = targetW - 2 * pad;
  const innerH = targetH - 2 * pad;
  if (innerW <= 0 || innerH <= 0) return null;
  const scale = Math.min(innerW / w, innerH / h);
  // centre the scaled content inside the padded box
  const dx = pad + (innerW - w * scale) / 2 - x * scale;
  const dy = pad + (innerH - h * scale) / 2 - y * scale;
  return { scale, dx, dy };
}

// Deterministic per-state colour map for "Negeri" mode + the legend swatches.
// Golden-angle (137.508°) hue spacing keeps consecutive states (e.g. Sabah/Sarawak)
// far apart on the wheel instead of clashing on a smooth ramp; the i%3 / i%2 jitter
// adds gentle saturation/lightness separation. Pure + stable: same seats array →
// byte-identical map (states sorted unique). Non-array seats → {} (no throw); a
// seat with a missing `state` is folded under the `undefined` key without crashing.
export function stateHues(seats) {
  if (!Array.isArray(seats)) return {};
  const states = [...new Set(seats.map((s) => s && s.state))].sort();
  const map = {};
  states.forEach((st, i) => {
    const h = Math.round((i * 137.508) % 360);
    const s = 38 + (i % 3) * 6;          // gentle sat/light jitter for extra separation
    const l = 40 + (i % 2) * 5;
    map[st] = `hsl(${h} ${s}% ${l}%)`;
  });
  return map;
}

// Compose the whole display-ready card from a raw result row. Pure: shapes values,
// no HTML. Numeric fields use the Number.isFinite guard so 0s and extremes (100%
// turnout) pass through unchanged. Returns null for a missing/non-object row.
export function formatResultCard(r) {
  if (!r || typeof r !== "object") return null;
  return {
    name: str(r.name),
    party: formatParty(r),
    coalition: str(r.coalition),
    coalitionFull: str(r.coalition_full),
    votes: num(r.votes),
    votePct: num(r.vote_pct),
    majority: num(r.majority),
    majorityPct: num(r.majority_pct),
    turnout: num(r.turnout),
    candidates: candidateCount(r),
    runnerUp: formatRunnerUp(r),
  };
}
