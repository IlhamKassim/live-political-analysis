# Agent Coordination — MyPolitik (VPS night shift)

**MyPolitik** (folder `peta-yb`, deploys as "politics") — interactive map of every Malaysian
Parliament/DUN seat. Static `public/` app (vanilla JS, no build) + tiny CF Worker.

**This is a VPS sandbox copy for autonomous overnight work.** It does NOT deploy and is separate
from the laptop working copy. All work lands on the `night/<date>` branch for morning review — never master.

## The vision we're building toward (read this — it's the north star)
Reframe from an *explorer's map* into a **citizen-first** tool whose hero is **"Find your YB"**:
a citizen wants ONE answer — "who represents me?" Search your area or "📍 use my location" → fly to
your seat → a beautiful, shareable card. The map is the *reward*, not the gate.
- **Map-first, score-later** — do NOT build the performance score; keep "Skor" gated as "Soon".
- **Amazing but simple = simple in STRUCTURE, amazing in CRAFT.** One find-action, one map, one card.
- Mobile-first, link-first; shareable seat cards are the growth engine; radical transparency (every number shows its source).

## Coordination protocol
1. Read this file, the tail of `AGENT_LOG.md`, and `NIGHT_QUEUE.md` before doing anything.
2. Take ONE task for your lane. Commit small, clear message. Tick its box. Append a handoff to
   `AGENT_LOG.md`: time · agent · files · commit SHA · verification · next.

## Labour split
- **Claude** = BUILD lane: UI/markup/copy/i18n/a11y/responsive in `public/`, the pure logic in `public/lib.js`.
- **Codex** = VERIFY+STRESS lane: run tests, adversarially try to break each change, repo hygiene, `pipeline/*.py`.

## QUALITY REGIME — verify relentlessly, never idle (REQUIRED)
1. **Verify, then adversarially STRESS every change.** After a build task, the next task RUNS the checks
   (`node --test public/lib.test.mjs`, `node --check public/app.js`, `scripts/validate.sh`) THEN tries to BREAK it:
   malformed/missing data, edge values (0 votes, 100% turnout, missing runner-up, single-candidate), rapid
   mode/tier/lang switching, the 600-seat DUN load, narrow mobile, deep-link to a bad seat code.
2. **Any bug found → add a `[ ]` fix task at the TOP of NIGHT_QUEUE.md** (highest priority).
3. **Regression every round — "over and over".** Re-run the full suite so new work never breaks shipped work.
   Every pure function ships WITH unit tests in `public/lib.test.mjs`; GROW the tests with each feature, never bypass.
4. **`[MV]`** tasks are provable here (node --test/--check). **`[HVR]`** tasks (UI/CSS) you can only sanity-check
   structurally — say so in the handoff; visual correctness is Danial's morning call. Never claim a screen "looks right".
5. **Self-feeding:** the ♻️ tail task in NIGHT_QUEUE.md re-queues work when the list drains — never leave it ticked.

## Guardrails / UNTOUCHABLES — do not violate
- **No `git push`, no `wrangler deploy`.** Stay on `night/<date>`. Keep zero-dependency / no build step.
- **FROZEN PROJECTION:** never touch the `PROJECTION` constants in `pipeline/01_boundaries.py` (viewBox
  `0 0 799.85 352.74`, Mercator + `lng>=107` Borneo-shift). When porting `project()` to `lib.js`, copy it
  FAITHFULLY (the seat path `d` coords were baked with it) — do not "improve" it.
- `code_parlimen` (`P.001`…) is the universal join key; DUN keys on `code_state_dun`. Don't rename.
- GE15 `party` normalised to coalition in `02_results.py` (tally: PH 82·PN 74·BN 30·GPS 23·GRS 6·WARISAN 3 = 222).
- Frontend is data-driven (`loadOptional`) — a mode lights up only when its data file exists. **Keep Skor GATED**
  ("Soon") even if `scores.json` appears.
- Boundaries/results are official DOSM + Thevesh — never fabricate data.
- Brand rename touches USER-FACING strings only → **MyPolitik**; leave infra names (`peta-yb`, `politics`) alone.
- **Verify via syntax checks + unit tests + data validation only** — this is a headless box, no browser/screenshots.
