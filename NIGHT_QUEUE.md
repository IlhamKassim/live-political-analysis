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
- [ ] (claude) [MV] Geolocation core in lib.js: faithful port of `project()` from pipeline/01_boundaries.py (INCL. the
      `lng>=107` Borneo-shift), `parsePathRings`, `pointInRings` (even-odd), bbox-prefiltered
      `findSeatForLocation(lat,lng,seats)` (point-in-polygon) + haversine `nearestSeat` fallback. Fixture-table tests:
      KLCC, Putrajaya, Penang, JB, **Kuching + KK** (shift branch). `node --test`.
- [ ] (codex) [MV] VERIFY+STRESS geolocation: run fixtures; stress offshore/out-of-country coords, boundary points,
      NaN/garbage, both tiers; confirm PIP hits known seats. Bugs → top.
- [ ] (claude) [MV] `pickInitialLang(saved, navLanguages)` pure fn + tests; wire boot default (BM-first w/ browser
      override — ship the MECHANISM; final taste is Danial's). `node --test`.
- [ ] (codex) [MV] VERIFY+STRESS lang picker: saved-pref wins; ms/en/other/empty nav langs.
- [ ] (claude) [MV] Pure card-format helpers in lib.js surfacing `party_full`, `n_candidates`, `runner_up.votes` + tests.
- [ ] (codex) [MV] VERIFY+STRESS formatters: missing runner-up, 0 votes, 100% turnout, single-candidate seats.

## Phase 2 — The front door (drafts for morning review)
- [ ] (claude) [HVR] "Find your YB": rewrite `#panel-empty` into an action card — hero question, promoted search w/
      plain examples, **📍 Use-my-location** (`#find-location`); demote legend/summary. New `I18N` keys (EN+BM).
- [ ] (codex) [HVR] VERIFY front door: node --check; every new I18N key present in BOTH en+ms; no untranslated strings.
- [ ] (claude) [HVR] Wire geolocation button → `navigator.geolocation` → `findSeatForLocation` → existing `select()`;
      locating/denied/not-found states + always-present "pick manually" fallback.
- [ ] (codex) [HVR] VERIFY+STRESS geo wiring: review denied/unsupported/timeout paths; fallback always reachable. node --check.
- [ ] (claude) [HVR] Enrich `renderPanel` (279-326) with the new fields + a **Share / Copy-link** button (`encodeHash` +
      `navigator.clipboard` + toast). Keep every number's source line (transparency).
- [ ] (codex) [HVR] VERIFY share/deep-link: hash round-trip via lib.test; open-on-load selects the seat; clipboard guarded.
- [ ] (claude) [HVR] Onboarding clarity: actionable empty copy, first-load tap hint (localStorage-dismissed),
      **Skor → "Segera/Soon" pill** (NOT a dead button; Skor STAYS gated), reset discoverability.
- [ ] (codex) [HVR] VERIFY onboarding: confirm Skor stays gated even if scores.json present; localStorage guarded.
- [ ] (claude) [HVR] Mobile-first sheet: draggable/scrollable bottom sheet (`dvh`, peek/expand ~85dvh), ≥44px tap targets,
      find-flow reachable in-sheet.
- [ ] (codex) [HVR] VERIFY mobile: 42vh truncation fixed, tap-target sizes, no horizontal overflow at ≤390px.

## Phase 3 — Growth surface (last/optional)
- [ ] (claude) [HVR] Share IMAGE `drawSeatCard()`: Canvas 2D + `new Path2D(seat.d)` silhouette, 1080×1350,
      `await document.fonts.ready`, `toBlob` → `navigator.share`/download. Reuse `partyColor`, `seat.bbox`.
- [ ] (codex) [HVR] VERIFY card image: bbox→thumbnail transform unit-tested; graceful Copy-link fallback when unsupported.

## Phase 4 — Regression + report (recurring)
- [ ] (codex) [MV] FULL REGRESSION: `node --test public/lib.test.mjs` + `node --check public/app.js` +
      `python3 -m py_compile pipeline/*.py` + `scripts/validate.sh`. All green. Any failure → top task.
- [ ] (codex) Write/refresh `NIGHT_REPORT.md`: every commit, what passed verification, the short **"needs Danial's eyes"** list.

## ♻️ PERPETUAL TAIL — do NOT tick; keeps the night productive
- [ ] (claude) ♻️ CRITIQUE & REPLENISH (NEVER tick — leave in place): when the lists above are drained, FIRST run the
      full regression, THEN audit code + behaviour against the AGENTS.md vision, hunt bugs/regressions/edge-cases, and
      APPEND 3-5 new small tasks ABOVE this line (bugs as top-priority fixes first, then next improvements). Leave THIS
      line so the loop never idles.
