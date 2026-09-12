// PolitikKu — client-side Swing Model (mirrors src/lpa/swing_model.py).
// Pure functions only — no DOM, no fetch.

export function leadingCoalition(voteShare, tieBreak = null) {
  const entries = Object.entries(voteShare || {});
  if (!entries.length) return tieBreak || "";
  const lead = Math.max(...entries.map(([, share]) => share));
  const tied = entries
    .filter(([, share]) => share === lead)
    .map(([coalition]) => coalition)
    .sort();
  if (tieBreak && tied.includes(tieBreak)) return tieBreak;
  return tied[0];
}

export function governmentSeatTotal(totals, config) {
  const gov = config.government_coalitions || [];
  return gov.reduce((sum, coalition) => sum + (totals[coalition] || 0), 0);
}

export function observedStateSwings(baseline, stateElectionSignals) {
  const baselineByState = {};
  for (const seat of baseline) {
    if (!baselineByState[seat.state]) baselineByState[seat.state] = [];
    baselineByState[seat.state].push(seat);
  }

  const collected = {};
  for (const signal of stateElectionSignals || []) {
    const stateSeats = baselineByState[signal.state];
    if (!stateSeats) continue;
    for (const [coalition, share] of Object.entries(signal.vote_share || {})) {
      const baselineShare =
        stateSeats.reduce((sum, seat) => sum + (seat.vote_share[coalition] || 0), 0) /
        stateSeats.length;
      if (!collected[signal.state]) collected[signal.state] = {};
      if (!collected[signal.state][coalition]) collected[signal.state][coalition] = [];
      collected[signal.state][coalition].push(share - baselineShare);
    }
  }

  const observed = {};
  for (const [state, byCoalition] of Object.entries(collected)) {
    observed[state] = {};
    for (const [coalition, values] of Object.entries(byCoalition)) {
      observed[state][coalition] = values.reduce((a, b) => a + b, 0) / values.length;
    }
  }
  return observed;
}

export function stateSwing(baseline, sentiment, stateElectionSignals, config) {
  const sentimentSwing = {};
  for (const [coalition, score] of Object.entries(sentiment || {})) {
    sentimentSwing[coalition] = score * config.sentiment_sensitivity;
  }
  const observed = observedStateSwings(baseline, stateElectionSignals);
  const weight = config.state_signal_weight;
  const states = [...new Set(baseline.map((seat) => seat.state))];
  const swings = {};

  for (const state of states) {
    const observedSwing = observed[state];
    if (!observedSwing) {
      swings[state] = { ...sentimentSwing };
      continue;
    }
    const coalitions = new Set([
      ...Object.keys(sentimentSwing),
      ...Object.keys(observedSwing),
    ]);
    swings[state] = {};
    for (const coalition of coalitions) {
      swings[state][coalition] =
        (1 - weight) * (sentimentSwing[coalition] || 0) +
        weight * (observedSwing[coalition] || 0);
    }
  }
  return swings;
}

export function projectedShares(seat, swing) {
  const floored = {};
  for (const [coalition, share] of Object.entries(seat.vote_share || {})) {
    floored[coalition] = Math.max(0, share + (swing[coalition] || 0));
  }
  const total = Object.values(floored).reduce((a, b) => a + b, 0);
  if (total === 0) return floored;
  const baselineTotal = Object.values(seat.vote_share || {}).reduce((a, b) => a + b, 0);
  const scale = baselineTotal / total;
  const scaled = {};
  for (const [coalition, share] of Object.entries(floored)) {
    scaled[coalition] = share * scale;
  }
  return scaled;
}

export function callSeat(seat, swing) {
  const projected = projectedShares(seat, swing);
  const coalition = leadingCoalition(projected, seat.winner);
  const runnerUp = Math.max(
    ...Object.entries(projected)
      .filter(([c]) => c !== coalition)
      .map(([, share]) => share),
    0,
  );
  return {
    code: seat.code,
    coalition,
    margin: projected[coalition] - runnerUp,
  };
}

export function swingModel(
  baseline,
  sentiment,
  stateElectionSignals,
  config,
  computedAt,
) {
  const swingByState = stateSwing(baseline, sentiment, stateElectionSignals, config);
  const calls = baseline.map((seat) => callSeat(seat, swingByState[seat.state] || {}));

  const totals = {};
  for (const seat of baseline) {
    for (const coalition of Object.keys(seat.vote_share || {})) {
      if (totals[coalition] === undefined) totals[coalition] = 0;
    }
  }
  for (const call of calls) {
    totals[call.coalition] = (totals[call.coalition] || 0) + 1;
  }

  const govSeats = governmentSeatTotal(totals, config);
  return {
    coalition_seat_totals: totals,
    government_majority: govSeats >= config.majority_threshold,
    computed_at: computedAt,
    seat_calls: calls,
  };
}

