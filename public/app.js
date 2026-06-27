// MyPolitik — interactive map of Malaysia's electoral seats.
// Data-driven: boundaries render now; GE15 results + scores light up the
// "Parti"/"Skor" modes and panel rows as soon as their JSON exists.

import { encodeHash, decodeHash, pickInitialLang, findSeatForLocation, nearestSeat,
  formatResultCard, fitBox, partyColor, scoreColor, searchSeats,
  resultKey, displayCode, tallyCoalitions } from "./lib.js";
import { I18N } from "./i18n.js";

const SVG = document.getElementById("map");
const SEATS = document.getElementById("seats");
const TOOLTIP = document.getElementById("tooltip");
const STAGE = document.getElementById("stage");
const PANEL = document.getElementById("panel");
const PANEL_EMPTY = document.getElementById("panel-empty");
const PANEL_SEAT = document.getElementById("panel-seat");
const RESET = document.getElementById("reset");
const LOADING = document.getElementById("loading");
const Q = document.getElementById("q");
const RESULTS = document.getElementById("results");
const FIND_LOC = document.getElementById("find-location");
const FIND_STATUS = document.getElementById("find-status");
const TOAST = document.getElementById("toast");
const TAP_HINT = document.getElementById("tap-hint");
const TAP_HINT_X = document.getElementById("tap-hint-x");
const SHEET_HANDLE = document.getElementById("sheet-handle");

const state = {
  tier: "parlimen",
  mode: "negeri",
  data: {},        // tier -> {viewBox, seats, byCode}
  results: null,   // code_parlimen -> {name, party, coalition, votes, majority}
  scores: null,    // code -> {score, grade, components}
  selected: null,
  paths: new Map(),// code -> <path>
};

const FULL = [0, 0, 799.85, 352.74];
let viewBox = FULL.slice();

// ---- coalition palette ----
// COALITION_COLORS + partyColor() now live in lib.js (one tested source of
// truth for legend/pills/seat-fill/share-card). COALITION_ORDER stays here.
const COALITION_ORDER = ["PH", "PN", "BN", "GPS", "GRS", "WARISAN", "KDM", "PBM", "BEBAS"];

// ---- i18n (English default, Bahasa Melayu toggle) ----
// The I18N string table now lives in ./i18n.js (one tested source of truth;
// lib.test.mjs asserts en/ms key-set parity). Imported at the top of this file.
// BM-first with a browser override; an explicit saved preference always wins.
let lang = "ms";
try {
  const saved = localStorage.getItem("peta-yb-lang");
  lang = pickInitialLang(saved, navigator.languages);
} catch (_) { lang = pickInitialLang(null, null); }

function t(key, params) {
  let s = (I18N[lang] && I18N[lang][key]) ?? I18N.en[key] ?? key;
  if (params) for (const k in params) s = s.split(`{${k}}`).join(params[k]);
  return s;
}
function applyStatic() {
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.setAttribute("placeholder", t(el.dataset.i18nPh)); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.setAttribute("title", t(el.dataset.i18nTitle)); });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
  document.querySelectorAll("[data-i18n-content]").forEach((el) => { el.setAttribute("content", t(el.dataset.i18nContent)); });
  // data-i18n-after → CSS ::after pill (e.g. the "Soon/Segera" badge on the gated Skor tab).
  // textContent assignment above can't clobber it: the badge is a pseudo-element, not a child.
  document.querySelectorAll("[data-i18n-after]").forEach((el) => { el.setAttribute("data-after", t(el.dataset.i18nAfter)); });
  document.documentElement.lang = lang;
  document.title = t("title");
}
function setLang(l) {
  if (l !== "en" && l !== "ms") return;
  lang = l;
  try { localStorage.setItem("peta-yb-lang", l); } catch (_) {}
  document.querySelectorAll("#lang button").forEach((x) => setOn(x, x.dataset.lang === l));
  applyStatic();
  if (loadError) showLoadError();   // applyStatic reset #loading to t("loading") — restore the error copy
  renderSummary();
  if (state.selected) {
    const seat = state.data[state.tier] && state.data[state.tier].byCode.get(state.selected);
    if (seat) renderPanel(seat);
  }
}

// ---- helpers ----
const $ = (sel, el = document) => el.querySelector(sel);
// toggle a tab/segment button's active class AND its ARIA selected state together
const setOn = (el, on) => { el.classList.toggle("on", on); el.setAttribute("aria-selected", on ? "true" : "false"); };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function stateHues(seats) {
  // golden-angle hue spacing → consecutive states (e.g. Sabah/Sarawak) always
  // land far apart on the wheel instead of clashing on a smooth ramp.
  const states = [...new Set(seats.map((s) => s.state))].sort();
  const map = {};
  states.forEach((st, i) => {
    const h = Math.round((i * 137.508) % 360);
    const s = 38 + (i % 3) * 6;          // gentle sat/light jitter for extra separation
    const l = 40 + (i % 2) * 5;
    map[st] = `hsl(${h} ${s}% ${l}%)`;
  });
  return map;
}

