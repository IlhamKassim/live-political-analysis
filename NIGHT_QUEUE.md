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
- [ ] (claude) [HVR] Link-preview growth: the `<head>` has `<title>` + `<meta name="description">` but NO Open Graph / Twitter Card tags,
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

## ♻️ PERPETUAL TAIL — do NOT tick; keeps the night productive
- [ ] (claude) ♻️ CRITIQUE & REPLENISH (NEVER tick — leave in place): when the lists above are drained, FIRST run the
      full regression, THEN audit code + behaviour against the AGENTS.md vision, hunt bugs/regressions/edge-cases, and
      APPEND 3-5 new small tasks ABOVE this line (bugs as top-priority fixes first, then next improvements). Leave THIS
      line so the loop never idles.
