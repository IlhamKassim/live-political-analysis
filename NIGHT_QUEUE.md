# Night Queue — Peta YB · Citizen-First Reframe

GOAL: make **"Find your YB"** the front door (citizen-first), **map-first / score-later**,
amazing-but-simple. Full vision + UNTOUCHABLES + quality regime in **AGENTS.md** — read it.

RULES: one task per round · `[MV]` = machine-verifiable (`node --test`/`node --check`), `[HVR]`
= needs human visual review (note it in the handoff, don't claim visual correctness) · every
build task is followed by its VERIFY+STRESS task · any bug found → add a `[ ]` fix task at the TOP.

## Phase B — Brand rename → MyPolitik (do first; user request)
- [x] (claude) [HVR] BRAND RENAME → **MyPolitik**: replace the "PETAYB" / "Peta YB" brand mark + tagline in the
      `index.html` header (`.brand`) and `#panel-empty`, the `<title>`, and any brand strings in `I18N` (both EN+BM)
      with **MyPolitik** (Malaysian "My" + *politik*). KEEP folder/worker/deploy names (`peta-yb`/`politics`) unchanged
      — infra only. List every string changed in the handoff.
- [ ] (codex) [MV] VERIFY brand: `grep -rni "petayb\|peta yb" public/` shows no user-facing leftovers; `<title>` updated;
      `node --check public/app.js`. Any leftover → fix task at top.

## Phase 0 — Testable foundation (keystone)
- [x] (claude) [MV] Create `public/lib.js` (DOM-free ES module) + `public/lib.test.mjs` (Node `node --test`,
      zero-dep). Refactor `writeHash`/`parseHash` (app.js ~470-481) into pure `encodeHash`/`decodeHash`;
      `import` them into app.js. No behaviour change. Run `node --test public/lib.test.mjs` + `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY+STRESS Phase 0: run node --test + node --check; break encode/decode with junk/empty/extra-field
      hashes; confirm app.js imports cleanly. Any bug → fix task at top.

## Phase 1 — The brain (machine-verified)
- [x] (claude) [MV] Geolocation core in lib.js: faithful port of `project()` from pipeline/01_boundaries.py (INCL. the
      `lng>=107` Borneo-shift), `parsePathRings`, `pointInRings` (even-odd), bbox-prefiltered
      `findSeatForLocation(lat,lng,seats)` (point-in-polygon) + haversine `nearestSeat` fallback. Fixture-table tests:
      KLCC, Putrajaya, Penang, JB, **Kuching + KK** (shift branch). `node --test`.
- [ ] (codex) [MV] VERIFY+STRESS geolocation: run fixtures; stress offshore/out-of-country coords, boundary points,
      NaN/garbage, both tiers; confirm PIP hits known seats. Bugs → top.
- [x] (claude) [MV] `pickInitialLang(saved, navLanguages)` pure fn + tests; wire boot default (BM-first w/ browser
      override — ship the MECHANISM; final taste is Danial's). `node --test`.
- [ ] (codex) [MV] VERIFY+STRESS lang picker: saved-pref wins; ms/en/other/empty nav langs.
- [x] (claude) [MV] Pure card-format helpers in lib.js surfacing `party_full`, `n_candidates`, `runner_up.votes` + tests.
- [ ] (codex) [MV] VERIFY+STRESS formatters: missing runner-up, 0 votes, 100% turnout, single-candidate seats.

## Phase 2 — The front door (drafts for morning review)
- [x] (claude) [HVR] "Find your YB": rewrite `#panel-empty` into an action card — hero question, promoted search w/
      plain examples, **📍 Use-my-location** (`#find-location`); demote legend/summary. New `I18N` keys (EN+BM).
- [ ] (codex) [HVR] VERIFY front door: node --check; every new I18N key present in BOTH en+ms; no untranslated strings.
- [x] (claude) [HVR] Wire geolocation button → `navigator.geolocation` → `findSeatForLocation` → existing `select()`;
      locating/denied/not-found states + always-present "pick manually" fallback.
- [ ] (codex) [HVR] VERIFY+STRESS geo wiring: review denied/unsupported/timeout paths; fallback always reachable. node --check.
- [x] (claude) [HVR] Enrich `renderPanel` (279-326) with the new fields + a **Share / Copy-link** button (`encodeHash` +
      `navigator.clipboard` + toast). Keep every number's source line (transparency).
- [ ] (codex) [HVR] VERIFY share/deep-link: hash round-trip via lib.test; open-on-load selects the seat; clipboard guarded.
- [x] (claude) [HVR] Onboarding clarity: actionable empty copy, first-load tap hint (localStorage-dismissed),
      **Skor → "Segera/Soon" pill** (NOT a dead button; Skor STAYS gated), reset discoverability.
- [ ] (codex) [HVR] VERIFY onboarding: confirm Skor stays gated even if scores.json present; localStorage guarded.
- [x] (claude) [HVR] Mobile-first sheet: draggable/scrollable bottom sheet (`dvh`, peek/expand ~85dvh), ≥44px tap targets,
      find-flow reachable in-sheet.
- [ ] (codex) [HVR] VERIFY mobile: 42vh truncation fixed, tap-target sizes, no horizontal overflow at ≤390px.

## Phase 3 — Growth surface (last/optional)
- [x] (claude) [HVR] Share IMAGE `drawSeatCard()`: Canvas 2D + `new Path2D(seat.d)` silhouette, 1080×1350,
      `await document.fonts.ready`, `toBlob` → `navigator.share`/download. Reuse `partyColor`, `seat.bbox`.
- [ ] (codex) [HVR] VERIFY card image: bbox→thumbnail transform unit-tested; graceful Copy-link fallback when unsupported.

## Phase 4 — Regression + report (recurring)
- [ ] (codex) [MV] FULL REGRESSION: `node --test public/lib.test.mjs` + `node --check public/app.js` +
      `python3 -m py_compile pipeline/*.py` + `scripts/validate.sh`. All green. Any failure → top task.
- [ ] (codex) Write/refresh `NIGHT_REPORT.md`: every commit, what passed verification, the short **"needs Danial's eyes"** list.

## Phase 5 — Critique round 1 (replenished 2026-06-27 23:30 UTC; full regression GREEN — no bugs found, these are hardening/craft)
- [x] (claude) [MV] Move the pure colour mapping into lib.js: export `partyColor(coalition)` + the `COALITION_COLORS`
      table from `public/lib.js` (currently inline in app.js ~40-46), have app.js `import` it (no behaviour change),
      and add unit tests in lib.test.mjs — every GE15 coalition (PH/PN/BN/GPS/GRS/WARISAN) maps to its colour,
      case-insensitive, unknown/empty/null/undefined → the `#5d6b7d` fallback. Strengthens the testable foundation
      (regime: every pure fn ships WITH tests). `node --test` + `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY+STRESS partyColor port: run node --test/--check; confirm the imported colours are byte-identical
      to the old inline table (no swatch drift in legend/pills/share-card); junk/mixed-case/non-string input → fallback. Bug → top.
- [x] (claude) [MV] Harden `renderPanel` numeric rows against partial result data by reusing the existing
      `formatResultCard` Number.isFinite guards (lib.js) for votes/majority/turnout, so a row with `vote_pct` present
      but `votes` missing can never render "NaN" (real GE15 data is complete today — this is defensive for future/DUN
      data). Add a lib.test case asserting formatResultCard drops non-finite numerics. `node --test` + `node --check`.
- [ ] (codex) [MV] VERIFY+STRESS panel hardening: synthetic rows (pct-without-votes, majority-without-pct, NaN/string
      numerics) render clean rows or omit them — never "NaN"/"undefined". node --check. Bug → top.
- [x] (claude) [HVR] Search-results keyboard nav: in the `#results` listbox, ↑/↓ move a `.active` highlight through the
      option buttons (wrap at ends), Enter selects the HIGHLIGHTED option (not just the first), Escape still clears;
      set `aria-activedescendant` on `#q` + `id`s on options so screen readers announce the focused row. Completes the
      accessibility pass. `node --check public/app.js`.
- [ ] (codex) [HVR] VERIFY search keyboard nav: ↑/↓ wrap, Enter picks the highlighted seat, Escape clears, no JS error
      on empty results; aria-activedescendant clears when the dropdown hides. node --check.

## Phase 6 — Critique round 2 (replenished 2026-06-27 · full regression GREEN: 53 tests pass, node --check + py_compile OK)
- [x] (claude) [HVR] FIX stale-result Enter (bug): `hideResults()` (app.js ~711) hides `#results` but never clears
      `RESULTS.innerHTML`, and the empty-input / Escape / post-selection paths leave the old option buttons in the DOM.
      The `#q` Enter handler (~754) has NO `RESULTS.hidden` guard (unlike ArrowUp/Down), so pressing Enter after Escape
      or after a selection re-clicks `opts[0]` and reselects a STALE seat. Fix: guard Enter with `if (RESULTS.hidden) return;`
      (mirror the arrow keys) — and/or clear `RESULTS.innerHTML` in `hideResults()` so stale options can't be announced
      or clicked. `node --check public/app.js`.
- [ ] (codex) [HVR] VERIFY stale-Enter fix: search→Escape→Enter does NOT select; search→click a result→Enter (empty box)
      does NOT reselect; ↑/↓+Enter still picks the highlighted seat; empty results → no JS error. node --check. Bug → top.
- [ ] (claude) [MV] Extract the score→colour ramp from `seatValueColor` (app.js ~273-276: `0..100 → hsl(0→130 60% 45%)`)
      into a pure `scoreColor(score)` in `public/lib.js`, have app.js `import` it (no behaviour change), and add
      lib.test.mjs cases: 0→hue 0 (red), 100→hue 130 (green), clamp <0 and >100 to the ends, NaN/non-number/null →
      a neutral fallback. Grows the tested foundation exactly like the partyColor port. `node --test` + `node --check`.
- [ ] (codex) [MV] VERIFY+STRESS scoreColor port: imported ramp byte-identical to the old inline math at 0/25/50/75/100;
      junk/NaN/string/out-of-range → fallback, never a malformed `hsl()`. node --test/--check. Bug → top.
- [ ] (claude) [HVR] A11y combobox semantics: confirm `#q` carries `role="combobox"`, `aria-controls="results"`,
      `aria-autocomplete="list"`, and an initial `aria-expanded="false"` in `index.html` (the JS already toggles
      `aria-expanded` + `aria-activedescendant`). Add any missing attribute so screen readers announce the listbox
      relationship — completes the keyboard-nav a11y pass. `node --check public/app.js`.
- [ ] (codex) [HVR] VERIFY combobox a11y: all four attributes present on `#q`; `aria-controls` id matches `#results`;
      `aria-expanded` flips true/false with the dropdown. node --check.

## ♻️ PERPETUAL TAIL — do NOT tick; keeps the night productive
- [ ] (claude) ♻️ CRITIQUE & REPLENISH (NEVER tick — leave in place): when the lists above are drained, FIRST run the
      full regression, THEN audit code + behaviour against the AGENTS.md vision, hunt bugs/regressions/edge-cases, and
      APPEND 3-5 new small tasks ABOVE this line (bugs as top-priority fixes first, then next improvements). Leave THIS
      line so the loop never idles.
