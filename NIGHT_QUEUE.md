# Night Queue — Peta YB · Citizen-First Reframe

GOAL: make **"Find your YB"** the front door (citizen-first), **map-first / score-later**,
amazing-but-simple. Full vision + UNTOUCHABLES + quality regime in **AGENTS.md** — read it.

RULES: one task per round · `[MV]` = machine-verifiable (`node --test`/`node --check`), `[HVR]`
= needs human visual review (note it in the handoff, don't claim visual correctness) · every
build task is followed by its VERIFY+STRESS task · any bug found → add a `[ ]` fix task at the TOP.

## 🔝 Bug fixes (top priority — found in critique round 5, 2026-06-27)
- [x] (claude) [MV] FIX search-throw on boundary-load failure: the `#q` input handler (app.js ~630) does
      `const data = state.data[state.tier]; ... searchSeats(data.seats, q, state.tier)`. On boot, if `render(tier)`
      throws (boundaries file missing/corrupt) `init()` shows the error overlay and `return`s early — but `#q` stays
      in the DOM and interactive, so the FIRST keystroke reads `state.data[state.tier]` (still `undefined`) and throws
      an uncaught `TypeError: Cannot read properties of undefined (reading 'seats')`. Guard the handler with
      `if (!data) return;` immediately after the `const data = …` line (mirror `renderSummary`'s existing
      `if (!data) return;` at ~527), so a failed-boundary page degrades to an inert search box instead of a console
      error. The tooltip `mousemove` handler (~562) shares the shape but is safe (no `.seat` paths exist when render
      failed) — leave it, or guard it too for symmetry; note which in the handoff. `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY+STRESS search-throw fix: simulate boundary failure (temporarily point `loadTier` at a missing
      file or assert `state.data` empty) → typing in `#q` no longer throws; normal load path unchanged (search still
      filters). node --check. Bug → top.

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
- [x] (claude) [MV] Extract the score→colour ramp from `seatValueColor` (app.js ~273-276: `0..100 → hsl(0→130 60% 45%)`)
      into a pure `scoreColor(score)` in `public/lib.js`, have app.js `import` it (no behaviour change), and add
      lib.test.mjs cases: 0→hue 0 (red), 100→hue 130 (green), clamp <0 and >100 to the ends, NaN/non-number/null →
      a neutral fallback. Grows the tested foundation exactly like the partyColor port. `node --test` + `node --check`.
- [ ] (codex) [MV] VERIFY+STRESS scoreColor port: imported ramp byte-identical to the old inline math at 0/25/50/75/100;
      junk/NaN/string/out-of-range → fallback, never a malformed `hsl()`. node --test/--check. Bug → top.
- [x] (claude) [HVR] A11y combobox semantics: confirm `#q` carries `role="combobox"`, `aria-controls="results"`,
      `aria-autocomplete="list"`, and an initial `aria-expanded="false"` in `index.html` (the JS already toggles
      `aria-expanded` + `aria-activedescendant`). Add any missing attribute so screen readers announce the listbox
      relationship — completes the keyboard-nav a11y pass. `node --check public/app.js`.
- [ ] (codex) [HVR] VERIFY combobox a11y: all four attributes present on `#q`; `aria-controls` id matches `#results`;
      `aria-expanded` flips true/false with the dropdown. node --check.

