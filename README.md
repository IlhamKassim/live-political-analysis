# Live Political Analysis

Tracks sentiment on the Malaysian political landscape and projects the outcome
of the next general election (GE16) — a Coalition-level seat estimate and
whether the Government Coalition retains its Majority.

Runs at zero recurring cost by default: the sentiment model is self-hosted
and open source, the data sources are free, and nothing calls a paid API
(see [ADR 0002](docs/adr/0002-zero-cost-self-hosted-sentiment-stack.md),
amended by [ADR 0007](docs/adr/0007-zero-cost-is-default-not-mandate.md) —
free is the default everywhere in this repo, not a hard ceiling).

Vocabulary — Coalition, Seat, Baseline, Sentiment, Swing, Projection — is
defined in [`CONTEXT.md`](CONTEXT.md). Read that first; the code uses those
terms precisely.

## Setup

Python 3.11+.

```sh
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev,sentiment,dashboard]"
```

The `sentiment` extra pulls `torch`, `transformers`, `sentencepiece` and
`protobuf`. All four are needed: the XLM-RoBERTa tokeniser fails without
`sentencepiece` *and* `protobuf`, with an error that only mentions the first.

Two more extras, not in the command above because most local work doesn't
need them: `postgres` (`psycopg`) to point `DATABASE_URL` at a real hosted
database instead of SQLite, and `telegram` (`Pillow`) to run
`lpa.telegram_post`/`lpa.telegram_card` locally — Pillow is needed to
compose the PNG card even when no `TELEGRAM_BOT_TOKEN` is set to actually
send it.

The `dashboard` extra pulls `streamlit` and `pandas`. It is separate from
`sentiment` because the two never run together: the pipeline scores articles
and needs no dashboard, and the dashboard only reads Storage and need not
carry `torch`.

## Running it

Storage is any SQLAlchemy URL — SQLite locally, free-tier Postgres in the
pipeline. Without `DATABASE_URL` it writes `lpa.db` in the working directory.

```sh
export DATABASE_URL="sqlite+pysqlite:///$PWD/lpa.db"
```

Load the Baseline once. It is GE15 (2022) historical fact and does not change:

```sh
.venv/bin/python -m lpa.baseline_loader     # writes 222 Seat Baselines
```

Then run the pipeline — scrape, score, aggregate, project, store:

```sh
.venv/bin/python -m lpa.pipeline
```

It prints the day's Sentiment and Projection and stores one snapshot row per
table. Re-running the same day corrects that day rather than adding a second
answer for it. The Baseline must be loaded first; the pipeline refuses to run
without it, and refuses to store a run that scraped nothing.

Poll Calibration is separate and periodic. Merdeka Center publishes a survey
report every few months, as a PDF and behind no API, so a person transcribes
one into `data/poll_calibration.json` and runs:

```sh
.venv/bin/python -m lpa.poll_calibration   # ingests every transcribed report
```

It prints the net approval it derives per Coalition and which leaders it could
not attribute to one. Re-running corrects a report rather than duplicating it,
and never deletes reports the data file no longer lists. The full process —
finding the report, which chart to read, and how to attribute a leader to a
Coalition — is [`docs/poll-calibration.md`](docs/poll-calibration.md).

To see the Scraper alone:

```sh
.venv/bin/python -m lpa.scraper             # prints Article records as JSON
```

## The dashboard

Read-only — it renders whatever the pipeline last stored, and never scrapes
or projects itself.

```sh
.venv/bin/streamlit run src/lpa/dashboard.py
```

The Sentiment trend needs at least two days of history to draw a line; with
one day it says so and shows that day's scores as bars instead. A fresh
database has exactly one day, so to see the trend, backfill some:

```sh
.venv/bin/python scripts/seed_dev_snapshots.py --days 14
```

Those days carry invented Sentiment — a seeded random walk — run through the
real Swing Model against the real Baseline. It refuses to touch anything but
SQLite and never overwrites a day that already has a snapshot, so it cannot
displace a real pipeline run. Local development only; never seed the
database the dashboard publishes from.

