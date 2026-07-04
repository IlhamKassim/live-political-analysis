// MyPolitik — interactive map of Malaysia's electoral seats.
// Data-driven: boundaries render now; GE15 results + scores light up the
// "Parti"/"Skor" modes and panel rows as soon as their JSON exists.

import { encodeHash, decodeHash, pickInitialLang, findSeatForLocation, nearestSeat,
  formatResultCard, fitBox, partyColor, scoreColor, searchSeats,
  resultKey, displayCode, tallyCoalitions, stateHues } from "./lib.js?v=3";
import { I18N } from "./i18n.js?v=3";

const SVG = document.getElementById("map");
const SEATS = document.getElementById("seats");
const SELECTED_OVERLAY = document.getElementById("selected-overlay");
const TOOLTIP = document.getElementById("tooltip");
const STAGE = document.getElementById("stage");
const TOPBAR = document.getElementById("topbar");
const TOP_CONTROLS = document.getElementById("top-controls");
const MOBILE_MENU = document.getElementById("mobile-menu");
const MOBILE_MENU_BTN = document.getElementById("mobile-menu-btn");
const PANEL = document.getElementById("panel");
const PANEL_EMPTY = document.getElementById("panel-empty");
const PANEL_SEAT = document.getElementById("panel-seat");
const STATE_ACTIONS = document.getElementById("state-actions");
const MAP_INSPECT_TOGGLE = document.getElementById("map-inspect-toggle");
const MAP_INSPECT_TRAY = document.getElementById("map-inspect-tray");
const RESET = document.getElementById("reset");
const LOADING = document.getElementById("loading");
const Q = document.getElementById("q");
const RESULTS = document.getElementById("results");
const FIND_LOC = document.getElementById("loc-btn") || document.getElementById("find-location");
const FIND_STATUS = document.getElementById("find-status");
const TOAST = document.getElementById("toast");
const CARD_PREVIEW = document.getElementById("card-preview");
const CARD_PREVIEW_IMG = document.getElementById("card-preview-img");
const CARD_PREVIEW_DOWNLOAD = document.getElementById("card-preview-download");
const CARD_PREVIEW_CLOSE = document.getElementById("card-preview-close");
const TAP_HINT = document.getElementById("tap-hint");
const TAP_HINT_X = document.getElementById("tap-hint-x");
const SHEET_HANDLE = document.getElementById("sheet-handle");

const state = {
  tier: "parlimen",
  mode: "parti",
  data: {},        // tier -> {viewBox, seats, byCode}
  results: null,   // code_parlimen -> {name, party, coalition, votes, majority}
  resultsDun: null,// code_state_dun -> same shape (state-election / PRN result, where we have it)
  scores: null,    // code -> {score, grade, components}
  candidates: null,// code_parlimen -> candidate rows from candidates_ge15.csv
  candidatesDun: null,// code_state_dun -> candidate rows from candidates_prn15.csv
  votingGuide: null,
  selected: null,
  seatTab: "overview",
  mapInspect: false,
  paths: new Map(),// code -> <path>
};

const FULL = [0, 0, 799.85, 352.74];
let viewBox = FULL.slice();

// ---- coalition palette ----
// COALITION_COLORS + partyColor() now live in lib.js (one tested source of
// truth for legend/pills/seat-fill/share-card). COALITION_ORDER stays here.
const COALITION_ORDER = ["PH", "PN", "BN", "GPS", "GRS", "WARISAN", "KDM", "PBM", "BEBAS"];
const SEAT_TABS = ["overview", "results", "candidates", "voting"];
const isSeatTab = (tab) => SEAT_TABS.includes(tab);

// ---- i18n (English default, Bahasa Melayu toggle) ----
// The I18N string table now lives in ./i18n.js (one tested source of truth;
// lib.test.mjs asserts en/ms key-set parity). Imported at the top of this file.
// BM-first with a browser override; an explicit saved preference always wins.
const LANG_KEY = "mypolitik-lang";
const LEGACY_LANG_KEY = "peta-yb-lang";
let lang = "ms";
try {
  const saved = localStorage.getItem(LANG_KEY) || localStorage.getItem(LEGACY_LANG_KEY);
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
  try {
    localStorage.setItem(LANG_KEY, l);
    localStorage.removeItem(LEGACY_LANG_KEY);
  } catch (_) {}
  document.querySelectorAll("#lang button").forEach((x) => setOn(x, x.dataset.lang === l));
  applyStatic();
  if (loadError) showLoadError();   // applyStatic reset #loading to t("loading") — restore the error copy
  renderSummary();
  if (state.selected) {
    const seat = state.data[state.tier] && state.data[state.tier].byCode.get(state.selected);
    if (seat && state.openState) {
      STATE_INFO.innerHTML = stateSeatCardHTML(seat);
      resetStateInfoScroll();
    }
    else if (seat) renderPanel(seat);
  } else if (state.openState) {
    document.getElementById("state-count").textContent = t(
      "state_count_" + (state.tier === "parlimen" ? "parlimen" : "dun"),
      { n: state.data[state.tier].seats.filter((s) => s.state === state.openState).length }
    );
    STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
  }
  syncMapInspectButton();
  renderMapInspectTray();
}

// ---- helpers ----
const $ = (sel, el = document) => el.querySelector(sel);
// toggle a tab/segment button's active class AND its ARIA selected state together
const setOn = (el, on) => { el.classList.toggle("on", on); el.setAttribute("aria-selected", on ? "true" : "false"); };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// stateHues() now lives in lib.js (pure, tested) — imported above.

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
    if (r.ok) { state.results = await r.json(); enableMode("parti"); paint(); renderSummary(); renderNatGlance(); }
  } catch (_) {}
  try {
    // DUN (state-assembly / PRN) results, where Thevesh publishes them (the 6-state
    // 2023 PRN today). Per-seat: a DUN seat with an entry shows its own result; one
    // without keeps the parent-Parliament fallback + "PRN coming soon" note.
    const rd = await fetch("data/results-dun.json");
    if (rd.ok) state.resultsDun = await rd.json();
  } catch (_) {}
  try {
    const s = await fetch("data/scores.json");
    // AGENTS.md UNTOUCHABLE: "Keep Skor GATED ('Soon') even if scores.json appears."
    // Load the scores (panel score row + seatValueColor skor branch use them) but
    // NEVER enableMode("skor") — the tab stays disabled with its "Soon/Segera" pill.
    if (s.ok) { state.scores = await s.json(); }
  } catch (_) {}
  try {
    const c = await fetch("data/candidates-ge15.json");
    if (c.ok) state.candidates = await c.json();
  } catch (_) {}
  try {
    const cd = await fetch("data/candidates-dun-prn15.json");
    if (cd.ok) state.candidatesDun = await cd.json();
  } catch (_) {}
  try {
    const vg = await fetch("data/voting-guide.json");
    if (vg.ok) state.votingGuide = await vg.json();
  } catch (_) {}
  try {
    // live election (PRN16 Johor): config + SPR-confirmed candidates, baked by
    // pipeline/05_prn16_johor.py. Its presence turns the election mode on.
    const pj = await fetch("data/prn16-johor.json");
    if (pj.ok) state.prn16 = await pj.json();
  } catch (_) {}
  try {
    // per-state context: MB/KM/Premier + election clock (pipeline/07_state_context.py)
    const sc = await fetch("data/state-context.json");
    if (sc.ok) state.stateCtx = await sc.json();
  } catch (_) {}
  try {
    // per-state economy report card, DOSM via data.gov.my (pipeline/08_state_econ.py)
    const se = await fetch("data/state-econ.json");
    if (se.ok) state.stateEcon = await se.json();
  } catch (_) {}
  try {
    // campaign-window headlines per PRN candidate (pipeline/06_candidate_news.py)
    const cn = await fetch("data/candidate-news-johor.json");
    if (cn.ok) state.prnNews = await cn.json();
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

// ---- entrance motion: compositor-only fade + slide for continuity on drill-down.
// Branches on reduced-motion (keep a gentle fade, drop the travel) per a11y. ----
const REDUCE_MOTION = matchMedia("(prefers-reduced-motion: reduce)");
const ANIM_OFF = false;   // motion is on by default; prefers-reduced-motion still gets the reduced path
function animateIn(el, dist = 10) {
  if (ANIM_OFF) return;
  if (!el || !el.animate) return;
  if (REDUCE_MOTION.matches) {
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 120, easing: "linear" });
    return;
  }
  el.animate(
    [{ opacity: 0, transform: `translateY(${dist}px)` }, { opacity: 1, transform: "none" }],
    { duration: 300, easing: "cubic-bezier(0,0,0.2,1)" }
  );
}

function animationDone(animation, duration) {
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    animation.onfinish = done;
    animation.oncancel = done;
    setTimeout(done, duration + 80);
  });
}

const nextFrame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));

function setPanelView(view) {
  PANEL.classList.toggle("empty", view === "overview");
  PANEL.classList.toggle("state-summary", view === "state");
  PANEL.classList.toggle("seat-detail", view === "seat");
  PANEL_EMPTY.hidden = view !== "overview";
  PANEL_STATE.hidden = view === "overview";
  PANEL_SEAT.hidden = true;
  if (STATE_ACTIONS) STATE_ACTIONS.hidden = view !== "seat";
  requestAnimationFrame(syncMapToCard);
}

// One clock for the More-pop: viewBox zoom and card rise run this duration with the
// same decelerate curve so they read as a single coordinated move.
const DETAIL_POP_MS = 600;
const DETAIL_POP_EASE = "cubic-bezier(0,0,0.2,1)";
// Danial's choreography for the district-detail pop: card pops DOWN, card pops UPWARD,
// and only once the rise is clearly underway does the state start shrinking — it lags
// the card by DELAY and catches up with a shorter glide so both settle together.
const DETAIL_GLIDE_DELAY_MS = 200;
const DETAIL_GLIDE_MS = 430;
let detailGlideTimer = null;
// JS twin of DETAIL_POP_EASE for the rAF viewBox glide — the map camera and the card's
// WAAPI rise must follow the IDENTICAL progress curve or the composite reads as two moves.
function cubicBezierEase(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const sampleX = (t) => ((ax * t + bx) * t + cx) * t;
  const sampleY = (t) => ((ay * t + by) * t + cy) * t;
  return (x) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let lo = 0, hi = 1, t = x;
    for (let i = 0; i < 24; i++) {
      t = (lo + hi) / 2;
      if (sampleX(t) < x) lo = t; else hi = t;
    }
    return sampleY(t);
  };
}
const DETAIL_POP_EASE_FN = cubicBezierEase(0, 0, 0.2, 1);

