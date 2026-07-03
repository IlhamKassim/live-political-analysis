# MyPolitik

**Interactive map of every Malaysian Parliament + DUN seat** — click your *kawasan*
to see the wakil rakyat, party/bloc, GE15 margin, and (soon) a transparently
computed performance score. Built on the [krackedmaps](https://maps.krackeddevs.com)
projection so it aligns pixel-for-pixel with the state map.

Self-contained, no build step. `public/` is a static app served by a tiny
Cloudflare Worker.

```
npm run data      # rebuild all data layers (pipeline/*.py)
npm run dev       # python http.server on :4178  -> http://localhost:4178
npm run deploy:staging   # wrangler deploy --env staging
npm run deploy           # prod
```

## Invariants — read before editing

1. **The projection is FROZEN, copied verbatim from krackedmaps.** `pipeline/01_boundaries.py`
   hardcodes the exact `PROJECTION` constants (viewBox `0 0 799.85 352.74`, Mercator +
   Borneo-shift). **Do not recompute bounds from the seat data** — reusing the frozen
   constants is what keeps MyPolitik aligned with maps.krackeddevs.com (seats could be
   overlaid on the state map). If krackedmaps ever re-bakes its projection, copy the new
   constants here; don't derive your own.
2. **`code_parlimen` (`P.001`…`P.222`) is the universal join key.** DOSM boundaries,
   GE15 results, and scores all key on it. DUN seats key on `code_state_dun` (`1_N.01`)
   because `N.xx` repeats across states; each DUN also carries its parent `parlimen`.
3. **Boundaries are official DOSM** (`dosm-malaysia/data-open`). 222 parlimen, 600 DUN
   (only 13 states have an assembly — the 3 Federal Territories have none).
4. **GE15 `party` is normalised to coalition** in `02_results.py` (`COALITION` map): the
   raw Thevesh ballots mix coalition labels (PH/PN) with component-party labels (DAP/PAS/
   MUDA). The map colours by `coalition`; the panel still shows the component `party`.
   Sanity check after a re-bake: PH 82 · PN 74 · BN 30 · GPS 23 · GRS 6 · WARISAN 3 = 222.
5. **The frontend is data-driven.** `app.js` renders boundaries immediately and lights up
   the *Parti* / *Skor* modes only when `results-ge15.json` / `scores.json` exist
   (`loadOptional()`). Adding a data file is enough to enable a mode — no code change.
6. **Assets dir is `./public`** (not repo root), so `worker.js` / `wrangler.jsonc` are
   never bundled. No `.assetsignore` needed.

## Data pipeline (`pipeline/`)

| Step | Script | Source | Output |
|---|---|---|---|
| 1 | `01_boundaries.py` | DOSM `electoral_0_parlimen` / `electoral_1_dun` | `seats-parlimen.json`, `seats-dun.json` |
| 2 | `02_results.py` | Thevesh `candidates_ge15` / `results_parlimen_ge15` | `results-ge15.json` |
| 3 | `03_results_dun.py` | Thevesh `candidates_prn15` (2023 six-state PRN) | `results-dun.json` |
| 4 | `04_verified_content.py` | Thevesh candidate CSVs + official SPR/MySPR links | `candidates-ge15.json`, `candidates-dun-prn15.json`, `voting-guide.json` |
| 5 | `04_scores.py` *(WIP)* | Hansard via Sinar pardocs / parlimen.gov.my | `scores.json` |

**DUN coverage:** `candidates_prn15.csv` is the **2023 six-state PRN** (Selangor, Kelantan,
Pulau Pinang, Kedah, Negeri Sembilan, Terengganu) — **245 of 600** DUN seats. The other 7
DUN states voted on different dates and aren't in this file, so the frontend (per-seat,
`loadOptional()`) shows their DUN seats' parent-Parliament GE15 result with a "PRN coming
soon" note. A DUN seat with an entry in `results-dun.json` shows its own state-election result.

Raw downloads are cached in `pipeline/raw/` (delete to refresh).

## Data sources & attribution

- Boundaries: **DOSM** — github.com/dosm-malaysia/data-open (official, WGS84)
- Election results: **Thevesh** — github.com/Thevesh/analysis-election-msia (peer-reviewed)
- Candidate rows: **Thevesh / ElectionData.MY** — baked from `candidates_ge15.csv` and
  `candidates_prn15.csv`; voter-specific lookups link out to official **MySPR Semak**
- Projection: **krackedmaps** — maps.krackeddevs.com
- Scores (planned): public **Hansard** (parlimen.gov.my) via **Sinar Project** pardocs

All inputs are public, official records. Scores (step 3) are computed in-house with a
documented, transparent method — MyPolitik does not mirror any third party's proprietary
scores.

## Deploy

Public/deploy name is **mypolitik**. Custom domains:
`mypolitik.xyz` / `www.mypolitik.xyz` (prod), `mypolitik.krackeddevs.com` (prod alias), and
`staging.mypolitik.krackeddevs.com` (staging).

```bash
source ~/.kracked/deploy.env        # CLOUDFLARE_API_TOKEN + ACCOUNT_ID
npx wrangler deploy --env staging   # → staging.mypolitik.krackeddevs.com
npx wrangler deploy                 # → mypolitik.xyz (prod)
```

`wrangler.jsonc` sets `run_worker_first: true` so `/api/health` reaches the Worker
instead of being swallowed by the SPA asset fallback.

## Status

- ✅ Boundaries (parlimen + DUN), interactive map (hover/click/zoom/select/search/reset)
- ✅ GE15 results layer: winner, party/bloc choropleth, majority, turnout, runner-up
- ✅ Polish: golden-angle state palette, shareable URL hash, coalition share-bar
- ✅ i18n: **English default + Bahasa Melayu toggle** (EN/BM, persisted in localStorage).
  Strings live in `I18N` in `app.js`; static markup uses `data-i18n` / `data-i18n-ph` / `data-i18n-title`.
- ✅ **Staging live** — staging.mypolitik.krackeddevs.com
- ✅ DUN (PRN) results — 2023 six-state election (245/600 seats); other states fall back to
  the parent Parliament result with a "coming soon" note
- ⏳ Performance scoring from Hansard (own, transparent method)
- ⏳ DUN for the remaining 7 states · prod promote · mobile pass
