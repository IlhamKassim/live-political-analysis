#!/usr/bin/env python3
"""Generalized live election polling-night engine.

Supports any Malaysian state election (PRN) and parliamentary general elections (GE).
Polls result sources, normalizes to canonical seat codes, cross-confirms via a
multi-source state machine, writes append-only provenance snapshots, and publishes
the live election JSON (optionally PUT-publishing to the Cloudflare Worker live API).

Confirmation state machine per seat:
  counting  -> no source has a call
  leading   -> at least one source reports a leader (vote counting under way)
  won       -> two independent sources agree on the winner, OR one trusted source
               (manual CSV / official aggregator) marks won
  official  -> trusted source or manual CSV marks it official (SPR announcement)

Sources are PLUGGABLE and all optional; the manual CSV alone is a complete,
guaranteed path (rows typed from official announcements on the night).

Usage:
  python3 pipeline/live/poller.py --election prn16-johor --once --phase live
  python3 pipeline/live/poller.py --election prn16-johor --watch 90 --phase live
  python3 pipeline/live/poller.py --election prn16-johor --fixture pipeline/live/fixtures/midcount.json
  python3 pipeline/live/poller.py --election prn16-johor --once --phase campaign
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIVE_DIR = os.path.join(ROOT, "pipeline", "live")
ELECTIONS_DIR = os.path.join(LIVE_DIR, "elections")
LOG_DIR = os.path.join(LIVE_DIR, "log")
RAW_DIR = os.path.join(ROOT, "pipeline", "raw")

PROD_BASE_URL = os.environ.get("LIVE_PROD_BASE_URL", "https://mypolitik.krackeddevs.com").rstrip("/")
STAGING_BASE_URL = os.environ.get("LIVE_STAGING_BASE_URL", "https://staging.mypolitik.krackeddevs.com").rstrip("/")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MyPolitikPoller/2.0"

COALITIONS = ("BN", "PH", "PN", "GPS", "GRS", "WARISAN", "BERSAMA", "MUDA-PSM", "OTHERS", "MUDA", "BEBAS", "OTHER")
MYUNDI_COAL_DEFAULT = {
    "BN": "BN", "PN": "PN", "PH": "PH", "MU": "BERSAMA",
    "MUDA": "MUDA-PSM", "PSM": "MUDA-PSM", "BEBAS": "OTHERS", "ASLI": "OTHERS",
    "GPS": "GPS", "GRS": "GRS", "WARISAN": "WARISAN",
}
TRUSTED_SOURCES = {"manual", "myundi"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def norm_name(n: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (n or "").lower())


def norm_code(raw: Any, prefix: str = "1_", by_code: dict[str, Any] | None = None) -> str | None:
    """Normalize seat code to canonical form (e.g. '1_N.01', '4_N.01', 'P.001')."""
    if not raw:
        return None
    raw_str = str(raw).strip()
    if by_code and raw_str in by_code:
        return raw_str

    # Direct match if prefix omitted
    if by_code and not raw_str.startswith(prefix) and f"{prefix}{raw_str}" in by_code:
        return f"{prefix}{raw_str}"

    # Match digits
    m = re.search(r"(?:[NP]\.?\s*)?0?(\d{1,3})", raw_str, re.I)
    if m:
        num = int(m.group(1))
        cand_n = f"{prefix}N.{num:02d}"
        if by_code and cand_n in by_code:
            return cand_n
        cand_p = f"P.{num:03d}"
        if by_code and cand_p in by_code:
            return cand_p
        # If by_code is known, check any code ending with the number
        if by_code:
            target_suffix = f".{num:02d}"
            for c in by_code:
                if c.endswith(target_suffix):
                    return c
        return cand_n

    m2 = re.search(r"N\.?\s?0?(\d{1,2})", raw_str, re.I)
    return f"{prefix}N.{int(m2.group(1)):02d}" if m2 else None


def load_election_config(election_id: str, config_path: str | None = None) -> dict[str, Any]:
    """Load configuration for the target election, resolving paths and defaults."""
    cfg: dict[str, Any] = {}
    if config_path and os.path.isfile(config_path):
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        # Search elections directory
        candidates = [
            os.path.join(ELECTIONS_DIR, f"{election_id}.json"),
            os.path.join(ELECTIONS_DIR, f"{election_id.lower()}.json"),
        ]
        if "johor" in election_id.lower():
            candidates.append(os.path.join(ELECTIONS_DIR, "prn16-johor.json"))

        for cand in candidates:
            if os.path.isfile(cand):
                with open(cand, encoding="utf-8") as f:
                    cfg = json.load(f)
                break

    resolved_id = cfg.get("id") or election_id
    state = cfg.get("state") or (resolved_id.split("-")[-1].capitalize() if "-" in resolved_id else "")
    state_slug = state.lower() if state else resolved_id.lower()

    # Resolve master seatmap file
    master_file = cfg.get("master_file")
    if master_file:
        master_path = master_file if os.path.isabs(master_file) else os.path.join(ROOT, master_file)
    else:
        candidates_master = [
            os.path.join(ROOT, "public", "data", f"{resolved_id}.json"),
            os.path.join(ROOT, "public", "data", f"prn16-{state_slug}.json"),
            os.path.join(ROOT, "public", "data", f"prn17-{state_slug}.json"),
            os.path.join(ROOT, "public", "data", f"{state_slug}.json"),
        ]
        master_path = next((p for p in candidates_master if os.path.isfile(p)), candidates_master[0])

    # Resolve output file
    out_file = cfg.get("out_file")
    if out_file:
        out_path = out_file if os.path.isabs(out_file) else os.path.join(ROOT, out_file)
    else:
        out_path = os.path.join(ROOT, "public", "data", f"live-{state_slug}.json")

    # Resolve manual CSV
    manual_file = cfg.get("manual_csv")
    if manual_file:
        manual_path = manual_file if os.path.isabs(manual_file) else os.path.join(ROOT, manual_file)
    else:
        candidates_manual = [
            os.path.join(LIVE_DIR, f"manual-{resolved_id}.csv"),
            os.path.join(LIVE_DIR, f"manual-{state_slug}.csv"),
            os.path.join(LIVE_DIR, "manual.csv"),
        ]
        manual_path = next((p for p in candidates_manual if os.path.isfile(p)), os.path.join(LIVE_DIR, "manual.csv"))

    # Resolve Sinar URLs
    sinar_file = cfg.get("sinar_urls")
    if sinar_file:
        sinar_path = sinar_file if os.path.isabs(sinar_file) else os.path.join(ROOT, sinar_file)
    else:
        candidates_sinar = [
            os.path.join(LIVE_DIR, f"sinar_urls_{resolved_id}.txt"),
            os.path.join(LIVE_DIR, f"sinar_urls_{state_slug}.txt"),
            os.path.join(LIVE_DIR, "sinar_urls.txt"),
        ]
        sinar_path = next((p for p in candidates_sinar if os.path.isfile(p)), os.path.join(LIVE_DIR, "sinar_urls.txt"))

    # Resolve Sinar cache dir
    sinar_cache = cfg.get("sinar_cache")
    if sinar_cache:
        sinar_cache_path = sinar_cache if os.path.isabs(sinar_cache) else os.path.join(ROOT, sinar_cache)
    else:
        sinar_cache_path = os.path.join(RAW_DIR, "sinar_undian")

    return {
        "id": resolved_id,
        "name": cfg.get("name") or f"PRN {state}",
        "state": state,
        "tier": cfg.get("tier") or "dun",
        "seat_prefix": cfg.get("seat_prefix") or "1_",
        "total_seats": cfg.get("total_seats"),
        "majority": cfg.get("majority"),
        "master_path": master_path,
        "out_path": out_path,
        "manual_path": manual_path,
        "sinar_urls_path": sinar_path,
        "sinar_cache_path": sinar_cache_path,
        "thestar_url": os.environ.get(cfg.get("thestar_url_env") or "THESTAR_URL"),
        "myundi_url": os.environ.get(cfg.get("myundi_url_env") or "MYUNDI_URL", "https://www.myundi.com.my/api/live-results"),
        "api_route": cfg.get("api_route") or f"/api/live/{resolved_id}",
    }


def load_seatmap(master_path: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], str]:
    """Load master seatmap JSON and return (prn_dict, by_code, by_name, derived_prefix)."""
    if not os.path.isfile(master_path):
        raise FileNotFoundError(f"master election seatmap not found at {master_path}")
    with open(master_path, encoding="utf-8") as f:
        prn = json.load(f)
    by_code, by_name = {}, {}
    seats = prn.get("seats", {})
    prefix = "1_"
    for code, s in seats.items():
        by_code[code] = s
        name = s.get("name")
        if name:
            by_name[norm_name(name)] = code
        if "_" in code:
            prefix = code.split("_", 1)[0] + "_"
    return prn, by_code, by_name, prefix


def get_election_meta(prn: dict[str, Any], default_id: str = "prn16-johor") -> dict[str, Any]:
    meta = prn.get("election") or prn.get("_election_concluded") or {}
    total = meta.get("total_seats") or len(prn.get("seats", {}))
    return {
        "id": meta.get("id") or default_id,
        "name": meta.get("name") or "PRN",
        "state": meta.get("state") or "",
        "tier": meta.get("tier") or "dun",
        "total_seats": total,
        "majority": meta.get("majority") or (total // 2 + 1 if total else 0),
    }


def log_snapshot(source: str, payload: Any, log_dir: str = LOG_DIR) -> None:
    os.makedirs(log_dir, exist_ok=True)
    day = dt.date.today().isoformat()
    body = json.dumps(payload, ensure_ascii=False)
    rec = {
        "ts": now_iso(), "source": source,
        "sha256": hashlib.sha256(body.encode()).hexdigest()[:16],
        "payload": payload,
    }
    with open(os.path.join(log_dir, f"snapshots-{day}.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def http_get(url: str, timeout: int = 18) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def assert_prod_checkout_current(prod_base_url: str = PROD_BASE_URL) -> None:
    """Refuse a prod asset deploy if this poller checkout has stale app code."""
    for filename in ("app.js", "styles.css"):
        local_path = os.path.join(ROOT, "public", filename)
        if not os.path.isfile(local_path):
            continue
        with open(local_path, "rb") as f:
            local_hash = hashlib.sha256(f.read()).hexdigest()
        url = f"{prod_base_url}/{filename}?live_guard={int(time.time())}"
        remote_hash = hashlib.sha256(http_get(url, timeout=20).encode("utf-8")).hexdigest()
        if remote_hash != local_hash:
            raise RuntimeError(
                f"refusing prod deploy: {filename} differs from {prod_base_url}; "
                "sync this checkout before restarting the poller"
            )


def publish_remote_live(
    body: dict[str, Any],
    deploy: str,
    election_id: str,
    prod_base_url: str = PROD_BASE_URL,
    staging_base_url: str = STAGING_BASE_URL,
) -> None:
    """Publish the mutable result document to the Cloudflare Worker live API."""
    token = os.environ.get("LIVE_PUBLISH_TOKEN")
    if not token:
        raise RuntimeError("LIVE_PUBLISH_TOKEN is required for data-only live publishing")
    base = prod_base_url if deploy == "prod" else staging_base_url
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/live/{election_id}",
        data=payload,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8", "replace"))
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError(f"live publish rejected by {base}: {result}")


# ---- sources: each returns {code: {status, coalition, party, name, majority, ...}} ----

def source_manual(manual_path: str, by_name: dict[str, str], norm_code_fn: Any) -> dict[str, Any] | None:
    if not os.path.exists(manual_path):
        return None
    rows = {}
    with open(manual_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = norm_code_fn(row.get("code")) or by_name.get(norm_name(row.get("code")))
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


def source_thestar(thestar_url: str | None, by_name: dict[str, str], norm_code_fn: Any, log_dir: str = LOG_DIR) -> dict[str, Any] | None:
    if not thestar_url:
        return None
    url = thestar_url + ("&" if "?" in thestar_url else "?") + f"v={int(time.time())}"
    try:
        raw = http_get(url, timeout=20)
        data = json.loads(raw)
    except Exception as e:
        print(f"[{now_iso()}] thestar fetch failed: {e}", file=sys.stderr)
        return None
    log_snapshot("thestar", data if isinstance(data, (dict, list)) else {"raw": str(data)[:2000]}, log_dir)
    items = data if isinstance(data, list) else (data.get("seats") or data.get("data") or data.get("results") or [])
    if not isinstance(items, list):
        return None
    rows = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        code = norm_code_fn(it.get("code") or it.get("ncode") or "")
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


def _slug_to_code_map(prn: dict[str, Any]) -> dict[str, str]:
    slug_to_code = {}
    for code, s in prn.get("seats", {}).items():
        slug = re.sub(r"[^a-z0-9]", "", (s.get("name") or "").lower())
        slug_to_code[slug] = code
    return slug_to_code


def _nk(s: str | None) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def parse_sinar_seat_html(html: str, code: str, seat: dict[str, Any], coalitions: tuple[str, ...] = COALITIONS) -> dict[str, Any] | None:
    """Pull candidate vote rows from a Sinar undian page."""
    cands = []
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
    by_n = {}
    for c in cands:
        k = c["name"]
        if k not in by_n or c["votes"] > by_n[k]["votes"]:
            by_n[k] = c
    ranked = sorted(by_n.values(), key=lambda x: x["votes"], reverse=True)
    if not any(c["votes"] > 0 for c in ranked):
        return None

    leader = ranked[0]
    second = ranked[1]["votes"] if len(ranked) > 1 else 0
    maj = leader["votes"] - second
    mm = re.search(r'lblBilMajoriti[^>]*>([\d,]+)<', html, re.I)
    if mm:
        try:
            maj = int(mm.group(1).replace(",", ""))
        except ValueError:
            pass

    coal = party = leader.get("party")
    for c in seat.get("candidates") or []:
        if _nk(c.get("name")) and (
            _nk(c.get("name")) in _nk(leader["name"]) or _nk(leader["name"]) in _nk(c.get("name"))
        ):
            coal, party = c.get("coalition"), c.get("party")
            leader["name"] = c.get("name")
            break
    if coal and coal in coalitions and not party:
        party = coal

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
            if f_coal and f_coal in coalitions and not f_party:
                f_party = f_coal
            field.append({
                "name": rc["name"],
                "votes": rc["votes"],
                "coalition": f_coal,
                "party": f_party,
            })

    return {
        "status": "leading",
        "coalition": coal,
        "party": party,
        "name": leader["name"],
        "majority": str(maj) if maj is not None else None,
        "votes": leader["votes"],
        "candidates": field,
    }


def _fetch_sinar_url(url: str, slug_to_code: dict[str, str], prn: dict[str, Any], sinar_cache: str) -> tuple[str | None, Any]:
    slug = re.sub(r"[^a-z0-9]", "", urllib.parse.unquote(url.rstrip("/").split("/")[-1]).lower())
    code = slug_to_code.get(slug)
    if not code:
        return None, None
    try:
        html = http_get(url, timeout=18)
    except Exception as e:
        return code, ("err", str(e))
    try:
        os.makedirs(sinar_cache, exist_ok=True)
        safe = re.sub(r"[^a-z0-9\-]+", "-", slug)[:80]
        with open(os.path.join(sinar_cache, f"{code}__{safe}.html"), "w", encoding="utf-8") as f:
            f.write(html)
    except OSError:
        pass
    row = parse_sinar_seat_html(html, code, prn.get("seats", {}).get(code, {}))
    return code, row


def source_sinar(
    prn: dict[str, Any],
    sinar_urls_path: str,
    sinar_cache: str,
    sinar_live: bool = True,
    sinar_workers: int = 10,
    log_dir: str = LOG_DIR,
) -> dict[str, Any] | None:
    """Fetch Sinar undian pages for all election seats, with offline cache fallback."""
    slug_to_code = _slug_to_code_map(prn)
    rows_out = {}
    errors = 0

    urls = []
    if sinar_live and os.path.isfile(sinar_urls_path):
        with open(sinar_urls_path, encoding="utf-8") as f:
            urls = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

    if urls:
        with ThreadPoolExecutor(max_workers=max(2, sinar_workers)) as pool:
            futs = [pool.submit(_fetch_sinar_url, u, slug_to_code, prn, sinar_cache) for u in urls]
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

    # Offline fallback from cache
    if os.path.isdir(sinar_cache):
        for fn in os.listdir(sinar_cache):
            if not fn.endswith(".html"):
                continue
            code = None
            if "__" in fn:
                cand_code = fn.split("__", 1)[0]
                if cand_code in prn.get("seats", {}):
                    code = cand_code
            if not code:
                seat_slug = fn.rsplit(".", 1)[0].split("__")[-1].replace("-", "").lower()
                code = slug_to_code.get(seat_slug)
            if not code or code in rows_out or code not in prn.get("seats", {}):
                continue
            try:
                html = open(os.path.join(sinar_cache, fn), errors="replace").read()
            except OSError:
                continue
            row = parse_sinar_seat_html(html, code, prn["seats"][code])
            if row:
                rows_out[code] = row

    if rows_out:
        log_snapshot("sinar-normalized", rows_out, log_dir)
    return rows_out or None


def source_myundi(
    myundi_url: str,
    myundi_live: bool,
    myundi_coal: dict[str, str],
    prn: dict[str, Any],
    norm_code_fn: Any,
    tier: str = "dun",
    log_dir: str = LOG_DIR,
    state_label: str = "",
) -> dict[str, Any] | None:
    """myundi.com.my live aggregator feed."""
    if not myundi_live or not myundi_url:
        return None
    try:
        url = myundi_url + ("&" if "?" in myundi_url else "?") + f"v={int(time.time())}"
        data = json.loads(http_get(url, timeout=20)).get("data") or []
    except Exception as e:
        print(f"[{now_iso()}] myundi fetch error: {e}", file=sys.stderr)
        return None
    seats_dict = prn.get("seats", {})
    rows_out = {}
    target_tier = tier.upper()
    for seat in data:
        if seat.get("t") and seat.get("t").upper() != target_tier:
            continue
        code = norm_code_fn(seat.get("c"))
        if not code or code not in seats_dict:
            continue
        cands = []
        for c in seat.get("cn") or []:
            votes = int(c.get("vn") or c.get("uvn") or 0)
            raw_pc = (c.get("pc") or "").upper()
            coal = myundi_coal.get(raw_pc, (raw_pc or "OTHERS"))
            cands.append({"name": (c.get("n") or "").strip(), "votes": votes,
                          "party": (c.get("pn") or "").strip(), "coalition": coal})
        if not cands or not any(x["votes"] > 0 for x in cands):
            continue
        cands.sort(key=lambda x: x["votes"], reverse=True)
        leader = cands[0]
        runner = cands[1]["votes"] if len(cands) > 1 else 0
        won_flag = any((c.get("uvs") or c.get("vs")) == "WON" for c in (seat.get("cn") or []))
        status = "official" if seat.get("s") == "final" else ("won" if won_flag else "leading")
        rows_out[code] = {
            "status": status,
            "coalition": leader["coalition"],
            "party": leader["party"],
            "name": leader["name"],
            "majority": str(leader["votes"] - runner),
            "votes": leader["votes"],
            "candidates": cands,
        }
    if rows_out:
        log_snapshot("myundi-normalized", rows_out, log_dir)
        lbl = state_label or "election"
        print(f"[{now_iso()}] myundi: {len(rows_out)} {lbl} seats")
    return rows_out or None


def merge(readings: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Cross-confirm independent source readings into published seat states."""
    seats = {}
    all_codes = set()
    for _, r in readings:
        all_codes.update(r.keys())
    for code in sorted(all_codes):
        calls = [(src, r[code]) for src, r in readings if code in r]
        if not calls:
            continue
        best = None
        by_winner = {}
        for src, c in calls:
            key = (c.get("coalition") or "?", c.get("party") or "?")
            by_winner.setdefault(key, []).append((src, c))
        for key, group in by_winner.items():
            srcs = {s for s, _ in group}
            group = sorted(group, key=lambda g: 0 if g[0] in TRUSTED_SOURCES else 1)
            c = dict(group[0][1])
            trusted = srcs & TRUSTED_SOURCES
            claimed = max((g[1].get("status") or "leading") for g in group)
            if trusted or len(srcs) >= 2:
                status = c.get("status") if trusted else "won"
                if not trusted and claimed == "leading":
                    status = "leading"
            else:
                status = "leading"
            c["status"] = status
            c["sources"] = sorted(srcs)
            if best is None or ("won", "official").count(c["status"]) > ("won", "official").count(best["status"]):
                best = c
        if best is not None:
            best_field = best.get("candidates") or []
            for _, c in calls:
                field = c.get("candidates") or []
                if len(field) > len(best_field):
                    best_field = field
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


