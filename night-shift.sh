#!/usr/bin/env bash
# night-shift.sh — run Claude + Codex against NIGHT_QUEUE.md overnight, in a paced relay.
#
# One round = Claude does a task -> commits -> appends to AGENT_LOG.md,
#             then Codex verifies / takes the next -> commits -> appends.
# The loop repeats until: the time budget runs out, the queue is empty, MAX_ROUNDS,
# or a STOP flag is set from the dashboard.
#
# It also emits live telemetry for night-dash.js:
#   ~/night-logs/<date>/status.json    current state (overwritten each phase)
#   ~/night-logs/<date>/events.ndjson  append-only event stream (rounds, caps, stops)
#   ~/night-logs/<date>/night-*.log    full transcript
#
# SAFE BY DESIGN: works only on a night/<date> branch (never master), never pushes,
# never deploys, logs OUTSIDE the repo, leaves pre-existing work alone.
#
# Usage:
#   bash night-shift.sh                       # laptop repo, 8h, ~8min pacing
#   HOURS=8 PACE=480 bash night-shift.sh /opt/master-lab-v2-app
#   ROUNDS=2 bash night-shift.sh              # short supervised test (2 rounds, then stop)
#
set -uo pipefail

# ---- config (override via env) --------------------------------------------
REPO="${1:-/Users/danialalias/Desktop/Experiments/master-lab-v2}"
HOURS="${HOURS:-8}"            # run for this many hours
PACE="${PACE:-480}"           # seconds to sleep between rounds (paces the Pro usage cap)
MAX_ROUNDS="${MAX_ROUNDS:-40}"   # hard safety cap on total rounds
ROUNDS="${ROUNDS:-0}"         # if >0, stop after this many rounds (for a quick test)
CODEX_FLAGS="${CODEX_FLAGS:--s workspace-write}"   # codex exec sandbox (0.141+)
BACKOFF="${BACKOFF:-1800}"    # seconds to wait when a usage/rate limit is hit
# ---------------------------------------------------------------------------

cd "$REPO" || { echo "no repo at $REPO"; exit 1; }

DATE="$(date +%Y%m%d)"
BRANCH="night/$DATE"
LOGDIR="$HOME/night-logs/$DATE"
mkdir -p "$LOGDIR"
RUNLOG="$LOGDIR/night-$(date +%H%M%S).log"
STATUS="$LOGDIR/status.json"
EVENTS="$LOGDIR/events.ndjson"
STOPFLAG="$LOGDIR/STOP"
LOCK="$HOME/night-logs/.lock"
rm -f "$STOPFLAG"

# single-instance lock
if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
  echo "night-shift already running (pid $(cat "$LOCK")). exiting."; exit 1
fi
echo $$ > "$LOCK"

say() { echo "[night] $*" | tee -a "$RUNLOG"; }
jesc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/	/ /g'; }

# telemetry state
START_EPOCH="$(date +%s)"
STOP=$(( START_EPOCH + HOURS*3600 ))
RUNNING=true
round=0
rounds_done=0
cap_events=0
phase="starting"; cur_agent=""; cur_note="warming up"
HAVE_CODEX=0; command -v codex >/dev/null 2>&1 && HAVE_CODEX=1

write_status() {
  local now; now="$(date +%s)"
  printf '{"running":%s,"pid":%s,"repo":"%s","branch":"%s","base_sha":"%s","started_epoch":%s,"last_update_epoch":%s,"stop_epoch":%s,"hours":%s,"pace":%s,"round":%s,"rounds_done":%s,"phase":"%s","agent":"%s","note":"%s","cap_events":%s,"have_codex":%s}\n' \
    "$RUNNING" "$$" "$(jesc "$REPO")" "$BRANCH" "${BASE_SHA:-}" "$START_EPOCH" "$now" "$STOP" "$HOURS" "$PACE" \
    "$round" "$rounds_done" "$phase" "$cur_agent" "$(jesc "$cur_note")" "$cap_events" "$HAVE_CODEX" > "$STATUS"
}
event() { printf '{"t":%s,"round":%s,"kind":"%s","agent":"%s","msg":"%s"}\n' \
  "$(date +%s)" "$round" "$1" "$2" "$(jesc "$3")" >> "$EVENTS"; }