// ---- data loading ----
async function loadTier(tier) {
  if (state.data[tier]) return state.data[tier];
  const res = await fetch(`data/seats-${tier}.json`);
  const json = await res.json();
  json.byCode = new Map(json.seats.map((s) => [s.code, s]));
  json.hues = stateHues(json.seats);
  state.data[tier] = json;
  return json;
}

async function loadOptional() {
  // results + scores are baked by later pipeline stages; absence is fine.
  try {
    const r = await fetch("data/results-ge15.json");
    if (r.ok) { state.results = await r.json(); enableMode("parti"); }
  } catch (_) {}
  try {
    const s = await fetch("data/scores.json");
    // AGENTS.md UNTOUCHABLE: "Keep Skor GATED ('Soon') even if scores.json appears."
    // Load the scores (panel score row + seatValueColor skor branch use them) but
    // NEVER enableMode("skor") — the tab stays disabled with its "Soon/Segera" pill.
    if (s.ok) { state.scores = await s.json(); }
  } catch (_) {}
  return state;
}
function enableMode(mode) {
  const btn = document.querySelector(`#mode button[data-mode="${mode}"]`);
  if (btn) { btn.disabled = false; btn.removeAttribute("title"); btn.removeAttribute("data-i18n-title"); }
}

// ---- loading + empty states ----
// The #loading element is an inset:0 overlay (pointer-events:none), so swapping
// between the loading affordance and a friendly error message never shifts layout.
let loadError = false;
function showLoading() {
  loadError = false;
  LOADING.classList.remove("error");
  LOADING.textContent = t("loading");
  LOADING.hidden = false;
}
function showLoadError() {
  loadError = true;
  LOADING.innerHTML = `<span>${esc(t("load_error"))}</span>`;
  LOADING.classList.add("error");
  LOADING.hidden = false;
}

// ---- rendering ----
async function render(tier) {
  const data = await loadTier(tier);
  SVG.setAttribute("viewBox", data.viewBox);
  viewBox = data.viewBox.split(" ").map(Number);
  SEATS.innerHTML = "";
  state.paths.clear();

  const frag = document.createDocumentFragment();
  for (const seat of data.seats) {
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", seat.d);
    p.setAttribute("class", "seat");
    p.dataset.code = seat.code;
    frag.appendChild(p);
    state.paths.set(seat.code, p);
  }
  SEATS.appendChild(frag);
  paint();
  LOADING.hidden = true;
}

function seatValueColor(seat) {
  const data = state.data[state.tier];
  if (state.mode === "parti" && state.results) {
    const key = resultKey(seat, state.tier);
    const r = state.results[key];
    return r ? partyColor(r.coalition) : "#222b36";
  }
  if (state.mode === "skor" && state.scores) {
    const key = resultKey(seat, state.tier);
    const sc = state.scores[key];
    if (!sc) return "#222b36";
    return scoreColor(sc.score); // 0..100 -> red..yellow..green ramp (lib.js)
  }
  return data.hues[seat.state] || "#1b2530";
}

function paint() {
  const data = state.data[state.tier];
  const hasData = state.mode !== "negeri";
  SEATS.classList.toggle("has-data", hasData);
  for (const seat of data.seats) {
    const p = state.paths.get(seat.code);
    if (p) p.style.fill = seatValueColor(seat);
  }
  // re-apply selection styling
  if (state.selected) {
    const p = state.paths.get(state.selected);
    if (p) p.classList.add("sel");
  }
}

// ---- viewBox zoom (lerp) ----
let animId = null;
function animateTo(target, ms = 480) {
  cancelAnimationFrame(animId);
  const start = viewBox.slice();
  const t0 = performance.now();
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  function step(now) {
    const k = Math.min(1, (now - t0) / ms);
    const e = ease(k);
    viewBox = start.map((v, i) => v + (target[i] - v) * e);
    SVG.setAttribute("viewBox", viewBox.map((n) => n.toFixed(2)).join(" "));
    if (k < 1) animId = requestAnimationFrame(step);
  }
  animId = requestAnimationFrame(step);
}
function zoomToSeat(seat) {
  const b = seat.bbox;
  const pad = Math.max(b.w, b.h) * 0.9 + 10;
  const w = b.w + pad * 2;
  const h = b.h + pad * 2;
  // keep map aspect ratio so preserveAspectRatio doesn't distort framing
  const ar = FULL[2] / FULL[3];
  let vw = w, vh = h;
  if (vw / vh > ar) vh = vw / ar; else vw = vh * ar;
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  animateTo([cx - vw / 2, cy - vh / 2, vw, vh]);
}
function zoomFull() { animateTo(FULL.slice()); }

