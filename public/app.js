// MyPolitik — interactive map of Malaysia's electoral seats.
// Data-driven: boundaries render now; GE15 results + scores light up the
// "Parti"/"Skor" modes and panel rows as soon as their JSON exists.

import { encodeHash, decodeHash, pickInitialLang, findSeatForLocation, nearestSeat,
  formatResultCard, fitBox, partyColor, scoreColor, searchSeats,
  resultKey, displayCode, tallyCoalitions, stateHues, swatchTextColor,
  competitivenessFromMajorityPct, withCurrentAffiliation } from "./lib.js?v=145";
import { I18N } from "./i18n.js?v=153";

const SVG = document.getElementById("map");
const STATE_OUTLINES = document.getElementById("state-outlines");
const SEATS = document.getElementById("seats");
const SELECTED_OVERLAY = document.getElementById("selected-overlay");
const TOOLTIP = document.getElementById("tooltip");
const STAGE = document.getElementById("stage");
const TOPBAR = document.getElementById("topbar");
const TOP_CONTROLS = document.getElementById("top-controls");
const MOBILE_MENU = document.getElementById("mobile-menu");
const MOBILE_MENU_BTN = document.getElementById("mobile-menu-btn");
const THEME_META = document.querySelector('meta[name="theme-color"]');
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
  politicians: null,// {mps: {P.xxx -> {name, photo, bio, socials, ...}}} federal MP roster
  currentAffiliations: null,// source-linked affiliation/vacancy updates, separate from election results
  polProfiles: null,// source-linked candidate/person profile cards keyed by DUN seat
  seatContextJohor: null,// per-DUN context pack (pipeline/13_johor_enrich.py)
  excoJohor: null,// caretaker EXCO portfolio map
  stateEmblems: null,// state/federal territory coat-of-arms/seal assets + source manifest
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
const COALITION_ORDER = ["PH", "PN", "BN", "GPS", "GRS", "WARISAN", "KDM", "PBM", "STAR", "UPKO", "PSB", "BEBAS"];
const SEAT_TABS = ["overview", "results", "candidates", "voting"];
const isSeatTab = (tab) => SEAT_TABS.includes(tab);
const LOAD_GATED_SCORES = false;
const THEME_KEY = "mypolitik-theme";
const THEMES = ["dark"]; // light mode disabled — PRN + map chrome were unreadable
let theme = "dark";

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

function syncThemeControls() {
  // Theme toggle hidden while dark-only; keep attrs consistent if markup stays.
  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
    btn.hidden = true;
    btn.setAttribute("aria-hidden", "true");
    btn.setAttribute("tabindex", "-1");
  });
  if (THEME_META) THEME_META.setAttribute("content", "#0e0f12");
}

function setTheme(next, persist = true) {
  // Always dark — ignore light requests until light theme is reworked.
  theme = "dark";
  document.documentElement.dataset.theme = "dark";
  if (persist) {
    try { localStorage.setItem(THEME_KEY, "dark"); } catch (_) {}
  }
  syncThemeControls();
}

function toggleTheme() {
  setTheme("dark");
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
  syncThemeControls();
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
  // Dynamic views build their own HTML (not data-i18n), so applyStatic() can't reach
  // them — re-render whatever is open so the language actually changes the content.
  if (state.openState && BENTO_MQ.matches) renderStateBento();          // wide-screen state dashboard
  if (document.body.classList.contains("politicians-open")) {          // politicians directory
    renderPoliticiansDirectory((document.getElementById("pol-search") || {}).value || "");
  }
  renderSidebarStates();                                                // sidebar state list (election badge)
  if (document.body.classList.contains("news-open")) openNewsPage();    // news full page
  if (PLEDGES_MODAL && PLEDGES_MODAL.open) openPledgesModal();
}

// ---- helpers ----
const $ = (sel, el = document) => el.querySelector(sel);
// toggle a tab/segment button's active class AND its ARIA selected state together
const setOn = (el, on) => { el.classList.toggle("on", on); el.setAttribute("aria-selected", on ? "true" : "false"); };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pillStyle = (bg, fg) => `background:${bg};color:${fg || swatchTextColor(bg)}`;

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
    // DUN (state-assembly / PRN) results — MECO + six-state PRN (544/600 seats; Johor
    // via prn16). MUST paint after load: party mode paints DUN from resultsDun, and
    // if we only painted after GE15, every DUN seat stayed neutral grey until a mode
    // switch. (Perak etc. looked patchy/grey on mobile for this reason.)
    const rd = await fetch("data/results-dun.json");
    if (rd.ok) {
      state.resultsDun = await rd.json();
      paint();
      renderSummary();
    }
  } catch (_) {}
  try {
    // Election results remain historical; this optional layer powers present-day
    // affiliation and vacancy displays without rewriting the result record.
    const ca = await fetch("data/current-affiliations.json");
    if (ca.ok) { state.currentAffiliations = await ca.json(); paint(); }
  } catch (_) {}
  if (LOAD_GATED_SCORES) {
    try {
      const s = await fetch("data/scores.json");
      // AGENTS.md UNTOUCHABLE: "Keep Skor GATED ('Soon') even if scores.json appears."
      // Keep this optional fetch off until the score product is intentionally unlocked;
      // otherwise local static dev logs a noisy 404 for a deliberately absent file.
      if (s.ok) { state.scores = await s.json(); }
    } catch (_) {}
  }
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
    // coalition manifesto pledges for PRN Johor (pipeline/10_johor_pledges.py)
    const jp = await fetch("data/johor-pledges.json");
    if (jp.ok) state.johorPledges = await jp.json();
  } catch (_) {}
  try {
    // per-state context: MB/KM/Premier + election clock (pipeline/07_state_context.py)
    const sc = await fetch("data/state-context.json");
    if (sc.ok) state.stateCtx = await sc.json();
  } catch (_) {}
  try {
    // state/federal territory crests and seals, locally stored with source metadata
    const se = await fetch("data/state-emblems.json");
    if (se.ok) state.stateEmblems = await se.json();
  } catch (_) {}
  try {
    // per-state economy report card, DOSM via data.gov.my (pipeline/08_state_econ.py)
    const se = await fetch("data/state-econ.json");
    if (se.ok) state.stateEcon = await se.json();
  } catch (_) {}
  try {
    // MB/KM/Premier portraits, Wikimedia Commons (pipeline/10_gov_photos.py)
    const gp = await fetch("data/gov-photos.json");
    if (gp.ok) state.govPhotos = await gp.json();
  } catch (_) {}
  try {
    // ADUN portraits keyed by DUN seat code (pipeline/11_aduns.py)
    const ad = await fetch("data/aduns.json");
    if (ad.ok) state.aduns = await ad.json();
  } catch (_) {}
  // Candidate-news matching is quarantined until it requires a distinctive full
  // name/seat match; the current bake contains demonstrable namesake false positives.
  state.prnNews = null;
  try {
    // Source-linked politician/candidate profile cards from curated scrape jobs.
    const pp = await fetch("data/politician-profiles-johor.json");
    if (pp.ok) state.polProfiles = await pp.json();
  } catch (_) {}
  try {
    // Per-DUN seat context: electorate, last result, by-election notes, competitiveness
    const scj = await fetch("data/seat-context-johor.json");
    if (scj.ok) state.seatContextJohor = await scj.json();
  } catch (_) {}
  try {
    // Caretaker EXCO portfolio map for Johor
    const ex = await fetch("data/exco-johor.json");
    if (ex.ok) state.excoJohor = await ex.json();
  } catch (_) {}
  try {
    // federal MP roster: photo + bio + socials per P.xxx (pipeline/09_politicians.py)
    const pl = await fetch("data/politicians.json");
    if (pl.ok) state.politicians = await pl.json();
  } catch (_) {}
  return state;
}

/** Johor DUN seat context row (electorate, bye-election, competitiveness). */
function johorSeatContext(code) {
  return (state.seatContextJohor && state.seatContextJohor.seats && state.seatContextJohor.seats[code]) || null;
}
/** EXCO member row for a DUN code (caretaker cabinet). */
function johorExcoForSeat(code) {
  const members = state.excoJohor && state.excoJohor.members;
  if (!members || !code) return null;
  const member = members.find((m) => m.seat_code === code);
  return member ? { ...member, caretaker: state.excoJohor.status === "caretaker" } : null;
}

