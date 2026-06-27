# Agent Coordination — Peta YB (VPS night shift)

Interactive map of every Malaysian Parliament/DUN seat (GE15 results; Hansard scoring later).
Static `public/` app served by a tiny CF Worker; data built by `pipeline/*.py`. No build step.

**This is a VPS sandbox copy for autonomous overnight work.** It does NOT deploy and is separate
from the laptop working copy (where another session may be editing). All work lands on the
`night/<date>` branch for morning review and reconciliation — never master.

## Coordination protocol
1. Read this file, the tail of `AGENT_LOG.md`, and `NIGHT_QUEUE.md` before doing anything.
2. Take ONE task for your lane. Commit small with a clear message. Tick its box in `NIGHT_QUEUE.md`.
3. Append a handoff to `AGENT_LOG.md`: time · agent · files · commit SHA · verification · next.

## Labour split
- **Claude**: UI / markup / copy / i18n / accessibility / responsive in `public/`
  (`index.html`, `styles.css`, `app.js`).
- **Codex**: verification, smoke/validation scripts, repo hygiene, `pipeline/*.py` checks.

## Guardrails / UNTOUCHABLES (from the repo README invariants — do not violate)
- **No `git push`, no `wrangler deploy`.** Stay on the `night/<date>` branch.
- Keep it **zero-dependency / no new build step**.
- **FROZEN PROJECTION:** do NOT touch the hardcoded `PROJECTION` constants in
  `pipeline/01_boundaries.py` (viewBox `0 0 799.85 352.74`, Mercator + Borneo-shift). Never
  recompute bounds from seat data — this is what keeps Peta YB aligned with krackedmaps.
- `code_parlimen` (`P.001`…) is the universal join key; DUN keys on `code_state_dun`. Don't rename.
- GE15 `party` is normalised to coalition in `02_results.py`. Sanity tally:
  PH 82 · PN 74 · BN 30 · GPS 23 · GRS 6 · WARISAN 3 = 222.
- The frontend is **data-driven** (`loadOptional`): a mode lights up only when its data file
  exists. Don't hardwire modes.
- Boundaries/results are official DOSM + Thevesh — never fabricate data.
- **Verify via SYNTAX CHECKS + DATA VALIDATION only** (`node --check`, `python3 -m py_compile`,
  `JSON.parse`). No browser/screenshots — this is a headless box.
