import assert from "node:assert/strict";
import test from "node:test";

import {
  buildNarrative,
  flippedSeats,
  formatPercentShare,
  governmentSeatTotal,
  sandboxRunCsv,
  sandboxRunExport,
  stateSwing,
  swingModel,
} from "./lib-swing.js";

const PH = "PH";
const PN = "PN";

function seat(code, state, voteShare) {
  const entries = Object.entries(voteShare);
  const winner = entries.reduce((best, [c, s]) => (s > best[1] ? [c, s] : best), entries[0])[0];
  const sorted = entries.map(([, s]) => s).sort((a, b) => b - a);
  return {
    code,
    name: code,
    state,
    vote_share: voteShare,
    margin: sorted[0] - (sorted[1] || 0),
    winner,
  };
}

function twoCoalitionSeats() {
  return [
    seat("P001", "Selangor", { PH: 0.60, PN: 0.40 }),
    seat("P002", "Selangor", { PH: 0.55, PN: 0.45 }),
    seat("P003", "Selangor", { PH: 0.53, PN: 0.47 }),
    seat("P004", "Selangor", { PH: 0.52, PN: 0.48 }),
    seat("P005", "Selangor", { PH: 0.45, PN: 0.55 }),
    seat("P006", "Selangor", { PH: 0.35, PN: 0.65 }),
  ];
}

function governmentConfig(overrides = {}) {
  return {
    government_coalitions: ["PH"],
    majority_threshold: 4,
    sentiment_sensitivity: 0.10,
    state_signal_weight: 0.5,
    ...overrides,
  };
}

test("neutral sentiment reproduces the baseline", () => {
  const projection = swingModel(
    twoCoalitionSeats(),
    { PH: 0.0, PN: 0.0 },
    [],
    governmentConfig(),
    "2026-08-06",
  );
  assert.deepEqual(projection.coalition_seat_totals, { PH: 4, PN: 2 });
  assert.equal(projection.government_majority, true);
});

test("sentiment against the government flips marginal seats", () => {
  const projection = swingModel(
    twoCoalitionSeats(),
    { PH: -0.4, PN: 0.4 },
    [],
    governmentConfig(),
    "2026-08-06",
  );
  assert.deepEqual(projection.coalition_seat_totals, { PH: 2, PN: 4 });
  assert.equal(projection.government_majority, false);
});

test("state election signal deepens the swing", () => {
  const projection = swingModel(
    twoCoalitionSeats(),
    { PH: -0.4, PN: 0.4 },
    [{ state: "Selangor", held_on: "2026-03-01", vote_share: { PH: 0.42, PN: 0.58 } }],
    governmentConfig(),
    "2026-08-06",
  );
  assert.deepEqual(projection.coalition_seat_totals, { PH: 1, PN: 5 });
});

test("stateSwing matches sentiment-only states", () => {
  const swings = stateSwing(twoCoalitionSeats(), { PH: -0.4, PN: 0.4 }, [], governmentConfig());
  assert.ok(Math.abs(swings.Selangor.PH + 0.04) < 1e-9);
  assert.ok(Math.abs(swings.Selangor.PN - 0.04) < 1e-9);
});

test("governmentSeatTotal counts configured coalitions", () => {
  const totals = { PH: 5, BN: 2, PN: 3 };
  assert.equal(governmentSeatTotal(totals, { government_coalitions: ["PH", "BN"] }), 7);
});

test("flippedSeats lists only seats that change coalition, closest first", () => {
  const seats = twoCoalitionSeats();
  const official = swingModel(seats, { PH: 0, PN: 0 }, [], governmentConfig(), "2026-08-06");
  const adjusted = swingModel(seats, { PH: -0.4, PN: 0.4 }, [], governmentConfig(), "2026-08-06");
  const flips = flippedSeats(official, adjusted, seats);
  assert.equal(flips.length, 2);
  assert.deepEqual(flips.map((row) => row.code), ["P003", "P004"]);
  assert.equal(flips[0].from, PH);
  assert.equal(flips[0].to, PN);
});

test("narrative names zero flips without inventing movement", () => {
  const seats = twoCoalitionSeats();
  const projection = swingModel(seats, { PH: 0, PN: 0 }, [], governmentConfig(), "2026-08-06");
  const text = buildNarrative(projection, projection, seats, governmentConfig());
  assert.match(text, /No Seat calls change/);
});

test("sandboxRunExport is a citable MODEL payload with FACT baseline source", () => {
  const seats = twoCoalitionSeats();
  const official = swingModel(seats, { PH: 0, PN: 0 }, [], governmentConfig(), "2026-08-06");
  const adjusted = swingModel(seats, { PH: -0.4, PN: 0.4 }, [], governmentConfig(), "2026-08-06");
  const payload = sandboxRunExport({
    officialProjection: official,
    adjustedProjection: adjusted,
    baseline: seats,
    config: governmentConfig(),
    sliders: { sentiment_sensitivity: 0.1, state_signal_weight: 0.5 },
    todaySentiment: { PH: 0, PN: 0 },
    adjustedSentiment: { PH: -0.4, PN: 0.4 },
    computedAt: "2026-08-06",
    narrative: "test",
  });
  assert.equal(payload.kind, "MODEL");
  assert.equal(payload.baseline_source.kind, "FACT");
  assert.equal(payload.flipped_seats.length, 2);
  assert.ok(payload.caveat);
  const csv = sandboxRunCsv(payload);
  assert.match(csv, /P003/);
});

test("formatPercentShare keeps census percents and scales fractions", () => {
  assert.equal(formatPercentShare(89.8), "89.8%");
  assert.equal(formatPercentShare(0.898), "89.8%");
  assert.equal(formatPercentShare(null), "—");
});
