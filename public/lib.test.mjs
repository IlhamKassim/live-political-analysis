// Zero-dependency unit tests for public/lib.js — run with `node --test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  encodeHash, decodeHash,
  pickInitialLang,
  project, parsePathRings, pointInRings,
  findSeatForLocation, haversine, nearestSeat,
  formatParty, candidateCount, formatRunnerUp, formatResultCard, fitBox,
  partyColor, COALITION_COLORS, scoreColor, searchSeats,
  resultKey, displayCode, tallyCoalitions, stateHues, swatchTextColor,
  competitivenessFromMajorityPct, withCurrentAffiliation,
} from "./lib.js";
import { I18N } from "./i18n.js";

const parlimen = JSON.parse(
  readFileSync(fileURLToPath(new URL("./data/seats-parlimen.json", import.meta.url)), "utf8")
);
const SEATS = parlimen.seats;

const RESULTS = JSON.parse(
  readFileSync(fileURLToPath(new URL("./data/results-ge15.json", import.meta.url)), "utf8")
);

const RESULTS_DUN = JSON.parse(
  readFileSync(fileURLToPath(new URL("./data/results-dun.json", import.meta.url)), "utf8")
);

const CURRENT_AFFILIATIONS = JSON.parse(
  readFileSync(fileURLToPath(new URL("./data/current-affiliations.json", import.meta.url)), "utf8")
);

test("encodeHash: tier + mode, no selection", () => {
  assert.equal(encodeHash({ tier: "parlimen", mode: "parti" }), "#parlimen/parti");
});

test("encodeHash: includes selected seat code when present", () => {
  assert.equal(
    encodeHash({ tier: "parlimen", mode: "parti", selected: "P.001" }),
    "#parlimen/parti/P.001"
  );
});

test("encodeHash: falsy selected is omitted (null/empty/undefined)", () => {
  assert.equal(encodeHash({ tier: "dun", mode: "skor", selected: null }), "#dun/skor");
  assert.equal(encodeHash({ tier: "dun", mode: "skor", selected: "" }), "#dun/skor");
  assert.equal(encodeHash({ tier: "dun", mode: "skor" }), "#dun/skor");
});

test("encodeHash: percent-encodes special characters", () => {
  assert.equal(
    encodeHash({ tier: "parlimen", mode: "parti", selected: "a b/c" }),
    "#parlimen/parti/a%20b%2Fc"
  );
});

test("encodeHash: prnMode appends a trailing /prn token", () => {
  assert.equal(encodeHash({ tier: "dun", mode: "parti", prnMode: true }), "#dun/parti/prn");
  assert.equal(
    encodeHash({ tier: "dun", mode: "parti", selected: "1_N.01", prnMode: true }),
    "#dun/parti/1_N.01/prn"
  );
  assert.equal(encodeHash({ tier: "dun", mode: "parti", prnMode: false }), "#dun/parti");
});

test("decodeHash: trailing prn token sets prn and never leaks into code", () => {
  assert.deepEqual(decodeHash("#dun/parti/prn"), { tier: "dun", mode: "parti", code: undefined, stateName: undefined, prn: true });
  assert.deepEqual(decodeHash("#dun/parti/1_N.01/prn"), { tier: "dun", mode: "parti", code: "1_N.01", stateName: undefined, prn: true });
  assert.deepEqual(decodeHash("#dun/parti/1_N.01"), { tier: "dun", mode: "parti", code: "1_N.01", stateName: undefined, prn: false });
});

test("decodeHash: empty hash returns null", () => {
  assert.equal(decodeHash(""), null);
  assert.equal(decodeHash("#"), null);
  assert.equal(decodeHash(null), null);
  assert.equal(decodeHash(undefined), null);
});

test("decodeHash: full hash with leading #", () => {
  assert.deepEqual(decodeHash("#parlimen/parti/P.001"), {
    tier: "parlimen",
    mode: "parti",
    code: "P.001",
    stateName: undefined,
    prn: false,
  });
});

test("decodeHash: works without leading #", () => {
  assert.deepEqual(decodeHash("dun/skor"), { tier: "dun", mode: "skor", code: undefined, stateName: undefined, prn: false });
});

test("decodeHash: absent trailing segments are undefined (faithful to old parseHash)", () => {
  assert.deepEqual(decodeHash("#parlimen"), { tier: "parlimen", mode: undefined, code: undefined, stateName: undefined, prn: false });
});

test("decodeHash: extra path segments are ignored", () => {
  assert.deepEqual(decodeHash("#a/b/c/d/e"), { tier: "a", mode: "b", code: "c", stateName: undefined, prn: false });
});

test("decodeHash: percent-decodes each segment", () => {
  assert.deepEqual(decodeHash("#parlimen/parti/a%20b%2Fc"), {
    tier: "parlimen",
    mode: "parti",
    code: "a b/c",
    stateName: undefined,
    prn: false,
  });
});

// ---- open-state token (s:StateName) ----
test("encodeHash: openState without selected emits an s: token", () => {
  assert.equal(
    encodeHash({ tier: "dun", mode: "parti", openState: "Selangor" }),
    "#dun/parti/s%3ASelangor"
  );
  // state names with spaces are percent-encoded whole
  assert.equal(
    encodeHash({ tier: "dun", mode: "parti", openState: "Negeri Sembilan" }),
    "#dun/parti/s%3ANegeri%20Sembilan"
  );
});

test("encodeHash: selected seat wins over openState (code implies its state)", () => {
  assert.equal(
    encodeHash({ tier: "dun", mode: "parti", selected: "10_N.01", openState: "Selangor" }),
    "#dun/parti/10_N.01"
  );
});

test("encodeHash: s: token composes with /prn", () => {
  assert.equal(
    encodeHash({ tier: "dun", mode: "parti", openState: "Johor", prnMode: true }),
    "#dun/parti/s%3AJohor/prn"
  );
});

