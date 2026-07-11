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
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRN16 = os.path.join(ROOT, "public", "data", "prn16-johor.json")
OUT = os.path.join(ROOT, "public", "data", "live-johor.json")
LOG_DIR = os.path.join(ROOT, "pipeline", "live", "log")
MANUAL = os.path.join(ROOT, "pipeline", "live", "manual.csv")
SINAR_URLS = os.path.join(ROOT, "pipeline", "live", "sinar_urls.txt")
SINAR_CACHE = os.path.join(ROOT, "pipeline", "raw", "sinar_undian")

# night-of recon fills this in (see docstring); leave None to skip the source
THESTAR_URL = os.environ.get("THESTAR_URL") or None
# skip live network fetches only if explicitly disabled
SINAR_LIVE = os.environ.get("SINAR_LIVE", "1") not in ("0", "false", "no")
SINAR_WORKERS = int(os.environ.get("SINAR_WORKERS", "10"))

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MyPolitikPoller/1.0"

COALITIONS = ("BN", "PH", "PN", "BERSAMA", "MUDA-PSM", "OTHERS", "MUDA", "BEBAS", "OTHER")


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


def http_get(url, timeout=18):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def source_thestar(by_name):
    if not THESTAR_URL:
        return None
    url = THESTAR_URL + ("&" if "?" in THESTAR_URL else "?") + f"v={int(time.time())}"
    try:
        raw = http_get(url, timeout=20)
        data = json.loads(raw)
    except Exception as e:
        print(f"[{now_iso()}] thestar fetch failed: {e}", file=sys.stderr)
        return None
    log_snapshot("thestar", data if isinstance(data, (dict, list)) else {"raw": str(data)[:2000]})
    # Best-effort shape adapter: list of {name|seat|constituency, winner|candidate, party|coalition, majority|votes}
    items = data if isinstance(data, list) else (data.get("seats") or data.get("data") or data.get("results") or [])
    if not isinstance(items, list):
        return None
    rows = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        code = norm_code(it.get("code") or it.get("ncode") or "")
        if not code:
            code = by_name.get(norm_name(it.get("name") or it.get("seat") or it.get("constituency") or ""))
        if not code:
            continue
        status = (it.get("status") or "leading").lower()
        if status not in ("leading", "won", "official"):
            status = "won" if it.get("winner") or it.get("official") else "leading"
        coal = (it.get("coalition") or it.get("bloc") or "").strip().upper() or None
        party = (it.get("party") or "").strip().upper() or None
        wname = it.get("winner") or it.get("candidate") or it.get("name") or None
        maj = it.get("majority") or it.get("majority_votes")
        rows[code] = {
            "status": status,
            "coalition": coal,
            "party": party,
            "name": wname,
            "majority": str(maj) if maj not in (None, "") else None,
        }
    return rows or None


def _slug_to_code_map(prn):
    slug_to_code = {}
    for code, s in prn["seats"].items():
        slug = re.sub(r"[^a-z0-9]", "", (s.get("name") or "").lower())
        slug_to_code[slug] = code
    return slug_to_code


