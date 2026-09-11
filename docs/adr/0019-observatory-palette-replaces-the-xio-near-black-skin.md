# The observatory palette replaces the XIO near-black skin

> **Amends [ADR 0015](0015-mypolitik-design-system-replaces-the-navy-paper-shell.md).**
> ADR 0015 made `mypolitik`'s dark map SPA the site's only design system. That
> still holds. This ADR changes what that one system *looks like*: its colours,
> type and decoration. It does not bring back a second system.

## Why

On 2026-09-11 a redesign of the Seat map was built as an isolated preview
(`codex/app-observatory-preview`, commit `71f1791`). It gave the app the same
"observatory" look the homepage already uses: ink `#101e23` ground, paper text
and a lime `#d6ed9a` accent. The owner reviewed it and chose it as the design
for the whole app, with the instruction that the old look be removed rather
than kept alongside.

The old look was several layers stacked in `frontend/public/styles.css`:

- the "XIO" near-black palette (`#0e0f12`) with white-on-black controls,
- a Redaction serif for headings,
- a light theme that the app had already switched off ("dark-only for now"),
- an animated `fluid-bg` WebGL background loaded from jsDelivr, and
- a silver "shimmer" animation on state titles, Seat names, search
  placeholders and sidebar crests.

## Decision

**The observatory palette is the app's palette.** Ink `#101e23`, surfaces
`#16272c` / `#192b30`, paper text `#edf1df`, lime accent `#d6ed9a`. Every
text colour clears WCAG AA (4.5:1) on every surface; the faintest,
`#94aaa2`, is 5.15:1 on the lightest surface. This also clears the old
`--ink-faint` contrast failure that ADR 0015 recorded.

**Space Grotesk is the display face.** Headings drop the Redaction serif.

**The app is dark only.** The light theme, its toggle button and all
`html[data-theme="light"]` rules are deleted.

**Decoration is flat.** The `fluid-bg` background (and its third-party
script), the shimmer animations and the live-state sweep are deleted. The map
sits on a quiet grid.

**The desktop overview is map beside explorer.** On wide screens the national
view puts the map next to a full-height panel: search, Seat layer / colour
controls, Coalition counts, and a plain line saying that election results are
records while a *Projection* is an estimate. Phones get a text list of all
destinations in the menu and a direct "Layers & colours" button.

**`politikku_shell.py` follows the same tokens**, so the standalone Learn and
Methodology pages match the app.

## What this does not change

- Seat boundary geometry, Coalition colours, results, citations or
  translations of existing strings.
- **The shareable Seat card PNG.** It is drawn on a canvas in Redaction, so
  `styles.css` keeps the Redaction `@font-face` for that one use. Changing the
  card artwork is a separate decision.
- The embed widget (`embed.html`), which is styled on its own.
- The homepage (`politikku_landing.py`), which already uses this palette.

## Consequence

A future session that finds `#0e0f12`, Redaction headings, `fluid-bg` or a
light theme in old commits or design docs should treat them as retired. As
ADR 0015 said: if a design reference in this repo is not named as live by an
ADR, it is not live. This one is.