## Phase 7 — Critique round 3 (replenished 2026-06-27 · full regression GREEN: 56 tests pass, node --check app.js+lib.js + py_compile OK — no bugs found; these are edge-case hardening + tested-foundation growth + share-link craft)
- [x] (claude) [MV] HARDEN out-of-country geolocation (honest "no match"): `nearestSeat` (lib.js) returns the closest seat
      at ANY distance, so `locate()` (app.js ~787 `findSeatForLocation(...) || nearestSeat(...)`) silently drops a user who
      is abroad (Singapore/Indonesia/elsewhere) onto a random Malaysian border seat instead of showing `loc_notfound`. Add an
      optional `maxKm` param to `nearestSeat(lat,lng,seats,maxKm)` (default `Infinity` → no behaviour change for existing
      callers/tests) that returns `null` when the closest seat's representative point is farther than `maxKm`; pass a sane
      bound from `locate()` (~150 km covers genuine offshore islands without claiming a match for far-away points). Add
      lib.test cases: a KK-offshore point still matches; a London / far-abroad point → null with a finite small maxKm; the
      default (no maxKm) keeps the current closest-seat behaviour. `node --test` + `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY+STRESS geo distance guard: confirm offshore-but-near points still resolve, far/out-of-country
      coords now return null (→ `loc_notfound`, fallback search still reachable), default maxKm unchanged vs old tests,
      NaN/garbage still null. `node --test` + `node --check`. Bug → top.
- [x] (claude) [MV] I18N parity foundation: extract the `I18N` table (app.js ~45-136) into a new DOM-free module
      `public/i18n.js` that `export`s it, and have app.js `import { I18N } from "./i18n.js"` (no behaviour change — same keys,
      same strings, zero new deps / no build step, it's a plain static ES module like lib.js). Then add lib.test.mjs cases
      that import it and assert: `en` and `ms` have IDENTICAL key sets (catches "added an EN key, forgot the BM translation"),
      and no value is an empty/whitespace-only string. Grows the tested foundation to guard the untranslated-key regression
      class. `node --test` + `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY i18n parity foundation: confirm app.js still loads (node --check), every existing I18N key/string
      is byte-identical to before the move (no copy drift), the new parity test fails if you delete one BM key. Bug → top.
- [x] (claude) [HVR] Honest deep-link hash: when a deep-linked mode is gated/unavailable, boot (app.js ~944 `setMode(h.mode)`)
      silently no-ops (the button is disabled) but the URL still reads e.g. `#parlimen/skor` while the active mode is `negeri`,
      so a re-shared link misrepresents state. After the boot mode/code restore (~948), call `writeHash()` once so the URL
      reflects the actually-active tier/mode/selection (the shareable link is the growth engine — keep it truthful). Confirm
      no extra history entry (writeHash uses `replaceState`). `node --check public/app.js`.
- [ ] (codex) [HVR] VERIFY honest deep-link hash: load `#parlimen/skor` (Skor gated) → URL normalises to the active mode, no
      stale `skor`; a valid `#dun/parti/<code>` deep-link still selects + keeps its hash; bad seat code still ignored cleanly;
      no duplicate history entry. `node --check`. Bug → top.