def publish(
    phase: str,
    seats: dict[str, Any],
    prn: dict[str, Any],
    out_path: str,
    total_seats: int,
    election_id: str,
    deploy: str | None = None,
    source_label: str | None = None,
    prod_base_url: str = PROD_BASE_URL,
    staging_base_url: str = STAGING_BASE_URL,
) -> dict[str, Any]:
    """Write the normalized live output JSON and optionally PUT-deploy to Worker."""
    tally = {}
    for r in seats.values():
        coal = r.get("coalition") or r.get("party")
        if coal and r.get("status") in ("won", "official"):
            tally[coal] = tally.get(coal, 0) + 1

    meta = get_election_meta(prn, default_id=election_id)
    eid = meta.get("id") or election_id
    out = {
        "phase": phase,
        "updated": now_iso(),
        "election": eid,
        "source": source_label or "manual + cross-checked feeds",
        "tally": tally,
        "seats": seats,
    }

    tmp_out = f"{out_path}.tmp"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(tmp_out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_out, out_path)

    declared = sum(1 for r in seats.values() if r.get("status") in ("won", "official"))
    print(f"[{now_iso()}] published phase={phase} declared={declared}/{total_seats} tally={tally}")

    if deploy:
        if deploy == "prod":
            try:
                assert_prod_checkout_current(prod_base_url)
            except RuntimeError as e:
                print(f"[{now_iso()}] WARN {e} — publishing live data anyway (KV is data-only)", file=sys.stderr)
        publish_remote_live(out, deploy, eid, prod_base_url, staging_base_url)
        print(f"[{now_iso()}] deployed to {deploy}")

    return out


