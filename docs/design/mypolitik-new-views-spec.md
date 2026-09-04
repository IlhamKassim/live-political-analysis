# New frontend views spec — projection, bills, sentiment, trust pattern

Step 4 of the PolitikKu x mypolitik merge (see the session plan). Written
after an audit confirmed `frontend/` (mypolitik) has **zero equivalent**
for four things core to what PolitikKu is: the GE16 seat projection, the
bill tracker, the sentiment digest, and the FACT/MODEL trust-labeling
pattern. These need new views built in `frontend/public/`'s own visual
language — this is new frontend work, not a wiring job. This file pins the
exact data contract and exact UI components to reuse, so whoever builds
each view (Antigravity, a Claude Code subagent, or by hand) isn't guessing.

**Do not retire any old Python-rendered page** (`politikku_homepage.py`,
`politikku_bills.py`, `politikku_landing.py`) until its replacement here is
built and verified — per the Step 4 decision already made.

## How a new view gets added (mechanical pattern — reuse exactly)

No router — a body-class + section-visibility convention
(`frontend/public/styles.css:3458-3459`,
`body.<x>-open #<x>-view { display:block }`). Follow the same shape as
`openDewanPage()`/`closeDewanPage()` (`frontend/public/app.js:4506-4524`)
for each new view:
1. `<section id="<view>-view">` added to `frontend/public/index.html`.
2. Matching `display:none` / `body.<view>-open` CSS rule.
3. `open<View>Page()` / `close<View>Page()` in `app.js`: closes sibling
   views, lazy-loads its data file, adds the body class, renders into the
   section's `innerHTML`, calls `syncSidebar()`, `history.pushState`.
4. A sidebar button (`#sb-<view>`, wired near `app.js:4247-4248`).
5. A hash case in `parseHash()` (`app.js:4002`) for deep-linking.

## Components to reuse (do not invent new ones)

- **Stat tiles** — `.bento-tile` (`styles.css:4173`, light-theme override
  at 5586): bordered panel, `border-radius:16px`, flex column. Use for
  summary numbers (e.g. coalition seat totals, total articles scored).
- **Ruled table** — `.rows` (`styles.css:365`): 2-col grid, row+column
  hairlines, `border-radius:10px`, last row's borders stripped. This is
  the "closed bordered table" pattern — closest to PolitikKu's old
  print-register ruled tables, already native to this app. Prefer this
  over `.dewan-table`'s row-only grid for anything presented as a data
  table (bill list, sentiment-by-coalition).
- **Badge/pill** — `.pill` (`styles.css:376`), background set via
  `pillStyle(partyColor(coalition))` — use for coalition/status badges.
- **Stacked share bar** — `.sharebar` + `.sharebar-key`
  (`styles.css:236`, built in JS at `app.js:3232-3266`) — use for the
  seat-projection coalition breakdown (this is the natural fit for
  `coalition_seat_totals`).
- **Empty state** — `.module-empty` (`styles.css:1454`) for a section with
  no data yet; `#panel-empty` (`styles.css:842-893`) if an entire view has
  nothing to show.
- **Colors**: `COALITION_COLORS` already defined in
  `frontend/public/lib.js:10-21` (`partyColor()`) — reuse verbatim, do not
  redefine.
- **Typography**: body/UI text uses `--sans` (Space Grotesk); headings
  (`h1`, `h2`, `.seat-head h2`) use `--font-display` (Redaction 20 serif);
  all numeric/data display uses `--mono` (JetBrains Mono) — apply this
  split to new views too (e.g. seat counts and vote shares in mono, not
  sans).

## The FACT/MODEL trust pattern — replicate verbatim, not reinvented

Source: `src/lpa/politikku_i18n.py:56-57`. The tag text is exactly:
- EN: `NOT CALIBRATED`
- MS: `BELUM DITENTUKUR`

**Rule** (quoted from `politikku_landing.py`): the tag appears **inline
beside every modelled number**, never as a page-level banner, and never on
factual data. `politikku_landing.py`'s `TrustCard` dataclass is the
reference pattern: `kind: FACT | MODEL`, `modelled_number: bool` gates
whether the tag renders.

In the new frontend, add a small pill/tag component (reuse `.pill`'s shape
but keep the exact wording above) and apply it inline next to any number
that comes from the swing model — the seat projection view is where this
matters most, since every seat call and coalition total there is modelled,
not observed.

## View 1 — GE16 seat projection