set_phase() { phase="$1"; cur_agent="$2"; cur_note="$3"; write_status; }
paced_sleep() { local e; e=$(( $(date +%s) + $1 )); while [ "$(date +%s)" -lt "$e" ]; do
  [ -e "$STOPFLAG" ] && return 0; sleep 3; done; }

# branch off whatever we're on (never the deploy branch), carrying any WIP
CUR="$(git rev-parse --abbrev-ref HEAD)"
git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
BASE_SHA="$(git rev-parse HEAD 2>/dev/null || echo '')"
# remember files already dirty at startup so autosave never touches pre-existing WIP
PRE_FILE="$LOGDIR/.preexisting"
git status --porcelain | cut -c4- | sort > "$PRE_FILE"

cleanup() { RUNNING=false; phase="done"; cur_agent=""; cur_note="run ended"; write_status 2>/dev/null
  rm -f "$LOCK"; echo "[night] stopped $(date '+%F %T')" | tee -a "$RUNLOG"; }
trap cleanup EXIT INT TERM

write_status
event start "" "night-shift started (budget ${HOURS}h, pace ${PACE}s)"
say "repo=$REPO  branch=$BRANCH (from $CUR)  base=$BASE_SHA  log=$RUNLOG"
say "started $(date '+%F %T')  budget=${HOURS}h  pace=${PACE}s  cap=${MAX_ROUNDS}"
[ "$HAVE_CODEX" = 0 ] && say "codex not found — running Claude-only loop"

GUARD="GUARDRAILS: stay on branch $BRANCH. Do NOT git push. Do NOT deploy. Do NOT touch any
file that was already modified before you started (check 'git status' — pre-existing changes
are not yours), and respect any UNTOUCHABLES listed in AGENTS.md. Keep the app
zero-dependency / no new build step. Do exactly ONE task this round, then stop."

CLAUDE_PROMPT="You are VPS-Claude on the autonomous NIGHT SHIFT in $REPO.
Read AGENTS.md, the tail of AGENT_LOG.md, and NIGHT_QUEUE.md.
Take the TOP unchecked task tagged (claude) — or any (claude) task if the top is blocked.
Do it. Commit with a clear message. Tick its box in NIGHT_QUEUE.md. Append a short handoff
entry to AGENT_LOG.md (date/time, agent, files, commit SHA, verification, next step).
If there is no doable (claude) task left, reply with EXACTLY: QUEUE EMPTY
$GUARD"

CODEX_PROMPT="You are Codex on the autonomous NIGHT SHIFT in $REPO.
Read AGENTS.md, the tail of AGENT_LOG.md, and NIGHT_QUEUE.md.
First verify Claude's most recent commit (node --check changed JS, git diff review, smoke if
cheap). Fix any breakage. Otherwise take the TOP unchecked task tagged (codex). Commit, tick
its box in NIGHT_QUEUE.md, append a handoff entry to AGENT_LOG.md.
If there is nothing to verify and no doable (codex) task, reply with EXACTLY: QUEUE EMPTY
$GUARD"

run_claude() { claude -p "$CLAUDE_PROMPT" --dangerously-skip-permissions 2>&1; }
run_codex()  { codex exec $CODEX_FLAGS "$CODEX_PROMPT" 2>&1; }
capped() { echo "$1" | grep -qiE "rate.?limit|usage limit|quota|429|overloaded"; }
trouble() { echo "$1" | grep -qiE "FAIL\b|error:|syntax error|traceback"; }

