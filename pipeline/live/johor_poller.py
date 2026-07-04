#!/usr/bin/env python3
"""PRN16 Johor polling-night poller.

Polls result sources, normalizes to our seat codes (1_N.01–1_N.56), cross-confirms,
appends every raw fetch to an append-only provenance log, and publishes
public/data/live-johor.json (optionally auto-deploying so /api/live/johor serves it).

Confirmation state machine per seat:
  counting  -> no source has a call
  leading   -> at least one source reports a leader (vote counting under way)
  won       -> two independent sources agree on the winner, OR one source plus a
               manual/official confirmation row
  official  -> the manual CSV marks it official (SPR announcement heard/seen)

Sources are PLUGGABLE and all optional; the manual CSV alone is a complete,
guaranteed path (56 rows typed from official announcements on the night):

  pipeline/live/manual.csv    columns: code,status,coalition,party,name,majority
  (status: leading|won|official; code accepts "N.01", "N01" or "1_N.01")

Usage:
  python3 pipeline/live/johor_poller.py --once --phase live            # single cycle
  python3 pipeline/live/johor_poller.py --watch 90 --phase live        # loop
  python3 pipeline/live/johor_poller.py --once --phase live --deploy staging
  python3 pipeline/live/johor_poller.py --fixture pipeline/live/fixtures/midnight.json
  python3 pipeline/live/johor_poller.py --once --phase campaign        # reset

The Star recon (night-of): their page polls
  https://elections.thestar.com.my/json/<mapType>Johor.json?v=<ts>
Set THESTAR_URL below once the real mapType is known (17:00 MYT recon, 11 Jul).
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRN16 = os.path.join(ROOT, "public", "data", "prn16-johor.json")
OUT = os.path.join(ROOT, "public", "data", "live-johor.json")
LOG_DIR = os.path.join(ROOT, "pipeline", "live", "log")
MANUAL = os.path.join(ROOT, "pipeline", "live", "manual.csv")

# night-of recon fills this in (see docstring); leave None to skip the source
THESTAR_URL = os.environ.get("THESTAR_URL") or None

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MyPolitikPoller/1.0"

COALITIONS = ("BN", "PH", "PN", "BERSAMA", "MUDA-PSM", "OTHERS")


def now_iso():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def load_seatmap():
    with open(PRN16) as f:
        prn = json.load(f)
    by_code, by_name = {}, {}
    for code, s in prn["seats"].items():
        by_code[code] = s
        by_name[norm_name(s["name"])] = code
    return prn, by_code, by_name


def norm_name(n):
    return re.sub(r"[^a-z0-9]", "", (n or "").lower())


def norm_code(raw):
    m = re.search(r"N\.?\s?0?(\d{1,2})", str(raw or ""), re.I)
    return f"1_N.{int(m.group(1)):02d}" if m else None


def log_snapshot(source, payload):
    os.makedirs(LOG_DIR, exist_ok=True)
    day = dt.date.today().isoformat()
    body = json.dumps(payload, ensure_ascii=False)
    rec = {
        "ts": now_iso(), "source": source,
        "sha256": hashlib.sha256(body.encode()).hexdigest()[:16],
        "payload": payload,
    }
    with open(os.path.join(LOG_DIR, f"snapshots-{day}.jsonl"), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---- sources: each returns {code: {status, coalition, party, name, majority}} ----

def source_manual(by_name):
    if not os.path.exists(MANUAL):
        return None
    rows = {}
    with open(MANUAL, newline="") as f:
        for row in csv.DictReader(f):
            code = norm_code(row.get("code")) or by_name.get(norm_name(row.get("code")))
            if not code:
                continue
            status = (row.get("status") or "won").strip().lower()
            if status not in ("leading", "won", "official"):
                status = "won"
            rows[code] = {
                "status": status,
                "coalition": (row.get("coalition") or "").strip().upper() or None,
                "party": (row.get("party") or "").strip().upper() or None,
                "name": (row.get("name") or "").strip() or None,
                "majority": (row.get("majority") or "").strip() or None,
            }
    return rows or None


def source_thestar(by_name):
    if not THESTAR_URL:
        return None
    url = THESTAR_URL + ("&" if "?" in THESTAR_URL else "?") + f"v={int(time.time())}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://election.thestar.com.my/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    log_snapshot("thestar", data)
    # shape unknown until night-of recon — expect a list/dict of seats with name/winner/party.
    # Adapt here on the 11th; return None until then so the poller never guesses.
    return None


SOURCES = [("manual", source_manual), ("thestar", source_thestar)]


def merge(readings):
    """Cross-confirm independent source readings into the published seat states."""
    seats = {}
    all_codes = set()
    for _, r in readings:
        all_codes.update(r.keys())
    for code in sorted(all_codes):
        calls = [(src, r[code]) for src, r in readings if code in r]
        if not calls:
            continue
        # official/manual wins outright; else two agreeing sources -> won; one -> leading cap
        best = None
        by_winner = {}
        for src, c in calls:
            key = (c.get("coalition") or "?", c.get("party") or "?")
            by_winner.setdefault(key, []).append((src, c))
        for key, group in by_winner.items():
            srcs = {s for s, _ in group}
            c = dict(group[0][1])
            manual = "manual" in srcs
            claimed = max((g[1].get("status") or "leading") for g in group)
            if manual or len(srcs) >= 2:
                status = c.get("status") if manual else "won"
                if not manual and claimed == "leading":
                    status = "leading"
            else:
                status = "leading"   # single non-manual source never publishes a win
            c["status"] = status
            c["sources"] = sorted(srcs)
            if best is None or ("won", "official").count(c["status"]) > ("won", "official").count(best["status"]):
                best = c
        seats[code] = best
    return seats


def publish(phase, seats, prn, deploy=None, source_label=None):
    tally = {}
    for r in seats.values():
        coal = r.get("coalition") or r.get("party")
        if coal and r.get("status") in ("won", "official"):
            tally[coal] = tally.get(coal, 0) + 1
    out = {
        "phase": phase,
        "updated": now_iso(),
        "election": prn["election"]["id"],
        "source": source_label or "manual + cross-checked feeds",
        "tally": tally,
        "seats": seats,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    declared = sum(1 for r in seats.values() if r.get("status") in ("won", "official"))
    print(f"[{now_iso()}] published phase={phase} declared={declared}/56 tally={tally}")
    if deploy:
        env = ["--env", "staging"] if deploy == "staging" else []
        subprocess.run(["npx", "wrangler", "deploy", *env], cwd=ROOT, check=True,
                       stdout=subprocess.DEVNULL)
        print(f"[{now_iso()}] deployed to {deploy}")


def cycle(phase, prn, by_code, by_name, deploy):
    readings = []
    for name, fn in SOURCES:
        try:
            r = fn(by_name)
            if r:
                readings.append((name, r))
                log_snapshot(f"{name}-normalized", r)
        except Exception as e:
            print(f"[{now_iso()}] source {name} failed: {e}", file=sys.stderr)
    seats = merge(readings)
    # sanity: never publish a seat code we don't know
    seats = {c: v for c, v in seats.items() if c in by_code}
    publish(phase, seats, prn, deploy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="live", choices=["campaign", "live", "final"])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--watch", type=int, metavar="SECONDS")
    ap.add_argument("--deploy", choices=["staging", "prod"])
    ap.add_argument("--fixture", help="publish a fixture JSON as-is (dress rehearsal)")
    args = ap.parse_args()

    prn, by_code, by_name = load_seatmap()

    if args.fixture:
        with open(args.fixture) as f:
            fx = json.load(f)
        seats = {c: v for c, v in fx.get("seats", {}).items() if c in by_code}
        publish(fx.get("phase", "live"), seats, prn, args.deploy, source_label="dress rehearsal fixture")
        return

    if args.phase == "campaign":
        # reset: publish an empty campaign file (the worker treats it as the default)
        publish("campaign", {}, prn, args.deploy)
        return

    if args.watch:
        while True:
            cycle(args.phase, prn, by_code, by_name, args.deploy)
            time.sleep(args.watch)
    else:
        cycle(args.phase, prn, by_code, by_name, args.deploy)


if __name__ == "__main__":
    main()