test("decodeHash: s: token yields stateName, never leaks into code", () => {
  assert.deepEqual(decodeHash("#dun/parti/s%3ANegeri%20Sembilan"), {
    tier: "dun", mode: "parti", code: undefined, stateName: "Negeri Sembilan", prn: false,
  });
  assert.deepEqual(decodeHash("#dun/parti/s%3AJohor/prn"), {
    tier: "dun", mode: "parti", code: undefined, stateName: "Johor", prn: true,
  });
});

test("decodeHash round-trip: openState survives encode → decode", () => {
  const d = decodeHash(encodeHash({ tier: "parlimen", mode: "parti", openState: "Pulau Pinang" }));
  assert.equal(d.stateName, "Pulau Pinang");
  assert.equal(d.code, undefined);
});

// ---- competitiveness classifier ----
test("competitivenessFromMajorityPct: thresholds and guards", () => {
  assert.deepEqual(competitivenessFromMajorityPct(2.3), { key: "marginal", pct: 2.3 });
  assert.deepEqual(competitivenessFromMajorityPct(4.99), { key: "marginal", pct: 4.99 });
  assert.deepEqual(competitivenessFromMajorityPct(5), { key: "leaning", pct: 5 });
  assert.deepEqual(competitivenessFromMajorityPct(14.9), { key: "leaning", pct: 14.9 });
  assert.deepEqual(competitivenessFromMajorityPct(15), { key: "safe", pct: 15 });
  assert.deepEqual(competitivenessFromMajorityPct(60), { key: "safe", pct: 60 });
  // 0 is a valid (dead-heat) margin, not a missing one
  assert.deepEqual(competitivenessFromMajorityPct(0), { key: "marginal", pct: 0 });
  for (const bad of [null, undefined, NaN, Infinity, -1, "5"]) {
    assert.equal(competitivenessFromMajorityPct(bad), null, `bad input: ${bad}`);
  }
});

test("round-trip: encode → decode preserves tier/mode/selected", () => {
  const state = { tier: "dun", mode: "parti", selected: "N.01" };
  const decoded = decodeHash(encodeHash(state));
  assert.equal(decoded.tier, state.tier);
  assert.equal(decoded.mode, state.mode);
  assert.equal(decoded.code, state.selected);
});

// ---- geolocation core ----

test("project: returns finite [x,y] within the viewBox for a Peninsular point", () => {
  const [x, y] = project(101.7117, 3.1578); // KLCC
  assert.ok(Number.isFinite(x) && Number.isFinite(y));
  assert.ok(x > 0 && x < 799.85, `x in viewBox: ${x}`);
  assert.ok(y > 0 && y < 352.74, `y in viewBox: ${y}`);
});

test("project: lng>=107 triggers the frozen Borneo shift (x jumps left by 240.0879)", () => {
  // Same lat, lng straddling the 107 boundary: the >=107 side is shifted left.
  const lat = 2.0;
  const [xWest] = project(106.9999, lat); // no shift
  const [xEast] = project(107.0001, lat); // shifted
  // Without the shift, a tiny lng increase would nudge x slightly RIGHT.
  // The shift instead drops x by ~240px, so xEast must be far left of xWest.
  assert.ok(xWest - xEast > 239 && xWest - xEast < 241, `delta=${xWest - xEast}`);
});

test("parsePathRings: parses M/L/Z into rings of [x,y] points", () => {
  const rings = parsePathRings("M10 20L30 20L30 40L10 40ZM0 0L1 0L1 1Z");
  assert.equal(rings.length, 2);
  assert.deepEqual(rings[0], [[10, 20], [30, 20], [30, 40], [10, 40]]);
  assert.deepEqual(rings[1], [[0, 0], [1, 0], [1, 1]]);
});

test("parsePathRings: tolerates missing trailing Z and garbage input", () => {
  assert.deepEqual(parsePathRings("M5 5L6 6L7 7"), [[[5, 5], [6, 6], [7, 7]]]);
  assert.deepEqual(parsePathRings(""), []);
  assert.deepEqual(parsePathRings(null), []);
  assert.deepEqual(parsePathRings(undefined), []);
});

test("pointInRings: inside / outside of a simple square", () => {
  const sq = [[[0, 0], [10, 0], [10, 10], [0, 10]]];
  assert.equal(pointInRings(5, 5, sq), true);
  assert.equal(pointInRings(15, 5, sq), false);
  assert.equal(pointInRings(-1, 5, sq), false);
});

test("pointInRings: even-odd rule punches a hole (inner ring)", () => {
  const outer = [[0, 0], [10, 0], [10, 10], [0, 10]];
  const hole = [[3, 3], [7, 3], [7, 7], [3, 7]];
  const rings = [outer, hole];
  assert.equal(pointInRings(5, 5, rings), false); // inside the hole → not in seat
  assert.equal(pointInRings(1, 1, rings), true);  // between outer and hole → in seat
});

// Fixture table: known GPS points → the seat that actually contains them.
// Kuching + KK have lng>=107 so they exercise the Borneo shift branch end-to-end.
const FIXTURES = [
  { place: "KLCC",            lat: 3.1578,  lng: 101.7117, code: "P.119", state: "W.P. Kuala Lumpur" },
  { place: "Putrajaya",       lat: 2.9264,  lng: 101.6964, code: "P.125", state: "W.P. Putrajaya" },
  { place: "Penang (G.Town)", lat: 5.4141,  lng: 100.3288, code: "P.049", state: "Pulau Pinang" },
  { place: "Johor Bahru",     lat: 1.4927,  lng: 103.7414, code: "P.160", state: "Johor" },
  { place: "Kuching",         lat: 1.5535,  lng: 110.3593, code: "P.195", state: "Sarawak" },
  { place: "Kota Kinabalu",   lat: 5.9804,  lng: 116.0735, code: "P.172", state: "Sabah" },
];

for (const f of FIXTURES) {
  test(`findSeatForLocation: ${f.place} → ${f.code}`, () => {
    const seat = findSeatForLocation(f.lat, f.lng, SEATS);
    assert.ok(seat, `${f.place} found no seat`);
    assert.equal(seat.code, f.code);
    assert.equal(seat.state, f.state);
  });
}