// ---- selection + panel ----
function select(code, { zoom = true } = {}) {
  const data = state.data[state.tier];
  const seat = data.byCode.get(code);
  if (!seat) return;
  if (state.selected && state.paths.get(state.selected))
    state.paths.get(state.selected).classList.remove("sel");
  state.selected = code;
  const p = state.paths.get(code);
  if (p) { p.classList.add("sel"); SEATS.appendChild(p); } // raise to top
  renderPanel(seat);
  if (zoom) zoomToSeat(seat);
  RESET.hidden = false;
  setSheet(true);  // on mobile, slide the bottom sheet up so the card is in view
  dismissHint();   // user found the interaction — retire the nudge
  writeHash();
}
function deselect() {
  if (state.selected && state.paths.get(state.selected))
    state.paths.get(state.selected).classList.remove("sel");
  state.selected = null;
  PANEL.classList.add("empty");
  PANEL_EMPTY.hidden = false;
  PANEL_SEAT.hidden = true;
  setSheet(false); // collapse the bottom sheet back to its peek — the map is the reward
  zoomFull();
  RESET.hidden = true;
  clearMatches();
  setFindStatus(null);   // drop any stale geolocation message
  writeHash();
}

function row(dt, dd, mono = false) {
  return `<dt>${esc(dt)}</dt><dd class="${mono ? "mono" : ""}">${dd}</dd>`;
}
function renderPanel(seat) {
  PANEL.classList.remove("empty");
  PANEL_EMPTY.hidden = true;
  PANEL_SEAT.hidden = false;

  const isP = state.tier === "parlimen";
  const kicker = isP ? `${t("kicker_parlimen")} · ${seat.code}` : `DUN · ${seat.dun_code}`;
  const rk = resultKey(seat, state.tier);
  const r = state.results && state.results[rk];
  const sc = state.scores && state.scores[rk];

  let rows = "";
  if (r) {
    // formatResultCard runs every numeric through a Number.isFinite guard (non-finite
    // → null) and composes party / candidate / runner-up shaping. Driving the panel
    // off the card means a partial row — vote_pct present but votes missing, a NaN or
    // string numeric — OMITS the row instead of rendering "NaN"/"undefined". Real GE15
    // data is complete today; this is defensive for future / DUN result data.
    const card = formatResultCard(r);
    const blocPill = `<span class="pill" style="background:${partyColor(r.coalition)};color:#fff">${esc(r.coalition)}</span>`;
    // surface party_full ("Perikatan Nasional (PN)") via the pure helper; only show
    // it when it adds something beyond the bloc pill (skip a redundant "PN · PN")
    const partyTxt = card.party && card.party.label && card.party.label !== r.coalition ? `${esc(card.party.label)} · ` : "";
    rows += `<dt>${t("rep")}</dt><dd>${esc(r.name)}</dd>`;
    rows += `<dt>${t("party_bloc")}</dt><dd>${partyTxt}${blocPill}</dd>`;
    if (card.majority != null)
      rows += `<dt>${t("majority")}</dt><dd class="mono">${card.majority.toLocaleString()}${card.majorityPct != null ? ` <span class="muted">(${card.majorityPct}%)</span>` : ""}</dd>`;
    if (card.votes != null)
      rows += `<dt>${t("win_votes")}</dt><dd class="mono">${card.votes.toLocaleString()}${card.votePct != null ? ` <span class="muted">(${card.votePct}%)</span>` : ""}</dd>`;
    if (card.turnout != null)
      rows += `<dt>${t("turnout")}</dt><dd class="mono">${card.turnout}%</dd>`;
    if (card.candidates != null)
      rows += `<dt>${t("candidates")}</dt><dd class="mono">${card.candidates}</dd>`;
    const ru = card.runnerUp;
    if (ru) {
      const ruPill = ru.party
        ? ` <span class="pill" style="background:${partyColor(ru.party === r.party ? r.coalition : ru.party)};color:#fff;opacity:.85">${esc(ru.party)}</span>`
        : "";
      // now also surfaces runner_up.votes (panel previously showed only name + party)
      const ruVotes = ru.votes != null ? ` <span class="muted">${ru.votes.toLocaleString()}</span>` : "";
      rows += `<dt>${t("runner")}</dt><dd>${esc(ru.name || "")}${ruPill}${ruVotes}</dd>`;
    }
  } else {
    rows += `<dt>${t("rep")}</dt><dd class="placeholder">${t("rep_ph")}</dd>`;
  }

  if (sc) {
    rows += `<dt>${t("score")}</dt><dd class="mono"><b style="color:var(--accent-2)">${sc.score.toFixed(1)}</b> · ${esc(sc.grade || "")}</dd>`;
  }

  const dunNote = !isP
    ? `<div class="note">${t("dun_note", { p: `<b>${esc(seat.parlimen)}</b>` })}</div>`
    : "";

  PANEL_SEAT.innerHTML = `
    <div class="seat-head">
      <div class="kicker">${esc(kicker)}</div>
      <h2>${esc(seat.name)}</h2>
      <div class="where">${t("state_label")} <b>${esc(seat.state)}</b></div>
    </div>
    <dl class="rows">${rows}</dl>
    ${r ? `<div class="src-line muted">${esc(t("src_ge15"))}</div>` : ""}
    ${dunNote}
    ${!r && isP ? `<div class="note">${t("score_building")}</div>` : ""}
    <div class="seat-actions">
      <button id="share-link" class="share-btn" type="button">${esc(t("share_btn"))}</button>
      <button id="share-card" class="share-btn" type="button">${esc(t("card_btn"))}</button>
    </div>
  `;
}