def cycle(
    phase: str,
    prn: dict[str, Any],
    by_code: dict[str, Any],
    by_name: dict[str, str],
    cfg: dict[str, Any],
    deploy: str | None = None,
) -> dict[str, Any]:
    prefix = cfg.get("seat_prefix") or "1_"
    norm_fn = lambda raw: norm_code(raw, prefix=prefix, by_code=by_code)
    readings = []

    # 1. Manual CSV
    try:
        r_manual = source_manual(cfg["manual_path"], by_name, norm_fn)
        if r_manual:
            readings.append(("manual", r_manual))
            log_snapshot("manual-normalized", r_manual, LOG_DIR)
    except Exception as e:
        print(f"[{now_iso()}] source manual failed: {e}", file=sys.stderr)

    # 2. MyUndi API
    myundi_live = os.environ.get("MYUNDI_LIVE", "1") not in ("0", "false", "no")
    try:
        r_myundi = source_myundi(
            cfg["myundi_url"],
            myundi_live,
            MYUNDI_COAL_DEFAULT,
            prn,
            norm_fn,
            tier=cfg.get("tier", "dun"),
            log_dir=LOG_DIR,
            state_label=cfg.get("state", ""),
        )
        if r_myundi:
            readings.append(("myundi", r_myundi))
    except Exception as e:
        print(f"[{now_iso()}] source myundi failed: {e}", file=sys.stderr)

    # 3. The Star JSON
    thestar_url = cfg.get("thestar_url")
    if thestar_url:
        try:
            r_thestar = source_thestar(thestar_url, by_name, norm_fn, log_dir=LOG_DIR)
            if r_thestar:
                readings.append(("thestar", r_thestar))
        except Exception as e:
            print(f"[{now_iso()}] source thestar failed: {e}", file=sys.stderr)

    # 4. Sinar Undian
    sinar_live = os.environ.get("SINAR_LIVE", "1") not in ("0", "false", "no")
    sinar_workers = int(os.environ.get("SINAR_WORKERS", "10"))
    try:
        r_sinar = source_sinar(
            prn,
            cfg["sinar_urls_path"],
            cfg["sinar_cache_path"],
            sinar_live=sinar_live,
            sinar_workers=sinar_workers,
            log_dir=LOG_DIR,
        )
        if r_sinar:
            readings.append(("sinar", r_sinar))
    except Exception as e:
        print(f"[{now_iso()}] source sinar failed: {e}", file=sys.stderr)

    seats = merge(readings)
    seats = {c: v for c, v in seats.items() if c in by_code}
    total_seats = cfg.get("total_seats") or len(by_code)
    return publish(
        phase,
        seats,
        prn,
        out_path=cfg["out_path"],
        total_seats=total_seats,
        election_id=cfg["id"],
        deploy=deploy,
    )


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="MyPolitik election-night live poller")
    ap.add_argument("--election", default=os.environ.get("LIVE_ELECTION", "prn16-johor"),
                    help="election identifier (default: prn16-johor)")
    ap.add_argument("--config", help="path to custom election JSON configuration")
    ap.add_argument("--phase", default="live", choices=["campaign", "live", "final"])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--watch", type=int, metavar="SECONDS")
    ap.add_argument("--deploy", choices=["staging", "prod"])
    ap.add_argument("--fixture", help="publish a fixture JSON as-is (dress rehearsal)")
    ap.add_argument("--master", help="override master seatmap JSON path")
    ap.add_argument("--out", help="override output live JSON path")
    ap.add_argument("--manual", help="override manual CSV path")
    ap.add_argument("--sinar-urls", help="override Sinar URLs list path")
    ap.add_argument("--thestar-url", help="override The Star JSON endpoint URL")
    ap.add_argument("--myundi-url", help="override MyUndi live results URL")
    return ap