export function flippedSeats(officialProjection, adjustedProjection, baseline) {
  const officialByCode = Object.fromEntries(
    (officialProjection.seat_calls || []).map((call) => [call.code, call]),
  );
  const seatByCode = Object.fromEntries((baseline || []).map((seat) => [seat.code, seat]));
  const flips = [];

  for (const call of adjustedProjection.seat_calls || []) {
    const prior = officialByCode[call.code];
    if (!prior || prior.coalition === call.coalition) continue;
    const seat = seatByCode[call.code] || {};
    flips.push({
      code: call.code,
      name: seat.name || call.code,
      state: seat.state || "",
      ge15_winner: seat.winner || "",
      ge15_margin: seat.margin ?? null,
      bumi_share: seat.demographics?.ethnicity_proportion_bumi ?? null,
      from: prior.coalition,
      from_margin: prior.margin,
      to: call.coalition,
      to_margin: call.margin,
    });
  }

  flips.sort((a, b) => Math.abs(a.to_margin) - Math.abs(b.to_margin));
  return flips;
}

export function buildNarrative(baselineProjection, adjustedProjection, baseline, config) {
  const changes = flippedSeats(baselineProjection, adjustedProjection, baseline);
  const stateCounts = {};
  for (const change of changes) {
    stateCounts[change.state] = (stateCounts[change.state] || 0) + 1;
  }

  const govBefore = governmentSeatTotal(baselineProjection.coalition_seat_totals, config);
  const govAfter = governmentSeatTotal(adjustedProjection.coalition_seat_totals, config);
  const majorityLine = config.majority_threshold;
  const majoritySide = govAfter >= majorityLine ? "above" : "below";

  if (!changes.length) {
    return `No Seat calls change under these assumptions. The Government Coalition holds ${govAfter} Seats, ${majoritySide} the ${majorityLine}-Seat Majority line. This is a direction, not a forecast.`;
  }

  const topStates = Object.entries(stateCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([state, count]) => `${count} in ${state || "unknown"}`)
    .join(", ");

  const majorityNote =
    govBefore === govAfter
      ? `The Government Coalition stays at ${govAfter} Seats, ${majoritySide} the ${majorityLine}-Seat Majority line.`
      : `The Government Coalition moves from ${govBefore} to ${govAfter} Seats, now ${majoritySide} the ${majorityLine}-Seat Majority line.`;

  return `${changes.length} Seat${changes.length === 1 ? "" : "s"} change coalition — mostly ${topStates}. ${majorityNote} This is a direction, not a forecast.`;
}

export function formatPercentShare(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  // Census ethnicity shares are 0–100; vote shares are 0–1.
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return `${pct.toFixed(1)}%`;
}

export const SANDBOX_CAVEAT =
  "Two constants in the Swing Model were set by judgement, not fitted to data. Treat every figure here as a direction, not a forecast. Every Seat's call is arithmetic against its GE15 result under a state-uniform swing, never a bespoke judgement about that constituency.";

export const BASELINE_SOURCE = {
  kind: "FACT",
  name: "Malaysian Election Corpus (MECo)",
  publisher: "ElectionData.MY / Thevesh Thevananthan",
  url: "https://electiondata.my/",
  citation:
    "Thevananthan, T. (2025). The Malaysian Election Corpus (MECo): Federal and State-Level Election Results from 1955 to 2025. Scientific Data. https://doi.org/10.1038/s41597-025-06502-7",
};

export function sandboxRunExport({
  officialProjection,
  adjustedProjection,
  baseline,
  config,
  sliders,
  todaySentiment,
  adjustedSentiment,
  computedAt,
  narrative,
}) {
  const flips = flippedSeats(officialProjection, adjustedProjection, baseline);
  const govOfficial = governmentSeatTotal(officialProjection.coalition_seat_totals, config);
  const govAdjusted = governmentSeatTotal(adjustedProjection.coalition_seat_totals, config);
  return {
    schema_version: 1,
    kind: "MODEL",
    description: "One Analyst sandbox what-if run. Slider changes stay local; they do not change production settings.",
    computed_at: computedAt,
    methodology_url: "https://politikku.my/methodology.html",
    baseline_source: BASELINE_SOURCE,
    caveat: SANDBOX_CAVEAT,
    sliders: sliders || {},
    today_sentiment: todaySentiment || {},
    adjusted_sentiment: adjustedSentiment || {},
    official_totals: { ...officialProjection.coalition_seat_totals },
    adjusted_totals: { ...adjustedProjection.coalition_seat_totals },
    official_government_seats: govOfficial,
    adjusted_government_seats: govAdjusted,
    majority_threshold: config.majority_threshold,
    official_government_majority: officialProjection.government_majority,
    adjusted_government_majority: adjustedProjection.government_majority,
    flipped_seats: flips,
    narrative,
  };
}

export function sandboxRunCsv(payload) {
  const header = "code,name,state,ge15_winner,ge15_margin,from,to,to_margin";
  const rows = (payload.flipped_seats || []).map((seat) =>
    [
      seat.code,
      csvCell(seat.name),
      csvCell(seat.state),
      seat.ge15_winner,
      seat.ge15_margin ?? "",
      seat.from,
      seat.to,
      seat.to_margin ?? "",
    ].join(","),
  );
  return [header, ...rows].join("\n") + "\n";
}

function csvCell(value) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}