// ---- politician profiles (federal MPs + ADUN portrait records) ----
function politicianFor(seat) {
  if (!seat) return null;
  // parliament: the full MP roster (P.xxx). DUN: the slimmer ADUN portrait records
  // from aduns.json ({name, photo, photo_credit, ballot_name?, wikidata}) — never
  // the parent MP, who is a different person than the ADUN.
  if (state.tier === "parlimen") {
    return (state.politicians && state.politicians.mps && state.politicians.mps[seat.code]) || null;
  }
  return (state.aduns && state.aduns[seat.code]) || null;
}
// loose person-name key (drops bin/binti/a-l/a-p/titles) — to tell whether the
// ballot name differs meaningfully from the common name
function namekeyLoose(s) {
  return String(s || "").toLowerCase()
    .replace(/\b(bin|binti|binte|bt|a\/l|a\/p|al|ap|anak|@|dato|datuk|seri|haji|hj|ir|dr|tan|sri)\b/g, " ")
    .replace(/[^a-z0-9]/g, "");
}
function politicianAge(dob) {
  if (!dob) return null;
  const b = new Date(dob + "T00:00:00Z");
  if (isNaN(b.getTime())) return null;
  const now = new Date();
  let a = now.getUTCFullYear() - b.getUTCFullYear();
  const m = now.getUTCMonth() - b.getUTCMonth();
  if (m < 0 || (m === 0 && now.getUTCDate() < b.getUTCDate())) a--;
  return a >= 18 && a < 110 ? a : null;
}
// deterministic monogram fallback — a hashed background colour + initials, zero
// licensing risk (used for the ~58% of MPs and all DUN reps without a Commons photo)
function monogramColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360} 42% 40%)`;
}
function personInitials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  const first = parts[0][0] || "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}
function personPhotoHTML(name, photo, cls = "") {
  if (photo) {
    return `<img class="pol-photo ${cls}" src="${esc(photo)}" alt="${esc(name)}" loading="lazy" decoding="async" width="72" height="72">`;
  }
  return `<span class="pol-photo pol-monogram ${cls}" style="background:${monogramColor(name || "")}" aria-hidden="true">${esc(personInitials(name))}</span>`;
}
// Hotlinked candidate/person portraits (Sinar Harian, state-gov sites) can 404 or
// block hotlinking — swap any broken .pol-photo <img> for the SAME monogram it would
// have had with no photo, so a broken-image glyph never shows. Capture phase because
// <img> 'error' does not bubble.
document.addEventListener("error", (e) => {
  const img = e.target;
  if (!(img instanceof HTMLImageElement) || !img.classList.contains("pol-photo")) return;
  const name = img.getAttribute("alt") || "";
  const span = document.createElement("span");
  span.className = ["pol-photo", "pol-monogram", ...[...img.classList].filter((c) => c !== "pol-photo")].join(" ");
  span.style.background = monogramColor(name);
  span.setAttribute("aria-hidden", "true");
  span.textContent = personInitials(name);
  img.replaceWith(span);
}, true);
// brand glyphs (inline SVG, currentColor — theme-safe, no external requests)
const SOCIAL_ICONS = {
  fb: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M13.4 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.63c-.3-.04-1.3-.13-2.47-.13-2.45 0-4.13 1.5-4.13 4.24V9.9H7.5V13h2.5v8z"/></svg>',
  ig: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="3.8"/><circle cx="17.1" cy="6.9" r="1" fill="currentColor" stroke="none"/></svg>',
  tw: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M17.5 3h3.1l-6.77 7.73L21.75 21H15.5l-4.9-6.4L5 21H1.9l7.24-8.27L2 3h6.4l4.43 5.86zm-1.1 16.14h1.72L7.7 4.77H5.86z"/></svg>',
  tiktok: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M16.6 3c.32 2.05 1.46 3.4 3.4 3.55v2.72c-1.13.11-2.2-.26-3.4-.98v5.9c0 3.5-2.5 5.86-5.68 5.86-2.9 0-5.22-2.24-5.22-5.2 0-3.2 2.66-5.55 6.03-4.98v2.94c-.4-.13-.9-.2-1.34-.2-1.28 0-2.2.9-2.2 2.2 0 1.4 1.05 2.3 2.35 2.3 1.4 0 2.4-1 2.4-2.83V3z"/></svg>',
  youtube: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M22 8.2a2.6 2.6 0 0 0-1.82-1.84C18.57 6 12 6 12 6s-6.57 0-8.18.36A2.6 2.6 0 0 0 2 8.2 27 27 0 0 0 1.7 12 27 27 0 0 0 2 15.8a2.6 2.6 0 0 0 1.82 1.84C5.43 18 12 18 12 18s6.57 0 8.18-.36A2.6 2.6 0 0 0 22 15.8 27 27 0 0 0 22.3 12 27 27 0 0 0 22 8.2M10 15V9l5.2 3z"/></svg>',
  telegram: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21.9 4.35 18.7 19.5c-.24 1.05-.87 1.3-1.76.8l-4.86-3.58-2.34 2.26c-.26.26-.48.48-.98.48l.35-4.94 9-8.13c.4-.35-.08-.54-.6-.2L6.7 13.06l-4.79-1.5c-1.04-.32-1.06-1.04.22-1.54l18.72-7.22c.87-.32 1.63.2 1.35 1.55z"/></svg>',
  web: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.6 2.6 15.4 0 18M12 3c-2.6 2.6-2.6 15.4 0 18"/></svg>',
};
const SOCIAL_META = {
  fb: ["Facebook", (v) => `https://facebook.com/${v}`],
  ig: ["Instagram", (v) => `https://instagram.com/${v}`],
  tw: ["X", (v) => `https://x.com/${v}`],
  tiktok: ["TikTok", (v) => `https://tiktok.com/@${v}`],
  youtube: ["YouTube", (v) => `https://youtube.com/channel/${v}`],
  telegram: ["Telegram", (v) => `https://t.me/${v}`],
  web: ["Website", (v) => (/^https?:\/\//.test(v) ? v : `https://${v}`)],
};
const SOCIAL_ORDER = ["fb", "ig", "tw", "tiktok", "youtube", "telegram", "web"];
// icon-only social links. opts.compact = tighter (mini cards); opts.source ===
// "community" → dashed styling (+ a note when not compact) so web-searched
// accounts are never passed off as Wikidata-verified.
function socialLinksHTML(socials, source, opts = {}) {
  if (!socials) return "";
  // Reject contaminated display labels (e.g. "Dr Richard Rapu") before they
  // become fabricated facebook.com/<label> links.
  const usable = (v) => typeof v === "string" && v.trim() && !/\s/.test(v);
  let keys = SOCIAL_ORDER.filter((k) => usable(socials[k]));
  // mini cards: cap to one line (opts.max) — the rest show in the profile pop-up
  let extra = 0;
  if (opts.max && keys.length > opts.max) { extra = keys.length - opts.max; keys = keys.slice(0, opts.max); }
  const items = keys.map((k) => {
    const [label, toUrl] = SOCIAL_META[k];
    return `<a class="pol-soc-icon" href="${esc(toUrl(socials[k]))}" target="_blank" rel="noopener" aria-label="${esc(label)}" title="${esc(label)}">${SOCIAL_ICONS[k]}</a>`;
  });
  if (!items.length) return "";
  const more = extra ? `<span class="pol-soc-more" aria-hidden="true">+${extra}</span>` : "";
  const cls = "pol-socials" + (opts.compact ? " pol-socials-compact" : "") + (source === "community" ? " pol-socials-unverified" : "");
  const note = (!opts.compact && source === "community") ? `<p class="pol-socials-note muted">${esc(t("pol_socials_community"))}</p>` : "";
  return `<div class="${cls}">${items.join("")}${more}</div>${note}`;
}

// ---- Politicians directory (browsable roster of all MPs) ----
const POL_VIEW = document.getElementById("politicians-view");
function politicianList() {
  const mps = (state.politicians && state.politicians.mps) || {};
  const pd = state.data.parlimen;
  return Object.entries(mps).map(([code, m]) => {
    const seat = pd && pd.byCode.get(code);
    const current = withCurrentAffiliation(m, currentAffiliationFor({ code }, "parlimen"));
    return { code, name: current.name || m.name,
             party: normPartyLabel(current.party) || current.current_bloc || current.party,
             coalition: normPartyLabel(current.coalition) || current.current_bloc || current.coalition,
             photo: m.photo,
             socials: m.socials, socials_source: m.socials_source,
             vacated: !!m.vacated || !!current.vacant_since,
             seatName: (seat && seat.name) || code, state: (seat && seat.state) || "" };
  }).sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}
// official results names are ALL CAPS for the PRN-2023 states — title-case them for
// display, keeping name particles (bin/binti/a/l/a/p) lowercased
function titleCaseName(s) {
  if (!s || s !== s.toUpperCase()) return s || "";
  return s.toLowerCase().replace(/[^\s/]+/g, (w) =>
    ["bin", "binti", "binte", "bt", "al", "ap", "a/l", "a/p", "anak"].includes(w) ? w : w.charAt(0).toUpperCase() + w.slice(1));
}
// the sitting rep of a DUN seat for the directory — tier-independent (the map may
// be on the parliament layer): the seat's own state-election result, or Johor's
// 2022 incumbent. Photo + pretty name from aduns.json where we matched one.
// Johor PRN strings arrive as "PN-Bersatu" / "PN-Pas"; results-dun uses "BERSATU" /
// "PAS". Upper-case so the Parties tab and party filters don't split one party in two.
function normPartyLabel(s) {
  const t0 = String(s || "").trim();
  return t0 ? t0.toUpperCase() : "";
}
function adunEntryFor(code) {
  const own = state.resultsDun && state.resultsDun[code];
  if (own && own.name) {
    const current = withCurrentAffiliation(own, currentAffiliationFor({ code }, "dun"));
    return {
      name: own.name,
      party: normPartyLabel(current.party) || current.current_bloc || current.party,
      coalition: normPartyLabel(current.coalition) || current.current_bloc || current.coalition,
    };
  }
  const e = state.prn16 && state.prn16.seats && state.prn16.seats[code];
  if (e && e.incumbent_2022) {
    const parts = String(e.incumbent_party_2022 || "").split("-");
    const current = withCurrentAffiliation({
      name: e.incumbent_2022,
      coalition: normPartyLabel(parts[0] || ""),
      party: normPartyLabel(parts[1] || parts[0] || ""),
    }, currentAffiliationFor({ code }, "dun"));
    return {
      name: current.name,
      party: normPartyLabel(current.party) || current.current_bloc || current.party,
      coalition: normPartyLabel(current.coalition) || current.current_bloc || current.coalition,
    };
  }
  return null;
}
function adunList() {
  const dd = state.data.dun;
  if (!dd) return [];
  const out = [];
  for (const seat of dd.seats) {
    const r = adunEntryFor(seat.code);
    if (!r) continue;
    const ad = state.aduns && state.aduns[seat.code];
    out.push({
      code: seat.code, dunCode: seat.dun_code,
      name: (ad && ad.name) || titleCaseName(r.name),
      party: r.party, coalition: r.coalition,
      photo: ad && ad.photo,
      seatName: seat.name, state: seat.state,
      former: !!assemblyDissolutionFor(seat.state),
    });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}
// Dual mandates: people holding BOTH a parliament and a state seat (Lim Guan Eng,
// Amirudin, Shafie Apdal…). Matched by loose name key + SAME STATE (kills namesakes
// like Abdul Hadi Awang Kechil vs Hadi Awang) + 1:1 uniqueness. Curated override
// for the rare cross-state dual mandate.
const DUAL_CROSS_STATE = { "6_N.04": "P.024" };   // Tuan Ibrahim Tuan Man: Kelantan MP + Pahang ADUN
let dualMapCache = null;
// True when two display names are the same person (ballot vs common form), not just
// a shared token. Bare includes() paired "Isnaraissah Munirah Majilis" with a
// different ADUN "Munirah Majilis" — too loose.
function namesLikelySamePerson(a, b) {
  const ak = namekeyLoose(a), bk = namekeyLoose(b);
  if (!ak || !bk || ak.length < 8 || bk.length < 8) return false;
  if (ak === bk) return true;
  // drop leading Mohd/Muhammad so "Yusof Apdal" ≡ "Mohammad Yusof bin Apdal"
  const core = (k) => k.replace(/^(mohd|muhammad|mohammad|muhamad|md)+/, "");
  const ca = core(ak), cb = core(bk);
  if (ca && cb && ca.length >= 8 && ca === cb) return true;
  // shorter is a trailing chunk of the longer ("Madius Tangau" ⊂ "Wilfred Madius Tangau")
  // and covers most of it — blocks short-token traps like Munirah ⊂ Isnaraissah Munirah
  const [lo, hi] = ak.length <= bk.length ? [ak, bk] : [bk, ak];
  if (hi.endsWith(lo) && lo.length / hi.length >= 0.6) return true;
  return false;
}
function dualSeatMap() {
  if (dualMapCache) return dualMapCache;
  const mps = politicianList();
  const aduns = adunList();
  if (!mps.length || !aduns.length) return { mpToDun: new Map(), matchedDun: new Set() };
  const mpToDun = new Map(), matchedDun = new Set(), mpHit = new Map();
  const keyed = mps.map((m) => ({ m, k: namekeyLoose(m.name) }));
  for (const a of aduns) {
    if (DUAL_CROSS_STATE[a.code]) {
      mpToDun.set(DUAL_CROSS_STATE[a.code], a);
      matchedDun.add(a.code);
      continue;
    }
    const ak = namekeyLoose(a.name);
    if (ak.length < 8) continue;
    const hits = keyed.filter(({ m, k }) => m.state === a.state && k.length >= 8 &&
      namesLikelySamePerson(m.name, a.name));
    if (hits.length !== 1) continue;
    const mp = hits[0].m;
    mpHit.set(mp.code, (mpHit.get(mp.code) || 0) + 1);
    mpToDun.set(mp.code, a);
    matchedDun.add(a.code);
  }
  // an MP matched by more than one ADUN is ambiguous — drop those pairings
  for (const [code, n] of mpHit) {
    if (n > 1) {
      const a = mpToDun.get(code);
      mpToDun.delete(code);
      if (a) matchedDun.delete(a.code);
    }
  }
  dualMapCache = { mpToDun, matchedDun };
  return dualMapCache;
}
// which roster tab the directory is showing: all (deduped) / parlimen / dun.
// Dual-mandate holders appear ONCE in "All" (one card, both seats) but keep a
// card in EACH role tab.
let polTier = "all";
// set when the user drills into a party card from the Parties tab — exact party
// match (NOT a free-text search, which false-positived on seat names like "Pasir *")
let polPartyFilter = "";
function polList() {
  if (polTier === "dun") return adunList();
  if (polTier === "parlimen") return politicianList();
  const { mpToDun, matchedDun } = dualSeatMap();
  const merged = politicianList().map((p) => {
    const dun = mpToDun.get(p.code);
    return dun ? { ...p, alsoDun: dun } : p;
  });
  return merged.concat(adunList().filter((a) => !matchedDun.has(a.code)))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}
function partyDisplayName(p) {
  // always upper-case so "Bersatu" (Johor PRN) and "BERSATU" (results-dun) merge
  return normPartyLabel((p && (p.party || p.coalition)) || "") || "UNKNOWN";
}
function politicianPartyKey(p) {
  return normPartyLabel((p && (p.party || p.coalition)) || "");
}
function topPartyCoalition(counts, fallback) {
  const xs = [...counts.entries()].filter(([k]) => k);
  if (!xs.length) return fallback || "";
  xs.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return xs[0][0];
}
function partyStatsList() {
  const byParty = new Map();
  const add = (p, tier) => {
    // A vacancy is a seat, not a politician; keep it in the directory but never
    // count it as an MP/ADUN in party totals.
    if (p.vacated) return;
    const party = partyDisplayName(p);
    const rec = byParty.get(party) || {
      party,
      coalitionCounts: new Map(),
      parliament: 0,
      dun: 0,
      states: new Map(),
      reps: [],
    };
    if (tier === "parlimen") rec.parliament += 1;
    else rec.dun += 1;
    if (p.coalition) rec.coalitionCounts.set(p.coalition, (rec.coalitionCounts.get(p.coalition) || 0) + 1);
    if (p.state) rec.states.set(p.state, (rec.states.get(p.state) || 0) + 1);
    rec.reps.push({
      name: p.name,
      state: p.state || "",
      seat: p.dunCode ? `${p.dunCode} · ${p.seatName}` : `${p.code} · ${p.seatName}`,
      tier,
    });
    byParty.set(party, rec);
  };
  politicianList().forEach((p) => add(p, "parlimen"));
  adunList().forEach((p) => add(p, "dun"));
  return [...byParty.values()].map((p) => {
    const coalition = topPartyCoalition(p.coalitionCounts, p.party);
    const topStates = [...p.states.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 3);
    return {
      ...p,
      coalition,
      total: p.parliament + p.dun,
      topStates,
      samples: p.reps.slice().sort((a, b) => {
        if (a.tier !== b.tier) return a.tier === "parlimen" ? -1 : 1;
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
      }).slice(0, 3),
    };
  }).sort((a, b) => b.total - a.total || a.party.localeCompare(b.party));
}
function renderPoliticianGrid() {
  const grid = document.getElementById("pol-grid");
  const countEl = document.getElementById("pol-count");
  if (!grid) return;
  const q = norm((document.getElementById("pol-search") || {}).value || "");
  const stateF = (document.getElementById("pol-state") || {}).value || "";
  const coalF = (document.getElementById("pol-coal") || {}).value || "";
  const partyF = normPartyLabel(polPartyFilter);
  const items = polList().filter((p) =>
    (!stateF || p.state === stateF) &&
    (!coalF || p.coalition === coalF) &&
    (!partyF || politicianPartyKey(p) === partyF) &&
    (!q || norm(p.name).includes(q) || norm(p.seatName).includes(q) || norm(p.code).includes(q) ||
      norm(p.party).includes(q) || norm(p.coalition).includes(q) ||
      (p.alsoDun && (norm(p.alsoDun.seatName).includes(q) || norm(p.alsoDun.dunCode).includes(q)))));
  if (countEl) {
    const base = t("pol_count", { n: items.length });
    countEl.textContent = partyF ? `${base} · ${partyF}` : base;
  }
  grid.className = "pol-grid";
  grid.innerHTML = items.length
    ? items.map((p) => {
        const seatLine = p.alsoDun
          ? `${p.code} · ${p.seatName}  ﹢  ${p.alsoDun.dunCode} · ${p.alsoDun.seatName}`
          : `${p.dunCode || p.code} · ${p.seatName}`;
        const partyBadge = normPartyLabel(p.party || p.coalition) || p.party || p.coalition || "";
        return `
        <div class="pol-card" tabindex="0" role="button" data-pol-code="${esc(p.code)}" aria-label="${esc(p.name)}, ${esc(seatLine)}${p.vacated ? `, ${esc(t("pol_seat_vacant"))}` : ""}">
          <div class="pol-card-photo">
            ${personPhotoHTML(p.name, p.photo)}
            <span class="pol-card-badge pill" style="${pillStyle(partyColor(p.coalition || p.party))}">${esc(partyBadge)}</span>
          </div>
          <div class="pol-card-name">${esc(p.name)}${p.vacated ? ` <span class="pol-card-vacant">${esc(t("pol_seat_vacant"))}</span>` : ""}</div>
          <div class="pol-card-seat" title="${esc(seatLine)}">${esc(seatLine)}</div>
          ${p.socials ? socialLinksHTML(p.socials, p.socials_source, { compact: true, max: 4 }) : '<div class="pol-card-socials-spacer"></div>'}
        </div>`;
      }).join("")
    : `<p class="pol-dir-empty">${esc(t("pol_no_match"))}</p>`;
}
function renderPartyGrid() {
  const grid = document.getElementById("pol-grid");
  const countEl = document.getElementById("pol-count");
  if (!grid) return;
  const q = norm((document.getElementById("pol-search") || {}).value || "");
  const stateF = (document.getElementById("pol-state") || {}).value || "";
  const coalF = (document.getElementById("pol-coal") || {}).value || "";
  const items = partyStatsList().filter((p) =>
    (!stateF || p.states.has(stateF)) &&
    (!coalF || p.coalition === coalF) &&
    (!q || norm(p.party).includes(q) || norm(p.coalition).includes(q) ||
      p.samples.some((r) => norm(r.name).includes(q) || norm(r.seat).includes(q))));
  if (countEl) countEl.textContent = t("pol_party_count", { n: items.length });
  grid.className = "pol-party-grid";
  grid.innerHTML = items.length
    ? items.map((p) => {
        const stateLine = p.topStates.length
          ? p.topStates.map(([s, n]) => `${s} ${n}`).join(" · ")
          : t("pol_party_state_none");
        const samples = p.samples.map((r) => `<li><b>${esc(r.name)}</b><span>${esc(r.seat)}</span></li>`).join("");
        return `<button type="button" class="pol-party-card" data-pol-party="${esc(p.party)}" aria-label="${esc(t("pol_party_open_aria", { party: p.party }))}">
          <div class="pol-party-top">
            <span class="pol-party-mark" style="${pillStyle(partyColor(p.coalition || p.party))}">${esc(p.party)}</span>
            ${p.coalition && p.coalition !== p.party ? `<span class="pill" style="${pillStyle(partyColor(p.coalition))}">${esc(p.coalition)}</span>` : ""}
          </div>
          <div class="pol-party-stats">
            <span><small>${esc(t("pol_party_total"))}</small><b>${p.total}</b></span>
            <span><small>${esc(t("pol_party_parliament"))}</small><b>${p.parliament}</b></span>
            <span><small>${esc(t("pol_party_state"))}</small><b>${p.dun}</b></span>
          </div>
          <div class="pol-party-meta"><span>${esc(t("pol_party_top_states"))}</span><b>${esc(stateLine)}</b></div>
          <ul class="pol-party-samples">${samples}</ul>
          <span class="pol-party-open">${esc(t("pol_party_open"))}</span>
        </button>`;
      }).join("")
    : `<p class="pol-dir-empty">${esc(t("pol_party_no_match"))}</p>`;
}
function renderPoliticiansBody() {
  if (polTier === "pledges") renderPledgesPane();
  else if (polTier === "parties") renderPartyGrid();
  else renderPoliticianGrid();
}
// Manifesto pledges as a Politicians-directory tab (moved off the sidebar).
function renderPledgesPane() {
  const grid = document.getElementById("pol-grid");
  const countEl = document.getElementById("pol-count");
  if (!grid) return;
  if (countEl) countEl.textContent = t("prn_pledges");
  grid.className = "pol-pledges-pane";
  if (!state.johorPledges) {
    grid.innerHTML = `<p class="pol-dir-empty">${esc(t("pol_pledges_empty"))}</p>`;
    return;
  }
  grid.innerHTML = `<div id="pol-pledges-body" class="pol-pledges-body">${prnPledgeTabsHTML()}</div>`;
}
function norm(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]/g, ""); }
function renderPoliticiansDirectory(keepQuery = "") {
  if (!POL_VIEW || !state.politicians) return;
  const showPledgesTab = !!state.johorPledges;
  if (polTier === "pledges" && !showPledgesTab) polTier = "all";
  const partyMode = polTier === "parties";
  const pledgesMode = polTier === "pledges";
  // Parties / pledges tabs have no party drill-down filter
  if (partyMode || pledgesMode) polPartyFilter = "";
  const list = partyMode || pledgesMode ? (partyMode ? partyStatsList() : []) : polList();
  const states = partyMode
    ? [...new Set(list.flatMap((p) => [...p.states.keys()]))].filter(Boolean).sort()
    : [...new Set(list.map((p) => p.state))].filter(Boolean).sort();
  const coals = [...new Set(list.map((p) => p.coalition).filter(Boolean))]
    .sort((a, b) => {
      const ai = COALITION_ORDER.indexOf(a), bi = COALITION_ORDER.indexOf(b);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
  const partyChip = (!partyMode && !pledgesMode && polPartyFilter)
    ? `<button type="button" id="pol-party-clear" class="pol-party-chip" aria-label="${esc(t("pol_party_clear_aria", { party: polPartyFilter }))}">
         <span>${esc(polPartyFilter)}</span><span aria-hidden="true">×</span>
       </button>`
    : "";
  const pledgesTab = showPledgesTab
    ? `<button type="button" role="tab" data-pol-tier="pledges" aria-selected="${pledgesMode}" class="${pledgesMode ? "on" : ""}">${esc(t("pol_tab_pledges"))}</button>`
    : "";
  const controls = pledgesMode ? "" : `
      <div class="pol-dir-controls">
        <input id="pol-search" class="pol-dir-search" type="search" autocomplete="off" spellcheck="false"
          aria-label="${esc(t(partyMode ? "pol_party_search" : "pol_search"))}" placeholder="${esc(t(partyMode ? "pol_party_search" : "pol_search"))}" value="${esc(keepQuery)}">
        <select id="pol-state" aria-label="${esc(t("pol_all_states"))}">
          <option value="">${esc(t("pol_all_states"))}</option>
          ${states.map((s) => `<option value="${esc(s)}">${esc(s)}</option>`).join("")}
        </select>
        <select id="pol-coal" aria-label="${esc(t("pol_all_coal"))}">
          <option value="">${esc(t("pol_all_coal"))}</option>
          ${coals.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")}
        </select>
        ${partyChip}
      </div>`;
  const srcKey = pledgesMode ? "prn_source" : (partyMode ? "pol_party_sources" : "pol_sources");
  const gridClass = pledgesMode ? "pol-pledges-pane" : (partyMode ? "pol-party-grid" : "pol-grid");
  POL_VIEW.innerHTML = `
    <div class="pol-dir">
      <div class="pol-dir-head">
        <button id="pol-back" class="pol-back" type="button">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
          <span>${esc(t("pol_back"))}</span>
        </button>
        <h1>${esc(t(pledgesMode ? "prn_pledges" : "pol_dir_title"))}</h1>
        <p class="pol-dir-sub">${esc(t(pledgesMode ? "pol_pledges_sub" : "pol_dir_sub"))}</p>
      </div>
      <div class="pol-dir-tabs-wrap">
        <div class="seg chip pol-dir-tabs" role="tablist">
          <button type="button" role="tab" data-pol-tier="all" aria-selected="${polTier === "all"}" class="${polTier === "all" ? "on" : ""}">${esc(t("pol_tab_all"))}</button>
          <button type="button" role="tab" data-pol-tier="parlimen" aria-selected="${polTier === "parlimen"}" class="${polTier === "parlimen" ? "on" : ""}">${esc(t("pol_tab_mp"))}</button>
          <button type="button" role="tab" data-pol-tier="dun" aria-selected="${polTier === "dun"}" class="${polTier === "dun" ? "on" : ""}">${esc(t("pol_tab_adun"))}</button>
          <button type="button" role="tab" data-pol-tier="parties" aria-selected="${polTier === "parties"}" class="${polTier === "parties" ? "on" : ""}">${esc(t("pol_tab_parties"))}</button>
          ${pledgesTab}
        </div>
      </div>
      ${controls}
      <div id="pol-count" class="pol-dir-count"></div>
      <div id="pol-grid" class="${gridClass}"></div>
      <p class="pol-dir-src">${esc(t(srcKey))}</p>
    </div>`;
  renderPoliticiansBody();
  document.getElementById("pol-back")?.addEventListener("click", () => { closePoliticians({ silent: true }); hideInfo(); backToControls(); syncSidebar(); });
  if (!pledgesMode) {
    const s = document.getElementById("pol-search");
    s && s.addEventListener("input", renderPoliticiansBody);
    document.getElementById("pol-state")?.addEventListener("change", renderPoliticiansBody);
    document.getElementById("pol-coal")?.addEventListener("change", renderPoliticiansBody);
    document.getElementById("pol-party-clear")?.addEventListener("click", () => {
      polPartyFilter = "";
      renderPoliticiansDirectory((document.getElementById("pol-search") || {}).value || "");
    });
  } else {
    // coalition tabs inside the manifesto pane
    document.getElementById("pol-grid")?.addEventListener("click", (ev) => {
      const tab = ev.target.closest(".prn-pl-tab");
      if (!tab) return;
      prnPledgeTab = tab.dataset.pledgeTab;
      const host = document.getElementById("pol-pledges-body");
      if (host) host.innerHTML = prnPledgeTabsHTML();
    });
  }
  POL_VIEW.querySelectorAll("[data-pol-tier]").forEach((b) => b.addEventListener("click", async () => {
    if (b.dataset.polTier === polTier) return;
    polTier = b.dataset.polTier;
    polPartyFilter = "";   // tier change drops the party drill-down
    if (polTier !== "parlimen" && polTier !== "pledges" && !state.data.dun) {
      try { await loadTier("dun"); } catch (_) {}
    }
    // rebuild the shell (filter options differ per roster) but keep the query
    renderPoliticiansDirectory((document.getElementById("pol-search") || {}).value || "");
  }));
}
async function openPoliticians() {
  if (!state.politicians) return;
  closeNewsPage({ silent: true });     // the directory and the news page are mutually exclusive
  if (state.prnMode) closePrnMode();   // leave the election dashboard before the directory takes over
  if (!state.data.parlimen) { try { await loadTier("parlimen"); } catch (_) {} }
  if (polTier !== "parlimen" && polTier !== "pledges" && !state.data.dun) {
    try { await loadTier("dun"); } catch (_) {}
  }
  document.body.classList.add("politicians-open");
  renderPoliticiansDirectory();
  syncSidebar();
  if (location.hash !== "#politicians") history.pushState(null, "", "#politicians");
  POL_VIEW.querySelector(".pol-dir")?.scrollTo?.(0, 0);
}
function closePoliticians(options = {}) {
  if (!document.body.classList.contains("politicians-open")) return;
  document.body.classList.remove("politicians-open");
  if (POL_VIEW) POL_VIEW.innerHTML = "";
  syncSidebar();
  if (!options.silent) writeHash();
}
function openSeatFromPolitician(code) {
  closePoliticians({ silent: true });
  const tier = code.startsWith("P.") ? "parlimen" : "dun";   // ADUN cards carry DUN codes
  const go = () => { const d = state.data[tier]; if (d && d.byCode.has(code)) select(code); };
  if (state.tier !== tier) setTier(tier).then(go); else go();
}

// full-profile pop-up for one politician (opened from a directory card — does NOT
// navigate the map; footer buttons offer that path explicitly). Renders the SAME
// bento (#candidate-modal, .cand-grid) the PRN candidate cards use, so a sitting
// rep and a 2026 candidate read identically — and every profile closes with a
// Sources tile (radical transparency: each box says where its facts came from).
const CAND_MODAL = document.getElementById("candidate-modal");
let candidateModalReturnTo = null;

// head-of-government (MB/KM/Premier) match for a person — loose name key against
// the curated state-context entry, so the bento can badge the role with its source
function govRoleFor(name, stateName) {
  const st = state.stateCtx && state.stateCtx.states && state.stateCtx.states[stateName];
  const g = st && st.gov;
  if (!g || !g.name) return null;
  const gk = namekeyLoose(g.name), pk = namekeyLoose(name);
  const aliases = {
    abangabdulrahmanzohariabangopeng: "abangjohariopeng",
  };
  const same = gk === pk || gk.includes(pk) || pk.includes(gk) || aliases[pk] === gk || aliases[gk] === pk;
  if (!gk || !pk || gk.length < 8 || !same) return null;
  const title = g.title === "MB" ? "Menteri Besar" : g.title === "KM" ? "Ketua Menteri" : g.title;
  return { ...g, displayTitle: title };
}
// reverse dual-mandate lookup: the parliament code an ADUN also holds (if any)
function dualMpForDun(code) {
  for (const [mp, a] of dualSeatMap().mpToDun) if (a.code === code) return mp;
  return null;
}
// lazy pool of national political headlines (pipeline/06 output) for the
// name-matched "In the news" tile — fetched on the first profile open, cached
let politicalNewsPromise = null;
function ensurePoliticalNews() {
  if (!politicalNewsPromise) {
    politicalNewsPromise = fetch("data/political-news.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { state.politicalNews = j; })
      .catch(() => {});
  }
  return politicalNewsPromise;
}
// headlines whose title contains the person's full name — full-name containment
// only (precision over recall; the tile carries the namesake disclaimer)
function politicianNewsMatchHTML(names, excludeUrls) {
  const pool = (state.politicalNews && state.politicalNews.national) || [];
  const keys = [...new Set(names.filter((n) => n && n.length >= 8).map((n) => n.toLowerCase()))];
  if (!keys.length || !pool.length) return "";
  const hits = pool.filter((n) => {
    if (!n || !n.t || !n.u || (excludeUrls && excludeUrls.has(n.u))) return false;
    const tl = String(n.t).toLowerCase();
    return keys.some((k) => tl.includes(k));
  }).slice(0, 4);
  if (!hits.length) return "";
  return `<div class="cand-news-list">${hits.map((n) =>
    `<a href="${esc(n.u)}" target="_blank" rel="noopener"><span>${esc(n.t)}</span><small>${esc(n.s || "")}${n.d ? " · " + esc(fmtDayMonth(n.d)) : ""}</small></a>`).join("")}</div>`;
}

// ---- bento bundles: normalise an MP / ADUN record into the tile model ----
function bentoFact(label, value, note) {
  return value != null && value !== "" ? { label, value, note: note || "" } : null;
}
function resultFacts(card) {
  if (!card) return [];
  return [
    bentoFact(t("win_votes"), card.votes != null ? card.votes.toLocaleString() : null,
      card.votePct != null ? `${card.votePct}%` : ""),
    bentoFact(t("pol_majority"), card.majority != null ? card.majority.toLocaleString() : null,
      card.majorityPct != null ? `${card.majorityPct}%` : ""),
    bentoFact(t("turnout"), card.turnout != null ? `${card.turnout}%` : null),
    bentoFact(t("pol_candidates_n"), card.candidates || null),
    card.runnerUp ? bentoFact(t("pol_runner_up"), card.runnerUp.name,
      [card.runnerUp.party, card.runnerUp.votes != null ? card.runnerUp.votes.toLocaleString() : ""].filter(Boolean).join(" · ")) : null,
  ].filter(Boolean);
}
// shared Sources-tile body: link pills + muted provenance notes — ALWAYS rendered
function politicianSourcesHTML(links, notes) {
  const seen = new Set();
  const pills = links.filter((l) => l && l.url && !seen.has(l.url) && seen.add(l.url))
    .map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join("");
  const lines = notes.filter(Boolean).map((n) => `<p class="cand-source-note muted">${esc(n)}</p>`).join("");
  return `${pills ? `<div class="cand-source-links">${pills}</div>` : ""}${lines}`;
}
function mpBentoBundle(code) {
  const m = state.politicians && state.politicians.mps && state.politicians.mps[code];
  if (!m) return null;
  const seat = state.data.parlimen && state.data.parlimen.byCode.get(code);
  const r = (state.results && state.results[code]) || null;
  const current = seat ? currentRepresentationFor(seat, "parlimen") : r;
  const card = r ? formatResultCard(r) : null;
  const dual = dualSeatMap().mpToDun.get(code) || null;
  const bio = m.wikipedia ? (m.wikipedia[lang] || m.wikipedia.en || m.wikipedia.ms) : null;
  const gov = seat ? govRoleFor(current && current.name || m.name, seat.state) : null;
  const vacant = !!m.vacated || !!(current && current.vacant_since);
  const col = prnCoalColor(current && current.current_bloc || m.coalition || m.party);
  // Wikidata often supplies year-only dates as YYYY-01-01. Until precision is
  // preserved in the bake, do not display a falsely precise age.
  const age = null;
  const official = r && namekeyLoose(r.name) !== namekeyLoose(m.name) ? titleCaseName(r.name) : "";
  const currentParty = current && current.party;
  const currentBloc = current && (current.current_bloc || current.coalition);
  const party = currentParty && currentParty !== currentBloc
    ? `${currentBloc} · ${currentParty}`
    : (currentBloc || m.coalition || m.party || "");
  const pills = [
    party ? `<span class="pill" style="${pillStyle(col.bg, col.fg)}">${esc(party)}</span>` : "",
    vacant ? `<span class="cand-vacant-chip">${esc(t("pol_seat_vacant"))}</span>` : "",
    gov ? `<span class="prn-cc-inc">${esc(gov.displayTitle)}${gov.caretaker ? ` · ${esc(t("ctx_caretaker"))}` : ""}</span>` : "",
  ].filter(Boolean).join("");
  const seatLabel = seat ? `${seat.name} (${code})` : code;
  const roleLines = [];
  if (vacant) {
    const note = (lang === "ms" ? m.vacancy_note_ms : m.vacancy_note_en) || m.vacancy_note_en || "";
    if (note) roleLines.push(note);
  }
  roleLines.push(t(vacant ? "pol_former_mandate_mp" : "pol_mandate_mp", { s: seatLabel }));
  if (gov) roleLines.push(`${gov.displayTitle}, ${seat.state}${gov.caretaker ? ` (${t("ctx_caretaker")})` : ""}`);
  if (dual) roleLines.push(t("pol_also_adun", { c: dual.dunCode, s: dual.seatName }));
  const links = [
    m.wikipedia && m.wikipedia.en ? { label: "Wikipedia (EN)", url: m.wikipedia.en.url } : null,
    m.wikipedia && m.wikipedia.ms ? { label: "Wikipedia (BM)", url: m.wikipedia.ms.url } : null,
    m.wikidata ? { label: "Wikidata", url: m.wikidata } : null,
    vacant && m.vacancy_source ? { label: m.vacancy_source.label, url: m.vacancy_source.url } : null,
  ];
  const notes = [
    r ? resultSourceText(r, false) : "",
    t("pol_src_roster"),
    gov && state.stateCtx && state.stateCtx.checked ? t("pol_src_govrole", { d: state.stateCtx.checked }) : "",
    m.photo_credit ? t("pol_photo_by", { credit: m.photo_credit }) : "",
  ];
  return {
    code,
    kicker: `${esc(t("kicker_parlimen"))} · ${esc(code)}`,
    name: (current && current.name) || m.name, ballot: official, col, pills,
    meta: [seat ? `${esc(seat.name)} · ${esc(seat.state)}` : esc(code), age ? esc(t("pol_age", { n: age })) : ""].filter(Boolean).join(" · "),
    photo: m.photo,
    socialsHTML: socialLinksHTML(m.socials, m.socials_source),
    roleLines,
    facts: resultFacts(card),
    resultNote: r ? resultSourceText(r, false) : "",
    bgHTML: bio ? `<p>${esc(bio.extract)}</p><a class="yb-bio-more" href="${esc(bio.url)}" target="_blank" rel="noopener">Wikipedia →</a>` : "",
    profile: null,
    education: m.education || "",
    contactHTML: "",
    prnNewsHTML: "",
    newsNames: [m.name, r && r.name ? titleCaseName(r.name) : ""].filter(Boolean),
    sourcesHTML: politicianSourcesHTML(links, notes),
    seatBtns: [
      { code, label: t("pol_view_seat") },
      dual ? { code: dual.code, label: t("pol_view_dun_seat", { c: dual.dunCode }) } : null,
    ].filter(Boolean),
  };
}
function adunBentoBundle(code) {
  const seat = state.data.dun && state.data.dun.byCode.get(code);
  const entry = adunEntryFor(code);
  if (!seat || !entry) return null;
  const ad = state.aduns && state.aduns[code];
  const name = (ad && ad.name) || titleCaseName(entry.name);
  const official = namekeyLoose(name) !== namekeyLoose(entry.name) ? titleCaseName(entry.name) : "";
  const own = state.resultsDun && state.resultsDun[code];
  const card = own ? formatResultCard(own) : null;
  const jctx = !own ? johorSeatContext(code) : null;   // Johor: 2022 numbers + electorate
  const profile = profileForCandidate(code, name) || profileForCandidate(code, titleCaseName(entry.name));
  const gov = govRoleFor(name, seat.state);
  const exco = gov ? null : johorExcoForSeat(code);   // the MB's EXCO row is his MB-ness — one badge, not two
  const mpCode = dualMpForDun(code);
  const mpSeat = mpCode && state.data.parlimen && state.data.parlimen.byCode.get(mpCode);
  const col = prnCoalColor(entry.coalition || entry.party);
  const govPhoto = gov && !(ad && ad.photo) && !(profile && profile.photo_url)
    ? (state.govPhotos && state.govPhotos[seat.state]) : null;
  const party = entry.party && entry.party !== entry.coalition ? `${entry.coalition} · ${entry.party}` : (entry.coalition || entry.party || "");
  const pills = [
    party ? `<span class="pill" style="${pillStyle(col.bg, col.fg)}">${esc(party)}</span>` : "",
    gov ? `<span class="prn-cc-inc">${esc(gov.displayTitle)}${gov.caretaker ? ` · ${esc(t("ctx_caretaker"))}` : ""}</span>` : "",
    exco ? `<span class="prn-cc-inc">${esc(exco.role || "EXCO")}${exco.caretaker ? ` · ${esc(t("ctx_caretaker"))}` : ""}</span>` : "",
  ].filter(Boolean).join("");
  const roleLines = [];
  const dissolved = assemblyDissolutionFor(seat.state);
  if (profile && profile.current_role && !dissolved) roleLines.push(profile.current_role);
  roleLines.push(t(dissolved ? "pol_former_mandate_adun" : "pol_mandate_adun", { s: `${seat.name} (${seat.dun_code})` }));
  if (gov && !(profile && profile.current_role)) roleLines.push(`${gov.displayTitle}, ${seat.state}${gov.caretaker ? ` (${t("ctx_caretaker")})` : ""}`);
  if (exco && exco.portfolio) roleLines.push(exco.portfolio);
  if (mpSeat) roleLines.push(t("pol_also_mp", { c: mpCode, s: mpSeat.name }));
  let facts = resultFacts(card);
  let resultNote = own ? resultSourceText(own, true) : "";
  if (!facts.length && jctx) {
    const runner = Array.isArray(jctx.last_field) && jctx.last_field[1];
    facts = [
      bentoFact(t("win_votes"), jctx.incumbent_votes_2022 != null ? jctx.incumbent_votes_2022.toLocaleString() : null,
        jctx.incumbent_pct_2022 != null ? `${jctx.incumbent_pct_2022}%` : ""),
      bentoFact(t("pol_majority"), jctx.majority_2022 || null),
      bentoFact(t("prn_electorate"), jctx.electorate != null ? jctx.electorate.toLocaleString() : null),
      runner ? bentoFact(t("pol_runner_up"), runner.name,
        [runner.party, runner.votes != null ? runner.votes.toLocaleString() : ""].filter(Boolean).join(" · ")) : null,
    ].filter(Boolean);
    resultNote = t("src_johor2022");
  }
  const summary = profile && (profile.summary || profile.biography_summary);
  const profSocials = profile && Array.isArray(profile.social_links) && profile.social_links.length
    ? `<div class="cand-socials">${profile.social_links.map((u) => {
        const host = (() => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (_) { return "link"; } })();
        return `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(host)}</a>`;
      }).join(" ")}</div>`
    : "";
  const contact = profile && profile.official_contact;
  const contactBits = contact ? [contact.phone, contact.email, contact.address].filter(Boolean) : [];
  const profileSources = profileSourcesFor(profile);
  const links = [
    ad && ad.wikidata ? { label: "Wikidata", url: `https://www.wikidata.org/wiki/${ad.wikidata}` } : null,
    ...profileSources.map((s) => ({ label: s.label, url: s.url })),
  ];
  const photoCredit = (ad && ad.photo_credit) || (profile && profile.photo_credit) || (govPhoto && govPhoto.credit) || "";
  const notes = [
    resultNote,
    t("pol_src_roster"),
    gov && state.stateCtx && state.stateCtx.checked ? t("pol_src_govrole", { d: state.stateCtx.checked }) : "",
    photoCredit ? t("pol_photo_by", { credit: photoCredit }) : "",
  ];
  return {
    code,
    kicker: `${esc(t("kicker_dun"))} · ${esc(seat.dun_code)}`,
    name, ballot: official, col, pills,
    meta: `${esc(seat.name)} · ${esc(seat.state)}`,
    photo: (ad && ad.photo) || (profile && profile.photo_url) || (govPhoto && govPhoto.photo) || null,
    socialsHTML: profSocials,
    roleLines,
    facts,
    resultNote,
    bgHTML: summary ? `<p>${esc(summary)}</p>` : "",
    profile,
    education: "",
    contactHTML: contactBits.length ? `<ul class="cand-list">${contactBits.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "",
    prnNewsHTML: candidateModalNewsHTML(code, name) || candidateModalNewsHTML(code, titleCaseName(entry.name)),
    newsNames: [name, titleCaseName(entry.name)].filter(Boolean),
    sourcesHTML: politicianSourcesHTML(links, notes),
    seatBtns: [
      { code, label: t("pol_view_seat") },
      mpSeat ? { code: mpCode, label: t("pol_view_mp_seat", { c: mpCode }) } : null,
    ].filter(Boolean),
  };
}
// one template for both tiers — the tile classes are the candidate bento's, so
// the politician profile inherits its layout and theming byte-for-byte
function politicianBentoHTML(b) {
  const factHTML = (f) => `<div class="cand-fact"><span>${esc(f.label)}</span><b>${esc(f.value)}</b>${f.note ? `<small>${esc(f.note)}</small>` : ""}</div>`;
  const facts = b.facts.map(factHTML).join("");
  // dedupe near-identical role lines (a curated current_role often restates the
  // gov/EXCO title, e.g. "Menteri Besar Johor" vs "Menteri Besar Johor (caretaker)")
  const seenRoles = [];
  const roleLines = b.roleLines.filter((l) => {
    const k = namekeyLoose(l);
    if (seenRoles.some((s) => s === k || s.includes(k) || k.includes(s))) return false;
    seenRoles.push(k);
    return true;
  });
  const roleBody = roleLines.length
    ? roleLines.map((l) => `<p class="cand-role-text">${esc(l)}</p>`).join("")
    : "";
  const partyHistory = candidateModalListHTML(b.profile && b.profile.party_history, false);
  const track = candidateModalListHTML(b.profile && b.profile.track_record, true)
    || candidateModalListHTML(b.profile && b.profile.career_highlights, false);
  const electionHistory = candidateModalListHTML(b.profile && b.profile.election_history, false);
  const education = candidateModalListHTML(b.profile && b.profile.education, false)
    || (b.education ? `<p class="cand-role-text">${esc(b.education)}</p>` : "");
  return `<div class="cand-modal-shell" style="--cc:${b.col.bg};--ccfg:${b.col.fg}">
    <button class="pol-modal-close cand-modal-close" type="button" data-i18n-title="card_preview_close" title="${esc(t("card_preview_close"))}" aria-label="${esc(t("card_preview_close"))}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><line x1="6" x2="18" y1="6" y2="18"/><line x1="6" x2="18" y1="18" y2="6"/></svg>
    </button>
    <div class="cand-grid">
      <section class="cand-hero cand-tile">
        <div class="cand-photo-wrap">${personPhotoHTML(b.name, b.photo, "cand-modal-photo")}</div>
        <div class="cand-hero-id">
          <div class="cand-kicker">${b.kicker}</div>
          <h2>${esc(b.name)}</h2>
          ${b.ballot ? `<span class="yb-ballot muted">${esc(b.ballot)}</span>` : ""}
          <p class="cand-seat muted">${b.meta}</p>
          <div class="cand-pill-row">${b.pills}</div>
          ${b.socialsHTML || ""}
        </div>
      </section>
      ${roleBody ? candidateModalTileHTML("cand-role", t("candidate_bento_current_role"), roleBody) : ""}
      ${facts ? candidateModalTileHTML("cand-facts", t("pol_bento_last_result"),
        `<div class="cand-facts-grid">${facts}</div>${b.resultNote ? `<p class="cand-source-note muted">${esc(b.resultNote)}</p>` : ""}`) : ""}
      ${b.bgHTML ? candidateModalTileHTML("cand-summary", t("profile_background"), b.bgHTML) : ""}
      ${partyHistory ? candidateModalTileHTML("cand-party", t("profile_party_history"), partyHistory) : ""}
      ${track ? candidateModalTileHTML("cand-track", t("profile_track_record"), track) : ""}
      ${electionHistory ? candidateModalTileHTML("cand-election", t("profile_election_history"), electionHistory) : ""}
      ${education ? candidateModalTileHTML("cand-education", t("profile_education"), education) : ""}
      ${b.contactHTML ? candidateModalTileHTML("cand-contact", "Contact", b.contactHTML) : ""}
      <section class="cand-tile cand-news" data-pol-news-slot hidden></section>
      ${candidateModalTileHTML("cand-sources", t("profile_sources"), b.sourcesHTML)}
    </div>
    ${b.seatBtns.length ? `<div class="cand-actions">${b.seatBtns.map((s) => `<button class="pol-modal-seatbtn cand-seatbtn" type="button" data-candidate-seat="${esc(s.code)}">${esc(s.label)}</button>`).join("")}</div>` : ""}
  </div>`;
}
function openPoliticianModal(code, returnTo = null) {
  if (!CAND_MODAL) return;
  const b = code.includes("_N.") ? adunBentoBundle(code) : mpBentoBundle(code);   // ADUN cards carry DUN seat codes
  if (!b) return;
  candidateModalReturnTo = returnTo;
  CAND_MODAL.setAttribute("aria-label", t("pol_bento_aria"));
  CAND_MODAL.dataset.polBento = code;
  CAND_MODAL.innerHTML = politicianBentoHTML(b);
  if (typeof CAND_MODAL.showModal === "function") CAND_MODAL.showModal();
  else CAND_MODAL.setAttribute("open", "");
  CAND_MODAL.querySelector(".pol-modal-close")?.focus();
  // the news tile fills once the headline pool is in — sync PRN items + name matches
  ensurePoliticalNews().then(() => {
    if (CAND_MODAL.dataset.polBento !== code) return;   // a different profile took over
    const slot = CAND_MODAL.querySelector("[data-pol-news-slot]");
    if (!slot) return;
    const exclude = new Set([...(b.prnNewsHTML || "").matchAll(/href="([^"]+)"/g)].map((m2) => m2[1]));
    const matched = politicianNewsMatchHTML(b.newsNames, exclude);
    const body = `${b.prnNewsHTML || ""}${matched}`;
    if (!body) return;
    slot.innerHTML = `<div class="cand-kicker">${esc(t("prn_news"))}</div>${body}<p class="cand-source-note muted">${esc(t("prn_news_note"))}</p>`;
    slot.hidden = false;
  });
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
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 80, easing: "linear" });
    return;
  }
  el.animate(
    [{ opacity: 0, transform: `translateY(${Math.min(dist, 6)}px)` }, { opacity: 1, transform: "none" }],
    { duration: 160, easing: "cubic-bezier(0,0,0.2,1)" }
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
  if (view === "overview") {
    // structural guard: minimizeCard holds the empty card at opacity 0 with a
    // fill:forwards animation — ANY route back to the overview must release it,
    // or the search bar comes back invisible (belt-and-braces for paths that
    // don't go through backToControls, and for animations paused mid-flight in
    // a backgrounded tab).
    PANEL_EMPTY.getAnimations().forEach((a) => a.cancel());
  }
  PANEL_STATE.hidden = view === "overview";
  PANEL_SEAT.hidden = true;
  if (STATE_ACTIONS) STATE_ACTIONS.hidden = view !== "seat";
  requestAnimationFrame(syncMapToCard);
}

// Snappy interaction clock — short enough to feel instant, long enough to read as motion.
// (prefers-reduced-motion still snaps to final frames.)
const DETAIL_POP_MS = 240;
const DETAIL_POP_EASE = "cubic-bezier(0,0,0.2,1)";
const STATE_ISOLATE_MS = 280;
const STATE_EXIT_MS = 220;
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
const STATE_EXIT_EASE_FN = cubicBezierEase(0.4, 0, 0.2, 1);

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
// Most views FLIP both the card and map element. When preserveMapView is set, the card
// can resize but the current map camera is rewritten so the isolated state keeps the
// same screen size/position instead of expanding to fit the new card layout.
function animateCardResize(card, mutate, options = {}) {
  const preserveMapView = !!options.preserveMapView;
  const firstMap = preserveMapView ? SVG.getBoundingClientRect() : null;
  if (ANIM_OFF) {
    mutate();
    syncMapToCard();
    if (preserveMapView) setViewBoxPreservingScreen(firstMap, SVG.getBoundingClientRect());
    return;
  }
  if (!card || !card.animate || REDUCE_MOTION.matches) {
    mutate();
    syncMapToCard();
    if (preserveMapView) setViewBoxPreservingScreen(firstMap, SVG.getBoundingClientRect());
    return;
  }
  const firstCard = card.getBoundingClientRect();
  const firstMapForFlip = firstMap || SVG.getBoundingClientRect();
  mutate();
  syncMapToCard();
  const lastCard = card.getBoundingClientRect();
  const lastMap = SVG.getBoundingClientRect();
  if (preserveMapView) setViewBoxPreservingScreen(firstMap, lastMap);
  animateRectFlip(card, firstCard, lastCard, 380);
  if (!preserveMapView) animateRectFlip(SVG, firstMapForFlip, lastMap, 420);
}

// onLayout (optional) fires once the swapped-in layout is real, with the map's pre/post
// layout rects, so callers can launch a concurrent viewBox move and the map shrinks /
// reframes IN STEP with the card's rise instead of jumping after it. Return true from
// onLayout to own the map's motion entirely (skips the element FLIP — a viewBox-only
// camera move has no scaleY distortion).
async function swapCardWithMinimizePop(card, mutate, onLayout) {
  if (ANIM_OFF || !card || !card.animate || REDUCE_MOTION.matches) {
    const firstMap = onLayout ? SVG.getBoundingClientRect() : null;
    mutate();
    syncMapToCard();
    if (onLayout) onLayout(firstMap, SVG.getBoundingClientRect());
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
function riseCard(el, delay = 0) {
  if (ANIM_OFF) return;
  if (!el || !el.animate) return;
  if (REDUCE_MOTION.matches) {
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 90, delay, fill: "backwards" });
    return;
  }
  el.animate([
    { offset: 0,    transform: "scaleY(0.08)", opacity: 0.4, easing: "cubic-bezier(0.2, 1.15, 0.4, 1)" },
    { offset: 0.55, opacity: 1 },
    { offset: 1,    transform: "scaleY(1)",    opacity: 1 },
  ], { duration: 280, delay, fill: "backwards" });
}

// MINIMIZE the overview card down to a bar (we watch it collapse) before the state
// backdrop springs up from that same point. Compositor-only (scaleY + opacity).
function minimizeCard(el) {
  if (ANIM_OFF) return;
  if (!el || !el.animate) return;
  if (REDUCE_MOTION.matches) { el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 70, fill: "forwards" }); return; }
  el.animate([
    { transform: "scaleY(1)",    opacity: 1, offset: 0 },
    { transform: "scaleY(0.35)", opacity: 0.85, offset: 0.5 },
    { transform: "scaleY(0.05)", opacity: 0, offset: 1 },
  ], { duration: 140, easing: "cubic-bezier(0.4, 0, 0.8, 0.1)", fill: "forwards" });
}

// ---- rendering ----
let hoverState = null;   // name of the state currently lit up under the cursor (mouse only)
async function render(tier) {
  const data = await loadTier(tier);
  SVG.setAttribute("viewBox", data.viewBox);
  viewBox = data.viewBox.split(" ").map(Number);
  SEATS.innerHTML = "";
  if (STATE_OUTLINES) STATE_OUTLINES.replaceChildren();
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
      p.dataset.state = seat.state;
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
  if (STATE_OUTLINES) {
    const byState = new Map();
    for (const seat of data.seats) {
      const name = seat.state || "";
      if (!name) continue;
      if (!byState.has(name)) byState.set(name, []);
      byState.get(name).push(seat);
    }
    const outlines = document.createDocumentFragment();
    for (const seats of byState.values()) {
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      group.setAttribute("class", "state-outline");
      for (const seat of seats) {
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", seat.d);
        group.appendChild(path);
      }
      outlines.appendChild(group);
    }
    STATE_OUTLINES.appendChild(outlines);
  }
  SEATS.appendChild(frag);
  paint();
  LOADING.hidden = true;
  syncMapToCard();
  requestAnimationFrame(syncMapToCard);
  // soft fade in — EXCEPT when a caller is about to isolate a state right after
  // (the Johor pill switching tier): fading the whole recoloured national map in
  // first reads as "reloading the map", so skip it and just recolour in place.
  if (skipMapFade) { skipMapFade = false; SEATS.style.opacity = ""; }
  else animateIn(SEATS, 0);   // opacity-only on the group
}
let skipMapFade = false;

// A DUN seat's OWN state-election (PRN) result, when we have one (the states in
// results-dun.json). Undefined for parlimen tier or an uncovered DUN seat.
// Johor has no PRN result in results-dun.json (only the 2023 six-state PRN is there),
// so without this a Johor DUN seat falls back to its PARENT-Parliament MP — making
// every pair of sibling DUN seats show the same person. Use the per-seat 2022 state
// assemblyman from the PRN dataset instead. (Assembly dissolved for PRN 11 Jul 2026.)
// tier-independent core: build the synthetic 2022-incumbent result for a Johor DUN
// seat code (assembly dissolved for the PRN — prn16 holds the sitting rep)
function johorDunResultRaw(code) {
  if (!state.prn16 || !state.prn16.seats) return undefined;
  const e = state.prn16.seats[code];
  if (!e || !e.incumbent_2022) return undefined;
  const parts = String(e.incumbent_party_2022 || "").split("-");
  const coalition = (parts[0] || "").trim();
  const party = (parts[1] || parts[0] || "").trim();
  const maj = e.majority_2022 ? Number(String(e.majority_2022).replace(/[^0-9]/g, "")) : NaN;
  return {
    name: e.incumbent_2022,
    coalition: coalition || party,
    party: party || coalition,
    majority: Number.isFinite(maj) && maj > 0 ? maj : undefined,
    _johor2022: true,
  };
}
function johorDunResult(seat) {
  if (state.tier !== "dun") return undefined;
  return johorDunResultRaw(seat.code);
}
function ownDunResult(seat) {
  if (state.tier === "parlimen") return undefined;
  const own = state.resultsDun && state.resultsDun[seat.code];
  return own || johorDunResult(seat);
}
// the tier a seat CODE belongs to — parliament codes are P.xxx, DUN codes {sc}_N.xx
function seatTierOf(code) {
  return typeof code === "string" && code.startsWith("P.") ? "parlimen" : "dun";
}
// tier-EXPLICIT result lookup (the bento spotlight can show a seat from either
// layer regardless of which one the map is on)
function seatResultOf(seat, tier) {
  if (tier === "parlimen") return state.results && state.results[seat.code];
  const own = state.resultsDun && state.resultsDun[seat.code];
  return own || johorDunResultRaw(seat.code);
}
// tier-EXPLICIT politician/ADUN record lookup (politicianFor reads state.tier)
function politicianOf(seat, tier) {
  if (tier === "parlimen") {
    return (state.politicians && state.politicians.mps && state.politicians.mps[seat.code]) || null;
  }
  return (state.aduns && state.aduns[seat.code]) || null;
}
function currentAffiliationFor(seat, tier = state.tier) {
  if (!seat || !state.currentAffiliations) return null;
  const rows = state.currentAffiliations[tier];
  return rows && rows[seat.code] ? rows[seat.code] : null;
}
function currentRepresentationFor(seat, tier = state.tier) {
  const result = seatResultOf(seat, tier);
  const override = currentAffiliationFor(seat, tier);
  return result || override ? withCurrentAffiliation(result, override) : null;
}
function assemblyDissolutionFor(stateName) {
  const assemblies = state.currentAffiliations && state.currentAffiliations.dissolved_assemblies;
  return assemblies && assemblies[stateName] ? assemblies[stateName] : null;
}
// Parliament's member roster sometimes files MPs under a generic heading
// ("PEMBANGKANG" = opposition, no formal bloc) with null party/coalition. That is
// not a colourable alliance — using it for the choropleth turns seats like
// Jeli / Gua Musang neutral grey even though they still sit under PN from GE15.
// Skip those labels and fall through to the election coalition/party.
const GENERIC_AFFILIATION_BLOCS = new Set([
  "PEMBANGKANG", "OPPOSITION", "KERAJAAN", "GOVERNMENT",
  "INDEPENDENT", "TIDAK BERAFILIASI", "UNAFFILIATED",
]);
function currentBlocFor(result) {
  if (!result) return "";
  for (const raw of [result.current_bloc, result.coalition, result.party,
                     result.election_coalition, result.election_party]) {
    const s = String(raw || "").trim();
    if (!s) continue;
    if (GENERIC_AFFILIATION_BLOCS.has(s.toUpperCase())) continue;
    if (s.toUpperCase() === "VACANT") continue;
    return s;
  }
  return "";
}
/** Bloc used for map fill: prefer real current affiliation, else GE15 / PRN election row. */
function mapBlocFor(seat, tier = state.tier) {
  const elect = seatResultOf(seat, tier);
  const r = currentRepresentationFor(seat, tier);
  if (r && r.vacant_since) return "";   // vacant → neutral grey
  return currentBlocFor(r) || (elect && (elect.coalition || elect.party)) || "";
}
// The result to DISPLAY for a seat. Parliament: the seat's own GE15 winner. DUN: the
// seat's OWN state-election result only — a covered PRN state (results-dun.json) or
// Johor's 2022 incumbent (johorDunResult) — and NEVER the parent-Parliament MP.
// Falling back to the parent MP mislabels a federal MP as the state assemblyman, and
// since 2-4 DUN seats share one Parliament seat it shows the SAME person on every
// sibling seat (the "sama YB" bug). Seats with no own DUN result (only Johor's 56
// are outside results-dun — they use prn16 incumbents) degrade to an honest empty
// state instead of a wrong, repeated federal name.
function resultFor(seat) {
  if (state.tier !== "parlimen") return ownDunResult(seat);
  return state.results && state.results[resultKey(seat, state.tier)];
}

// State-level rollups must not multiply parent-Parliament fallback rows across DUN
// seats. Parliament uses GE15 rows; DUN aggregates only use real DUN result rows.
function stateSummaryResultFor(seat) {
  return state.tier === "parlimen" ? resultFor(seat) : ownDunResult(seat);
}

// the seat's current representative (YB / MP) name — the politician's common name
// where we have one, else the election winner. Used so search matches people, not
// just place names, and so a result row can show who holds the seat.
function repNameForSeat(seat) {
  if (!seat) return "";
  const pol = politicianFor(seat);   // parlimen only; common name preferred
  const current = currentAffiliationFor(seat);
  if (current && current.current_name) return current.current_name;
  if (pol && pol.name) return pol.name;
  const r = resultFor(seat);
  return (r && r.name) || "";
}
// search seats by place AND by representative name (so "rafizi" finds Pandan)
function searchSeatsAndReps(seats, q, tier) {
  const base = searchSeats(seats, q, tier);
  const ql = (typeof q === "string" ? q : "").trim().toLowerCase();
  if (!ql) return base;
  const seen = new Set(base.map((s) => s.code));
  const extra = seats.filter((s) => !seen.has(s.code) && repNameForSeat(s).toLowerCase().includes(ql));
  return base.concat(extra);
}

function seatValueColor(seat) {
  const data = state.data[state.tier];
  // live-election view: paint by tonight's leader/winner (grey until a result lands).
  if (state.prnMode && liveElection() && seat.state === liveElection().state && state.tier === liveElection().tier) {
    const lr = (typeof prnLiveForSeat === "function" ? prnLiveForSeat(seat.code) : null)
      || (state.prnLive && state.prnLive.seats && state.prnLive.seats[seat.code]);
    const p = state.paths.get(seat.code);
    if (lr && (lr.coalition || lr.party)) {
      if (p) p.style.fillOpacity = lr.status === "leading" ? "0.55" : "";
      return prnCoalColor(lr.coalition || lr.party).bg;
    }
    if (p) p.style.fillOpacity = "";
    return "#39404c";
  }
  // Party choropleth: GE15 on Parliament, own state-election (resultsDun / Johor
  // prn16) on DUN. Gate on either results table so DUN isn't stuck waiting on GE15.
  // mapBlocFor falls back to the election coalition when the roster only says
  // "PEMBANGKANG" with null party (Jeli / Gua Musang / etc.).
  if (state.mode === "parti" && (state.results || state.resultsDun || state.prn16)) {
    const bloc = mapBlocFor(seat);
    return bloc ? partyColor(bloc) : "#222b36";
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
function animateTo(target, ms = 260, ease = (t) => 1 - Math.pow(1 - t, 3)) {
  cancelAnimationFrame(animId);
  if (ANIM_OFF || REDUCE_MOTION.matches || !(ms > 0)) {   // snap to final frame
    viewBox = target.slice();
    SVG.setAttribute("viewBox", viewBox.map((n) => n.toFixed(2)).join(" "));
    syncStageLabelPosition();
    syncSelectedTexture();
    syncLiveBadge();
    return;
  }
  const start = viewBox.slice();
  // skip animation when already effectively there
  const near = start.every((v, i) => Math.abs(v - target[i]) < 0.15);
  if (near) {
    viewBox = target.slice();
    SVG.setAttribute("viewBox", viewBox.map((n) => n.toFixed(2)).join(" "));
    return;
  }
  const t0 = performance.now();
  let frame = 0;
  function step(now) {
    const k = Math.min(1, (now - t0) / ms);
    const e = ease(k);
    viewBox = start.map((v, i) => v + (target[i] - v) * e);
    SVG.setAttribute("viewBox", viewBox.map((n) => n.toFixed(2)).join(" "));
    // chrome sync is relatively heavy — every other frame mid-flight, always on settle
    if (k >= 1 || (frame++ & 1) === 0) {
      syncStageLabelPosition();
      syncSelectedTexture();
    }
    if (k < 1) animId = requestAnimationFrame(step);
    else {
      syncStageLabelPosition();
      syncSelectedTexture();
      syncLiveBadge();
    }
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
function stateLabelClearanceBottom() {
  const label = document.getElementById("state-label");
  if (!label || !state.openState) return null;
  const labelH = label.getBoundingClientRect().height || 0;
  if (labelH <= 0) return null;
  const topbarBottom = TOPBAR ? TOPBAR.getBoundingClientRect().bottom : 0;
  const labelTop = Math.max(12, Math.round(topbarBottom + 6));
  const gap = MOBILE_MAP_INSPECT_MQ.matches ? 8 : 14;
  return labelTop + labelH + gap;
}
function stateViewBox(name) {
  const b = stateBBox(name);
  const pad = Math.max(b.w, b.h) * 0.06 + 2;
  let w = b.w + pad * 2, h = b.h + pad * 2;
  const ar = stateFrameAspect();
  if (w / h > ar) h = w / ar; else w = h * ar;
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  // The map now has its own reserved band above the card on every viewport, so centre
  // the state in that band, then bias it down only when the persistent title would
  // otherwise overlap northern geometry (Sabah's islands are the common case).
  let anchor = 0.5;
  const mapRect = SVG.getBoundingClientRect();
  const clearanceBottom = stateLabelClearanceBottom();
  if (clearanceBottom != null && mapRect.width > 0 && mapRect.height > 0) {
    const scale = Math.min(mapRect.width / w, mapRect.height / h);
    if (Number.isFinite(scale) && scale > 0) {
      const offsetY = (mapRect.height - h * scale) / 2;
      const stateTop = mapRect.top + offsetY + (b.y - (cy - anchor * h)) * scale;
      if (stateTop < clearanceBottom) {
        anchor += (clearanceBottom - stateTop) / (h * scale);
      }
    }
  }
  return [cx - w / 2, cy - anchor * h, w, h];
}
function zoomToState(name, ms = STATE_ISOLATE_MS, ease = undefined) { animateTo(stateViewBox(name), ms, ease); }

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
// programmatic deselection (tier switches, data reloads) must keep the layer the
// caller just set — only explicit "go home" actions reset to the landing view
function deselect() { backToControls({ keepLayer: true }); }

// "P.140 · Segamat" for a DUN seat — the parliament dataset is already cached in DUN
// tier (the FT underlays load it); degrades to the bare code if it isn't.
function parlimenContext(seat) {
  if (!seat || !seat.parlimen) return "";
  const pd = state.data.parlimen;
  const p = pd && pd.byCode.get(seat.parlimen);
  return p ? `${seat.parlimen} · ${p.name}` : seat.parlimen;
}

// which election a result row came from — src label shared by the seat panel,
// the bento spotlight and the politician-profile Sources tile. resultSourceText
// is the bare string (for contexts that lay it out themselves); resultSourceLine
// wraps it in the classic src-line div. Output unchanged.
function resultSourceText(r, ownDun) {
  return r
    ? (r._johor2022 ? t("src_johor2022")
      : r.election ? t(r._byelection ? "src_byelection" : "src_state_election", { e: r.election })
      : ownDun ? t("src_prn15")
      : t("src_ge15"))
    : "";
}
function resultSourceLine(r, ownDun) {
  const s = resultSourceText(r, ownDun);
  return s ? `<div class="src-line muted">${esc(s)}</div>` : "";
}

// the "Current YB" profile card (photo/bio/socials when we have the politician,
// plain name+party otherwise) — shared by the seat detail panel and the bento
// spotlight. opts.compact (bento): photo + name + party only — no Wikipedia bio /
// socials, so the map tile never grows when a seat is selected. Full bio lives in
// the click-to-open politician modal (data-pol-code).
// The politician record's common name (e.g. "Hannah Yeoh") is more recognisable
// than the ballot name; keep the ballot name as a subtitle when they differ.
function ybCardHTML(seat, r, partyLabel, blocUnit, polOverride, opts = {}) {
  const compact = !!opts.compact;
  const pol = polOverride !== undefined ? polOverride : politicianFor(seat);
  const current = currentRepresentationFor(seat, opts.tier || state.tier);
  if (current && current.vacant_since) {
    const former = pol && pol.name ? pol.name : r.name;
    return `<div class="seat-yb-card has-profile${compact ? " is-compact" : ""}">
      <div class="yb-head"><div class="yb-id">
        <span class="yb-kicker">${esc(t("pol_seat_vacant"))}</span>
        <strong>${esc(t("card_no_current_yb"))}</strong>
        <p class="muted">${esc(t("card_former_yb", { name: former }))}</p>
      </div></div>
    </div>`;
  }
  const affiliation = currentAffiliationFor(seat, opts.tier || state.tier);
  if (affiliation) {
    const bloc = currentBlocFor(current);
    partyLabel = current.party && current.party !== bloc ? esc(current.party) : "";
    const pill = bloc ? `<span class="pill" style="${pillStyle(partyColor(bloc))}">${esc(bloc)}</span>` : "";
    blocUnit = `<span class="bloc-unit">${partyLabel && pill ? "· " : ""}${pill}</span>`;
  }
  const ybName = current && current.name ? current.name : (pol && pol.name ? pol.name : r.name);
  const ybBallot = pol && pol.ballot_name && namekeyLoose(pol.ballot_name) !== namekeyLoose(ybName) ? pol.ballot_name : "";
  // Do not infer an exact age from year-only Wikidata dates.
  const age = null;
  const ybMeta = [];
  if (age) ybMeta.push(`<span>${esc(t("pol_age", { n: age }))}</span>`);
  // education is long and variable — only on the full card, not the bento strip
  if (!compact && pol && pol.education) ybMeta.push(`<span>${esc(pol.education)}</span>`);
  const bioEntry = !compact && pol && pol.wikipedia
    ? (pol.wikipedia[lang] || pol.wikipedia.en || pol.wikipedia.ms)
    : null;
  // The bento can resolve a representative from the seat result even when the
  // optional portrait/profile roster has no entry (the common ADUN case).
  const openCode = compact && r && seat && seat.code ? seat.code : "";
  const openAttrs = openCode
    ? ` role="button" tabindex="0" data-pol-code="${esc(openCode)}" aria-haspopup="dialog" aria-label="${esc(t("card_current_yb"))}: ${esc(ybName)}"`
    : "";
  const openCls = openCode ? " is-openable" : "";
  const compactCls = compact ? " is-compact" : "";
  return pol
    ? `<div class="seat-yb-card has-profile${compactCls}${openCls}"${openAttrs}>
         <div class="yb-head">
           ${personPhotoHTML(ybName, pol.photo, "yb-photo")}
           <div class="yb-id">
             <span class="yb-kicker">${esc(t("card_current_yb"))}</span>
             <strong>${esc(ybName)}</strong>
             ${ybBallot ? `<span class="yb-ballot muted">${esc(ybBallot)}</span>` : ""}
             <p>${partyLabel ? partyLabel + " " : ""}${blocUnit}</p>
             ${ybMeta.length ? `<p class="yb-meta muted">${ybMeta.join(" · ")}</p>` : ""}
           </div>
         </div>
         ${bioEntry ? `<div class="yb-bio"><p class="yb-bio-text">${esc(bioEntry.extract)}</p><a class="yb-bio-more" href="${esc(bioEntry.url)}" target="_blank" rel="noopener">Wikipedia →</a></div>` : ""}
         ${compact ? "" : socialLinksHTML(pol.socials, pol.socials_source)}
       </div>`
    : `<div class="seat-yb-card has-profile${compactCls}${openCls}"${openAttrs}>
         <div class="yb-head">
           ${personPhotoHTML(r.name, null, "yb-photo")}
           <div class="yb-id">
             <span class="yb-kicker">${esc(t("card_current_yb"))}</span>
             <strong>${esc(r.name)}</strong>
             <p>${partyLabel ? partyLabel + " " : ""}${blocUnit}</p>
           </div>
         </div>
       </div>`;
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
  const resultSource = resultSourceLine(r, ownDun);
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
    const blocPill = `<span class="pill" style="${pillStyle(partyColor(r.coalition))}">${esc(r.coalition)}</span>`;
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
        ? ` <span class="pill" style="${pillStyle(partyColor(ru.party === r.party ? r.coalition : ru.party))};opacity:.85">${esc(ru.party)}</span>`
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
    const ybCard = ybCardHTML(seat, r, partyLabel, blocUnit);
    overviewHTML = `
      <div class="seat-overview">
        ${ybCard}
        ${metrics.length ? `<div class="seat-metrics">${metrics.join("")}</div>` : ""}
      </div>
      ${sc ? `<dl class="rows seat-score-row"><dt>${t("score")}</dt><dd class="mono"><b style="color:var(--accent-2)">${sc.score.toFixed(1)}</b> · ${esc(sc.grade || "")}</dd></dl>` : ""}
      ${resultSource}
      ${dunNote}
    `;
  } else {
    repRows += `<dt>${t("rep")}</dt><dd class="placeholder">${t("rep_ph")}</dd>`;
    // DUN seat in a state with no PRN result of its own → explain the gap rather than
    // leaving a bare empty state (and never borrow the parent-Parliament MP as the YB).
    overviewHTML = `${moduleEmptyHTML("overview")}${dunNote}`;
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
      : `${moduleEmptyHTML("results")}${isP ? `<div class="note">${t("score_building")}</div>` : dunNote}`;
  } else if (active === "candidates") {
    panelHTML = candidatesHTML(seat);
  } else if (active === "voting") {
    panelHTML = votingGuideHTML();
  } else {
    panelHTML = moduleEmptyHTML(active);
  }

  // desktop/landscape isolated view: keep the district finder pinned at the TOP of the
  // seat detail too, so switching to another district stays one tap away (mobile uses
  // the sticky bottom switcher instead).
  const desktopFinder = (state.openState && !MOBILE_MAP_INSPECT_MQ.matches)
    ? `<div class="state-info-h muted">${esc(t("find_district"))}</div>
       <div class="state-district-find state-district-find-top">${districtSwitchRowHTML(seat.code, false)}</div>`
    : "";
  return `
    ${desktopFinder}
    <div class="seat-detail-main">
      <div class="seat-head">
        <button class="share-icon seat-head-share" type="button" data-share-link data-i18n-aria="share_btn" aria-label="Share link" data-i18n-title="share_btn" title="Share link">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.2 14.8 14.8 9.2"/><path d="M10.4 7.4 11.8 6a4.2 4.2 0 0 1 6 6l-1.4 1.4"/><path d="M13.6 16.6 12.2 18a4.2 4.2 0 0 1-6-6l1.4-1.4"/></svg>
        </button>
        <div class="kicker">${esc(kicker)}</div>
        <h2>${esc(seat.name)}</h2>
        ${showStateLine ? `<div class="where">${t("state_label")} <b>${esc(seat.state)}</b></div>` : ""}
        ${!isP && seat.parlimen ? `<div class="where">${esc(t("parlimen_label"))} <b>${esc(parlimenContext(seat))}</b></div>` : ""}
      </div>
      ${seatDetailActionsHTML()}
      ${seatTabsHTML(active)}
      <div id="seat-tabpanel-${esc(active)}" class="seat-tabpanel" role="tabpanel" aria-labelledby="seat-tab-${esc(active)}">
        ${panelHTML}
      </div>
    </div>
    ${includeDistrictSwitcher ? seatDistrictSwitcherHTML(seat.code) : ""}
  `;
}

function seatDetailActionsHTML() {
  return `
    <div class="seat-detail-actions">
      <button class="share-btn seat-detail-action" type="button" data-share-link>${esc(t("share_btn"))}</button>
      <button class="share-btn seat-detail-action" type="button" data-share-card>${esc(t("card_btn"))}</button>
    </div>
  `;
}

function stateSeatCardHTML(seat) {
  // live-election view: the seat card IS the PRN candidate card (the GE15/PRN15
  // fallback stays available outside the election mode)
  if (state.prnMode && liveElection() && seat.state === liveElection().state && state.tier === liveElection().tier) {
    const entry = state.prn16.seats && state.prn16.seats[seat.code];
    if (entry) {
      // No mobile seat-picker under PRN cards (confusing vs normal Johor search)
      return `<div class="seat-detail-main">${prnSeatCardHTML(seat, entry)}</div>`;
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
          <span class="pill" style="${pillStyle(partyColor(c.coalition || c.party))}">${esc(c.party || c.coalition || "")}</span>
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
  }, { preserveMapView: !!state.openState });
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
function showToast(key, params) {
  if (!TOAST) return;
  TOAST.textContent = t(key, params);
  if (TOAST.hidden) {
    TOAST.hidden = false;
    TOAST.getBoundingClientRect();   // flush styles so the .show transition actually plays
  }
  TOAST.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { TOAST.classList.remove("show"); TOAST.hidden = true; }, 2600);
}
function showToastText(msg) {
  if (!TOAST || !msg) return;
  TOAST.textContent = msg;
  if (TOAST.hidden) {
    TOAST.hidden = false;
    TOAST.getBoundingClientRect();
  }
  TOAST.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { TOAST.classList.remove("show"); TOAST.hidden = true; }, 2800);
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
  if (handleCandidateCardClick(e)) return;
  if (e.target.closest("#share-link, [data-share-link]")) shareLink();
  else if (e.target.closest("#share-card, [data-share-card]")) shareCard(e.target);
});
PANEL_SEAT.addEventListener("keydown", handleCandidateCardKeydown);
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
// national at-a-glance: the Dewan Rakyat (GE15) coalition makeup under the home
// search bar. Colour bar only by default; bloc counts reveal on hover/focus and
// linger ~3s after the pointer leaves so the eye can finish reading PH 82 · …
// Always the parliament picture (tier-independent).
const NAT_GLANCE_LINGER_MS = 3000;
let natGlanceHideTimer = null;

function openNatGlanceKey() {
  const host = document.getElementById("nat-glance");
  if (!host) return;
  if (natGlanceHideTimer) { clearTimeout(natGlanceHideTimer); natGlanceHideTimer = null; }
  host.classList.add("is-open");
}
function scheduleCloseNatGlanceKey() {
  const host = document.getElementById("nat-glance");
  if (!host) return;
  if (natGlanceHideTimer) clearTimeout(natGlanceHideTimer);
  natGlanceHideTimer = setTimeout(() => {
    host.classList.remove("is-open");
    natGlanceHideTimer = null;
  }, NAT_GLANCE_LINGER_MS);
}
function bindNatGlanceHover() {
  const host = document.getElementById("nat-glance");
  if (!host || host.dataset.hoverBound) return;
  host.dataset.hoverBound = "1";
  host.addEventListener("mouseenter", openNatGlanceKey);
  host.addEventListener("mouseleave", scheduleCloseNatGlanceKey);
  host.addEventListener("focusin", openNatGlanceKey);
  host.addEventListener("focusout", (ev) => {
    // still inside the bar (e.g. tabbing between children) — keep open
    if (ev.relatedTarget && host.contains(ev.relatedTarget)) return;
    scheduleCloseNatGlanceKey();
  });
}

function renderNatGlance() {
  const host = document.getElementById("nat-glance");
  if (!host) return;
  if (!state.results) { host.hidden = true; requestAnimationFrame(syncMapToCard); return; }
  const counts = tallyCoalitions(state.results);
  const ordered = COALITION_ORDER.filter((c) => counts[c]);
  const summary = ordered.map((c) => `${c} ${counts[c]}`).join(" · ");
  document.getElementById("nat-bar").innerHTML = ordered
    .map((c) => `<span style="flex:${counts[c]};background:${partyColor(c)}" title="${esc(c)} ${counts[c]}"></span>`).join("");
  document.getElementById("nat-key").innerHTML = ordered
    .map((c) => `<span class="sk"><span class="sw" style="background:${partyColor(c)}"></span>${esc(c)} <b>${counts[c]}</b></span>`).join("");
  // full tally in aria so bar-only visual still announces PH 82 · PN 74 · …
  host.setAttribute("aria-label", `${t("by_bloc")}. ${summary}. ${t("simple_majority")}`);
  host.hidden = false;
  bindNatGlanceHover();
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
  // Mobile district detail: pin the title under the topbar. The map band also
  // starts below that title (syncMapToCard) and we reframe the state into that
  // band so geometry rides with the name instead of staying put while the
  // title alone jumps.
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
// along so drilling into DUN level always says which layer you're in — and is tappable
// to flip that state's layer without leaving the isolated view.
function setStageLabel(text) {
  const chip = text && text === state.openState ? t(state.tier === "dun" ? "tier_dun" : "tier_parlimen") : "";
  const memo = text ? `${text}|${chip}|${state.tier}` : text;
  if (memo === labelText) return;
  labelText = memo;
  if (!STATE_LABEL) return;
  if (text) {
    // structure: a big main line (name + tier chip) with a smaller sub line reserved
    // beneath it for the hovered district name (setStageSubLabel). Rebuilding the main
    // clears any hover sub — fine, the label just changed which state it names.
    const main = document.createElement("span");
    main.className = "label-main";
    const flagAsset = stateFlagAssetFor(text);
    if (flagAsset) {
      const flag = document.createElement("img");
      flag.className = "label-flag";
      flag.src = flagAsset;
      flag.alt = "";
      flag.setAttribute("aria-hidden", "true");
      flag.loading = "lazy";
      flag.decoding = "async";
      main.appendChild(flag);
    }
    main.appendChild(document.createTextNode(text));
    if (chip) {
      const next = state.tier === "dun" ? "parlimen" : "dun";
      const nextLabel = t(next === "dun" ? "tier_dun" : "tier_parlimen");
      const s = document.createElement("button");
      s.type = "button";
      s.className = "label-tier";
      s.textContent = chip;
      s.dataset.tierToggle = next;
      s.setAttribute("aria-label", t("tier_toggle_aria", { tier: nextLabel }));
      s.title = t("tier_toggle_aria", { tier: nextLabel });
      // Disable when we already know the other layer has no seats here (e.g. W.P. → DUN).
      const other = state.data[next];
      if (other && !other.seats.some((seat) => seat.state === text)) {
        s.disabled = true;
        s.title = t("tier_toggle_unavailable");
        s.setAttribute("aria-label", t("tier_toggle_unavailable"));
      }
      main.appendChild(s);
    }
    const sub = document.createElement("span");
    sub.className = "label-sub";
    STATE_LABEL.replaceChildren(main, sub);
    STATE_LABEL.classList.add("show");
    requestAnimationFrame(syncStageLabelPosition);
  } else {
    STATE_LABEL.classList.remove("show");
    STATE_LABEL.replaceChildren();
    document.documentElement.style.removeProperty("--state-label-top");
  }
}

// Flip Parliament ⇄ DUN while a state stays open (label-tier chip). Keeps isolation,
// refreshes the bottom card / map, and leaves PRN when the layer changes.
let openStateTierBusy = false;
async function switchOpenStateTier() {
  if (openStateTierBusy || !state.openState) return;
  const name = state.openState;
  const next = state.tier === "dun" ? "parlimen" : "dun";
  openStateTierBusy = true;
  try {
    // Leaving the election view when the user explicitly changes layer.
    if (state.prnMode) {
      state.prnMode = false;
      clearTimeout(prnLiveTimer);
      document.body.classList.remove("prn-mode");
      prnOptOut = true;
    }
    if (next === "parlimen") prnOptOut = true;

    const prev = state.tier;
    document.querySelectorAll("#tier button").forEach((x) => setOn(x, x.dataset.tier === next));
    state.tier = next;
    state.selected = null;
    clearSelectedDistrict();
    const cached = !!state.data[next];
    if (!cached) showLoading();
    try {
      await render(next);
    } catch (err) {
      console.error("switchOpenStateTier: render failed", err);
      state.tier = prev;
      document.querySelectorAll("#tier button").forEach((x) => setOn(x, x.dataset.tier === prev));
      showLoadError();
      return;
    }

    const d = state.data[next];
    const seats = d ? d.seats.filter((s) => s.state === name) : [];
    if (!seats.length) {
      // Revert — e.g. federal territory has no DUN layer.
      state.tier = prev;
      document.querySelectorAll("#tier button").forEach((x) => setOn(x, x.dataset.tier === prev));
      try { await render(prev); } catch (_) { /* keep previous if rebuild fails */ }
      state.openState = name;
      SEATS.classList.add("isolated");
      document.body.classList.add("state-open");
      highlightState(name);
      labelText = null;
      setStageLabel(name);
      refitOpenStateMap();
      return;
    }

    state.openState = name;
    document.getElementById("state-name").textContent = name;
    const countKey = "state_count_" + (next === "parlimen" ? "parlimen" : "dun") + (seats.length === 1 ? "_one" : "");
    document.getElementById("state-count").textContent = t(countKey, { n: seats.length });
    STATE_INFO.innerHTML = stateSummaryHTML(name);
    labelText = null;
    subLabelText = null;
    setStageLabel(name);
    SEATS.classList.add("isolated");
    document.body.classList.add("state-open");
    suppressMapRefit = true;
    try {
      setMapInspect(MOBILE_MAP_INSPECT_MQ.matches);
    } finally {
      suppressMapRefit = false;
    }
    highlightState(name);
    paint();
    zoomToState(name);
    if (BENTO_MQ.matches) showStateBento(name);
    else hideStateBento();
    renderSummary();
    renderMapInspectTray();
    syncLiveBadge();
    syncSidebar();
    writeHash();
    requestAnimationFrame(() => {
      syncMapToCard();
      refitOpenStateMap();
    });
  } finally {
    openStateTierBusy = false;
  }
}
if (STATE_LABEL) {
  STATE_LABEL.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button.label-tier");
    if (!btn || btn.disabled) return;
    e.preventDefault();
    e.stopPropagation();
    void switchOpenStateTier();
  });
}
// The hovered district name, shown smaller beneath the locked state name (isolated view,
// mouse only). Its space is reserved (CSS min-height) so the state name never jumps.
let subLabelText = null;
function setStageSubLabel(name) {
  if (!STATE_LABEL) return;
  const txt = name || "";
  if (txt === subLabelText) return;
  subLabelText = txt;
  const sub = STATE_LABEL.querySelector(".label-sub");
  if (!sub) return;
  sub.textContent = txt;
  sub.classList.toggle("show", !!txt);
}
function setStateHover(name, data) {
  if (name === hoverState) return;   // only re-paint when the hovered state actually changes
  clearStateHover();
  hoverState = name;
  setStageLabel(name);
  for (const s of data.seats) {
    if (s.state === name) { const p = state.paths.get(s.code); if (p) p.classList.add("state-hover"); }
  }
  SEATS.querySelectorAll(".seat.no-dun").forEach((p) =>
    p.classList.toggle("state-hover", p.dataset.state === name));
  // mirror the hover in the sidebar: the matching state emblem gets a glint sweep
  document.querySelectorAll("#sb-states [data-sb-state]").forEach((b) =>
    b.classList.toggle("is-map-hover", b.dataset.sbState === name));
}
function clearStateHover() {
  if (!hoverState) {
    setStageLabel(state.openState || null);
    return;
  }
  hoverState = null;
  setStageLabel(state.openState || null);
  SEATS.querySelectorAll(".seat.state-hover").forEach((p) => p.classList.remove("state-hover"));
  document.querySelectorAll("#sb-states .is-map-hover").forEach((b) => b.classList.remove("is-map-hover"));
}
function clearHoverUI() {
  TOOLTIP.hidden = true;
  setStageSubLabel("");
  clearStateHover();
}
SVG.addEventListener("mousemove", (e) => {
  if (!HOVER_MQ.matches) {
    clearHoverUI();
    return;
  }
  const tgt = e.target;   // NOT `t` — that name is the module-level i18n fn t(); shadowing breaks t("key")
  // Isolated state view: keep the state name locked above the map (no cursor tooltip),
  // and name the hovered district in a smaller line beneath the state header.
  if (state.openState) {
    TOOLTIP.hidden = true;
    setStageLabel(state.openState);
    if (tgt.classList && tgt.classList.contains("seat") && !tgt.classList.contains("no-dun")) {
      const data = state.data[state.tier];
      const seat = data && data.byCode.get(tgt.dataset.code);
      setStageSubLabel(seat && seat.state === state.openState ? seat.name : "");
    } else {
      setStageSubLabel("");
    }
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
// When a state is open the map camera is locked — user must not be able to drag/pan
// the isolated state around the screen (mobile map-inspect used to allow this).
SVG.addEventListener("pointerdown", (e) => {
  if (state.openState) return;
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
  if (state.openState) { mapDrag = null; return; }
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
  const tgt = e.target;   // NOT `t` — that name is the module-level i18n fn t(); shadowing it would break any t("key") added here
  TOOLTIP.hidden = true; clearStateHover();  // dismiss any lingering hover tooltip / state highlight
  const isSeat = !!(tgt.classList && tgt.classList.contains("seat"));
  const seat = isSeat && state.data[state.tier] && state.data[state.tier].byCode.get(tgt.dataset.code);
  // mobile seat-detail: tapping a district OF THE OPEN STATE opens the inspect tray.
  // Only own-state districts qualify — sea/outside taps used to be swallowed here,
  // stranding the user in the seat view after "locate me".
  if (MOBILE_MAP_INSPECT_MQ.matches && state.openState && state.selected && !state.mapInspect
      && seat && seat.state === state.openState) {
    setMapInspect(true);
    return;
  }
  if (isSeat) {
    if (!seat) return;
    if (state.openState) {
      // already isolated in a state → tapping a district shows its detail
      if (seat.state === state.openState) {
        if (state.mapInspect) previewDistrict(seat.code);
        else showDistrict(seat.code);
      } else {
        goBack();   // tapped a neighbouring state's seat → step back, same as empty space
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
  const seatHits = searchSeatsAndReps(data.seats, q, state.tier);
  // direct state matches — jump straight to a state's dashboard by name, so users
  // don't have to recognise it on the map (the sidebar state list is desktop-only).
  const stateHits = [...new Set(data.seats.map((s) => s.state))]
    .filter((st) => st && st.toLowerCase().includes(q))
    .sort();
  if (!seatHits.length && !stateHits.length) return;
  for (const p of state.paths.values()) p.classList.add("dim");
  const lit = (code) => { const p = state.paths.get(code); if (p) { p.classList.remove("dim"); p.classList.add("match"); } };
  for (const s of seatHits.slice(0, 60)) lit(s.code);
  if (stateHits.length) for (const s of data.seats) if (stateHits.includes(s.state)) lit(s.code);
  let i = -1;
  const stateRows = stateHits.slice(0, 4).map((st) => {
    const n = data.seats.filter((s) => s.state === st).length;
    return `<button id="result-opt-${++i}" role="option" aria-selected="false" data-state="${esc(st)}" class="result-state"><span>${esc(st)} <span class="muted" style="font-size:11px">${n} ${esc(t("bento_donut_seats"))}</span></span><span class="code">${esc(t("search_state"))}</span></button>`;
  });
  const seatRows = seatHits.slice(0, Math.max(4, 8 - stateRows.length)).map((s) => {
    const code = displayCode(s, state.tier);
    const rep = repNameForSeat(s);           // show the YB so a name match is obvious
    const sub = rep ? `${esc(rep)} <span style="opacity:.6">· ${esc(s.state)}</span>` : esc(s.state);
    return `<button id="result-opt-${++i}" role="option" aria-selected="false" data-code="${esc(s.code)}"><span>${esc(s.name)} <span class="muted" style="font-size:11px">${sub}</span></span><span class="code">${esc(code)}</span></button>`;
  });
  RESULTS.innerHTML = stateRows.concat(seatRows).join("");
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
  if (b.dataset.state) openStateCard(b.dataset.state);
  else select(b.dataset.code);
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
  // only flash the loading veil when the layer isn't already in memory
  const cached = !!state.data[tier];
  if (!cached) showLoading();
  try {
    await render(tier);
  } catch (err) {
    console.error("setTier: render failed", err);   // surfaced — a silent revert here reads as a dead button
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
// Quiet layer swap for openPrnMode only: load DUN without deselect()/home flash.
// setTier() would paint the whole country as DUN (different colours/shapes) for a
// frame before isolating Johor — that's the "click Johor and everything turns DUN".
async function ensureTierQuiet(tier) {
  if (tier === state.tier) return true;
  const prev = state.tier;
  document.querySelectorAll("#tier button").forEach((x) => setOn(x, x.dataset.tier === tier));
  state.tier = tier;
  state.selected = null;
  const cached = !!state.data[tier];
  if (!cached) showLoading();
  try {
    await render(tier);
  } catch (err) {
    console.error("ensureTierQuiet: render failed", err);
    state.tier = prev;
    document.querySelectorAll("#tier button").forEach((x) => setOn(x, x.dataset.tier === prev));
    showLoadError();
    return false;
  }
  // No deselect / writeHash — caller (openPrnMode) isolates next
  return true;
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
// The map layer/colour controls sit beside the search only on the widest layout (where
// the sidebar owns nav); below the sidebar breakpoint they live in the hamburger menu
// alongside the other nav, so the topbar never overflows. One set of elements, relocated
// by viewport — handlers bind by id, so they keep working wherever the nodes land.
const MAPCTRL_MQ = matchMedia("(min-width: 640px)");
function placeMapControls() {
  const tier = document.getElementById("tier"), mode = document.getElementById("mode");
  const target = MAPCTRL_MQ.matches
    ? document.querySelector("#panel-empty .find-actions")
    : document.getElementById("menu-map-controls");
  if (!tier || !mode || !target) return;
  target.appendChild(tier);            // append keeps [location] then [tier][mode] on desktop
  target.appendChild(mode);
  // phone topbar keeps only brand · live badge · burger — the language seg and
  // theme toggle ride into the menu's icon row (flex `order` restores the topbar
  // arrangement when they move back; handlers bind by id/attr so they keep working)
  const lang = document.getElementById("lang");
  const theme = document.getElementById("top-theme");
  const icons = document.querySelector("#mobile-menu .topicons");
  const end = document.querySelector("#topbar .topbar-end");
  if (lang && theme && icons && end) {
    if (MAPCTRL_MQ.matches) { end.appendChild(lang); end.appendChild(theme); }
    else { icons.appendChild(lang); icons.appendChild(theme); }
  }
}
MAPCTRL_MQ.addEventListener ? MAPCTRL_MQ.addEventListener("change", placeMapControls) : MAPCTRL_MQ.addListener(placeMapControls);
placeMapControls();
document.getElementById("lang").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (b) setLang(b.dataset.lang);
});
document.querySelectorAll("[data-theme-toggle]").forEach((btn) => btn.addEventListener("click", toggleTheme));
document.querySelectorAll("#stage > fluid-bg").forEach(randomizeFluidPhase);

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

// ---- manifesto pledges dialog (seat-card shortcut; full view is Politicians → Pledges) ----
const PLEDGES_MODAL = document.getElementById("pledges-modal");
const NEWS_VIEW = document.getElementById("news-view");
function openPledgesModal() {
  // Prefer the Politicians directory tab when the roster is available
  if (state.politicians && state.johorPledges) {
    polTier = "pledges";
    openPoliticians();
    return;
  }
  if (!PLEDGES_MODAL || !state.johorPledges) return;
  PLEDGES_MODAL.innerHTML = `
    <div class="pol-modal-shell">
      <button class="pol-modal-close" type="button" aria-label="${esc(t("card_preview_close"))}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><line x1="6" x2="18" y1="6" y2="18"/><line x1="6" x2="18" y1="18" y2="6"/></svg>
      </button>
      <h2 class="pledges-modal-h">${esc(t("prn_pledges"))}</h2>
      <div id="pledges-modal-body">${prnPledgeTabsHTML()}</div>
      <p class="src-line muted">${esc(t("prn_source"))}</p>
    </div>`;
  if (typeof PLEDGES_MODAL.showModal === "function") PLEDGES_MODAL.showModal();
  else PLEDGES_MODAL.setAttribute("open", "");
}
PLEDGES_MODAL?.addEventListener("click", (ev) => {
  if (ev.target.closest(".pol-modal-close") || ev.target === PLEDGES_MODAL) {
    if (PLEDGES_MODAL.open) PLEDGES_MODAL.close();
    PLEDGES_MODAL.innerHTML = "";
    return;
  }
  const tab = ev.target.closest(".prn-pl-tab");
  if (tab) {
    prnPledgeTab = tab.dataset.pledgeTab;
    const host = document.getElementById("pledges-modal-body");
    if (host) host.innerHTML = prnPledgeTabsHTML();
  }
});
// the mobile seat card links out to the manifesto rather than dumping every pledge inline
document.addEventListener("click", (ev) => {
  if (ev.target.closest("[data-open-pledges]")) { ev.preventDefault(); openPledgesModal(); }
});
CAND_MODAL?.addEventListener("click", (ev) => {
  if (ev.target.closest(".pol-modal-close") || ev.target === CAND_MODAL) {
    closeCandidateModal();
    return;
  }
  const seatBtn = ev.target.closest("[data-candidate-seat]");
  if (seatBtn) {
    const code = seatBtn.dataset.candidateSeat;
    closeCandidateModal();
    openSeatFromPolitician(code);
  }
});
CAND_MODAL?.addEventListener("close", () => {
  CAND_MODAL.innerHTML = "";
  const returnTo = candidateModalReturnTo;
  candidateModalReturnTo = null;
  if (returnTo && document.contains(returnTo)) returnTo.focus({ preventScroll: true });
});

// ---- sidebar (wide screens): brand · nav · states list · lang ----
function renderSidebarStates() {
  const host = document.getElementById("sb-states");
  const d = state.data.parlimen || state.data.dun;
  if (!host || !d) return;
  const names = [...new Set(d.seats.map((s) => s.state))]
    .sort((a, b) => (a.startsWith("W.P.") - b.startsWith("W.P.")) || a.localeCompare(b));
  const e = liveElection();
  host.innerHTML = names.map((n) => {
    const isElection = !!(e && e.state === n);
    const liveLabel = isElection ? `${n} · ${e.name || t("prn_kicker")}` : n;
    return `<button type="button" class="sb-item sb-state${isElection ? " is-election" : ""}" data-sb-state="${esc(n)}" aria-label="${esc(liveLabel)}" title="${esc(liveLabel)}">
      ${stateEmblemHTML(n, "sb-state-emblem")}
      <span class="sb-state-name">${esc(n)}</span>
      ${isElection ? `<span class="live-dot sb-state-dot" title="${esc(t("prn_kicker"))}" aria-hidden="true"></span>` : ""}
    </button>`;
  }).join("");
  host.querySelectorAll("[data-sb-state]").forEach((button) => {
    button.addEventListener("pointerenter", () => previewSidebarState(button));
    button.addEventListener("pointerleave", clearSidebarStatePreview);
    button.addEventListener("focus", () => previewSidebarState(button));
    button.addEventListener("blur", clearSidebarStatePreview);
  });
}
function previewSidebarState(button) {
  const name = button && button.dataset.sbState;
  const data = state.data[state.tier];
  if (!name || !data) return;
  setStateHover(name, data);

  const label = document.getElementById("sb-state-hover-label");
  if (!label || !document.body.classList.contains("sb-collapsed")) return;
  label.textContent = name;
  label.hidden = false;
  const rect = button.getBoundingClientRect();
  const half = (label.offsetHeight || 30) / 2;
  const center = rect.top + rect.height / 2;
  label.style.top = `${Math.round(Math.max(half + 8, Math.min(innerHeight - half - 8, center)))}px`;
}
function clearSidebarStatePreview() {
  const label = document.getElementById("sb-state-hover-label");
  if (label) label.hidden = true;
  clearStateHover();
}
function syncSidebar() {
  const sb = document.getElementById("sidebar");
  if (!sb) return;
  const pol = document.body.classList.contains("politicians-open");
  sb.querySelector("#sb-map")?.classList.toggle("on", !state.openState && !pol);
  sb.querySelector("#sb-politicians")?.classList.toggle("on", pol);
  // live election is highlighted on its state row (e.g. Johor), not a separate PRN nav item
  const e = liveElection();
  sb.querySelectorAll("[data-sb-state]").forEach((b) => {
    const isOpen = !pol && state.openState === b.dataset.sbState;
    const isLiveState = !!(e && e.state === b.dataset.sbState);
    b.classList.toggle("on", isOpen);
    b.classList.toggle("is-election", isLiveState);
    b.classList.toggle("is-prn-on", isLiveState && !!state.prnMode && !pol);
  });
  sb.querySelectorAll("[data-sb-lang]").forEach((b) =>
    b.classList.toggle("on", b.dataset.sbLang === lang));
}
// a state picked from the sidebar — W.P. territories only exist on the parliament
// layer, so switch tiers when the current layer has no seats for it
async function sidebarOpenState(name) {
  closePoliticians({ silent: true });
  hideInfo();
  // live election state (Johor) → open the PRN dashboard; other states open normally
  const e = liveElection();
  if (e && e.state === name) {
    if (state.prnMode && state.openState === name) { syncSidebar(); return; }
    await openPrnMode();
    syncSidebar();
    return;
  }
  // switching to a non-election state leaves the election view — without this the
  // prn flag stays on, /prn leaks into the other state's hash, and a later click
  // on the election state dead-ends in openPrnMode's already-open guard
  if (state.prnMode) closePrnMode({ silent: true });
  const has = () => state.data[state.tier] && state.data[state.tier].seats.some((sd) => sd.state === name);
  if (!has()) await setTier(state.tier === "dun" ? "parlimen" : "dun");
  if (state.openState !== name) openStateCard(name);
  syncSidebar();
}
// collapse ⇄ expand: the rail shrinks to an icon strip and the content reflows
// beside it (the sidebar never overlays the map or the dashboard).
// Desktop: click the toggle to expand; auto-collapse after 1.5s idle. No hover-open.
const SB_AUTO_COLLAPSE_MS = 1500;
const SB_WIDE_MQ = matchMedia("(min-width: 640px)");
let sbAutoTimer = null;

function sbAutoCollapseEnabled() {
  return SB_WIDE_MQ.matches;
}
function clearSbAutoTimer() {
  if (sbAutoTimer) { clearTimeout(sbAutoTimer); sbAutoTimer = null; }
}
function scheduleSidebarAutoCollapse() {
  clearSbAutoTimer();
  if (!sbAutoCollapseEnabled()) return;
  if (document.body.classList.contains("sb-collapsed")) return;
  sbAutoTimer = setTimeout(() => {
    sbAutoTimer = null;
    if (!sbAutoCollapseEnabled()) return;
    if (document.body.classList.contains("sb-collapsed")) return;
    setSidebarCollapsed(true);
  }, SB_AUTO_COLLAPSE_MS);
}
/** Reset the idle clock while the rail is expanded (click / move / scroll / focus). */
function bumpSidebarAutoCollapse() {
  if (!sbAutoCollapseEnabled()) return;
  if (document.body.classList.contains("sb-collapsed")) return;
  scheduleSidebarAutoCollapse();
}

function setSidebarCollapsed(v) {
  clearSidebarStatePreview();
  document.body.classList.toggle("sb-collapsed", !!v);
  try { localStorage.setItem("mp-sb-collapsed", v ? "1" : "0"); } catch (_) {}
  requestAnimationFrame(syncMapToCard);          // map band re-measures at the new width
  setTimeout(syncLiveBadge, 160);                // badge re-pins after the transition
  if (v) clearSbAutoTimer();
  else scheduleSidebarAutoCollapse();            // expanded → start idle collapse
}
function bindSidebarAutoCollapse() {
  const sb = document.getElementById("sidebar");
  if (!sb || sb.dataset.autoCollapseBound) return;
  sb.dataset.autoCollapseBound = "1";
  // activity while open restarts the 1.5s idle timer — never opens on hover
  const bump = () => bumpSidebarAutoCollapse();
  sb.addEventListener("pointermove", bump, { passive: true });
  sb.addEventListener("wheel", bump, { passive: true });
  sb.addEventListener("scroll", bump, { passive: true, capture: true });
  sb.addEventListener("focusin", bump);
  SB_WIDE_MQ.addEventListener?.("change", () => {
    if (!sbAutoCollapseEnabled()) clearSbAutoTimer();
    else if (!document.body.classList.contains("sb-collapsed")) scheduleSidebarAutoCollapse();
  });
}
// desktop: start collapsed; narrow keeps prior preference
try {
  if (typeof matchMedia === "function" && matchMedia("(min-width: 640px)").matches) {
    document.body.classList.add("sb-collapsed");
  } else if (localStorage.getItem("mp-sb-collapsed") === "1") {
    document.body.classList.add("sb-collapsed");
  }
} catch (_) {}
bindSidebarAutoCollapse();
if (sbAutoCollapseEnabled() && !document.body.classList.contains("sb-collapsed")) {
  scheduleSidebarAutoCollapse();
}
document.getElementById("sidebar")?.addEventListener("click", (ev) => {
  // any click in the rail counts as use (and may expand via the toggle below)
  bumpSidebarAutoCollapse();
  if (ev.target.closest("#sb-collapse")) {
    const willCollapse = !document.body.classList.contains("sb-collapsed");
    setSidebarCollapsed(willCollapse);
    return;
  }
  const langBtn = ev.target.closest("[data-sb-lang]");
  if (langBtn) {
    document.querySelector(`#lang button[data-lang="${langBtn.dataset.sbLang}"]`)?.click();
    syncSidebar();
    return;
  }
  if (ev.target.closest("#sb-brand") || ev.target.closest("#sb-map")) {
    closePoliticians({ silent: true }); closeNewsPage({ silent: true }); hideInfo(); backToControls(); syncSidebar(); return;
  }
  if (ev.target.closest("#sb-politicians")) { hideInfo(); openPoliticians(); setTimeout(syncSidebar, 60); return; }
  if (ev.target.closest("#sb-about")) { showInfo(); return; }
  if (ev.target.closest("#sb-share")) { shareApp(); return; }
  const st = ev.target.closest("[data-sb-state]");
  if (st) sidebarOpenState(st.dataset.sbState);
});

// ---- boot ----
(async function init() {
  setTheme(theme, false);
  document.querySelectorAll("#lang button").forEach((x) => setOn(x, x.dataset.lang === lang));
  applyStatic();
  // Measure the empty card early so --map-h is close before paths paint
  try { syncMapToCard(); } catch (_) {}
  const bootHash = location.hash;   // captured before writeHash() normalises it
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
  // warm the other map layer in the background so Parliament ⇄ DUN flips feel instant
  const otherTier = tier === "parlimen" ? "dun" : "parlimen";
  const warmOther = () => { loadTier(otherTier).catch(() => {}); };
  if (typeof requestIdleCallback === "function") requestIdleCallback(warmOther, { timeout: 1800 });
  else setTimeout(warmOther, 250);
  renderSummary();
  try {
    await loadOptional();           // results/scores ready → modes can be restored
  } catch (_) { /* optional layers must never blank the map */ }
  renderSidebarStates();
  syncSidebar();                  // PRN entry + lang state need the loaded data
  if (h && h.mode === "negeri") setMode("negeri");
  else if (h && h.mode === "skor") setMode("parti");
  else setMode("parti");
  if (h && h.code) {
    const data = state.data[state.tier];
    if (data.byCode.has(h.code)) select(h.code);
  } else if (h && h.stateName && !h.prn) {
    // deep-linked state dashboard (#tier/mode/s:StateName) — only for a real state
    // in this tier; a bogus name just falls through to writeHash() normalisation
    const data = state.data[state.tier];
    if (data.seats.some((s) => s.state === h.stateName)) openStateCard(h.stateName);
  }
  if (h && h.prn && liveElection()) {
    try {
      await openPrnMode();     // deep-linked election view (#dun/parti[/seat]/prn)
      if (h.code && state.data[state.tier].byCode.has(h.code)) showDistrict(h.code);
    } catch (_) {}
  }
  syncLiveBadge();
  refreshPrnLive();
  writeHash();       // normalise URL to the actually-active state — a gated mode (Skor) or bad seat
                     // code in the deep link gets dropped so a re-shared link can't misrepresent state
                     // (replaceState → no extra history entry)
  if (bootHash === "#politicians" && state.politicians) await openPoliticians();  // deep-linked directory
  if (bootHash === "#news") openNewsPage();   // deep-linked news page
  maybeShowHint();   // fresh visit, nothing selected → nudge that seats are tappable
  try { syncMapToCard(); } catch (_) {}
  // body.sb-collapsed is set above; drop the html pre-paint hint
  document.documentElement.classList.remove("sb-pref-collapsed");
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
document.getElementById("topbar-title")?.addEventListener("click", showWholeMap);
document.getElementById("top-map")?.addEventListener("click", showWholeMap);
document.getElementById("top-info")?.addEventListener("click", showInfo);
document.getElementById("top-share")?.addEventListener("click", shareApp);
document.getElementById("top-politicians")?.addEventListener("click", () => openPoliticians());
// mobile-menu nav parity with the wide-screen sidebar (each shown only when relevant)
POL_VIEW?.addEventListener("click", (e) => {
  if (e.target.closest("a")) return;   // a social-icon link — let it open, don't pop the profile
  const party = e.target.closest("[data-pol-party]");
  if (party) {
    // exact party filter (not free-text search — "PAS" used to match "Pasir Gudang")
    polTier = "all";
    polPartyFilter = normPartyLabel(party.dataset.polParty || "");
    renderPoliticiansDirectory("");
    return;
  }
  const card = e.target.closest("[data-pol-code]");
  if (card) openPoliticianModal(card.dataset.polCode, card);   // full-profile bento, not the map
});
POL_VIEW?.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const card = e.target.closest(".pol-card");
  if (card && e.target === card) { e.preventDefault(); openPoliticianModal(card.dataset.polCode, card); }
});
// browser back closes the directory (it pushed a #politicians history entry)
window.addEventListener("popstate", () => {
  if (location.hash === "#politicians") { if (state.politicians) openPoliticians(); }
  else if (document.body.classList.contains("politicians-open")) closePoliticians({ silent: true });
  if (location.hash === "#news") openNewsPage();
  else if (document.body.classList.contains("news-open")) closeNewsPage({ silent: true });
});

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
  const label = esc(t(state.prnMode ? "prn_pick_seat_label" : "map_inspect_select_label"));
  const selected = seats.find((seat) => seat.code === selectedCode);
  const selectedText = selected
    ? `${displayCode(selected, state.tier) || selected.code} · ${selected.name}`
    : t(state.prnMode ? "prn_pick_seat_ph" : "map_inspect_select_ph");
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
        <div class="map-inspect-search-wrap">
          <input id="map-inspect-search" class="map-inspect-search" type="search" autocomplete="off" spellcheck="false"
            placeholder="${esc(t("find_district_search"))}" aria-label="${esc(t("find_district_search"))}" />
        </div>
        <div class="map-inspect-options">
        ${seats.map((seat) => {
          const code = displayCode(seat, state.tier) || seat.code;
          const isSelected = seat.code === selectedCode;
          const rep = repNameForSeat(seat);
          return `
            <button
              class="map-inspect-option"
              type="button"
              role="option"
              aria-selected="${isSelected ? "true" : "false"}"
              data-map-inspect-district="${esc(seat.code)}"
              data-search="${esc(`${code} ${seat.name} ${rep}`.toLowerCase())}">
              ${esc(code)} · ${esc(seat.name)}${rep ? ` <span class="map-inspect-option-yb muted">· ${esc(rep)}</span>` : ""}
            </button>
          `;
        }).join("")}
        <div class="map-inspect-noresult muted" hidden>${esc(t("map_inspect_no_match"))}</div>
        </div>
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

let districtPickerIgnoreCloseUntil = 0;
function setDistrictPickerOpen(open, focusOption = false) {
  const picker = document.getElementById("map-inspect-district-picker");
  if (!picker) return;
  const toggle = picker.querySelector("#map-inspect-district-toggle");
  const list = picker.querySelector("#map-inspect-district-list");
  if (!toggle || !list) return;
  const next = !!open;
  picker.classList.toggle("open", next);
  document.body.classList.toggle("district-picker-open", next);
  toggle.setAttribute("aria-expanded", next ? "true" : "false");
  list.hidden = !next;
  if (next) {
    // Ignore the same-gesture document click that would immediately re-close on iOS
    districtPickerIgnoreCloseUntil = Date.now() + 400;
    // opening: reset any prior filter, then put the cursor in the search box so the
    // user can type straight away (arrow-down hops into the options list).
    const search = list.querySelector("#map-inspect-search");
    if (search) { search.value = ""; filterDistrictOptions(list, ""); }
    if (focusOption) (search || list.querySelector(".map-inspect-option"))?.focus({ preventScroll: true });
  }
}

// show only options whose code / name / YB matches the query; toggle the empty state
function filterDistrictOptions(list, q) {
  const ql = (q || "").trim().toLowerCase();
  let any = false;
  list.querySelectorAll(".map-inspect-option").forEach((opt) => {
    const match = !ql || (opt.dataset.search || "").includes(ql);
    opt.hidden = !match;
    if (match) any = true;
  });
  const empty = list.querySelector(".map-inspect-noresult");
  if (empty) empty.hidden = any;
}

function districtPickerOpen() {
  const toggle = document.getElementById("map-inspect-district-toggle");
  return toggle?.getAttribute("aria-expanded") === "true";
}

function focusDistrictPickerOption(current, key) {
  const list = document.getElementById("map-inspect-district-list");
  if (!list) return;
  const options = [...list.querySelectorAll(".map-inspect-option:not([hidden])")];
  if (!options.length) return;
  const currentIndex = Math.max(0, options.indexOf(current));
  let nextIndex = currentIndex;
  if (key === "ArrowDown") nextIndex = Math.min(options.length - 1, currentIndex + 1);
  else if (key === "ArrowUp") nextIndex = Math.max(0, currentIndex - 1);
  else if (key === "Home") nextIndex = 0;
  else if (key === "End") nextIndex = options.length - 1;
  options[nextIndex].focus();
}

function chooseMapInspectDistrict(code, focusToggle = false) {
  if (!code) return;
  setDistrictPickerOpen(false);
  if (state.mapInspect) previewDistrict(code);
  else showDistrict(code);
  if (focusToggle) {
    requestAnimationFrame(() => {
      document.getElementById("map-inspect-district-toggle")?.focus({ preventScroll: true });
    });
  }
}

// district-picker search box (lives inside PANEL_STATE or PANEL_SEAT, so bind once
// at the document): filter as you type; Enter picks the first visible, ArrowDown
// hops into the list, Escape closes.
document.addEventListener("input", (e) => {
  if (e.target.id !== "map-inspect-search") return;
  const list = e.target.closest(".map-inspect-select-list");
  if (list) filterDistrictOptions(list, e.target.value);
});
document.addEventListener("keydown", (e) => {
  if (e.target.id !== "map-inspect-search") return;
  const list = e.target.closest(".map-inspect-select-list");
  if (!list) return;
  const first = () => list.querySelector(".map-inspect-option:not([hidden])");
  if (e.key === "Enter") { e.preventDefault(); chooseMapInspectDistrict(first()?.dataset.mapInspectDistrict, true); }
  else if (e.key === "ArrowDown") { e.preventDefault(); first()?.focus(); }
  else if (e.key === "Escape") { e.preventDefault(); setDistrictPickerOpen(false); }
});

function mapInspectOverviewHTML(seat) {
  if (!seat) return "";
  // Election night: show tonight's lead for this seat, not the 2022 incumbent
  if (state.prnMode && prnLiveIsHot()) {
    const lr = prnLiveForSeat(seat.code);
    if (lr && (lr.name || lr.coalition || lr.party)) {
      const coal = lr.coalition || lr.party || "";
      const col = coal ? prnCoalColor(coal) : null;
      const pill = col
        ? `<span class="pill" style="${pillStyle(col.bg, col.fg)}">${esc(coal)}</span>`
        : "";
      const maj = lr.majority != null && lr.majority !== ""
        ? ` · ${esc(t("prn_majority_n", { n: lr.majority }))}`
        : "";
      const st = prnLiveStatusMeta(lr);
      return `
        <button id="map-inspect-details" class="map-inspect-overview is-live-lead" type="button" title="${esc(t("map_inspect_more"))}">
          <span>${esc(t("prn_tonight_leader"))} · ${esc(st.label)}</span>
          <strong>${esc(lr.name || "—")}</strong>
          <p>${pill}${maj ? `<span class="muted">${maj}</span>` : ""}</p>
        </button>
      `;
    }
    return `
      <button id="map-inspect-details" class="map-inspect-overview is-live-await" type="button" title="${esc(t("map_inspect_more"))}">
        <span>${esc(seat.dun_code || seat.code)} · ${esc(seat.name)}</span>
        <strong>${esc(t("prn_tonight_awaiting_seat"))}</strong>
        <p class="muted">${esc(t("prn_tap_hint"))}</p>
      </button>
    `;
  }
  const r = resultFor(seat);
  if (!r) {
    return `
      <div class="map-inspect-overview">
        <span>${esc(t("rep"))}</span>
        <strong>${esc(t("rep_ph"))}</strong>
      </div>
    `;
  }
  const current = currentRepresentationFor(seat);
  if (current && current.vacant_since) return `
    <div class="map-inspect-overview">
      <span>${esc(t("pol_seat_vacant"))}</span>
      <strong>${esc(t("card_no_current_yb"))}</strong>
    </div>`;
  const card = formatResultCard(r);
  const bloc = currentBlocFor(current);
  const partyLabel = current && current.party && current.party !== bloc
    ? esc(current.party)
    : (card.party && card.party.label && card.party.label !== r.coalition ? esc(card.party.label) : "");
  const blocPill = bloc ? `<span class="pill" style="${pillStyle(partyColor(bloc))}">${esc(bloc)}</span>` : "";
  // A BUTTON, not a div: the YB overview is the biggest thing in the tray and reads as
  // tappable — so it is. It opens the same detail as "More" (#map-inspect-details handler).
  return `
    <button id="map-inspect-details" class="map-inspect-overview" type="button" title="${esc(t("map_inspect_more"))}">
      <span>${esc(t("card_current_yb"))}</span>
      <strong>${esc((current && current.name) || (politicianFor(seat) || {}).name || r.name)}</strong>
      <p>${partyLabel ? `${partyLabel} ` : ""}${blocPill}</p>
    </button>
  `;
}

function mapInspectPrnSummaryHTML() {
  if (!state.prnMode) return "";
  const e = prnActiveForState(state.openState);
  const p = state.prn16;
  if (!e || !p) return "";
  const liveNow = prnLiveIsHot();
  const totalCands = prnContestTotal(p);
  const seatSelected = !!selectedSeat();
  const phaseChip = liveNow
    ? `<span class="prn-live-chip">${esc(t(state.prnLive.phase === "final" ? "prn_phase_final" : "prn_phase_live"))}</span>`
    : "";

  if (liveNow) {
    const { declared, leading, majority, total, live } = prnLiveStats();
    // Landing (no seat): full race picture. Seat open: keep a compact race strip so
    // you never lose the night tally behind "choose district".
    const metrics = `
      <div class="prn-mobile-metrics" role="group" aria-label="${esc(t("prn_live_strip_title"))}">
        <div class="prn-mobile-metric">
          <span class="muted">${esc(t("prn_live_declared_short"))}</span>
          <b>${declared}<small>/${total}</small></b>
        </div>
        <div class="prn-mobile-metric">
          <span class="muted">${esc(t("prn_live_leading_short"))}</span>
          <b>${leading}</b>
        </div>
        <div class="prn-mobile-metric">
          <span class="muted">${esc(t("prn_live_majority_short"))}</span>
          <b>${majority}</b>
        </div>
      </div>`;
    const tally = prnLiveTallyHTML({ compact: true });
    // Order matters on iOS: actions ABOVE the table so they never paint over rows
    // when WebKit mishandles nested flex overflow.
    const candsBtn = !seatSelected
      ? `<button id="prn-all-candidates" class="prn-pledges-btn prn-mobile-cands" type="button">👥 ${esc(t("prn_all_cands", { n: totalCands }))} →</button>`
      : "";
    const board = !seatSelected
      ? `<div id="mobile-live-board" class="mobile-live-board prn-mobile-board">${bentoLiveTableHTML(state.openState)}</div>`
      : "";
    return `
      <section class="prn-mobile-summary is-live${seatSelected ? " is-compact" : ""}" aria-label="${esc(e.name)}">
        <div class="prn-mobile-title">
          <span class="live-dot" aria-hidden="true"></span>
          <span>${esc(e.name)}</span>
          ${phaseChip}
        </div>
        <div class="prn-mobile-meta">${esc(t("prn_live_polling_today"))} · ${esc(fmtDayMonth(e.polling_day))}</div>
        ${metrics}
        ${tally}
        ${candsBtn}
        ${board}
      </section>
    `;
  }

  // Pre-count / campaign: still more than a title — dates, majority, field size
  const cd = prnCountdownLabel(e);
  const order = Object.entries(p.contested || {}).sort((a, b) => b[1] - a[1]);
  const bar = order.map(([coal, n]) => {
    const c = prnCoalColor(coal);
    return `<span style="width:${(100 * n / Math.max(1, totalCands)).toFixed(2)}%;background:${c.bg}"></span>`;
  }).join("");
  const key = order.map(([coal, n]) => {
    const c = prnCoalColor(coal);
    return `<span class="state-bloc"><span class="sw" style="background:${c.bg}"></span>${esc(coal)} ${n}</span>`;
  }).join("");
  return `
    <section class="prn-mobile-summary" aria-label="${esc(e.name)}">
      <div class="prn-mobile-title"><span class="live-dot" aria-hidden="true"></span><span>${esc(e.name)}</span></div>
      <div class="prn-mobile-meta">${esc(t("prn_polling"))} ${esc(fmtDayMonth(e.polling_day))}${cd ? " · " + esc(cd) : ""}</div>
      <div class="prn-mobile-chips">
        <span class="prn-mobile-chip"><b>${esc(t("prn_candidates_filed", { n: totalCands }))}</b></span>
        <span class="prn-mobile-chip">${esc(t("prn_majority", { n: e.majority }))}</span>
      </div>
      <div class="prn-mobile-board-h muted">${esc(t("prn_contested"))} · ${totalCands}</div>
      <div class="sharebar prn-live-bar">${bar}</div>
      <div class="sharebar-key">${key}</div>
      <button id="prn-all-candidates" class="prn-pledges-btn prn-mobile-cands" type="button">👥 ${esc(t("prn_all_cands", { n: totalCands }))} →</button>
      <p class="prn-mobile-hint muted">${esc(t("prn_mobile_landing_hint"))}</p>
    </section>
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
  // PRN election view: no district/candidate search on mobile — the live table +
  // map are enough; search stays available in normal Johor (non-PRN) mode.
  const districtRow = state.prnMode
    ? ""
    : districtSwitchRowHTML(state.selected || "", !!seat);
  // Landing only: current YB / coalition breakdown (same idea as the home nat-glance bar).
  // Hidden once a district is open so the YB overview owns the tray.
  const makeupGlance = !seat ? stateMakeupGlanceHTML(state.openState) : "";
  MAP_INSPECT_TRAY.innerHTML = `
    <div class="map-inspect-choice">
      ${makeupGlance}
      ${prnRow}
      ${mapInspectPrnSummaryHTML()}
      ${mapInspectOverviewHTML(seat)}
      ${districtRow}
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
    // During the More pop the onLayout callback owns the viewBox so district details
    // can open without refitting or expanding the isolated state.
    if (mapInspectDetailsAnimating) return;
    // Explicit refits frame the whole state; district-detail entry suppresses this so
    // tapping a district only highlights it and does not resize the isolated state.
    zoomToState(state.openState);
    requestAnimationFrame(syncMapToCard);
  };
  if (delay) setTimeout(run, delay);
  else requestAnimationFrame(run);
}

