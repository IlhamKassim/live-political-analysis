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
  formatParty, candidateCount, formatRunnerUp, formatResultCard,
} from "./lib.js";

const parlimen = JSON.parse(
  readFileSync(fileURLToPath(new URL("./data/seats-parlimen.json", import.meta.url)), "utf8")
);
const SEATS = parlimen.seats;

const RESULTS = JSON.parse(
  readFileSync(fileURLToPath(new URL("./data/results-ge15.json", import.meta.url)), "utf8")
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
  });
});

test("decodeHash: works without leading #", () => {
  assert.deepEqual(decodeHash("dun/skor"), { tier: "dun", mode: "skor", code: undefined });
});

test("decodeHash: absent trailing segments are undefined (faithful to old parseHash)", () => {
  assert.deepEqual(decodeHash("#parlimen"), { tier: "parlimen", mode: undefined, code: undefined });
});

test("decodeHash: extra path segments are ignored", () => {
  assert.deepEqual(decodeHash("#a/b/c/d/e"), { tier: "a", mode: "b", code: "c" });
});

test("decodeHash: percent-decodes each segment", () => {
  assert.deepEqual(decodeHash("#parlimen/parti/a%20b%2Fc"), {
    tier: "parlimen",
    mode: "parti",
    code: "a b/c",
  });
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