## Phase 8 — Critique round 4 (replenished 2026-06-27 · full regression GREEN: 60 tests pass, node --check app.js+lib.js+i18n.js + py_compile OK — audit found NO bugs. Verified two suspected issues are non-bugs: GE15 `runner_up.party` is a COALITION code ("BN") so the runner-up pill colours correctly, and DUN `code` ("10_N.01") contains `dun_code` ("N.01") as a substring so search-by-DUN-code already matches. These are tested-foundation growth + link-preview growth craft.)
- [x] (claude) [MV] Extract the inline search filter (app.js ~631 `data.seats.filter(s => name||code||state includes q)`) into a pure
      `searchSeats(seats, query, tier)` in `public/lib.js` and have app.js `import` + call it (NO behaviour change — same predicate,
      same file order, app.js still slices `.slice(0,8)`/`.slice(0,60)` and does the DOM dim/match highlighting). Search is the one core
      citizen interaction with NO unit tests today. Match case-insensitively on `name`, `code`, `state`; ALSO match DUN seats on their
      visible `dun_code` and their `parlimen` code (so a citizen can find a DUN by its parliamentary constituency). Add lib.test cases:
      empty/whitespace query → `[]`; case-insensitive name/code/state substring; DUN `dun_code`/`parlimen` match; non-array seats / null
      query → `[]` (no throw). Grows the tested foundation. `node --test` + `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY+STRESS searchSeats port: confirm the dropdown + map highlight are byte-identical to the old inline filter on
      real data (same seats, same order); empty/whitespace/garbage/non-string query → `[]` with no throw; DUN dun_code + parlimen matches
      resolve; node --test/--check. Bug → top.
- [x] (claude) [HVR] Link-preview growth: the `<head>` has `<title>` + `<meta name="description">` but NO Open Graph / Twitter Card tags,
      so a shared deep-link (the growth engine) renders a bare URL in WhatsApp/Twitter/FB. Add static `og:title`, `og:description`,
      `og:type=website`, `og:site_name=MyPolitik`, `og:image` (point at an existing `public/` asset — reuse the favicon/icon if no social
      image exists; note it in the handoff for Danial to swap a 1200×630 card later), `twitter:card=summary_large_image`,
      `twitter:title`, `twitter:description`, plus a `<meta name="theme-color">` matching the dark app chrome for mobile polish. Wire
      og:title/description to I18N via `data-i18n-content` where it mirrors an existing key (e.g. `title`/`meta_desc`) so the toggle keeps
      them translated; KEEP zero-dep / no build step. Markup-only → `node --check public/app.js` (sanity) + note it's HVR (Danial's eye on
      the rendered preview). List every tag added in the handoff.
- [ ] (codex) [HVR] VERIFY link-preview meta: every new og:/twitter: tag present and well-formed; `og:image` path resolves to a real file
      under `public/`; data-i18n-content tags carry a key that exists in BOTH en+ms; `theme-color` present; no duplicate `<title>`/desc;
      node --check. Bug → top.

## Phase 9 — Critique round 5 (replenished 2026-06-27 · full regression GREEN: 69 tests pass, node --check app.js+lib.js+i18n.js + py_compile OK, JSON.parse OK, GE15 tally PH82·PN74·BN30·GPS23·GRS6·WARISAN3+others=222 verified. validate.sh's only failures are `/tmp` log-write permission denials in this sandbox — every underlying check passes when run directly. Audit found ONE defensive bug (queued at top) + these tested-foundation/DRY items.)
- [x] (claude) [MV] Extract the seat→key helpers into lib.js + tests: the `tier === "parlimen" ? seat.code : seat.parlimen`
      RESULT join-key is duplicated 5× (app.js ~176, ~181, ~276, ~381, ~566) and the citizen-visible `tier === "parlimen"
      ? seat.code : seat.dun_code` DISPLAY code 2× (~565, ~639). Add pure `resultKey(seat, tier)` (parlimen→`seat.code`,
      dun→`seat.parlimen`) and `displayCode(seat, tier)` (parlimen→`seat.code`, dun→`seat.dun_code`) to `public/lib.js`,
      `import` them into app.js and replace every inline ternary (NO behaviour change — same value at every call site).
      Add lib.test cases: parlimen tier returns `code` for both; dun tier returns `parlimen`/`dun_code` respectively;
      missing seat / missing field → faithful `undefined`/null (no throw); non-"parlimen" tier strings treated as dun
      (matches the existing `=== "parlimen"` test). Grows the tested foundation + removes 7 copies of the join-key rule.
      `node --test` + `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY+STRESS resultKey/displayCode port: confirm panel/seat-fill/tooltip/share-card/search all resolve
      byte-identical keys to the old inline ternaries on real parlimen + DUN data; missing fields → no throw; node --test/--check. Bug → top.
