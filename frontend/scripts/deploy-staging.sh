#!/usr/bin/env bash
# One-command STAGING deploy: validate → deploy → verify. Safe for any agent or
# terminal: the wrangler env is hardcoded to staging, production is unreachable
# from here. Any validation failure aborts before anything is uploaded.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== validate"
node --check public/app.js
node --test public/lib.test.mjs > /dev/null && echo "lib tests: pass"
PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/private/tmp/mypolitik-pycache}" bash scripts/validate.sh

echo "== deploy (staging only)"
# credentials: deploy.env when present (laptop), else wrangler's cached login
[ -f "$HOME/.kracked/deploy.env" ] && source "$HOME/.kracked/deploy.env"
npx wrangler deploy --env staging

echo "== verify"
curl -sf -m 20 https://staging.mypolitik.krackeddevs.com/api/health && echo
cb=$(date +%s)
for f in app.js styles.css; do
  local_hash=$(shasum "public/$f" | cut -d' ' -f1)
  remote_hash=$(curl -s -m 20 "https://staging.mypolitik.krackeddevs.com/$f?cb=$cb" | shasum | cut -d' ' -f1)
  if [ "$local_hash" = "$remote_hash" ]; then
    echo "$f: staging matches working tree"
  else
    echo "$f: MISMATCH — edge cache may lag a deploy by ~30s; re-run to re-check" >&2
    exit 1
  fi
done
echo "staging deploy verified ✓"
