import {
  buildHemicycleSVG,
  COALITION_COLORS,
  partyColor,
  trustTagHTML,
} from "./lib.js";
import { buildNarrative, swingModel } from "./lib-swing.js";

const DATA_BASE = "/analyst/data/";

let baseline = [];
let modelConfig = null;
let stateSignals = [];
let currentInputs = null;
let articlesPayload = null;
let baselineProjection = null;

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

function readSliders() {
  const sensitivity = Number(document.getElementById("sensitivity").value);
  const signalWeight = Number(document.getElementById("signal-weight").value);
  const sentiment = {};
  for (const coalition of coalitionOrder) {
    const el = document.getElementById(`sentiment-${coalition}`);
    if (!el || !currentInputs?.scores?.[coalition]) continue;
    const base = currentInputs.scores[coalition];
    const offset = Number(el.value);
    sentiment[coalition] = base + offset;
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

function renderSandbox(projection, narrative) {
  const totalsEl = document.getElementById("sandbox-totals");
  const hemicycleEl = document.getElementById("sandbox-hemicycle");
  const tableEl = document.getElementById("sandbox-seats");
  const narrativeEl = document.getElementById("sandbox-narrative");

  const totals = projection.coalition_seat_totals;
  const rows = coalitionOrder
    .filter((c) => totals[c] !== undefined)
    .map(
      (c) =>
        `<div class="dewan-tile"><span>${c}</span><strong>${trustTagHTML("MODEL", totals[c] || 0)}</strong></div>`,
    )
    .join("");
  const govTotal = (modelConfig.government_coalitions || []).reduce(
    (sum, c) => sum + (totals[c] || 0),
    0,
  );
  totalsEl.innerHTML =
    rows +
    `<div class="dewan-tile"><span>Government</span><strong>${trustTagHTML("MODEL", `${govTotal} / ${modelConfig.majority_threshold}+`)}</strong></div>`;

  const seatRows = projection.seat_calls.map((call) => {
    const seat = baseline.find((s) => s.code === call.code) || {};
    const baseCall = baselineProjection.seat_calls.find((c) => c.code === call.code);
    const flipped = baseCall && baseCall.coalition !== call.coalition;
    return `<tr class="dewan-tr${flipped ? " row-changed" : ""}"><td>${call.code}</td><td>${seat.state || ""}</td><td>${baseCall?.coalition || ""}</td><td style="color:${partyColor(call.coalition)}">${call.coalition}</td><td>${(call.margin * 100).toFixed(1)}pp</td></tr>`;
  });
  tableEl.innerHTML = seatRows.join("");

  const hemSeats = projection.seat_calls.map((call) => {
    const seat = baseline.find((s) => s.code === call.code) || {};
    return { ...call, name: seat.name, state: seat.state };
  });
  hemicycleEl.innerHTML = buildHemicycleSVG(hemSeats, {
    governmentCoalitions: modelConfig.government_coalitions,
  });
  narrativeEl.textContent = narrative;
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
  renderSandbox(projection, narrative);
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
          if (id.startsWith("sentiment-")) {
            const base = currentInputs.scores[id.replace("sentiment-", "")] || 0;
            out.textContent = fmtScore(base + Number(el.value));
          } else {
            out.textContent = Number(el.value).toFixed(2);
          }
        }
        updateSandbox();
      });
    },
  );
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
      Number(configData.sentiment_sensitivity).toFixed(2);
    document.getElementById("signal-weight-value").textContent =
      Number(configData.state_signal_weight).toFixed(2);

    for (const coalition of coalitionOrder) {
      const wrap = document.getElementById(`sentiment-wrap-${coalition}`);
      if (!wrap || inputsData.scores[coalition] === undefined) {
        if (wrap) wrap.hidden = true;
        continue;
      }
      wrap.hidden = false;
      document.getElementById(`sentiment-${coalition}-base`).textContent = fmtScore(
        inputsData.scores[coalition],
      );
    }

    baselineProjection = swingModel(
      baseline,
      inputsData.scores,
      stateSignals,
      configData,
      inputsData.computed_at,
    );

    wireSliders();
    updateSandbox();
    renderCoalitionPicker();
    document.getElementById("download-bundle")?.addEventListener("click", downloadBundle);
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