function refitOpenStateMapSettled() {
  refitOpenStateMap();
  refitOpenStateMap(60);
  refitOpenStateMap(160);
}

let suppressMapRefit = false;
function setMapInspectWithoutRefit(open) {
  suppressMapRefit = true;
  try {
    setMapInspect(open);
  } finally {
    suppressMapRefit = false;
  }
}
function setMapInspect(open) {
  const next = !!open && !!state.openState && MOBILE_MAP_INSPECT_MQ.matches;
  if (state.mapInspect === next) {
    renderMapInspectTray();
    syncMapInspectButton();
    if (!suppressMapRefit) {
      if (next) refitOpenStateMapSettled();
      else refitOpenStateMap();
    }
    return;
  }
  state.mapInspect = next;
  document.body.classList.toggle("map-inspect", next);
  if (next) setPanelView("state");
  renderMapInspectTray();
  syncMapInspectButton();
  if (!suppressMapRefit) {
    if (next) refitOpenStateMapSettled();
    else refitOpenStateMap();
  }
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

// Leave the bento: full map pops up from center (scale+fade) instead of a side-pan
// zoom out from the last state camera — that read as the map "coming from the side".
const MAP_POP_MS = 300;
function playMapCenterPop() {
  if (!SVG || ANIM_OFF || REDUCE_MOTION.matches || !SVG.animate) return;
  SVG.getAnimations().forEach((a) => a.cancel());
  const prevOrigin = SVG.style.transformOrigin;
  const prevWillChange = SVG.style.willChange;
  SVG.style.transformOrigin = "50% 50%";
  SVG.style.willChange = "transform, opacity";
  const a = SVG.animate(
    [
      { opacity: 0, transform: "scale(0.84)" },
      { opacity: 1, transform: "scale(1)" },
    ],
    { duration: MAP_POP_MS, easing: "cubic-bezier(0.16, 1.05, 0.3, 1)", fill: "both" }
  );
  const done = () => {
    SVG.style.transformOrigin = prevOrigin;
    SVG.style.willChange = prevWillChange;
  };
  a.onfinish = done;
  a.oncancel = done;
  setTimeout(done, MAP_POP_MS + 40);
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
          showDistrict(seat.code);
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
        setMapInspectWithoutRefit(false);
        setPanelView("seat");
        STATE_INFO.innerHTML = stateSeatCardHTML(seat);
        resetStateInfoScroll();
        writeHash();
      }, (firstMap, lastMap) => {
        // Keep the camera stable through the card FLIP, then reframe so the state
        // rides up with the title pinned under the topbar.
        if (MOBILE_MAP_INSPECT_MQ.matches && state.openState) {
          setViewBoxPreservingScreen(firstMap, lastMap);
          return true;
        }
        return false;
      });
      if (MOBILE_MAP_INSPECT_MQ.matches && state.openState) {
        requestAnimationFrame(() => reframeMobileStateWithTitle());
      }
    } finally {
      mapInspectDetailsAnimating = false;
    }
    return;
  }
  setMapInspectWithoutRefit(false);
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