// ---- share / copy deep-link ----
// Builds the canonical deep-link to the selected seat (encodeHash already encodes
// #tier/mode/code) and copies it to the clipboard, with a transient toast. The
// clipboard API is guarded — on any failure we tell the user to copy from the URL bar.
let toastTimer = null;
function showToast(key) {
  if (!TOAST) return;
  TOAST.textContent = t(key);
  TOAST.hidden = false;
  TOAST.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { TOAST.classList.remove("show"); TOAST.hidden = true; }, 2600);
}
async function shareLink() {
  const url = location.origin + location.pathname + encodeHash(state);
  let ok = false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(url);
      ok = true;
    }
  } catch (_) { ok = false; }
  showToast(ok ? "share_ok" : "share_fail");
}
// ---- share IMAGE: a 1080×1350 seat card (Canvas 2D) ----
// Draws the selected seat's silhouette (new Path2D(seat.d), fit via the pure
// fitBox transform) + headline facts onto an off-screen canvas, then shares the
// PNG via navigator.share({files}) where supported, falling back to a download.
// Fully guarded — any failure shows a toast pointing back to the 🔗 share link.
const CARD_W = 1080, CARD_H = 1350;
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function drawSeatCard(seat) {
  const isP = state.tier === "parlimen";
  const rk = resultKey(seat, state.tier);
  const r = state.results && state.results[rk];
  const accent = r ? partyColor(r.coalition) : "#5d6b7d";

  const cv = document.createElement("canvas");
  cv.width = CARD_W; cv.height = CARD_H;
  const ctx = cv.getContext("2d");
  if (!ctx) return null;

  // backdrop
  ctx.fillStyle = "#0f141b";
  ctx.fillRect(0, 0, CARD_W, CARD_H);
  // accent header band
  ctx.fillStyle = accent;
  ctx.fillRect(0, 0, CARD_W, 12);

  // brand
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#e8edf3";
  ctx.font = "600 44px 'Space Grotesk', system-ui, sans-serif";
  ctx.fillText("◧ MyPolitik", 64, 110);

  // seat silhouette in a centred region, tinted by the bloc colour
  const REG = { x: 64, y: 170, w: CARD_W - 128, h: 620 };
  const fit = fitBox(seat.bbox, REG.w, REG.h, 40);
  if (fit) {
    try {
      const path = new Path2D(seat.d);
      ctx.save();
      ctx.translate(REG.x, REG.y);
      ctx.translate(fit.dx, fit.dy);
      ctx.scale(fit.scale, fit.scale);
      ctx.fillStyle = accent;
      ctx.globalAlpha = 0.92;
      ctx.fill(path, "evenodd");
      ctx.restore();
    } catch (_) { /* Path2D unsupported / bad d — text card still works */ }
  }
  ctx.globalAlpha = 1;

  // kicker · code
  const kicker = isP ? `${t("kicker_parlimen")} · ${seat.code}` : `DUN · ${seat.dun_code}`;
  ctx.fillStyle = accent;
  ctx.font = "600 30px 'Space Grotesk', system-ui, sans-serif";
  ctx.fillText(kicker.toUpperCase(), 64, 900);

  // seat name (clamped to width)
  ctx.fillStyle = "#f5f8fb";
  ctx.font = "700 84px 'Space Grotesk', system-ui, sans-serif";
  let name = String(seat.name || "");
  while (name.length > 6 && ctx.measureText(name).width > CARD_W - 128) name = name.slice(0, -1);
  if (name !== seat.name) name = name.trim() + "…";
  ctx.fillText(name, 64, 985);

  // state
  ctx.fillStyle = "#9fb0c0";
  ctx.font = "400 38px 'Space Grotesk', system-ui, sans-serif";
  ctx.fillText(`${t("state_label")}: ${seat.state || ""}`, 64, 1045);

  // representative + bloc pill, or a gentle "data soon" line
  let y = 1130;
  if (r) {
    ctx.fillStyle = "#e8edf3";
    ctx.font = "600 46px 'Space Grotesk', system-ui, sans-serif";
    ctx.fillText(String(r.name || ""), 64, y);
    // bloc pill
    const label = String(r.coalition || "");
    ctx.font = "600 30px 'Space Grotesk', system-ui, sans-serif";
    const pw = ctx.measureText(label).width + 40;
    ctx.fillStyle = accent;
    roundRect(ctx, 64, y + 28, pw, 50, 25);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.fillText(label, 84, y + 62);
    if (r.majority != null) {
      ctx.fillStyle = "#9fb0c0";
      ctx.font = "400 30px 'JetBrains Mono', monospace";
      ctx.fillText(`${t("majority")}: ${Number(r.majority).toLocaleString()}`, 84 + pw, y + 62);
    }
  } else {
    ctx.fillStyle = "#9fb0c0";
    ctx.font = "400 40px 'Space Grotesk', system-ui, sans-serif";
    ctx.fillText(t("rep_ph"), 64, y);
  }

  // footer: call-to-action + source line
  ctx.fillStyle = "#7d8da0";
  ctx.font = "400 28px 'Space Grotesk', system-ui, sans-serif";
  const host = (location.host || "mypolitik").replace(/^www\./, "");
  ctx.fillText(`${t("card_find")} ${host}`, 64, CARD_H - 90);
  ctx.fillStyle = "#5d6b7d";
  ctx.font = "400 24px 'Space Grotesk', system-ui, sans-serif";
  if (r) ctx.fillText(t("src_ge15"), 64, CARD_H - 52);
  return cv;
}
let sharingCard = false;
async function shareCard() {
  if (sharingCard) return;
  const seat = state.selected && state.data[state.tier] &&
    state.data[state.tier].byCode.get(state.selected);
  if (!seat) return;
  sharingCard = true;
  try {
    if (document.fonts && document.fonts.ready) {
      try { await document.fonts.ready; } catch (_) {}
    }
    const cv = drawSeatCard(seat);
    if (!cv) { showToast("card_fail"); return; }
    const blob = await new Promise((res) =>
      cv.toBlob ? cv.toBlob(res, "image/png") : res(null));
    if (!blob) { showToast("card_fail"); return; }
    const fname = `mypolitik-${(seat.code || "seat").replace(/[^\w.-]/g, "_")}.png`;
    const file = new File([blob], fname, { type: "image/png" });
    // prefer the native share sheet when it accepts files (mobile)
    if (navigator.canShare && navigator.canShare({ files: [file] }) && navigator.share) {
      try {
        await navigator.share({ files: [file], title: t("title"), text: seat.name });
        return;
      } catch (err) {
        if (err && err.name === "AbortError") return; // user dismissed — not an error
        // fall through to download
      }
    }
    // fallback: trigger a download
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = fname;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } catch (_) {
    showToast("card_fail");
  } finally {
    sharingCard = false;
  }
}
// PANEL_SEAT.innerHTML is rebuilt on every render, so delegate rather than re-bind.
PANEL_SEAT.addEventListener("click", (e) => {
  if (e.target.closest("#share-link")) shareLink();
  else if (e.target.closest("#share-card")) shareCard();
});