def _nk(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def parse_sinar_seat_html(html, code, seat):
    """Pull candidate vote rows from a Sinar undian DUN page."""
    cands = []
    # Primary: ASP.NET labels lblBilUndi next to calon name + parti
    # Walk each calon block (href /calon/…) and grab the following undi number.
    for m in re.finditer(
        r'href=["\']/calon/(\d+)/([a-zA-Z0-9\-]+)["\'][^>]*>\s*(?:<span class="nama">)?([^<]{2,80})',
        html, re.I,
    ):
        name = re.sub(r"\s+", " ", m.group(3)).strip()
        chunk = html[m.start(): m.start() + 2200]
        votes = 0
        um = re.search(r'lblBilUndi[^>]*>([\d,]+)<', chunk, re.I)
        if um:
            try:
                votes = int(um.group(1).replace(",", ""))
            except ValueError:
                votes = 0
        parti = None
        pm = re.search(r"class=['\"]parti[^'\"]*['\"][^>]*>([^<]{1,20})<", chunk, re.I)
        if pm:
            parti = pm.group(1).strip().upper()
        cands.append({"name": name, "votes": votes, "party": parti})

    if not cands:
        return None
    # de-dupe by name, keep max votes
    by_n = {}
    for c in cands:
        k = c["name"]
        if k not in by_n or c["votes"] > by_n[k]["votes"]:
            by_n[k] = c
    ranked = sorted(by_n.values(), key=lambda x: x["votes"], reverse=True)
    if not any(c["votes"] > 0 for c in ranked):
        return None  # still counting / no figures yet

    leader = ranked[0]
    second = ranked[1]["votes"] if len(ranked) > 1 else 0
    maj = leader["votes"] - second
    # majority label on page if present
    mm = re.search(r'lblBilMajoriti[^>]*>([\d,]+)<', html, re.I)
    if mm:
        try:
            maj = int(mm.group(1).replace(",", ""))
        except ValueError:
            pass

    coal = party = leader.get("party")
    # map onto SPR-confirmed candidate when names match
    for c in seat.get("candidates") or []:
        if _nk(c.get("name")) and (
            _nk(c.get("name")) in _nk(leader["name"]) or _nk(leader["name"]) in _nk(c.get("name"))
        ):
            coal, party = c.get("coalition"), c.get("party")
            leader["name"] = c.get("name")
            break
    # if only party acronym known, treat as coalition when it's a bloc
    if coal and coal in COALITIONS and not party:
        party = coal

    # full field with votes so the frontend can paint a per-seat share bar
    field = []
    for rc in ranked:
        f_coal, f_party = rc.get("party"), rc.get("party")
        for c in seat.get("candidates") or []:
            if _nk(c.get("name")) and (
                _nk(c.get("name")) in _nk(rc["name"]) or _nk(rc["name"]) in _nk(c.get("name"))
            ):
                f_coal, f_party = c.get("coalition"), c.get("party")
                field.append({
                    "name": c.get("name") or rc["name"],
                    "votes": rc["votes"],
                    "coalition": f_coal,
                    "party": f_party,
                })
                break
        else:
            if f_coal and f_coal in COALITIONS and not f_party:
                f_party = f_coal
            field.append({
                "name": rc["name"],
                "votes": rc["votes"],
                "coalition": f_coal,
                "party": f_party,
            })

    # Sinar alone never auto-promotes to official; clear majority + votes → leading
    # (manual or second source can promote to won)
    return {
        "status": "leading",
        "coalition": coal,
        "party": party,
        "name": leader["name"],
        "majority": str(maj) if maj is not None else None,
        "votes": leader["votes"],
        "candidates": field,
    }


def _fetch_sinar_url(url, slug_to_code, prn):
    # seat slug = last path segment
    slug = re.sub(r"[^a-z0-9]", "", urllib.parse.unquote(url.rstrip("/").split("/")[-1]).lower())
    code = slug_to_code.get(slug)
    if not code:
        return None, None
    try:
        html = http_get(url, timeout=18)
    except Exception as e:
        return code, ("err", str(e))
    # optional cache write for debugging
    try:
        os.makedirs(SINAR_CACHE, exist_ok=True)
        safe = re.sub(r"[^a-z0-9\-]+", "-", slug)[:80]
        with open(os.path.join(SINAR_CACHE, f"{code}__{safe}.html"), "w", encoding="utf-8") as f:
            f.write(html)
    except OSError:
        pass
    row = parse_sinar_seat_html(html, code, prn["seats"][code])
    return code, row


def source_sinar(by_name):
    """Live-fetch Sinar Harian undian pages for all 56 DUN seats (autonomous).

    Falls back to any HTML already under pipeline/raw/sinar_undian/.
    Only emits seats where at least one candidate has votes > 0.
    """
    with open(PRN16) as f:
        prn = json.load(f)
    slug_to_code = _slug_to_code_map(prn)
    rows_out = {}
    errors = 0

    urls = []
    if SINAR_LIVE and os.path.isfile(SINAR_URLS):
        with open(SINAR_URLS) as f:
            urls = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

    if urls:
        with ThreadPoolExecutor(max_workers=max(2, SINAR_WORKERS)) as pool:
            futs = [pool.submit(_fetch_sinar_url, u, slug_to_code, prn) for u in urls]
            for fut in as_completed(futs):
                try:
                    code, row = fut.result()
                except Exception:
                    errors += 1
                    continue
                if not code:
                    continue
                if isinstance(row, tuple) and row and row[0] == "err":
                    errors += 1
                    continue
                if row:
                    rows_out[code] = row
        print(f"[{now_iso()}] sinar live: {len(rows_out)} seats with votes, {errors} fetch errors / {len(urls)} urls")

    # merge any pre-cached HTML not covered (offline fallback)
    if os.path.isdir(SINAR_CACHE):
        for fn in os.listdir(SINAR_CACHE):
            if not fn.endswith(".html"):
                continue
            code = None
            m = re.match(r"(1_N\.\d{2})__", fn)
            if m:
                code = m.group(1)
            else:
                seat_slug = fn.rsplit(".", 1)[0].split("__")[-1].replace("-", "").lower()
                code = slug_to_code.get(seat_slug)
            if not code or code in rows_out or code not in prn["seats"]:
                continue
            try:
                html = open(os.path.join(SINAR_CACHE, fn), errors="replace").read()
            except OSError:
                continue
            row = parse_sinar_seat_html(html, code, prn["seats"][code])
            if row:
                rows_out[code] = row

    if rows_out:
        log_snapshot("sinar-normalized", rows_out)
    return rows_out or None


SOURCES = [("manual", source_manual), ("thestar", source_thestar), ("sinar", source_sinar)]


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
        # keep the richest candidate vote field from any source that published one
        if best is not None:
            best_field = best.get("candidates") or []
            for _, c in calls:
                field = c.get("candidates") or []
                if len(field) > len(best_field):
                    best_field = field
                # prefer higher leader vote totals when present
                if c.get("votes") is not None and (
                    best.get("votes") is None or int(c.get("votes") or 0) >= int(best.get("votes") or 0)
                ):
                    if field:
                        best_field = field
                    if c.get("votes") is not None:
                        best["votes"] = c["votes"]
            if best_field:
                best["candidates"] = best_field
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
        # wrangler multi-env configs warn if --env is omitted; prod is top-level (empty env name)
        env_args = ["--env", "staging"] if deploy == "staging" else ["--env", ""]
        subprocess.run(
            ["npx", "wrangler", "deploy", *env_args],
            cwd=ROOT, check=True,
            stdout=subprocess.DEVNULL,
            env={**os.environ, **({} if deploy == "staging" else {})},
        )
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