- [x] (claude) [MV] Pin the GE15 coalition tally in a unit test: extract the legend bloc counter (app.js ~542
      `for (const v of Object.values(state.results)) counts[v.coalition] = (counts[v.coalition]||0)+1`) into a pure
      `tallyCoalitions(results)` in `public/lib.js` returning `{coalition: count}` (null/non-object/empty → `{}`, skips
      rows with a missing/blank coalition), `import` it into `renderSummary` (no behaviour change). Add a lib.test that
      loads `public/data/results-ge15.json` via `node:fs` and asserts the AGENTS.md UNTOUCHABLE invariant — PH 82, PN 74,
      BN 30, GPS 23, GRS 6, WARISAN 3, and a 222 grand total — so any future data edit that breaks the tally fails CI here
      (the validate.sh tally check can't write its `/tmp` log in this sandbox; this gives a node --test-native guard).
      Plus a synthetic-input case (null/`{}`/missing-coalition rows → `{}` / skipped). `node --test` + `node --check`.
- [ ] (codex) [MV] VERIFY tallyCoalitions: legend bloc bar/key still render identical counts to the old inline tally; the
      new GE15-invariant test fails if you mutate one seat's coalition; null/garbage results → `{}` no throw. node --test/--check. Bug → top.

## Phase 10 — Critique round 6 (replenished 2026-06-27 · full regression GREEN: 79 tests pass, node --check app.js+lib.js+i18n.js + py_compile OK. GE15 tally invariant test still green (PH82·PN74·BN30·GPS23·GRS6·WARISAN3 = 222). validate.sh's only failures remain the sandbox `/tmp` log-write denials — every underlying check passes run directly. Audit found ONE real Escape double-action bug + ONE latent guardrail-violation + tested-foundation/link-preview craft.)
- [x] (claude) [MV] FIX Escape double-action (bug): pressing Escape inside the search box `#q` to clear the query ALSO
      deselects the current seat. The `#q` keydown Escape branch (app.js ~668 `{ Q.value=""; hideResults(); clearMatches(); }`)
      clears search but does NOT `stopPropagation`, so the event bubbles to the document-level keydown (~836
      `if (e.key==="Escape" && state.selected) deselect()`) which zooms out + collapses the panel — ONE Escape, TWO actions.
      Repro: click a seat (selected, zoomed) → click into `#q` and type → press Escape → search clears AND the seat
      deselects/zooms out unexpectedly. Fix: in the `#q` Escape branch call `e.stopPropagation()` (ONLY there — leave the
      arrow/Enter branches untouched) so Escape in the search clears the dropdown/query first without nuking the selection;
      a second Escape (focus outside `#q`) still deselects via the global handler. `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY+STRESS Escape fix: seat selected + typing in `#q` → Escape clears search only (seat stays
      selected/zoomed); Escape with empty search + seat selected (focus outside `#q`) still deselects; arrow/Enter result
      nav unchanged; no JS error on empty results. `node --check`. Bug → top.
- [x] (claude) [MV] HARDEN Skor gating (guardrail): AGENTS.md UNTOUCHABLE says **"Keep Skor GATED ('Soon') even if
      scores.json appears"**, but `loadOptional()` (app.js ~124-127) calls `enableMode("skor")` the moment a
      `data/scores.json` fetch succeeds — removing `disabled` + the title so the gated tab becomes clickable (and a
      `#parlimen/skor` deep-link would then activate it). That directly contradicts the guardrail. scores.json does NOT
      exist today so nothing breaks now — this is defensive. Fix: stop un-gating skor on data presence — still load
      `state.scores` (the panel score row + `seatValueColor` skor branch keep working) but NEVER light the mode button:
      either drop the `enableMode("skor")` call or make `enableMode` ignore `"skor"`. Leave `enableMode("parti")` unchanged.
      Add a one-line comment citing the untouchable. `node --check public/app.js` (behavioural — note it in the handoff).
- [ ] (codex) [MV] VERIFY Skor stays gated: drop a synthetic `data/scores.json` in → Skor tab STAYS `disabled` + keeps its
      "Soon/Segera" pill; `#parlimen/skor` deep-link does NOT activate skor (normalises away per the honest-deep-link rule);
      `parti` still enables when results load. `node --check`. Bug → top.