function animateRectFlip(el, first, last, duration = 360, easing = "cubic-bezier(0.4,0,0.2,1)") {
  if (!el || !el.animate || !first || !last || last.width <= 0 || last.height <= 0) return;
  const dx = first.left - last.left;
  const dy = first.top - last.top;
  const sx = first.width / last.width;
  const sy = first.height / last.height;
  if (Math.abs(dx) < 1 && Math.abs(dy) < 1 && Math.abs(sx - 1) < 0.01 && Math.abs(sy - 1) < 0.01) return;
  const prevOrigin = el.style.transformOrigin;
  const prevWillChange = el.style.willChange;
  el.style.transformOrigin = "top left";
  el.style.willChange = "transform, opacity";
  const a = el.animate(
    [
      { transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`, opacity: 0.98 },
      { transform: "translate(0, 0) scale(1, 1)", opacity: 1 }
    ],
    { duration, easing }
  );
  const done = () => {
    el.style.transformOrigin = prevOrigin;
    el.style.willChange = prevWillChange;
  };
  a.onfinish = done; a.oncancel = done;
  setTimeout(done, duration + 80);
}

// Smoothly grow/shrink the bottom card to fit new content (make-up ⇄ district detail).
// The map band is resized by layout, so use FLIP transforms on both the card and map to
// make the final layout feel like one coordinated move.
function animateCardResize(card, mutate) {
  if (ANIM_OFF) { mutate(); syncMapToCard(); return; }
  if (!card || !card.animate || REDUCE_MOTION.matches) {
    mutate();
    syncMapToCard();
    return;
  }
  const firstCard = card.getBoundingClientRect();
  const firstMap = SVG.getBoundingClientRect();
  mutate();
  syncMapToCard();
  const lastCard = card.getBoundingClientRect();
  const lastMap = SVG.getBoundingClientRect();
  animateRectFlip(card, firstCard, lastCard, 380);
  animateRectFlip(SVG, firstMap, lastMap, 420);
}

// onLayout (optional) fires once the swapped-in layout is real, with the map's pre/post
// layout rects, so callers can launch a concurrent viewBox move and the map shrinks /
// reframes IN STEP with the card's rise instead of jumping after it. Return true from
// onLayout to own the map's motion entirely (skips the element FLIP — a viewBox-only
// camera move has no scaleY distortion).
async function swapCardWithMinimizePop(card, mutate, onLayout) {
  if (ANIM_OFF || !card || !card.animate || REDUCE_MOTION.matches) {
    mutate();
    syncMapToCard();
    if (onLayout) onLayout();
    return;
  }
  const prevOrigin = card.style.transformOrigin;
  const prevWillChange = card.style.willChange;
  const prevTransform = card.style.transform;
  const prevOpacity = card.style.opacity;
  card.getAnimations().forEach((animation) => animation.cancel());
  card.style.transformOrigin = "bottom center";
  card.style.willChange = "transform, opacity";
  try {
    const exitDuration = 220;
    const exit = card.animate(
      [
        { transform: "scaleY(1)", opacity: 1 },
        { transform: "scaleY(0.08)", opacity: 0 }
      ],
      { duration: exitDuration, easing: "cubic-bezier(0.4,0,1,1)", fill: "forwards" }
    );
    await animationDone(exit, exitDuration);
    card.style.transform = "scaleY(0.08)";
    card.style.opacity = "0";
    exit.cancel();

    const firstMap = SVG.getBoundingClientRect();
    mutate();
    syncMapToCard();
    const lastMap = SVG.getBoundingClientRect();
    const mapHandled = onLayout ? onLayout(firstMap, lastMap) : false;
    if (!mapHandled) animateRectFlip(SVG, firstMap, lastMap, DETAIL_POP_MS, DETAIL_POP_EASE);
    await nextFrame();

    // Single-segment rise (no overshoot): the card's scaleY tracks the exact same
    // progress curve as the map's FLIP, so both travel and settle together.
    const enterDuration = DETAIL_POP_MS;
    const enter = card.animate(
      [
        { offset: 0, transform: "scaleY(0.08)", opacity: 0 },
        { offset: 0.35, opacity: 1 },
        { offset: 1, transform: "scaleY(1)", opacity: 1 }
      ],
      { duration: enterDuration, easing: DETAIL_POP_EASE, fill: "forwards" }
    );
    await animationDone(enter, enterDuration);
    enter.cancel();
  } finally {
    card.style.transformOrigin = prevOrigin;
    card.style.willChange = prevWillChange;
    card.style.transform = prevTransform;
    card.style.opacity = prevOpacity;
  }
}

// Keep the map in the visible band between the top chrome and the bottom card. When
// the viewport is short, cap the card and let it scroll before it can cover the map.
function syncMapToCard() {
  const root = document.documentElement;
  const stageRect = STAGE.getBoundingClientRect();
  const viewportH = Math.floor((window.visualViewport && window.visualViewport.height) || window.innerHeight);
  const inspecting = !!(state.mapInspect && MOBILE_MAP_INSPECT_MQ.matches);
  // the topbar is visible in every mode (logo + menu at all times) — the band always
  // starts below it; inspect mode just tucks a little closer.
  const chromeBottom = Math.max(
    TOPBAR ? TOPBAR.getBoundingClientRect().bottom : 0,
    TOP_CONTROLS ? TOP_CONTROLS.getBoundingClientRect().bottom : 0
  );
  let topInset = Math.max(0, Math.ceil(chromeBottom - stageRect.top + (inspecting ? 8 : 12)));
  // Mobile district detail: the state title is pinned just under the topbar, so the map
  // band starts BELOW it — the shrunken state then centers between the title and the card.
  if (MOBILE_MAP_INSPECT_MQ.matches && PANEL.classList.contains("seat-detail") && state.openState) {
    const labelH = (STATE_LABEL && STATE_LABEL.getBoundingClientRect().height) || 30;
    topInset = Math.max(0, Math.ceil(chromeBottom - stageRect.top + 6 + labelH + 8));
  }
  const panelStyle = getComputedStyle(PANEL);
  const panelPadBottom = parseFloat(panelStyle.paddingBottom) || 0;
  const gap = 12;
  const narrow = matchMedia("(max-width: 860px)").matches;
  // While the on-screen keyboard is up (searching), the map surrenders its minimum —
  // the shrunken visual viewport belongs to the card so the search box stays visible.
  const kbOpen = keyboardInset > 60;
  // Desktop/landscape: the state card is now content-rich (stats + economy + context),
  // so give the map a generous share (~40% of the viewport) instead of a fixed 160px —
  // otherwise a wide state like Sarawak reads as a squashed sliver and the card scrolls
  // its whole height. On desktop there's plenty of vertical room to spend.
  const preferredMinMapH = kbOpen ? 0
    : (inspecting ? Math.floor(viewportH * 0.72)
    : (narrow ? 144 : Math.floor(viewportH * 0.40)));
  const viewportBoundMin = kbOpen ? 0 : Math.max(96, Math.floor((viewportH - topInset - panelPadBottom - gap) * 0.42));
  const minMapH = Math.min(preferredMinMapH, viewportBoundMin);
  const cardMaxH = Math.max(120, Math.floor(viewportH - topInset - minMapH - gap - panelPadBottom));

  root.style.setProperty("--map-top", `${topInset}px`);
  root.style.setProperty("--panel-card-max-h", `${cardMaxH}px`);

  const activeCard = !PANEL_STATE.hidden ? PANEL_STATE : (!PANEL_EMPTY.hidden ? PANEL_EMPTY : PANEL_SEAT);
  if (!activeCard || !activeCard.getClientRects().length) return;
  // LAYOUT top, not rect top: the card is bottom-anchored in #panel (flex-end), so its
  // untransformed top = panel bottom − panel padding − its layout height. A mid-animation
  // card (minimize-pop holds scaleY 0.08) would otherwise report a near-bottom rect and
  // blow the map band up to fill the gap — the band must track where the card WILL rest.
  const cardTop = PANEL.getBoundingClientRect().bottom - panelPadBottom - activeCard.offsetHeight;
  const mapH = Math.max(0, Math.floor(cardTop - stageRect.top - topInset - gap));
  root.style.setProperty("--map-h", `${mapH}px`);
  requestAnimationFrame(() => { syncStageLabelPosition(); syncSelectedTexture(); syncLiveBadge(); });
}

function mobileMenuOpen() {
  return document.body.classList.contains("mobile-menu-open");
}
function setMobileMenu(open) {
  if (!MOBILE_MENU || !MOBILE_MENU_BTN) return;
  if (open) hideInfo();
  document.body.classList.toggle("mobile-menu-open", open);
  MOBILE_MENU_BTN.setAttribute("aria-expanded", open ? "true" : "false");
  if (!open) requestAnimationFrame(syncMapToCard);
}
MOBILE_MENU_BTN?.addEventListener("click", (e) => {
  e.stopPropagation();
  setMobileMenu(!mobileMenuOpen());
});
MOBILE_MENU?.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (btn && !btn.disabled) setMobileMenu(false);
});
document.addEventListener("click", (e) => {
  if (!mobileMenuOpen()) return;
  if (MOBILE_MENU?.contains(e.target) || MOBILE_MENU_BTN?.contains(e.target)) return;
  setMobileMenu(false);
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !mobileMenuOpen()) return;
  e.preventDefault();
  e.stopPropagation();
  setMobileMenu(false);
}, true);

// the backdrop card, choreographed to FOLLOW the isolate/zoom (a delay lets the state
// lead): it starts MINIMIZED (a thin bar at the bottom) and springs UPWARD, growing into
// the backdrop with an overshoot bounce (transform-origin: bottom). Compositor-only
// (scaleY + opacity). Reduced-motion: a plain delayed fade — no scale, no bounce.
function riseCard(el, delay = 260) {
  if (ANIM_OFF) return;
  if (!el || !el.animate) return;
  if (REDUCE_MOTION.matches) {
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160, delay, fill: "backwards" });
    return;
  }
  el.animate([
    { offset: 0,    transform: "scaleY(0.05)", opacity: 0.25, easing: "cubic-bezier(0.34, 1.5, 0.64, 1)" }, // minimized → spring up
    { offset: 0.45, opacity: 1 },                                                                           // content faded in by mid-rise
    { offset: 1,    transform: "scaleY(1)",    opacity: 1 },                                                 // bounced up to full
  ], { duration: 660, delay, fill: "backwards" });
}

// MINIMIZE the overview card down to a bar (we watch it collapse) before the state
// backdrop springs up from that same point. Compositor-only (scaleY + opacity).
function minimizeCard(el) {
  if (ANIM_OFF) return;
  if (!el || !el.animate) return;
  if (REDUCE_MOTION.matches) { el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 120, fill: "forwards" }); return; }
  el.animate([
    { transform: "scaleY(1)",    opacity: 1, offset: 0 },
    { transform: "scaleY(0.4)",  opacity: 1, offset: 0.55 },   // visibly shrinking
    { transform: "scaleY(0.05)", opacity: 0, offset: 1 },      // collapsed to a faded bar
  ], { duration: 300, easing: "cubic-bezier(0.5, 0, 0.75, 0)", fill: "forwards" });
}

// ---- rendering ----
let hoverState = null;   // name of the state currently lit up under the cursor (mouse only)
async function render(tier) {
  const data = await loadTier(tier);
  SVG.setAttribute("viewBox", data.viewBox);
  viewBox = data.viewBox.split(" ").map(Number);
  SEATS.innerHTML = "";
  if (SELECTED_OVERLAY) SELECTED_OVERLAY.replaceChildren();
  state.paths.clear();
  hoverState = null;   // paths are rebuilt → any prior hover highlight is gone

  const frag = document.createDocumentFragment();
  // DUN tier has no federal-territory seats (KL / Putrajaya / Labuan have no state assembly),
  // which would otherwise leave black holes in the map. Underlay those FT areas using the
  // Parliament geometry (identical FROZEN projection) as muted, non-interactive
  // "no state assembly" shapes — so the map reads as complete, not broken.
  if (tier === "dun") {
    const pdata = await loadTier("parlimen");
    for (const seat of pdata.seats) {
      if (!(seat.state || "").startsWith("W.P.")) continue;   // W.P. Kuala Lumpur / Putrajaya / Labuan
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", seat.d);
      p.setAttribute("class", "seat no-dun");
      frag.appendChild(p);
    }
  }
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
  requestAnimationFrame(syncMapToCard);
  animateIn(SEATS, 0);   // the map arrives with a soft fade (opacity only on the group)
}

// A DUN seat's OWN state-election (PRN) result, when we have one (the states in
// results-dun.json). Undefined for parlimen tier or an uncovered DUN seat.
function ownDunResult(seat) {
  return state.tier !== "parlimen" && state.resultsDun ? state.resultsDun[seat.code] : undefined;
}
// The result to DISPLAY for a seat: a DUN seat shows its own PRN result where it
// exists, otherwise falls back to the parent Parliament GE15 result.
function resultFor(seat) {
  return ownDunResult(seat) || (state.results && state.results[resultKey(seat, state.tier)]);
}

// State-level rollups must not multiply parent-Parliament fallback rows across DUN
// seats. Parliament uses GE15 rows; DUN aggregates only use real DUN result rows.
function stateSummaryResultFor(seat) {
  return state.tier === "parlimen" ? resultFor(seat) : ownDunResult(seat);
}

function seatValueColor(seat) {
  const data = state.data[state.tier];
  // live-election view: the contested state's seats are "not yet voted" neutral
  // until results flow in on polling night (grey → leading translucent → won solid).
  if (state.prnMode && liveElection() && seat.state === liveElection().state && state.tier === liveElection().tier) {
    const lr = state.prnLive && state.prnLive.seats && state.prnLive.seats[seat.code];
    const p = state.paths.get(seat.code);
    if (lr && (lr.coalition || lr.party)) {
      if (p) p.style.fillOpacity = lr.status === "leading" ? "0.45" : "";
      return prnCoalColor(lr.coalition || lr.party).bg;
    }
    if (p) p.style.fillOpacity = "";
    return "#39404c";
  }
  if (state.mode === "parti" && state.results) {
    const r = resultFor(seat);
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
    if (p) {
      if (!state.prnMode) p.style.fillOpacity = "";   // live-night "leading" translucency is PRN-only
      p.style.fill = seatValueColor(seat);
    }
  }
  // re-apply selection styling
  if (state.selected) setSelectedDistrict(state.selected);
}

function clearSelectedDistrict() {
  SEATS.querySelectorAll(".seat.sel").forEach((p) => p.classList.remove("sel"));
  if (SELECTED_OVERLAY) SELECTED_OVERLAY.replaceChildren();
}

function setSelectedDistrict(code) {
  clearSelectedDistrict();
  const sel = state.paths.get(code);
  if (!sel) return;
  sel.classList.add("sel");
  if (!SELECTED_OVERLAY) return;
  const overlay = document.createElementNS("http://www.w3.org/2000/svg", "path");
  overlay.setAttribute("d", sel.getAttribute("d") || "");
  overlay.setAttribute("class", "selected-texture");
  overlay.setAttribute("data-code", code);
  SELECTED_OVERLAY.appendChild(overlay);
  syncSelectedTexture();
}

// The stripe pattern is defined in map user units, but the frozen projection means px-per-
// unit varies ~20× between a zoomed-in W.P. and a whole-Malaysia view — fixed user-unit
// stripes render as a solid blob on small states. Re-derive the pattern from the CURRENT
// render scale so the stripes are always ~1px thin and ~5px apart ON SCREEN, everywhere.
const SEL_TEX_PATTERN = document.getElementById("selected-district-lines");
const SEL_TEX_LINE = SEL_TEX_PATTERN && SEL_TEX_PATTERN.querySelector("path");
const SEL_TEX_SPACING_PX = 5;   // stripe pitch on screen
const SEL_TEX_WIDTH_PX = 1;     // stripe thickness on screen
function syncSelectedTexture() {
  if (!SEL_TEX_PATTERN || !SEL_TEX_LINE || !SELECTED_OVERLAY || !SELECTED_OVERLAY.childElementCount) return;
  const r = SVG.getBoundingClientRect();
  if (!(r.width > 0) || !(viewBox[2] > 0) || !(viewBox[3] > 0)) return;
  const k = Math.min(r.width / viewBox[2], r.height / viewBox[3]);   // meet scale: px per unit
  if (!Number.isFinite(k) || k <= 0) return;
  const cell = (SEL_TEX_SPACING_PX / k).toFixed(4);
  SEL_TEX_PATTERN.setAttribute("width", cell);
  SEL_TEX_PATTERN.setAttribute("height", cell);
  SEL_TEX_LINE.setAttribute("d", `M0 0V${cell}`);
  SEL_TEX_LINE.setAttribute("stroke-width", (SEL_TEX_WIDTH_PX / k).toFixed(4));
}

// ---- viewBox zoom (lerp) ----
let animId = null;
function animateTo(target, ms = 480, ease = (t) => 1 - Math.pow(1 - t, 3)) {
  cancelAnimationFrame(animId);
  if (ANIM_OFF || REDUCE_MOTION.matches) {   // animations off / a11y: jump straight to the frame
    viewBox = target.slice();
    SVG.setAttribute("viewBox", viewBox.map((n) => n.toFixed(2)).join(" "));
    syncStageLabelPosition();
    syncSelectedTexture();
    syncLiveBadge();
    return;
  }
  const start = viewBox.slice();
  const t0 = performance.now();
  function step(now) {
    const k = Math.min(1, (now - t0) / ms);
    const e = ease(k);
    viewBox = start.map((v, i) => v + (target[i] - v) * e);
    SVG.setAttribute("viewBox", viewBox.map((n) => n.toFixed(2)).join(" "));
    syncStageLabelPosition();
    syncSelectedTexture();
    syncLiveBadge();
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
// the viewBox that frames a whole state into the upper part of the map (state centre
// ~37% down). Aspect-matched so preserveAspectRatio won't distort. Returns [x,y,w,h].
function stateFrameAspect() {
  const mapRect = SVG.getBoundingClientRect();
  const aspect = mapRect.width > 0 && mapRect.height > 0 ? mapRect.width / mapRect.height : null;
  if (state.openState && matchMedia("(max-width: 860px)").matches && Number.isFinite(aspect) && aspect > 0) {
    return aspect;
  }
  return FULL[2] / FULL[3];
}
function stateViewBox(name) {
  const b = stateBBox(name);
  const pad = Math.max(b.w, b.h) * 0.06 + 2;
  let w = b.w + pad * 2, h = b.h + pad * 2;
  const ar = stateFrameAspect();
  if (w / h > ar) h = w / ar; else w = h * ar;
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  // The map now has its own reserved band above the card on every viewport, so centre
  // the state in that band instead of biasing it upward under the top chrome.
  const anchor = 0.5;
  return [cx - w / 2, cy - anchor * h, w, h];
}
function zoomToState(name, ms = 540, ease = undefined) { animateTo(stateViewBox(name), ms, ease); }

// The state's bottom edge in screen px, at its FINAL zoom — computed deterministically
// from the target viewBox + the SVG's preserveAspectRatio="xMidYMid meet", so it is
// correct on ANY viewport and even before the zoom animation has settled (no measuring).
function stateBottomScreenY(name) {
  const b = stateBBox(name);
  const vb = stateViewBox(name);
  const mr = SVG.getBoundingClientRect();
  const scale = Math.min(mr.width / vb[2], mr.height / vb[3]);   // "meet": fit, don't crop
  const offsetY = (mr.height - vb[3] * scale) / 2;               // letterbox top/bottom
  return mr.top + offsetY + ((b.y + b.h) - vb[1]) * scale;
}
function currentStateTopScreenY(name) {
  const b = stateBBox(name);
  const mr = SVG.getBoundingClientRect();
  const scale = Math.min(mr.width / viewBox[2], mr.height / viewBox[3]);
  const offsetY = (mr.height - viewBox[3] * scale) / 2;
  return mr.top + offsetY + (b.y - viewBox[1]) * scale;
}

// Previous layouts pinned card text below the visible state. The card is now independent
// and bottom-anchored, so content should size naturally inside the card.
function pinBelowState(sb) {
  STATE_INFO.style.height = "";
  STATE_INFO.style.overflowY = "";
}
// GROUND TRUTH: where the visible state actually ends on screen right now.
function visibleStateBottom() {
  const ins = SEATS.querySelectorAll(".seat.instate");
  if (!ins.length) return null;
  let sb = -Infinity;
  ins.forEach((p) => { const r = p.getBoundingClientRect(); if (r.bottom > sb) sb = r.bottom; });
  return isFinite(sb) ? sb : null;
}
// Deterministic — for the IMMEDIATE reveal: correct for the FINAL frame even mid-zoom.
function fitContentBelowState() {
  if (!state.openState || !PANEL_STATE.getClientRects().length) return;
  pinBelowState(stateBottomScreenY(state.openState));
}
// Measured — used once the state has SETTLED (and on resize / font swap): uses the real
// render, so it cannot be wrong about where the state is, whatever the viewport.
function refitMeasured() {
  if (!state.openState || !PANEL_STATE.getClientRects().length) return;
  const sb = visibleStateBottom();
  if (sb != null) pinBelowState(sb);
}

// Re-pin when the viewport changes while a state is open (rotation, resize, iOS URL-bar)
// and after a late webfont swap reflows the header — otherwise the pin goes stale.
let refitTimer = null;
function scheduleRefit() {
  if (!state.openState) return;
  clearTimeout(refitTimer);
  refitTimer = setTimeout(refitMeasured, 120);
}
addEventListener("resize", scheduleRefit);
addEventListener("resize", () => { syncMapToCard(); refitOpenStateMap(60); });            // re-fit the map above the card on resize
addEventListener("orientationchange", scheduleRefit);
addEventListener("orientationchange", () => { syncMapToCard(); refitOpenStateMap(80); });
if (window.visualViewport) visualViewport.addEventListener("resize", scheduleRefit);
if (window.visualViewport) visualViewport.addEventListener("resize", () => { syncMapToCard(); refitOpenStateMap(60); });

// iOS keyboard: the on-screen keyboard shrinks the VISUAL viewport while position:fixed
// elements track the LAYOUT viewport — the bottom card (with the focused search box)
// would hide behind the keyboard and Safari scroll-jumps the page hunting for the input.
// Lift the panel by the keyboard inset (--kb-inset, see styles.css) and keep the page
// pinned at origin so the app never displaces.
let keyboardInset = 0;
function syncKeyboardInset() {
  const vv = window.visualViewport;
  if (!vv) return;
  keyboardInset = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop));
  document.documentElement.style.setProperty("--kb-inset", `${keyboardInset}px`);
  // iOS freezes position:fixed anchoring while the keyboard is open — a bottom offset
  // is visually ignored there. A compositor transform is not: lift the whole panel.
  PANEL.style.transform = keyboardInset > 0 ? `translateY(-${keyboardInset}px)` : "";
  if (keyboardInset > 0 && (window.scrollY || window.scrollX)) window.scrollTo(0, 0);
  syncMapToCard();
  kbDebugHud();
}
if (window.visualViewport) {
  visualViewport.addEventListener("resize", syncKeyboardInset);
  visualViewport.addEventListener("scroll", syncKeyboardInset);
}
// iOS viewport events around the keyboard are flaky (some fire mid-animation, some not
// at all on certain versions) — while the search box is focused, FOLLOW the visual
// viewport every frame instead of trusting events. Cheap: runs only while typing.
let kbRaf = 0;
function kbFollowLoop() {
  const vv = window.visualViewport;
  if (vv) {
    const kb = Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop));
    if (kb !== keyboardInset) {
      syncKeyboardInset();          // full re-layout only when the inset actually changes
    } else if (kb > 0) {
      PANEL.style.transform = `translateY(-${kb}px)`;   // re-pin in case anything cleared it
      if (window.scrollY || window.scrollX) window.scrollTo(0, 0);
    }
  }
  kbRaf = document.activeElement === SEARCH_INPUT ? requestAnimationFrame(kbFollowLoop) : 0;
}
// on-device debug readout: open the app with ?kbdebug to see the live viewport numbers
const KB_DEBUG = new URLSearchParams(location.search).has("kbdebug");
let kbHudEl = null;
function kbDebugHud() {
  if (!KB_DEBUG) return;
  if (!kbHudEl) {
    kbHudEl = document.createElement("div");
    kbHudEl.style.cssText = "position:fixed;top:70px;left:8px;z-index:99;background:rgba(0,0,0,.85);color:#9f9;font:11px/1.5 monospace;padding:6px 8px;border-radius:6px;pointer-events:none;white-space:pre";
    document.body.appendChild(kbHudEl);
  }
  const vv = window.visualViewport;
  kbHudEl.textContent = `ih ${window.innerHeight}\nvvH ${vv ? Math.round(vv.height) : "-"}\nvvTop ${vv ? Math.round(vv.offsetTop) : "-"}\nkb ${keyboardInset}\nscrollY ${Math.round(window.scrollY)}\ntf ${PANEL.style.transform || "none"}`;
}
// Safari-only gesture events: block page pinch-zoom entirely — the UI is an app, not a document
document.addEventListener("gesturestart", (e) => e.preventDefault());

// Typing in "Search a seat": the keyboard-shrunken card belongs to the search box —
// hide the national stats above it (they pushed the input below the card's fold).
// The class lifts on blur AFTER a beat, so a tap on a result lands before re-layout.
let searchBlurTimer = null;
const SEARCH_INPUT = document.getElementById("q");
SEARCH_INPUT?.addEventListener("focus", () => {
  clearTimeout(searchBlurTimer);
  document.body.classList.add("searching");
  requestAnimationFrame(syncMapToCard);
  cancelAnimationFrame(kbRaf);
  kbRaf = requestAnimationFrame(kbFollowLoop);   // track the keyboard frame-by-frame while typing
});
SEARCH_INPUT?.addEventListener("blur", () => {
  clearTimeout(searchBlurTimer);
  searchBlurTimer = setTimeout(() => {
    document.body.classList.remove("searching");
    syncKeyboardInset();          // keyboard gone → clears the transform + restores the band
  }, 250);
  setTimeout(syncKeyboardInset, 700);   // belt-and-braces after the close animation
});
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { if (state.openState) refitMeasured(); syncMapToCard(); });

// ---- selection + panel ----
function select(code) {
  const seat = state.data[state.tier] && state.data[state.tier].byCode.get(code);
  if (!seat) return;
  openStateCard(seat.state);
  showDistrict(code);
  dismissHint();
}
function deselect() { backToControls(); }

// "P.140 · Segamat" for a DUN seat — the parliament dataset is already cached in DUN
// tier (the FT underlays load it); degrades to the bare code if it isn't.
function parlimenContext(seat) {
  if (!seat || !seat.parlimen) return "";
  const pd = state.data.parlimen;
  const p = pd && pd.byCode.get(seat.parlimen);
  return p ? `${seat.parlimen} · ${p.name}` : seat.parlimen;
}

function seatCardHTML(seat, options = {}) {
  const includeDistrictSwitcher = !!options.includeDistrictSwitcher;
  const showStateLine = options.showStateLine !== false;
  if (!isSeatTab(state.seatTab)) state.seatTab = "overview";
  const isP = state.tier === "parlimen";
  const kicker = isP ? `${t("kicker_parlimen")} · ${seat.code}` : `DUN · ${seat.dun_code}`;
  const r = resultFor(seat);
  const ownDun = !!ownDunResult(seat);          // a real PRN result (not the parent fallback)?
  const sc = state.scores && state.scores[resultKey(seat, state.tier)];
  const card = r ? formatResultCard(r) : null;
  const resultSource = r ? `<div class="src-line muted">${esc(t(ownDun ? "src_prn15" : "src_ge15"))}</div>` : "";
  const dunNote = (!isP && !ownDun)
    ? `<div class="note">${t("dun_note", { p: `<b>${esc(seat.parlimen)}</b>` })}</div>`
    : "";

  let repRows = "";
  let resultRows = "";
  let overviewHTML = "";
  if (r) {
    // formatResultCard runs every numeric through a Number.isFinite guard (non-finite
    // → null) and composes party / candidate / runner-up shaping. Driving the panel
    // off the card means a partial row — vote_pct present but votes missing, a NaN or
    // string numeric — OMITS the row instead of rendering "NaN"/"undefined". Real GE15
    // data is complete today; this is defensive for future / DUN result data.
    const blocPill = `<span class="pill" style="background:${partyColor(r.coalition)};color:#fff">${esc(r.coalition)}</span>`;
    // surface party_full ("Perikatan Nasional (PN)") via the pure helper; only show
    // it when it adds something beyond the bloc pill (skip a redundant "PN · PN")
    const partyLabel = card.party && card.party.label && card.party.label !== r.coalition ? esc(card.party.label) : "";
    // keep the "· <pill>" together so the pill never orphans onto its own line on mobile
    const blocUnit = `<span class="bloc-unit">${partyLabel ? "· " : ""}${blocPill}</span>`;

    repRows += `<dt>${t("rep")}</dt><dd>${esc(r.name)}</dd>`;
    repRows += `<dt>${t("party_bloc")}</dt><dd>${partyLabel ? partyLabel + " " : ""}${blocUnit}</dd>`;
    if (card.majority != null)
      resultRows += `<dt>${t(ownDun ? "majority_prn" : "majority")}</dt><dd class="mono">${card.majority.toLocaleString()}${card.majorityPct != null ? ` <span class="muted">(${card.majorityPct}%)</span>` : ""}</dd>`;
    if (card.votes != null)
      resultRows += `<dt>${t("win_votes")}</dt><dd class="mono">${card.votes.toLocaleString()}${card.votePct != null ? ` <span class="muted">(${card.votePct}%)</span>` : ""}</dd>`;
    if (card.turnout != null)
      resultRows += `<dt>${t("turnout")}</dt><dd class="mono">${card.turnout}%</dd>`;
    if (card.candidates != null)
      resultRows += `<dt>${t("candidates")}</dt><dd class="mono">${card.candidates}</dd>`;
    const ru = card.runnerUp;
    if (ru) {
      const ruPill = ru.party
        ? ` <span class="pill" style="background:${partyColor(ru.party === r.party ? r.coalition : ru.party)};color:#fff;opacity:.85">${esc(ru.party)}</span>`
        : "";
      // now also surfaces runner_up.votes (panel previously showed only name + party)
      const ruVotes = ru.votes != null ? ` <span class="muted">${ru.votes.toLocaleString()}</span>` : "";
      resultRows += `<dt>${t("runner")}</dt><dd>${esc(ru.name || "")}${ruPill}${ruVotes}</dd>`;
    }

    const metric = (label, value, note = "") => (
      `<div class="seat-metric"><span>${esc(label)}</span><b>${value}</b>${note ? `<small>${note}</small>` : ""}</div>`
    );
    const metrics = [];
    if (card.majority != null)
      metrics.push(metric(t(ownDun ? "majority_prn" : "majority"), card.majority.toLocaleString(), card.majorityPct != null ? `${card.majorityPct}%` : ""));
    if (card.turnout != null) metrics.push(metric(t("turnout"), `${card.turnout}%`));
    if (card.candidates != null) metrics.push(metric(t("candidates"), card.candidates));
    overviewHTML = `
      <div class="seat-overview">
        <div class="seat-yb-card">
          <span>${esc(t("card_current_yb"))}</span>
          <strong>${esc(r.name)}</strong>
          <p>${partyLabel ? partyLabel + " " : ""}${blocUnit}</p>
        </div>
        ${metrics.length ? `<div class="seat-metrics">${metrics.join("")}</div>` : ""}
      </div>
      ${sc ? `<dl class="rows seat-score-row"><dt>${t("score")}</dt><dd class="mono"><b style="color:var(--accent-2)">${sc.score.toFixed(1)}</b> · ${esc(sc.grade || "")}</dd></dl>` : ""}
      ${resultSource}
      ${dunNote}
    `;
  } else {
    repRows += `<dt>${t("rep")}</dt><dd class="placeholder">${t("rep_ph")}</dd>`;
    overviewHTML = moduleEmptyHTML("overview");
  }

  if (sc) {
    repRows += `<dt>${t("score")}</dt><dd class="mono"><b style="color:var(--accent-2)">${sc.score.toFixed(1)}</b> · ${esc(sc.grade || "")}</dd>`;
  }

  const active = state.seatTab;
  let panelHTML = "";
  if (active === "overview") {
    panelHTML = overviewHTML;
  } else if (active === "results") {
    panelHTML = r
      ? `<dl class="rows">${repRows}${resultRows}</dl>${resultSource}${dunNote}`
      : `${moduleEmptyHTML("results")}${!r && isP ? `<div class="note">${t("score_building")}</div>` : ""}`;
  } else if (active === "candidates") {
    panelHTML = candidatesHTML(seat);
  } else if (active === "voting") {
    panelHTML = votingGuideHTML();
  } else {
    panelHTML = moduleEmptyHTML(active);
  }

  return `
    <div class="seat-detail-main">
      <div class="seat-head">
        <div class="kicker">${esc(kicker)}</div>
        <h2>${esc(seat.name)}</h2>
        ${showStateLine ? `<div class="where">${t("state_label")} <b>${esc(seat.state)}</b></div>` : ""}
        ${!isP && seat.parlimen ? `<div class="where">${esc(t("parlimen_label"))} <b>${esc(parlimenContext(seat))}</b></div>` : ""}
      </div>
      ${seatTabsHTML(active)}
      <div id="seat-tabpanel-${esc(active)}" class="seat-tabpanel" role="tabpanel" aria-labelledby="seat-tab-${esc(active)}">
        ${panelHTML}
      </div>
    </div>
    ${includeDistrictSwitcher ? seatDistrictSwitcherHTML(seat.code) : ""}
  `;
}

function stateSeatCardHTML(seat) {
  // live-election view: the seat card IS the PRN candidate card (the GE15/PRN15
  // fallback stays available outside the election mode)
  if (state.prnMode && liveElection() && seat.state === liveElection().state && state.tier === liveElection().tier) {
    const entry = state.prn16.seats && state.prn16.seats[seat.code];
    if (entry) {
      const switcher = state.openState && MOBILE_MAP_INSPECT_MQ.matches ? seatDistrictSwitcherHTML(seat.code) : "";
      return `<div class="seat-detail-main">${prnSeatCardHTML(seat, entry)}</div>${switcher}`;
    }
  }
  return seatCardHTML(seat, {
    includeDistrictSwitcher: !!(state.openState && MOBILE_MAP_INSPECT_MQ.matches),
    showStateLine: false,
  });
}

function seatTabsHTML(active) {
  return `
    <div class="seat-tabs" role="tablist" aria-label="${esc(t("seat_tabs_aria"))}">
      ${SEAT_TABS.map((tab) => `
        <button id="seat-tab-${esc(tab)}" class="seat-tab${tab === active ? " on" : ""}" type="button"
          role="tab" aria-selected="${tab === active ? "true" : "false"}" tabindex="${tab === active ? "0" : "-1"}"
          data-seat-tab="${esc(tab)}">
          ${esc(t("tab_" + tab))}
        </button>
      `).join("")}
    </div>
  `;
}

function moduleEmptyHTML(tab) {
  return `
    <section class="module-empty" aria-label="${esc(t("module_empty_aria"))}">
      <span class="module-empty-kicker">${esc(t("module_empty_kicker"))}</span>
      <h3>${esc(t("empty_" + tab + "_title"))}</h3>
      <p>${esc(t("empty_" + tab + "_body"))}</p>
      <div class="module-empty-needed">
        <span>${esc(t("module_empty_needed"))}</span>
        <p>${esc(t("empty_" + tab + "_needed"))}</p>
      </div>
    </section>
  `;
}

function candidateSetFor(seat) {
  if (state.tier === "parlimen") return state.candidates && state.candidates[seat.code];
  return state.candidatesDun && state.candidatesDun[seat.code];
}

function candidateResultText(result) {
  const key = "candidate_result_" + String(result || "lost").replace(/[^a-z0-9_]/gi, "_").toLowerCase();
  return t(key);
}

function voteSharePercent(candidate, totalVotes) {
  const pct = Number(candidate.vote_pct);
  if (Number.isFinite(pct)) return pct;
  const votes = Number(candidate.votes);
  if (!totalVotes || !Number.isFinite(votes)) return null;
  return Math.round((votes / totalVotes) * 1000) / 10;
}

function formatVoteShare(value) {
  const rounded = Math.round(Number(value) * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}%` : `${rounded.toFixed(1)}%`;
}

function candidateVoteShareHTML(data) {
  const rows = data.candidates
    .map((c) => ({ c, votes: Number(c.votes) }))
    .filter((row) => Number.isFinite(row.votes) && row.votes > 0);
  const totalVotes = rows.reduce((sum, row) => sum + row.votes, 0);
  if (!totalVotes) return "";
  const shares = rows.map((row) => ({
    ...row,
    pct: voteSharePercent(row.c, totalVotes),
    bloc: row.c.coalition || row.c.party || "",
  })).filter((row) => Number.isFinite(row.pct));
  if (!shares.length) return "";
  const summary = shares
    .map((row) => `${row.c.name} ${row.bloc} ${formatVoteShare(row.pct)}`)
    .join("; ");
  const sideLabel = (row, side) => {
    if (!row) return "";
    const pct = formatVoteShare(row.pct);
    return `
      <div class="candidate-vote-side ${side}">
        <span class="candidate-vote-side-name">
          <span class="candidate-vote-dot" style="background:${partyColor(row.bloc)}"></span>
          <span class="candidate-vote-side-text">${esc(row.c.name)}</span>
        </span>
        <span class="candidate-vote-side-meta">${esc(row.bloc)} · ${esc(pct)}</span>
      </div>
    `;
  };
  const barShares = shares.length > 2 ? [shares[0], ...shares.slice(2), shares[1]] : shares;
  const segments = barShares.map((row) => {
    const pct = formatVoteShare(row.pct);
    const title = `${row.c.name} · ${row.bloc} · ${pct}`;
    const sideClass = row === shares[0] ? " left-edge" : (row === shares[1] ? " right-edge" : " middle");
    return `
      <span
        class="candidate-vote-seg${sideClass}"
        style="flex-grow:${row.votes};background:${partyColor(row.bloc)}"
        title="${esc(title)}"
        aria-hidden="true"
      ><span>${row.pct >= 8 ? esc(pct) : ""}</span></span>
    `;
  }).join("");
  const key = shares.map((row) => `
    <span class="candidate-vote-key-item">
      <span class="candidate-vote-dot" style="background:${partyColor(row.bloc)}"></span>
      <span class="candidate-vote-key-name">${esc(row.c.name)}</span>
      <b>${esc(formatVoteShare(row.pct))}</b>
    </span>
  `).join("");
  return `
    <div class="candidate-vote-share">
      <div class="candidate-vote-head">
        <h3>${esc(t("candidate_vote_share"))}</h3>
        <span>${esc(t("candidate_vote_total", { n: totalVotes.toLocaleString() }))}</span>
      </div>
      <div class="candidate-vote-sides${shares.length < 2 ? " single" : ""}">
        ${sideLabel(shares[0], "left")}
        ${sideLabel(shares[1], "right")}
      </div>
      <div class="candidate-vote-bar" role="img" aria-label="${esc(t("candidate_vote_share_aria", { items: summary }))}">
        ${segments}
      </div>
      <div class="candidate-vote-key">${key}</div>
    </div>
  `;
}

function candidatesHTML(seat) {
  const data = candidateSetFor(seat);
  if (!data || !Array.isArray(data.candidates) || !data.candidates.length) return moduleEmptyHTML("candidates");
  const voteShare = candidateVoteShareHTML(data);
  const cards = data.candidates.map((c) => {
    const bits = [];
    if (Number.isFinite(c.votes)) bits.push(t("candidate_votes", { n: c.votes.toLocaleString() }));
    if (Number.isFinite(c.vote_pct)) bits.push(`${c.vote_pct}%`);
    if (Number.isFinite(c.age)) bits.push(t("candidate_age", { n: c.age }));
    if (Number.isFinite(c.ballot_order)) bits.push(t("candidate_ballot", { n: c.ballot_order }));
    const won = String(c.result || "").startsWith("won");
    return `
      <article class="candidate-card${won ? " won" : ""}">
        <div class="candidate-main">
          <span class="candidate-rank">#${c.rank}</span>
          <div>
            <h3>${esc(c.name)}</h3>
            ${c.name_ballot && c.name_ballot !== c.name ? `<p>${esc(c.name_ballot)}</p>` : ""}
          </div>
        </div>
        <div class="candidate-side">
          <span class="pill" style="background:${partyColor(c.coalition || c.party)};color:#fff">${esc(c.party || c.coalition || "")}</span>
          <span class="candidate-status">${esc(candidateResultText(c.result))}</span>
        </div>
        ${bits.length ? `<div class="candidate-meta">${bits.map(esc).join(" · ")}</div>` : ""}
      </article>
    `;
  }).join("");
  return `
    <section class="candidate-module">
      <div class="module-source">
        <span>${esc(data.election || "")}</span>
        <p>${esc(t("candidate_source", { source: data.source || "" }))}</p>
      </div>
      ${voteShare}
      <div class="candidate-list">${cards}</div>
      ${data.coverage_note ? `<div class="src-line muted">${esc(data.coverage_note)}</div>` : ""}
    </section>
  `;
}

function localizedField(obj, key) {
  return (lang === "ms" && obj[key + "_ms"]) ? obj[key + "_ms"] : obj[key];
}

function votingGuideHTML() {
  const guide = state.votingGuide;
  if (!guide || !Array.isArray(guide.items)) return moduleEmptyHTML("voting");
  const cards = guide.items.map((item) => `
    <a class="voting-action" href="${esc(item.url)}" target="_blank" rel="noopener">
      <strong>${esc(localizedField(item, "title"))}</strong>
      <span>${esc(localizedField(item, "body"))}</span>
      <em>${esc(localizedField(item, "label"))}</em>
    </a>
  `).join("");
  return `
    <section class="voting-guide">
      <div class="module-source">
        <span>${esc(t("voting_official_source"))}</span>
        <p>${esc(guide.source || "")} · ${esc(t("voting_updated", { date: guide.updated || "" }))}</p>
      </div>
      <p class="voting-privacy">${esc(localizedField(guide, "privacy_note"))}</p>
      <div class="voting-actions">${cards}</div>
    </section>
  `;
}

function setSeatTab(tab, focusTab = false) {
  if (!isSeatTab(tab) || tab === state.seatTab) return;
  const seat = state.selected && state.data[state.tier] && state.data[state.tier].byCode.get(state.selected);
  if (!seat) return;
  state.seatTab = tab;
  animateCardResize(PANEL_STATE, () => {
    STATE_INFO.innerHTML = stateSeatCardHTML(seat);
    resetStateInfoScroll();
  });
  animateIn(STATE_INFO.querySelector(".seat-tabpanel"), 6);   // the new tab's content rises in
  requestAnimationFrame(() => {
    syncMapToCard();
    const activeTab = STATE_INFO.querySelector(`[data-seat-tab="${CSS.escape(tab)}"]`);
    const tabRow = activeTab && activeTab.closest(".seat-tabs");
    if (activeTab && tabRow) {
      tabRow.scrollLeft = activeTab.offsetLeft - (tabRow.clientWidth - activeTab.clientWidth) / 2;
    }
    if (focusTab) activeTab?.focus({ preventScroll: true });
  });
}
function renderPanel(seat) {
  PANEL.classList.remove("empty"); PANEL_EMPTY.hidden = true; PANEL_SEAT.hidden = false;
  PANEL_SEAT.innerHTML = seatCardHTML(seat);
  animateIn(PANEL_SEAT);
}

// ---- share / copy deep-link ----
// Builds the canonical deep-link to the selected seat (encodeHash already encodes
// #tier/mode/code) and copies it to the clipboard, with a transient toast. The
// clipboard API is guarded — on any failure we tell the user to copy from the URL bar.
let toastTimer = null;
function showToast(key) {
  if (!TOAST) return;
  TOAST.textContent = t(key);
  if (TOAST.hidden) {
    TOAST.hidden = false;
    TOAST.getBoundingClientRect();   // flush styles so the .show transition actually plays
  }
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
// ---- card IMAGE: a 1080×1350 seat card (Canvas 2D) ----
// Draws the selected seat's silhouette (new Path2D(seat.d), fit via the pure
// fitBox transform) + headline facts onto an off-screen canvas. The card button
// opens a preview first; the dialog's primary action downloads the PNG.
// Fully guarded — any failure shows a toast pointing back to the share link.
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
function fitCanvasText(ctx, text, maxWidth, minChars = 8) {
  let out = String(text || "");
  while (out.length > minChars && ctx.measureText(out).width > maxWidth) out = out.slice(0, -1);
  return out !== String(text || "") ? out.trim() + "..." : out;
}
function setFittedFont(ctx, text, maxWidth, { weight, size, min, family }) {
  let s = size;
  do {
    ctx.font = `${weight} ${s}px ${family}`;
    if (ctx.measureText(String(text || "")).width <= maxWidth || s <= min) break;
    s -= 2;
  } while (s >= min);
  return s;
}
function drawBlueprintBackground(ctx, accent) {
  const bg = ctx.createLinearGradient(0, 0, CARD_W, CARD_H);
  bg.addColorStop(0, "#07111d");
  bg.addColorStop(0.58, "#0a1420");
  bg.addColorStop(1, "#060b12");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, CARD_W, CARD_H);

  const drawGrid = (step, alpha, width) => {
    ctx.save();
    ctx.strokeStyle = `rgba(118, 191, 222, ${alpha})`;
    ctx.lineWidth = width;
    ctx.beginPath();
    for (let x = 0; x <= CARD_W; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, CARD_H); }
    for (let y = 0; y <= CARD_H; y += step) { ctx.moveTo(0, y); ctx.lineTo(CARD_W, y); }
    ctx.stroke();
    ctx.restore();
  };
  drawGrid(36, 0.055, 1);
  drawGrid(144, 0.115, 1.4);

  ctx.save();
  ctx.globalAlpha = 0.12;
  ctx.strokeStyle = accent;
  ctx.lineWidth = 2;
  for (let i = -340; i < CARD_W; i += 180) {
    ctx.beginPath();
    ctx.moveTo(i, CARD_H);
    ctx.lineTo(i + 620, 0);
    ctx.stroke();
  }
  ctx.restore();

}
function drawSeatCard(seat) {
  const isP = state.tier === "parlimen";
  const r = resultFor(seat);
  const ownDun = !!ownDunResult(seat);
  const accent = r ? partyColor(r.coalition) : "#5d6b7d";

  const cv = document.createElement("canvas");
  cv.width = CARD_W; cv.height = CARD_H;
  const ctx = cv.getContext("2d");
  if (!ctx) return null;

  drawBlueprintBackground(ctx, accent);

  // brand
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#eef5fb";
  ctx.fillRect(72, 86, 16, 26);
  ctx.strokeStyle = "rgba(238,245,251,.65)";
  ctx.lineWidth = 3;
  ctx.strokeRect(82, 94, 16, 26);
  ctx.fillStyle = "#e8edf3";
  ctx.font = "700 44px 'Redaction 20', Georgia, 'Times New Roman', serif";
  ctx.fillText("MyPolitik", 116, 116);
  ctx.fillStyle = "#6f8498";
  ctx.font = "500 22px 'JetBrains Mono', monospace";
  ctx.textAlign = "right";
  ctx.fillText(`${(seat.state || "").toUpperCase()} / ${(seat.code || seat.dun_code || "").toUpperCase()}`, CARD_W - 72, 112);
  ctx.textAlign = "left";

  // seat silhouette in a centred region, tinted by the bloc colour
  const REG = { x: 78, y: 180, w: CARD_W - 156, h: 540 };
  const fit = fitBox(seat.bbox, REG.w, REG.h, 52);
  if (fit) {
    try {
      const path = new Path2D(seat.d);
      ctx.save();
      ctx.translate(REG.x, REG.y);
      ctx.strokeStyle = "rgba(140, 210, 238, .14)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, REG.h / 2);
      ctx.lineTo(REG.w, REG.h / 2);
      ctx.moveTo(REG.w / 2, 0);
      ctx.lineTo(REG.w / 2, REG.h);
      ctx.stroke();
      ctx.translate(fit.dx, fit.dy);
      ctx.scale(fit.scale, fit.scale);
      ctx.shadowColor = accent;
      ctx.shadowBlur = 34;
      ctx.fillStyle = accent;
      ctx.globalAlpha = 0.9;
      ctx.fill(path, "evenodd");
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 0.52;
      ctx.strokeStyle = "#eef6ff";
      ctx.lineWidth = Math.max(1.4 / fit.scale, 0.02);
      ctx.stroke(path);
      ctx.restore();
    } catch (_) { /* Path2D unsupported / bad d — text card still works */ }
  }
  ctx.globalAlpha = 1;

  // kicker · code
  const kicker = isP ? `${t("kicker_parlimen")} · ${seat.code}` : `DUN · ${seat.dun_code}`;
  ctx.fillStyle = accent;
  ctx.font = "600 30px 'Space Grotesk', system-ui, sans-serif";
  ctx.fillText(kicker.toUpperCase(), 72, 790);

  // seat name (clamped to width)
  ctx.fillStyle = "#f5f8fb";
  let name = String(seat.name || "");
  setFittedFont(ctx, name, CARD_W - 144, {
    weight: 700,
    size: 94,
    min: 58,
    family: "'Redaction 20', Georgia, 'Times New Roman', serif",
  });
  ctx.fillText(name, 72, 884);

  // state
  ctx.fillStyle = "#9fb0c0";
  ctx.font = "500 34px 'Space Grotesk', system-ui, sans-serif";
  ctx.fillText(`${t("state_label")}: ${seat.state || ""}`, 72, 940);

  // representative + bloc pill, or a gentle "data soon" line
  const infoY = 998;

  if (r) {
    const repName = String(r.name || "");
    ctx.fillStyle = "#7f95a9";
    ctx.font = "600 22px 'JetBrains Mono', monospace";
    ctx.fillText(t("card_current_yb").toUpperCase(), 72, infoY + 48);
    ctx.fillStyle = "#e8edf3";
    ctx.font = "700 42px 'Space Grotesk', system-ui, sans-serif";
    ctx.fillText(fitCanvasText(ctx, repName, 610, 12), 72, infoY + 104);
    // bloc pill
    const label = String(r.coalition || "");
    ctx.font = "600 30px 'Space Grotesk', system-ui, sans-serif";
    const pw = ctx.measureText(label).width + 40;
    ctx.fillStyle = accent;
    roundRect(ctx, 72, infoY + 124, pw, 50, 25);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.fillText(label, 92, infoY + 158);
    if (r.majority != null) {
      ctx.fillStyle = "#9fb0c0";
      ctx.font = "500 30px 'JetBrains Mono', monospace";
      ctx.textAlign = "right";
      ctx.fillText(`${t(ownDun ? "majority_prn" : "majority")}: ${Number(r.majority).toLocaleString()}`, CARD_W - 110, infoY + 88);
      if (r.votes != null) {
        ctx.fillStyle = "#6f8498";
        ctx.font = "400 26px 'JetBrains Mono', monospace";
        ctx.fillText(`${t("win_votes")}: ${Number(r.votes).toLocaleString()}`, CARD_W - 110, infoY + 130);
      }
      ctx.textAlign = "left";
    }
  } else {
    ctx.fillStyle = "#9fb0c0";
    ctx.font = "400 40px 'Space Grotesk', system-ui, sans-serif";
    ctx.fillText(t("rep_ph"), 72, infoY + 96);
  }

  // footer: provenance only, no dev/local URL baked into the share image
  ctx.fillStyle = "#7d8da0";
  ctx.font = "500 26px 'Space Grotesk', system-ui, sans-serif";
  ctx.fillText("MyPolitik / public electoral data", 72, CARD_H - 94);
  ctx.fillStyle = "#5d6b7d";
  ctx.font = "400 23px 'Space Grotesk', system-ui, sans-serif";
  if (r) ctx.fillText(t(ownDun ? "src_prn15" : "src_ge15"), 72, CARD_H - 56);
  return cv;
}
let sharingCard = false;
let cardPreviewURL = null;
let cardPreviewBlob = null;
let cardPreviewName = "";
let cardPreviewReturnTo = null;

function cardFileName(seat) {
  return `mypolitik-${(seat.code || "seat").replace(/[^\w.-]/g, "_")}.png`;
}
function clearCardPreviewURL() {
  if (cardPreviewURL) URL.revokeObjectURL(cardPreviewURL);
  cardPreviewURL = null;
  cardPreviewBlob = null;
  cardPreviewName = "";
  if (CARD_PREVIEW_IMG) {
    CARD_PREVIEW_IMG.removeAttribute("src");
    CARD_PREVIEW_IMG.alt = "";
  }
}
function openCardPreview(blob, fname, seat, returnTo) {
  if (!CARD_PREVIEW || !CARD_PREVIEW_IMG) return false;
  clearCardPreviewURL();
  cardPreviewURL = URL.createObjectURL(blob);
  cardPreviewBlob = blob;
  cardPreviewName = fname;
  cardPreviewReturnTo = returnTo || document.activeElement;
  CARD_PREVIEW_IMG.src = cardPreviewURL;
  CARD_PREVIEW_IMG.alt = t("card_preview_alt", { seat: seat.name || "" });
  if (CARD_PREVIEW.showModal) CARD_PREVIEW.showModal();
  else CARD_PREVIEW.setAttribute("open", "");
  requestAnimationFrame(() => CARD_PREVIEW_DOWNLOAD?.focus({ preventScroll: true }));
  return true;
}
function closeCardPreview() {
  if (!CARD_PREVIEW) return;
  if (CARD_PREVIEW.open && CARD_PREVIEW.close) CARD_PREVIEW.close();
  else {
    CARD_PREVIEW.removeAttribute("open");
    clearCardPreviewURL();
  }
}
function downloadCardPreview() {
  if (!cardPreviewBlob) { showToast("card_fail"); return; }
  const url = URL.createObjectURL(cardPreviewBlob);
  const a = document.createElement("a");
  a.href = url;
  a.download = cardPreviewName || "mypolitik-card.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  closeCardPreview();
  showToast("card_download_ok");
}

async function shareCard(trigger) {
  if (sharingCard) return;
  const seat = state.selected && state.data[state.tier] &&
    state.data[state.tier].byCode.get(state.selected);
  if (!seat) return;
  const btn = trigger && trigger.closest ? trigger.closest("button") : null;
  sharingCard = true;
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    if (document.fonts && document.fonts.ready) {
      try { await document.fonts.ready; } catch (_) {}
    }
    const cv = drawSeatCard(seat);
    if (!cv) { showToast("card_fail"); return; }
    const blob = await new Promise((res) =>
      cv.toBlob ? cv.toBlob(res, "image/png") : res(null));
    if (!blob) { showToast("card_fail"); return; }
    if (!openCardPreview(blob, cardFileName(seat), seat, btn)) showToast("card_fail");
  } catch (_) {
    showToast("card_fail");
  } finally {
    sharingCard = false;
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}
// PANEL_SEAT.innerHTML is rebuilt on every render, so delegate rather than re-bind.
PANEL_SEAT.addEventListener("click", (e) => {
  if (e.target.closest("#share-link")) shareLink();
  else if (e.target.closest("#share-card")) shareCard(e.target);
});
CARD_PREVIEW_DOWNLOAD?.addEventListener("click", downloadCardPreview);
CARD_PREVIEW_CLOSE?.addEventListener("click", closeCardPreview);
CARD_PREVIEW?.addEventListener("click", (e) => {
  if (e.target === CARD_PREVIEW) closeCardPreview();
});
CARD_PREVIEW?.addEventListener("close", () => {
  const returnTo = cardPreviewReturnTo;
  cardPreviewReturnTo = null;
  clearCardPreviewURL();
  if (returnTo && document.contains(returnTo)) {
    returnTo.focus({ preventScroll: true });
  }
});

// ---- summary + legend (empty panel) ----
// national at-a-glance: the Dewan Rakyat (GE15) coalition makeup, shown on the idle
// card the moment results load. Always the parliament picture (tier-independent).
function renderNatGlance() {
  const host = document.getElementById("nat-glance");
  if (!host) return;
  if (!state.results) { host.hidden = true; requestAnimationFrame(syncMapToCard); return; }
  const counts = tallyCoalitions(state.results);
  const ordered = COALITION_ORDER.filter((c) => counts[c]);
  document.getElementById("nat-bar").innerHTML = ordered
    .map((c) => `<span style="flex:${counts[c]};background:${partyColor(c)}"></span>`).join("");
  document.getElementById("nat-key").innerHTML = ordered
    .map((c) => `<span class="sk"><span class="sw" style="background:${partyColor(c)}"></span>${esc(c)} <b>${counts[c]}</b></span>`).join("");
  host.hidden = false;
  requestAnimationFrame(syncMapToCard);
  animateIn(host);
}

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
  requestAnimationFrame(syncMapToCard);
}

// ---- hover: light up the state under the cursor and name it ----
// Gated to mouse/pointer devices so it never flashes on a touch tap. The overview is a state
// map, so hovering should tell you which state you're pointing at (and about to open).
const HOVER_MQ = matchMedia("(hover: hover) and (pointer: fine) and (min-width: 861px)");
const STATE_LABEL = document.getElementById("state-label");
let labelText = null;
function syncStageLabelPosition() {
  if (!STATE_LABEL || !state.openState) {
    document.documentElement.style.removeProperty("--state-label-top");
    return;
  }
  // Mobile district detail: pin the title to its resting spot under the topbar (the map
  // band starts below it — see syncMapToCard). Tracking the state's top here would make
  // the title chase the camera through the whole district glide.
  if (MOBILE_MAP_INSPECT_MQ.matches && PANEL.classList.contains("seat-detail")) {
    const floor = TOPBAR ? Math.max(12, Math.round(TOPBAR.getBoundingClientRect().bottom + 6)) : 12;
    document.documentElement.style.setProperty("--state-label-top", `${floor}px`);
    return;
  }
  const stateTop = currentStateTopScreenY(state.openState);
  const labelH = STATE_LABEL.getBoundingClientRect().height || 32;
  const gap = MOBILE_MAP_INSPECT_MQ.matches ? 8 : 12;
  // Never rise into the topbar — it is visible in EVERY mode now (logo + menu at all times).
  const floor = TOPBAR ? Math.max(12, Math.round(TOPBAR.getBoundingClientRect().bottom + 6)) : 12;
  const top = Math.max(floor, Math.round(stateTop - labelH - gap));
  document.documentElement.style.setProperty("--state-label-top", `${top}px`);
}
// The big name centred above the map: hover state in overview, locked state once isolated.
// When the label IS the open state's name, a small tier chip (DUN / Parliament) rides
// along so drilling into DUN level always says which layer you're in.
function setStageLabel(text) {
  const chip = text && text === state.openState ? t(state.tier === "dun" ? "tier_dun" : "tier_parlimen") : "";
  const memo = text ? `${text}|${chip}` : text;
  if (memo === labelText) return;
  labelText = memo;
  if (!STATE_LABEL) return;
  if (text) {
    STATE_LABEL.textContent = text;
    if (chip) {
      const s = document.createElement("span");
      s.className = "label-tier";
      s.textContent = chip;
      STATE_LABEL.appendChild(s);
    }
    STATE_LABEL.classList.add("show");
    requestAnimationFrame(syncStageLabelPosition);
  } else {
    STATE_LABEL.classList.remove("show");
    document.documentElement.style.removeProperty("--state-label-top");
  }
}
function setStateHover(name, data) {
  if (name === hoverState) return;   // only re-paint when the hovered state actually changes
  clearStateHover();
  hoverState = name;
  setStageLabel(name);
  for (const s of data.seats) {
    if (s.state === name) { const p = state.paths.get(s.code); if (p) p.classList.add("state-hover"); }
  }
}
function clearStateHover() {
  if (!hoverState) {
    setStageLabel(state.openState || null);
    return;
  }
  hoverState = null;
  setStageLabel(state.openState || null);
  SEATS.querySelectorAll(".seat.state-hover").forEach((p) => p.classList.remove("state-hover"));
}
function clearHoverUI() {
  TOOLTIP.hidden = true;
  clearStateHover();
}
SVG.addEventListener("mousemove", (e) => {
  if (!HOVER_MQ.matches) {
    clearHoverUI();
    return;
  }
  const tgt = e.target;   // NOT `t` — that name is the module-level i18n fn t(); shadowing breaks t("key")
  // Isolated state view: keep the state name locked above the map; no cursor tooltip here.
  if (state.openState) {
    TOOLTIP.hidden = true;
    setStageLabel(state.openState);
    return;
  }
  if (tgt.classList && tgt.classList.contains("seat") && !tgt.classList.contains("no-dun")) {
    const data = state.data[state.tier];
    if (!data) return;   // boundary layer unavailable — no seat paths exist anyway
    const seat = data.byCode.get(tgt.dataset.code);
    if (!seat) return;
    setStateHover(seat.state, data);   // light up the whole state under the cursor
    TOOLTIP.hidden = true;
  } else {
    clearHoverUI();
  }
});
SVG.addEventListener("mouseleave", clearHoverUI);
if (HOVER_MQ.addEventListener) HOVER_MQ.addEventListener("change", clearHoverUI);
else HOVER_MQ.addListener(clearHoverUI);

// Tactile press on the map itself: the tapped state (overview) or district (isolated)
// dips the instant the finger lands — the tap is acknowledged before any zoom starts.
// Opacity-only on the already-lit paths; outstate/no-dun paths are never touched.
function pressPulse(paths) {
  for (const p of paths) {
    if (!p.animate) continue;
    p.animate(
      [{ opacity: 1 }, { opacity: 0.6, offset: 0.3 }, { opacity: 1 }],
      { duration: 260, easing: "cubic-bezier(0, 0, 0.2, 1)" }
    );
  }
}
SVG.addEventListener("pointerdown", (e) => {
  if (ANIM_OFF || REDUCE_MOTION.matches || !e.isPrimary) return;
  const tgt = e.target;
  if (!(tgt.classList && tgt.classList.contains("seat")) || tgt.classList.contains("no-dun")) return;
  if (tgt.classList.contains("outstate")) return;
  const data = state.data[state.tier];
  if (!data) return;
  if (state.openState) {                       // isolated → just the tapped district answers
    pressPulse([tgt]);
    return;
  }
  const seat = data.byCode.get(tgt.dataset.code);   // overview → the whole tapped state answers
  if (!seat) return;
  const paths = [];
  for (const s of data.seats) {
    if (s.state !== seat.state) continue;
    const p = state.paths.get(s.code);
    if (p) paths.push(p);
  }
  pressPulse(paths);
});

let mapDrag = null;
let suppressMapClickUntil = 0;
SVG.addEventListener("pointerdown", (e) => {
  if (!mapInspectActive() || !e.isPrimary) return;
  mapDrag = {
    id: e.pointerId,
    x: e.clientX,
    y: e.clientY,
    vb: viewBox.slice(),
    moved: false,
  };
  // Capture is DEFERRED to the first real drag movement (pointermove below). Capturing
  // here retargets pointerup/mouseup — and therefore the tap's click — to the <svg>
  // itself, so a mouse-tap on a district read as an empty-space tap and closed the state.
});
SVG.addEventListener("pointermove", (e) => {
  if (!mapDrag || e.pointerId !== mapDrag.id) return;
  const dx = e.clientX - mapDrag.x;
  const dy = e.clientY - mapDrag.y;
  if (Math.hypot(dx, dy) > 5) {
    if (!mapDrag.moved) { try { SVG.setPointerCapture(e.pointerId); } catch (_) {} }
    mapDrag.moved = true;
  }
  if (!mapDrag.moved) return;
  e.preventDefault();
  const rect = SVG.getBoundingClientRect();
  const sx = mapDrag.vb[2] / Math.max(1, rect.width);
  const sy = mapDrag.vb[3] / Math.max(1, rect.height);
  setViewBoxNow(clampInspectViewBox([
    mapDrag.vb[0] - dx * sx,
    mapDrag.vb[1] - dy * sy,
    mapDrag.vb[2],
    mapDrag.vb[3],
  ]));
});
function endMapDrag(e) {
  if (!mapDrag || e.pointerId !== mapDrag.id) return;
  if (mapDrag.moved) suppressMapClickUntil = performance.now() + 250;
  mapDrag = null;
}
SVG.addEventListener("pointerup", endMapDrag);
SVG.addEventListener("pointercancel", endMapDrag);

// ---- click ----
SVG.addEventListener("click", (e) => {
  if (performance.now() < suppressMapClickUntil) {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  if (MOBILE_MAP_INSPECT_MQ.matches && state.openState && state.selected && !state.mapInspect) {
    setMapInspect(true);
    return;
  }
  const tgt = e.target;   // NOT `t` — that name is the module-level i18n fn t(); shadowing it would break any t("key") added here
  TOOLTIP.hidden = true; clearStateHover();  // dismiss any lingering hover tooltip / state highlight
  if (tgt.classList && tgt.classList.contains("seat")) {
    const seat = state.data[state.tier] && state.data[state.tier].byCode.get(tgt.dataset.code);
    if (!seat) return;
    if (state.openState) {
      // already isolated in a state → tapping a district shows its detail
      if (seat.state === state.openState) {
        if (state.mapInspect) previewDistrict(seat.code);
        else showDistrict(seat.code);
      }
    } else {
      openStateCard(seat.state);   // overview → isolate + zoom into the tapped state
    }
  } else {
    goBack();   // tap empty space → step back one level
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
function setLocatingControl(btn, busy) {
  if (!btn) return;
  btn.disabled = !!busy;
  if (busy) btn.setAttribute("aria-busy", "true");
  else btn.removeAttribute("aria-busy");
}
function setFindStatus(key) {
  if (!FIND_STATUS) return;
  if (!key) {
    delete FIND_STATUS.dataset.i18n;
    FIND_STATUS.textContent = "";
    FIND_STATUS.hidden = true;
    requestAnimationFrame(syncMapToCard);
    return;
  }
  FIND_STATUS.dataset.i18n = key;     // applyStatic() re-translates it on setLang
  FIND_STATUS.textContent = t(key);
  FIND_STATUS.hidden = false;
  requestAnimationFrame(syncMapToCard);
}
function seatFromPosition(pos) {
  const { latitude: lat, longitude: lng } = pos.coords;
  const seats = state.data[state.tier] && state.data[state.tier].seats;
  // 150 km bound covers genuine offshore islands without snapping an
  // out-of-country user (Singapore/Indonesia/abroad) onto a border seat.
  return seats && (findSeatForLocation(lat, lng, seats) || nearestSeat(lat, lng, seats, 150));
}
function findSeatByLocation() {
  if (!navigator.geolocation) return Promise.reject("loc_unsupported");
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const seat = seatFromPosition(pos);
        if (!seat) reject("loc_notfound");
        else resolve(seat);
      },
      (err) => {
        reject(err && err.code === 1 ? "loc_denied" : "loc_error");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
    );
  });
}
function locate() {
  if (locating) return;
  locating = true;
  setLocatingControl(FIND_LOC, true);
  setFindStatus("loc_locating");
  findSeatByLocation().then(
    (seat) => {
      setFindStatus(null);
      select(seat.code);
    },
    (key) => {
      setFindStatus(key || "loc_error");
    }
  ).finally(() => {
    locating = false;
    setLocatingControl(FIND_LOC, false);
  });
}
if (FIND_LOC) FIND_LOC.addEventListener("click", locate);

// ---- first-load tap hint (dismissed for good once seen) ----
// A one-time nudge over the map so first-time visitors know the seats are tappable.
// Dismissed by the ✕, by selecting any seat, and remembered in localStorage so it
// never re-appears. localStorage access is guarded — a blocked store just means the
// hint shows each visit (harmless) rather than throwing.
const HINT_KEY = "mypolitik-hint-seen";
const LEGACY_HINT_KEY = "peta-yb-hint-seen";
function hintSeen() {
  try {
    return localStorage.getItem(HINT_KEY) === "1" || localStorage.getItem(LEGACY_HINT_KEY) === "1";
  } catch (_) { return false; }
}
function dismissHint() {
  if (!TAP_HINT || TAP_HINT.hidden) return;
  TAP_HINT.hidden = true;
  try {
    localStorage.setItem(HINT_KEY, "1");
    localStorage.removeItem(LEGACY_HINT_KEY);
  } catch (_) {}
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
  if (state.prnMode) closePrnMode({ silent: true });   // manual tier switch leaves the election view
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
  if (e.key !== "Escape") return;
  if (state.mapInspect) {
    e.preventDefault();
    goBack();
    return;
  }
  if (state.selected) deselect();
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
  if (h && h.mode === "negeri") setMode("negeri");
  else if (h && h.mode === "skor") setMode("parti");
  else setMode("parti");
  if (h && h.code) {
    const data = state.data[state.tier];
    if (data.byCode.has(h.code)) select(h.code);
  }
  if (h && h.prn && liveElection()) {
    await openPrnMode();     // deep-linked election view (#dun/parti[/seat]/prn)
    if (h.code && state.data[state.tier].byCode.has(h.code)) showDistrict(h.code);
  }
  syncLiveBadge();
  refreshPrnLive();
  writeHash();       // normalise URL to the actually-active state — a gated mode (Skor) or bad seat
                     // code in the deep link gets dropped so a re-shared link can't misrepresent state
                     // (replaceState → no extra history entry)
  maybeShowHint();   // fresh visit, nothing selected → nudge that seats are tappable
})();

/* ===== top-bar icon actions ===== */
const INFO_CARD = document.getElementById("info-card");
function showInfo() {
  setMobileMenu(false);
  if (INFO_CARD) INFO_CARD.hidden = false;
}
function hideInfo() { if (INFO_CARD) INFO_CARD.hidden = true; }
document.getElementById("info-close")?.addEventListener("click", hideInfo);
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !INFO_CARD || INFO_CARD.hidden) return;
  e.preventDefault();
  e.stopPropagation();
  hideInfo();
}, true);
async function shareApp() {
  hideInfo();
  const url = location.origin + location.pathname;
  try {
    if (navigator.share) await navigator.share({ title: "MyPolitik", url });
    else { await navigator.clipboard.writeText(url); showToast("share_ok"); }
  } catch (e) { /* user cancelled */ }
}
function showWholeMap() { hideInfo(); backToControls(); }
document.getElementById("brand-home")?.addEventListener("click", showWholeMap);
document.getElementById("top-map")?.addEventListener("click", showWholeMap);
document.getElementById("top-info")?.addEventListener("click", showInfo);
document.getElementById("top-share")?.addEventListener("click", shareApp);

