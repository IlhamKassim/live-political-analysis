#!/usr/bin/env python3
"""Rick-facing CLI for PRN Johor live-results night ops.

General Rick runs this via Discord (!johor …). It manages manual.csv, the poller
watch loop, and optional Cloudflare deploys of public/data/live-johor.json.

Env:
  MY_POLITIK_ROOT  — repo root (default: /opt/data/projects/mypolitik)
  JOHOR_DEPLOY     — prod | staging | off  (default: prod when starting watch)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("MY_POLITIK_ROOT", "/opt/data/projects/mypolitik")).resolve()
LIVE_DIR = ROOT / "pipeline" / "live"
POLLER = LIVE_DIR / "johor_poller.py"
MANUAL = LIVE_DIR / "manual.csv"
LIVE_JSON = ROOT / "public" / "data" / "live-johor.json"
PID_FILE = LIVE_DIR / "log" / "poller.pid"
LOG_FILE = LIVE_DIR / "log" / "poller.out"
ENV_LIVE = ROOT / ".env.live"
MYT = dt.timezone(dt.timedelta(hours=8))

FIELDS = ["code", "status", "coalition", "party", "name", "majority"]


def now_myt() -> str:
    return dt.datetime.now(MYT).strftime("%Y-%m-%d %H:%M MYT")


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}")
    sys.exit(code)


def ensure_layout() -> None:
    if not POLLER.is_file():
        die(f"poller not found at {POLLER} — is MY_POLITIK_ROOT set?")
    LIVE_DIR.joinpath("log").mkdir(parents=True, exist_ok=True)
    if not MANUAL.is_file():
        MANUAL.write_text("code,status,coalition,party,name,majority\n", encoding="utf-8")


def load_env_live() -> dict:
    env = os.environ.copy()
    if ENV_LIVE.is_file():
        for line in ENV_LIVE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def norm_code(raw: str) -> str | None:
    m = re.search(r"N\.?\s?0?(\d{1,2})", str(raw or ""), re.I)
    return f"1_N.{int(m.group(1)):02d}" if m else None


def read_manual() -> list[dict]:
    ensure_layout()
    if not MANUAL.is_file():
        return []
    with MANUAL.open(newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f) if any((r.get(k) or "").strip() for k in FIELDS)]


def write_manual(rows: list[dict]) -> None:
    ensure_layout()
    with MANUAL.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") or "" for k in FIELDS})


def read_live() -> dict:
    if not LIVE_JSON.is_file():
        return {}
    try:
        return json.loads(LIVE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def poller_pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def cmd_status(_: argparse.Namespace) -> None:
    ensure_layout()
    live = read_live()
    pid = poller_pid()
    seats = live.get("seats") or {}
    declared = sum(1 for s in seats.values() if (s.get("status") or "") in ("won", "official"))
    leading = sum(1 for s in seats.values() if (s.get("status") or "") == "leading")
    tally = live.get("tally") or {}
    manual = read_manual()
    print(f"johor live · {now_myt()}")
    print(f"root: {ROOT}")
    print(f"phase: {live.get('phase') or '—'}")
    print(f"updated: {live.get('updated') or '—'}")
    print(f"source: {live.get('source') or '—'}")
    print(f"declared: {declared}/56 · leading: {leading} · tally: {tally or '{}'}")
    print(f"manual rows: {len(manual)}")
    if pid:
        print(f"poller: RUNNING pid={pid}  log={LOG_FILE}")
    else:
        print("poller: stopped")
    if manual:
        print("manual:")
        for r in manual[:12]:
            print(f"  {r.get('code')}  {r.get('status')}  {r.get('coalition')}/{r.get('party')}  {r.get('name')}  maj={r.get('majority') or '—'}")
        if len(manual) > 12:
            print(f"  … +{len(manual) - 12} more")


def cmd_list(_: argparse.Namespace) -> None:
    live = read_live()
    seats = live.get("seats") or {}
    if not seats:
        print("no seats in live-johor.json yet")
        return
    for code in sorted(seats):
        s = seats[code]
        print(f"{code}  {s.get('status')}  {s.get('coalition') or '—'}  {s.get('name') or '—'}  maj={s.get('majority') or '—'}  src={','.join(s.get('sources') or [])}")


def run_poller(args: list[str], deploy: str | None) -> int:
    ensure_layout()
    env = load_env_live()
    cmd = [sys.executable, str(POLLER), *args]
    if deploy and deploy != "off":
        cmd += ["--deploy", deploy]
    print(f"$ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def cmd_once(ns: argparse.Namespace) -> None:
    code = run_poller(["--once", "--phase", ns.phase], ns.deploy)
    if code != 0:
        die(f"poller exited {code}", code)
    cmd_status(ns)


def cmd_campaign(ns: argparse.Namespace) -> None:
    code = run_poller(["--once", "--phase", "campaign"], ns.deploy if ns.deploy != "off" else None)
    if code != 0:
        die(f"poller exited {code}", code)
    print("reset to campaign (empty tally)")
    cmd_status(ns)


def cmd_start(ns: argparse.Namespace) -> None:
    ensure_layout()
    existing = poller_pid()
    if existing:
        print(f"already running pid={existing}")
        return
    env = load_env_live()
    deploy = ns.deploy
    cmd = [sys.executable, str(POLLER), "--watch", str(ns.interval), "--phase", "live"]
    if deploy and deploy != "off":
        cmd += ["--deploy", deploy]
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    # detach
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(f"\n---- start {now_myt()} ----\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"started poller pid={proc.pid} interval={ns.interval}s deploy={deploy}")
    print(f"log: {LOG_FILE}")
    time.sleep(1.5)
    if poller_pid() != proc.pid:
        print("warning: process may have exited — check log")
    cmd_status(ns)


def cmd_stop(_: argparse.Namespace) -> None:
    pid = poller_pid()
    if not pid:
        print("poller not running")
        if PID_FILE.is_file():
            PID_FILE.unlink()
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"kill failed: {e}")
    # wait briefly
    for _ in range(20):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except OSError:
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if PID_FILE.is_file():
        PID_FILE.unlink()
    print(f"stopped pid={pid}")


def cmd_call(ns: argparse.Namespace) -> None:
    code = norm_code(ns.code) or ns.code.strip()
    if not re.match(r"1_N\.\d{2}$", code or ""):
        # still allow raw N.xx via norm
        code = norm_code(ns.code)
    if not code:
        die(f"bad seat code: {ns.code}")
    status = (ns.status or "won").lower()
    if status not in ("leading", "won", "official"):
        die("status must be leading|won|official")
    coal = (ns.coalition or "").upper()
    party = (ns.party or "").upper()
    name = (ns.name or "").strip()
    maj = (ns.majority or "").strip()
    rows = read_manual()
    # upsert by normalised code
    out = []
    found = False
    for r in rows:
        rc = norm_code(r.get("code") or "") or r.get("code")
        if rc == code:
            out.append({
                "code": code, "status": status, "coalition": coal,
                "party": party, "name": name, "majority": maj,
            })
            found = True
        else:
            out.append(r)
    if not found:
        out.append({
            "code": code, "status": status, "coalition": coal,
            "party": party, "name": name, "majority": maj,
        })
    write_manual(out)
    print(f"manual: {code} → {status} {coal}/{party} {name} maj={maj or '—'}")
    # publish immediately
    deploy = ns.deploy
    rc = run_poller(["--once", "--phase", "live"], deploy)
    if rc != 0:
        die(f"saved manual but poller failed ({rc})", rc)
    cmd_status(ns)


def cmd_uncall(ns: argparse.Namespace) -> None:
    code = norm_code(ns.code) or ns.code.strip()
    rows = read_manual()
    kept = []
    removed = 0
    for r in rows:
        rc = norm_code(r.get("code") or "") or r.get("code")
        if rc == code:
            removed += 1
            continue
        kept.append(r)
    if not removed:
        die(f"no manual row for {ns.code}")
    write_manual(kept)
    print(f"removed {code} from manual ({removed} row(s))")
    rc = run_poller(["--once", "--phase", "live"], ns.deploy)
    if rc != 0:
        die(f"manual updated but poller failed ({rc})", rc)
    cmd_status(ns)


def cmd_log(ns: argparse.Namespace) -> None:
    if not LOG_FILE.is_file():
        print("no poller log yet")
        return
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    n = max(1, int(ns.lines or 40))
    print("\n".join(lines[-n:]))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="johor_live", description="PRN Johor live ops for Rick")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="phase, tally, poller state")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("list", help="list seats in live-johor.json")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("once", help="one poll cycle")
    sp.add_argument("--phase", default="live", choices=["live", "final", "campaign"])
    sp.add_argument("--deploy", default="prod", choices=["prod", "staging", "off"])
    # Discord-friendly: !johor once staging
    sp.add_argument("deploy_pos", nargs="?", choices=["prod", "staging", "off"])
    sp.set_defaults(func=cmd_once)

    sp = sub.add_parser("start", help="start background poller watch loop")
    sp.add_argument("--interval", type=int, default=90, help="seconds between cycles")
    sp.add_argument("--deploy", default="prod", choices=["prod", "staging", "off"])
    sp.add_argument("deploy_pos", nargs="?", choices=["prod", "staging", "off"])
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("stop", help="stop background poller")
    sp.set_defaults(func=cmd_stop)

    sp = sub.add_parser("campaign", help="reset live file to empty campaign phase")
    sp.add_argument("--deploy", default="prod", choices=["prod", "staging", "off"])
    sp.add_argument("deploy_pos", nargs="?", choices=["prod", "staging", "off"])
    sp.set_defaults(func=cmd_campaign)

    sp = sub.add_parser("call", help="record a seat result into manual.csv and publish")
    sp.add_argument("code", help="N.01 or 1_N.01")
    sp.add_argument("status", help="leading|won|official")
    sp.add_argument("coalition", help="BN|PH|PN|…")
    sp.add_argument("party", help="UMNO|DAP|…")
    sp.add_argument("name", help="winner name (quote if spaces)")
    sp.add_argument("majority", nargs="?", default="", help="majority votes (optional)")
    sp.add_argument("--deploy", default="prod", choices=["prod", "staging", "off"])
    sp.set_defaults(func=cmd_call)

    sp = sub.add_parser("uncall", help="remove a seat from manual.csv and republish")
    sp.add_argument("code")
    sp.add_argument("--deploy", default="prod", choices=["prod", "staging", "off"])
    sp.set_defaults(func=cmd_uncall)

    sp = sub.add_parser("log", help="tail poller log")
    sp.add_argument("-n", "--lines", type=int, default=40)
    sp.set_defaults(func=cmd_log)

    return p


def apply_deploy_pos(ns: argparse.Namespace) -> None:
    """Allow `start staging` as well as `start --deploy staging`."""
    pos = getattr(ns, "deploy_pos", None)
    if pos:
        ns.deploy = pos


def main() -> None:
    parser = build_parser()
    ns = parser.parse_args()
    apply_deploy_pos(ns)
    ns.func(ns)


if __name__ == "__main__":
    main()