// The per-state aggregation (coalition tally + records), shaped once and consumed by
// BOTH the panel summary and the bento tiles. Pure extraction of stateSummaryHTML's
// former inline computation — fragments are byte-identical. Returns null when the
// state has no result rows (caller shows the tap hint / empty state).
function stateStats(name, tier = state.tier) {
  const d = state.data[tier];
  if (!d) return null;
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
    const code = displayCode(row.seat, tier) || row.seat.code;
    return [code, row.seat.name].filter(Boolean).join(" · ");
  };
  const marginHTML = (row) => {
    const majority = fmtInt(row.card.majority);
    if (!majority) return "";
    const pct = Number.isFinite(row.card.majorityPct) ? ` <span class="muted">(${fmtPct(row.card.majorityPct)})</span>` : "";
    return `<span class="mono">${majority}</span>${pct}`;
  };
  for (const s of seats) {
    const card = formatResultCard(seatResultOf(s, tier));
    if (!card) continue;
    rows.push({ seat: s, card });
    const bloc = currentBlocFor(currentRepresentationFor(s, tier));
    if (bloc) tally[bloc] = (tally[bloc] || 0) + 1;
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
  if (!ents.length) return null;
  const bar = ents.map(([c, n]) => '<span style="flex:' + n + ';background:' + partyColor(c) + '"></span>').join("");
  const key = ents.map(([c, n]) => '<span class="sw" style="background:' + partyColor(c) + '"></span>' + esc(c) + " <b>" + n + "</b>").join("");

  const stat = (labelKey, valueHTML, note) => (
    '<div class="state-stat">' +
      '<span class="state-stat-label">' + esc(t(labelKey)) + "</span>" +
      '<span class="state-stat-value">' + valueHTML + "</span>" +
      (note ? '<span class="state-stat-note">' + esc(note) + "</span>" : "") +
    "</div>"
  );
  let leaderStat = "", turnoutStat = "", closestStat = "", largestStat = "", votesStat = "", candidatesStat = "";
  const leader = ents[0];
  if (leader) {
    const [coalition, count] = leader;
    const pct = seats.length ? Math.round((count / seats.length) * 100) : 0;
    leaderStat = stat(
      "state_leading_bloc",
      `<span class="state-bloc"><span class="sw" style="background:${partyColor(coalition)}"></span>${esc(coalition)}</span>`,
      `${count}/${seats.length} · ${t("state_seat_share", { pct })}`
    );
  }
  if (tN) {
    const turnouts = rows.map((row) => row.card.turnout).filter(Number.isFinite);
    const min = Math.min(...turnouts), max = Math.max(...turnouts);
    turnoutStat = stat(
      "state_avg_turnout",
      `<span class="mono">${fmtPct(tSum / tN)}</span>`,
      t("state_turnout_range", { min: fmtPct(min), max: fmtPct(max) })
    );
  }
  const withMajority = rows.filter((row) => Number.isFinite(row.card.majority));
  const closest = withMajority.reduce((best, row) => !best || row.card.majority < best.card.majority ? row : best, null);
  const largest = withMajority.reduce((best, row) => !best || row.card.majority > best.card.majority ? row : best, null);
  if (closest) closestStat = stat("state_closest_race", marginHTML(closest), seatLabel(closest));
  if (largest && largest !== closest) largestStat = stat("state_largest_majority", marginHTML(largest), seatLabel(largest));
  if (voteN) votesStat = stat("state_winner_votes", `<span class="mono">${fmtInt(voteSum)}</span>`, t("state_winner_count", { n: voteN }));
  if (candidateN) candidatesStat = stat("state_avg_candidates", `<span class="mono">${(candidateSum / candidateN).toFixed(1)}</span>`, t("state_per_seat"));
  return { seats, ents, bar, key, leaderStat, turnoutStat, closestStat, largestStat, votesStat, candidatesStat };
}