# the loop commits anything an agent left uncommitted (e.g. Codex's sandbox blocks .git),
# staging ONLY files that were not already dirty at startup — pre-existing WIP is never swept in.
commit_leftovers() {
  local agent="$1" new n
  new="$(git status --porcelain | cut -c4- | sort | comm -23 - "$PRE_FILE" | sed '/^$/d')"
  [ -z "$new" ] && return 0
  printf '%s\n' "$new" | tr '\n' '\0' | xargs -0 git add -- 2>/dev/null
  git diff --cached --quiet && return 0
  n="$(printf '%s\n' "$new" | wc -l | tr -d ' ')"
  git commit -q -m "$agent round $round — autosave ($n file(s) the agent left uncommitted)"
  say "autosaved $agent leftovers -> $(git rev-parse --short HEAD) ($n file)"
  event autosave "$agent" "committed $n file(s) $agent left uncommitted"
}

empty_streak=0

while [ "$(date +%s)" -lt "$STOP" ] && [ "$round" -lt "$MAX_ROUNDS" ]; do
  if [ -e "$STOPFLAG" ]; then say "STOP flag set — exiting"; event stop "" "stopped from dashboard"; break; fi
  round=$((round+1))
  say "===== round $round  $(date '+%F %T') ====="
  event round "" "round $round begins"

  set_phase claude claude "round $round — Claude working a task"
  out="$(run_claude)"; echo "$out" >> "$RUNLOG"
  if capped "$out"; then
    cap_events=$((cap_events+1)); event cap claude "usage/rate limit — backing off ${BACKOFF}s"
    set_phase backoff claude "Claude capped — backing off"; say "Claude capped — backoff ${BACKOFF}s"
    paced_sleep "$BACKOFF"; continue
  fi
  commit_leftovers claude
  c_empty=0; echo "$out" | grep -q "QUEUE EMPTY" && c_empty=1 && { say "Claude: nothing to do"; event idle claude "no (claude) task"; }

  x_empty=1
  if [ "$HAVE_CODEX" = 1 ]; then
    set_phase codex codex "round $round — Codex verifying + task"
    out="$(run_codex)"; echo "$out" >> "$RUNLOG"
    if capped "$out"; then
      cap_events=$((cap_events+1)); event cap codex "usage/rate limit — backing off ${BACKOFF}s"
      set_phase backoff codex "Codex capped — backing off"; say "Codex capped — backoff ${BACKOFF}s"
      paced_sleep "$BACKOFF"; continue
    fi
    commit_leftovers codex
    trouble "$out" && event warn codex "failed check in transcript — review"
    x_empty=0; echo "$out" | grep -q "QUEUE EMPTY" && x_empty=1 && { say "Codex: nothing to do"; event idle codex "no (codex) task"; }
  fi

  if [ "$c_empty" = 1 ] && [ "$x_empty" = 1 ]; then
    empty_streak=$((empty_streak+1)); event empty "" "queue drained ($empty_streak)"
    say "queue looks drained ($empty_streak) — sleeping 20m in case you add tasks"
    set_phase waiting "" "queue empty — waiting for new tasks"
    [ "$empty_streak" -ge 3 ] && { say "queue empty 3x — wrapping up"; event done "" "queue empty, wrapping up"; break; }
    paced_sleep 1200; continue
  fi
  empty_streak=0
  rounds_done=$((rounds_done+1))

  if [ "$ROUNDS" -gt 0 ] && [ "$round" -ge "$ROUNDS" ]; then
    say "ROUNDS=$ROUNDS reached — stopping (test mode)"; event done "" "test rounds reached"; break
  fi

  set_phase pacing "" "pacing ${PACE}s before next round"; event pace "" "pacing ${PACE}s"
  say "round $round done — pacing ${PACE}s"
  paced_sleep "$PACE"
done

say "===== MORNING ====="
say "review:  git -C $REPO log --oneline --stat $BRANCH"
say "log:     less $RUNLOG"
say "dash:    REPO=$REPO node night-dash.js   ->  http://localhost:4199"
say "to ship: review the diff, then merge to master and 'git push vps master'"
