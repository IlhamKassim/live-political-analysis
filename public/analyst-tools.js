import {
  buildHemicycleSVG,
  partyColor,
  trustTagHTML,
} from "./lib.js";
import {
  buildNarrative,
  flippedSeats,
  formatPercentShare,
  sandboxRunCsv,
  sandboxRunExport,
  swingModel,
} from "./lib-swing.js";

const DATA_BASE = "/analyst/data/";

let baseline = [];
let modelConfig = null;
let stateSignals = [];
let currentInputs = null;
let articlesPayload = null;
let baselineProjection = null;
let lastRun = null;
let showAllSeats = false;
let stateFilter = "";

const coalitionOrder = ["PH", "BN", "PN", "GPS", "GRS"];

async function loadJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

function fmtScore(value) {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Number(value).toFixed(2)}`;
}

function fmtDelta(value) {
  if (value === null || value === undefined) return "";
  const sign = value > 0 ? "↑" : value < 0 ? "↓" : "→";
  return `${sign}${Math.abs(value).toFixed(2)}`;
}

function fmtPp(share) {
  if (share === null || share === undefined || Number.isNaN(Number(share))) return "—";
  return `${(Number(share) * 100).toFixed(1)}pp`;
}

function fmtPct(share) {
  return formatPercentShare(share);
}

function readSliders() {
  const sensitivity = Number(document.getElementById("sensitivity").value);
  const signalWeight = Number(document.getElementById("signal-weight").value);
  const sentiment = {};
  for (const coalition of coalitionOrder) {
    const el = document.getElementById(`sentiment-${coalition}`);
    if (!el || currentInputs?.scores?.[coalition] === undefined) continue;
    sentiment[coalition] = currentInputs.scores[coalition] + Number(el.value);
  }
  for (const [coalition, score] of Object.entries(currentInputs?.scores || {})) {
    if (sentiment[coalition] === undefined) sentiment[coalition] = score;
  }
  return {
    sentiment_sensitivity: sensitivity,
    state_signal_weight: signalWeight,
    sentiment,
  };
}

function coalitionLine(totals) {
  return coalitionOrder
    .filter((c) => totals[c] !== undefined)
    .map((c) => `${c} ${totals[c] || 0}`)
    .join(" · ");
}

function renderCompare(official, adjusted, config) {
  const el = document.getElementById("sandbox-compare");
  const govOfficial = (config.government_coalitions || []).reduce(
    (sum, c) => sum + (official.coalition_seat_totals[c] || 0),
    0,
  );
  const govAdjusted = (config.government_coalitions || []).reduce(
    (sum, c) => sum + (adjusted.coalition_seat_totals[c] || 0),
    0,
  );
  el.innerHTML = `
    <div class="compare-card"><span>Today (official)</span><strong>${trustTagHTML("MODEL", `${govOfficial} / ${config.majority_threshold}+`)}</strong><p>${coalitionLine(official.coalition_seat_totals)}</p></div>
    <div class="compare-card"><span>This what-if</span><strong>${trustTagHTML("MODEL", `${govAdjusted} / ${config.majority_threshold}+`)}</strong><p>${coalitionLine(adjusted.coalition_seat_totals)}</p></div>
  `;
}

function renderSeatTable(projection) {
  const tableEl = document.getElementById("sandbox-seats");
  const countEl = document.getElementById("flip-count");
  const flips = flippedSeats(baselineProjection, projection, baseline);
  const officialByCode = Object.fromEntries(
    baselineProjection.seat_calls.map((call) => [call.code, call]),
  );

  let rows = showAllSeats
    ? projection.seat_calls.map((call) => {
        const seat = baseline.find((s) => s.code === call.code) || {};
        const today = officialByCode[call.code];
        const flipped = today && today.coalition !== call.coalition;
        return {
          call,
          seat,
          today,
          flipped,
          sortMargin: call.margin,
        };
      })
    : flips.map((flip) => ({
        call: { code: flip.code, coalition: flip.to, margin: flip.to_margin },
        seat: baseline.find((s) => s.code === flip.code) || {},
        today: { coalition: flip.from, margin: flip.from_margin },
        flipped: true,
        sortMargin: flip.to_margin,
      }));

  if (stateFilter) {
    rows = rows.filter((row) => row.seat.state === stateFilter);
  }
  rows.sort((a, b) => Math.abs(a.sortMargin) - Math.abs(b.sortMargin));

  countEl.textContent = showAllSeats
    ? `${rows.length} Seats shown · ${flips.length} flipped vs today`
    : flips.length
      ? `${rows.length} flipped Seat${rows.length === 1 ? "" : "s"} (closest first)`
      : "No Seats change under these assumptions";

  tableEl.innerHTML = rows
    .map((row) => {
      const bumi = row.seat.demographics?.ethnicity_proportion_bumi;
      return `<tr class="${row.flipped ? "row-changed" : ""}">
        <td><span class="seat-code">${row.call.code}</span><span class="seat-name">${row.seat.name || ""}</span></td>
        <td>${row.seat.state || ""}</td>
        <td>${row.seat.winner || ""} ${fmtPp(row.seat.margin)}</td>
        <td>${fmtPct(bumi)}</td>
        <td style="color:${partyColor(row.today?.coalition)}">${row.today?.coalition || ""}</td>
        <td style="color:${partyColor(row.call.coalition)}">${row.call.coalition}</td>
        <td>${fmtPp(row.call.margin)}</td>
      </tr>`;
    })
    .join("");
}

function fillStateFilter() {
  const select = document.getElementById("state-filter");
  const states = [...new Set(baseline.map((seat) => seat.state))].sort();
  select.innerHTML =
    `<option value="">All states</option>` +
    states.map((state) => `<option value="${state}">${state}</option>`).join("");
}

function renderSandbox(projection, narrative, sliders) {
  const hemicycleEl = document.getElementById("sandbox-hemicycle");
  const narrativeEl = document.getElementById("sandbox-narrative");
  renderCompare(baselineProjection, projection, {
    ...modelConfig,
    sentiment_sensitivity: sliders.sentiment_sensitivity,
    state_signal_weight: sliders.state_signal_weight,
  });
  narrativeEl.textContent = narrative;
  renderSeatTable(projection);

  const hemSeats = projection.seat_calls.map((call) => {
    const seat = baseline.find((s) => s.code === call.code) || {};
    return { ...call, name: seat.name, state: seat.state };
  });
  hemicycleEl.innerHTML = buildHemicycleSVG(hemSeats, {
    governmentCoalitions: modelConfig.government_coalitions,
  });

  lastRun = {
    projection,
    narrative,
    sliders,
  };
}

function updateSandbox() {
  const { sentiment_sensitivity, state_signal_weight, sentiment } = readSliders();
  const config = {
    ...modelConfig,
    sentiment_sensitivity,
    state_signal_weight,
  };
  const projection = swingModel(
    baseline,
    sentiment,
    stateSignals,
    config,
    currentInputs.computed_at,
  );
  const narrative = buildNarrative(baselineProjection, projection, baseline, config);
  renderSandbox(projection, narrative, {
    sentiment_sensitivity,
    state_signal_weight,
    sentiment,
  });
}

function renderCoalitionPicker() {
  const picker = document.getElementById("trace-coalitions");
  if (!articlesPayload) return;
  picker.innerHTML = coalitionOrder
    .filter((c) => currentInputs?.scores?.[c] !== undefined)
    .map(
      (c, i) =>
        `<button type="button" class="filter-chip${i === 0 ? " on" : ""}" data-coalition="${c}">${c} ${fmtScore(currentInputs.scores[c])} ${fmtDelta(articlesPayload.coalition_deltas?.[c])}</button>`,
    )
    .join("");
  picker.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      picker.querySelectorAll("button").forEach((b) => b.classList.remove("on"));
      btn.classList.add("on");
      renderArticleTable(btn.dataset.coalition);
    });
  });
  const first = picker.querySelector("button");
  if (first) renderArticleTable(first.dataset.coalition);
}

function renderArticleTable(coalition) {
  const table = document.getElementById("trace-articles");
  const summary = document.getElementById("trace-summary");
  const articles = (articlesPayload?.articles || [])
    .filter((a) => a.scores && a.scores[coalition] !== undefined)
    .sort((a, b) => Math.abs(b.scores[coalition]) - Math.abs(a.scores[coalition]));

  table.innerHTML = articles
    .map(
      (a) =>
        `<tr class="dewan-tr"><td><a href="${a.url}" target="_blank" rel="noopener">${a.title}</a></td><td>${a.source}</td><td>${fmtScore(a.scores[coalition])}</td><td>${(a.topics || []).join(", ") || "—"}</td></tr>`,
    )
    .join("");

  const delta = articlesPayload?.coalition_deltas?.[coalition];
  const top = articles.slice(0, 3);
  const outlets = new Set(top.map((a) => a.source));
  summary.textContent =
    top.length === 0
      ? `No articles scored ${coalition} today.`
      : `${coalition}'s score is ${fmtScore(currentInputs.scores[coalition])}${delta != null ? ` (${fmtDelta(delta)} vs yesterday)` : ""}. Top sources: ${top.map((a) => `"${a.title}" (${a.source})`).join("; ")}. Outlets represented: ${outlets.size}.`;
}