Poll Calibration points are drawn on the Sentiment trend as diamonds, but only
where a report's fieldwork closed inside the span of stored daily history —
otherwise one point months back would stretch the x axis and flatten the trend
it is there to show. The comparison table below the chart always shows the
latest report, whether or not it could be drawn.

Reads are cached for 15 minutes, so a pipeline run that finishes while a tab
is open takes up to that long to appear.

## The public site

A second surface over the same Storage, and a different thing from the
dashboard above. Every page of it is a static file rather than a served app
([ADR 0006](docs/adr/0006-static-html-for-the-public-page.md)) — the daily
Action renders and publishes them, so public traffic never reaches the
database. It is served at [politikku.my](https://politikku.my)
(`public/CNAME`).

Since #104's cutover ([ADR
0011](docs/adr/0011-politikku-becomes-the-site-old-dashboard-moves-to-projection.md))
the site *is* PolitikKu: the homepage at `/`, the landing page at
`/landing.html`, one MP profile per Seat under `/mp/`, and the seat
projection — one day's Projection drawn as the Dewan Rakyat, with all 222
Seats called individually — at `/projection/`, with the full methodology at
`/methodology.html`. Each page has a Bahasa Malaysia sibling under `/ms/`
(`/ms/`, `/ms/landing.html`, `/projection/ms/`, …).

```sh
.venv/bin/python -m lpa.politikku_homepage      # public/index.html + public/ms/
.venv/bin/python -m lpa.politikku_landing
.venv/bin/python -m lpa.politikku_projection    # /projection/ + /methodology.html
.venv/bin/python -m lpa.politikku_mp_profile
.venv/bin/python -m lpa.politikku_lookup_index  # public/data/lookup-index.json
(cd ts && npm ci && npm run build)              # public/lookup.js
```

`lpa.public_page` no longer renders a page of its own — the old chamber
dashboard's URL was what the cutover retired — but it is still where
`page_model()` computes every figure the pages above state, and every one of
them imports it. Its own renderer and preview server still work, and remain
the fastest way to iterate on that shared model. Every request re-renders
from Storage and the browser reloads itself when the output changes, so a
saved edit is on screen without a build step:

```sh
.venv/bin/python scripts/preview_public_page.py     # http://127.0.0.1:8000
```

The pages need a Projection carrying Seat Calls, which means one computed
since Seat-Level Projection shipped; they refuse to draw an empty chamber
rather than render 222 blanks that look like a result.

Each day's run also writes a **dated, citable copy** of the projection page
alongside the live one (`public/projection/YYYY/MM/DD.html`) — the "cite
this" link points at it, so a figure quoted from the site still resolves once
tomorrow's run overwrites `index.html` (issue #55).

Three more surfaces are rendered from the same Storage, by the same daily run:

- **Machine-readable export** — `python -m lpa.public_export` writes
  `public/projection.json` and `public/projection.csv`: the same Projection
  as data, for a journalist or third party who wants to cite or build on the
  numbers directly rather than scrape the HTML.
