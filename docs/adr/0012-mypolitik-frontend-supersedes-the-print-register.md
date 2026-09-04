# `mypolitik`'s frontend supersedes the print-register visual decision

> **Supersedes [`docs/design/HANDOFF.md`'s "Decisions already made — do not
> relitigate"](../design/HANDOFF.md#decisions-already-made--do-not-relitigate),
> item 3 ("Print register, not dashboard register") and item 7 ("The print
> register is the point").** Those decisions are not wrong in retrospect —
> they were the right call for the page they were made for. They stop
> applying because that page's role in the site is changing, not because
> the reasoning behind them was flawed.

## Why

This repo merged with `mypolitik` (github.com/enonforetsam/mypolitik), a
hand-rolled interactive Parliament+DUN map SPA whose ownership KrackedDevs
transferred to the maintainer. The merge decision (session of 2026-08-29,
`git log --grep=mypolitik`) settled on one merged product: `mypolitik`'s
frontend becomes the surviving interactive architecture across the whole
site, and PolitikKu's Python pipeline becomes its trusted data backend.
`frontend/` (the imported `mypolitik` code) is now where every page —
including the seat projection this print-register work was built for —
eventually renders.

`mypolitik`'s visual language (`frontend/public/styles.css`) was not
designed against `HANDOFF.md`'s "arrived at by elimination" reasoning and
does not match it: bordered `.bento-tile` panels with `border-radius:16px`,
a body/UI sans (Space Grotesk) rather than a print serif, JetBrains Mono
for data rather than a system mono stack. It is closer to a conventional
dashboard register than `HANDOFF.md` item 7 called for — the exact
direction that document named as a failure mode to watch for, in the page
it was written for.

Rebuilding `mypolitik`'s entire frontend into the print register's asymmetric,
constrained-palette, ruled-table visual language was considered and
rejected: it would mean re-doing thousands of lines of a working,
already-interactive SPA (map, search, live election mode) to match a
design brief written for one static page, for no functional gain. The
print register's credibility argument (asymmetry, hairline rules, visible
authorship read as more trustworthy than a templated dashboard) is a real
tradeoff being given up here — see "What this does not do" below for what
is kept instead.

## Decision

**`mypolitik`'s existing visual language is the surviving frontend design
system**, including for the seat projection page `HANDOFF.md` was written
for once it's ported into `frontend/public/` (Step 4 of the merge plan).
`docs/design/mypolitik-new-views-spec.md`'s "Components to reuse (do not
invent new ones)" section is the operative design reference going forward:
`.bento-tile`, `.rows` (ruled table), `.pill`, `.sharebar`, `COALITION_COLORS`,
and the `--sans`/`--font-display`/`--mono` typography split.

`HANDOFF.md` items 1, 2, 5, and 6 are **not** superseded and still apply
wherever the projection view is rebuilt in `frontend/`:
- Hemicycle over bar chart or choropleth (item 1) — no `mypolitik` component
  contradicts this; it has no chamber visualization today, so this is new
  work built fresh, not a conflict to resolve.
- Uncertainty encoded as form, not only colour (item 2) — carries over as a
  rendering requirement for the hemicycle regardless of surrounding chrome.
- Token-driven theming (item 5) — `mypolitik`'s CSS already follows this
  pattern (`:root` custom properties, `prefers-color-scheme` and
  `[data-theme]` overrides), so this item is inherited for free, not lost.
- The "not calibrated" caveat staying visible, not moved to a subpage (item
  6) — carries over as the FACT/MODEL trust pattern
  (`docs/design/mypolitik-new-views-spec.md`'s "trust pattern" section),
  applied inline per number rather than as a page banner, which is a
  *stricter* reading of item 6's intent, not a relaxation of it.

Item 4 (system font stacks only) is superseded implicitly: `mypolitik`
already loads Space Grotesk/Redaction 20/JetBrains Mono as real webfonts,
which was the option item 4 explicitly deferred ("If the real deploy can
self-host fonts, revisit"). That revisit has effectively happened via the
merge, not via a fresh CSP/hosting decision made on its own terms.

## What this does not do

It does not delete or retroactively invalidate the print-register mockup
or `HANDOFF.md`'s reasoning — that reasoning is kept in place as the
record of a real, considered design pass, and the "arrived at by
elimination" argument (item 7) remains true for the two earlier
templated-dashboard mockups it was actually elimination against. It also
does not mean every visual decision in `mypolitik` is now unquestionable
in the way `HANDOFF.md` asked its own conclusions to be treated — this ADR
retires the print register as the site's design direction; it does not
promote `mypolitik`'s CSS to the same "do not relitigate" status.

## Consequence

`docs/design/ui-ux-brief.md` (written to prioritize UI/UX work *within* the
print-register direction) is stale as of this ADR and is retired — see the
note added at its top — rather than edited to match `mypolitik`'s design
system, since none of its four prioritized workstreams describe real
remaining work once the direction itself has changed. `GEMINI.md`'s pointer
to it is removed in the same change. `docs/design/mypolitik-new-views-spec.md`
is the design reference for new work going forward.
