# PRN Johor live results — night-of runbook

## Paths

| Path | Role |
|---|---|
| `pipeline/live/manual.csv` | **Guaranteed path** — type winners as SPR announces |
| `pipeline/live/johor_poller.py` | Merges sources → `public/data/live-johor.json` |
| `pipeline/live/fixtures/midcount.json` | Dress rehearsal |
| `/api/live/johor` | Worker endpoint (KV-backed, data-only PUT publishing) |

## Manual CSV

```csv
code,status,coalition,party,name,majority
N.01,official,BN,UMNO,Datuk Zahari Sarip,7987
1_N.26,leading,BN,UMNO,Datuk Onn Hafiz Ghazi,1200
```

- `status`: `leading` | `won` | `official`
- `code`: `N.01`, `N01`, or `1_N.01`

## Commands

```bash
# reset to campaign (empty tally)
npm run live:campaign

# single poll (manual + sinar cache + optional THESTAR_URL)
npm run live:once

# loop every 90s on the night
npm run live:watch

# dress rehearsal from fixture
npm run live:rehearsal

# publish + deploy staging after each cycle
python3 pipeline/live/johor_poller.py --watch 90 --phase live --deploy staging
```

## Optional feeds

```bash
export THESTAR_URL='https://elections.thestar.com.my/json/<mapType>Johor.json'
# set after night-of recon when the mapType is known
```

Sinar undian: re-fetch seat HTML into `pipeline/raw/sinar_undian/` then run the poller;
`source_sinar` only emits seats with votes > 0.

## Frontend

`refreshPrnLive()` polls `/api/live/johor` while PRN mode is open (keeps looping
through campaign → live so the night flips automatically).

## Autonomous night ops (default)

On the VPS, **systemd keeps the poller alive**:

```bash
systemctl status mypolitik-johor-live   # should be active
# every 60s: Sinar live-fetch 56 seats → merge → atomic write + authenticated PUT to KV
# no Worker/app deploy occurs per cycle; LIVE_PUBLISH_TOKEN is required
```

- Unit: `pipeline/live/mypolitik-johor-live.service`
- Sinar URLs: `pipeline/live/sinar_urls.txt` (56 DUN pages)
- Fallback supervisor cron: every 5 min `johor_supervisor.sh`
- Set `THESTAR_URL=…` in `.env.live` if/when The Star JSON is open
- `SINAR_LIVE=0` disables network scrape (manual-only)

## Rick (Hermes) control plane

```
!johor status | start | stop | once | list | log | campaign
!johor call N.01 official BN UMNO "Name" 1234
!johor uncall N.01
```

Wrapper: `/opt/data/scripts/johor_live.py`  
Working tree: `/opt/data/projects/mypolitik` (Hermes data mount)  
Vault runbook: Master Lab `50_agents/johor-live-ops.md`
