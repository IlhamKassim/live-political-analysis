# Public dashboard redesign — handoff

Status as of **9 August 2026**. Design direction is agreed; implementation has
not started. This file is the whole context — read it and `CONTEXT.md` before
touching anything.

## What exists

- `docs/design/ge16-chamber-mockup.html` — a self-contained mockup of the
  proposed public dashboard. Open it in a browser. Nothing in it is wired to
  real data; every figure is a placeholder (see **Fabricated content** below).
- Published copy: https://claude.ai/code/artifact/4a94942f-c9e2-4701-8eda-3cade3067e28

The existing `src/lpa/dashboard.py` is untouched and still the working
dashboard. The mockup is a proposal for a *public-facing* page, which may or
may not replace it — see **Open decision 2**.

## The design, in one paragraph

The hero is the Dewan Rakyat drawn as a hemicycle of 222 seats, ordered from
safest-Government at the left to safest-Opposition at the right, with the
112-seat Majority line drawn through it. The Government Coalition's block
overruns that line, so the size of its buffer is a visible distance rather than
a number to be read. Everything else — a ruled seat ledger, a stress-test row,
a colophon — is secondary and set as print, not as dashboard cards.

## Decisions already made — do not relitigate

1. **Hemicycle, not bar chart and not a geographic map.** A choropleth of
   Malaysia would let Sarawak's land area dominate its 31 Seats; the hemicycle
   is the chamber the Projection is actually about.
2. **Uncertainty is encoded as *form*, not only colour** — solid dot, half-tone
   dot, hollow ring. Survives greyscale and colour blindness.
3. **Print register, not dashboard register.** Green-grey paper ground,
   printed-ink coalition colours, hairline rules, a ruled table instead of
   rounded cards, ~3% press grain. Serif for prose and display figures, mono
   for every label and datum.
4. **System font stacks only.** The Artifact CSP blocks font CDNs and a
   fabricated `@font-face` data URI risks a silent fallback. The pairing is
   `ui-serif/Iowan/Georgia` + `ui-monospace/SF Mono/Menlo` + a system sans for
   micro-labels. If the real deploy can self-host fonts, revisit — but it is a
   deliberate choice, not an oversight.
5. **Both themes are token-driven.** Palette lives in custom properties on
   `:root`; `prefers-color-scheme` and `:root[data-theme=…]` both redefine
   tokens only. Never style a component inside the media query.
6. **The "not calibrated" caveat stays on the page**, in the colophon, in red.
   It is not moved to a subpage.

## Open decisions — these block implementation

### 1. What data does the hemicycle render? (blocking, decide first)

The mockup calls 222 individual Seats and gives each a margin in its tooltip.
**The pipeline does not produce that.** `swing_model` calls Seats internally but
publishes Coalition totals only, and ADR 0001 defers Seat-Level Projection until
the Swing Model is validated. Three options:

| Option | Cost | Honest today? |
| --- | --- | --- |
| a. Build Seat-Level Projection now | High; contradicts ADR 0001 | No — model is uncalibrated |
| b. **Render the hemicycle from Coalition totals alone** — 222 dots in bloc order, no per-Seat identity, no tooltips, no confidence rings | Low | Yes |
| c. Keep rings, derive the uncertainty band at Coalition level from the model's sensitivity to its two uncalibrated constants | Medium | Yes |

**Recommendation: (b) now, (c) once ADR 0003's constants are fitted (issue
#15).** (b) keeps the whole visual idea — the block overrunning the 112 line is
the point, and that needs only the totals. Dropping (a) also means dropping the
"Too close" ledger column and rewriting the four stress-test cells against a
Coalition-level basis.

### 2. Streamlit, or a static page? (blocking)

The mockup is hand-authored HTML/SVG. Streamlit will fight it: custom type,
full-bleed layout, the grain overlay and the theme toggle all need
`components.html` or heavy CSS injection, and Streamlit ships its own theme
toggle that will collide. Either

- accept Streamlit chrome and rebuild this Streamlit-native, losing much of the
  character, or
- serve the public page as static HTML generated from the same Storage, and keep
  the Streamlit app as the internal view.

The second preserves the design and costs a small generator plus somewhere to
host it. Note the zero-cost constraint in ADR 0002 binds this choice.

## Known defects in the mockup — fix during implementation

1. **Caption contradicts the sort.** The caption promises safest-Government to
   safest-Opposition, but the sort is bloc-first (GPS, GRS, BN, PH) and
   safest-first *within* each bloc, so BN's marginals sit mid-left rather than
   at the contest line. Either sort globally by margin and lose contiguous
   blocs, or rewrite the caption. (Moot if Open decision 1 resolves to (b).)
