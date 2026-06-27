// Peta YB — interactive map of Malaysia's electoral seats.
// Data-driven: boundaries render now; GE15 results + scores light up the
// "Parti"/"Skor" modes and panel rows as soon as their JSON exists.

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

// ---- coalition palette (used once results-ge15.json lands) ----
const COALITION_COLORS = {
  PH: "#d7263d", PN: "#15387c", BN: "#1f9bd6", GPS: "#b8332e",
  GRS: "#e8772e", WARISAN: "#16a085", KDM: "#8e44ad", PBM: "#6c7a89",
  BEBAS: "#8a97a6",
};
const COALITION_ORDER = ["PH", "PN", "BN", "GPS", "GRS", "WARISAN", "KDM", "PBM", "BEBAS"];
const partyColor = (p) => COALITION_COLORS[(p || "").toUpperCase()] || "#5d6b7d";

// ---- i18n (English default, Bahasa Melayu toggle) ----
const I18N = {
  en: {
    title: "Peta YB — Map Malaysia's Representatives",
    meta_desc: "Interactive map of every Malaysian Parliament and State (DUN) seat. Click your area to see the representative, party, and performance — public data, computed transparently.",
    map_aria: "Map of Malaysia's electoral seats",
    aria_tier: "Seat layer", aria_mode: "Colour mode", aria_lang: "Language",
    brand_tag: "Your representatives, on the map",
    tier_parlimen: "Parliament", tier_dun: "DUN",
    mode_negeri: "State", mode_parti: "Party", mode_skor: "Score",
    mode_parti_need: "Needs GE15 data", mode_skor_need: "Needs score data",
    search_ph: "Search a seat…",
    search_aria: "Search a seat", results_aria: "Search results", reset_aria: "Show all seats",
    empty_h: "Pick a seat",
    empty_p: "Click any seat on the map, or search by name above.",
    src_bound: "Boundaries", src_proj: "Projection",
    loading: "Loading boundaries…",
    load_error: "Couldn't load seat boundaries — check your connection and refresh.",
    reset_btn: "↺ Show all", reset_title: "Show all (Esc)",
    rep: "Representative", rep_ph: "GE15 data not loaded",
    party_bloc: "Party / Bloc", majority: "GE15 majority", win_votes: "Winning votes",
    turnout: "Turnout", runner: "Runner-up", score: "Performance score",
    state_label: "State", kicker_parlimen: "PARLIAMENT SEAT",
    dun_note: "Results shown at the parent Parliament level ({p}). State-election (PRN) results coming soon.",
    score_building: "Performance-score layer is being built.",
    seats: "Seats", states: "States", layer: "Layer",
    by_state: "Coloured by state", more: "+ {n} more…",
    by_bloc: "Parliament seats by bloc · GE15", simple_majority: "Simple majority = 112 seats",
    by_score: "Coloured by score (red→green)",
  },
  ms: {
    title: "Peta YB — Petakan Wakil Rakyat Malaysia",
    meta_desc: "Peta interaktif setiap kerusi Parlimen dan Negeri (DUN) Malaysia. Klik kawasan anda untuk melihat wakil rakyat, parti dan prestasi — data awam, dikira secara telus.",
    map_aria: "Peta kerusi pilihan raya Malaysia",
    aria_tier: "Lapisan kerusi", aria_mode: "Mod warna", aria_lang: "Bahasa",
    brand_tag: "Wakil rakyat anda, atas peta",
    tier_parlimen: "Parlimen", tier_dun: "DUN",
    mode_negeri: "Negeri", mode_parti: "Parti", mode_skor: "Skor",
    mode_parti_need: "Perlu data PRU15", mode_skor_need: "Perlu data skor",
    search_ph: "Cari kawasan…",
    search_aria: "Cari kawasan", results_aria: "Hasil carian", reset_aria: "Papar semua kerusi",
    empty_h: "Pilih sesebuah kawasan",
    empty_p: "Klik mana-mana kerusi pada peta, atau cari nama kawasan di atas.",
    src_bound: "Sempadan", src_proj: "Projeksi",
    loading: "Memuatkan sempadan…",
    load_error: "Tidak dapat memuatkan sempadan kerusi — semak sambungan dan muat semula.",
    reset_btn: "↺ Papar semua", reset_title: "Papar semua (Esc)",
    rep: "Wakil rakyat", rep_ph: "data PRU15 belum dimuat",
    party_bloc: "Parti / Blok", majority: "Majoriti PRU15", win_votes: "Undi menang",
    turnout: "Penyertaan", runner: "Penyangga", score: "Skor prestasi",
    state_label: "Negeri", kicker_parlimen: "KERUSI PARLIMEN",
    dun_note: "Keputusan dipaparkan pada peringkat Parlimen induk ({p}). Keputusan DUN (PRN) menyusul.",
    score_building: "Lapisan skor prestasi sedang dibina.",
    seats: "Kerusi", states: "Negeri", layer: "Lapisan",
    by_state: "Warna ikut negeri", more: "+ {n} lagi…",
    by_bloc: "Kerusi Parlimen ikut blok · PRU15", simple_majority: "Majoriti mudah = 112 kerusi",
    by_score: "Warna ikut skor (merah→hijau)",
  },
};
let lang = "en";
try { const saved = localStorage.getItem("peta-yb-lang"); if (saved === "ms" || saved === "en") lang = saved; } catch (_) {}

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
    if (s.ok) { state.scores = await s.json(); enableMode("skor"); }
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
    const key = state.tier === "parlimen" ? seat.code : seat.parlimen;
    const r = state.results[key];
    return r ? partyColor(r.coalition) : "#222b36";
  }
  if (state.mode === "skor" && state.scores) {
    const key = state.tier === "parlimen" ? seat.code : seat.parlimen;
    const sc = state.scores[key];
    if (!sc) return "#222b36";
    // 0..100 -> red..yellow..green
    const t = Math.max(0, Math.min(1, sc.score / 100));
    const h = Math.round(t * 130); // 0 red -> 130 green
    return `hsl(${h} 60% 45%)`;
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
  writeHash();
}
function deselect() {
  if (state.selected && state.paths.get(state.selected))
    state.paths.get(state.selected).classList.remove("sel");
  state.selected = null;
  PANEL.classList.add("empty");
  PANEL_EMPTY.hidden = false;
  PANEL_SEAT.hidden = true;
  zoomFull();
  RESET.hidden = true;
  clearMatches();
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
  const resultKey = isP ? seat.code : seat.parlimen;
  const r = state.results && state.results[resultKey];
  const sc = state.scores && state.scores[resultKey];

  let rows = "";
  if (r) {
    const blocPill = `<span class="pill" style="background:${partyColor(r.coalition)};color:#fff">${esc(r.coalition)}</span>`;
    const partyTxt = r.party && r.party !== r.coalition ? `${esc(r.party)} · ` : "";
    rows += `<dt>${t("rep")}</dt><dd>${esc(r.name)}</dd>`;
    rows += `<dt>${t("party_bloc")}</dt><dd>${partyTxt}${blocPill}</dd>`;
    if (r.majority != null)
      rows += `<dt>${t("majority")}</dt><dd class="mono">${Number(r.majority).toLocaleString()}${r.majority_pct != null ? ` <span class="muted">(${r.majority_pct}%)</span>` : ""}</dd>`;
    if (r.vote_pct != null)
      rows += `<dt>${t("win_votes")}</dt><dd class="mono">${Number(r.votes).toLocaleString()} <span class="muted">(${r.vote_pct}%)</span></dd>`;
    if (r.turnout != null)
      rows += `<dt>${t("turnout")}</dt><dd class="mono">${r.turnout}%</dd>`;
    if (r.runner_up)
      rows += `<dt>${t("runner")}</dt><dd>${esc(r.runner_up.name)} <span class="pill" style="background:${partyColor(r.runner_up.party === r.party ? r.coalition : r.runner_up.party)};color:#fff;opacity:.85">${esc(r.runner_up.party)}</span></dd>`;
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
    ${dunNote}
    ${!r && isP ? `<div class="note">${t("score_building")}</div>` : ""}
  `;
}

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
    const counts = {};
    if (state.results) for (const v of Object.values(state.results)) counts[v.coalition] = (counts[v.coalition] || 0) + 1;
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
    const seat = data.byCode.get(t.dataset.code);
    if (!seat) return;
    const code = state.tier === "parlimen" ? seat.code : seat.dun_code;
    const rk = state.tier === "parlimen" ? seat.code : seat.parlimen;
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
Q.addEventListener("input", () => {
  const q = Q.value.trim().toLowerCase();
  RESULTS.hidden = true;
  clearMatches();
  if (!q) return;
  const data = state.data[state.tier];
  const hits = data.seats.filter((s) =>
    s.name.toLowerCase().includes(q) || s.code.toLowerCase().includes(q) || s.state.toLowerCase().includes(q)
  );
  if (!hits.length) return;
  for (const p of state.paths.values()) p.classList.add("dim");
  for (const s of hits.slice(0, 60)) {
    const p = state.paths.get(s.code);
    if (p) { p.classList.remove("dim"); p.classList.add("match"); }
  }
  RESULTS.innerHTML = hits.slice(0, 8).map((s) => {
    const code = state.tier === "parlimen" ? s.code : s.dun_code;
    return `<button data-code="${esc(s.code)}"><span>${esc(s.name)} <span class="muted" style="font-size:11px">${esc(s.state)}</span></span><span class="code">${esc(code)}</span></button>`;
  }).join("");
  RESULTS.hidden = false;
});
RESULTS.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  RESULTS.hidden = true;
  Q.value = "";
  clearMatches();
  select(b.dataset.code);
});
Q.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const first = RESULTS.querySelector("button");
    if (first) first.click();
  } else if (e.key === "Escape") { Q.value = ""; RESULTS.hidden = true; clearMatches(); }
});
document.addEventListener("click", (e) => {
  if (!e.target.closest(".search")) RESULTS.hidden = true;
});

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
  const parts = [state.tier, state.mode];
  if (state.selected) parts.push(state.selected);
  const h = "#" + parts.map(encodeURIComponent).join("/");
  if (location.hash !== h) history.replaceState(null, "", h);
}
function parseHash() {
  const raw = location.hash.replace(/^#/, "");
  if (!raw) return null;
  const [tier, mode, code] = raw.split("/").map((s) => decodeURIComponent(s || ""));
  return { tier, mode, code };
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
})();
