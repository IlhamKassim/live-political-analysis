# Night Queue — Peta YB (VPS overnight)

Small, contained, client-side or verification tasks. One per round. Respect the UNTOUCHABLES
in AGENTS.md. Verify with syntax checks / data validation only (no browser).

- [x] (codex) Add `scripts/validate.sh`: `node --check public/app.js`; `python3 -m py_compile pipeline/*.py`;
      `JSON.parse` each `public/data/*.json`; assert the GE15 coalition tally
      (PH 82 · PN 74 · BN 30 · GPS 23 · GRS 6 · WARISAN 3 = 222) from `results-ge15.json`.
      Print PASS/FAIL, exit non-zero on failure. Run it; paste the result in the handoff.
- [x] (claude) Mobile/responsive pass: make the map, side panel, search, and legend usable on
      narrow screens (≤390px) with no horizontal overflow. CSS in `public/styles.css` only.
- [x] (claude) i18n completeness: find any user-facing string in `index.html`/`app.js` not wired
      through the `I18N`/`data-i18n` system; add the missing EN + BM entries. List every string touched.
- [x] (claude) Accessibility pass: `aria-label`s on the search box, mode toggles, reset/zoom, and the
      language toggle; a visible `:focus-visible` ring; ensure the legend isn't colour-only. Client-only.
- [x] (codex) Verify the `loadOptional()` failure path: if `results-ge15.json`/`scores.json` fail to
      load, the map must still render boundaries. Read the code, confirm, write findings — change only if broken.
- [x] (claude) Loading + empty states: a subtle "loading seats…" affordance and a friendly message if a
      data layer is unavailable. No layout shift. Client-only.
- [ ] (codex) Hygiene: scan `public/app.js` for stray `console.log`/debug and dead code; report, and
      remove only clearly-dead lines conservatively. `node --check` after.

<!-- add more anytime via the cockpit's +Task box. queue empty 3 rounds running = loop waits then wraps. -->