test("findSeatForLocation: NaN / out-of-country / bad input → null", () => {
  assert.equal(findSeatForLocation(NaN, 101, SEATS), null);
  assert.equal(findSeatForLocation(3.15, NaN, SEATS), null);
  assert.equal(findSeatForLocation(3.15, 101.7, null), null);
  assert.equal(findSeatForLocation(48.8566, 2.3522, SEATS), null); // Paris
});

test("haversine: KL→Singapore ≈ 300 km", () => {
  const km = haversine(3.139, 101.6869, 1.3521, 103.8198);
  assert.ok(km > 290 && km < 320, `got ${km} km`);
  assert.equal(haversine(1, 1, 1, 1), 0);
});

test("nearestSeat: offshore point falls back to the closest seat", () => {
  // A point in the Strait off Penang: PIP misses, nearest should still be sane.
  const seat = nearestSeat(5.30, 100.10, SEATS);
  assert.ok(seat, "nearest returned null");
  assert.equal(seat.state, "Pulau Pinang");
});

test("nearestSeat: bad input → null", () => {
  assert.equal(nearestSeat(NaN, 100, SEATS), null);
  assert.equal(nearestSeat(5, 100, []), null);
  assert.equal(nearestSeat(5, 100, null), null);
});

test("nearestSeat: maxKm bounds the match (offshore matches, abroad → null)", () => {
  // Strait off Penang: near a real seat, so a generous bound still resolves.
  const offshore = nearestSeat(5.30, 100.10, SEATS, 150);
  assert.ok(offshore, "near-offshore point should still match within 150 km");
  assert.equal(offshore.state, "Pulau Pinang");
  // London is thousands of km from any seat → no honest match under a small bound.
  assert.equal(nearestSeat(51.5074, -0.1278, SEATS, 150), null);
  // Singapore (~25 km from JB) sits within 150 km → it would still snap to a
  // border seat, which is why locate() relies on maxKm + the loc_notfound copy
  // for genuinely far points; here we assert a 1 km bound rejects even Singapore.
  assert.equal(nearestSeat(1.3521, 103.8198, SEATS, 1), null);
});

test("nearestSeat: default (no maxKm) keeps closest-seat behaviour", () => {
  // Same far point as above, but with no bound → returns the closest seat (old behaviour).
  const seat = nearestSeat(51.5074, -0.1278, SEATS);
  assert.ok(seat, "default nearestSeat should never return null for valid coords");
});

// ---- pickInitialLang ----

test("pickInitialLang: saved preference always wins", () => {
  assert.equal(pickInitialLang("ms", ["en-US", "en"]), "ms");
  assert.equal(pickInitialLang("en", ["ms-MY", "ms"]), "en");
});

test("pickInitialLang: browser language decides when no saved pref", () => {
  assert.equal(pickInitialLang(null, ["en-GB", "en"]), "en");
  assert.equal(pickInitialLang(null, ["ms-MY"]), "ms");
  assert.equal(pickInitialLang(undefined, ["EN-US"]), "en"); // case-insensitive
  // first recognised tag wins, unknowns are skipped
  assert.equal(pickInitialLang(null, ["zh-CN", "en-US"]), "en");
  assert.equal(pickInitialLang(null, ["fr", "ms-MY", "en"]), "ms");
});

test("pickInitialLang: BM-first default when nothing matches", () => {
  assert.equal(pickInitialLang(null, []), "ms");
  assert.equal(pickInitialLang(null, ["zh-CN", "ja"]), "ms");
  assert.equal(pickInitialLang(null, null), "ms");
  assert.equal(pickInitialLang(null, undefined), "ms");
  assert.equal(pickInitialLang("bogus", ["en"]), "en"); // invalid saved → fall through
  assert.equal(pickInitialLang("", null), "ms");
});

test("pickInitialLang: ignores non-string entries in nav list", () => {
  assert.equal(pickInitialLang(null, [null, 42, {}, "en-US"]), "en");
  assert.equal(pickInitialLang(null, [undefined, "ms"]), "ms");
});

// ---- seat-card formatting ----

test("formatParty: full + abbr produce a combined label", () => {
  assert.deepEqual(
    formatParty({ party: "PN", party_full: "Perikatan Nasional" }),
    { abbr: "PN", full: "Perikatan Nasional", label: "Perikatan Nasional (PN)" }
  );
});

test("formatParty: identical abbr & full collapse to one value", () => {
  // GE15 rows where party === coalition often repeat the name; don't echo "X (X)".
  assert.deepEqual(
    formatParty({ party: "PH", party_full: "PH" }),
    { abbr: "PH", full: "PH", label: "PH" }
  );
});

test("formatParty: missing one side falls back to the other", () => {
  assert.deepEqual(formatParty({ party: "BN" }), { abbr: "BN", full: null, label: "BN" });
  assert.deepEqual(
    formatParty({ party_full: "Pakatan Harapan" }),
    { abbr: null, full: "Pakatan Harapan", label: "Pakatan Harapan" }
  );
});

test("formatParty: no usable party → null; trims whitespace", () => {
  assert.equal(formatParty({}), null);
  assert.equal(formatParty({ party: "   ", party_full: "" }), null);
  assert.equal(formatParty(null), null);
  assert.equal(formatParty(undefined), null);
  assert.deepEqual(formatParty({ party: "  PN  " }), { abbr: "PN", full: null, label: "PN" });
});

test("candidateCount: surfaces n_candidates; null when absent/invalid", () => {
  assert.equal(candidateCount({ n_candidates: 5 }), 5);
  assert.equal(candidateCount({ n_candidates: 1 }), 1);   // single-candidate seat
  assert.equal(candidateCount({ n_candidates: 3.9 }), 3); // truncates
  assert.equal(candidateCount({ n_candidates: 0 }), null); // 0 candidates is nonsense
  assert.equal(candidateCount({}), null);
  assert.equal(candidateCount({ n_candidates: "5" }), null); // non-number
  assert.equal(candidateCount(null), null);
});

