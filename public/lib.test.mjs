// Zero-dependency unit tests for public/lib.js — run with `node --test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { encodeHash, decodeHash } from "./lib.js";

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
