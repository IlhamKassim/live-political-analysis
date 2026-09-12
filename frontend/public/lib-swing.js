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

export function buildNarrative(baselineProjection, adjustedProjection, baseline, config) {
  const changes = [];
  const baselineByCode = Object.fromEntries(
    baselineProjection.seat_calls.map((call) => [call.code, call]),
  );
  const stateCounts = {};

  for (const call of adjustedProjection.seat_calls) {
    const prior = baselineByCode[call.code];
    if (!prior || prior.coalition === call.coalition) continue;
    const seat = baseline.find((s) => s.code === call.code);
    const state = seat ? seat.state : "unknown";
    stateCounts[state] = (stateCounts[state] || 0) + 1;
    changes.push({ code: call.code, from: prior.coalition, to: call.coalition, state });
  }

  const govBefore = governmentSeatTotal(baselineProjection.coalition_seat_totals, config);
  const govAfter = governmentSeatTotal(adjustedProjection.coalition_seat_totals, config);
  const majorityLine = config.majority_threshold;

  if (!changes.length) {
    return `No Seat calls change under these assumptions. Government Coalition holds ${govAfter} Seats (${govAfter >= majorityLine ? "above" : "below"} the ${majorityLine}-Seat Majority line).`;
  }

  const topStates = Object.entries(stateCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([state, count]) => `${count} in ${state}`)
    .join(", ");

  const majorityNote =
    govBefore === govAfter
      ? `Government Coalition total unchanged at ${govAfter} Seats.`
      : `Government Coalition moves from ${govBefore} to ${govAfter} Seats.`;

  return `${changes.length} Seat${changes.length === 1 ? "" : "s"} change coalition — mostly ${topStates}. ${majorityNote} Treat this as direction, not a forecast.`;
}
