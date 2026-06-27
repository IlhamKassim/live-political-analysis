// Zero-dependency unit tests for public/lib.js — run with `node --test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  encodeHash, decodeHash,
  project, parsePathRings, pointInRings,
  findSeatForLocation, haversine, nearestSeat,
} from "./lib.js";

const parlimen = JSON.parse(
  readFileSync(fileURLToPath(new URL("./data/seats-parlimen.json", import.meta.url)), "utf8")
);
const SEATS = parlimen.seats;

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
