# Live Political Analysis

Tracks sentiment on the Malaysian political landscape and projects the outcome
of the next general election (GE16) — a Coalition-level seat estimate and
whether the Government Coalition retains its Majority.

Runs at zero recurring cost: the sentiment model is self-hosted and open
source, the data sources are free, and nothing calls a paid API
(see [ADR 0002](docs/adr/0002-zero-cost-self-hosted-sentiment-stack.md)).

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
| `lpa/scraper.py` | Outlet feeds → Article records, robots.txt-aware |
| `lpa/sentiment.py` | Self-hosted model, scored per Coalition |
| `lpa/aggregate.py` | The day's Articles → one Sentiment per Coalition |
| `lpa/poll_calibration.py` | Published survey reports → net approval per Coalition |
| `lpa/pipeline.py` | Wires all of the above and stores a snapshot |
| `lpa/storage.py` | Baseline table, daily Projection/Sentiment snapshots, Poll Calibration points |
| `lpa/dashboard.py` | Streamlit page rendering the latest stored Projection |
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
  date once the Election Commission sets one. Edit it the day Parliament is
  dissolved; the dashboard states what it says under the headline Projection.
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

- Projected vote shares are not clamped or renormalised. This cannot change
  which Coalition leads a Seat, so it cannot change a Projection — but it must
  be fixed before any projected *margin* is published.
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
- Only Coalition-level totals ship. Seat-Level Projection is deferred until the
  Swing Model is validated ([ADR 0001](docs/adr/0001-seat-level-baseline-with-coalition-first-projection.md)).