- [x] (claude) [MV] Extract `stateHues(seats)` (app.js ~93-105) into a pure DOM-free `stateHues(seats)` in `public/lib.js`,
      `import` it into app.js (NO behaviour change — same golden-angle 137.508° hue spacing, same `i%3`/`i%2` sat/light
      jitter, same sorted-unique state order). It's the LAST pure helper still inline in app.js. Add lib.test.mjs cases:
      deterministic + stable (same seats array → byte-identical `{state: hsl(...)}` map); distinct states get distinct hues;
      empty / non-array seats → `{}` (no throw); an entry with a missing `state` doesn't crash. Grows the tested foundation
      per the regime (every pure fn ships WITH tests). `node --test` + `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY+STRESS stateHues port: legend swatches + `negeri`-mode seat fills are byte-identical to the old
      inline hues on real parlimen + DUN data; empty/garbage seats → `{}` no throw; same colour for the same state across
      reloads. `node --test` + `node --check`. Bug → top.
- [x] (claude) [HVR] Link-preview completeness: the `<head>` has og:title/description/image/type/site_name + twitter card
      tags but NO `og:url` (the canonical link many unfurlers require) and no image-alt. Add static `<meta property="og:url">`
      (the deployed site origin — note it for Danial to confirm the final domain), `og:image:alt` + `twitter:image:alt`
      describing the share card, and `<meta property="og:locale" content="en_MY">` matching the default copy. Keep zero-dep /
      no build step; markup-only → `node --check public/app.js` (sanity) + HVR note (Danial eyes the rendered unfurl). List
      every tag added in the handoff.
- [ ] (codex) [HVR] VERIFY link-preview additions: `og:url`/`og:image:alt`/`twitter:image:alt`/`og:locale` present +
      well-formed; no duplicate tags; existing og/twitter/title/desc tags intact; `og:image` path still resolves under
      `public/`. `node --check`. Bug → top.

## Phase 11 — Critique round 7 (replenished 2026-06-27 · full regression GREEN: 85 tests pass, node --check app.js+lib.js+i18n.js + py_compile OK. GE15 tally invariant test green. validate.sh's only failures remain the sandbox `/tmp` log-write denials — every underlying check passes run directly. Audit found NO active bugs; combobox a11y is complete (#q role=combobox + aria-controls→#results role=listbox), both og:image/icon assets resolve under public/assets/. These are latent-landmine hardening + dead-code cleanup + tested-foundation growth.)
- [x] (claude) [MV] HARDEN i18n-shadow (latent landmine): the SVG `mousemove` (app.js ~551) and `click` (~576) handlers each
      open with `const t = e.target;`, which SHADOWS the module-level `t()` i18n translation fn (app.js ~56) inside those
      blocks. Safe today — neither handler calls `t("...")` — but it is a trap: the moment anyone adds a translated string to
      the tooltip or click path, `t("key")` throws `TypeError: t is not a function`. Rename BOTH locals from `t` to `tgt`
      (and update their in-block uses: `t.classList`/`t.dataset.code` → `tgt.classList`/`tgt.dataset.code`) so the i18n fn is
      always reachable. NO behaviour change. `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY i18n-shadow fix: confirm both handlers reference `tgt` (no remaining `const t = e.target`),
      tooltip + seat-click still resolve seat by `dataset.code`, no other `t` reference broke; node --check. Bug → top.
- [ ] (claude) [MV] Remove dead `row()` helper (app.js ~258-260): `function row(dt, dd, mono=false)` is defined but NEVER
      called — `renderPanel` builds its `<dt>/<dd>` rows inline via template strings (and the empty-panel `#summary`/legend
      build their own markup). Delete the unused function (and its one-line lead comment if any). Pure dead-code cleanup,
      no behaviour change, shrinks the surface. `node --check public/app.js`.
- [ ] (codex) [MV] VERIFY row() removal: confirm `grep -n "row(" public/app.js` shows no orphan call site, renderPanel
      still emits the same rows (compare the rendered `<dl>` shape), node --check. Bug → top.
- [ ] (claude) [MV] Tested-foundation: automate the markup-key parity check. Today the "every `data-i18n*` attribute names a
      real I18N key" invariant is verified by HAND each round (AGENT_LOG: "all 29 data-i18n* markup keys resolve"). Add a
      lib.test.mjs case that reads `public/index.html` via `node:fs` (same `readFileSync(new URL(...))` pattern the existing
      data tests use), regex-extracts every `data-i18n`, `data-i18n-ph`, `data-i18n-title`, `data-i18n-aria`,
      `data-i18n-content`, `data-i18n-after` attribute VALUE, and asserts each extracted key exists in BOTH `I18N.en` and
      `I18N.ms` (import `I18N` from `./i18n.js`). Fails loudly if a future markup edit references a missing/untranslated key.
      Grows the tested foundation; guards the silent-untranslated-markup regression class. `node --test` + `node --check`.
- [ ] (codex) [MV] VERIFY markup-key parity test: confirm the new test passes on current HTML, and FAILS if you (a) add a
      bogus `data-i18n="nope"` to index.html or (b) delete one of the referenced keys from i18n.js (en OR ms). node --test/--check. Bug → top.

## ♻️ PERPETUAL TAIL — do NOT tick; keeps the night productive
- [ ] (claude) ♻️ CRITIQUE & REPLENISH (NEVER tick — leave in place): when the lists above are drained, FIRST run the
      full regression, THEN audit code + behaviour against the AGENTS.md vision, hunt bugs/regressions/edge-cases, and
      APPEND 3-5 new small tasks ABOVE this line (bugs as top-priority fixes first, then next improvements). Leave THIS
      line so the loop never idles.