2. **Contrast failure, light mode.** `--ink-faint` `#8A8D83` on `--ground`
   `#E9EAE4` is **2.79:1**; it carries every eyebrow, the tally label, the
   colophon headings and the seat key. Needs 4.5:1 — approximately `#6C6F66`.
   `--ink-soft` is fine at 5.99:1.
3. **The pulsing dot claims live data.** The pipeline is a once-daily batch at
   15:00 UTC. Remove the pulse or make it a static marker.
4. **Mobile.** The hemicycle has `min-width: 460px` and scrolls sideways inside
   its wrapper, so on a 375px screen the hero is partly off-screen. Needs a
   stacked-bar fallback below ~600px.
5. **Keyboard and touch.** The 222 dots are not focusable and the hover-dim does
   nothing on touch. The SVG `aria-label` carries the summary; a
   visually-hidden table is the real fix.
6. **Bilingual treatment is tokenistic.** "Projeksi Kerusi GE16" in the masthead
   is the only Bahasa Malaysia on the page. Either commit to genuine bilingual
   labelling or drop the phrase.

## Fabricated content — none of these numbers are real

Every figure in the mockup is invented and several contradict the repo. They
exist to show typographic weight and must all be replaced from Storage:

- Seat totals (158 / 85 / 42 / 22 / 9 / 64) and all per-Seat margins.
- The GE15 column, especially **"Government total 141"** — that bloc formed by
  post-election agreement and was never a GE15 result.
- **"Losing Johor and Malacca cost it 11 seats"** — `data/state_elections.json`
  holds Johor only; Malacca's election is due by November 2026 and has not
  happened. The lede must be regenerated from real State Election Signals.
- The `MODEL RUN 09 AUG 2026 · 23:00 MYT` stamp.

Treat any number that cannot be traced to Storage or to `data/` as a bug.

## Constraints that bind the design

- **Vocabulary is precise.** Coalition, Seat, Majority, Baseline, Sentiment,
  Swing, Projection, Election Status — use them as `CONTEXT.md` defines them, in
  code and in user-visible copy. "Win" is specifically avoided because a
  Coalition can lead without a Majority.
- **ADR 0001** — Coalition-level Projection only, for now.
- **ADR 0002** — zero recurring cost. No paid hosting, no paid fonts, no CDN.
- **ADR 0003** — `sentiment_sensitivity` (0.10) and `state_signal_weight` (0.5)
  are judgement, not fitted. The page must not imply forecast precision.
- **`data/election_status.json`** — GE16 is not called. The page must render the
  called / not-called / no-polling-date states from that file and never guess.
- `pyproject.toml` force-includes each `data/*.json` into the wheel by hand; a
  new data file needs adding there too.

## Research already done — do not re-derive

A subagent surveyed how newsrooms and electoral commissions handle this. The
findings that shaped the design:

- **Value-Suppressing Uncertainty Palettes** (UW Interactive Data Lab) —
  reduce colour distinction as uncertainty rises, so a tight race cannot be
  read as decisive. This is where the solid/half-tone/hollow scale comes from.
- **The Guardian's 2024 election coverage** abandoned digital templates for
  handmade collage, specifically to read as human in an AI-saturated
  environment. Asymmetry, custom type pairing, a constrained palette and
  visible authorship are the transferable signals.
- **Washington Post cartograms** — equal-area seat squares inside recognisable
  geography, with hand-placed callouts. Rejected here in favour of the
  hemicycle, but reconsider if Seat-Level Projection ever ships.
- **AEC / UK Electoral Commission** — progressive disclosure and cautious
  language ("leading by", never "will win"), with data-freshness always visible.

## Suggested phasing

| Phase | Work | Suits |
| --- | --- | --- |
| 0 | Settle Open decisions 1 and 2 with the user | Opus, high — judgement, not code |
| 1 | Whichever data path decision 1 picks; extend Storage/`domain` as needed, test-first | Opus or Sonnet, medium-high |
| 2 | Build the page from the mockup against real data | Opus, high — design execution |
| 3 | Defects 2–5: contrast, pulse, mobile fallback, a11y table | Sonnet, medium — mechanical |

Working rhythm is the project's usual one: implement test-first → `/code-review`
→ fix → merge to `main` → close the issue, one ticket at a time, and run the
real thing before calling it done.
