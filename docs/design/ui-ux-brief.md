# UI/UX improvement brief — for Antigravity

> **Retired, superseded by [ADR 0012](../adr/0012-mypolitik-frontend-supersedes-the-print-register.md).**
> This brief was written to prioritize work *within* the print-register
> visual direction (`docs/design/HANDOFF.md`), which that ADR retires in
> favor of `mypolitik`'s existing frontend design system. None of the
> workstreams below describe real remaining work once the direction itself
> has changed — see `docs/design/mypolitik-new-views-spec.md` for the
> design reference that replaces this file going forward. Kept for its
> historical reasoning, not as an active brief.

Status as of **29 August 2026**. This file is the brief for prioritized
UI/UX work on the public PolitikKu site. Read it, then `CONTEXT.md`, before
touching any visual or layout code.

## Read first

- **`CONTEXT.md`** — domain glossary. Use exact terms; never invent synonyms.
- **Design tokens**, `src/lpa/politikku_shell.py:719-780`
  (`_CSS_TEMPLATE`'s `:root` block) — the canonical source of truth for
  color, type, spacing, and radius. These tokens derive from a
  `design_handoff_politikku/README.md` that is **not in this repo** — do not
  look for it or reference it; the tokens themselves are what's canonical
  now.
- **"Decisions already made — do not relitigate"**, in
  `docs/design/HANDOFF.md`:
  1. Hemicycle, not bar chart, not a geographic map.
  2. Uncertainty encoded as *form* (solid/half-tone/hollow), not color alone.
  3. **Print register, not dashboard register** — green-grey paper ground,
     printed-ink coalition colors, hairline rules, ruled tables instead of
     rounded cards, ~3% press grain, serif for prose/display figures, mono
     for labels/data.
  4. System font stacks only (self-hosted woff2, no font CDN — the token
     file already wires this via `@font-face`).

  Any UI/UX change that drifts toward rounded "dashboard cards," drops the
  print register, or introduces a new color/font outside the token set is
  relitigating a closed decision — flag it explicitly instead of doing it.

## Constraints

- Stay within the existing tokens. If a workstream genuinely needs a new
  color, font weight, or spacing value, name it explicitly in the commit
  message rather than adding it silently.
- Static-HTML/CSS-in-Python only — no new JS framework or build step
  (ADR 0006). The small `ts/src/` module is the only client-side code; don't
  expand its scope without flagging it.
- Verify mechanically before claiming done: `.venv/bin/pytest`,
  `ruff check`, `mypy`.
- No `git push`, no PRs, no merges — local commits only, per this repo's
  standing guardrails.

## Prioritized workstreams

Ordered by what hasn't had a UI pass yet and by how much of the site each
change touches — do them in this order unless a dependency forces otherwise.

### 1. Bills tracker page (`src/lpa/politikku_bills.py`)

Never had a dedicated UI/UX pass. The homepage's bill cards
(`_bill_card()` in `src/lpa/politikku_homepage.py:355`) were just upgraded
with status pills, division/vote badges, and sentiment styling (`45b816f`) —
bring the tracker page's own card/status treatment in line with that pattern
so the two don't visibly diverge when a user moves between them.

### 2. Shell chrome (`src/lpa/politikku_shell.py` nav/header/footer, `src/lpa/politikku_landing.py`)

Persistent across every page — improvements here compound. Check the
language toggle and trust-strip treatment for the same polish level the
homepage hero now has (popular-search chips, upgraded card style).

### 3. Site-wide mobile/accessibility sweep

- Confirm the `@media (max-width: 900px)` breakpoint pattern already used
  in the homepage CSS (`src/lpa/politikku_homepage.py:649`) is applied
  consistently on the bills tracker and shell chrome once workstreams 1–2
  land.
- Contrast-check `--muted` / `--ink-secondary` text against `--paper` /
  `--paper-alt` backgrounds (see token values in `politikku_shell.py`).
- Keyboard-nav and focus-state check on every interactive element: search
  chips, language toggle, the MP/constituency lookup form.

### 4. Homepage, further iteration

Lowest priority — `45b816f` just shipped a homepage pass. Only revisit if
the sweep above (workstream 3) surfaces a cross-page inconsistency that
traces back to the homepage specifically.

## Acceptance criteria (all workstreams)

- `.venv/bin/pytest`, `ruff check`, and `mypy` all pass.
- Visually verified at 375px and 1440px, in the site's single existing
  (print/dark-ink) theme — there is no separate light/dark mode to check.
- No color, font, spacing, or radius value introduced outside
  `politikku_shell.py`'s token set without being named explicitly in the
  commit message.
- Bilingual (EN/BM) labels preserved everywhere they currently exist.

## Human check required before anything is committed to `main`

This is trigger-1 work (visual/design judgment) under
`docs/agents/model-effort.md` — "does this look right" is a judgment call,
not something `pytest`/`ruff`/`mypy` can verify. That policy requires a
**human visual check before merge** for exactly this kind of work. Running
the tests and linters is necessary but not sufficient — the user looks at
the real rendered page before anything here lands on `main`.