// ---- summary + legend (empty panel) ----
function renderSummary() {
  const data = state.data[state.tier];
  if (!data) return;   // boundary layer unavailable — error overlay is showing instead
  const states = new Set(data.seats.map((s) => s.state));
  $("#summary").innerHTML =
    `<dt>${t("seats")}</dt><dd>${data.count}</dd>` +
    `<dt>${t("states")}</dt><dd>${states.size}</dd>` +
    `<dt>${t("layer")}</dt><dd>${state.tier === "parlimen" ? t("tier_parlimen") : t("tier_dun")}</dd>`;
  // legend reflects current color mode
  const lg = $("#legend");
  if (state.mode === "negeri") {
    const top = [...states].sort().slice(0, 6);
    lg.innerHTML = `<div class="row" style="color:var(--ink-faint);margin-bottom:2px">${t("by_state")}</div>` +
      top.map((st) => `<div class="row"><span class="sw" style="background:${data.hues[st]}"></span>${esc(st)}</div>`).join("") +
      (states.size > 6 ? `<div class="row muted">${t("more", { n: states.size - 6 })}</div>` : "");
  } else if (state.mode === "parti") {
    const counts = tallyCoalitions(state.results);
    const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
    const ordered = COALITION_ORDER.filter((c) => counts[c]);
    const bar = `<div class="sharebar">` +
      ordered.map((c) => `<span style="background:${partyColor(c)};width:${(100 * counts[c] / total).toFixed(2)}%" title="${c} ${counts[c]}"></span>`).join("") +
      `</div>`;
    const key = `<div class="sharebar-key">` +
      ordered.map((c) => `<span style="display:flex;align-items:center;gap:5px"><span class="sw" style="width:9px;height:9px;background:${partyColor(c)}"></span>${esc(c)} <b>${counts[c]}</b></span>`).join("") +
      `</div>`;
    lg.innerHTML = `<div class="row" style="color:var(--ink-faint)">${t("by_bloc")}</div>${bar}${key}` +
      `<div class="row muted" style="margin-top:8px;font-size:11px">${t("simple_majority")}</div>`;
  } else {
    lg.innerHTML = `<div class="row" style="margin-bottom:2px">${t("by_score")}</div>`;
  }
}

