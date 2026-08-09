# Public dashboard redesign — handoff

Status as of **9 August 2026**. **The page is built, reviewed, run and
merged.** What is left is the defect pass and the deploy. This file is the
whole context. Read it, then `CONTEXT.md`, before touching anything.

## Start here

**If you have just been told "continue", this is the state and the next action.**

| | |
| --- | --- |
| Ticket | **#17** — **closed** 9 Aug 2026, shipped in #20 (merge `582ccd1`) |
| Steps 1–6 | **Done** 9 Aug 2026 — ADRs, per-Seat calls through Storage, the page, `/code-review` and its fixes, run across every state, merged |
| Next action | **Step 7**, the defect pass. Everything it needs is decided and written down below; it does not need the strong model. |
| After that | **Step 8**, deploy — blocked on the user setting `DATABASE_URL`, which has had the daily Action failing every run since 6 Aug 2026 |

**Step 7 is fully specified. Do not re-open its design decisions** — read
*Known defects* below, where each carries the choice made, the reasoning, and
what was rejected. Two things are genuinely still open and both belong to the
user, not to you: **the Malay wording** for the bilingual labels, and the
**`DATABASE_URL` secret**.

The one thing to carry forward from step 5: the sub-600px problem is bigger
than this file originally said. The **ledger** is cut at 375px as badly as the
chamber is, so fixing only the chamber leaves the page with no uncertainty
information on a phone at all. Measurements are under defect 4.

The two decisions that used to block this are answered, and both are now ADRs:

1. **The chamber renders named Seats with per-Seat calls**, not Coalition
   totals alone —
   [ADR 0005](../adr/0005-publish-the-seat-level-projection.md), which
   supersedes ADR 0001.
2. **The public page is static HTML**, not Streamlit —
   [ADR 0006](../adr/0006-static-html-for-the-public-page.md).
   `src/lpa/dashboard.py` stays as the internal view; it is not deleted and not
   redesigned.

Both are written up in full, with what they require and the constraint on
presenting per-Seat calls, in the *Decisions settled* comment on #17. Read it —
it is the authority, and the sections below still describe the pre-decision
state where they conflict.

## What Step 2 built, and what Step 3 can now read

`Projection.seat_calls` carries a `SeatCall` per Seat — `code`, the `coalition`
projected to take it, and the projected `margin` over the runner-up. Name and
state are *not* on it; they come from `SeatBaseline` by joining on `code`, which
the page needs loaded anyway to show GE15 against the Projection.

- `load_projections(engine)` attaches the calls to the newest Projection and
  leaves every earlier one's `seat_calls` empty. That is deliberate, not a
  gap — Storage keeps per-Seat rows for the latest Projection only.
- Margins are taken from shares floored at zero and rescaled to their Baseline
  total, so a margin is always a real share of the vote. A margin of exactly
  `0.0` means a dead heat held on the Baseline.
- Against the real 222-Seat Baseline as of 9 Aug 2026: **41 Seats fall inside
  six points.** The hollow-ring encoding is carrying about a fifth of the
  chamber, which is the argument for it.

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
7. **The print register is the point, and it was arrived at by elimination.**
   Two earlier mockups were rejected for reading as templated — centred grids,
   rounded cards on a symmetric layout, a six-colour palette, emoji as section
   markers, a status badge instead of the arithmetic. If work on this page
   starts drifting back toward a conventional dashboard, that is the failure
   mode; name it and stop. Asymmetry, a constrained palette, ruled tables and
   visible authorship are what carry the credibility here.

## Open decisions — SETTLED 9 Aug 2026, kept for the reasoning

> Both were answered on 9 August 2026: **(a)** per-Seat calls with named Seats,
> and **static HTML**. See the *Decisions settled* comment on #17 for what each
> requires. The tradeoffs below are kept because they are why the answers are
> what they are — not because anything is still open.

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

## Known defects in the mockup

Three were fixed while building the page (step 3) because each was about what
the page *claims* rather than how it looks. Three remain, and are step 7.

1. ~~**Caption contradicts the sort.**~~ **Fixed.** Seats now sort by margin
   across the whole Government side rather than bloc-first, which is what the
   caption always promised. Blocs are no longer contiguous; the colours carry
   that. See `_ordered_seats` in `src/lpa/public_page.py`.
