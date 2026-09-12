# Analyst pilot (IDEAS)

## Audience

Think-tank researcher (IDEAS pilot), not campaign strategists.

## Success metric

The contact uses at least one sandbox insight or exported dataset in something they publish.

## Routes

| URL | Purpose |
|-----|---------|
| `/analyst/` | Marketing / concept page (scroll demo) |
| `/analyst/tools/` | **Functional workbench** — sandbox, drill-down, export |

## Local dev

```sh
.venv/bin/python -m lpa.baseline_loader   # once
.venv/bin/python scripts/seed_dev_snapshots.py --days 14   # optional history
.venv/bin/python -m lpa.release_data      # writes public/analyst/data/
cd frontend && npm run dev                # http://localhost:4178/analyst/tools/
```

## Model governance

Sandbox slider changes are **local what-if only** in the browser. Changing production Swing Model constants requires a recorded edit in `data/` and an ADR note. This pilot does not expose a production settings editor.

## Export bundle

Daily release (`lpa.release_data`) writes:

- `public/analyst/data/baseline.json` — GE15 Baseline (FACT)
- `model_config.json`, `current_inputs.json` — MODEL
- `articles.json` — article-level sentiment
- `analyst-bundle.zip` — full bundle with IDEAS topic CSV folders

## Sandbox run export

The workbench **Download this run** button writes JSON + CSV of the current what-if: slider values, flipped Seats, narrative, and the MECo / ElectionData.MY Baseline citation. That file is what to cite. The daily ZIP remains today’s official snapshot.

GE15 Baseline demographics (ethnicity, income) appear in the sandbox table as FACT. They are display-only and do not enter the Swing Model.