// ---- hover tooltip ----
SVG.addEventListener("mousemove", (e) => {
  const t = e.target;
  if (t.classList && t.classList.contains("seat")) {
    const data = state.data[state.tier];
    if (!data) return;   // boundary layer unavailable — no seat paths exist anyway; guard for symmetry
    const seat = data.byCode.get(t.dataset.code);
    if (!seat) return;
    const code = displayCode(seat, state.tier);
    const rk = resultKey(seat, state.tier);
    const r = state.results && state.results[rk];
    const win = r
      ? `<div class="t-win">${esc(r.name)} <span class="pill" style="background:${partyColor(r.coalition)};color:#fff">${esc(r.coalition)}</span></div>`
      : "";
    TOOLTIP.innerHTML = `<div class="t-code">${esc(code)}</div>${esc(seat.name)}<div class="t-state">${esc(seat.state)}</div>${win}`;
    const rect = STAGE.getBoundingClientRect();
    TOOLTIP.style.left = `${e.clientX - rect.left}px`;
    TOOLTIP.style.top = `${e.clientY - rect.top}px`;
    TOOLTIP.hidden = false;
  } else {
    TOOLTIP.hidden = true;
  }
});
SVG.addEventListener("mouseleave", () => { TOOLTIP.hidden = true; });

// ---- click ----
SVG.addEventListener("click", (e) => {
  const t = e.target;
  if (t.classList && t.classList.contains("seat")) {
    select(t.dataset.code);
  } else {
    deselect();
  }
});

// ---- search ----
function clearMatches() {
  for (const p of state.paths.values()) p.classList.remove("dim", "match");
}
// keyboard nav over the #results listbox: an .active highlight tracks the
// focused option, mirrored to aria-activedescendant on #q for screen readers.
let activeResult = -1;
const resultOptions = () => RESULTS.querySelectorAll("button");
function setActiveResult(idx) {
  const opts = resultOptions();
  activeResult = idx;
  opts.forEach((o, i) => {
    const on = i === idx;
    o.classList.toggle("active", on);
    o.setAttribute("aria-selected", on ? "true" : "false");
    if (on) { Q.setAttribute("aria-activedescendant", o.id); o.scrollIntoView({ block: "nearest" }); }
  });
  if (idx < 0) Q.removeAttribute("aria-activedescendant");
}
function moveActiveResult(delta) {
  const opts = resultOptions();
  if (!opts.length) return;
  let idx = activeResult + delta;
  if (idx < 0) idx = opts.length - 1;        // wrap up → bottom
  else if (idx >= opts.length) idx = 0;      // wrap down → top
  setActiveResult(idx);
}
function hideResults() {
  RESULTS.hidden = true;
  RESULTS.innerHTML = "";                       // drop stale options so they can't be announced or re-clicked
  setActiveResult(-1);                          // also clears aria-activedescendant
  Q.setAttribute("aria-expanded", "false");
}
Q.addEventListener("input", () => {
  const q = Q.value.trim().toLowerCase();
  hideResults();
  clearMatches();
  if (!q) return;
  const data = state.data[state.tier];
  if (!data) return;   // boundary layer unavailable (init bailed) — keep search inert, don't throw
  const hits = searchSeats(data.seats, q, state.tier);
  if (!hits.length) return;
  for (const p of state.paths.values()) p.classList.add("dim");
  for (const s of hits.slice(0, 60)) {
    const p = state.paths.get(s.code);
    if (p) { p.classList.remove("dim"); p.classList.add("match"); }
  }
  RESULTS.innerHTML = hits.slice(0, 8).map((s, i) => {
    const code = displayCode(s, state.tier);
    return `<button id="result-opt-${i}" role="option" aria-selected="false" data-code="${esc(s.code)}"><span>${esc(s.name)} <span class="muted" style="font-size:11px">${esc(s.state)}</span></span><span class="code">${esc(code)}</span></button>`;
  }).join("");
  setActiveResult(-1);            // fresh list: nothing highlighted yet
  RESULTS.hidden = false;
  Q.setAttribute("aria-expanded", "true");
});
RESULTS.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  hideResults();
  Q.value = "";
  clearMatches();
  select(b.dataset.code);
});
Q.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") {
    if (RESULTS.hidden) return;
    e.preventDefault(); moveActiveResult(1);
  } else if (e.key === "ArrowUp") {
    if (RESULTS.hidden) return;
    e.preventDefault(); moveActiveResult(-1);
  } else if (e.key === "Enter") {
    if (RESULTS.hidden) return;                  // no open dropdown → don't re-select a stale seat
    const opts = resultOptions();
    const pick = activeResult >= 0 ? opts[activeResult] : opts[0];   // highlighted, else first
    if (pick) pick.click();
  } else if (e.key === "Escape") {
    // Clear the search only — stopPropagation so the event doesn't bubble to the
    // document handler that deselects the seat (one Escape, one action). A second
    // Escape with focus outside #q still deselects via the global handler.
    e.stopPropagation();
    Q.value = ""; hideResults(); clearMatches();
  }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".search")) hideResults();
});