def main(default_election: str = "prn16-johor", argv: list[str] | None = None) -> int:
    parser = build_parser()
    if default_election != "prn16-johor":
        parser.set_defaults(election=default_election)
    args = parser.parse_args(argv)

    cfg = load_election_config(args.election, config_path=args.config)
    if args.master:
        cfg["master_path"] = args.master
    if args.out:
        cfg["out_path"] = args.out
    if args.manual:
        cfg["manual_path"] = args.manual
    if args.sinar_urls:
        cfg["sinar_urls_path"] = args.sinar_urls
    if args.thestar_url:
        cfg["thestar_url"] = args.thestar_url
    if args.myundi_url:
        cfg["myundi_url"] = args.myundi_url

    prn, by_code, by_name, prefix = load_seatmap(cfg["master_path"])
    cfg["seat_prefix"] = cfg.get("seat_prefix") or prefix
    total_seats = cfg.get("total_seats") or len(by_code)
    cfg["total_seats"] = total_seats

    if args.fixture:
        with open(args.fixture, encoding="utf-8") as f:
            fx = json.load(f)
        seats = {c: v for c, v in fx.get("seats", {}).items() if c in by_code}
        publish(
            fx.get("phase", "live"),
            seats,
            prn,
            out_path=cfg["out_path"],
            total_seats=total_seats,
            election_id=cfg["id"],
            deploy=args.deploy,
            source_label="dress rehearsal fixture",
        )
        return 0

    if args.phase == "campaign":
        publish(
            "campaign",
            {},
            prn,
            out_path=cfg["out_path"],
            total_seats=total_seats,
            election_id=cfg["id"],
            deploy=args.deploy,
        )
        return 0

    if args.watch:
        while True:
            cycle(args.phase, prn, by_code, by_name, cfg, deploy=args.deploy)
            time.sleep(args.watch)
    else:
        cycle(args.phase, prn, by_code, by_name, cfg, deploy=args.deploy)
    return 0


if __name__ == "__main__":
    sys.exit(main())