// Compact coalition share bar for mobile state landing — same idea as #nat-glance
// on the home card (coloured line + bloc counts). Uses current YB affiliations.
function stateMakeupGlanceHTML(name) {
  const st = stateStats(name);
  if (!st || !st.ents.length) return "";
  const label = state.prnMode ? t("prn_incumbent") : t("state_makeup");
  const summary = st.ents.map(([c, n]) => `${c} ${n}`).join(" · ");
  const bar = st.ents.map(([c, n]) =>
    `<span style="flex:${n};background:${partyColor(c)}" title="${esc(c)} ${n}"></span>`
  ).join("");
  const key = st.ents.map(([c, n]) =>
    `<span class="sk"><span class="sw" style="background:${partyColor(c)}"></span>${esc(c)} <b>${n}</b></span>`
  ).join("");
  return `<section class="state-makeup-glance" tabindex="0" aria-label="${esc(label)}. ${esc(summary)}">
    <div class="state-makeup-glance-h muted">${esc(label)} · ${st.seats.length}</div>
    <div class="sharebar state-makeup-bar">${bar}</div>
    <div class="sharebar-key">${key}</div>
  </section>`;
}

function stateSeatCountText(tier, n) {
  const key = "state_count_" + (tier === "parlimen" ? "parlimen" : "dun") + (n === 1 ? "_one" : "");
  return t(key, { n });
}

function stateGovBrief(name) {
  const st = state.stateCtx && state.stateCtx.states && state.stateCtx.states[name];
  const g = st && st.gov;
  if (!g) return null;
  const title = g.title === "MB" ? "Menteri Besar" : g.title === "KM" ? "Ketua Menteri" : g.title;
  return { title, name: g.name, coalition: g.coalition };
}

function prnContestTotal(p = state.prn16) {
  return Object.values((p && p.contested) || {}).reduce((a, b) => a + b, 0);
}

function stateBriefHTML(name, st) {
  const e = prnActiveForState(name);
  if (e) {
    const cd = prnCountdownLabel(e);
    const total = prnContestTotal();
    const chips = [
      `<span class="state-brief-chip"><b>${esc(t("state_status_polling", { d: fmtDayMonth(e.polling_day) }))}</b></span>`,
      cd ? `<span class="state-brief-chip">${esc(t("state_status_countdown", { v: cd }))}</span>` : "",
      total ? `<span class="state-brief-chip">${esc(t("prn_candidates_filed", { n: total }))}</span>` : "",
      `<span class="state-brief-chip">${esc(t("state_status_majority", { n: e.majority }))}</span>`,
    ].filter(Boolean).join("");
    return `<section class="state-brief is-election">
      <div>
        <div class="state-brief-kicker"><span class="live-dot" aria-hidden="true"></span>${esc(t("prn_kicker"))}</div>
        <h3>${esc(e.name)}</h3>
        <p>${esc(t("state_brief_election_body"))}</p>
      </div>
      <div class="state-brief-chips">${chips}</div>
      <button id="prn-open" class="prn-open-btn" type="button">${esc(t("prn_open"))} →</button>
    </section>`;
  }

  const leader = st.ents[0];
  const gov = stateGovBrief(name);
  const clock = stateClockText(name);
  const leadChip = leader
    ? `<span class="state-brief-chip"><span class="sw" style="background:${partyColor(leader[0])}"></span><b>${esc(leader[0])}</b> ${leader[1]}/${st.seats.length}</span>`
    : "";
  const chips = [
    `<span class="state-brief-chip">${esc(stateSeatCountText(state.tier, st.seats.length))}</span>`,
    leadChip,
    gov ? `<span class="state-brief-chip">${esc(t("state_status_gov", { title: gov.title, name: gov.name }))}</span>` : "",
    clock ? `<span class="state-brief-chip">${esc(t("state_status_clock", { v: clock }))}</span>` : "",
  ].filter(Boolean).join("");
  const body = leader
    ? t("state_brief_lead", { coalition: leader[0], count: leader[1], total: st.seats.length }) + " " + t("state_brief_select")
    : t("state_brief_select");
  return `<section class="state-brief">
    <div>
      <div class="state-brief-kicker">${esc(t("state_brief_kicker"))}</div>
      <h3>${esc(name)}</h3>
      <p>${esc(body)}</p>
    </div>
    <div class="state-brief-chips">${chips}</div>
  </section>`;
}