// ---- geolocation: "📍 Use my location" → find your seat ----
// Always non-fatal: any failure (unsupported / denied / timeout / no match) shows a
// short status that points back to the search box, which is the always-present manual
// fallback. The status lives in #panel-empty and re-translates on language toggle.
let locating = false;
function setFindStatus(key) {
  if (!FIND_STATUS) return;
  if (!key) { delete FIND_STATUS.dataset.i18n; FIND_STATUS.textContent = ""; FIND_STATUS.hidden = true; return; }
  FIND_STATUS.dataset.i18n = key;     // applyStatic() re-translates it on setLang
  FIND_STATUS.textContent = t(key);
  FIND_STATUS.hidden = false;
}
function locate() {
  if (locating) return;
  if (!navigator.geolocation) { setFindStatus("loc_unsupported"); return; }
  locating = true;
  FIND_LOC.disabled = true;
  setFindStatus("loc_locating");
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      locating = false;
      FIND_LOC.disabled = false;
      const { latitude: lat, longitude: lng } = pos.coords;
      const seats = state.data[state.tier] && state.data[state.tier].seats;
      // 150 km bound covers genuine offshore islands without snapping an
      // out-of-country user (Singapore/Indonesia/abroad) onto a border seat.
      const seat = seats && (findSeatForLocation(lat, lng, seats) || nearestSeat(lat, lng, seats, 150));
      if (!seat) { setFindStatus("loc_notfound"); return; }
      setFindStatus(null);
      select(seat.code);
    },
    (err) => {
      locating = false;
      FIND_LOC.disabled = false;
      // PERMISSION_DENIED === 1; everything else (unavailable, timeout) is a generic error
      setFindStatus(err && err.code === 1 ? "loc_denied" : "loc_error");
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
  );
}
if (FIND_LOC) FIND_LOC.addEventListener("click", locate);

// ---- first-load tap hint (dismissed for good once seen) ----
// A one-time nudge over the map so first-time visitors know the seats are tappable.
// Dismissed by the ✕, by selecting any seat, and remembered in localStorage so it
// never re-appears. localStorage access is guarded — a blocked store just means the
// hint shows each visit (harmless) rather than throwing.
const HINT_KEY = "peta-yb-hint-seen";
function hintSeen() {
  try { return localStorage.getItem(HINT_KEY) === "1"; } catch (_) { return false; }
}
function dismissHint() {
  if (!TAP_HINT || TAP_HINT.hidden) return;
  TAP_HINT.hidden = true;
  try { localStorage.setItem(HINT_KEY, "1"); } catch (_) {}
}
function maybeShowHint() {
  // only on a fresh visit with nothing selected — a deep-linked seat skips the hint
  if (!TAP_HINT || hintSeen() || state.selected) return;
  TAP_HINT.hidden = false;
}
if (TAP_HINT_X) TAP_HINT_X.addEventListener("click", dismissHint);