function wireSliders() {
  ["sensitivity", "signal-weight", ...coalitionOrder.map((c) => `sentiment-${c}`)].forEach(
    (id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("input", () => {
        const out = document.getElementById(`${id}-value`);
        if (out) {
          if (id === "sensitivity") {
            out.textContent = `${Math.round(Number(el.value) * 100)}%`;
          } else if (id === "signal-weight") {
            out.textContent = `${Math.round(Number(el.value) * 100)}%`;
          } else {
            const base = currentInputs.scores[id.replace("sentiment-", "")] || 0;
            out.textContent = fmtScore(base + Number(el.value));
          }
        }
        updateSandbox();
      });
    },
  );
  document.getElementById("show-all-seats")?.addEventListener("change", (event) => {
    showAllSeats = event.target.checked;
    if (lastRun) renderSeatTable(lastRun.projection);
  });
  document.getElementById("state-filter")?.addEventListener("change", (event) => {
    stateFilter = event.target.value;
    if (lastRun) renderSeatTable(lastRun.projection);
  });
}

function downloadText(filename, body, type) {
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadThisRun() {
  if (!lastRun) return;
  const payload = sandboxRunExport({
    officialProjection: baselineProjection,
    adjustedProjection: lastRun.projection,
    baseline,
    config: {
      ...modelConfig,
      sentiment_sensitivity: lastRun.sliders.sentiment_sensitivity,
      state_signal_weight: lastRun.sliders.state_signal_weight,
    },
    sliders: {
      sentiment_sensitivity: lastRun.sliders.sentiment_sensitivity,
      state_signal_weight: lastRun.sliders.state_signal_weight,
    },
    todaySentiment: currentInputs.scores,
    adjustedSentiment: lastRun.sliders.sentiment,
    computedAt: currentInputs.computed_at,
    narrative: lastRun.narrative,
  });
  const stamp = currentInputs.computed_at || "run";
  downloadText(`politikku-sandbox-${stamp}.json`, JSON.stringify(payload, null, 2) + "\n", "application/json");
  downloadText(`politikku-sandbox-${stamp}.csv`, sandboxRunCsv(payload), "text/csv");
}

async function downloadBundle() {
  const res = await fetch(`${DATA_BASE}analyst-bundle.zip`, { cache: "no-store" });
  if (!res.ok) {
    alert("Bundle not available yet. Run the release export to generate it.");
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `politikku-analyst-${currentInputs?.computed_at || "bundle"}.zip`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function initAnalystWorkbench() {
  try {
    const [baselineData, configData, signalsData, inputsData, articlesData] = await Promise.all([
      loadJSON(`${DATA_BASE}baseline.json`),
      loadJSON(`${DATA_BASE}model_config.json`),
      loadJSON(`${DATA_BASE}state_signals.json`),
      loadJSON(`${DATA_BASE}current_inputs.json`),
      loadJSON(`${DATA_BASE}articles.json`).catch(() => ({ articles: [], coalition_deltas: {} })),
    ]);
    baseline = baselineData.seats;
    modelConfig = configData;
    stateSignals = signalsData.signals || [];
    currentInputs = inputsData;
    articlesPayload = articlesData;

    document.getElementById("run-date").textContent = inputsData.computed_at;
    document.getElementById("sensitivity").value = configData.sentiment_sensitivity;
    document.getElementById("signal-weight").value = configData.state_signal_weight;
    document.getElementById("sensitivity-value").textContent =
      `${Math.round(Number(configData.sentiment_sensitivity) * 100)}%`;
    document.getElementById("signal-weight-value").textContent =
      `${Math.round(Number(configData.state_signal_weight) * 100)}%`;

    for (const coalition of coalitionOrder) {
      const wrap = document.getElementById(`sentiment-wrap-${coalition}`);
      if (!wrap || inputsData.scores[coalition] === undefined) {
        if (wrap) wrap.hidden = true;
        continue;
      }
      wrap.hidden = false;
      const baseEl = document.getElementById(`sentiment-${coalition}-base`);
      if (baseEl) baseEl.textContent = fmtScore(inputsData.scores[coalition]);
      const valueEl = document.getElementById(`sentiment-${coalition}-value`);
      if (valueEl) valueEl.textContent = fmtScore(inputsData.scores[coalition]);
    }

    baselineProjection = swingModel(
      baseline,
      inputsData.scores,
      stateSignals,
      configData,
      inputsData.computed_at,
    );

    fillStateFilter();
    wireSliders();
    updateSandbox();
    renderCoalitionPicker();
    document.getElementById("download-bundle")?.addEventListener("click", downloadBundle);
    document.getElementById("download-run")?.addEventListener("click", downloadThisRun);
  } catch (err) {
    document.getElementById("workbench-error").hidden = false;
    document.getElementById("workbench-error").textContent =
      `Could not load analyst data: ${err.message}. Run the pipeline and release export locally.`;
    console.error(err);
  }
}

if (document.body.classList.contains("analyst-workbench")) {
  initAnalystWorkbench();
}