test("formatRunnerUp: surfaces name, party and votes", () => {
  assert.deepEqual(
    formatRunnerUp({ runner_up: { name: "Zahida Binti Zarik Khan", party: "BN", votes: 11753 } }),
    { name: "Zahida Binti Zarik Khan", party: "BN", votes: 11753 }
  );
});

test("formatRunnerUp: 0 votes survives the guard", () => {
  // Number.isFinite(0) is true — a falsy check would wrongly drop a real zero.
  assert.deepEqual(
    formatRunnerUp({ runner_up: { name: "X", party: "IND", votes: 0 } }),
    { name: "X", party: "IND", votes: 0 }
  );
});

test("formatRunnerUp: no runner-up (single-candidate seat) → null", () => {
  assert.equal(formatRunnerUp({ name: "Solo" }), null);
  assert.equal(formatRunnerUp({ runner_up: null }), null);
  assert.equal(formatRunnerUp(null), null);
});

test("formatRunnerUp: per-field guards for partial runner-up", () => {
  assert.deepEqual(
    formatRunnerUp({ runner_up: { name: "  Y  ", votes: "lots" } }),
    { name: "Y", party: null, votes: null }
  );
});

test("formatResultCard: shapes the full Perlis fixture (real data)", () => {
  const card = formatResultCard(RESULTS["P.001"]);
  assert.equal(card.name, "Rushdan Bin Rusmi");
  assert.deepEqual(card.party, { abbr: "PN", full: "Perikatan Nasional", label: "Perikatan Nasional (PN)" });
  assert.equal(card.coalition, "PN");
  assert.equal(card.votes, 24267);
  assert.equal(card.votePct, 53.6);
  assert.equal(card.majority, 12514);
  assert.equal(card.majorityPct, 27.6);
  assert.equal(card.turnout, 76.5);
  assert.equal(card.candidates, 5);
  assert.deepEqual(card.runnerUp, { name: "Zahida Binti Zarik Khan", party: "BN", votes: 11753 });
});

test("formatResultCard: every result row shapes without throwing", () => {
  // Whole-dataset smoke test — name + party + finite votes for all 222 seats.
  for (const [code, r] of Object.entries(RESULTS)) {
    const card = formatResultCard(r);
    assert.ok(card, `${code} → card`);
    assert.ok(card.name, `${code} → name`);
    assert.ok(card.party && card.party.label, `${code} → party label`);
    assert.ok(Number.isFinite(card.votes), `${code} → votes`);
  }
});

test("formatResultCard: edge values survive — 0 votes, 0% majority, 100% turnout", () => {
  const card = formatResultCard({
    name: "Edge", party: "IND", party_full: "Independent", coalition: "IND",
    votes: 0, vote_pct: 0, majority: 0, majority_pct: 0, turnout: 100, n_candidates: 1,
  });
  assert.equal(card.votes, 0);
  assert.equal(card.votePct, 0);
  assert.equal(card.majority, 0);
  assert.equal(card.majorityPct, 0);
  assert.equal(card.turnout, 100);
  assert.equal(card.candidates, 1);
  assert.equal(card.runnerUp, null);
});

test("formatResultCard: missing/garbage input → null or null-filled fields", () => {
  assert.equal(formatResultCard(null), null);
  assert.equal(formatResultCard(undefined), null);
  assert.equal(formatResultCard("nope"), null);
  const sparse = formatResultCard({ name: "Only Name" });
  assert.equal(sparse.name, "Only Name");
  assert.equal(sparse.party, null);
  assert.equal(sparse.votes, null);
  assert.equal(sparse.candidates, null);
  assert.equal(sparse.runnerUp, null);
});

test("formatResultCard: non-finite numerics drop to null (panel renders no NaN)", () => {
  // A partial / malformed row — vote_pct present but votes missing, NaN majority,
  // string turnout. renderPanel gates each numeric row on `card.<field> != null`,
  // so every one of these must become null (→ the row is omitted, never "NaN").
  const card = formatResultCard({
    name: "Partial", party: "PH", coalition: "PH",
    vote_pct: 53.2,            // present, but…
    votes: undefined,          // …missing → null
    majority: NaN,             // garbage → null
    majority_pct: "53",        // non-number → null
    turnout: "100",            // string → null
    n_candidates: "3",         // non-number → null candidate count
  });
  assert.equal(card.votes, null);
  assert.equal(card.votePct, 53.2);   // the lone finite value survives
  assert.equal(card.majority, null);
  assert.equal(card.majorityPct, null);
  assert.equal(card.turnout, null);
  assert.equal(card.candidates, null);
  // Infinity is not finite either → null
  assert.equal(formatResultCard({ votes: Infinity }).votes, null);
});

// ---- fitBox: share-card thumbnail transform ----
test("fitBox: a square bbox centres in a wider target, no overflow", () => {
  const f = fitBox({ x: 0, y: 0, w: 100, h: 100 }, 400, 200, 0);
  // height is the limiting dimension → scale = 200/100 = 2
  assert.equal(f.scale, 2);
  // scaled content 200×200 centred in 400×200 → dx offset, dy 0
  assert.equal(f.dy, 0);
  assert.equal(f.dx, 100); // (400-200)/2 - 0
  // a corner point maps inside the target box
  assert.deepEqual([0 * f.scale + f.dx, 0 * f.scale + f.dy], [100, 0]);
  assert.deepEqual([100 * f.scale + f.dx, 100 * f.scale + f.dy], [300, 200]);
});

test("fitBox: honours padding and a non-zero bbox origin", () => {
  const f = fitBox({ x: 50, y: 50, w: 100, h: 100 }, 220, 220, 10);
  // inner box 200×200, square content → scale = 2
  assert.equal(f.scale, 2);
  // top-left of seat maps to the padded edge (centred square fills inner box)
  assert.equal(50 * f.scale + f.dx, 10);
  assert.equal(50 * f.scale + f.dy, 10);
  // bottom-right maps to the far padded edge
  assert.equal(150 * f.scale + f.dx, 210);
  assert.equal(150 * f.scale + f.dy, 210);
});

