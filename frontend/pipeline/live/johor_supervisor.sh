#!/usr/bin/env bash
# Keep the Johor live poller healthy. Safe to run from cron every 5 minutes.
# Prefer systemd (mypolitik-johor-live.service); this is a fallback + status pinger.
set -euo pipefail
ROOT="${MY_POLITIK_ROOT:-/docker/hermes-agent-nefo/data/projects/mypolitik}"
CLI="${JOHOR_LIVE_CLI:-/docker/hermes-agent-nefo/data/scripts/johor_live.py}"
PY="${PYTHON:-/usr/bin/python3}"
export MY_POLITIK_ROOT="$ROOT"

if [[ ! -f "$CLI" ]]; then
  # hermes-container path
  CLI="/opt/data/scripts/johor_live.py"
  ROOT="/opt/data/projects/mypolitik"
  export MY_POLITIK_ROOT="$ROOT"
fi

if systemctl is-active --quiet mypolitik-johor-live.service 2>/dev/null; then
  echo "systemd poller active"
  exit 0
fi

# fallback: johor_live.py managed process
if "$PY" "$CLI" status 2>/dev/null | grep -q "poller: RUNNING"; then
  echo "script poller running"
  exit 0
fi

echo "poller down — starting via johor_live.py start (prod)"
"$PY" "$CLI" start --interval 60 --deploy prod || true
"$PY" "$CLI" status || true
