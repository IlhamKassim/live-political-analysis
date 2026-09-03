# PRN Playbook — running the next live state election

How to stand up campaign + polling-night mode for a new PRN (Sarawak, Melaka, …)
the way PRN16 Johor was run. Distilled from a full code audit (2026-08-02) of every
Johor-hardcoded seam. The N9 2026 election skipped this machinery entirely (results
imported post-hoc via `pipeline/n9_results.py`) — this doc is for running one LIVE.

**Likely next:** Sarawak (clock says "expected 2026", auto-dissolve 14 Feb 2027;
82 seats, code prefix `13_`, majority 42) and Melaka (assembly expires 27 Dec 2026;
28 seats, prefix `4_`, majority 15).

## The good news: the runtime engine is generic

Everything that decides and renders a live election reads ONE config object —
`state.prn16.election` `{id, name, state, tier, nomination_day, early_voting,
polling_day, total_seats, majority, phase, source, check_voter_url}`:

- `liveElection()` (app.js:5295), `prnActiveForState()` (:5298), `openPrnMode()`
  (:5533), `closePrnMode()`, `prnUpcomingOrLive()` — zero literals.
- Countdown (`prnCountdownLabel` :5312), phase handling (`refreshPrnLive` :5687,
  15s hot / 60s campaign polling), status meta (awaiting/leading/called/official).
- Sidebar/nav gating, `#dun/parti[/seat]/prn` deep link (lib.js codec), PRN view,
  seat cards, bento live table, live filter chips (derived from `contested` keys).
- CSS, index.html, lib.js: fully election-agnostic. `STATE_FLAG_ASSETS` complete.
- Worker KV binding `PRN_LIVE` + `LIVE_PUBLISH_TOKEN` secret: reusable as-is.

The Johor kill-switch that ended PRN16 is data, not code: `prn16-johor.json` has
`"election": null` (config parked under `"_election_concluded"`). **Before layering
a new election, confirm `liveElection()` is still null** or the two will fight.

## The hardwired seams (what actually must change)

| Layer | Seam |
|---|---|
| app.js loaders | `fetch` paths hardcoded: prn16-johor.json (:251), johor-pledges (:256), politician-profiles-johor (:289), seat-context-johor (:294), exco-johor (:299); live URLs `["data/live-johor.json", "/api/live/johor"]` (:5695, order flips on localhost) |
| app.js helpers | `johorSeatContext` (:316), `johorExcoForSeat` (:320), `johorDunResultRaw/johorDunResult` (:1666/:1682, stamps `_johor2022`), `johorNewsItems` (:6853), `resultSourceText` branch on `_johor2022` (:2168) |
| app.js `1_` prefix | :5719, :5914, :5926, :6103-6111 — bare-code fallbacks literally strip/add `1_`. Harmless no-ops for other states (regex `/^1_/` doesn't match `10_`–`13_`), but the poller bare-key fallback silently stops working. Derive the prefix from the election's seat codes instead. |
| app.js misc | `PRN_COLORS` (:5304) needs the new state's blocs (Sarawak: GPS, PBB, SUPP, PDP, PRS, PSB); `prnLiveStats` fallbacks `\|\| 29`/`\|\| 56` (:5655); popular-vote tile requires literal `BN`+`PH` keys (:5363) |
| worker.js | route `/api/live/johor` (:16), payload assert `election !== "prn16-johor"` (:34), KV key `"johor"` (:37/:47), asset fallback `/data/live-johor.json` (:51) |
| i18n.js | `prn_open` "View PRN Johor 2026" (:72/:431), `news_title` (:188/:547), `src_johor2022` (:287/:646), `prn_source` frozen source string (:136), `prn_popular_vote` BN/PH literal (:142). ~90 other `prn_*` keys are generic. |
| pipeline | `05_prn16_johor.py` (bakes master; `== "Johor"` + `assert 56`), `06_candidate_news.py`, `12_johor_profiles.py`, `13_johor_enrich.py` (EXCO_SEED with literal `1_N.xx`), `johor_results.py`, `live/johor_poller.py` (`norm_code` emits `1_N.xx`; Sinar URL list; MYUNDI_COAL bloc map), `live/johor_live_ops.py`, systemd unit + supervisor |
| package.json | `data:johor-*`, `live:*` scripts point at johor_* files |

## Route A — minimal change (reuse the Johor slots, one more cycle only)

Cheapest path, no refactor; every file stays misnamed (acceptable once, not twice):

1. Bake the new master INTO `public/data/prn16-johor.json` with
   `election.state/"total_seats"/"majority"/dates/id` for the new state.
2. `worker.js:34`: accept the new election id.
3. Fix the four `1_` sites to derive the prefix from the config's seat codes.
4. Reword `prn_open` / `news_title` / `src_johor2022` (EN + MS).
5. Add the state's blocs to `PRN_COLORS`; extend the poller's `MYUNDI_COAL` map.
6. Replace `pipeline/live/sinar_urls.txt` with the new state's undian URLs;
   `johor_poller.py norm_code()` must emit the right prefix.
7. `07_state_context.py`: caretaker flag + clock for the new state; regen.

## Route B — proper genericization (recommended before Sarawak's 82 seats)

- `public/data/elections/<id>.json` (+ `-live`, `-seat-context`, `-exco`,
  `-pledges`, `-profiles`) + `election-manifest.json` `{active: "<id>"|null}`;
  app loads the manifest, then derives all paths + `/api/live/${id}`.
- Worker: `match(/^\/api\/live\/([a-z0-9-]+)$/)`, assert `body.election === id`,
  KV key = id, fallback `/data/elections/${id}-live.json`.
- Rename helpers (`johorSeatContext`→`prnSeatContext` etc.); `_johor2022` →
  `_prnIncumbent: {year}` with `src_prn_incumbent` `{s}/{y}` i18n; kill the
  `||29/||56` fallbacks; popular-vote takes top-two blocs.
- Fork pipeline scripts with `--election/--state` flags (follow
  `n9_results.py`'s `ELECTION/ELECTION_ID/STATE_NAME` constants pattern — it's
  the closest template in the repo); EXCO seed → per-state JSON.

## Per-election content that must be produced fresh (no code generates it)

SPR nomination CSV (candidates × seats, triple-cross-checked — see AGENT_LOG
2026-07-04 for the Johor method); Sinar undian URL list (one per DUN); caretaker
EXCO roster with `<sc>_N.xx` codes; coalition pledges; Bernama official-results
URL + page anchor (cf. `johor_results.py:33/:170`, `n9_results.py`); night-of
ops (systemd unit, supervisor path, Discord verb, fresh live/README).

## Pre-flight (night before)

- `curl /api/live/<id>` → `{"phase":"campaign"}`; KV put/get round-trip
  (TTL 900 self-expires a stalled poller back to the baked asset — test it).
- `assert_prod_checkout_current()` refuses prod deploys from a stale checkout —
  sync the poller checkout BEFORE the night.
- Fixture rehearsal: `--fixture pipeline/live/fixtures/midcount.json`.
- Seat-code end-to-end: poller emits `13_N.05` → live table row → map flash.

## After polling night

Official import + permanent record: follow `johor_results.py` / `n9_results.py`
(Bernama official page → committed snapshot → results-dun/candidates/aduns
updates + rebuild-preservation hooks in `03_results_dun.py` and
`04_verified_content.py`), then clear `dissolved_assemblies`, update
`07_state_context.py` (MB, caretaker, clock), and park the election config
under `"_election_concluded"`.