test("fitBox: a real seat bbox fits within a 1080×1350 card region", () => {
  const seat = SEATS[0]; // P.001 Padang Besar
  const W = 1080, H = 760, PAD = 60;
  const f = fitBox(seat.bbox, W, H, PAD);
  assert.ok(f && Number.isFinite(f.scale) && f.scale > 0);
  const b = seat.bbox;
  for (const [px, py] of [[b.x, b.y], [b.x + b.w, b.y + b.h]]) {
    const cx = px * f.scale + f.dx, cy = py * f.scale + f.dy;
    assert.ok(cx >= PAD - 0.01 && cx <= W - PAD + 0.01, `x ${cx} in box`);
    assert.ok(cy >= PAD - 0.01 && cy <= H - PAD + 0.01, `y ${cy} in box`);
  }
});

test("fitBox: degenerate / garbage input → null", () => {
  assert.equal(fitBox(null, 100, 100), null);
  assert.equal(fitBox({ x: 0, y: 0, w: 0, h: 10 }, 100, 100), null);   // zero width
  assert.equal(fitBox({ x: 0, y: 0, w: 10, h: -5 }, 100, 100), null);  // negative height
  assert.equal(fitBox({ x: 0, y: 0, w: 10, h: 10 }, 0, 100), null);    // no target
  assert.equal(fitBox({ x: NaN, y: 0, w: 10, h: 10 }, 100, 100), null);// NaN coord
  assert.equal(fitBox({ x: 0, y: 0, w: 10, h: 10 }, 20, 20, 15), null);// pad eats the box
});

// ---- partyColor / COALITION_COLORS ----
test("partyColor: every GE15 coalition maps to its swatch", () => {
  assert.equal(partyColor("PH"), "#d7263d");
  assert.equal(partyColor("PN"), "#15387c");
  assert.equal(partyColor("BN"), "#1f9bd6");
  assert.equal(partyColor("GPS"), "#b8332e");
  assert.equal(partyColor("GRS"), "#e8772e");
  assert.equal(partyColor("WARISAN"), "#16a085");
});

test("partyColor: case-insensitive", () => {
  assert.equal(partyColor("ph"), "#d7263d");
  assert.equal(partyColor("Warisan"), "#16a085");
  assert.equal(partyColor("Bn"), "#1f9bd6");
});

test("partyColor: unknown / empty / nullish / non-string → #5d6b7d fallback", () => {
  assert.equal(partyColor("XYZ"), "#5d6b7d");
  assert.equal(partyColor(""), "#5d6b7d");
  assert.equal(partyColor(null), "#5d6b7d");
  assert.equal(partyColor(undefined), "#5d6b7d");
  assert.equal(partyColor(), "#5d6b7d");
  assert.equal(partyColor(42), "#5d6b7d");
  assert.equal(partyColor({}), "#5d6b7d");
  assert.equal(partyColor([]), "#5d6b7d");
});

test("withCurrentAffiliation: preserves election data unless a current override is explicit", () => {
  const result = { name: "Example", party: "UMNO", coalition: "BN", votes: 1000 };
  assert.deepEqual(withCurrentAffiliation(result), result);
  assert.deepEqual(withCurrentAffiliation(result, {
    current_party: "PAS", current_coalition: "PN", current_bloc: "PN",
  }), {
    name: "Example", party: "PAS", coalition: "PN", votes: 1000,
    current_bloc: "PN", vacant_since: null, affiliation_status: null,
  });
  // Explicit nulls must clear historical party/bloc fields when the official
  // current roster lists a representative only under a generic opposition heading.
  assert.deepEqual(withCurrentAffiliation(result, {
    current_party: null, current_coalition: null, current_bloc: "PEMBANGKANG",
    affiliation_status: "opposition-unaffiliated",
  }), {
    name: "Example", party: null, coalition: null, votes: 1000,
    current_bloc: "PEMBANGKANG", vacant_since: null,
    affiliation_status: "opposition-unaffiliated",
  });
  assert.deepEqual(withCurrentAffiliation(null, { vacant_since: "2026-05-18" }), {
    name: undefined, party: undefined, coalition: undefined, current_bloc: "", vacant_since: "2026-05-18", affiliation_status: null,
  });
});