**Data**: `public/projection.json` (already exists,
`src/lpa/public_page.py`/`politikku_projection.py`) — real shape:
```json
{
  "schema_version": 1,
  "computed_at": "2026-08-23",
  "coalition_seat_totals": {"PN": 69, "BN": 41, "PH": 75, "GRS": 7, "GPS": 23},
  "government_majority": true,
  "seats": [
    {"code": "P.001", "name": "Padang Besar", "state": "Perlis",
     "coalition": "PN", "coalition_name": "Perikatan Nasional",
     "margin": 0.2679827874568371}
  ],
  "caveat": "..."
}
```
**Gap — needs Python-side work before the frontend can show everything**:
the richer `PageModel` (majority_threshold, buffer, too_close_seats,
sensitivity_table, state_rollup, trend, threshold_seat/swing) is NOT in
`projection.json` today, only in the old page's HTML. Decide: either (a)
extend `projection.json`'s export to include these fields, or (b) ship a
v1 view with just coalition totals + seat calls (what's already exported)
and treat the richer fields as a v2 follow-up. Flagging for a decision,
not deciding silently — this is real backend work, not frontend wiring.

**Render**: coalition totals as a `.sharebar` (party-colored, matches
PolitikKu's existing GE15-results sharebar visually) + `.bento-tile`s for
majority/government_majority. Per-seat calls in a `.rows` table or reuse
the map's own seat-click panel pattern (a seat's projected call could
render in the same panel slot as its GE15 result, toggled by a "GE16
projection" mode next to the existing "Parti"/"Skor" mode toggle). Every
number here gets the `NOT CALIBRATED` tag inline — this view is where that
rule matters most.

## View 2 — Bill tracker

**Data**: `data/bills.json` — a dict keyed by Bill number (not a list),
e.g. `"D.R.22/2026"`, 67 entries. Real shape:
```json
{
  "title": "RUU Kumpulan Wang Amanah Negara 2026",
  "year": 2026,
  "stage": "Lulus",
  "stage_date": "2026-07-16",
  "summary": "... verbatim excerpt from the Bill's own HURAIAN section ...",
  "summary_source_url": "https://www.parlimen.gov.my/files/billindex/pdf/...",
  "division": null,
  "unverified": {"division": "Not among the 15th Parliament's ten recorded Divisions ..."}
}
```
Where a Division vote happened, `division` is populated (sitting_date,
ayes, noes, abstentions, absent, outcome, hansard_url) instead of null.
`stage` is Parliament's own literal status label — display it verbatim,
do not translate or invent an English taxonomy. `title`/`summary` are in
Bahasa Malaysia, source-verbatim — do not paraphrase (ADR 0010).

**Gap**: `data/bills.json` isn't currently exported into
`frontend/public/data/` at all — needs a copy/symlink step (likely in
whatever build step eventually reconciles the two pipelines) before the
frontend can fetch it as `data/bills.json`.

**Render**: `.rows` table (title, stage pill via `.pill`, stage_date in
mono) with each row expandable to show the summary + division info where
present. Most bills have `division: null` — this is a documented finding
(Malaysia has no working private-member's-bill route, per
`mp_profiles.json`'s own `unverified.bills_sponsored` note), not a gap to
apologize for in the UI; render it plainly ("no recorded Division — passed
by voice vote" or similar factual phrasing, not an empty/broken-looking
state).

## View 3 — Sentiment digest

**Data**: no JSON export exists yet — sentiment is DB (`Storage` /
`SentimentSnapshot`) → page-model → HTML only today
(`src/lpa/politikku_sentiment.py`). **Real prerequisite**: a new export
step (mirroring how `projection.json` is produced) needs to serialize
`SentimentPageModel` (per-coalition `score`, `article_count`,
`delta` vs. 7 days prior, plus `history`: last 14 runs of
`computed_at`/`total_articles`/`scores`) to a
`frontend/public/data/sentiment.json` file. This is Python work, not
frontend work — flagging as a blocking prerequisite for this view, not
something the frontend builder should invent a shape for on their own.

**Render** (once the export exists): `.rows` table, one row per coalition,
score as a horizontal bar (reuse `.sharebar`'s visual language, single-bar
variant) with a delta arrow (↑/↓/→) in mono next to it. History as a
small trend line or sparkline — check whether PolitikKu has any existing
sparkline component before building a new one (none was found in this
session's UI survey; if still true when this is built, keep it simple —
a row of small numbers is acceptable, an elaborate new chart component is
not the point of v1).

## Sequencing note

Views 1 and 2 have real but bounded Python-side prerequisites (extend
`projection.json`, export `data/bills.json` into `frontend/public/data/`).
View 3 has a bigger one (no export exists at all — needs building from
scratch, mirroring `projection.json`'s pattern). If parallelizing further,
the Python export work is independent of the frontend rendering work and
could be split out as its own task, handed to whichever worker frees up
next alongside (not blocking) the frontend view scaffolding.