2. ~~**Contrast failure, light mode.**~~ **Fixed** — but not at the value this
   file suggested. `#6C6F66` measures **4.23:1** on `--ground`, still short of
   4.5:1; `--ink-faint` is now `#666960`, at 4.62:1. The swing column needed
   its own tokens too: `--pn` is 4.17:1, fine for a 9px dot and short for 14px
   type, so `--ink-pos` / `--ink-neg` carry the text. Measure, don't eyeball.
3. ~~**The pulsing dot claims live data.**~~ **Fixed.** The pulse is gone; the
   stamp is a static `MODEL RUN <date>` from `Projection.computed_at`.
4. **Mobile.** The hemicycle has `min-width: 460px` and scrolls sideways inside
   its wrapper, so on a 375px screen the hero is partly off-screen.
   **Decided 9 Aug 2026 — a stacked bar below ~600px, segmented by Coalition
   in bloc order.** Government Coalitions first, then non-government, each run
   in the same order as the ledger's rows. The Majority tick goes at the 112th
   seat along the bar; because every Government Coalition still comes first,
   the block still overruns it and the buffer is still a visible distance,
   which is the one idea the hero exists for.

   **Why bloc order and not the chamber's margin order.** The bar *replaces*
   the hemicycle below 600px rather than accompanying it, so the two orderings
   never appear on one screen, and the thing the bar does sit beside is the
   ledger — which is ordered by bloc. Colouring by Coalition in margin order
   was rejected outright: at 375px a seat is under 2px, and interleaved
   sub-2px stripes read as dither, or as a rendering fault.

   Two consequences that must be handled, not discovered:

   - **The caption changes with it.** The desktop caption promises
     safest-Government to safest Non-government, which is false of the bar.
     The narrow layout needs its own caption; do not let the desktop one leak.
   - **Marginals no longer sit at the contest line**, so the bar carries no
     uncertainty encoding at all. The ledger's "too close" column is the only
     place it survives on mobile — which is another reason defect 5's
     visually-hidden table matters more than it looks.

   **Measured at 375px on 9 Aug 2026, and it is worse than this file said.**
   The chamber is not the only casualty:

   | | Measured |
   | --- | --- |
   | Viewport | 375px |
   | Content column | 335px |
   | Hemicycle SVG | 460px — **overflows by 125px**, the Non-government side clipped |
   | Ledger table | 540px — **205px of columns hidden** |
   | "Too close" header | sits at x=498, **off-screen entirely** |

   So **the ledger cannot carry the uncertainty on mobile**, because at 375px
   the ledger has no numbers on it at all — only the Coalition names column is
   visible, and Projected, GE15, Swing and Too close are all behind a sideways
   scroll a reader will not find. The stacked-bar decision above assumed
   otherwise. Step 7 must therefore fix **both**: the chamber *and* a narrow
   layout for the ledger (per-Coalition stacked rows rather than a 540px table
   is the obvious move). Fixing only the chamber leaves the page with no
   uncertainty information on a phone whatsoever.

   The page body itself does not scroll horizontally — both overflows are
   contained inside their own wrappers, so this is a legibility failure and
   not a layout break.

   Do not try to keep the dots by shrinking them: 3px rings are
   indistinguishable and untappable, and that option was considered and
   rejected.
5. **Keyboard and touch.** The 222 dots are not focusable and the hover-dim does
   nothing on touch. The SVG `aria-label` carries the summary; a
   visually-hidden table is the real fix. Note the table is also what makes the
   per-Seat detail reachable on mobile once the chamber becomes a bar.
6. **Bilingual treatment is tokenistic.** "Projeksi Kerusi GE16" in the masthead
   is the only Bahasa Malaysia on the page. **Decided 9 Aug 2026 — bilingual
   structural labels.** BM alongside English for the masthead, the section
   eyebrows, the Majority line and the seat key; prose (lede, method, colophon,
   caveat) stays English. Not full bilingual, and not dropped.

   **The BM wording is not settled.** These were the suggestions on the table
   when the approach was chosen, and they need a native eye before they ship:
   *Dewan Rakyat, unjuran* · *majoriti* · *selamat* · *berkemungkinan* ·
   *terlalu rapat*. Ask the user rather than committing them as-is — half-right
   Malay on a page about Malaysian politics is worse than none, which is the
   whole reason this defect exists.