// ---- mobile bottom sheet ----
// On narrow screens the panel is a draggable sheet that overlays the map: it peeks
// at the bottom (CSS transform) and slides up to ~85dvh when opened. Tapping or
// dragging the grab-handle toggles it; selecting a seat opens it, deselect collapses.
// On desktop the handle is display:none and the .sheet-open class is inert (no CSS
// rule), so all of this is a no-op there — select/deselect call setSheet harmlessly.
const SHEET_MQ = window.matchMedia("(max-width: 820px)");
function sheetOpen() { return PANEL.classList.contains("sheet-open"); }
function setSheet(open) {
  PANEL.classList.toggle("sheet-open", open);
  if (SHEET_HANDLE) SHEET_HANDLE.setAttribute("aria-expanded", open ? "true" : "false");
}
function peekPx() {
  const v = parseFloat(getComputedStyle(PANEL).getPropertyValue("--sheet-peek"));
  return Number.isFinite(v) ? v : 172;
}
if (SHEET_HANDLE) {
  let startY = null, base = 0, moved = false;
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  SHEET_HANDLE.addEventListener("pointerdown", (e) => {
    if (!SHEET_MQ.matches) return;
    startY = e.clientY; moved = false;
    base = sheetOpen() ? 0 : Math.max(0, PANEL.offsetHeight - peekPx());
    PANEL.classList.add("dragging"); // suspend the CSS transition while finger-following
    try { SHEET_HANDLE.setPointerCapture(e.pointerId); } catch (_) {}
  });
  SHEET_HANDLE.addEventListener("pointermove", (e) => {
    if (startY === null) return;
    const dy = e.clientY - startY;
    if (Math.abs(dy) > 6) moved = true;
    const closed = Math.max(0, PANEL.offsetHeight - peekPx());
    PANEL.style.transform = `translateY(${clamp(base + dy, 0, closed)}px)`;
  });
  const endDrag = (e) => {
    if (startY === null) return;
    const dy = (e.clientY ?? startY) - startY;
    const closed = Math.max(0, PANEL.offsetHeight - peekPx());
    startY = null;
    PANEL.classList.remove("dragging");
    PANEL.style.transform = ""; // hand control back to the class-driven CSS transform
    if (moved) setSheet(clamp(base + dy, 0, closed) < closed / 2);
    // a pure tap (no move) is handled by the click listener below
  };
  SHEET_HANDLE.addEventListener("pointerup", endDrag);
  SHEET_HANDLE.addEventListener("pointercancel", endDrag);
  // tap / keyboard (Enter/Space) → toggle; suppressed right after a drag gesture
  SHEET_HANDLE.addEventListener("click", () => { if (!moved) setSheet(!sheetOpen()); });
}

// ---- toggles ----
async function setTier(tier) {
  if (tier === state.tier) return;
  const prev = state.tier;
  document.querySelectorAll("#tier button").forEach((x) => setOn(x, x.dataset.tier === tier));
  state.tier = tier;
  state.selected = null;
  showLoading();
  try {
    await render(tier);
  } catch (_) {
    // new tier's boundaries unavailable — keep the previous layer and explain why
    state.tier = prev;
    document.querySelectorAll("#tier button").forEach((x) => setOn(x, x.dataset.tier === prev));
    showLoadError();
    return;
  }
  deselect();
  renderSummary();
  writeHash();
}
function setMode(mode) {
  const b = document.querySelector(`#mode button[data-mode="${mode}"]`);
  if (!b || b.disabled) return;
  document.querySelectorAll("#mode button").forEach((x) => setOn(x, x === b));
  state.mode = mode;
  paint();
  renderSummary();
  writeHash();
}
document.getElementById("tier").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (b) setTier(b.dataset.tier);
});
document.getElementById("mode").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (b && !b.disabled) setMode(b.dataset.mode);
});
document.getElementById("lang").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (b) setLang(b.dataset.lang);
});

// ---- shareable URL state  (#tier/mode[/code]) ----
function writeHash() {
  const h = encodeHash(state);
  if (location.hash !== h) history.replaceState(null, "", h);
}
function parseHash() {
  return decodeHash(location.hash);
}

// ---- keyboard ----
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && state.selected) deselect();
});
RESET.addEventListener("click", deselect);

// ---- boot ----
(async function init() {
  document.querySelectorAll("#lang button").forEach((x) => setOn(x, x.dataset.lang === lang));
  applyStatic();
  const h = parseHash();
  const tier = h && (h.tier === "dun" || h.tier === "parlimen") ? h.tier : "parlimen";
  state.tier = tier;
  document.querySelectorAll("#tier button").forEach((x) => setOn(x, x.dataset.tier === tier));
  try {
    await render(tier);
  } catch (_) {
    showLoadError();              // core boundaries unavailable — stop here with a friendly message
    return;
  }
  renderSummary();
  await loadOptional();           // results/scores ready → modes can be restored
  if (h && (h.mode === "parti" || h.mode === "skor")) setMode(h.mode);
  if (h && h.code) {
    const data = state.data[state.tier];
    if (data.byCode.has(h.code)) select(h.code);
  }
  writeHash();       // normalise URL to the actually-active state — a gated mode (Skor) or bad seat
                     // code in the deep link gets dropped so a re-shared link can't misrepresent state
                     // (replaceState → no extra history entry)
  maybeShowHint();   // fresh visit, nothing selected → nudge that seats are tappable
})();