test("current-affiliations: audited vacancy and bloc corrections are source-linked", () => {
  assert.equal(CURRENT_AFFILIATIONS.parlimen["P.100"].current_bloc, "VACANT");
  assert.equal(CURRENT_AFFILIATIONS.parlimen["P.118"].current_bloc, "VACANT");
  assert.equal(CURRENT_AFFILIATIONS.parlimen["P.030"].current_bloc, "PEMBANGKANG");
  assert.equal(CURRENT_AFFILIATIONS.parlimen["P.146"].current_party, "MUDA");
  assert.equal(CURRENT_AFFILIATIONS.dun["13_N.11"].current_bloc, "BEBAS");
  assert.equal(CURRENT_AFFILIATIONS.dun["13_N.33"].current_coalition, "GPS");
  assert.equal(CURRENT_AFFILIATIONS.dun["4_N.06"].current_coalition, "PN");
  for (const group of [CURRENT_AFFILIATIONS.parlimen, CURRENT_AFFILIATIONS.dun]) {
    for (const row of Object.values(group)) assert.match(row.source_url, /^https:\/\//);
  }
});

// ---- scoreColor (0..100 red→green ramp) ----
test("scoreColor: byte-identical to old inline math at 0/25/50/75/100", () => {
  // Mirrors seatValueColor's old math: h = round(clamp(s/100,0,1) * 130).
  assert.equal(scoreColor(0), "hsl(0 60% 45%)");    // red
  assert.equal(scoreColor(25), "hsl(33 60% 45%)");  // round(32.5)
  assert.equal(scoreColor(50), "hsl(65 60% 45%)");
  assert.equal(scoreColor(75), "hsl(98 60% 45%)");  // round(97.5)
  assert.equal(scoreColor(100), "hsl(130 60% 45%)"); // green
});

test("scoreColor: clamps out-of-range scores to the ends", () => {
  assert.equal(scoreColor(-1), "hsl(0 60% 45%)");
  assert.equal(scoreColor(-9999), "hsl(0 60% 45%)");
  assert.equal(scoreColor(101), "hsl(130 60% 45%)");
  assert.equal(scoreColor(9999), "hsl(130 60% 45%)");
});

test("scoreColor: NaN / non-number / nullish → #5d6b7d fallback (never malformed hsl)", () => {
  assert.equal(scoreColor(NaN), "#5d6b7d");
  assert.equal(scoreColor(Infinity), "#5d6b7d");
  assert.equal(scoreColor(-Infinity), "#5d6b7d");
  assert.equal(scoreColor("50"), "#5d6b7d");
  assert.equal(scoreColor(null), "#5d6b7d");
  assert.equal(scoreColor(undefined), "#5d6b7d");
  assert.equal(scoreColor(), "#5d6b7d");
  assert.equal(scoreColor({}), "#5d6b7d");
  assert.equal(scoreColor([]), "#5d6b7d");
});

test("COALITION_COLORS: exact byte-for-byte table (no swatch drift)", () => {
  assert.deepEqual(COALITION_COLORS, {
    PH: "#d7263d", PN: "#15387c", BN: "#1f9bd6", GPS: "#b8332e",
    GRS: "#e8772e", WARISAN: "#16a085", KDM: "#8e44ad", PBM: "#6c7a89",
    BEBAS: "#8a97a6",
    STAR: "#b08a1f", UPKO: "#2e8b57", PSB: "#9b4d8a",
  });
});

// ---- i18n parity (guards the untranslated-key regression class) ----
test("I18N: en and ms have IDENTICAL key sets (no forgotten translation)", () => {
  const en = Object.keys(I18N.en).sort();
  const ms = Object.keys(I18N.ms).sort();
  assert.deepEqual(ms, en);
});

test("I18N: every value is a non-empty, non-whitespace-only string", () => {
  for (const locale of ["en", "ms"]) {
    for (const [key, value] of Object.entries(I18N[locale])) {
      assert.equal(typeof value, "string", `${locale}.${key} must be a string`);
      assert.ok(value.trim().length > 0, `${locale}.${key} must not be empty/whitespace`);
    }
  }
});

// ---- markup-key parity: every data-i18n* attribute in index.html names a real,
// translated I18N key (guards the silent-untranslated-markup regression class). ----
test("I18N: every data-i18n* key in index.html exists in BOTH en and ms", () => {
  const html = readFileSync(fileURLToPath(new URL("./index.html", import.meta.url)), "utf8");
  // The six attribute flavours app.js's applyStatic() consumes.
  const attrs = ["data-i18n", "data-i18n-ph", "data-i18n-title", "data-i18n-aria", "data-i18n-content", "data-i18n-after"];
  // \b after the attr name prevents data-i18n from also swallowing data-i18n-ph etc.
  const re = new RegExp(`(?:${attrs.join("|")})\\b\\s*=\\s*"([^"]*)"`, "g");
  const keys = new Set();
  for (const m of html.matchAll(re)) keys.add(m[1]);
  assert.ok(keys.size > 0, "expected to find data-i18n* attributes in index.html");
  for (const key of keys) {
    assert.ok(key in I18N.en, `data-i18n key "${key}" missing from I18N.en`);
    assert.ok(key in I18N.ms, `data-i18n key "${key}" missing from I18N.ms`);
  }
});

// ---- searchSeats (search dropdown filter) ----
const SS_PARLIMEN = [
  { code: "P.092", name: "Sungai Buloh", state: "Selangor" },
  { code: "P.114", name: "Bangi", state: "Selangor" },
  { code: "P.001", name: "Padang Besar", state: "Perlis" },
];
const SS_DUN = [
  { code: "10_N.01", dun_code: "N.01", parlimen: "P.092", name: "Sungai Air Tawar", state: "Selangor" },
  { code: "01_N.02", dun_code: "N.02", parlimen: "P.001", name: "Beseri", state: "Perlis" },
];

test("searchSeats: empty / whitespace / null / non-string query → []", () => {
  assert.deepEqual(searchSeats(SS_PARLIMEN, "", "parlimen"), []);
  assert.deepEqual(searchSeats(SS_PARLIMEN, "   ", "parlimen"), []);
  assert.deepEqual(searchSeats(SS_PARLIMEN, null, "parlimen"), []);
  assert.deepEqual(searchSeats(SS_PARLIMEN, undefined, "parlimen"), []);
  assert.deepEqual(searchSeats(SS_PARLIMEN, 123, "parlimen"), []);
});

test("searchSeats: non-array seats → [] (no throw)", () => {
  assert.deepEqual(searchSeats(null, "bangi", "parlimen"), []);
  assert.deepEqual(searchSeats(undefined, "bangi", "parlimen"), []);
  assert.deepEqual(searchSeats({}, "bangi", "parlimen"), []);
});

test("searchSeats: case-insensitive name substring", () => {
  const hits = searchSeats(SS_PARLIMEN, "BANGI", "parlimen");
  assert.equal(hits.length, 1);
  assert.equal(hits[0].code, "P.114");
});

test("searchSeats: case-insensitive code substring", () => {
  const hits = searchSeats(SS_PARLIMEN, "p.09", "parlimen");
  assert.equal(hits.length, 1);
  assert.equal(hits[0].name, "Sungai Buloh");
});

test("searchSeats: case-insensitive state substring", () => {
  const hits = searchSeats(SS_PARLIMEN, "selangor", "parlimen");
  assert.deepEqual(hits.map((s) => s.code), ["P.092", "P.114"]);
});

test("searchSeats: DUN matches on dun_code", () => {
  const hits = searchSeats(SS_DUN, "n.02", "dun");
  assert.equal(hits.length, 1);
  assert.equal(hits[0].name, "Beseri");
});

test("searchSeats: DUN matches on parent parlimen code", () => {
  const hits = searchSeats(SS_DUN, "P.092", "dun");
  assert.equal(hits.length, 1);
  assert.equal(hits[0].name, "Sungai Air Tawar");
});

test("searchSeats: parlimen tier does NOT match dun_code/parlimen fields", () => {
  // Even if such fields existed on a parlimen seat, only name/code/state count.
  const seats = [{ code: "P.092", name: "Sungai Buloh", state: "Selangor", dun_code: "N.99", parlimen: "P.500" }];
  assert.deepEqual(searchSeats(seats, "n.99", "parlimen"), []);
  assert.deepEqual(searchSeats(seats, "p.500", "parlimen"), []);
});

test("searchSeats: tolerates null entries and missing fields (no throw)", () => {
  const seats = [null, { code: "P.001" }, { name: "Bangi" }, undefined];
  assert.deepEqual(searchSeats(seats, "bangi", "parlimen").map((s) => s.name), ["Bangi"]);
});

// ---- resultKey / displayCode (seat join + display codes) ----
const KEY_SEAT = { code: "P.092", parlimen: "P.092", dun_code: "N.01" };
const DUN_SEAT = { code: "10_N.01", parlimen: "P.092", dun_code: "N.01" };

test("resultKey: parlimen tier returns the seat's own code", () => {
  assert.equal(resultKey(KEY_SEAT, "parlimen"), "P.092");
});

test("resultKey: dun tier returns the parent parlimen code", () => {
  assert.equal(resultKey(DUN_SEAT, "dun"), "P.092");
});

test("resultKey: non-parlimen tier strings treated as dun", () => {
  assert.equal(resultKey(DUN_SEAT, "negeri"), "P.092");
  assert.equal(resultKey(DUN_SEAT, undefined), "P.092");
});

test("displayCode: parlimen tier returns the seat's own code", () => {
  assert.equal(displayCode(KEY_SEAT, "parlimen"), "P.092");
});

test("displayCode: dun tier returns the visible dun_code", () => {
  assert.equal(displayCode(DUN_SEAT, "dun"), "N.01");
});

test("resultKey/displayCode: missing field → undefined, no throw", () => {
  assert.equal(resultKey({ code: "P.001" }, "dun"), undefined);   // no parlimen
  assert.equal(displayCode({ code: "P.001" }, "dun"), undefined); // no dun_code
});

test("resultKey/displayCode: missing/non-object seat → undefined, no throw", () => {
  for (const bad of [null, undefined, 42, "P.001"]) {
    assert.equal(resultKey(bad, "parlimen"), undefined);
    assert.equal(displayCode(bad, "parlimen"), undefined);
  }
});

// ---- tallyCoalitions: the GE15 invariant (AGENTS.md UNTOUCHABLE) ----
test("tallyCoalitions: GE15 results match the frozen PH82·PN74·BN30·GPS23·GRS6·WARISAN3 = 222 tally", () => {
  const counts = tallyCoalitions(RESULTS);
  assert.equal(counts.PH, 82);
  assert.equal(counts.PN, 74);
  assert.equal(counts.BN, 30);
  assert.equal(counts.GPS, 23);
  assert.equal(counts.GRS, 6);
  assert.equal(counts.WARISAN, 3);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  assert.equal(total, 222);
});

// ---- DUN (PRN) results: the 2023 six-state tally invariant (now a subset) ----
// 3 of the 245 PRN-2023 rows are superseded by later by-elections (Nenggiri,
// Sungai Bakap, Kuala Kubu Baharu) — those carry an `election` label and drop
// out of the unlabelled subset, so it's 242 = 245 - 3 with PN 146→144, PH 80→79.
test("results-dun.json: 2023 six-state PRN subset tally is PN144·PH79·BN19 = 242 (3 by-election overlays)", () => {
  // six-state PRN entries are the ones WITHOUT an `election` label (MECO states + by-elections carry one)
  const prn23 = Object.fromEntries(Object.entries(RESULTS_DUN).filter(([, v]) => !v.election));
  const counts = tallyCoalitions(prn23);
  assert.equal(counts.PN, 144);
  assert.equal(counts.PH, 79);
  assert.equal(counts.BN, 19);
  assert.equal(Object.keys(prn23).length, 242);
  const states = new Set(Object.values(prn23).map((v) => v.state));
  assert.equal(states.size, 6);
});

// ---- DUN (PRN) results: by-election overlays = the CURRENT holder of each seat ----
test("results-dun.json: the 7 by-election overlays hold (incl. Nenggiri PN→BN flip)", () => {
  const byel = Object.entries(RESULTS_DUN).filter(([, v]) => v._byelection);
  assert.deepEqual(
    Object.fromEntries(byel.map(([k, v]) => [k, v.coalition])),
    { "3_N.43": "BN", "7_N.20": "PN", "10_N.06": "PH", "12_N.58": "BN",
      "13_N.67": "GPS", "6_N.36": "BN", "8_N.48": "BN" }
  );
  // every overlay names its poll so the card can cite it (src_byelection line)
  assert.ok(byel.every(([, v]) => /by-election \d{4}$/.test(v.election)));
});

// ---- DUN (PRN) results: full coverage after the MECO other-states bake ----
test("results-dun.json: 544/600 seats across 12 states, 302 election-labelled, turnout null", () => {
  assert.equal(Object.keys(RESULTS_DUN).length, 544);
  const states = new Set(Object.values(RESULTS_DUN).map((v) => v.state));
  assert.equal(states.size, 12);
  // MECO states + by-election overlays carry an `election` label; six-state PRN entries don't
  const withElection = Object.values(RESULTS_DUN).filter((v) => v.election).length;
  assert.equal(withElection, 302);
  // turnout isn't in either source → must be null on every entry (card omits the row)
  assert.ok(Object.values(RESULTS_DUN).every((v) => v.turnout === null));
});

// ---- GE15 results: parliament by-election overlays (current holder doctrine) ----
test("results-ge15.json: 4 by-election overlays, coalition tally unchanged", () => {
  const byel = Object.entries(RESULTS).filter(([, v]) => v._byelection);
  assert.deepEqual(
    Object.fromEntries(byel.map(([k, v]) => [k, v.name])),
    {
      "P.036": "Ahmad Amzad bin Mohamed @ Hashim",        // KT 2023: re-elected after nullification
      "P.040": "Ahmad Samsuri bin Mokhtar",               // Kemaman 2023 (voided GE15 result)
      "P.161": "Suhaizan bin Kaiat",                      // Pulai 2023 (death of Salahuddin Ayub)
      "P.187": "Mohd Kurniawan Naim bin Moktar (Naim Moktar)", // Kinabatangan 2026 (death of Bung Moktar)
    }
  );
  assert.ok(byel.every(([, v]) => /by-election \d{4}$/.test(v.election)));
});

test("results-dun.json: every key matches a real DUN boundary code", () => {
  const dun = JSON.parse(
    readFileSync(fileURLToPath(new URL("./data/seats-dun.json", import.meta.url)), "utf8")
  );
  const valid = new Set(dun.seats.map((s) => s.code));
  for (const key of Object.keys(RESULTS_DUN)) assert.ok(valid.has(key), `orphan DUN result: ${key}`);
});

test("tallyCoalitions: null/non-object/empty input → {} (no throw)", () => {
  for (const bad of [null, undefined, 42, "x", []]) {
    assert.deepEqual(tallyCoalitions(bad), {});
  }
  assert.deepEqual(tallyCoalitions({}), {});
});

test("tallyCoalitions: rows with missing/blank/non-string coalition are skipped", () => {
  const synthetic = {
    a: { coalition: "PH" },
    b: { coalition: "PH" },
    c: { coalition: "" },        // blank → skipped
    d: { coalition: "   " },     // whitespace → skipped
    e: {},                       // missing → skipped
    f: null,                     // null row → skipped
    g: { coalition: 5 },         // non-string → skipped
  };
  assert.deepEqual(tallyCoalitions(synthetic), { PH: 2 });
});

test("stateHues: deterministic + stable — same seats → byte-identical map", () => {
  const seats = [{ state: "Selangor" }, { state: "Johor" }, { state: "Sabah" }];
  const a = stateHues(seats);
  const b = stateHues(seats);
  assert.deepEqual(a, b);                       // stable across calls
  assert.deepEqual(stateHues(SEATS), stateHues(SEATS)); // stable on real data too
});

test("stateHues: distinct states get distinct hues, sorted-unique order", () => {
  const map = stateHues([
    { state: "Johor" }, { state: "Johor" },     // dup folds to one entry
    { state: "Kedah" }, { state: "Perak" },
  ]);
  assert.deepEqual(Object.keys(map), ["Johor", "Kedah", "Perak"]); // sorted, unique
  const hues = Object.values(map);
  assert.equal(new Set(hues).size, hues.length); // all distinct
  for (const v of hues) assert.match(v, /^hsl\(\d+ \d+% \d+%\)$/); // well-formed
});

test("stateHues: golden-angle math matches the formula at index 0..2", () => {
  const map = stateHues([{ state: "AA" }, { state: "BB" }, { state: "CC" }]);
  assert.equal(map.AA, `hsl(0 38% 40%)`);   // i=0: h=0, s=38, l=40
  assert.equal(map.BB, `hsl(138 44% 45%)`); // i=1: h=round(137.508)=138, s=44, l=45
  assert.equal(map.CC, `hsl(275 50% 40%)`); // i=2: h=round(275.016)=275, s=50, l=40
});

test("stateHues: empty / non-array seats → {} (no throw)", () => {
  assert.deepEqual(stateHues([]), {});
  assert.deepEqual(stateHues(null), {});
  assert.deepEqual(stateHues(undefined), {});
  assert.deepEqual(stateHues("nope"), {});
  assert.deepEqual(stateHues(42), {});
});

test("stateHues: a seat with a missing state doesn't crash", () => {
  assert.doesNotThrow(() => stateHues([{ code: "P.001" }, null, { state: "Perak" }]));
  const map = stateHues([{ code: "P.001" }, { state: "Perak" }]);
  assert.ok("Perak" in map); // the well-formed seat still gets a colour
});

test("stateHues: byte-identical to the real-data hue map app.js relied on", () => {
  // sanity: every real state resolves to a well-formed hsl() string
  const map = stateHues(SEATS);
  const states = [...new Set(SEATS.map((s) => s.state))];
  for (const st of states) assert.match(map[st], /^hsl\(\d+ \d+% \d+%\)$/);
});

test("swatchTextColor: chooses readable text for bright and dark party swatches", () => {
  assert.equal(swatchTextColor("#15387c"), "#fff");      // PN blue stays white
  assert.equal(swatchTextColor("#d7263d"), "#fff");      // PH red stays white
  assert.equal(swatchTextColor("#1f9bd6"), "#05070c");   // BN blue fails with white
  assert.equal(swatchTextColor("#e8772e"), "#05070c");   // GRS orange fails with white
  assert.equal(swatchTextColor("#16a085"), "#05070c");   // WARISAN teal fails with white
  assert.equal(swatchTextColor("#8a97a6"), "#05070c");   // BEBAS grey fails with white
});

test("swatchTextColor: accepts short hex and falls back on invalid input", () => {
  assert.equal(swatchTextColor("#fff"), "#05070c");
  assert.equal(swatchTextColor("#000"), "#fff");
  assert.equal(swatchTextColor("not-a-colour"), "#fff");
  assert.equal(swatchTextColor(null), "#fff");
});