7. **The theme toggle does not survive a reload.** Found while building the
   page. It sets `data-theme` on the root and nothing persists it, so every
   visit reverts to the system preference. `localStorage`, read before first
   paint to avoid a flash.

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
- **ADR 0005** — per-Seat calls are published, but a call is arithmetic against
  GE15 under a state-uniform Swing, never a judgement about that Seat. The page
  must not imply otherwise. (Supersedes ADR 0001.)
- **ADR 0002** — zero recurring cost. No paid hosting, no paid fonts, no CDN.
- **ADR 0003** — `sentiment_sensitivity` (0.10) and `state_signal_weight` (0.5)
  are judgement, not fitted. The page must not imply forecast precision.
- **`data/election_status.json`** — GE16 is not called. The page must render the
  called / not-called / no-polling-date states from that file and never guess.
- `pyproject.toml` force-includes each `data/*.json` into the wheel by hand; a
  new data file needs adding there too, or an installed dashboard reads a path
  that only exists in a checkout.

## Operational traps

Each of these has already cost time on this project.

- **The Dashboard has no automated tests, by design.** Issue #1 settled that it
  is verified by running the pipeline end to end and looking at the page. So a
  green test run says nothing about this work — running it for real is the gate.
  Cover the states a fresh deploy hits first: empty database, one day of
  history, and all three Election Status states.
- **Most stored daily history is seeded.** `scripts/seed_dev_snapshots.py`
  writes an invented random walk. Any trend that looks interesting on local data
  is probably about the seeder, not about Malaysia.
- **Do not take review subagents at face value.** A spec reviewer once reported
  Bernama's Malay RSS feed returning 200 with Malay items; it returns a stable
  500. Another argued a change had destroyed GPS coverage, citing seeded days as
  evidence. Check any factual claim against the real thing before acting on it.
- **Streamlit caches reads for 15 minutes.** A pipeline run that finishes while
  a tab is open takes up to that long to appear. Not a bug; do not chase it.
- **GitHub disables a scheduled workflow after 60 days with no commits.** If
  snapshots stop appearing during a quiet stretch, check that first.

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

## Workflow, start to end

The project's usual rhythm — implement test-first → `/code-review` → fix → run
the real thing → merge to `main` → close the issue, one ticket at a time.
Applied to this piece of work:

| Step | Work | Owner | Model / effort |
| --- | --- | --- | --- |
| ~~1~~ | ~~Settle the two decisions~~ — **done 9 Aug 2026**, see #17 | — | — |
| ~~2~~ | ~~ADR 0005, ADR 0006, and per-Seat calls through `swing_model` → `Projection` → `storage`~~ — **done 9 Aug 2026** | — | — |
| ~~3~~ | ~~Build the page from the mockup against real Storage data~~ — **done 9 Aug 2026**, `src/lpa/public_page.py` | — | — |
| 4 | `/code-review`, then fix findings. | Agent | inherits |
| 5 | Run it for real: empty database, one day of history, 375px and 1440px, both themes, all three Election Status states. | **User** and agent together | — |
| 6 | Merge to `main`, close #17 noting what shipped and what did not. | Agent | Sonnet, medium |
| 7 | Defect pass — **the sub-600px fallback and the keyboard path**, which are what remain: contrast and the liveness pulse were fixed while building the page, and the caption/sort contradiction went with the global margin sort. Add the theme toggle not surviving a reload. Separable; can be its own PR. | Agent | Sonnet, medium — mechanical |
| 8 | Deploy. | — | — |

**Step 8 is real work**, now that decision 2 is static: a renderer plus free
hosting, with ADR 0002's zero-cost rule binding the choice. GitHub Pages is the
obvious answer, and the existing daily Action can render and publish the page in
the same job it already runs. The public page then never touches the database at
request time — only the Action does.

**Where the user is the bottleneck:** steps 1 and 5. Nobody else can make those
calls, or say the page reads right. Everything else an agent can carry.

**Rough shape:** steps 1–2 in one session, 3–6 in another, 7–8 in a third.