- **Shareable Seat Call cards** — `python -m lpa.seat_call_card --all`
  writes one SVG per Seat Call to `public/cards/`, in the same register as
  the public page (issue #23).
- **Return Trigger push** — `python -m lpa.telegram_post` decides whether
  today is worth a push (`return_trigger.py`; three trigger types: Election
  Status change, a State Election Signal, or a chamber-wide Majority swing —
  see `CONTEXT.md`'s Return Trigger definition), composes a Seat-anchored or
  aggregate post with a PNG card (`telegram_card.py`), and sends it to a
  Telegram channel if `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHANNEL_ID` are set as
  repository secrets. Runs safely either way — without those secrets it logs
  what it would have posted and sends nothing. Always (re)writes
  `public/feed.xml`, an Atom feed of every Return Trigger post ever composed,
  whether or not it was actually sent (issue #40).

## Site-literacy pages

`public/learn/` (glossary, Coalition explainer, GE16 process — issue #22) is
hand-authored, not rendered by the pipeline: nothing in it depends on
Storage or the day's Projection, so it doesn't regenerate daily.

```sh
.venv/bin/python -m lpa.citation_check public/learn/<page>.html
```

Verifies every factual claim on a page actually traces to its cited source —
required before any site-literacy content counts as done (issue #22's
"Verification — settled"), with no per-claim human gate. Shells out to the
`claude` CLI's subscription seat as the judge, not the metered API ADR 0002
rules out for unattended use.

## Deploying it

Two moving parts, both free: a scheduled GitHub Action runs the pipeline daily
against a hosted Postgres, and Streamlit Community Cloud serves the dashboard
from that same database.

Both need accounts, so the setup is a wizard rather than a list of steps:

```sh
scripts/setup_deployment.sh
```

It creates the Neon Postgres, sets the `DATABASE_URL` Actions secret, loads
the Baseline and runs the pipeline on GitHub to prove the schedule works, then
walks through the Streamlit deploy. Stop and re-run it at any point.

`.github/workflows/daily.yml` runs at 15:00 UTC — 23:00 in Malaysia, late
enough in the Malaysian day that a snapshot covers the day it is dated for.
It runs the pipeline, renders every public surface above (page, dated
permalink, export, cards, feed/Telegram), and deploys to GitHub Pages, all
on GitHub's free hosted runners. `bootstrap.yml` loads the Baseline and is
run by hand, once, because the Baseline is historical fact rather than
daily data.

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID` are optional repository
secrets — without them the Return Trigger step still runs and still writes
`public/feed.xml`, it just doesn't send anything.

The connection string a provider gives you works as-is:
`storage.normalise_database_url` names the driver, so `postgresql://…` does
not have to be hand-edited into `postgresql+psycopg://…`.

GitHub disables a scheduled workflow after 60 days with no commits to the
repository. If snapshots stop appearing during a quiet stretch, that is the
first thing to check.

## Tests

```sh
.venv/bin/python -m pytest                  # fast; no network, no model
.venv/bin/python -m pytest -m model         # loads the real model, ~10s cached
```

The Dashboard has no automated tests. Per issue #1 it is verified by running
the pipeline end to end and looking at the page — including its thin-history
and empty-database states, which are the ones a fresh deployment hits first.

The default run excludes tests marked `model`. Those download model weights on
first use (a few hundred MB) and do real CPU inference; everything else runs
against fixtures with no network, so CI stays fast and offline.

## Layout

| Module | Role |
| --- | --- |
| `lpa/domain.py` | The record types: `SeatBaseline`, `Article`, `Projection`, … |
| `lpa/swing_model.py` | The seam. Baseline + Sentiment + State Election Signal → Projection, pure |
| `lpa/baseline_loader.py` | GE15 per-Seat Baseline from public datasets |
| `lpa/sources.py` | The Baseline Loader's only I/O — fetches the underlying election/census CSVs |
| `lpa/scraper.py` | Outlet feeds → Article records, robots.txt-aware |
| `lpa/sentiment.py` | Self-hosted model, scored per Coalition |
| `lpa/aggregate.py` | The day's Articles → one Sentiment per Coalition |
| `lpa/poll_calibration.py` | Published survey reports → net approval per Coalition |
| `lpa/pipeline.py` | Wires all of the above and stores a snapshot |
| `lpa/storage.py` | Baseline table, daily snapshots, Poll Calibration points, the frozen archive |
| `lpa/dashboard.py` | Streamlit page rendering the latest stored Projection |
| `lpa/public_page.py` | `page_model()` — every figure the public pages state, computed from Storage (ADR 0006). Its own renderer is retired as a published page (ADR 0011) |
| `lpa/politikku_shell.py` | The persistent site chrome (header, trust strip, EN/BM toggle, footer) and the one routing table behind every internal link |
| `lpa/politikku_homepage.py` | The homepage at `/` |
| `lpa/politikku_landing.py` | The landing page at `/landing.html` |
| `lpa/politikku_projection.py` | `/projection/` + `/methodology.html` + the dated permalink |
| `lpa/politikku_mp_profile.py` | One MP profile page per Seat, under `/mp/` |
| `lpa/politikku_lookup_index.py` | `public/data/lookup-index.json`, the constituency lookup's client-side data |
| `lpa/public_export.py` | The Projection as `projection.json`/`projection.csv` |
| `lpa/seat_call_card.py` | One shareable SVG per Seat Call, written to `public/cards/` |
| `lpa/return_trigger.py` | Pure: does today's Storage state cross a Return Trigger threshold |
| `lpa/telegram_card.py` | PNG rendering for the Telegram post images |
| `lpa/telegram_post.py` | Composes and sends the Return Trigger post; writes `feed.xml` |
| `lpa/citation_check.py` | Verifies a `public/learn/` page's claims against its cited sources |
| `lpa/config.py` | Loads everything under `data/` |

## Configuration is data, not code

Everything politically volatile lives in `data/` so it can be updated without
touching model logic. Each file carries a `_comment` explaining its rules.

- **`coalitions.json`** — Government Coalition membership, the party→Coalition
  rollup, and how each Coalition is named in coverage. Edit this if the
  coalition realigns; the Swing Model needs no change.
- **`outlets.json`** — the feeds the Scraper reads.
- **`state_elections.json`** — state elections held since GE15, maintained by
  hand. Currently Johor 2026; Malacca's is due by November 2026.
- **`election_status.json`** — whether GE16 has been called, and the polling
  date once the Election Commission sets one. Edit it the day the Dewan Rakyat
  is dissolved; the dashboard states what it says under the headline Projection.
- **`poll_calibration.json`** — Merdeka Center reports, transcribed by hand.
  Each entry carries the published percentages verbatim plus the provenance
  to go and check them, and records which Coalition each rated leader sat in
  *at the time of the fieldwork* — a historical fact about the poll, not
  something derived from current membership.

## Model status — read before trusting a number

The Projection is model-driven and **not calibrated**. Two constants in
`SwingModelConfig` were chosen by judgement, not fitted to anything:
`sentiment_sensitivity` (0.10) and `state_signal_weight` (0.5).
See [ADR 0003](docs/adr/0003-provisional-swing-constants.md).

Poll Calibration now supplies the published series to check them against, and
the dashboard shows it beside News Sentiment — but nothing is fitted yet, and
no Projection reads a poll. Fitting needs a daily Sentiment history long
enough to overlap several reports, and reports arrive every few months, so
this is waiting on elapsed time rather than on code.

Other known limitations, each documented at its site in the code:

- A projected margin is a lead under a Swing that is uniform within a state, and
  the model carries no Seat-specific signal at all: two Seats in the same state
  with the same GE15 margin always get the same answer, and
  `SeatBaseline.demographics` is loaded but read by nothing. A per-Seat call is
  arithmetic against GE15, not a judgement about that constituency
  ([ADR 0005](docs/adr/0005-publish-the-seat-level-projection.md)).
- Sentiment is an unweighted mean over articles, so a prolific outlet counts
  for more than a quiet one, and syndicated copy running in two outlets counts
  twice. Nothing de-duplicates. This is why `data/outlets.json` weighs a
  candidate outlet's newsroom rather than just its feed.
- Five of the seven outlets named in issue #1 are read, not all seven. The
  Star publishes no working feed and Sinar Daily's robots.txt forbids its
  one; both reasons are recorded in `data/outlets.json`.
- Two Bahasa Malaysia outlets are read — Berita Harian and Utusan Malaysia —
  against five English ones, so Malay coverage is present but is the smaller
  half of the sample. Neither is named by issue #1: of the outlets it names,
  only Bernama has a Malay edition and its feed answers 500.
- Bernama's feed dates no article, so those Articles carry no
  `published_at`. Nothing reads the field yet; anything that starts to must
  handle its absence.
- Per-Seat rows are kept for the latest two days only (enough to diff for a
  Return Trigger, issue #54), so there is no long per-Seat history to look
  back over — just what changed since yesterday, beside the Coalition
  totals that are kept per day. The exception: once Election Status is
  "called," every day's full Seat-Level Projection is archived permanently
  into `frozen_projection`/`frozen_seat_call`, exempt from the two-day
  window ([ADR 0005](docs/adr/0005-publish-the-seat-level-projection.md)).