/* ===== state-first drill: main map = states; tap a state to open its district mini-map in the card ===== */
const STATE_MAP = document.getElementById("state-map");
const STATE_SEATS = document.getElementById("state-seats");
const PANEL_STATE = document.getElementById("panel-state");
const STATE_INFO = document.getElementById("state-info");
const MOBILE_MAP_INSPECT_MQ = matchMedia("(max-width: 860px)");

function resetStateInfoScroll() {
  STATE_INFO.scrollTop = 0;
  STATE_INFO.querySelector(".seat-detail-main")?.scrollTo({ top: 0, left: 0 });
}

function selectedSeat() {
  return state.selected && state.data[state.tier] && state.data[state.tier].byCode.get(state.selected);
}

function mapInspectActive() {
  return !!(state.mapInspect && state.openState && MOBILE_MAP_INSPECT_MQ.matches);
}

function syncMapInspectButton() {
  if (!MAP_INSPECT_TOGGLE) return;
  MAP_INSPECT_TOGGLE.hidden = false;
  const key = state.mapInspect ? "map_inspect_exit_aria" : "map_inspect_aria";
  MAP_INSPECT_TOGGLE.setAttribute("aria-pressed", state.mapInspect ? "true" : "false");
  MAP_INSPECT_TOGGLE.setAttribute("aria-label", t(key));
  MAP_INSPECT_TOGGLE.setAttribute("title", t(key));
}