function stateSummaryHTML(name) {
  if (state.prnMode && prnActiveForState(name)) return prnSummaryHTML();
  const st = stateStats(name);
  if (!st) return '<p class="state-tap-hint">' + esc(t("tap_district")) + "</p>";
  const { bar, key } = st;
  const stats = [st.leaderStat, st.turnoutStat, st.closestStat, st.largestStat, st.votesStat, st.candidatesStat].filter(Boolean);

  // desktop/landscape: the mobile inspect tray isn't shown, so give the state card
  // its own district finder (dropdown + locate) at the TOP — it's the primary action
  // (you opened the state to drill into a district) and must be visible without
  // scrolling past the stats + economy. On mobile the tray already has one.
  const desktopFinder = !MOBILE_MAP_INSPECT_MQ.matches
    ? `<div class="state-section state-find-section">
       <div class="state-info-h muted">${esc(t("find_district"))}</div>
       <div class="state-district-find state-district-find-top">${districtSwitchRowHTML(state.selected || "", false)}</div>`
       + `</div>`
    : "";
  return (
    stateBriefHTML(name, st) +
    desktopFinder +
    '<div class="state-section"><div class="state-info-h muted">' + esc(t("state_makeup")) + "</div>" +
    '<div class="sharebar">' + bar + "</div>" +
    '<div class="sharebar-key">' + key + "</div>" +
    (stats.length ? '<div class="state-stats">' + stats.join("") + "</div>" : "") +
    "</div>" +
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
function stateClockText(name) {
  const ctx = state.stateCtx;
  const st = ctx && ctx.states && ctx.states[name];
  const clock = st && st.clock;
  if (!clock || prnActiveForState(name)) return "";
  if (clock.federal) {
    return `${t("ctx_federal")} · ${t("ctx_due_by", { d: fmtDMY(addDays(ctx.parlimen.dissolve_by, 60)) })}`;
  }
  if (clock.next) {
    return `${fmtDMY(clock.next)} · ${t("ctx_in_days", { n: daysUntil(clock.next) })}`;
  }
  if (clock.dissolve_by) {
    const due = addDays(clock.dissolve_by, 60);   // dissolution deadline + 60-day window
    let v = t("ctx_due_by", { d: fmtDMY(due) });
    if (clock.expected) v += ` · ${t("ctx_expected", { y: clock.expected })}`;
    v += ` · ${t("ctx_in_days", { n: daysUntil(due) })}`;
    return v;
  }
  return "";
}
// gov + election-clock rows (dt/dd fragments) — shared by the panel context block
// and the bento government tile. Pure extraction; fragments unchanged.
// the "next election" dt/dd row (or "" when a live election supersedes the clock) —
// shared by the panel context block, stateGovRows, and the bento government tile
function stateClockRow(name) {
  const v = stateClockText(name);
  return v ? `<dt>${esc(t("ctx_next_election"))}</dt><dd>${esc(v)}</dd>` : "";
}

function stateGovRows(name) {
  const ctx = state.stateCtx;
  const st = ctx && ctx.states && ctx.states[name];
  if (!st) return [];
  const rows = [];
  if (st.gov) {
    const g = st.gov;
    const title = g.title === "MB" ? "Menteri Besar" : g.title === "KM" ? "Ketua Menteri" : g.title;
    const care = g.caretaker ? ` <span class="muted">(${esc(t("ctx_caretaker"))})</span>` : "";
    rows.push(`<dt>${esc(title)}</dt><dd>${esc(g.name)} · ${esc(g.party)} (${esc(g.coalition)})${care}</dd>`);
  }
  const clock = stateClockRow(name);
  if (clock) rows.push(clock);
  return rows;
}

// economy report-card rows + source line — shared by the panel and the bento econ
// tile. Returns { rows, src }. Pure extraction; fragments unchanged.
function stateEconRows(name) {
  const econ = state.stateEcon;
  const ec = econ && econ.states && econ.states[name];
  if (!ec) return { rows: [], src: "" };
  const rows = [];
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
  return { rows, src: `<p class="src-line muted">${esc(t("econ_src"))}</p>` };
}

function stateContextHTML(name) {
  // original gate preserved: no context entry for the state → no block at all
  // (even if econ data alone exists)
  const ctx = state.stateCtx;
  if (!ctx || !ctx.states || !ctx.states[name]) return "";
  const rows = stateGovRows(name);
  const econ = stateEconRows(name);
  rows.push(...econ.rows);
  return rows.length ? `<dl class="rows state-ctx">${rows.join("")}</dl>${econ.src}` : "";
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
// polling-night tally: declared wins when any exist; otherwise provisional leads
// (election night spends hours with status=leading only — empty bar was useless).
function prnLiveTallyHTML(opts = {}) {
  const { e, live, declared, leading, won, lead, majority, total } = prnLiveStats();
  if (!e || !live) return "";
  const provisional = declared === 0;
  const counts = provisional ? lead : won;
  const order = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const bar = order.map(([coal, n]) => {
    const c = prnCoalColor(coal);
    return `<span style="width:${(100 * n / total).toFixed(2)}%;background:${c.bg}"></span>`;
  }).join("");
  const key = order.map(([coal, n]) => {
    const c = prnCoalColor(coal);
    const extra = !provisional && lead[coal] ? ` <span class="muted">+${lead[coal]}</span>` : "";
    return `<span class="state-bloc"><span class="sw" style="background:${c.bg}"></span>${esc(coal)} <b>${n}</b>${extra}</span>`;
  }).join("");
  const updated = live.updated
    ? new Date(live.updated).toLocaleTimeString(lang === "ms" ? "ms-MY" : "en-MY", { hour: "2-digit", minute: "2-digit" })
    : "";
  const title = provisional
    ? t("prn_live_leading_count", { n: leading, total })
    : t("prn_live_tally", { n: declared, total });
  const note = provisional
    ? t("prn_live_provisional")
    : t("prn_majority", { n: majority });
  const headCls = opts.compact ? "prn-live-tally-h muted" : "state-info-h muted";
  const headStyle = opts.compact ? "" : ' style="margin-top:14px"';
  return `<div class="${headCls}"${headStyle}>${esc(title)}</div>
    <div class="sharebar prn-live-bar">${bar}</div>
    <div class="sharebar-key">${key || `<span class="muted">${esc(t("prn_live_waiting"))}</span>`}</div>
    <p class="prn-majority muted">${esc(note)}${updated ? ` · ${esc(t("prn_live_updated", { t: updated }))}` : ""}${live.source ? ` · ${esc(live.source)}` : ""}</p>`;
}

// the PRN summary card (replaces the state make-up while the election view is on)
function prnSummaryHTML() {
  const e = liveElection();
  const p = state.prn16;
  if (!e || !p) return "";
  const liveNow = state.prnLive && (state.prnLive.phase === "live" || state.prnLive.phase === "final");
  const cd = liveNow ? null : prnCountdownLabel(e);
  const total = prnContestTotal(p);
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
    // polling night: the tally leads, then the full 56-seat live board (same
    // renderer as the desktop bento) so phones see every race, not just the map
    return `<div class="prn-summary">
      ${head}
      ${prnLiveTallyHTML()}
      <div id="mobile-live-board" class="mobile-live-board">${bentoLiveTableHTML(state.openState)}</div>
      <button id="prn-all-candidates" class="prn-pledges-btn" type="button">👥 ${esc(t("prn_all_cands", { n: total }))} →</button>
      <p class="state-tap-hint muted">${esc(t("prn_tap_hint"))}</p>
      <p class="src-line muted">${esc(t("prn_source"))}</p>
      <button id="prn-close" class="prn-close-btn" type="button">${esc(t("prn_close"))}</button>
    </div>`;
  }
  const prnFinder = !MOBILE_MAP_INSPECT_MQ.matches
    ? `<div class="state-section state-find-section"><div class="state-info-h muted">${esc(t("find_district"))}</div><div class="state-district-find state-district-find-top">${districtSwitchRowHTML(state.selected || "", false)}</div></div>`
    : "";
  return `<div class="prn-summary">
    <section class="state-brief is-election prn-brief">
      <div>
        <div class="state-brief-kicker"><span class="live-dot" aria-hidden="true"></span>${esc(t("prn_kicker"))}</div>
        <h3>${esc(e.name)}</h3>
        <p>${esc(t("prn_panel_compare"))}</p>
      </div>
      <div class="state-brief-chips">
        <span class="state-brief-chip"><b>${esc(t("state_status_polling", { d: fmtDayMonth(e.polling_day) }))}</b></span>
        ${cd ? `<span class="state-brief-chip">${esc(t("state_status_countdown", { v: cd }))}</span>` : ""}
        <span class="state-brief-chip">${esc(t("prn_candidates_filed", { n: total }))}</span>
        <span class="state-brief-chip">${esc(t("state_status_majority", { n: e.majority }))}</span>
      </div>
    </section>
    ${prnFinder}
    <div class="prn-panel-grid">
      <section class="prn-panel-card">
        <div class="state-info-h muted">${esc(t("prn_bento_key_dates"))}</div>
        <dl class="rows prn-dates">${rows}</dl>
      </section>
      <section class="prn-panel-card">
        <div class="state-info-h muted">${esc(t("prn_contested"))} · ${total}</div>
        <div class="sharebar">${bar}</div>
        <div class="sharebar-key">${key}</div>
        <p class="prn-majority muted">${esc(t("prn_majority", { n: e.majority }))}</p>
      </section>
    </div>
    ${newsStripHTML()}
    ${prnFinder ? "" : `<p class="state-tap-hint muted">${esc(t("prn_tap_hint"))}</p>`}
    <button id="prn-all-candidates" class="prn-pledges-btn" type="button">👥 ${esc(t("prn_all_cands", { n: total }))} →</button>
    <a class="prn-check" href="${esc(e.check_voter_url)}" target="_blank" rel="noopener">${esc(t("prn_check"))}</a>
    <p class="src-line muted">${esc(t("prn_source"))}</p>
    <button id="prn-close" class="prn-close-btn" type="button">${esc(t("prn_close"))}</button>
  </div>`;
}
function prnRaceFactsHTML(seat, entry) {
  const facts = [];
  if (entry.electorate) facts.push([t("prn_electorate"), entry.electorate.toLocaleString()]);
  facts.push([t("prn_candidates"), entry.candidates.length]);
  if (seat.parlimen) facts.push([t("parlimen_label"), parlimenContext(seat)]);
  const comp = competitiveness(entry);
  if (comp) facts.push([t("bento_last_result"), t("prn_comp_" + comp.key)]);
  return `<div class="prn-race-facts">${facts.map(([k, v]) =>
    `<div class="prn-race-fact"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}</div>`;
}
// per-seat candidate card (replaces the GE15-fallback seat card inside PRN view)
function prnSeatCardHTML(seat, entry) {
  const e = liveElection();
  const seatNews = state.prnNews && state.prnNews[seat.code];
  const hasNews = !!(seatNews && entry.candidates.some((c) => seatNews[c.name] && seatNews[c.name].length));
  return `<div class="seat-head prn-seat-head">
      <div class="kicker">🗳️ ${esc(e.name)} · ${esc(entry.ncode)}</div>
      <h2>${esc(entry.name)}</h2>
      ${seat.parlimen ? `<div class="where">${esc(t("parlimen_label"))} <b>${esc(parlimenContext(seat))}</b></div>` : ""}
    </div>
    ${seatDetailActionsHTML()}
    <div class="state-info-h muted">${esc(t("prn_race_facts"))}</div>
    ${prnRaceFactsHTML(seat, entry)}
    ${incumbentBlockHTML(entry, seat.code)}
    <div class="state-info-h muted">${esc(t("prn_candidate_compare"))} · ${entry.candidates.length}</div>
    <div class="prn-cands prn-cands-compare">${prnCandidateCardsHTML(entry, seat.code, true)}</div>
    ${hasNews ? `<p class="src-line muted">${esc(t("prn_news_note"))}</p>` : ""}
    ${lastResultHTML(entry)}
    ${state.johorPledges && prnPledgesHTML(entry) ? `<button type="button" class="prn-pledges-btn" data-open-pledges>📜 ${esc(t("prn_pledges"))} →</button>` : ""}
    <p class="callout prn-note">${esc(t("prn_results_note"))}</p>
    <p class="src-line muted">${esc(t("prn_source"))}</p>`;
}

// coalition manifesto pledges for the coalitions contesting THIS seat — attributed
// to the coalition (not the individual candidate), each with a link to the manifesto.
// one coalition's platform block — a real manifesto (title + note + pledges + source)
// or an honest "not released yet" state for a bloc that is contesting but hasn't
// published. Returns "" for a coalition we simply have no entry for.
function pledgeBlockHTML(coal, m, opts = {}) {
  if (!m) return "";
  const col = prnCoalColor(coal);
  const head = `<div class="prn-pledge-h"><span class="pill" style="${pillStyle(col.bg, col.fg)}">${esc(coal)}</span>${m.title ? ` <span class="muted">${esc(m.title)}</span>` : ""}</div>`;
  const src = m.source ? `<a class="src-line muted prn-pledge-src" href="${esc(m.source)}" target="_blank" rel="noopener">${esc(t("prn_pledge_src"))}</a>` : "";
  if (m.pending) {
    return `<div class="prn-pledge-coal is-pending">${head}
      <p class="prn-pledge-pending muted">${esc(t("prn_pledge_pending", { d: m.as_of || "" }))}</p></div>`;
  }
  if (!m.pledges || !m.pledges.length) return "";
  const note = m.note ? `<p class="prn-pledge-note muted">${esc(m.note)}</p>` : "";
  const list = m.pledges.slice(0, opts.max || m.pledges.length);
  return `<div class="prn-pledge-coal">${head}${note}
    <ul class="prn-pledge-list">${list.map((pl) => `<li>${esc(pl)}</li>`).join("")}</ul>${src}</div>`;
}

function prnPledgesHTML(entry) {
  const p = state.johorPledges;
  if (!p || !p.coalitions || !entry) return "";
  // only the coalitions actually contesting THIS seat, in ballot order
  const coals = [...new Set(entry.candidates.map((c) => c.coalition))];
  const blocks = coals.map((coal) => pledgeBlockHTML(coal, p.coalitions[coal])).filter(Boolean).join("");
  if (!blocks) return "";
  return `<div class="state-info-h muted" style="margin-top:14px">${esc(t("prn_pledges"))}</div>
    <div class="prn-pledges">${blocks}</div>`;
}
// user turned the election view off for this visit — don't auto re-enter it on every
// seat click within the state; reset when the state is left entirely (backToControls)
let prnOptOut = false;
// Bumped when the user navigates away mid-open so a slow setTier() can't yank them
// back into Johor PRN after they tapped Sarawak / another state.
let prnOpenGen = 0;
// default the election view ON only while it matters: up to polling day, or while
// results are still flowing on the night
function prnUpcomingOrLive(e) {
  const liveNow = state.prnLive && (state.prnLive.phase === "live" || state.prnLive.phase === "final");
  return liveNow || prnDaysToPolling(e) >= 0;
}
// the election-view flag + chrome WITHOUT the state-open choreography — used by
// openPrnMode (badge / deep link) and by the bento's PRN toggle chip
function enterPrnMode() {
  const e = liveElection();
  if (!e || state.prnMode) return;
  state.prnMode = true;
  document.body.classList.add("prn-mode");
  paint();
  syncLiveBadge();
  refreshPrnLive();
}
async function openPrnMode() {
  const e = liveElection();
  // bail only when the election view is already showing ITS state — a leaked
  // prn flag with another state open must not dead-end the click
  if (!e || (state.prnMode && state.openState === e.state)) return;
  const gen = ++prnOpenGen;
  closeNewsPage({ silent: true });
  const preSel = state.selected;   // openStateCard clears the selection — keep it for the bento spotlight
  // Hide map while swapping Parliament → DUN so the national DUN recolour never flashes
  document.body.classList.add("tier-switching");
  try {
    if (state.tier !== e.tier) {
      // Quiet path — never setTier() here (that deselects and shows full-country DUN)
      const ok = await ensureTierQuiet(e.tier);
      if (!ok) return;
    }
    // Race guard: user opened another state (or cancelled) while we awaited render
    if (gen !== prnOpenGen) return;
    enterPrnMode();
    openStateCard(e.state);   // isolation choreography + (on wide screens) the bento
    if (gen !== prnOpenGen) return;
    if (BENTO_MQ.matches && preSel && state.data.dun && state.data.dun.byCode.has(preSel)) {
      bentoSeat = preSel;
      updateBentoSpotlight();
    }
    writeHash();
  } finally {
    // Reveal after isolation has applied so first paint is Johor DUN, not Malaysia DUN
    requestAnimationFrame(() => {
      document.body.classList.remove("tier-switching");
      try { syncMapToCard(); } catch (_) {}
    });
  }
}
function closePrnMode(options = {}) {
  if (!state.prnMode) return;
  state.prnMode = false;
  clearTimeout(prnLiveTimer);
  document.body.classList.remove("prn-mode");
  if (options.silent) {
    // silent callers (backToControls, tier switch) tear the whole state view down
    hideStateBento();
    return;
  }
  if (state.openState) {
    STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
    renderMapInspectTray();
  }
  // wide screen with the state still open → drop to the generic state dashboard
  // (the PRN toggle just went OFF); otherwise the bento goes away entirely
  if (state.openState && BENTO_MQ.matches) renderStateBento();
  else hideStateBento();
  paint();
  syncLiveBadge();
  writeHash();
}
// polling-night data. While PRN mode is open we re-poll continuously so a tab left
// open through campaign → live flips automatically. Interval tightens to ~15s once
// phase is live/final (election-night tempo); ~60s during campaign.
let prnLiveTimer = null;
let prnLiveSeatSnap = {};   // code → last-seen status (for map flash + toasts)
let bentoLiveFilter = "all"; // live seat table filter

/** Apply All / Undeclared / BN / PH / … filter and re-render wherever the board lives. */
function setLiveSeatFilter(raw) {
  const next = String(raw || "all").trim() || "all";
  bentoLiveFilter = next;
  // Desktop bento dashboard
  if (document.body.classList.contains("bento-on")) {
    renderStateBento();
    return;
  }
  // Mobile map-inspect tray owns the night board
  if (state.mapInspect && MOBILE_MAP_INSPECT_MQ.matches && state.prnMode) {
    renderMapInspectTray();
    return;
  }
  // Panel summary path (state-summary with #mobile-live-board)
  if (state.prnMode && state.openState && PANEL.classList.contains("state-summary")) {
    STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
    return;
  }
  const board = document.getElementById("mobile-live-board");
  if (board && state.openState) board.innerHTML = bentoLiveTableHTML(state.openState);
}

function liveSeatMatchesFilter(lr, st, filter) {
  const f = (filter || "all").toUpperCase();
  if (f === "ALL" || filter === "all") return true;
  // Undeclared = not yet won/official (includes leading + awaiting)
  if (filter === "open") {
    const status = (lr && lr.status) || "";
    return status !== "won" && status !== "official";
  }
  const coal = String((lr && (lr.coalition || lr.party)) || "").toUpperCase();
  const party = String((lr && lr.party) || "").toUpperCase();
  // Chip id may be a coalition (BN/PH/PN) or a minor ticket (BERSAMA, MUDA-PSM)
  return coal === f || party === f;
}
let prnFlashCodes = [];      // seats to pulse on next map paint

function prnLiveIsHot(live = state.prnLive) {
  return !!(live && (live.phase === "live" || live.phase === "final"));
}
function prnLiveStats() {
  const e = liveElection() || (state.prn16 && state.prn16.election) || null;
  const live = state.prnLive;
  const seats = (live && live.seats) || {};
  let declared = 0, leading = 0;
  const won = {}, lead = {};
  for (const r of Object.values(seats)) {
    const coal = r.coalition || r.party;
    if (r.status === "won" || r.status === "official") {
      declared++;
      if (coal) won[coal] = (won[coal] || 0) + 1;
    } else if (r.status === "leading") {
      leading++;
      if (coal) lead[coal] = (lead[coal] || 0) + 1;
    }
  }
  // poller may not set .declared — always derive from seats
  if (live && live.declared == null) live.declared = declared;
  return {
    e, live, seats, declared, leading, won, lead,
    majority: (e && e.majority) || 29,
    total: (e && e.total_seats) || 56,
  };
}
function prnLiveStatusMeta(lr) {
  if (!lr || !lr.status) return { key: "awaiting", label: t("prn_st_awaiting") };
  if (lr.status === "official") return { key: "official", label: t("prn_st_official") };
  if (lr.status === "won") return { key: "called", label: t("prn_st_called") };
  if (lr.status === "leading") return { key: "leading", label: t("prn_st_leading") };
  return { key: "awaiting", label: t("prn_st_awaiting") };
}
function detectPrnLiveFlashes(prevSnap, live) {
  const seats = (live && live.seats) || {};
  const flashed = [];
  for (const [code, r] of Object.entries(seats)) {
    const st = r.status || "";
    if (!st || st === "counting") continue;
    const prev = prevSnap[code];
    if (prev !== st && (st === "leading" || st === "won" || st === "official")) {
      flashed.push({ code, status: st, coal: r.coalition || r.party || "", name: r.name || "" });
    }
  }
  return flashed;
}
function snapshotPrnLiveStatuses(live) {
  const snap = {};
  for (const [code, r] of Object.entries((live && live.seats) || {})) {
    snap[code] = r.status || "";
  }
  return snap;
}

async function refreshPrnLive() {
  clearTimeout(prnLiveTimer);
  // No live election → never poll the live endpoint. Without this a concluded
  // election still fetched stale /api/live/johor data and fired seat-call toasts
  // ("N.xx · Leading · BN") on the normal map.
  if (!liveElection()) { state.prnLive = null; prnFlashCodes = []; return; }
  let live = null;
  const localHost = ["", "localhost", "127.0.0.1", "::1"].includes(location.hostname);
  const urls = localHost ? ["data/live-johor.json", "/api/live/johor"] : ["/api/live/johor", "data/live-johor.json"];
  for (const url of urls) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (r.ok) {
        live = await r.json();
        break;
      }
    } catch (_) {}
  }
  const prevPhase = state.prnLive && state.prnLive.phase;
  const prevUpdated = state.prnLive && state.prnLive.updated;
  if (live && live.phase) {
    const flashes = detectPrnLiveFlashes(prnLiveSeatSnap, live);
    prnLiveSeatSnap = snapshotPrnLiveStatuses(live);
    state.prnLive = live;
    const isLive = prnLiveIsHot(live);
    const changed = isLive && (live.phase !== prevPhase || live.updated !== prevUpdated);
    if (flashes.length) {
      prnFlashCodes = flashes.map((f) => f.code);
      // toast the most recent few flips (avoid spam if many seats land at once)
      const f = flashes[flashes.length - 1];
      const meta = prnLiveStatusMeta({ status: f.status });
      showToast("prn_live_flash", {
        code: (f.code || "").replace(/^1_/, ""),
        status: meta.label,
        coal: f.coal || "—",
      });
    }
    // re-paint on phase/updated ticks OR seat status flips — keeps tonight's count
    // bar in the spotlight filled as Rick/Sinar publish vote numbers
    if (state.prnMode && (changed || flashes.length || (isLive && live.updated !== prevUpdated))) {
      paint();
      renderPrnSummaryIfOpen();
      if (document.body.classList.contains("bento-on")) renderStateBento();
      setTimeout(renderPrnSummaryIfOpen, 800);
    }
  }
  const interval = prnLiveIsHot(state.prnLive) ? 15000 : 60000;
  if (state.prnMode) prnLiveTimer = setTimeout(refreshPrnLive, interval);
}
function renderPrnSummaryIfOpen() {
  if (!(state.prnMode && state.openState)) return;
  if (PANEL.classList.contains("state-summary")) {
    STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
  }
  // Mobile map-inspect tray owns the night landing — keep it in sync with live ticks
  if (state.mapInspect && MOBILE_MAP_INSPECT_MQ.matches) renderMapInspectTray();
  else {
    const board = document.getElementById("mobile-live-board");
    if (board) board.innerHTML = bentoLiveTableHTML(state.openState);
  }
}

// ============================================================================
// Wide-screen PRN "bento" dashboard — a spatial dashboard for the live Johor
// election, shown only on big landscape screens. Purely additive: on narrow
// screens (or outside PRN mode) it stays hidden and the normal map+panel flow
// runs untouched. Self-rendered Johor map tile → no reparenting of #map.
// ============================================================================
const BENTO = document.getElementById("state-bento");
const BENTO_MQ = matchMedia("(min-width: 1000px)");   // landscape tablets & up (kept in sync with styles.css)
let bentoSeat = null;   // seat code spotlighted in the bento
let bentoTier = null;   // explore-card map layer override (null → follow the app tier)
function bentoMapTier() { return bentoElectionMode() ? "dun" : (bentoTier || state.tier); }

// the bento shows election tiles when the open state's live election is toggled on
// (state.prnMode IS the toggle — reusing it keeps the hash /prn token, polling-night
// refresh and every exit path working unchanged)
function bentoElectionMode() {
  return !!(state.prnMode && state.openState && prnActiveForState(state.openState));
}

function prnDaysToPolling(e) {
  return Math.ceil((new Date(e.polling_day + "T00:00:00+08:00").getTime() - Date.now()) / 86400000);
}

// seat fill for the bento map tile. Election mode: live-night colour if we have it,
// else the 2022 incumbent's coalition. Generic mode: the seat's own result coalition
// (NOT seatValueColor — that mutates main-map path opacity as a side effect).
function bentoSeatColor(seat) {
  if (bentoElectionMode()) {
    const lr = state.prnLive && state.prnLive.seats && state.prnLive.seats[seat.code];
    if (lr && (lr.coalition || lr.party)) return prnCoalColor(lr.coalition || lr.party).bg;
    const r = johorDunResult(seat);
    return r ? prnCoalColor(r.coalition).bg : "#39404c";
  }
  const bloc = mapBlocFor(seat, bentoMapTier());
  return bloc ? partyColor(bloc) : "#39404c";
}

// a compact, self-contained state choropleth built from the seat paths of the open
// tier — clicking a seat spotlights it in the bento without touching the national map
function stateMapTileSVG(name) {
  const data = state.data[bentoMapTier()];
  if (!data || !name) return "";
  const seats = data.seats.filter((s) => s.state === name && s.bbox);
  if (!seats.length) return "";
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const s of seats) {
    const b = s.bbox;
    x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
    x1 = Math.max(x1, b.x + b.w); y1 = Math.max(y1, b.y + b.h);
  }
  const px = (x1 - x0) * 0.03, py = (y1 - y0) * 0.03;
  // padded bounding box of the state's own seats. The FINAL viewBox is aspect-matched
  // to the rendered tile in fitBentoMapTiles() so small / odd-shaped federal territories
  // (W.P. Kuala Lumpur, Labuan, Putrajaya) frame consistently instead of letterboxing.
  // The krackedmaps projection is FROZEN — only this framing viewBox changes.
  const bx = x0 - px, by = y0 - py, bw = (x1 - x0) + 2 * px, bh = (y1 - y0) + 2 * py;
  const vb = `${bx.toFixed(2)} ${by.toFixed(2)} ${bw.toFixed(2)} ${bh.toFixed(2)}`;
  const flash = new Set(prnFlashCodes || []);
  const paths = seats.map((s) => {
    const lr = bentoElectionMode() && state.prnLive && state.prnLive.seats
      ? state.prnLive.seats[s.code] : null;
    const st = prnLiveStatusMeta(lr).key;
    const cls = [
      "bento-seat",
      s.code === bentoSeat ? "sel" : "",
      bentoElectionMode() ? `st-${st}` : "",
      flash.has(s.code) ? "just-called" : "",
    ].filter(Boolean).join(" ");
    return `<path d="${s.d}" data-code="${esc(s.code)}" class="${cls}" style="fill:${bentoSeatColor(s)}"><title>${esc(s.name)}</title></path>`;
  }).join("");
  // clear one-shot flash list after paint (animation CSS still plays)
  if (flash.size) setTimeout(() => { prnFlashCodes = []; }, 50);
  return `<svg viewBox="${vb}" data-bx="${bx.toFixed(2)}" data-by="${by.toFixed(2)}" data-bw="${bw.toFixed(2)}" data-bh="${bh.toFixed(2)}" preserveAspectRatio="xMidYMid meet" class="bento-map-svg" role="img" aria-label="${esc(name)}">${paths}</svg>`;
}

// ---- election-night bento: live strip + 56-seat table ----
function bentoLiveStripHTML() {
  if (!bentoElectionMode()) return "";
  const { e, live, declared, leading, won, lead, majority, total } = prnLiveStats();
  if (!e) return "";
  // per-coalition "who's ahead" bar under the metrics: won (bold) + leading (+N).
  // Before declarations start it shows pure leading counts, so it's live all night.
  const provisional = declared === 0;
  const counts = provisional ? lead : won;
  const barOrder = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const aheadBar = barOrder.length
    ? `<div class="bento-live-ahead">
        <div class="sharebar prn-live-bar">${barOrder.map(([c, n]) =>
          `<span style="width:${(100 * n / total).toFixed(2)}%;background:${prnCoalColor(c).bg}"></span>`).join("")}</div>
        <div class="sharebar-key">${barOrder.map(([c, n]) => {
          const extra = !provisional && lead[c] ? ` <span class="muted">+${lead[c]}</span>` : "";
          return `<span class="state-bloc"><span class="sw" style="background:${prnCoalColor(c).bg}"></span>${esc(c)} <b>${n}</b>${extra}</span>`;
        }).join("")}</div>
      </div>`
    : "";
  const hot = prnLiveIsHot(live);
  const days = prnDaysToPolling(e);
  const today = days <= 0;
  const phaseChip = hot
    ? `<span class="live-chip">${esc(t(live.phase === "final" ? "prn_phase_final" : "prn_phase_live"))}</span>`
    : "";
  const dayLine = today
    ? esc(t("prn_live_polling_today"))
    : (days === 1 ? esc(t("prn_tomorrow")) : esc(t("prn_days", { n: Math.max(0, days) })));
  const updated = live && live.updated
    ? new Date(live.updated).toLocaleTimeString(lang === "ms" ? "ms-MY" : "en-MY", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "";
  const legend = ["awaiting", "leading", "called", "official"].map((k) => {
    const lab = t(k === "awaiting" ? "prn_st_awaiting" : k === "leading" ? "prn_st_leading" : k === "called" ? "prn_st_called" : "prn_st_official");
    return `<span class="bento-live-leg st-${k}"><i></i>${esc(lab)}</span>`;
  }).join("");
  return `<div class="bento-live-strip${hot ? " is-hot" : ""}" role="status" aria-live="polite">
    <div class="bento-live-strip-h">
      <span class="live-dot" aria-hidden="true"></span>
      <div class="bento-live-strip-title">
        <b>${esc(t("prn_live_strip_title"))}</b>
        <span class="muted">${dayLine} · ${esc(fmtDayMonth(e.polling_day))}</span>
      </div>
      ${phaseChip}
    </div>
    <div class="bento-live-metrics">
      <div class="bento-live-metric">
        <span class="muted">${esc(t("prn_live_declared_short"))}</span>
        <b>${declared}<small>/${total}</small></b>
      </div>
      <div class="bento-live-metric">
        <span class="muted">${esc(t("prn_live_leading_short"))}</span>
        <b>${leading}</b>
      </div>
      <div class="bento-live-metric">
        <span class="muted">${esc(t("prn_live_majority_short"))}</span>
        <b>${majority}</b>
      </div>
    </div>
    ${aheadBar}
    <div class="bento-live-meta">
      <div class="bento-live-legend">${legend}</div>
      <span class="bento-live-updated muted">${updated ? esc(t("prn_live_updated", { t: updated })) : esc(t("prn_live_watching"))}${live && live.source ? ` · ${esc(live.source)}` : ""}</span>
    </div>
  </div>`;
}

function bentoLiveTableHTML(name) {
  if (!bentoElectionMode()) return "";
  const data = state.data.dun;
  if (!data || !name) return "";
  const seats = data.seats.filter((s) => s.state === name).slice().sort((a, b) => {
    const ac = a.dun_code || a.code, bc = b.dun_code || b.code;
    return String(ac).localeCompare(String(bc), undefined, { numeric: true });
  });
  const liveSeats = (state.prnLive && state.prnLive.seats) || {};
  const filter = bentoLiveFilter || "all";
  // filter chips: All, Undeclared, then coalitions present in contest
  const e = liveElection() || (state.prn16 && state.prn16.election);
  const coals = Object.keys((state.prn16 && state.prn16.contested) || { BN: 1, PH: 1, PN: 1 })
    .sort((a, b) => ((state.prn16.contested[b] || 0) - (state.prn16.contested[a] || 0)));
  const chips = [
    ["all", t("prn_live_filter_all")],
    ["open", t("prn_live_filter_open")],
    ...coals.map((c) => [c, c]),
  ].map(([id, lab]) =>
    `<button type="button" class="bento-live-chip${filter === id ? " on" : ""}" data-live-filter="${esc(id)}" aria-pressed="${filter === id}">${esc(lab)}</button>`
  ).join("");

  const rows = seats.map((s) => {
    const lr = liveSeats[s.code] || liveSeats[String(s.code).replace(/^1_/, "")] || null;
    const st = prnLiveStatusMeta(lr);
    const coal = (lr && (lr.coalition || lr.party)) || "";
    if (!liveSeatMatchesFilter(lr, st, filter)) return "";
    const leader = (lr && lr.name) || "—";
    const maj = lr && lr.majority != null && lr.majority !== "" ? lr.majority : "—";
    // Party of whoever is leading / won this seat
    const party = (lr && (lr.party || lr.coalition)) || coal || "—";
    const col = coal ? prnCoalColor(coal) : (party !== "—" ? prnCoalColor(party) : null);
    const sw = col ? `<span class="sw" style="background:${col.bg}"></span>` : "";
    const sel = s.code === bentoSeat ? " is-sel" : "";
    const flash = (prnFlashCodes || []).includes(s.code) ? " just-called" : "";
    const codeLabel = s.dun_code || s.code.replace(/^1_/, "");
    return `<tr class="bento-live-row st-${st.key}${sel}${flash}" data-code="${esc(s.code)}" tabindex="0" role="button">
      <td class="col-code mono">${esc(codeLabel)}</td>
      <td class="col-seat"><span class="bento-live-cell">${esc(s.name)}</span></td>
      <td class="col-status"><span class="bento-live-st st-${st.key}">${esc(st.label)}</span></td>
      <td class="col-leader"><span class="bento-live-cell">${esc(leader)}</span></td>
      <td class="col-party bento-live-coal">${sw}<span class="bento-live-cell">${esc(party)}</span></td>
      <td class="col-bloc bento-live-coal">${sw}<span class="bento-live-cell">${esc(coal || "—")}</span></td>
      <td class="col-maj mono">${esc(String(maj))}</td>
    </tr>`;
  }).filter(Boolean).join("");

  const body = rows || `<tr><td colspan="7" class="muted bento-live-empty">${esc(t("prn_live_empty"))}</td></tr>`;
  return `<div class="bento-tile bento-livetable">
    <div class="bento-livetable-head">
      <div class="bento-kicker">${esc(t("prn_live_table"))} · ${seats.length}</div>
      <div class="bento-live-filters" role="toolbar" aria-label="${esc(t("prn_live_table"))}">${chips}</div>
    </div>
    <div class="bento-livetable-scroll">
      <table class="bento-live-table">
        <colgroup>
          <col class="col-code" />
          <col class="col-seat" />
          <col class="col-status" />
          <col class="col-leader" />
          <col class="col-party" />
          <col class="col-bloc" />
          <col class="col-maj" />
        </colgroup>
        <thead>
          <tr>
            <th class="col-code">${esc(t("prn_live_col_code"))}</th>
            <th class="col-seat">${esc(t("prn_live_col_seat"))}</th>
            <th class="col-status">${esc(t("prn_live_col_status"))}</th>
            <th class="col-leader">${esc(t("prn_live_col_leader"))}</th>
            <th class="col-party">${esc(t("prn_live_col_party"))}</th>
            <th class="col-bloc">${esc(t("prn_live_col_coal"))}</th>
            <th class="col-maj">${esc(t("prn_live_col_maj"))}</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  </div>`;
}

// Aspect-match every state-map tile's viewBox to its own rendered box, so the state
// sits centred with symmetric margins regardless of its raw bbox shape (fixes the
// letterboxed federal-territory tiles). Mirrors the main map's stateViewBox aspect
// lock; touches only the viewBox string, never the frozen projection or seat paths.
function fitBentoMapTiles() {
  if (!BENTO) return;
  BENTO.querySelectorAll(".bento-map-svg[data-bw]").forEach((svg) => {
    const wrap = svg.parentElement;
    if (!wrap) return;
    const rw = wrap.clientWidth, rh = wrap.clientHeight;
    if (!(rw > 0 && rh > 0)) return;
    const ar = rw / rh;
    let w = +svg.dataset.bw, h = +svg.dataset.bh;
    if (!(w > 0 && h > 0)) return;
    const cx = +svg.dataset.bx + w / 2, cy = +svg.dataset.by + h / 2;
    if (w / h > ar) h = w / ar; else w = h * ar;
    svg.setAttribute("viewBox", `${(cx - w / 2).toFixed(2)} ${(cy - h / 2).toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)}`);
  });
}
// One ResizeObserver on the map wrap keeps the fit correct through the panel's width
// transitions and any viewport resize without per-frame polling.
let bentoMapRO = null;
function observeBentoMap() {
  fitBentoMapTiles();   // first pass now (sync layout) so the correct frame paints immediately
  const wrap = BENTO && BENTO.querySelector(".bento-map-wrap");
  if (!wrap) return;
  if (typeof ResizeObserver === "undefined") { requestAnimationFrame(fitBentoMapTiles); return; }
  if (!bentoMapRO) bentoMapRO = new ResizeObserver(() => fitBentoMapTiles());
  bentoMapRO.disconnect();
  BENTO.querySelectorAll(".bento-map-wrap").forEach((w) => bentoMapRO.observe(w));
}

// the seat's CURRENT holder + how they won it (votes, %, majority) — from the most
// recent completed Johor poll (2022, or a later by-election), baked into prn16-johor.
function incumbentStatLine(entry) {
  const bits = [];
  if (entry.incumbent_votes_2022)
    bits.push(t("prn_votes_n", { n: entry.incumbent_votes_2022.toLocaleString() }) + (entry.incumbent_pct_2022 ? ` (${entry.incumbent_pct_2022}%)` : ""));
  if (entry.majority_2022) bits.push(t("prn_majority_n", { n: entry.majority_2022 }));
  return bits.join(" · ");
}
// coalition the sitting rep won under (from "BN-MCA" → "BN")
function incumbentCoalition(entry) {
  return (String(entry.incumbent_party_2022 || "").split("-")[0] || "").trim();
}
// last win's majority as a % of the vote → how competitive the seat is
function majorityPct2022(entry) {
  const v = entry.incumbent_votes_2022, pct = entry.incumbent_pct_2022;
  const maj = entry.majority_2022 ? Number(String(entry.majority_2022).replace(/[^0-9]/g, "")) : NaN;
  if (!v || !pct || !Number.isFinite(maj) || maj <= 0) return null;
  const total = v / (pct / 100);
  return total > 0 ? Math.round((maj / total) * 1000) / 10 : null;
}
function competitiveness(entry) {
  return competitivenessFromMajorityPct(majorityPct2022(entry));   // classifier lives in lib.js (tested)
}
// "currently held by" — richer: a coalition-coloured 2022 margin bar + a
// competitiveness badge (Marginal/Leaning/Safe) so a voter can see at a glance how
// contested their seat is, and by how much the incumbent won last time.
function incumbentBlockHTML(entry, seatCode) {
  if (!entry || !entry.incumbent_2022) return "";
  const col = prnCoalColor(incumbentCoalition(entry)).bg;
  const party = entry.incumbent_party_2022 ? ` <span class="muted">· ${esc(entry.incumbent_party_2022)}</span>` : "";
  const pct = Number(entry.incumbent_pct_2022) || 0;
  const bar = pct ? `<div class="prn-margin-bar"><span style="width:${Math.min(100, pct)}%;background:${col}"></span></div>` : "";
  const comp = competitiveness(entry);
  const badge = comp ? `<span class="prn-comp prn-comp-${comp.key}" title="${esc(t("prn_comp_title", { n: comp.pct }))}">${esc(t("prn_comp_" + comp.key))}</span>` : "";
  const bits = [];
  if (entry.incumbent_votes_2022)
    bits.push(t("prn_votes_n", { n: entry.incumbent_votes_2022.toLocaleString() }) + (pct ? ` (${pct}%)` : ""));
  if (entry.majority_2022) {
    const mp = majorityPct2022(entry);
    bits.push(t("prn_won_by", { n: entry.majority_2022 }) + (mp != null ? ` (${mp}%)` : ""));
  }
  // portrait: prefer localised PRN profile photo, else aduns.json
  const prof = seatCode ? profileForCandidate(seatCode, entry.incumbent_2022) : null;
  const adun = seatCode && state.aduns && state.aduns[seatCode];
  const photoUrl = (prof && prof.photo_url) || (adun && adun.photo) || "";
  const photo = photoUrl ? personPhotoHTML(entry.incumbent_2022, photoUrl, "prn-inc-photo") : "";
  const photoCredit = (prof && prof.photo_credit) || (adun && adun.photo_credit) || "";
  return `<div class="prn-inc${photo ? " has-photo" : ""}">
    <div class="prn-inc-top"><span class="prn-inc-kicker">${esc(t("prn_incumbent"))}</span>${badge}</div>
    <div class="prn-inc-row">
      ${photo}
      <div class="prn-inc-main">
        <div class="prn-inc-name">${esc(entry.incumbent_2022)}${party}</div>
        ${bar}
        ${bits.length ? `<div class="prn-inc-stat muted">${esc(bits.join(" · "))}</div>` : ""}
      </div>
    </div>
    ${photo && photoCredit ? `<p class="yb-credit muted">${esc(t("pol_photo_by", { credit: photoCredit }))}</p>` : ""}
  </div>`;
}

function prnSpotlightHTML() {
  const data = state.data.dun;
  const seat = bentoSeat && data && data.byCode.get(bentoSeat);
  const entry = seat && state.prn16.seats[seat.code];
  if (!seat || !entry) {
    return `<div class="bento-spot-empty"><div class="bento-spot-mark">🗳️</div><p class="muted">${esc(t("prn_bento_pick"))}</p></div>`;
  }
  const ctx = johorSeatContext(seat.code);
  const exco = johorExcoForSeat(seat.code);
  const inc = incumbentBlockHTML(entry, seat.code);
  const meta = [];
  if (entry.electorate) meta.push(`${entry.electorate.toLocaleString()} ${esc(t("prn_electorate"))}`);
  if (seat.parlimen) meta.push(`${esc(t("parlimen_label"))} ${esc(parlimenContext(seat))}`);
  if (ctx && ctx.competitiveness) meta.push(esc(t("prn_comp_" + ctx.competitiveness) || ctx.competitiveness));
  const metaLine = meta.length ? `<span class="bento-spot-meta muted">${meta.join(" · ")}</span>` : "";
  const bye = ctx && ctx.byelection
    ? `<p class="bento-spot-bye muted">↩ ${esc(ctx.byelection.note || ("By-election " + (ctx.byelection.date || "")))}</p>`
    : "";
  const excoLine = exco
    ? `<div class="bento-exco-chip"><span class="bento-exco-kicker">${esc(exco.role || "EXCO")}</span> ${esc(exco.portfolio || "")}</div>`
    : "";
  // incumbent right under the seat name (answers "who holds this now?" first),
  // then the 2026 candidates as cards laid out beside the map
  return `<div class="bento-spot-head">
      <div class="bento-spot-kicker">${esc(entry.ncode)} · ${esc(t("prn_candidates"))} ${entry.candidates.length}</div>
      <h3>${esc(entry.name)}</h3>${metaLine}${bye}${excoLine}
    </div>${inc}
    <div class="bento-cand-label muted">${esc(t("prn_candidates"))}</div>
    <div class="bento-cand-grid bento-cand-row">${prnCandidateCardsHTML(entry, seat.code, true)}</div>`;
}

// Spotlight: holder + (in PRN mode) 2026 runners + Rick-fed tonight count + how it voted.
function bentoSpotlightHTML() {
  return stateSpotlightHTML();
}

// Resolve a seat's live row under either "1_N.01" or "N.01" keys.
function prnLiveForSeat(code) {
  const seats = state.prnLive && state.prnLive.seats;
  if (!seats || !code) return null;
  if (seats[code]) return seats[code];
  const bare = String(code).replace(/^1_/, "");
  if (seats[bare]) return seats[bare];
  if (seats["1_" + bare]) return seats["1_" + bare];
  return null;
}
function prnCandNameKey(s) {
  return String(s || "").toLowerCase()
    .replace(/\b(bin|binti|a\/l|a\/p|anak|datuk|dato'?|datin|tan\s*sri|tun|yb)\b/g, " ")
    .replace(/[^a-z]+/g, "");
}
function prnNamesMatch(a, b) {
  const ka = prnCandNameKey(a), kb = prnCandNameKey(b);
  if (!ka || !kb) return false;
  return ka === kb || ka.includes(kb) || kb.includes(ka) || namesLikelySamePerson(a, b);
}

// Compact 2026 runners for the seat spotlight (same cards as bottom tile).
function prnSpotRunnersHTML(entry, seatCode) {
  if (!entry || !entry.candidates || !entry.candidates.length) return "";
  return `<div class="prn-spot-runners">
    <div class="bento-cand-label muted">${esc(t("prn_bento_running"))} · ${entry.candidates.length}</div>
    <div class="bento-cand-grid bento-cand-row">${prnCandidateCardsHTML(entry, seatCode, true)}</div>
  </div>`;
}

// Per-seat "tonight's count" line — empty until Rick/Sinar publish votes for this seat.
// When live.candidates[] has votes, paint a share bar over the SPR field; otherwise
// show leader + majority (manual call) with runners still listed as awaiting.
function prnSpotTonightHTML(seatCode, entry, headingKey = "prn_tonight") {
  if (!liveElection() || !state.prnLive) return "";
  const lr = prnLiveForSeat(seatCode);
  const meta = prnLiveStatusMeta(lr);
  const hasCall = !!(lr && lr.status && lr.status !== "counting");
  const liveField = (lr && Array.isArray(lr.candidates) && lr.candidates.length) ? lr.candidates : [];
  const liveByKey = new Map();
  for (const c of liveField) liveByKey.set(prnCandNameKey(c.name), c);

  const roster = (entry && entry.candidates) || [];
  let rows = [];
  if (roster.length) {
    rows = roster.map((c) => {
      let hit = liveByKey.get(prnCandNameKey(c.name));
      if (!hit) hit = liveField.find((lc) => prnNamesMatch(lc.name, c.name));
      const isLeader = !!(lr && lr.name && prnNamesMatch(lr.name, c.name));
      let votes = hit && hit.votes != null ? Number(hit.votes) : 0;
      if (!votes && isLeader && lr && lr.votes != null) votes = Number(lr.votes) || 0;
      return {
        name: c.name,
        coalition: (hit && hit.coalition) || c.coalition,
        party: (hit && hit.party) || c.party,
        votes: Number.isFinite(votes) ? votes : 0,
        isLeader,
      };
    });
  } else if (liveField.length) {
    rows = liveField.map((c) => ({
      name: c.name,
      coalition: c.coalition || c.party,
      party: c.party,
      votes: Number(c.votes) || 0,
      isLeader: !!(lr && lr.name && prnNamesMatch(lr.name, c.name)),
    }));
  } else if (hasCall && lr.name) {
    rows = [{
      name: lr.name,
      coalition: lr.coalition || lr.party,
      party: lr.party,
      votes: Number(lr.votes) || 0,
      isLeader: true,
    }];
  }

  const totalVotes = rows.reduce((a, r) => a + (r.votes || 0), 0);
  const anyVotes = totalVotes > 0;
  const statusChip = `<span class="prn-tonight-st prn-tonight-st-${meta.key}">${esc(meta.label)}</span>`;

  let body;
  if (!hasCall && !anyVotes) {
    body = `<p class="prn-tonight-empty muted">${esc(t("prn_tonight_awaiting"))}</p>`;
  } else {
    const barRows = rows.map((r) => {
      const col = prnCoalColor(r.coalition || r.party).bg;
      const pct = anyVotes && r.votes ? Math.round((1000 * r.votes / totalVotes)) / 10 : 0;
      const party = r.party && r.party !== r.coalition
        ? `${esc(r.coalition || "")} · ${esc(r.party)}`
        : esc(r.coalition || r.party || "");
      const pctLabel = anyVotes && r.votes ? `${pct}%` : "—";
      const voteLabel = r.votes ? r.votes.toLocaleString() : "";
      return `<div class="prn-tonight-row${r.isLeader ? " is-lead" : ""}">
        <div class="prn-last-lbl">
          <span class="prn-last-name">${esc(r.name)}${r.isLeader ? ` <span class="prn-tonight-lead">${esc(t("prn_tonight_lead"))}</span>` : ""}</span>
          <span class="prn-last-party muted">${party}</span>
        </div>
        <div class="prn-last-bar"><span style="width:${Math.min(100, pct)}%;background:${col}"></span></div>
        <div class="prn-last-pct mono" title="${esc(voteLabel)}">${pctLabel}</div>
      </div>`;
    }).join("");

    const bits = [];
    if (lr && lr.name) {
      const who = [lr.name, lr.party || lr.coalition].filter(Boolean).join(" · ");
      bits.push(esc(who));
    }
    if (lr && lr.majority != null && lr.majority !== "") {
      const majN = Number(String(lr.majority).replace(/[^0-9.-]/g, ""));
      bits.push(esc(t("prn_majority_n", { n: Number.isFinite(majN) ? majN.toLocaleString() : lr.majority })));
    }
    if (lr && lr.votes != null && Number(lr.votes) > 0 && !anyVotes) {
      bits.push(esc(t("prn_votes_n", { n: Number(lr.votes).toLocaleString() })));
    }
    const sumLine = bits.length ? `<div class="prn-tonight-sum muted">${bits.join(" · ")}</div>` : "";
    body = `${barRows ? `<div class="prn-tonight-field">${barRows}</div>` : ""}${sumLine}`;
  }

  return `<div class="prn-tonight" data-seat="${esc(seatCode)}">
    <div class="prn-tonight-h">
      <span class="prn-inc-kicker">${esc(t(headingKey))}</span>
      ${statusChip}
    </div>
    ${body}
  </div>`;
}

/** Bottom tile for PRN mode: 2026 candidates for the spotlighted seat. */
function bentoRunnersTileHTML() {
  const entry = bentoSeat && state.prn16 && state.prn16.seats && state.prn16.seats[bentoSeat];
  const seat = bentoSeat && state.data.dun && state.data.dun.byCode.get(bentoSeat);
  const title = seat
    ? `${esc(entry && entry.ncode ? entry.ncode : seat.dun_code || "")} · ${esc(seat.name)} · ${esc(t("prn_candidates"))}`
    : esc(t("prn_candidates"));
  if (!entry || !entry.candidates || !entry.candidates.length) {
    return `<div class="bento-tile bento-statsrow bento-runners">
      <div class="bento-kicker">${title}</div>
      <div id="bento-runners-body" class="bento-runners-body">
        <p class="muted">${esc(t("prn_bento_pick"))}</p>
      </div>
    </div>`;
  }
  return `<div class="bento-tile bento-statsrow bento-runners">
    <div class="bento-kicker">${title} · ${entry.candidates.length}</div>
    <div id="bento-runners-body" class="bento-runners-body">
      <div class="bento-cand-grid bento-runners-grid">${prnCandidateCardsHTML(entry, bentoSeat, true)}</div>
    </div>
  </div>`;
}
function bentoRunnersBodyHTML() {
  const entry = bentoSeat && state.prn16 && state.prn16.seats && state.prn16.seats[bentoSeat];
  if (!entry || !entry.candidates || !entry.candidates.length) {
    return `<p class="muted">${esc(t("prn_bento_pick"))}</p>`;
  }
  return `<div class="bento-cand-grid bento-runners-grid">${prnCandidateCardsHTML(entry, bentoSeat, true)}</div>`;
}

// generic seat spotlight — who represents this seat and how they won it.
// Parliament: the full politician card (photo/bio/socials). DUN: the assemblyman
// from the seat's own state-election result. Johor DUN (assembly dissolved):
// the 2022 incumbent block + "how it voted" recap from the PRN dataset.
function stateSpotlightHTML() {
  // the spotlighted seat may come from EITHER layer (the search box surfaces both
  // parliament and DUN seats of the open state) — resolve tier from the code
  const spotTier = bentoSeat ? seatTierOf(bentoSeat) : state.tier;
  const data = state.data[spotTier];
  const seat = bentoSeat && data && data.byCode.get(bentoSeat);
  if (!seat) {
    return `<div class="bento-spot-empty"><div class="bento-spot-mark">🗺️</div><p class="muted">${esc(t("bento_pick"))}</p></div>`;
  }
  const isP = spotTier === "parlimen";
  const kicker = isP ? seat.code : `DUN · ${esc(seat.dun_code)}`;
  const meta = [];
  if (!isP && seat.parlimen) meta.push(`${esc(t("parlimen_label"))} ${esc(parlimenContext(seat))}`);
  const head = (extraMeta = []) => {
    const line = extraMeta.concat(meta);
    return `<div class="bento-spot-head">
      <div class="bento-spot-kicker">${kicker}</div>
      <h3>${esc(seat.name)}</h3>
      ${line.length ? `<span class="bento-spot-meta muted">${line.join(" · ")}</span>` : ""}
    </div>`;
  };
  // Johor DUN: DURING the live PRN (assembly dissolved) the richest data is the
  // prn16 incumbent block. Once the election concludes (liveElection() null), fall
  // through to the seat's own 2026 result in results-dun.json like any other state.
  const prnEntry = !isP && liveElection() && state.prn16 && state.prn16.seats && state.prn16.seats[seat.code];
  if (prnEntry && prnEntry.incumbent_2022) {
    const em = prnEntry.electorate ? [`${prnEntry.electorate.toLocaleString()} ${esc(t("prn_electorate"))}`] : [];
    // PRN night board: runners + Rick-fed tonight count between holder and 2022 recap
    const liveResult = prnLiveForSeat(seat.code);
    const hasPublishedResult = !!(liveResult && ["leading", "won", "official"].includes(liveResult.status));
    const race = bentoElectionMode()
      ? `${prnSpotRunnersHTML(prnEntry, seat.code)}${prnSpotTonightHTML(seat.code, prnEntry)}`
      : (hasPublishedResult ? prnSpotTonightHTML(seat.code, prnEntry, "prn_result_2026") : "");
    const prior = hasPublishedResult ? "" : lastResultHTML(prnEntry);
    return `${head(em)}${incumbentBlockHTML(prnEntry, seat.code)}${race}${prior}
      <div class="src-line muted">${esc((bentoElectionMode() || hasPublishedResult) ? t("prn_source") : t("src_johor2022"))}</div>`;
  }
  const r = seatResultOf(seat, spotTier);
  if (!r) {
    return `${head()}<div class="bento-spot-empty"><div class="bento-spot-mark">🗳️</div><p class="muted">${esc(t("rep_ph"))}</p></div>`;
  }
  const card = formatResultCard(r);
  const blocPill = `<span class="pill" style="${pillStyle(partyColor(r.coalition))}">${esc(r.coalition)}</span>`;
  const partyLabel = card.party && card.party.label && card.party.label !== r.coalition ? esc(card.party.label) : "";
  const blocUnit = `<span class="bloc-unit">${partyLabel ? "· " : ""}${blocPill}</span>`;
  // compact: no Wikipedia bio / socials in the bento strip — keeps the map row height stable
  const yb = ybCardHTML(seat, r, partyLabel, blocUnit, politicianOf(seat, spotTier), { compact: true, tier: spotTier });
  // last-result block: coalition margin bar + competitiveness badge + the numbers
  const col = partyColor(r.coalition);
  const bar = Number.isFinite(card.votePct)
    ? `<div class="prn-margin-bar"><span style="width:${Math.min(100, card.votePct)}%;background:${col}"></span></div>` : "";
  const comp = competitivenessFromMajorityPct(card.majorityPct);
  const badge = comp
    ? `<span class="prn-comp prn-comp-${comp.key}" title="${esc(t("prn_comp_title", { n: comp.pct }))}">${esc(t("prn_comp_" + comp.key))}</span>` : "";
  const bits = [];
  if (card.votes != null) bits.push(t("prn_votes_n", { n: card.votes.toLocaleString() }) + (Number.isFinite(card.votePct) ? ` (${card.votePct}%)` : ""));
  if (card.majority != null) bits.push(t("prn_won_by", { n: card.majority.toLocaleString() }) + (Number.isFinite(card.majorityPct) ? ` (${card.majorityPct}%)` : ""));
  if (card.turnout != null) bits.push(`${t("turnout")} ${card.turnout}%`);
  const ru = card.runnerUp;
  const runner = ru && ru.name
    ? `<div class="bento-spot-runner muted">${esc(t("runner"))}: ${esc(ru.name)}${ru.party ? ` · ${esc(ru.party)}` : ""}${ru.votes != null ? ` · ${ru.votes.toLocaleString()}` : ""}</div>` : "";
  return `${head()}${yb}
    <div class="prn-inc bento-spot-result">
      <div class="prn-inc-top"><span class="prn-inc-kicker">${esc(t("bento_last_result"))}</span>${badge}</div>
      ${bar}
      ${bits.length
        ? `<div class="prn-inc-stat muted">${esc(bits.join(" · "))}</div>`
        : (r.pending ? `<div class="prn-inc-stat muted">${esc(t("prn_count_pending"))}</div>` : "")}
      ${runner}
    </div>
    ${resultSourceLine(r, !isP && !!(state.resultsDun && state.resultsDun[seat.code]))}`;
}

// "how this seat voted last time" — the previous contest's top candidates as a
// coalition-coloured bar chart. Real context that fills the spotlight usefully.
function lastResultHTML(entry) {
  const field = entry.last_field;
  if (!field || !field.length) return "";
  const rows = field.map((f) => {
    const col = prnCoalColor(f.coalition).bg;
    const pct = Number(f.pct) || 0;
    const party = f.party && f.party !== f.coalition ? `${esc(f.coalition)} · ${esc(f.party)}` : esc(f.coalition);
    return `<div class="prn-last-row">
      <div class="prn-last-lbl"><span class="prn-last-name">${esc(f.name)}</span><span class="prn-last-party muted">${party}</span></div>
      <div class="prn-last-bar"><span style="width:${Math.min(100, pct)}%;background:${col}"></span></div>
      <div class="prn-last-pct mono">${pct ? pct + "%" : ""}</div>
    </div>`;
  }).join("");
  return `<div class="prn-last">
    <div class="prn-last-h muted">${esc(t("prn_last_result", { y: entry.last_field_year || "" }))}</div>
    ${rows}
  </div>`;
}

function profileSourceHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch (_) { return t("profile_source"); }
}
function profileQualityLabel(profile) {
  const q = String((profile && profile.source_quality) || "").toLowerCase();
  return q.includes("official") ? t("profile_quality_official") : t("profile_quality_profile");
}
function normalProfileSource(src) {
  if (!src) return null;
  if (typeof src === "string") return { label: profileSourceHost(src), url: src };
  const url = src.url || src.href || "";
  if (!url) return null;
  return { label: src.label || profileSourceHost(url), url };
}
function profileSourcesFor(profile) {
  const sources = Array.isArray(profile && profile.sources)
    ? profile.sources.map(normalProfileSource).filter(Boolean)
        .filter((s) => !/mypolitik\.krackeddevs\.com/i.test(s.url))
    : [];
  const firstParty = /(^|\.)spr\.gov\.my|(^|\.)parlimen\.gov\.my|(^|\.)dewannegeri\.johor\.gov\.my|bernama\.com/i;
  return sources.sort((a, b) => Number(firstParty.test(b.url)) - Number(firstParty.test(a.url)));
}
function profileSourcesHTML(profile) {
  const sources = profileSourcesFor(profile).slice(0, 3);
  if (!sources.length) return "";
  return `<div class="prn-profile-sources"><span>${esc(t("profile_sources"))}</span>${sources.map((s) =>
    `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a>`).join("")}</div>`;
}
function profileListHTML(labelKey, items, max = 3) {
  const xs = Array.isArray(items) ? items.filter(Boolean).slice(0, max) : [];
  if (!xs.length) return "";
  return `<div class="prn-profile-list"><span>${esc(t(labelKey))}</span><ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
}
function profileRecordText(item) {
  if (!item) return "";
  if (typeof item === "string") return item;
  const head = [item.period, item.title || item.role || item.party].filter(Boolean).join(" - ");
  const tail = [item.seat, item.coalition, item.note, item.result].filter(Boolean).join(" · ");
  return [head, tail].filter(Boolean).join(" · ");
}
function profileTimelineHTML(labelKey, items, max = 4) {
  const xs = Array.isArray(items) ? items.map(profileRecordText).filter(Boolean).slice(0, max) : [];
  if (!xs.length) return "";
  return `<div class="prn-profile-timeline"><span>${esc(t(labelKey))}</span><ol>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ol></div>`;
}
function profilePartyHistoryHTML(items) {
  const xs = Array.isArray(items) ? items.map(profileRecordText).filter(Boolean).slice(0, 4) : [];
  if (!xs.length) return "";
  return `<div class="prn-profile-partyhist"><span>${esc(t("profile_party_history"))}</span>${xs.map((x) => `<b>${esc(x)}</b>`).join("")}</div>`;
}
function profileForCandidate(seatCode, candidateName) {
  const bySeat = state.polProfiles && state.polProfiles.profiles && state.polProfiles.profiles[seatCode];
  if (!bySeat || !candidateName) return null;
  if (bySeat[candidateName]) return bySeat[candidateName];
  const target = namekeyLoose(candidateName);
  const match = Object.entries(bySeat).find(([name]) => {
    const k = namekeyLoose(name);
    return k === target || (k.length >= 8 && target.includes(k)) || (target.length >= 8 && k.includes(target));
  });
  return match ? match[1] : null;
}
function candidateProfileHTML(profile) {
  if (!profile) return "";
  const summary = profile.summary || profile.biography_summary || "";
  const role = profile.current_role ? `<div class="prn-profile-role">${esc(profile.current_role)}</div>` : "";
  const quality = `<span class="prn-profile-quality">${esc(profileQualityLabel(profile))}</span>`;
  const lists = [
    profilePartyHistoryHTML(profile.party_history),
    profileTimelineHTML("profile_track_record", profile.track_record, 4),
    profileListHTML("profile_experience", profile.career_highlights, 3),
    profileListHTML("profile_education", profile.education, 2),
    profileListHTML("profile_election_history", profile.election_history, 2),
  ].join("");
  return `<div class="prn-profile">
    <div class="prn-profile-meta"><span>${esc(t("profile_background"))}</span>${quality}</div>
    ${role}
    ${summary ? `<p class="prn-profile-summary">${esc(summary)}</p>` : ""}
    ${lists}
    ${profileSourcesHTML(profile)}
  </div>`;
}
function prnCandidateForSeat(seatCode, candidateName) {
  const entry = state.prn16 && state.prn16.seats && state.prn16.seats[seatCode];
  if (!entry || !candidateName) return null;
  const target = namekeyLoose(candidateName);
  const candidate = entry.candidates.find((c) => namekeyLoose(c.name) === target);
  return candidate ? { entry, candidate } : null;
}
function candidateModalTileHTML(cls, label, body) {
  if (!body) return "";
  return `<section class="cand-tile ${cls}">
    <div class="cand-kicker">${esc(label)}</div>
    ${body}
  </section>`;
}
function candidateModalListHTML(items, ordered = false) {
  const xs = Array.isArray(items) ? items.map(profileRecordText).filter(Boolean) : [];
  if (!xs.length) return "";
  const tag = ordered ? "ol" : "ul";
  return `<${tag} class="cand-list">${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</${tag}>`;
}
function candidateModalSourcesHTML(profile, election) {
  const sources = profileSourcesFor(profile);
  const links = sources.length ? `<div class="cand-source-links">${sources.map((s) =>
    `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label)}</a>`).join("")}</div>` : "";
  const src = election && election.source ? `<p class="cand-source-note muted">${esc(t("candidate_source", { source: election.source }))}</p>` : "";
  return links || src ? `${links}${src}` : "";
}
function candidateModalNewsHTML(seatCode, name) {
  const bucket = state.prnNews && state.prnNews[seatCode];
  const items = (bucket && bucket[name]) || [];
  const seatItems = (bucket && bucket._seat) || [];
  const merged = [...items, ...seatItems.filter((s) => !items.some((i) => i.u === s.u))].slice(0, 5);
  if (!merged.length) return "";
  return `<div class="cand-news-list">${merged.map((n) =>
    `<a href="${esc(n.u)}" target="_blank" rel="noopener"><span>${esc(n.t)}</span><small>${esc(n.s)}${n.d ? " · " + esc(fmtDayMonth(n.d)) : ""}</small></a>`).join("")}</div>`;
}
function candidateModalHTML(seat, entry, candidate, profile) {
  const election = (state.prn16 && state.prn16.election) || liveElection();
  const col = prnCoalColor(candidate.coalition);
  const name = candidate.name;
  const party = candidate.party && candidate.party !== candidate.coalition ? `${esc(candidate.coalition)} · ${esc(candidate.party)}` : esc(candidate.coalition);
  const isInc = namekeyLoose(name) === namekeyLoose(entry.incumbent_2022 || "");
  const summary = (profile && (profile.summary || profile.biography_summary)) || "";
  const role = (profile && profile.current_role) || "";
  const fact = (label, value, note) => value != null && value !== ""
    ? `<div class="cand-fact"><span>${esc(label)}</span><b>${esc(value)}</b>${note ? `<small>${esc(note)}</small>` : ""}</div>` : "";
  const facts = [
    fact(t("party_bloc"), candidate.party || candidate.coalition || "", candidate.coalition || ""),
    fact(t("prn_electorate"), entry.electorate ? entry.electorate.toLocaleString() : ""),
    fact(t("prn_incumbent"), entry.incumbent_2022 || "", entry.incumbent_party_2022 || ""),
    candidate.symbol ? fact(t("candidate_symbol"), candidate.symbol) : "",
  ].filter(Boolean).join("");
  const partyHistory = candidateModalListHTML(profile && profile.party_history, false);
  const track = candidateModalListHTML(profile && profile.track_record, true);
  const experience = candidateModalListHTML(profile && profile.career_highlights, false);
  const education = candidateModalListHTML(profile && profile.education, false);
  const electionHistory = candidateModalListHTML(profile && profile.election_history, false);
  const news = candidateModalNewsHTML(seat.code, name);
  // Nomination-dashboard demographic fields are not reliable enough for display
  // (81 age mismatches and one sex mismatch found against Bernama/SPR).
  const demoLine = "";
  const socials = profile && Array.isArray(profile.social_links) && profile.social_links.length
    ? `<div class="cand-socials">${profile.social_links.map((u) => {
        const host = (() => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (_) { return "link"; } })();
        return `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(host)}</a>`;
      }).join(" ")}</div>`
    : "";
  const contact = profile && profile.official_contact;
  const contactBits = contact
    ? [contact.phone, contact.email, contact.address].filter(Boolean)
    : [];
  const contactHtml = contactBits.length
    ? `<ul class="cand-list">${contactBits.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
    : "";
  const exco = isInc ? johorExcoForSeat(seat.code) : null;
  const roleText = [role, exco && exco.portfolio].filter(Boolean).join(" · ");
  // meta as chips (not one long muted sentence) — clearer hierarchy in the hero
  const metaChips = [
    entry.ncode || seat.dun_code,
    entry.name || seat.name,
    seat.parlimen ? `${t("parlimen_label")} ${parlimenContext(seat)}` : "",
    election && election.name ? election.name : "",
    demoLine,
  ].filter(Boolean).map((x) => `<span class="cand-meta-chip">${esc(x)}</span>`).join("");
  return `<div class="cand-modal-shell" style="--cc:${col.bg};--ccfg:${col.fg}">
    <button class="pol-modal-close cand-modal-close" type="button" data-i18n-title="card_preview_close" title="${esc(t("card_preview_close"))}" aria-label="${esc(t("card_preview_close"))}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true"><line x1="6" x2="18" y1="6" y2="18"/><line x1="6" x2="18" y1="18" y2="6"/></svg>
    </button>
    <div class="cand-grid">
      <section class="cand-hero cand-tile">
        <div class="cand-photo-wrap">${personPhotoHTML(name, profile && profile.photo_url, "cand-modal-photo")}</div>
        <div class="cand-hero-id">
          <div class="cand-kicker">${esc(t("candidate_bento_title"))}</div>
          <h2>${esc(name)}</h2>
          <div class="cand-meta-row">${metaChips}</div>
          <div class="cand-pill-row">
            <span class="pill" style="${pillStyle(col.bg, col.fg)}">${party}</span>
            ${isInc ? `<span class="prn-cc-inc">${esc(t("prn_cc_incumbent"))}</span>` : ""}
            ${exco ? `<span class="prn-cc-inc">${esc(exco.role || "EXCO")}</span>` : ""}
          </div>
          ${socials}
        </div>
      </section>
      ${roleText ? candidateModalTileHTML("cand-role", t("candidate_bento_current_role"), `<p class="cand-role-text">${esc(roleText)}</p>`) : ""}
      ${candidateModalTileHTML("cand-facts", t("candidate_bento_context"), `<div class="cand-facts-grid">${facts}</div>`)}
      ${summary ? candidateModalTileHTML("cand-summary", t("profile_background"), `<p>${esc(summary)}</p>`) : ""}
      ${partyHistory ? candidateModalTileHTML("cand-party", t("profile_party_history"), partyHistory) : ""}
      ${(track || experience) ? candidateModalTileHTML("cand-track", t("profile_track_record"), track || experience) : ""}
      ${electionHistory ? candidateModalTileHTML("cand-election", t("profile_election_history"), electionHistory) : ""}
      ${education ? candidateModalTileHTML("cand-education", t("profile_education"), education) : ""}
      ${contactHtml ? candidateModalTileHTML("cand-contact", "Contact", contactHtml) : ""}
      ${news ? candidateModalTileHTML("cand-news", t("prn_news"), news) : ""}
      ${candidateModalTileHTML("cand-sources", t("profile_sources"), candidateModalSourcesHTML(profile, election))}
    </div>
    <div class="cand-actions">
      <button class="pol-modal-seatbtn cand-seatbtn" type="button" data-candidate-seat="${esc(seat.code)}">${esc(t("pol_view_seat"))}</button>
    </div>
  </div>`;
}
function closeCandidateModal() {
  if (!CAND_MODAL) return;
  if (CAND_MODAL.open && typeof CAND_MODAL.close === "function") CAND_MODAL.close();
  else {
    CAND_MODAL.removeAttribute("open");
    CAND_MODAL.innerHTML = "";
    const returnTo = candidateModalReturnTo;
    candidateModalReturnTo = null;
    if (returnTo && document.contains(returnTo)) returnTo.focus({ preventScroll: true });
  }
}
// the full field, one screen: every 2026 candidate grouped by seat. Seat headers
// carry data-candidate-seat, so the modal's existing delegation closes the browser
// and opens that seat — no new handlers needed for navigation.
function openAllCandidatesBrowser() {
  const p = state.prn16, e = liveElection();
  if (!p || !e || !CAND_MODAL) return;
  const entries = Object.entries(p.seats || {}).sort((a, b) =>
    String(a[1].ncode || a[0]).localeCompare(String(b[1].ncode || b[0]), undefined, { numeric: true }));
  const groups = entries.map(([code, s]) => {
    const cands = (s.candidates || []).map((c) => {
      const col = prnCoalColor(c.coalition);
      const profile = profileForCandidate(code, c.name);
      const party = c.party && c.party !== c.coalition ? `${esc(c.coalition)} · ${esc(c.party)}` : esc(c.coalition);
      return `<li class="prn-all-cand">
        ${personPhotoHTML(c.name, profile && profile.photo_url, "prn-all-photo")}
        <span class="prn-all-name">${esc(c.name)}</span>
        <span class="pill" style="${pillStyle(col.bg)}">${party}</span>
      </li>`;
    }).join("");
    return `<section class="prn-all-seat">
      <button type="button" class="prn-all-seathead" data-candidate-seat="${esc(code)}">
        <b>${esc(s.ncode || code)}</b> ${esc(s.name)} <span class="muted">· ${(s.candidates || []).length}</span>
      </button>
      <ul class="prn-all-list">${cands}</ul>
    </section>`;
  }).join("");
  CAND_MODAL.setAttribute("aria-label", t("prn_all_cands", { n: prnContestTotal(p) }));
  delete CAND_MODAL.dataset.polBento;
  CAND_MODAL.innerHTML = `<div class="pol-modal-shell prn-all-shell">
    <button type="button" class="pol-modal-close" aria-label="✕">✕</button>
    <h2 class="prn-all-title">🗳️ ${esc(e.name)} · ${esc(t("prn_all_cands", { n: prnContestTotal(p) }))}</h2>
    <div class="prn-all-groups">${groups}</div>
  </div>`;
  if (typeof CAND_MODAL.showModal === "function") CAND_MODAL.showModal();
  else CAND_MODAL.setAttribute("open", "");
  CAND_MODAL.querySelector(".pol-modal-close")?.focus();
}
function openCandidateModal(seatCode, candidateName, returnTo = null) {
  if (!CAND_MODAL) return;
  const seat = state.data.dun && state.data.dun.byCode.get(seatCode);
  const found = prnCandidateForSeat(seatCode, candidateName);
  if (!seat || !found) return;
  candidateModalReturnTo = returnTo;
  CAND_MODAL.setAttribute("aria-label", t("candidate_bento_title"));   // the politician bento may have relabelled it
  delete CAND_MODAL.dataset.polBento;
  const profile = profileForCandidate(seatCode, found.candidate.name);
  CAND_MODAL.innerHTML = candidateModalHTML(seat, found.entry, found.candidate, profile);
  if (typeof CAND_MODAL.showModal === "function") CAND_MODAL.showModal();
  else CAND_MODAL.setAttribute("open", "");
  CAND_MODAL.querySelector(".pol-modal-close")?.focus();
}
function candidateCardFromEvent(e) {
  const card = e.target.closest(".prn-cc[data-prn-candidate]");
  if (!card || e.target.closest("a")) return null;
  return card;
}
function openCandidateCard(card) {
  openCandidateModal(card.dataset.prnSeat, card.dataset.prnCandidate, card);
}
function handleCandidateCardClick(e) {
  const card = candidateCardFromEvent(e);
  if (!card) return false;
  e.preventDefault();
  openCandidateCard(card);
  return true;
}
function handleCandidateCardKeydown(e) {
  if (e.key !== "Enter" && e.key !== " ") return;
  const card = candidateCardFromEvent(e);
  if (!card) return;
  if (card.tagName === "BUTTON") return;   // native button already fires click on Enter/Space
  e.preventDefault();
  openCandidateCard(card);
}

// per-candidate cards for the bento spotlight — coalition-accented, with the ballot
// name, party badge, ballot symbol and any campaign-window headlines we have.
// compact=true → photo + name + party only (the bento spotlight, so it never scrolls);
// the full background/sources/news live in the click-to-open candidate modal.
function prnCandidateCardsHTML(entry, seatCode, compact) {
  const nameKey = (s) => s.toLowerCase().replace(/\b(bin|binti|a\/l|a\/p|anak)\b/g, " ").replace(/[^a-z]+/g, "");
  const incKey = nameKey(entry.incumbent_2022 || "");
  const seatNews = state.prnNews && state.prnNews[seatCode];
  return entry.candidates.map((c) => {
    const col = prnCoalColor(c.coalition);
    const profile = profileForCandidate(seatCode, c.name);
    const isInc = incKey && nameKey(c.name) === incKey;   // the sitting rep, re-contesting
    const alias = c.ballot_name && nameKey(c.ballot_name) !== nameKey(c.name)
      ? `<span class="prn-cc-alias muted">${esc(c.ballot_name)}</span>` : "";
    const party = c.party && c.party !== c.coalition ? `${esc(c.coalition)} · ${esc(c.party)}` : esc(c.coalition);
    const sym = c.symbol ? `<span class="prn-cc-sym muted">🗳 ${esc(c.symbol)}</span>` : "";
    const items = seatNews && seatNews[c.name];
    const news = items && items.length
      ? `<div class="prn-cc-news">${items.slice(0, 2).map((n) =>
          `<a class="prn-cc-newslink" href="${esc(n.u)}" target="_blank" rel="noopener"><span class="prn-cc-newst">${esc(n.t)}</span><span class="muted">${esc(n.s)}${n.d ? " · " + esc(fmtDayMonth(n.d)) : ""}</span></a>`).join("")}</div>`
      : "";
    const extra = sym || news ? `<div class="prn-cc-extra">${sym}${news}</div>` : "";
    const incChip = isInc ? ` <span class="prn-cc-inc">${esc(t("prn_cc_incumbent"))}</span>` : "";
    // always show a face (profile photo or monogram) so compact runner cards never look empty
    const photo = personPhotoHTML(c.name, profile && profile.photo_url, "prn-profile-photo");
    const body = compact ? "" : `${candidateProfileHTML(profile)}${extra}`;
    const tag = compact ? "button" : "div";
    const attrs = compact ? `type="button"` : `role="button" tabindex="0"`;
    return `<${tag} class="prn-cc${isInc ? " is-inc" : ""}${profile ? " has-profile" : ""}${compact ? " is-compact" : ""}" style="--cc:${col.bg}" ${attrs} aria-haspopup="dialog" aria-label="${esc(t("candidate_open_profile_aria", { name: c.name }))}" data-prn-seat="${esc(seatCode)}" data-prn-candidate="${esc(c.name)}">
      <div class="prn-cc-head">
        ${photo}
        <div class="prn-cc-id"><span class="prn-cc-name"><span>${esc(c.name)}</span>${incChip}</span>${alias}</div>
        <span class="pill" style="${pillStyle(col.bg, col.fg)}">${party}</span>
      </div>${body}<span class="prn-cc-open">${esc(t("candidate_open_profile"))}</span></${tag}>`;
  }).join("");
}

function prnStandingsTileHTML() {
  const p = state.prn16;
  const total = Object.values(p.contested || {}).reduce((a, b) => a + b, 0) || 1;
  const order = Object.entries(p.contested || {}).sort((a, b) => b[1] - a[1]);
  const bar = order.map(([coal, n]) => `<span style="width:${(100 * n / total).toFixed(2)}%;background:${prnCoalColor(coal).bg}"></span>`).join("");
  const key = order.map(([coal, n]) => `<span class="state-bloc"><span class="sw" style="background:${prnCoalColor(coal).bg}"></span>${esc(coal)} ${n}</span>`).join("");
  return `<div class="sharebar bento-standings-bar">${bar}</div><div class="sharebar-key">${key}</div>`;
}

// coalitions with a manifesto OR a pending state, biggest blocs first
function prnPledgeOrder() {
  const p = state.johorPledges;
  if (!p || !p.coalitions) return [];
  const rank = ["PH", "BN", "PN", "BERSAMA", "MUDA-PSM"];
  return Object.keys(p.coalitions)
    .filter((c) => { const m = p.coalitions[c]; return m && ((m.pledges && m.pledges.length) || m.pending); })
    .sort((a, b) => { const ai = rank.indexOf(a), bi = rank.indexOf(b); return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi); });
}
let prnPledgeTab = null;   // active manifesto tab (coalition code) in the bento pledges tile
// Tabbed manifestos: one coalition at a time (clearer than 5 uneven columns). A tab
// per contesting bloc; the panel shows that bloc's pledges (or its pending state).
function prnPledgeTabsHTML() {
  const p = state.johorPledges;
  const order = prnPledgeOrder();
  if (!order.length) return `<p class="muted">—</p>`;
  if (!prnPledgeTab || !order.includes(prnPledgeTab)) prnPledgeTab = order[0];
  const tabs = order.map((coal) => {
    const col = prnCoalColor(coal);
    const on = coal === prnPledgeTab;
    return `<button type="button" role="tab" aria-selected="${on}" class="prn-pl-tab${on ? " on" : ""}" data-pledge-tab="${esc(coal)}" style="--cc:${col.bg}">${esc(coal)}</button>`;
  }).join("");
  return `<div class="prn-pl-tabs" role="tablist">${tabs}</div>
    <div class="prn-pl-panel">${pledgeBlockHTML(prnPledgeTab, p.coalitions[prnPledgeTab])}</div>`;
}

// shared map tile (both modes): choropleth + seat search for the open state
// the map section (kicker + search + choropleth), tile-agnostic: the election grid
// wraps it in its own tile; the state grid embeds it beside the spotlight
function bentoMapSectionHTML(name) {
  const tier = bentoMapTier();
  const count = (tr) => {
    const d = state.data[tr];
    return d ? d.seats.filter((s) => s.state === name).length : 0;
  };
  let layerControls;
  if (bentoElectionMode()) {
    layerControls = `<span class="bento-map-count">${esc(count("dun"))} ${esc(t("tier_dun"))}</span>`;
  } else {
    // both layers as a segmented pill (same look as the main Parliament/DUN toggle) —
    // tapping one flips the choropleth (search already spans both)
    const chip = (tr, label) => {
      const n = count(tr);
      return n
        ? `<button type="button" role="tab" class="${tier === tr ? "on" : ""}" data-bento-tier="${tr}" aria-selected="${tier === tr}">${n} ${esc(label)}</button>`
        : "";
    };
    layerControls = `<span class="seg chip bento-map-seg" role="tablist">${chip("parlimen", t("tier_parlimen"))}${chip("dun", t("tier_dun"))}</span>`;
  }
  return `<div class="bento-map-wrap">${stateMapTileSVG(name)}</div>
    <div class="bento-map-controls">
      <div class="bento-search">
        <input id="bento-q" class="bento-q" type="search" autocomplete="off" spellcheck="false" placeholder="${esc(t("search_ph"))}" aria-label="${esc(t("search_ph"))}" />
        <div id="bento-results" class="bento-results" role="listbox" hidden></div>
      </div>
      ${layerControls}
    </div>`;
}
function bentoMapTileHTML(name) {
  return `<div class="bento-tile bento-map">${bentoMapSectionHTML(name)}</div>`;
}

// crest monogram initials — strip the "W.P." federal-territory prefix so the
// territory reads by its real name (W.P. Kuala Lumpur → KL, W.P. Putrajaya → P).
function stateInitials(name) {
  return personInitials(String(name || "").replace(/^W\.P\.\s*/i, ""));
}
const STATE_FLAG_ASSETS = Object.freeze({
  "Johor": "assets/state-flags/johor.svg",
  "Kedah": "assets/state-flags/kedah.svg",
  "Kelantan": "assets/state-flags/kelantan.svg",
  "Melaka": "assets/state-flags/melaka.svg",
  "Negeri Sembilan": "assets/state-flags/negeri-sembilan.svg",
  "Pahang": "assets/state-flags/pahang.svg",
  "Perak": "assets/state-flags/perak.svg",
  "Perlis": "assets/state-flags/perlis.svg",
  "Pulau Pinang": "assets/state-flags/penang.svg",
  "Penang": "assets/state-flags/penang.svg",
  "Sabah": "assets/state-flags/sabah.svg",
  "Sarawak": "assets/state-flags/sarawak.svg",
  "Selangor": "assets/state-flags/selangor.svg",
  "Terengganu": "assets/state-flags/terengganu.svg",
  "W.P. Kuala Lumpur": "assets/state-flags/kuala-lumpur.svg",
  "Kuala Lumpur": "assets/state-flags/kuala-lumpur.svg",
  "W.P. Putrajaya": "assets/state-flags/putrajaya.svg",
  "Putrajaya": "assets/state-flags/putrajaya.svg",
  "W.P. Labuan": "assets/state-flags/labuan.svg",
  "Labuan": "assets/state-flags/labuan.svg"
});
function stateFlagAssetFor(name) {
  return STATE_FLAG_ASSETS[String(name || "").trim()];
}
// Sourced emblem art when the manifest is loaded; deterministic monogram fallback
// when the optional file fails or a new state key is missing.
function stateEmblemFor(name) {
  return state.stateEmblems && state.stateEmblems.states && state.stateEmblems.states[name];
}
function stateEmblemHTML(name, cls = "") {
  if (!name) return "";
  const em = stateEmblemFor(name);
  const classes = ["state-emblem", cls].filter(Boolean).join(" ");
  if (em && em.asset) {
    const title = em.title || `${name} emblem`;
    return `<span class="${esc(classes)}" title="${esc(title)}" aria-hidden="true"><img src="${esc(em.asset)}" alt="" loading="lazy" decoding="async"></span>`;
  }
  const d = state.data[bentoMapTier()] || state.data.parlimen || state.data.dun;
  const hue = (d && d.hues && d.hues[name]) || monogramColor(name);
  return `<span class="${esc(classes)} state-emblem-fallback" style="background:${hue}" aria-hidden="true">${esc(stateInitials(name))}</span>`;
}
function stateCrestHTML(name) {
  return stateEmblemHTML(name, "bento-crest");
}

// Dashboard actions live in the nav bar on wide screens. Centre "MyPolitik" title
// is permanent (topbar-context) — only the right-side actions swap for PRN/close.
function renderBentoChrome() {
  const actEl = document.getElementById("topbar-actions");
  if (!actEl) return;
  const name = state.openState || "";
  const e = prnActiveForState(name);
  const election = bentoElectionMode();
  const toggle = e
    ? `<button id="bento-prn-toggle" class="bento-prn-toggle${election ? " on" : ""}" type="button" aria-pressed="${election}">
         <span class="live-dot"></span>🗳️ ${esc(e.name)}
       </button>`
    : "";
  actEl.innerHTML = `${toggle}<button id="bento-close-btn" class="prn-close-btn bento-close" type="button">${esc(t("bento_close"))}</button>`;
  actEl.hidden = false;
}
function hideBentoChrome() {
  const actEl = document.getElementById("topbar-actions");
  if (actEl) { actEl.hidden = true; actEl.innerHTML = ""; }
}

// ---- News (reviewer's most-repeated ask) ----
// A compact strip of the campaign-window headlines already matched per Johor PRN
// candidate (pipeline/06_candidate_news.py → candidate-news-johor.json), aggregated
// + de-duplicated. Headline + source + outbound LINK only — no republished text.
// Empty / sparse data → the strip simply doesn't render (graceful, never destabilises
// the live election view). National + per-constituency news, and a migration to the
// owned Kracked OSINT feed, are the later passes.
function johorNewsItems() {
  const src = state.prnNews;
  if (!src || typeof src !== "object") return [];
  const seen = new Set(), out = [];
  for (const seat of Object.keys(src)) {
    if (seat === "_done" || !src[seat] || typeof src[seat] !== "object") continue;
    for (const cand of Object.keys(src[seat])) {
      const arr = src[seat][cand];
      if (!Array.isArray(arr)) continue;
      for (const n of arr) {
        if (!n || !n.u || !n.t || seen.has(n.u)) continue;
        seen.add(n.u);
        out.push({ t: n.t, u: n.u, s: n.s || "", d: n.d || "", candidate: cand });
      }
    }
  }
  out.sort((a, b) => String(b.d).localeCompare(String(a.d)));
  return out;
}
function newsItemLinkHTML(n, withCand) {
  const meta = [n.s, n.d ? fmtDayMonth(n.d) : "", withCand ? n.candidate : ""]
    .filter(Boolean).map(esc).join(" · ");
  return `<a class="news-link" href="${esc(n.u)}" target="_blank" rel="noopener">
      <span class="news-t">${esc(n.t)}</span>
      <span class="news-meta muted">${meta}</span>
    </a>`;
}
// Full news list on the Johor PRN dashboard (sidebar News nav removed).
function newsStripHTML() {
  const items = johorNewsItems();
  if (!items.length) return "";
  const rows = items.map((n) => `<li>${newsItemLinkHTML(n, true)}</li>`).join("");
  return `<section class="bento-news" id="bento-news" aria-label="${esc(t("news_title"))}">
      <div class="bento-news-head">
        <h3 class="bento-news-title">📰 ${esc(t("news_title"))} · ${items.length}</h3>
      </div>
      <ul class="bento-news-list">${rows}</ul>
      <p class="bento-news-note muted">${esc(t("prn_news_note"))}</p>
      <p class="bento-news-note muted">${esc(t("news_note"))}</p>
    </section>`;
}
// Legacy #news deep-link → open the PRN dashboard and scroll to the news section.
async function openNewsPage() {
  closePoliticians({ silent: true });
  closeNewsPage({ silent: true });
  if (liveElection()) {
    await openPrnMode();
    requestAnimationFrame(() => {
      document.getElementById("bento-news")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
}
function closeNewsPage(options = {}) {
  if (!document.body.classList.contains("news-open")) return;
  document.body.classList.remove("news-open");
  if (NEWS_VIEW) NEWS_VIEW.innerHTML = "";
  syncSidebar();
  if (!options.silent) writeHash();
}

// election tiles — the original PRN dashboard body (unchanged content)
function bentoElectionTilesHTML() {
  const e = liveElection();
  if (!e || !state.prn16) return "";
  const days = prnDaysToPolling(e);
  const liveNow = state.prnLive && (state.prnLive.phase === "live" || state.prnLive.phase === "final");
  const dates = [
    [t("prn_nomination"), fmtDayMonth(e.nomination_day)],
    [t("prn_early"), fmtDayMonth(e.early_voting)],
    [t("prn_polling"), fmtDayMonth(e.polling_day)],
  ].map(([k, v], i) => `<div class="bento-date${i === 2 ? " is-poll" : ""}"><span class="muted">${esc(k)}</span><b>${esc(v)}</b></div>`).join("");

  // countdown + "are you registered?" — ONE long thin strip at the bottom of the bento:
  // blue countdown on the left, periwinkle SPR voter-check on the right, each laid out
  // horizontally so the whole tile is a short bar.
  const countBig = liveNow
    ? `<div class="bento-count-big">${state.prnLive.declared || 0}<span>/${e.total_seats}</span></div>`
    : `<div class="bento-count-big">${days > 0 ? days : 0}<span>${esc(days === 1 ? t("prn_bento_day") : t("prn_bento_days_unit"))}</span></div>`;
  const countCap = liveNow
    ? `<b>${esc(t(state.prnLive.phase === "final" ? "prn_phase_final" : "prn_phase_live"))}</b><span class="muted">${esc(t("prn_polling"))} · ${esc(fmtDayMonth(e.polling_day))}</span>`
    : `<b>${esc(t("prn_bento_to_polling"))}</b><span class="muted">${esc(t("prn_polling"))} · ${esc(fmtDayMonth(e.polling_day))}</span>`;
  const countRegTile = `<div class="bento-tile bento-countreg${liveNow ? " is-live" : ""}">
      <div class="bento-cr-count">${countBig}<div class="bento-cr-cap">${countCap}</div></div>
      <a class="bento-cr-reg" href="${esc(e.check_voter_url)}" target="_blank" rel="noopener">
        <span class="bento-cr-q">${esc(t("prn_bento_register_h"))}</span>
        <span class="bento-reg-cta">${esc(t("prn_check"))}</span>
      </a>
    </div>`;

  return `<div class="bento-grid is-prn">
      ${countRegTile}
      ${bentoMapTileHTML(e.state)}
      <div class="bento-tile bento-stand">
        <div class="bento-kicker">${esc(t("prn_contested"))}</div>
        ${liveNow ? prnLiveTallyHTML() : prnStandingsTileHTML()}
        <p class="bento-maj muted">${esc(t("prn_majority", { n: e.majority }))}</p>
      </div>
      <div class="bento-tile bento-dates">
        <div class="bento-kicker">${esc(t("prn_bento_key_dates"))}</div>
        <div class="bento-dates-row">${dates}</div>
      </div>
      <div class="bento-tile bento-spot" id="bento-spot">
        <div class="bento-kicker">${esc(t("prn_bento_spotlight"))}</div>
        <div id="bento-spot-body">${bentoSpotlightHTML()}</div>
      </div>
    </div>
    ${newsStripHTML()}
    <p class="bento-foot src-line muted">${esc(t("prn_source"))}</p>`;
}

// Leadership card: state identity on the left, current MB/KM/Premier on the right.
// W.P. territories keep the identity half and omit the government half cleanly.
function bentoGovTileHTML(name) {
  const ctx = state.stateCtx;
  const st = ctx && ctx.states && ctx.states[name];
  const g = st && st.gov;
  const gp = state.govPhotos && state.govPhotos[name];
  const govPane = g ? (() => {
    const title = g.title === "MB" ? "Menteri Besar" : g.title === "KM" ? "Ketua Menteri" : g.title;
    const care = g.caretaker ? ` <span class="muted">(${esc(t("ctx_caretaker"))})</span>` : "";
    const since = g.since ? ` <span class="muted">· ${esc(t("bento_gov_since", { y: g.since }))}</span>` : "";
    return `<div class="bento-gov-yb-pane">
      <div class="bento-kicker">${esc(t("bento_gov"))}</div>
      <div class="bento-gov-head">
        ${personPhotoHTML(g.name, gp && gp.photo, "bento-gov-photo")}
        <div class="bento-gov-id">
          <span class="bento-gov-title muted">${esc(title)}${care}</span>
          <strong>${esc(g.name)}</strong>
          <p>${esc(g.party)} <span class="pill" style="${pillStyle(partyColor(g.coalition))}">${esc(g.coalition)}</span>${since}</p>
        </div>
      </div>
    </div>`;
  })() : "";
  return `<div class="bento-tile bento-gov">
    <div class="bento-gov-split${govPane ? "" : " solo"}">
      <div class="bento-gov-emblem-pane">
        <div class="bento-gov-state-name">${esc(name)}</div>
        ${stateEmblemHTML(name, "bento-gov-emblem")}
      </div>
      ${govPane}
    </div>
  </div>`;
}

// generic state tiles — gov · clock · makeup · map · spotlight · econ · records
// seats-by-coalition donut: ring segments in fixed party colours (2px surface gaps),
// total in the centre, identity + counts carried by the text legend beside it
// (never colour-alone — GPS/PH reds are close, the legend is the identity channel)
function donutHTML(ents, total) {
  if (!ents.length || !total) return "";
  // viewBox padded so stroke-width doesn't get clipped at the edge of the card
  const R = 42, SW = 14, C = 2 * Math.PI * R;
  const gap = ents.length > 1 ? 2.5 : 0;
  let acc = 0;
  const segs = ents.map(([coal, n]) => {
    const len = C * n / total;
    const draw = Math.max(len - gap, 0.75);
    const seg = `<circle r="${R}" cx="60" cy="60" fill="none" stroke="${partyColor(coal)}" stroke-width="${SW}" stroke-linecap="butt"
      stroke-dasharray="${draw.toFixed(2)} ${(C - draw).toFixed(2)}" stroke-dashoffset="${(-acc).toFixed(2)}"><title>${esc(coal)} ${n}</title></circle>`;
    acc += len;
    return seg;
  }).join("");
  return `<svg viewBox="0 0 120 120" class="bento-donut-svg" role="img" aria-label="${esc(t("state_makeup"))}" focusable="false">
    <g transform="rotate(-90 60 60)">${segs}</g>
    <text x="60" y="56" text-anchor="middle" dominant-baseline="middle" class="bento-donut-total">${total}</text>
    <text x="60" y="74" text-anchor="middle" class="bento-donut-sub">${esc(t("bento_donut_seats"))}</text>
  </svg>`;
}
function donutLegendHTML(ents, total) {
  const max = Math.max(...ents.map(([, n]) => n));
  return ents.map(([coal, n]) => {
    const lead = n === max;
    const pct = Math.round((n / total) * 100);
    return `<div class="bento-donut-row${lead ? " is-lead" : ""}">
      <span class="sw" style="background:${partyColor(coal)}"></span>
      <span class="bento-donut-name">${esc(coal)}</span>
      <b class="mono">${n}</b>
      ${lead ? `<span class="muted">· ${pct}% · ${esc(t("state_leading_bloc"))}</span>` : ""}
    </div>`;
  }).join("");
}

// FOUR cards: government (top-left) · seats by coalition (top-right) ·
// one explore section holding BOTH the map and the seat spotlight · key numbers
// + economy merged into one stats card.
// Also used for PRN Johor election mode (identical shell; spotlight adds runners).
function bentoStateTilesHTML(name) {
  const st = stateStats(name, bentoMapTier());
  const econ = stateEconRows(name);
  const govTile = bentoGovTileHTML(name);
  const totalSeats = st ? st.seats.length : 0;
  // Same seats-by-coalition donut as the normal state bento (always). During the
  // count, a "who's leading now" line appears under the legend — derived from the
  // live seats (declared/leading per coalition), not the poller's optional .tally.
  const ls = bentoElectionMode() ? prnLiveStats() : null;
  const liveNow = ls && (ls.declared > 0 || ls.leading > 0);
  const liveLine = liveNow
    ? `<div class="bento-live-under muted">${prnLiveTallyHTML()}</div>`
    : "";
  const makeupTile = st
    ? `<div class="bento-tile bento-stand">
         <div class="bento-kicker">${esc(t("state_makeup"))}</div>
         <div class="bento-donut">
           ${donutHTML(st.ents, totalSeats)}
           <div class="bento-donut-legend">${donutLegendHTML(st.ents, totalSeats)}</div>
         </div>
         ${liveLine}
       </div>`
    : "";
  const exploreTile = `<div class="bento-tile bento-explore">
      <div class="bento-explore-inner">
        <div class="bento-explore-map">${bentoMapSectionHTML(name)}</div>
        <div class="bento-explore-spot">
          <div class="bento-kicker">${esc(t("prn_bento_spotlight"))}</div>
          <div id="bento-spot-body">${bentoSpotlightHTML()}</div>
        </div>
      </div>
    </div>`;
  const records = st ? [st.closestStat, st.largestStat, st.turnoutStat, st.candidatesStat].filter(Boolean) : [];
  // PRN mode: bottom card = running candidates for the selected seat (replaces key numbers + economy).
  // Normal state mode: key numbers + economy as before.
  let statsTile = "";
  if (bentoElectionMode()) {
    statsTile = bentoRunnersTileHTML();
  } else if (records.length || econ.rows.length) {
    statsTile = `<div class="bento-tile bento-statsrow">
        <div class="bento-stats-inner">
          ${records.length ? `<div class="bento-records">
            <div class="bento-kicker">${esc(t("bento_records"))}</div>
            <div class="state-stats bento-stats bento-records-grid">${records.join("")}</div>
          </div>` : ""}
          ${econ.rows.length ? `<div class="bento-econ">
            <div class="bento-kicker">${esc(t("bento_econ"))}</div>
            <dl class="rows state-ctx bento-ctx">${econ.rows.join("")}</dl>
            ${econ.src}
          </div>` : ""}
        </div>
      </div>`;
  }
  // election-night: live strip above the grid + 56-seat table above runners
  const liveStrip = bentoElectionMode() ? bentoLiveStripHTML() : "";
  const liveTable = bentoElectionMode() ? bentoLiveTableHTML(name) : "";
  return `${liveStrip}<div class="bento-grid is-state${bentoElectionMode() ? " is-prn-live" : ""}">
      ${govTile}
      ${makeupTile}
      ${exploreTile}
      ${liveTable}
      ${statsTile}
    </div>
    <p class="bento-foot src-line muted">${esc(t(bentoElectionMode() ? "prn_source" : "bento_foot_src"))}</p>`;
}

function renderStateBento() {
  if (!state.openState) return;
  renderBentoChrome();
  // PRN mode uses the SAME four-card state layout as a normal state open
  // (gov · makeup · map+spotlight · key numbers/economy). Election mode only
  // changes the spotlight body (incumbent + 2026 runners) and the DUN map layer —
  // no separate Key-dates / countdown grid.
  let html = bentoStateTilesHTML(state.openState);
  if (bentoElectionMode()) {
    const news = newsStripHTML();
    if (news) {
      // inject news strip above the foot line
      html = html.replace(/(<p class="bento-foot)/, `${news}$1`);
    }
  }
  // render into a display:contents wrapper so re-renders never wipe the
  // fluid-bg layer (a sibling) — wiping it would restart the iframe sim
  let host = document.getElementById("bento-content");
  if (!host) {
    BENTO.insertAdjacentHTML("beforeend", '<div id="bento-content"></div>');
    host = document.getElementById("bento-content");
  }
  host.innerHTML = html;
  observeBentoMap();   // aspect-lock the state-map tile(s) to their rendered size
}

// the seat held by the state's head of government — the DEFAULT spotlight when the
// dashboard opens (a selected seat / deep link still wins). Name-matched within the
// state's own DUN roster; one curated override where the official ballot name is too
// far from the common name to match.
const GOV_SEAT_OVERRIDE = { "Sarawak": "13_N.26" };   // Abang Johari (official: Abang Abdul Rahman Zohari…)
function govSeatOf(name) {
  if (GOV_SEAT_OVERRIDE[name]) return GOV_SEAT_OVERRIDE[name];
  const ctx = state.stateCtx;
  const g = ctx && ctx.states && ctx.states[name] && ctx.states[name].gov;
  if (!g || !g.name) return null;
  const gk = namekeyLoose(g.name);
  if (gk.length < 8) return null;
  const d = state.data.dun;
  if (!d) return null;
  for (const seat of d.seats) {
    if (seat.state !== name) continue;
    const r = seatResultOf(seat, "dun");
    const ad = state.aduns && state.aduns[seat.code];
    for (const n of [r && r.name, ad && ad.name]) {
      if (!n) continue;
      const rk = namekeyLoose(n);
      if (rk.length >= 8 && (rk === gk || rk.includes(gk) || gk.includes(rk))) return seat.code;
    }
  }
  return null;
}

let bentoState = null;   // which state's dashboard is showing (resets the spotlight on change)
function showStateBento(name) {
  if (!name || !BENTO_MQ.matches) return;
  // the explore card searches BOTH layers — fetch the other one in the background
  const other = state.tier === "parlimen" ? "dun" : "parlimen";
  if (!state.data[other]) {
    loadTier(other).then(() => {
      if (bentoState === name && document.body.classList.contains("bento-on")) renderStateBento();
    }).catch(() => {});
  }
  if (bentoState !== name) { bentoSeat = null; bentoTier = null; bentoState = name; }   // fresh state → fresh spotlight + layer
  const d = state.data[state.tier];
  if (!bentoSeat && state.selected && d && d.byCode.has(state.selected)) bentoSeat = state.selected;
  // no seat chosen → spotlight the head of government's own seat by default
  if (!bentoSeat) {
    bentoSeat = govSeatOf(name);
    if (!bentoSeat && !state.data.dun) {
      // DUN roster still loading (opened on the parliament layer) — backfill once it lands
      loadTier("dun").then(() => {
        if (!bentoSeat && bentoState === name && document.body.classList.contains("bento-on")) {
          bentoSeat = govSeatOf(name);
          if (bentoSeat) updateBentoSpotlight();
        }
      }).catch(() => {});
    }
  }
  document.body.classList.add("bento-on");
  BENTO.hidden = false;
  ensureBentoFluid();
  // fresh landing colour per open (the warm element persists across opens)
  randomizeFluidPhase(BENTO.querySelector("fluid-bg"));
  renderStateBento();
}
function hideStateBento() {
  document.body.classList.remove("bento-on");
  BENTO.hidden = true;
  hideBentoChrome();
  // the fluid stays mounted: display:none throttles the iframe but keeps it
  // loaded, so the next open shows the background instantly (no sim reboot)
}
// fluid dashboard background — the fluid-bg web component (jsDelivr, embeds
// fluid.krackeddevs.com as an iframe). Mounted ONCE and kept warm: created at
// boot (desktop only), its shadow iframe flipped from lazy to eager so it loads
// while the bento is still hidden — opening a state then shows the background
// immediately instead of waiting out an iframe + sim boot. Skipped under
// prefers-reduced-motion. z="0" paints it above the page background; the bento
// children lift to z:1 in CSS.
const BENTO_FLUID_HASH = "#p=0.82,1.65,1.9,0.025,1,15,0,1,20.77,0,0,1.5,0,0,14,0,0,0,0,0,0,0,0,0,0.37,0,0,0,3";
// random landing colour: jump the hue journey to a random point in its cycle.
// 72 = the fluid-hue keyframes duration (styles.css); literal on purpose — this
// is called from top-level code above these declarations, so a const here
// would be a TDZ ReferenceError at module evaluation.
function randomizeFluidPhase(el) {
  if (el) el.style.animationDelay = `-${(Math.random() * 72).toFixed(1)}s`;
}
function ensureBentoFluid() {
  if (!BENTO || BENTO.querySelector("fluid-bg")) return;
  if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const el = document.createElement("fluid-bg");
  el.setAttribute("fixed", "");
  el.setAttribute("z", "0");
  el.setAttribute("hash", BENTO_FLUID_HASH);
  randomizeFluidPhase(el);
  BENTO.prepend(el);
  // no eager warm-up: the lazy iframe loads when the bento first becomes visible
  // (showStateBento calls this right as it opens). Keeping the second WebGL sim
  // unloaded until then halves idle GPU/memory for everyone on the plain map.
}
function updateBentoSpotlight() {
  const body = document.getElementById("bento-spot-body");
  if (body) body.innerHTML = bentoSpotlightHTML();
  // PRN bottom tile tracks the same seat as the spotlight
  if (bentoElectionMode()) {
    const runners = document.getElementById("bento-runners-body");
    if (runners) runners.innerHTML = bentoRunnersBodyHTML();
    const tile = BENTO && BENTO.querySelector(".bento-runners .bento-kicker");
    if (tile) {
      const entry = bentoSeat && state.prn16 && state.prn16.seats && state.prn16.seats[bentoSeat];
      const seat = bentoSeat && state.data.dun && state.data.dun.byCode.get(bentoSeat);
      if (seat && entry) {
        tile.textContent = `${entry.ncode || seat.dun_code || ""} · ${seat.name} · ${t("prn_candidates")} · ${entry.candidates.length}`;
      } else {
        tile.textContent = t("prn_candidates");
      }
    }
  }
  BENTO.querySelectorAll(".bento-seat.sel").forEach((p) => p.classList.remove("sel"));
  const p = bentoSeat && BENTO.querySelector(`.bento-seat[data-code="${CSS.escape(bentoSeat)}"]`);
  if (p) p.classList.add("sel");
  // keep the live seat table selection in sync with map / search picks
  BENTO.querySelectorAll(".bento-live-row.is-sel").forEach((r) => r.classList.remove("is-sel"));
  const row = bentoSeat && BENTO.querySelector(`.bento-live-row[data-code="${CSS.escape(bentoSeat)}"]`);
  if (row) {
    row.classList.add("is-sel");
    // reveal the row ONLY within the table's own scroll box — scrollIntoView also
    // scrolls the page, yanking the reader away from the spotlight beside the map
    const scroller = row.closest(".bento-livetable-scroll");
    if (scroller) {
      const target = row.offsetTop - (scroller.clientHeight - row.offsetHeight) / 2;
      scroller.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
    }
  }
}

// bento seat search — type a seat name/code/YB of the OPEN state, pick to spotlight
function bentoSeats() {
  const d = state.data[state.tier];
  return (d && state.openState && d.seats.filter((s) => s.state === state.openState)) || [];
}
// the searchable people attached to a seat: in election mode the 2026 candidates
// (incl. ballot aliases) + the incumbent; otherwise the sitting rep of that tier
function seatPersonOf(seat, tier) {
  const pol = politicianOf(seat, tier);
  if (pol && pol.name) return pol.name;
  const r = seatResultOf(seat, tier);
  return (r && r.name) || "";
}
function bentoSeatPersons(seat) {
  const entry = state.prn16 && state.prn16.seats && state.prn16.seats[seat.code];
  if (!entry) return [];
  const names = entry.candidates.flatMap((c) => [c.name, c.ballot_name].filter(Boolean));
  if (entry.incumbent_2022) names.push(entry.incumbent_2022);
  return names;
}
function bentoResultRow({ seat, tier, who }) {
  return `<button type="button" role="option" class="bento-result" data-code="${esc(seat.code)}"><b>${esc(displayCode(seat, tier) || seat.code)}</b> ${esc(seat.name)}${who ? ` <span class="muted">· ${esc(who)}</span>` : ""}</button>`;
}
function bentoResultsHTML(query) {
  const q = (typeof query === "string" ? query : "").trim().toLowerCase();
  if (!q) return "";
  if (bentoElectionMode()) {
    // election view: the 2026 candidates + incumbents of the contested (DUN) tier
    const seats = bentoSeats();
    const base = searchSeats(seats, q, state.tier);
    const seen = new Set(base.map((s) => s.code));
    const person = [];
    for (const s of seats) {
      if (seen.has(s.code)) continue;
      const hit = bentoSeatPersons(s).find((n) => n.toLowerCase().includes(q));
      if (hit) person.push({ seat: s, tier: state.tier, who: hit });
    }
    const rows = base.map((s) => ({ seat: s, tier: state.tier, who: bentoSeatPersons(s)[0] || "" })).concat(person);
    return rows.slice(0, 8).map(bentoResultRow).join("");
  }
  // state dashboard: BOTH layers of the open state are searchable (MPs and ADUNs),
  // the map's current tier listed first
  const tiers = state.tier === "parlimen" ? ["parlimen", "dun"] : ["dun", "parlimen"];
  const rows = [];
  for (const tier of tiers) {
    const d = state.data[tier];
    if (!d || !state.openState) continue;
    const seats = d.seats.filter((sd) => sd.state === state.openState);
    const base = searchSeats(seats, q, tier);
    const seen = new Set(base.map((sd) => sd.code));
    for (const sd of base) rows.push({ seat: sd, tier, who: seatPersonOf(sd, tier) });
    for (const sd of seats) {
      if (seen.has(sd.code)) continue;
      const who = seatPersonOf(sd, tier);
      if (who && who.toLowerCase().includes(q)) rows.push({ seat: sd, tier, who });
    }
  }
  return rows.slice(0, 8).map(bentoResultRow).join("");
}
function bentoSearchClose() {
  const box = document.getElementById("bento-results");
  if (box) { box.hidden = true; box.innerHTML = ""; }
}
function bentoSearchPick(code) {
  bentoSeat = code;
  updateBentoSpotlight();
  const q = document.getElementById("bento-q");
  if (q) { q.value = ""; q.blur(); }
  bentoSearchClose();
}
// Pointer-only preview: show the hovered district + sitting YB in the search
// field without changing its value, query results, focus, or keyboard behaviour.
// Matches the bento result-row shape (code · place · YB), not the open state name.
function showBentoHoverPreview(path) {
  const q = document.getElementById("bento-q");
  if (!q || q.value || document.activeElement === q) return;
  const tier = bentoMapTier();
  const data = state.data[tier];
  const seat = data && data.byCode.get(path.dataset.code);
  if (!seat) return;
  const who = seatPersonOf(seat, tier);
  const code = displayCode(seat, tier) || seat.code || "";
  const place = seat.name || path.dataset.code || "";
  if (!place && !who) return;
  if (!q.dataset.basePlaceholder) q.dataset.basePlaceholder = q.placeholder || t("search_ph");
  // e.g. "N.59 Belaga · YB Liwan Lagang" — district first, not "Sarawak · …"
  const head = [code, place].filter(Boolean).join(" ");
  q.placeholder = who ? `${head} · YB ${who}` : head;
  q.classList.add("is-hover-preview");
}
function clearBentoHoverPreview() {
  const q = document.getElementById("bento-q");
  if (!q || !q.classList.contains("is-hover-preview")) return;
  q.placeholder = q.dataset.basePlaceholder || t("search_ph");
  delete q.dataset.basePlaceholder;
  q.classList.remove("is-hover-preview");
}
function isBentoBackdropClick(ev) {
  return document.body.classList.contains("bento-on") &&
    BENTO.contains(ev.target) &&
    !ev.target.closest(".bento-tile, .bento-news, .bento-foot, .bento-live-strip");
}

function toggleBentoPrn() {
  const e = prnActiveForState(state.openState);
  if (!e) return;
  if (state.prnMode) {
    prnOptOut = true;          // user said "state view, please" — respect it this visit
    closePrnMode();            // reconciles to the generic dashboard
  } else {
    prnOptOut = false;
    if (state.tier !== e.tier) { openPrnMode(); }   // needs a tier switch — full path
    else { enterPrnMode(); renderStateBento(); writeHash(); }
  }
}
// the dashboard's title/toggle/close live in the fixed topbar
document.getElementById("topbar")?.addEventListener("click", (ev) => {
  if (ev.target.closest("#bento-close-btn")) { backToControls(); return; }
  if (ev.target.closest("#bento-prn-toggle")) toggleBentoPrn();
});
BENTO.addEventListener("click", (ev) => {
  if (handleCandidateCardClick(ev)) return;
  // compact Current-YB strip → full profile modal (bio lives there, not in the bento)
  const ybCard = ev.target.closest(".seat-yb-card[data-pol-code]");
  if (ybCard) {
    // don't steal clicks on links that may still appear (e.g. future external anchors)
    if (ev.target.closest("a")) return;
    openPoliticianModal(ybCard.dataset.polCode, ybCard);
    return;
  }
  if (ev.target.closest("#bento-close-btn")) { backToControls(); return; }   // leave the state entirely
  const prnToggle = ev.target.closest("#bento-prn-toggle");
  if (prnToggle) { toggleBentoPrn(); return; }
  const res = ev.target.closest(".bento-result");
  if (res) { bentoSearchPick(res.dataset.code); return; }
  const tab = ev.target.closest(".prn-pl-tab");
  if (tab) {
    prnPledgeTab = tab.dataset.pledgeTab;
    const host = document.getElementById("bento-pledge-body");
    if (host) host.innerHTML = prnPledgeTabsHTML();
    return;
  }
  const tierChip = ev.target.closest("[data-bento-tier]");
  if (tierChip) {
    if (tierChip.dataset.bentoTier !== bentoMapTier()) {
      bentoTier = tierChip.dataset.bentoTier;
      renderStateBento();   // map + makeup + key numbers follow the chosen layer
    }
    return;
  }
  // live seat table filters
  const liveChip = ev.target.closest("[data-live-filter]");
  if (liveChip) {
    ev.preventDefault();
    ev.stopPropagation();
    setLiveSeatFilter(liveChip.getAttribute("data-live-filter") || liveChip.dataset.liveFilter || "all");
    return;
  }
  // live table row → spotlight (same as map click)
  const liveRow = ev.target.closest(".bento-live-row[data-code]");
  if (liveRow) {
    bentoSeat = liveRow.dataset.code;
    updateBentoSpotlight();
    return;
  }
  const path = ev.target.closest(".bento-seat");
  if (path) { bentoSeat = path.dataset.code; updateBentoSpotlight(); }
  else if (isBentoBackdropClick(ev)) { backToControls(); }
});
BENTO.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter" && ev.key !== " ") return;
  const ybCard = ev.target.closest && ev.target.closest(".seat-yb-card[data-pol-code]");
  if (ybCard && ev.target === ybCard) {
    ev.preventDefault();
    openPoliticianModal(ybCard.dataset.polCode, ybCard);
    return;
  }
  const liveRow = ev.target.closest && ev.target.closest(".bento-live-row[data-code]");
  if (liveRow) {
    ev.preventDefault();
    bentoSeat = liveRow.dataset.code;
    updateBentoSpotlight();
    return;
  }
  handleCandidateCardKeydown(ev);
});
BENTO.addEventListener("mouseover", (ev) => {
  const path = ev.target.closest && ev.target.closest(".bento-seat");
  if (!path || path.contains(ev.relatedTarget)) return;
  showBentoHoverPreview(path);
});
BENTO.addEventListener("mouseout", (ev) => {
  const path = ev.target.closest && ev.target.closest(".bento-seat");
  if (!path || path.contains(ev.relatedTarget)) return;
  clearBentoHoverPreview();
});
BENTO.addEventListener("input", (ev) => {
  if (ev.target.id !== "bento-q") return;
  const box = document.getElementById("bento-results");
  if (!box) return;
  const html = bentoResultsHTML(ev.target.value);
  box.innerHTML = html;
  box.hidden = !html;
});
BENTO.addEventListener("keydown", (ev) => {
  if (ev.target.id !== "bento-q") return;
  if (ev.key === "Enter") {
    const first = document.querySelector("#bento-results .bento-result");
    if (first) { ev.preventDefault(); bentoSearchPick(first.dataset.code); }
  } else if (ev.key === "Escape") {
    ev.target.value = "";
    bentoSearchClose();
  }
});
// let a click register before hiding the dropdown on blur
BENTO.addEventListener("focusout", (ev) => {
  if (ev.target.id === "bento-q") setTimeout(bentoSearchClose, 150);
});
// keep the bento in sync with the viewport crossing the wide breakpoint: any open
// state gets the dashboard on wide screens; narrow lands on the panel underneath
BENTO_MQ.addEventListener("change", () => {
  if (state.openState && BENTO_MQ.matches) showStateBento(state.openState);
  else hideStateBento();
});
// Topbar live-election shortcut beside the theme toggle.
function syncLiveBadge() {
  const el = document.getElementById("live-badge");
  if (!el) return;
  // permanent "PRN Johor 2026" shortcut into the concluded DUN result; hide only
  // while that view is already open so it isn't redundant.
  el.hidden = state.openState === "Johor" && state.tier === "dun";
}

function openStateCard(name) {
  if (!name) return;
  // From the main map (or any open), Johor during election night → PRN mode so
  // DUN seats paint by current live leaders, not GE15 / state-hue colours.
  // openPrnMode switches to DUN, enters PRN, then re-enters here with prnMode on.
  const election = prnActiveForState(name);
  // Opening ANY non-election state cancels an in-flight openPrnMode (setTier await)
  // and leaves PRN chrome — otherwise Sarawak can flash then get replaced by Johor.
  if (!election) {
    prnOpenGen++;
    if (state.prnMode) closePrnMode({ silent: true });
  } else if (!state.prnMode && !prnOptOut && prnUpcomingOrLive(election)) {
    openPrnMode();
    return;
  }
  closeNewsPage({ silent: true });   // opening a state leaves the news full page (no overlap)
  // cancel a pending home→Parliament rebuild so it doesn't yank the layer mid-open
  if (homeTierResetTimer) { clearTimeout(homeTierResetTimer); homeTierResetTimer = null; }
  clearTimeout(stateExitTimer);
  SEATS.classList.remove("returning");
  const firstMap = SVG.getBoundingClientRect();
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
  suppressMapRefit = true;
  try {
    setMapInspect(MOBILE_MAP_INSPECT_MQ.matches);
  } finally {
    suppressMapRefit = false;
  }
  highlightState(name);
  // once the zoom settles, re-pin against the GROUND-TRUTH rendered state bottom (covers
  // any geometry edge case the deterministic pin might miss on an unusual viewport).
  clearTimeout(settleTimer);
  settleTimer = setTimeout(refitMeasured, (ANIM_OFF || REDUCE_MOTION.matches) ? 32 : STATE_ISOLATE_MS + 40);
  // Start the state camera move immediately. The card can compress/rise alongside it,
  // but it must not hold the selected state in place after the click.
  clearTimeout(revealTimer);
  if (!ANIM_OFF && PANEL.classList.contains("empty")) {
    minimizeCard(PANEL_EMPTY);
  }
  revealStateCard({ firstMap, animateState: true });
  // wide screens: the state opens as a bento dashboard (map+panel keep rendering
  // underneath so narrow viewports and resize-down land on a coherent view).
  // PRN auto-enter is handled at the top of openStateCard for all viewports.
  if (BENTO_MQ.matches) showStateBento(name);
  // Ensure live choropleth after isolation (enterPrnMode already paint()s; this
  // covers open when prnMode was already on and live data just arrived).
  if (state.prnMode) paint();
  syncSidebar();
  writeHash();
}
let revealTimer = null, settleTimer = null, stateExitTimer = null;
// deferred DUN→Parliament rebuild after home (see deferHomeTierReset)
let homeTierResetTimer = null;
function revealStateCard(options = {}) {
  const firstMap = options.firstMap || SVG.getBoundingClientRect();
  setPanelView("state");
  syncMapToCard();
  if (options.animateState && state.openState) {
    const lastMap = SVG.getBoundingClientRect();
    setViewBoxPreservingScreen(firstMap, lastMap);
    zoomToState(state.openState, STATE_ISOLATE_MS, DETAIL_POP_EASE_FN);
  } else {
    refitOpenStateMap();
  }
  riseCard(PANEL_STATE, 0);          // the minimize already led; bounce up from the minimized bar
}

// After a mobile district open/close, re-pin the title and reframe the whole
// state into the new map band so the geometry moves with the name.
function reframeMobileStateWithTitle(ms = DETAIL_POP_MS) {
  if (!MOBILE_MAP_INSPECT_MQ.matches || !state.openState) return;
  syncMapToCard();
  syncStageLabelPosition();
  zoomToState(state.openState, (ANIM_OFF || REDUCE_MOTION.matches) ? 0 : ms, DETAIL_POP_EASE_FN);
}

function showDistrict(code) {
  const seat = state.data[state.tier] && state.data[state.tier].byCode.get(code);
  if (!seat) return;
  const wasMapInspect = state.mapInspect;
  const mobileDetail = MOBILE_MAP_INSPECT_MQ.matches;
  state.selected = code;
  // highlight the tapped district on the zoomed-in map
  setSelectedDistrict(code);
  animateCardResize(PANEL_STATE, () => {   // grow/shrink the floating card to fit the detail
    if (wasMapInspect) {
      setMapInspectWithoutRefit(false);
    }
    setPanelView("seat");
    STATE_INFO.innerHTML = stateSeatCardHTML(seat);
    resetStateInfoScroll();
  }, { preserveMapView: true });
  // mobile: title pins under the topbar + map band shrinks — reframe so the
  // state rides up with the title (not left floating mid-band)
  if (mobileDetail) {
    requestAnimationFrame(() => reframeMobileStateWithTitle());
  }
  animateIn(STATE_INFO, 6);   // the district detail swaps into the card under the header
  // a district chosen while the dashboard is up (search, geolocate, deep link)
  // spotlights it there too — the hidden panel stays consistent for resize-down
  if (document.body.classList.contains("bento-on")) {
    bentoSeat = code;
    updateBentoSpotlight();
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
        setMapInspectWithoutRefit(true);
      }, { preserveMapView: true });
      // reverse of district open: title leaves the top pin, map reframes with it
      requestAnimationFrame(() => reframeMobileStateWithTitle());
      writeHash();
      return;
    }
    animateCardResize(PANEL_STATE, () => {   // shrink the floating card back to the make-up size
      setPanelView("state");
      STATE_INFO.innerHTML = stateSummaryHTML(state.openState);
      STATE_INFO.scrollTop = 0;
    }, { preserveMapView: true });
    animateIn(STATE_INFO, 6);
    writeHash();
  } else {
    backToControls();
  }
}

// Home resets the map layer to Parliament — but NOT on the critical path of the
// back gesture. Rebuilding all seat paths is the main lag when leaving a DUN state.
function deferHomeTierReset() {
  if (homeTierResetTimer) {
    clearTimeout(homeTierResetTimer);
    homeTierResetTimer = null;
  }
  const run = () => {
    homeTierResetTimer = null;
    if (state.openState) return;           // user drilled in again
    if (state.tier === "parlimen") return;
    void setTier("parlimen");
  };
  // Wait a frame so overview paint is on screen, then run when idle (or soon).
  requestAnimationFrame(() => {
    if (typeof requestIdleCallback === "function") {
      requestIdleCallback(run, { timeout: 280 });
    } else {
      homeTierResetTimer = setTimeout(run, 60);
    }
  });
}

function backToControls(options = {}) {
  const wasBento = document.body.classList.contains("bento-on");
  const closingState = state.openState;
  const mobile = MOBILE_MAP_INSPECT_MQ.matches;
  // Mobile: snap home instantly (no 220ms zoom + no waiting on isolation cleanup).
  // Desktop panel exit keeps a short zoom; bento uses a center pop.
  const animateStateExit = !mobile && !wasBento && !!closingState && SEATS.classList.contains("isolated")
    && !ANIM_OFF && !REDUCE_MOTION.matches;
  const firstMap = animateStateExit ? SVG.getBoundingClientRect() : null;
  prnOpenGen++;                                     // cancel in-flight openPrnMode (setTier race)
  if (state.prnMode) closePrnMode({ silent: true }); // leaving the state leaves the election view
  hideStateBento();          // leaving the state closes its dashboard
  bentoSeat = null;
  bentoState = null;
  prnOptOut = false;         // a fresh visit re-defaults the election view
  state.mapInspect = false;
  document.body.classList.remove("map-inspect");
  renderMapInspectTray();
  syncMapInspectButton();
  state.selected = null;
  // Always clear openState immediately so chrome/hash aren't stuck mid-exit
  // (desktop animated path used to delay this until the zoom finished).
  state.openState = null;
  setStageLabel(null);
  clearTimeout(revealTimer);
  clearTimeout(settleTimer);
  clearTimeout(stateExitTimer);
  STATE_INFO.style.height = "";   // drop the pinned height for the next open / overview
  STATE_INFO.style.overflowY = "";
  PANEL_EMPTY.getAnimations().forEach((a) => a.cancel());   // clear the held minimize → overview shows full again
  document.body.classList.remove("state-open");
  clearSelectedDistrict();
  highlightState(null);
  SEATS.classList.remove("isolated", "returning");
  setPanelView("overview");
  syncMapToCard();            // state closed → release --map-h, map grows back to full height
  if (wasBento) {
    // full country, centered pop — no lateral camera glide from the last state frame
    setViewBoxNow(FULL.slice());
    requestAnimationFrame(() => {
      syncMapToCard();
      playMapCenterPop();
    });
  } else if (animateStateExit) {
    const lastMap = SVG.getBoundingClientRect();
    setViewBoxPreservingScreen(firstMap, lastMap);
    animateTo(FULL.slice(), STATE_EXIT_MS, STATE_EXIT_EASE_FN);
  } else {
    // mobile / reduced-motion: snap the camera home now
    setViewBoxNow(FULL.slice());
  }
  syncLiveBadge();
  clearMatches();
  setFindStatus(null);
  syncSidebar();
  // Landing defaults: Party mode immediately (cheap paint). Parliament tier is
  // deferred so a DUN→home tap is not blocked by rebuilding every path.
  if (!options.keepLayer) {
    if (state.mode !== "parti") setMode("parti");
    if (state.tier !== "parlimen") deferHomeTierReset();
  }
  writeHash();
}

SEATS.classList.add("overview");   // the main map is always the states overview

STATE_SEATS.addEventListener("click", (e) => {
  const t2 = e.target.closest(".mini-seat");
  if (t2) showDistrict(t2.dataset.code);
});
document.getElementById("state-back")?.addEventListener("click", goBack);
document.getElementById("live-badge")?.addEventListener("click", async () => {
  // shortcut → the Johor DUN (state assembly) result view. Preload the DUN geometry
  // first so setTier shows no loading veil, and skip the map fade so the switch
  // recolours in place and zooms to Johor instead of looking like a reload.
  closePoliticians({ silent: true });
  hideInfo();
  if (state.tier !== "dun") {
    await loadTier("dun");
    skipMapFade = true;
    await setTier("dun");
  }
  if (state.openState !== "Johor") openStateCard("Johor");
  syncSidebar();
  writeHash();
});
PANEL_STATE.addEventListener("click", (e) => {
  if (handleCandidateCardClick(e)) return;
  if (e.target.closest("#prn-open") || e.target.closest("#prn-open-tray")) {
    openPrnMode();
    return;
  }
  if (e.target.closest("#prn-all-candidates")) {
    openAllCandidatesBrowser();
    return;
  }
  // mobile live board: filter chips (All / BN / PH / …)
  const liveChip = e.target.closest("[data-live-filter]");
  if (liveChip) {
    e.preventDefault();
    e.stopPropagation();
    setLiveSeatFilter(liveChip.getAttribute("data-live-filter") || liveChip.dataset.liveFilter || "all");
    return;
  }
  const liveRow = e.target.closest(".bento-live-row[data-code]");
  if (liveRow) {
    showDistrict(liveRow.dataset.code);
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
    e.preventDefault();
    e.stopPropagation();
    setDistrictPickerOpen(!districtPickerOpen());
    return;
  }
  const districtOption = e.target.closest("[data-map-inspect-district]");
  if (districtOption) {
    e.preventDefault();
    e.stopPropagation();
    chooseMapInspectDistrict(districtOption.dataset.mapInspectDistrict);
    return;
  }
  const tab = e.target.closest("[data-seat-tab]");
  if (tab) {
    setSeatTab(tab.dataset.seatTab, true);
    return;
  }
  if (e.target.closest("#share-link, [data-share-link]")) shareLink();
  else if (e.target.closest("#share-card, [data-share-card]")) shareCard(e.target);
  else if (e.target === PANEL_STATE) goBack();   // tap the empty backdrop (behind the state) → step back
});
PANEL_STATE.addEventListener("keydown", (e) => {
  handleCandidateCardKeydown(e);
  if (e.defaultPrevented) return;
  const districtToggle = e.target.closest("#map-inspect-district-toggle");
  if (districtToggle && ["ArrowDown", "ArrowUp"].includes(e.key)) {
    e.preventDefault();
    setDistrictPickerOpen(true, true);
    return;
  }
  if (districtToggle && ["Enter", " "].includes(e.key)) {
    e.preventDefault();
    if (districtPickerOpen()) {
      const list = document.getElementById("map-inspect-district-list");
      const target = list?.querySelector(".map-inspect-option:focus") ||
        list?.querySelector('[aria-selected="true"]') ||
        list?.querySelector(".map-inspect-option");
      chooseMapInspectDistrict(target?.dataset.mapInspectDistrict, true);
    } else {
      setDistrictPickerOpen(true, true);
    }
    return;
  }
  const districtOption = e.target.closest("[data-map-inspect-district]");
  if (districtOption) {
    if (["Enter", " "].includes(e.key)) {
      e.preventDefault();
      chooseMapInspectDistrict(districtOption.dataset.mapInspectDistrict, true);
      return;
    }
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
  if (Date.now() < districtPickerIgnoreCloseUntil) return;
  if (e.target.closest("#map-inspect-district-picker")) return;
  if (districtPickerOpen()) setDistrictPickerOpen(false);
});

// Some state-level YB cards are rendered without the compact bento metadata.
// Keep those cards actionable too by resolving the currently selected seat.
function openFallbackYbBento(e, root, fallbackCode) {
  if (!root.contains(e.target) || e.target.closest("a")) return false;
  const card = e.target.closest(".seat-yb-card");
  if (!card || card.dataset.polCode) return false;
  const code = fallbackCode || state.selected || "";
  if (!code) return false;
  openPoliticianModal(code, card);
  return true;
}
PANEL_STATE.addEventListener("click", (e) => { openFallbackYbBento(e, PANEL_STATE, state.selected); });
// Capture-phase: filter chips must win even if a parent stops bubbling (iOS flex overflow quirks)
if (MAP_INSPECT_TRAY) {
  MAP_INSPECT_TRAY.addEventListener("click", (e) => {
    const liveChip = e.target.closest("[data-live-filter]");
    if (!liveChip || !MAP_INSPECT_TRAY.contains(liveChip)) return;
    e.preventDefault();
    e.stopPropagation();
    setLiveSeatFilter(liveChip.getAttribute("data-live-filter") || "all");
  }, true);
}

BENTO.addEventListener("click", (e) => { openFallbackYbBento(e, BENTO, bentoSeat); });
