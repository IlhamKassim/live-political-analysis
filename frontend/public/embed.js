// PolitikKu — standalone embed widget logic.
// Zero dependencies, fast asynchronous data loading.

import { decodeHash, partyColor, swatchTextColor, getRepPhotoUrl, resultKey, displayCode } from "./lib.js";
import { I18N } from "./i18n.js";

function getParams() {
  const hash = decodeHash(window.location.hash);
  const search = new URLSearchParams(window.location.search);

  const tier = search.get("tier") || (hash && hash.tier) || "parlimen";
  const code = search.get("seat") || search.get("code") || (hash && hash.code) || "P.121";
  const lang = search.get("lang") || "ms";

  return { tier: tier === "dun" ? "dun" : "parlimen", code, lang: lang === "en" ? "en" : "ms" };
}

function t(key, lang, params) {
  let s = (I18N[lang] && I18N[lang][key]) ?? I18N.en[key] ?? key;
  if (params) for (const k in params) s = s.split(`{${k}}`).join(params[k]);
  return s;
}

function esc(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function loadData(tier) {
  const seatFile = tier === "dun" ? "data/seats-dun.json" : "data/seats-parlimen.json";
  const resultFile = tier === "dun" ? "data/results-dun.json" : "data/results-ge15.json";
  
  const [seatsData, resultsData, polData] = await Promise.all([
    fetch(seatFile).then((r) => r.json()).catch(() => null),
    fetch(resultFile).then((r) => r.json()).catch(() => null),
    fetch("data/politicians.json").then((r) => r.json()).catch(() => null),
  ]);

  return { seatsData, resultsData, polData };
}

function renderWidget(seat, result, polData, tier, lang) {
  const container = document.getElementById("widget-container");
  if (!container) return;

  const accent = result ? partyColor(result.coalition || result.party) : "#5d6b7d";
  const textCol = swatchTextColor(accent);
  document.documentElement.style.setProperty("--accent", accent);

  const isParlimen = tier === "parlimen";
  const codeStr = displayCode(seat, tier) || seat.code || "";
  const kicker = isParlimen ? `${t("kicker_parlimen", lang)} · ${codeStr}` : `DUN · ${codeStr}`;
  const repPhoto = getRepPhotoUrl(seat, result, polData, null);
  const repName = result ? (result.name || t("rep_ph", lang)) : t("rep_ph", lang);
  const party = result ? (result.coalition || result.party || "") : "";

  // Seat silhouette SVG mini view
  let silhouetteSvg = "";
  if (seat.bbox && seat.d) {
    const { x, y, w, h } = seat.bbox;
    const pad = Math.max(w, h) * 0.1;
    const vb = `${x - pad} ${y - pad} ${w + pad * 2} ${h + pad * 2}`;
    silhouetteSvg = `
      <div class="seat-silhouette-wrap" aria-hidden="true">
        <svg viewBox="${vb}" preserveAspectRatio="xMidYMid meet">
          <path d="${seat.d}" fill="${accent}" fill-opacity="0.85" stroke="#ffffff" stroke-width="${Math.max(w, h) * 0.02}" stroke-opacity="0.6" />
        </svg>
      </div>
    `;
  }

  // Representative photo / avatar
  const avatarHtml = repPhoto
    ? `<img src="${esc(repPhoto)}" alt="${esc(repName)}" loading="lazy" />`
    : `<span>${esc((repName || "YB").slice(0, 2).toUpperCase())}</span>`;

  // Key stats
  const majNum = result && result.majority != null ? Number(result.majority).toLocaleString() : "—";
  const winVotes = result && result.votes != null ? Number(result.votes).toLocaleString() : "—";
  const runnerUp = result && result.runner_up && result.runner_up.name
    ? `${result.runner_up.name} (${result.runner_up.party || ""})`
    : "—";

  const deepLink = `/#${tier}/parti/${encodeURIComponent(seat.code)}`;

  container.innerHTML = `
    <div class="widget-header">
      <div class="seat-meta">
        <span class="seat-badge">${esc(kicker)}</span>
        <h1 class="seat-title">${esc(seat.name || "")}</h1>
        <span class="seat-state">${esc(seat.state || "")}</span>
      </div>
      ${silhouetteSvg}
    </div>

    <div class="rep-row">
      <div class="rep-avatar">
        ${avatarHtml}
      </div>
      <div class="rep-info">
        <span class="rep-kicker">${esc(t("card_current_yb", lang))}</span>
        <span class="rep-name" title="${esc(repName)}">${esc(repName)}</span>
        ${party ? `<span class="party-pill" style="background:${accent};color:${textCol};">${esc(party)}</span>` : ""}
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-box">
        <div class="stat-label">${esc(t("majority", lang))}</div>
        <div class="stat-val">${esc(majNum)}</div>
      </div>
      <div class="stat-box">
        <div class="stat-label">${esc(t("runner", lang))}</div>
        <div class="stat-val" style="font-size:12px;font-family:var(--font-sans);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${esc(runnerUp)}">${esc(runnerUp)}</div>
      </div>
    </div>

    <div class="widget-footer">
      <a href="${deepLink}" target="_blank" rel="noopener noreferrer" class="brand-link">
        <span class="brand-mark"></span>
        <span>PolitikKu</span>
      </a>
      <a href="${deepLink}" target="_blank" rel="noopener noreferrer" class="cta-btn">
        <span>${esc(t("embed_explore_cta", lang))}</span>
      </a>
    </div>
  `;
}

async function init() {
  const container = document.getElementById("widget-container");
  const { tier, code, lang } = getParams();

  try {
    const { seatsData, resultsData, polData } = await loadData(tier);
    if (!seatsData || !seatsData.seats) {
      if (container) container.innerHTML = `<div class="error-state">Could not load electoral data.</div>`;
      return;
    }

    const targetCode = code.toUpperCase();
    const seat = seatsData.seats.find((s) =>
      (s.code && s.code.toUpperCase() === targetCode) ||
      (s.dun_code && s.dun_code.toUpperCase() === targetCode) ||
      (s.name && s.name.toUpperCase() === targetCode)
    ) || seatsData.seats[0];

    if (!seat) {
      if (container) container.innerHTML = `<div class="error-state">Seat not found.</div>`;
      return;
    }

    const rKey = resultKey(seat, tier);
    const result = resultsData ? resultsData[rKey] : null;

    renderWidget(seat, result, polData, tier, lang);
  } catch (err) {
    if (container) container.innerHTML = `<div class="error-state">Error loading widget.</div>`;
  }
}

window.addEventListener("DOMContentLoaded", init);
window.addEventListener("hashchange", init);