function districtOptionsForOpenState() {
  const data = state.data[state.tier];
  if (!data || !state.openState) return [];
  return data.seats
    .filter((seat) => seat.state === state.openState)
    .slice()
    .sort((a, b) => {
      const aCode = displayCode(a, state.tier) || a.code;
      const bCode = displayCode(b, state.tier) || b.code;
      return String(aCode).localeCompare(String(bCode), undefined, { numeric: true });
    });
}

function districtSelectHTML(selectedCode = "") {
  const seats = districtOptionsForOpenState();
  const label = esc(t("map_inspect_select_label"));
  const selected = seats.find((seat) => seat.code === selectedCode);
  const selectedText = selected
    ? `${displayCode(selected, state.tier) || selected.code} · ${selected.name}`
    : t("map_inspect_select_ph");
  return `
    <div class="map-inspect-select" id="map-inspect-district-picker">
      <button
        id="map-inspect-district-toggle"
        class="map-inspect-select-button"
        type="button"
        aria-haspopup="listbox"
        aria-expanded="false"
        aria-controls="map-inspect-district-list"
        aria-label="${label}">
        <span>${esc(selectedText)}</span>
        <i class="map-inspect-select-caret" aria-hidden="true"></i>
      </button>
      <div id="map-inspect-district-list" class="map-inspect-select-list" role="listbox" aria-label="${label}" hidden>
        ${seats.map((seat) => {
          const code = displayCode(seat, state.tier) || seat.code;
          const isSelected = seat.code === selectedCode;
          return `
            <button
              class="map-inspect-option"
              type="button"
              role="option"
              aria-selected="${isSelected ? "true" : "false"}"
              data-map-inspect-district="${esc(seat.code)}">
              ${esc(code)} · ${esc(seat.name)}
            </button>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function locateIconHTML() {
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="2" x2="5" y1="12" y2="12"/><line x1="19" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="5"/><line x1="12" x2="12" y1="19" y2="22"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/></svg>';
}

function mapInspectLocateHTML() {
  const label = esc(t("find_district_loc"));
  return `<button id="map-inspect-locate" class="loc-fab map-inspect-locate" type="button" aria-label="${label}" title="${label}">${locateIconHTML()}</button>`;
}

function districtSwitchRowHTML(selectedCode = "", includeMore = false) {
  return `
    <div class="map-inspect-row">
      ${districtSelectHTML(selectedCode)}
      ${mapInspectLocateHTML()}
      ${includeMore ? `<button id="map-inspect-more" class="map-inspect-more" type="button">${esc(t("map_inspect_more"))}</button>` : ""}
    </div>
  `;
}

function seatDistrictSwitcherHTML(selectedCode = "") {
  return `
    <div class="seat-district-switcher" aria-label="${esc(t("map_inspect_select_label"))}">
      ${districtSwitchRowHTML(selectedCode, false)}
    </div>
  `;
}

function setDistrictPickerOpen(open, focusOption = false) {
  const picker = document.getElementById("map-inspect-district-picker");
  if (!picker) return;
  const toggle = picker.querySelector("#map-inspect-district-toggle");
  const list = picker.querySelector("#map-inspect-district-list");
  if (!toggle || !list) return;
  const next = !!open;
  picker.classList.toggle("open", next);
  toggle.setAttribute("aria-expanded", next ? "true" : "false");
  list.hidden = !next;
  if (next && focusOption) {
    const target = list.querySelector('[aria-selected="true"]') || list.querySelector(".map-inspect-option");
    requestAnimationFrame(() => target?.focus());
  }
}

function districtPickerOpen() {
  const toggle = document.getElementById("map-inspect-district-toggle");
  return toggle?.getAttribute("aria-expanded") === "true";
}

function focusDistrictPickerOption(current, key) {
  const list = document.getElementById("map-inspect-district-list");
  if (!list) return;
  const options = [...list.querySelectorAll(".map-inspect-option")];
  if (!options.length) return;
  const currentIndex = Math.max(0, options.indexOf(current));
  let nextIndex = currentIndex;
  if (key === "ArrowDown") nextIndex = Math.min(options.length - 1, currentIndex + 1);
  else if (key === "ArrowUp") nextIndex = Math.max(0, currentIndex - 1);
  else if (key === "Home") nextIndex = 0;
  else if (key === "End") nextIndex = options.length - 1;
  options[nextIndex].focus();
}

function mapInspectOverviewHTML(seat) {
  if (!seat) return "";
  const r = resultFor(seat);
  if (!r) {
    return `
      <div class="map-inspect-overview">
        <span>${esc(t("rep"))}</span>
        <strong>${esc(t("rep_ph"))}</strong>
      </div>
    `;
  }
  const card = formatResultCard(r);
  const partyLabel = card.party && card.party.label && card.party.label !== r.coalition ? esc(card.party.label) : "";
  const blocPill = r.coalition ? `<span class="pill" style="background:${partyColor(r.coalition)};color:#fff">${esc(r.coalition)}</span>` : "";
  // A BUTTON, not a div: the YB overview is the biggest thing in the tray and reads as
  // tappable — so it is. It opens the same detail as "More" (#map-inspect-details handler).
  return `
    <button id="map-inspect-details" class="map-inspect-overview" type="button" title="${esc(t("map_inspect_more"))}">
      <span>${esc(t("card_current_yb"))}</span>
      <strong>${esc(r.name)}</strong>
      <p>${partyLabel ? `${partyLabel} ` : ""}${blocPill}</p>
    </button>
  `;
}

let lastTraySelection = null;
function renderMapInspectTray() {
  if (!MAP_INSPECT_TRAY) return;
  if (!state.mapInspect || !state.openState) {
    MAP_INSPECT_TRAY.hidden = true;
    MAP_INSPECT_TRAY.innerHTML = "";
    MAP_INSPECT_TRAY.classList.remove("has-select");
    MAP_INSPECT_TRAY.classList.remove("has-selection");
    lastTraySelection = null;
    syncMapInspectButton();
    return;
  }
  const seat = selectedSeat();
  MAP_INSPECT_TRAY.hidden = false;
  MAP_INSPECT_TRAY.classList.add("has-select");
  MAP_INSPECT_TRAY.classList.toggle("has-selection", !!seat);
  // mobile tray: surface the election door when the contested state is open
  const prnRow = prnActiveForState(state.openState) && !state.prnMode
    ? `<button id="prn-open-tray" class="prn-open-btn prn-open-compact" type="button">🗳️ ${esc(t("prn_open"))} →</button>`
    : "";
  MAP_INSPECT_TRAY.innerHTML = `
    <div class="map-inspect-choice">
      ${prnRow}
      ${mapInspectOverviewHTML(seat)}
      ${districtSwitchRowHTML(state.selected || "", !!seat)}
    </div>
  `;
  // the YB overview answers a NEW selection with a small rise-in (causality, not noise:
  // re-renders that keep the same selection stay still)
  if (seat && state.selected !== lastTraySelection) {
    animateIn(MAP_INSPECT_TRAY.querySelector(".map-inspect-overview"), 6);
  }
  lastTraySelection = state.selected || null;
  syncMapInspectButton();
}

function refitOpenStateMap(delay = 0) {
  if (!state.openState) return;
  const run = () => {
    syncMapToCard();
    // During the More pop the onLayout camera glide owns the viewBox — a refit here
    // (setMapInspect(false) inside the swap's mutate) would restart the glide a frame
    // in and stutter its launch.
    if (mapInspectDetailsAnimating) return;
    // Every view frames the WHOLE state — in mobile seat detail it simply refits to the
    // shorter band's aspect (nothing cut off; the selected district stays highlighted).
    zoomToState(state.openState);
    requestAnimationFrame(syncMapToCard);
  };
  if (delay) setTimeout(run, delay);
  else requestAnimationFrame(run);
}

function refitOpenStateMapSettled() {
  refitOpenStateMap();
  refitOpenStateMap(140);
  refitOpenStateMap(360);
}

function setMapInspect(open) {
  const next = !!open && !!state.openState && MOBILE_MAP_INSPECT_MQ.matches;
  if (state.mapInspect === next) {
    renderMapInspectTray();
    syncMapInspectButton();
    if (next) refitOpenStateMapSettled();
    else refitOpenStateMap();
    return;
  }
  state.mapInspect = next;
  document.body.classList.toggle("map-inspect", next);
  if (next) setPanelView("state");
  renderMapInspectTray();
  syncMapInspectButton();
  if (next) refitOpenStateMapSettled();
  else refitOpenStateMap();
}

function inspectMapBounds() {
  if (!state.openState) return null;
  const b = stateBBox(state.openState);
  const pad = Math.max(b.w, b.h) * 0.18 + 8;
  return { x: b.x - pad, y: b.y - pad, w: b.w + pad * 2, h: b.h + pad * 2 };
}

function clampInspectViewBox(vb) {
  const bounds = inspectMapBounds();
  if (!bounds) return vb;
  const [x, y, w, h] = vb;
  const cx = Math.max(bounds.x, Math.min(bounds.x + bounds.w, x + w / 2));
  const cy = Math.max(bounds.y, Math.min(bounds.y + bounds.h, y + h / 2));
  return [cx - w / 2, cy - h / 2, w, h];
}

function setViewBoxNow(vb) {
  cancelAnimationFrame(animId);
  viewBox = vb.slice();
  SVG.setAttribute("viewBox", viewBox.map((n) => n.toFixed(2)).join(" "));
  syncStageLabelPosition();
  syncSelectedTexture();
  syncLiveBadge();
}

// The map band was just resized by layout (oldRect → newRect) while the viewBox is
// unchanged. Rewrite the viewBox so the content renders PIXEL-IDENTICAL in the new
// band — same scale, same screen position — so a follow-up animateTo carries the whole
// visual move as one distortion-free camera glide (no element FLIP, no scaleY stretch).
function setViewBoxPreservingScreen(oldRect, newRect) {
  if (!oldRect || !newRect || oldRect.width <= 0 || oldRect.height <= 0 || newRect.width <= 0 || newRect.height <= 0) return;
  const [vx, vy, vw, vh] = viewBox;
  const k = Math.min(oldRect.width / vw, oldRect.height / vh);   // xMidYMid meet scale
  if (!Number.isFinite(k) || k <= 0) return;
  const ox = oldRect.left + (oldRect.width - vw * k) / 2;        // content origin on screen
  const oy = oldRect.top + (oldRect.height - vh * k) / 2;
  setViewBoxNow([
    vx + (newRect.left - ox) / k,
    vy + (newRect.top - oy) / k,
    newRect.width / k,
    newRect.height / k
  ]);
}

function zoomToDistrict(seat, ms = 320, ease = undefined) {
  if (!seat || !seat.bbox) return;
  const b = seat.bbox;
  const pad = Math.max(b.w, b.h) * 0.85 + 5;
  let w = b.w + pad * 2;
  let h = b.h + pad * 2;
  const ar = stateFrameAspect();
  if (w / h > ar) h = w / ar;
  else w = h * ar;
  const cx = b.x + b.w / 2;
  const cy = b.y + b.h / 2;
  animateTo(clampInspectViewBox([cx - w / 2, cy - h / 2, w, h]), ms, ease);
}

function previewDistrict(code, zoom = false) {
  const seat = state.data[state.tier] && state.data[state.tier].byCode.get(code);
  if (!seat || seat.state !== state.openState) return;
  state.selected = code;
  setSelectedDistrict(code);
  renderMapInspectTray();
  if (zoom) requestAnimationFrame(() => zoomToDistrict(seat));
}

function locateMapInspectDistrict(btn, options = {}) {
  if (locating) return;
  const showDetails = !!options.showDetails;
  locating = true;
  setLocatingControl(btn, true);
  findSeatByLocation().then(
    (seat) => {
      if (seat.state !== state.openState) openStateCard(seat.state);
      if (MOBILE_MAP_INSPECT_MQ.matches && !showDetails) setMapInspect(true);
      requestAnimationFrame(() => {
        if (showDetails) {
          showDistrict(seat.code);   // its mobile branch refits the whole state to the band
        } else {
          previewDistrict(seat.code, true);
        }
      });
    },
    (key) => {
      showToast(key || "loc_error");
    }
  ).finally(() => {
    locating = false;
    setLocatingControl(btn, false);
  });
}

let mapInspectDetailsAnimating = false;
async function showMapInspectDetails(options = {}) {
  const code = state.selected;
  if (!code) return;
  const seat = state.data[state.tier] && state.data[state.tier].byCode.get(code);
  if (!seat) return;
  const shouldPop = !!options.pop && state.mapInspect && MOBILE_MAP_INSPECT_MQ.matches;
  if (shouldPop) {
    if (mapInspectDetailsAnimating) return;
    mapInspectDetailsAnimating = true;
    try {
      await swapCardWithMinimizePop(PANEL_STATE, () => {
        state.selected = code;
        setSelectedDistrict(code);
        setMapInspect(false);
        setPanelView("seat");
        STATE_INFO.innerHTML = stateSeatCardHTML(seat);
        resetStateInfoScroll();
        writeHash();
      }, (firstMap, lastMap) => {
        // The map's whole move is ONE viewBox camera glide: rewrite the viewBox so the
        // state renders pixel-identical in the just-resized band (no snap), hold it there
        // while the card pops upward OVER it (card z-30 > stage z-1), then — only once
        // the rise is clearly underway — glide the WHOLE state up into the band (never
        // crop it). Returning true skips the element FLIP (its non-uniform scaleY
        // stretched the geometry mid-move).
        if (MOBILE_MAP_INSPECT_MQ.matches && state.openState) {
          if (!firstMap || !lastMap) {           // reduced-motion / anim-off: jump straight
            zoomToState(state.openState);
            return true;
          }
          setViewBoxPreservingScreen(firstMap, lastMap);
          clearTimeout(detailGlideTimer);
          detailGlideTimer = setTimeout(() => {
            // still in district detail? (a fast back-tap within the delay cancels the glide)
            if (state.openState && PANEL.classList.contains("seat-detail")) {
              zoomToState(state.openState, DETAIL_GLIDE_MS, DETAIL_POP_EASE_FN);
            }
          }, DETAIL_GLIDE_DELAY_MS);
          return true;
        }
        return false;
      });
    } finally {
      mapInspectDetailsAnimating = false;
    }
    return;
  }
  setMapInspect(false);
  showDistrict(code);
}

if (MOBILE_MAP_INSPECT_MQ.addEventListener) {
  MOBILE_MAP_INSPECT_MQ.addEventListener("change", (e) => { if (!e.matches) setMapInspect(false); });
} else {
  MOBILE_MAP_INSPECT_MQ.addListener((e) => { if (!e.matches) setMapInspect(false); });
}

function stateBBox(name) {
  const d = state.data[state.tier];
  let a = Infinity, b = Infinity, c = -Infinity, e = -Infinity;
  for (const s of d.seats) {
    if (s.state !== name) continue;
    const x = s.bbox;
    if (x.x < a) a = x.x;
    if (x.y < b) b = x.y;
    if (x.x + x.w > c) c = x.x + x.w;
    if (x.y + x.h > e) e = x.y + x.h;
  }
  return { x: a, y: b, w: c - a, h: e - b };
}

// spotlight the open state on the main overview map: keep its seats lit, dim the rest.
// name === null clears the effect (no class left on any path).
function highlightState(name) {
  const d = state.data[state.tier];
  if (!d) return;
  for (const s of d.seats) {
    const p = state.paths.get(s.code);
    if (!p) continue;
    p.classList.toggle("instate", name != null && s.state === name);
    p.classList.toggle("outstate", name != null && s.state !== name);
  }
}

function stateSummaryHTML(name) {
  if (state.prnMode && prnActiveForState(name)) return prnSummaryHTML();
  const d = state.data[state.tier];
  const seats = d.seats.filter((s) => s.state === name);
  const tally = {};
  const rows = [];
  let tSum = 0, tN = 0, voteSum = 0, voteN = 0, candidateSum = 0, candidateN = 0;
  const fmtInt = (n) => Number.isFinite(n) ? n.toLocaleString() : "";
  const fmtPct = (n) => {
    if (!Number.isFinite(n)) return "";
    const v = Math.round(n * 10) / 10;
    return (Number.isInteger(v) ? String(v) : v.toFixed(1)) + "%";
  };
  const seatLabel = (row) => {
    const code = displayCode(row.seat, state.tier) || row.seat.code;
    return [code, row.seat.name].filter(Boolean).join(" · ");
  };
  const marginHTML = (row) => {
    const majority = fmtInt(row.card.majority);
    if (!majority) return "";
    const pct = Number.isFinite(row.card.majorityPct) ? ` <span class="muted">(${fmtPct(row.card.majorityPct)})</span>` : "";
    return `<span class="mono">${majority}</span>${pct}`;
  };
  for (const s of seats) {
    const card = formatResultCard(stateSummaryResultFor(s));
    if (!card) continue;
    rows.push({ seat: s, card });
    if (card.coalition) tally[card.coalition] = (tally[card.coalition] || 0) + 1;
    if (card.turnout != null) { tSum += card.turnout; tN++; }
    if (card.votes != null) { voteSum += card.votes; voteN++; }
    if (card.candidates != null) { candidateSum += card.candidates; candidateN++; }
  }
  const ents = Object.entries(tally).sort((a, b) => {
    if (b[1] !== a[1]) return b[1] - a[1];
    const ai = COALITION_ORDER.indexOf(a[0]), bi = COALITION_ORDER.indexOf(b[0]);
    if (ai !== -1 || bi !== -1) return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    return a[0].localeCompare(b[0]);
  });
  if (!ents.length) return '<p class="state-tap-hint">' + esc(t("tap_district")) + "</p>";
  const bar = ents.map(([c, n]) => '<span style="flex:' + n + ';background:' + partyColor(c) + '"></span>').join("");
  const key = ents.map(([c, n]) => '<span class="sw" style="background:' + partyColor(c) + '"></span>' + esc(c) + " <b>" + n + "</b>").join("");

  const stat = (labelKey, valueHTML, note) => (
    '<div class="state-stat">' +
      '<span class="state-stat-label">' + esc(t(labelKey)) + "</span>" +
      '<span class="state-stat-value">' + valueHTML + "</span>" +
      (note ? '<span class="state-stat-note">' + esc(note) + "</span>" : "") +
    "</div>"
  );
  const stats = [];
  const leader = ents[0];
  if (leader) {
    const [coalition, count] = leader;
    const pct = seats.length ? Math.round((count / seats.length) * 100) : 0;
    stats.push(stat(
      "state_leading_bloc",
      `<span class="state-bloc"><span class="sw" style="background:${partyColor(coalition)}"></span>${esc(coalition)}</span>`,
      `${count}/${seats.length} · ${t("state_seat_share", { pct })}`
    ));
  }
  if (tN) {
    const turnouts = rows.map((row) => row.card.turnout).filter(Number.isFinite);
    const min = Math.min(...turnouts), max = Math.max(...turnouts);
    stats.push(stat(
      "state_avg_turnout",
      `<span class="mono">${fmtPct(tSum / tN)}</span>`,
      t("state_turnout_range", { min: fmtPct(min), max: fmtPct(max) })
    ));
  }
  const withMajority = rows.filter((row) => Number.isFinite(row.card.majority));
  const closest = withMajority.reduce((best, row) => !best || row.card.majority < best.card.majority ? row : best, null);
  const largest = withMajority.reduce((best, row) => !best || row.card.majority > best.card.majority ? row : best, null);
  if (closest) stats.push(stat("state_closest_race", marginHTML(closest), seatLabel(closest)));
  if (largest && largest !== closest) stats.push(stat("state_largest_majority", marginHTML(largest), seatLabel(largest)));
  if (voteN) stats.push(stat("state_winner_votes", `<span class="mono">${fmtInt(voteSum)}</span>`, t("state_winner_count", { n: voteN })));
  if (candidateN) stats.push(stat("state_avg_candidates", `<span class="mono">${(candidateSum / candidateN).toFixed(1)}</span>`, t("state_per_seat")));

  // desktop/landscape: the mobile inspect tray isn't shown, so give the state card
  // its own district finder (dropdown + locate) at the TOP — it's the primary action
  // (you opened the state to drill into a district) and must be visible without
  // scrolling past the stats + economy. On mobile the tray already has one.
  const desktopFinder = !MOBILE_MAP_INSPECT_MQ.matches
    ? `<div class="state-info-h muted">${esc(t("find_district"))}</div>
       <div class="state-district-find state-district-find-top">${districtSwitchRowHTML(state.selected || "", false)}</div>`
    : "";
  return (
    prnBannerHTML(name) +
    desktopFinder +
    '<div class="state-info-h muted"' + (desktopFinder ? ' style="margin-top:16px"' : "") + ">" + esc(t("state_makeup")) + "</div>" +
    '<div class="sharebar">' + bar + "</div>" +
    '<div class="sharebar-key">' + key + "</div>" +
    (stats.length ? '<div class="state-stats">' + stats.join("") + "</div>" : "") +
    stateContextHTML(name) +
    (desktopFinder ? "" : '<p class="state-tap-hint muted">' + esc(t("tap_district")) + "</p>")
  );
}

// per-state context rows: head of government + the election clock (from
// public/data/state-context.json, curated + verified 2026-07-04)
function fmtDMY(iso) {
  return `${fmtDayMonth(iso)} ${iso.slice(0, 4)}`;
}
function daysUntil(iso) {
  return Math.ceil((new Date(iso + "T00:00:00+08:00").getTime() - Date.now()) / 86400000);
}
function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00+08:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function stateContextHTML(name) {
  const ctx = state.stateCtx;
  const st = ctx && ctx.states && ctx.states[name];
  if (!st) return "";
  const rows = [];
  if (st.gov) {
    const g = st.gov;
    const title = g.title === "MB" ? "Menteri Besar" : g.title === "KM" ? "Ketua Menteri" : g.title;
    const care = g.caretaker ? ` <span class="muted">(${esc(t("ctx_caretaker"))})</span>` : "";
    rows.push(`<dt>${esc(title)}</dt><dd>${esc(g.name)} · ${esc(g.party)} (${esc(g.coalition)})${care}</dd>`);
  }
  const clock = st.clock;
  if (clock && !prnActiveForState(name)) {
    let v = "";
    if (clock.federal) {
      v = `${t("ctx_federal")} · ${t("ctx_due_by", { d: fmtDMY(addDays(ctx.parlimen.dissolve_by, 60)) })}`;
    } else if (clock.next) {
      v = `${fmtDMY(clock.next)} · ${t("ctx_in_days", { n: daysUntil(clock.next) })}`;
    } else if (clock.dissolve_by) {
      const due = addDays(clock.dissolve_by, 60);   // dissolution deadline + 60-day window
      v = t("ctx_due_by", { d: fmtDMY(due) });
      if (clock.expected) v += ` · ${t("ctx_expected", { y: clock.expected })}`;
      v += ` · ${t("ctx_in_days", { n: daysUntil(due) })}`;
    }
    if (v) rows.push(`<dt>${esc(t("ctx_next_election"))}</dt><dd>${esc(v)}</dd>`);
  }
  // economy report card (Azlan's suggestion: who's growing, who's doing well)
  const econ = state.stateEcon;
  const ec = econ && econ.states && econ.states[name];
  let econSrc = "";
  if (ec) {
    const nat = econ.national || {};
    if (Number.isFinite(ec.gdp_growth)) {
      const diff = Number.isFinite(nat.gdp_growth) ? ec.gdp_growth - nat.gdp_growth : null;
      const arrow = diff == null ? "" : (diff >= 0 ? ' <span class="econ-up">▲</span>' : ' <span class="econ-down">▼</span>');
      const natRef = Number.isFinite(nat.gdp_growth) ? ` <span class="muted">(${esc(t("econ_national"))} ${nat.gdp_growth}%)</span>` : "";
      rows.push(`<dt>${esc(t("econ_growth", { y: econ.year_gdp }))}</dt><dd><span class="mono">${ec.gdp_growth}%</span>${arrow}${natRef}</dd>`);
    }
    if (ec.gdp_pc) rows.push(`<dt>${esc(t("econ_pc"))}</dt><dd class="mono">RM ${ec.gdp_pc.toLocaleString()}</dd>`);
    if (Number.isFinite(ec.u_rate)) rows.push(`<dt>${esc(t("econ_unemp", { q: econ.u_qtr }))}</dt><dd class="mono">${ec.u_rate}%</dd>`);
    if (ec.income_median) rows.push(`<dt>${esc(t("econ_income", { y: econ.income_year }))}</dt><dd class="mono">RM ${ec.income_median.toLocaleString()}</dd>`);
    econSrc = `<p class="src-line muted">${esc(t("econ_src"))}</p>`;
  }
  return rows.length ? `<dl class="rows state-ctx">${rows.join("")}</dl>${econSrc}` : "";
}

/* ===== live election (PRN16 Johor) =====
   Data: public/data/prn16-johor.json (config + SPR-confirmed candidates, baked by
   pipeline/05_prn16_johor.py). Live results arrive later via /api/live/johor. */
function liveElection() {
  return (state.prn16 && state.prn16.election) || null;
}
function prnActiveForState(name) {
  const e = liveElection();
  return e && e.state === name ? e : null;
}
// coalition swatches for the PRN cards: GE15 blocs reuse partyColor; PRN-only
// players get their own. fg is the pill text colour on that swatch.
const PRN_COLORS = {
  BERSAMA: { bg: "#7a5cc7", fg: "#fff" },
  "MUDA-PSM": { bg: "#d0d4da", fg: "#101318" },
  OTHERS: { bg: "#5d6b7d", fg: "#fff" },
};
function prnCoalColor(coal) {
  return PRN_COLORS[coal] || { bg: partyColor(coal), fg: "#fff" };
}
function prnCountdownLabel(e) {
  const days = Math.ceil((new Date(e.polling_day + "T00:00:00+08:00").getTime() - Date.now()) / 86400000);
  if (days > 1) return t("prn_days", { n: days });
  if (days === 1) return t("prn_tomorrow");
  if (days === 0) return t("prn_today");
  return null;
}
function fmtDayMonth(iso) {
  const d = new Date(iso + "T00:00:00+08:00");
  const months = lang === "ms"
    ? ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogo", "Sep", "Okt", "Nov", "Dis"]
    : ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${d.getDate()} ${months[d.getMonth()]}`;
}
// banner atop the contested state's card (only outside PRN view)
function prnBannerHTML(name) {
  const e = prnActiveForState(name);
  if (!e || state.prnMode) return "";
  const cd = prnCountdownLabel(e);
  return `<div class="prn-banner">
    <div class="prn-banner-h"><span class="live-dot" aria-hidden="true"></span>🗳️ ${esc(e.name)}</div>
    <div class="prn-banner-sub muted">${esc(t("prn_polling"))} ${esc(fmtDayMonth(e.polling_day))}${cd ? " · " + esc(cd) : ""}</div>
    <button id="prn-open" class="prn-open-btn" type="button">${esc(t("prn_open"))} →</button>
  </div>`;
}
// polling-night tally block: won (solid) counts per coalition racing to the majority line
function prnLiveTallyHTML() {
  const e = liveElection();
  const live = state.prnLive;
  if (!e || !live || !live.seats) return "";
  const won = {}, leading = {};
  let declared = 0;
  for (const r of Object.values(live.seats)) {
    const coal = r.coalition || r.party;
    if (!coal) continue;
    if (r.status === "won" || r.status === "official") { won[coal] = (won[coal] || 0) + 1; declared++; }
    else if (r.status === "leading") leading[coal] = (leading[coal] || 0) + 1;
  }
  const order = Object.entries(won).sort((a, b) => b[1] - a[1]);
  const bar = order.map(([coal, n]) => {
    const c = prnCoalColor(coal);
    return `<span style="width:${(100 * n / e.total_seats).toFixed(2)}%;background:${c.bg}"></span>`;
  }).join("");
  const key = order.map(([coal, n]) => {
    const c = prnCoalColor(coal);
    const lead = leading[coal] ? ` <span class="muted">+${leading[coal]}</span>` : "";
    return `<span class="state-bloc"><span class="sw" style="background:${c.bg}"></span>${esc(coal)} <b>${n}</b>${lead}</span>`;
  }).join("");
  const updated = live.updated ? new Date(live.updated).toLocaleTimeString(lang === "ms" ? "ms-MY" : "en-MY", { hour: "2-digit", minute: "2-digit" }) : "";
  return `<div class="state-info-h muted" style="margin-top:14px">${esc(t("prn_live_tally", { n: declared, total: e.total_seats }))}</div>
    <div class="sharebar prn-live-bar">${bar}</div>
    <div class="sharebar-key">${key || `<span class="muted">${esc(t("prn_live_waiting"))}</span>`}</div>
    <p class="prn-majority muted">${esc(t("prn_majority", { n: e.majority }))}${updated ? ` · ${esc(t("prn_live_updated", { t: updated }))}` : ""}${live.source ? ` · ${esc(live.source)}` : ""}</p>`;
}

// the PRN summary card (replaces the state make-up while the election view is on)
function prnSummaryHTML() {
  const e = liveElection();
  const p = state.prn16;
  if (!e || !p) return "";
  const liveNow = state.prnLive && (state.prnLive.phase === "live" || state.prnLive.phase === "final");
  const cd = liveNow ? null : prnCountdownLabel(e);
  const total = Object.values(p.contested || {}).reduce((a, b) => a + b, 0);
  const order = Object.entries(p.contested || {}).sort((a, b) => b[1] - a[1]);
  const bar = order.map(([coal, n]) => {
    const c = prnCoalColor(coal);
    return `<span style="width:${(100 * n / total).toFixed(2)}%;background:${c.bg}"></span>`;
  }).join("");
  const key = order.map(([coal, n]) => {
    const c = prnCoalColor(coal);
    return `<span class="state-bloc"><span class="sw" style="background:${c.bg}"></span>${esc(coal)} ${n}</span>`;
  }).join("");
  const rows = [
    [t("prn_nomination"), fmtDayMonth(e.nomination_day)],
    [t("prn_early"), fmtDayMonth(e.early_voting)],
    [t("prn_polling"), fmtDayMonth(e.polling_day) + " 🗳️"],
  ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
  const head = `<div class="prn-banner-h"><span class="live-dot" aria-hidden="true"></span>🗳️ ${esc(e.name)}${liveNow ? ` <span class="prn-live-chip">${esc(t(state.prnLive.phase === "final" ? "prn_phase_final" : "prn_phase_live"))}</span>` : ""}</div>`;
  if (liveNow) {
    // polling night: the tally IS the card
    return `<div class="prn-summary">
      ${head}
      ${prnLiveTallyHTML()}
      <p class="state-tap-hint muted">${esc(t("prn_tap_hint"))}</p>
      <p class="src-line muted">${esc(t("prn_source"))}</p>
      <button id="prn-close" class="prn-close-btn" type="button">${esc(t("prn_close"))}</button>
    </div>`;
  }
  const prnFinder = !MOBILE_MAP_INSPECT_MQ.matches
    ? `<div class="state-info-h muted" style="margin-top:14px">${esc(t("find_district"))}</div><div class="state-district-find state-district-find-top">${districtSwitchRowHTML(state.selected || "", false)}</div>`
    : "";
  return `<div class="prn-summary">
    ${head}
    ${cd ? `<div class="prn-countdown">${esc(cd)}</div>` : ""}
    ${prnFinder}
    <dl class="rows prn-dates"${prnFinder ? ' style="margin-top:14px"' : ""}>${rows}</dl>
    <div class="state-info-h muted" style="margin-top:14px">${esc(t("prn_contested"))} · ${total}</div>
    <div class="sharebar">${bar}</div>
    <div class="sharebar-key">${key}</div>
    <p class="prn-majority muted">${esc(t("prn_majority", { n: e.majority }))}</p>
    ${prnFinder ? "" : `<p class="state-tap-hint muted">${esc(t("prn_tap_hint"))}</p>`}
    <a class="prn-check" href="${esc(e.check_voter_url)}" target="_blank" rel="noopener">${esc(t("prn_check"))}</a>
    <p class="src-line muted">${esc(t("prn_source"))}</p>
    <button id="prn-close" class="prn-close-btn" type="button">${esc(t("prn_close"))}</button>
  </div>`;
}
// per-seat candidate card (replaces the GE15-fallback seat card inside PRN view)
function prnSeatCardHTML(seat, entry) {
  const e = liveElection();
  const nameKey = (s) => s.toLowerCase().replace(/\b(bin|binti|a\/l|a\/p|anak)\b/g, " ").replace(/[^a-z]+/g, "");
  const cands = entry.candidates.map((c) => {
    const col = prnCoalColor(c.coalition);
    const alias = c.ballot_name && nameKey(c.ballot_name) !== nameKey(c.name)
      ? ` <small class="muted">(${esc(c.ballot_name)})</small>` : "";
    const sym = c.symbol ? ` <small class="muted">· ${esc(c.symbol)}</small>` : "";
    const party = c.party && c.party !== c.coalition ? `${esc(c.coalition)} · ${esc(c.party)}` : esc(c.coalition);
    return `<div class="prn-cand"><span class="prn-cand-name">${esc(c.name)}${alias}${sym}</span>` +
      `<span class="pill" style="background:${col.bg};color:${col.fg}">${party}</span></div>`;
  }).join("");
  const meta = [];
  if (entry.electorate) meta.push(`<dt>${esc(t("prn_electorate"))}</dt><dd class="mono">${entry.electorate.toLocaleString()}</dd>`);
  if (entry.incumbent_2022) {
    const maj = entry.majority_2022 ? ` <span class="muted">(${esc(entry.majority_2022)})</span>` : "";
    meta.push(`<dt>${esc(t("prn_incumbent"))}</dt><dd>${esc(entry.incumbent_2022)}${entry.incumbent_party_2022 ? " · " + esc(entry.incumbent_party_2022) : ""}${maj}</dd>`);
  }
  // campaign-window headlines per candidate (links only — never paraphrased)
  const seatNews = state.prnNews && state.prnNews[seat.code];
  let newsHTML = "";
  if (seatNews) {
    const blocks = entry.candidates.map((c) => {
      const items = seatNews[c.name];
      if (!items || !items.length) return "";
      const links = items.map((n) =>
        `<a class="prn-news-item" href="${esc(n.u)}" target="_blank" rel="noopener">
          <span class="prn-news-t">${esc(n.t)}</span>
          <span class="prn-news-s muted">${esc(n.s)}${n.d ? " · " + esc(fmtDayMonth(n.d)) : ""}</span></a>`).join("");
      return `<div class="prn-news-cand"><div class="prn-news-name muted">${esc(c.name)}</div>${links}</div>`;
    }).filter(Boolean).join("");
    if (blocks) {
      newsHTML = `<div class="state-info-h muted" style="margin-top:14px">${esc(t("prn_news"))}</div>
        <div class="prn-news">${blocks}</div>
        <p class="src-line muted">${esc(t("prn_news_note"))}</p>`;
    }
  }
  return `<div class="seat-head prn-seat-head">
      <div class="kicker">🗳️ ${esc(e.name)} · ${esc(entry.ncode)}</div>
      <h2>${esc(entry.name)}</h2>
      ${seat.parlimen ? `<div class="where">${esc(t("parlimen_label"))} <b>${esc(parlimenContext(seat))}</b></div>` : ""}
    </div>
    <div class="state-info-h muted">${esc(t("prn_candidates"))} · ${entry.candidates.length}</div>
    <div class="prn-cands">${cands}</div>
    ${newsHTML}
    ${meta.length ? `<dl class="rows prn-dates">${meta.join("")}</dl>` : ""}
    <p class="callout prn-note">${esc(t("prn_results_note"))}</p>
    <p class="src-line muted">${esc(t("prn_source"))}</p>`;
}
async function openPrnMode() {
  const e = liveElection();
  if (!e || state.prnMode) return;
  if (state.tier !== e.tier) await setTier(e.tier);   // before the flag — setTier exits PRN mode
  state.prnMode = true;
  document.body.classList.add("prn-mode");
  openStateCard(e.state);   // (re)runs the isolation choreography for the contested state
  paint();
  syncLiveBadge();
  refreshPrnLive();
  writeHash();
}
function closePrnMode(options = {}) {
  if (!state.prnMode) return;
  state.prnMode = false;
  clearTimeout(prnLiveTimer);
  document.body.classList.remove("prn-mode");
  if (!options.silent) {
    if (state.openState) {
      STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
      renderMapInspectTray();
    }
    paint();
    syncLiveBadge();
    writeHash();
  }
}
// polling-night data: harmless no-op while /api/live/johor reports campaign phase.
// While the PRN view is open in a live phase, re-poll every ~75s and re-render.
let prnLiveTimer = null;
async function refreshPrnLive() {
  clearTimeout(prnLiveTimer);
  let live = null;
  try {
    const r = await fetch("/api/live/johor");
    if (r.ok) live = await r.json();
  } catch (_) {}
  if (!live) {
    try {
      // dev parity: the python dev server has no /api — read the baked asset directly
      const a = await fetch("data/live-johor.json", { cache: "no-store" });
      if (a.ok) live = await a.json();
    } catch (_) {}
  }
  if (live && live.phase && live.phase !== "campaign") {
    state.prnLive = live;
    if (state.prnMode) {
      paint();
      renderPrnSummaryIfOpen();
      // the state card's reveal choreography may still be swapping content in —
      // re-assert once it has settled so the LIVE tally can't lose the race
      setTimeout(renderPrnSummaryIfOpen, 800);
      prnLiveTimer = setTimeout(refreshPrnLive, 75000);
    }
  }
}
function renderPrnSummaryIfOpen() {
  if (state.prnMode && state.openState && PANEL.classList.contains("state-summary")) {
    STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
  }
}
// overview badge pinned above the contested state, tracking the camera
function syncLiveBadge() {
  const el = document.getElementById("live-badge");
  if (!el) return;
  const e = liveElection();
  const show = !!e && !state.openState;
  el.hidden = !show;
  if (!show) return;
  let b;
  try { b = stateBBox(e.state); } catch (_) { el.hidden = true; return; }
  if (!b || !Number.isFinite(b.x)) { el.hidden = true; return; }
  const r = SVG.getBoundingClientRect();
  const [vx, vy, vw, vh] = viewBox;
  if (!(vw > 0) || !(r.width > 0)) return;
  const k = Math.min(r.width / vw, r.height / vh);
  const ox = r.left + (r.width - vw * k) / 2;
  const oy = r.top + (r.height - vh * k) / 2;
  el.style.left = `${ox + (b.x + b.w / 2 - vx) * k}px`;
  el.style.top = `${Math.max(oy + (b.y - vy) * k - 10, 64)}px`;
}

function openStateCard(name) {
  if (!name) return;
  const d = state.data[state.tier];
  const seats = d.seats.filter((s) => s.state === name);
  document.getElementById("state-name").textContent = name;
  const n = seats.length;
  const countKey = "state_count_" + (state.tier === "parlimen" ? "parlimen" : "dun") + (n === 1 ? "_one" : "");
  document.getElementById("state-count").textContent = t(countKey, { n });
  // set openState/selected BEFORE rendering — the desktop district finder reads
  // districtOptionsForOpenState(), which is empty until state.openState is set.
  state.openState = name;
  state.selected = null;
  STATE_INFO.innerHTML = stateSummaryHTML(name);
  setStageLabel(name);
  // isolate: fade the other states out, reveal this state's district borders, zoom in.
  // the big map IS the district map now — no separate mini-map in the card.
  SEATS.classList.add("isolated");
  document.body.classList.add("state-open");   // card rises into a tall backdrop, map lifts above it
  setMapInspect(MOBILE_MAP_INSPECT_MQ.matches);
  highlightState(name);
  zoomToState(name);
  // once the zoom settles, re-pin against the GROUND-TRUTH rendered state bottom (covers
  // any geometry edge case the deterministic pin might miss on an unusual viewport).
  clearTimeout(settleTimer);
  settleTimer = setTimeout(refitMeasured, (ANIM_OFF || REDUCE_MOTION.matches) ? 60 : 700);
  // choreograph: watch the overview card MINIMIZE, then the state backdrop springs up
  // from that minimized point. (Coming from another state card, just reveal + bounce.)
  clearTimeout(revealTimer);
  if (!ANIM_OFF && PANEL.classList.contains("empty")) {
    minimizeCard(PANEL_EMPTY);
    revealTimer = setTimeout(revealStateCard, 300);
  } else {
    revealStateCard();
  }
  writeHash();
}
let revealTimer = null, settleTimer = null;
function revealStateCard() {
  setPanelView("state");
  syncMapToCard();
  refitOpenStateMap();
  riseCard(PANEL_STATE, 0);          // the minimize already led; bounce up from the minimized bar
}

function showDistrict(code) {
  const seat = state.data[state.tier] && state.data[state.tier].byCode.get(code);
  if (!seat) return;
  const wasMapInspect = state.mapInspect;
  state.selected = code;
  // highlight the tapped district on the (static) zoomed-in map
  setSelectedDistrict(code);
  animateCardResize(PANEL_STATE, () => {   // grow/shrink the floating card to fit the detail
    if (wasMapInspect) setMapInspect(false);
    setPanelView("seat");
    STATE_INFO.innerHTML = stateSeatCardHTML(seat);
    resetStateInfoScroll();
  });
  animateIn(STATE_INFO, 6);   // the district detail swaps into the card under the header
  // Mobile detail: refit the WHOLE state to the short band's aspect (never crop it);
  // the selected district is highlighted, not zoomed to.
  if (MOBILE_MAP_INSPECT_MQ.matches && state.openState) {
    requestAnimationFrame(() => zoomToState(state.openState));
  }
  writeHash();
}

// two-level back: a chosen district → back to the state make-up; the state → overview.
function goBack() {
  if (state.selected && state.openState) {
    state.selected = null;
    clearSelectedDistrict();
    if (state.mapInspect) {
      renderMapInspectTray();
      writeHash();
      return;
    }
    if (MOBILE_MAP_INSPECT_MQ.matches) {
      animateCardResize(PANEL_STATE, () => {
        STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
        STATE_INFO.scrollTop = 0;
        setMapInspect(true);
      });
      writeHash();
      return;
    }
    animateCardResize(PANEL_STATE, () => {   // shrink the floating card back to the make-up size
      setPanelView("state");
      STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
      STATE_INFO.scrollTop = 0;
    });
    animateIn(STATE_INFO, 6);
    writeHash();
  } else {
    backToControls();
  }
}

function backToControls() {
  if (state.prnMode) closePrnMode({ silent: true });   // leaving the state leaves the election view
  state.mapInspect = false;
  document.body.classList.remove("map-inspect");
  renderMapInspectTray();
  syncMapInspectButton();
  state.selected = null;
  state.openState = null;
  setStageLabel(null);
  clearTimeout(revealTimer);
  clearTimeout(settleTimer);
  STATE_INFO.style.height = "";   // drop the pinned height for the next open / overview
  STATE_INFO.style.overflowY = "";
  PANEL_EMPTY.getAnimations().forEach((a) => a.cancel());   // clear the held minimize → overview shows full again
  SEATS.classList.remove("isolated");
  document.body.classList.remove("state-open");
  clearSelectedDistrict();
  highlightState(null);
  zoomFull();                 // zoom back out to the whole country
  syncMapToCard();            // state closed → release --map-h, map grows back to full height
  setPanelView("overview");
  clearMatches();
  setFindStatus(null);
  writeHash();
}

SEATS.classList.add("overview");   // the main map is always the states overview

STATE_SEATS.addEventListener("click", (e) => {
  const t2 = e.target.closest(".mini-seat");
  if (t2) showDistrict(t2.dataset.code);
});
document.getElementById("state-back")?.addEventListener("click", goBack);
document.getElementById("live-badge")?.addEventListener("click", () => openPrnMode());
PANEL_STATE.addEventListener("click", (e) => {
  if (e.target.closest("#prn-open") || e.target.closest("#prn-open-tray")) {
    openPrnMode();
    return;
  }
  if (e.target.closest("#prn-close")) {
    closePrnMode();
    return;
  }
  if (e.target.closest("#map-inspect-toggle")) {
    if (state.mapInspect && state.selected) {
      showMapInspectDetails();
      return;
    }
    setMapInspect(!state.mapInspect);
    return;
  }
  if (e.target.closest("#map-inspect-more")) {
    showMapInspectDetails({ pop: true });
    return;
  }
  if (e.target.closest("#map-inspect-details")) {
    showMapInspectDetails({ pop: true });
    return;
  }
  const mapInspectLocate = e.target.closest("#map-inspect-locate");
  if (mapInspectLocate) {
    locateMapInspectDistrict(mapInspectLocate, { showDetails: !state.mapInspect });
    return;
  }
  const districtToggle = e.target.closest("#map-inspect-district-toggle");
  if (districtToggle) {
    setDistrictPickerOpen(!districtPickerOpen());
    return;
  }
  const districtOption = e.target.closest("[data-map-inspect-district]");
  if (districtOption) {
    const code = districtOption.dataset.mapInspectDistrict;
    setDistrictPickerOpen(false);
    if (state.mapInspect) previewDistrict(code);
    else showDistrict(code);
    return;
  }
  const tab = e.target.closest("[data-seat-tab]");
  if (tab) {
    setSeatTab(tab.dataset.seatTab, true);
    return;
  }
  if (e.target.closest("#share-link")) shareLink();
  else if (e.target.closest("#share-card")) shareCard(e.target);
  else if (e.target === PANEL_STATE) goBack();   // tap the empty backdrop (behind the state) → step back
});
PANEL_STATE.addEventListener("keydown", (e) => {
  const districtToggle = e.target.closest("#map-inspect-district-toggle");
  if (districtToggle && ["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
    e.preventDefault();
    setDistrictPickerOpen(true, true);
    return;
  }
  const districtOption = e.target.closest("[data-map-inspect-district]");
  if (districtOption) {
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      focusDistrictPickerOption(districtOption, e.key);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setDistrictPickerOpen(false);
      document.getElementById("map-inspect-district-toggle")?.focus();
      return;
    }
  }
  const tab = e.target.closest("[data-seat-tab]");
  if (!tab) return;
  const i = SEAT_TABS.indexOf(tab.dataset.seatTab);
  if (i === -1) return;
  let next = null;
  if (e.key === "ArrowRight") next = SEAT_TABS[(i + 1) % SEAT_TABS.length];
  else if (e.key === "ArrowLeft") next = SEAT_TABS[(i - 1 + SEAT_TABS.length) % SEAT_TABS.length];
  else if (e.key === "Home") next = SEAT_TABS[0];
  else if (e.key === "End") next = SEAT_TABS[SEAT_TABS.length - 1];
  if (!next) return;
  e.preventDefault();
  setSeatTab(next, true);
});
document.addEventListener("click", (e) => {
  if (!e.target.closest("#map-inspect-district-picker")) setDistrictPickerOpen(false);
});
