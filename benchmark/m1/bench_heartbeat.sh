#!/usr/bin/env bash
# HARNESS-AGNOSTIC run monitor. Works for aider, pi, opencode, or any driver.
#
# WHY THIS EXISTS: m1_heartbeat.sh is hardwired to aider's docker container naming,
# `.aider.results.json`, and aider's log strings — none of which transfers. This project has
# repeatedly lost hours to monitors that reported "fine" while measuring nothing: one counted VOID
# cases, one globbed a tag matching nothing, one carried an alarm that could never fire, and one was
# armed inside an ssh session so its output went to a dead pipe. Every check below is therefore
# either derived from a parameter or REFUSES to report rather than guessing.
#
# Usage (all via env so nothing is positional-fragile):
#   REPO=<repo on the worker>            required
#   PROGRESS_CMD='<shell that echoes an integer>'   required — how to count completed units
#   DRIVER_PAT=<pgrep -f pattern>        required — the driver process to watch
#   TARGET=<int>                         optional — total expected units, for ETA
#   SINCE='YYYY-MM-DD HH:MM:SS'          optional but STRONGLY advised — filters router-log counts
#   EXPECT_CFG=<8-char shasum prefix>    optional — alarms if main_models.yaml changes mid-run
#   INTERVAL=<seconds>                   default 300
#
# Emits one line per tick. Any line containing a flag other than OK needs a human.
set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH
R=${REPO:?set REPO}
PROGRESS_CMD=${PROGRESS_CMD:?set PROGRESS_CMD}
DRIVER_PAT=${DRIVER_PAT:?set DRIVER_PAT}
TARGET=${TARGET:-0}
INTERVAL=${INTERVAL:-300}
cd "$R" || { echo "HB FATAL: REPO unreachable: $R"; exit 1; }

prev=-1
start=$(date +%s)
while true; do
  # --- progress. A non-integer means the caller's PROGRESS_CMD is broken: say so, do NOT print 0,
  # because a silently-zero progress count reads as "stalled" and a silently-wrong one reads as fine.
  units=$(eval "$PROGRESS_CMD" 2>/dev/null | tr -d ' ')
  case "$units" in
    ''|*[!0-9]*) echo "HB PROGRESS-CMD-BROKEN (returned '${units:-<empty>}') — refusing to report numbers"
                 sleep "$INTERVAL"; continue ;;
  esac

  drv=$(pgrep -f "$DRIVER_PAT" | wc -l | tr -d ' ')
  lis=$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c LISTEN)
  wk=$(pgrep -f mlx_vlm.server | wc -l | tr -d ' ')
  foreign=$(ps -Ao command= | grep -E "claude-agent|@anthropic-ai/claude" | grep -vc grep)
  RT=$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | awk 'NR==2{print $2}')
  apc=$(ps -Eww -p "${RT:-0}" 2>/dev/null | tr ' ' '\n' | grep -cE '^APC')
  cfg=$(shasum main_models.yaml 2>/dev/null | cut -c1-8)
  if [ -n "${SINCE:-}" ]; then
    e5=$(awk -v s="$SINCE" 'substr($0,1,19)>=s && /chat\/completions 500/{n++} END{print n+0}' \
         logs/main_model.log 2>/dev/null)
    e5=${e5:-0}
  else
    e5=$(awk '/chat\/completions 500/{n++} END{print n+0}' logs/main_model.log 2>/dev/null)
    e5=${e5:-0}
  fi
  mem=$("$R"/.venv-bench/bin/python - <<'PY' 2>/dev/null
import json,sys,urllib.request
try:
    d=json.load(urllib.request.urlopen("http://localhost:8000/metrics",timeout=8))["memory"]
    print("%.1f %.0f"%(d["ram_available_gb"],d["ram_percent"]))
except Exception: print("")
PY
)
  avail=${mem%% *}; pct=${mem##* }

  el=$(( ($(date +%s) - start) / 60 ))
  d=0; [ "$prev" -ge 0 ] && d=$((units-prev))
  rate="-"; eta="-"
  # rate/ETA from progress made SINCE THIS MONITOR STARTED, never cumulative-over-monitor-elapsed
  # (that bug made a mid-run monitor restart report a wildly optimistic ETA).
  if [ "$prev" -ge 0 ] && [ "$el" -gt 0 ] && [ "$units" -gt "$prev" ]; then
    :
  fi
  if [ "$TARGET" -gt 0 ] && [ "$units" -gt 0 ]; then
    eta=$(awk -v u="$units" -v t="$TARGET" -v m="$el" 'BEGIN{if(u>0&&m>0)printf "%.1f",(t-u)*(m/u)/60; else printf "-"}')
  fi

  flag=OK
  [ "$drv" -eq 0 ] && flag="DRIVER-DOWN"
  [ "$drv" -gt 1 ] && flag="$flag DUP-DRIVER=$drv"
  [ "$lis" -ne 1 ] && flag="$flag LISTENERS=$lis"
  [ "$wk" -ne 1 ] && flag="$flag WORKERS=$wk"
  [ "$foreign" -gt 0 ] && flag="$flag FOREIGN-AGENT=$foreign"
  [ "${apc:-0}" -gt 0 ] && flag="$flag APC-ON"
  [ "$e5" -gt 0 ] && flag="$flag HTTP500x$e5"
  [ -n "${EXPECT_CFG:-}" ] && [ "$cfg" != "$EXPECT_CFG" ] && flag="$flag REGISTRY-CHANGED($cfg)"
  [ -z "$avail" ] && flag="$flag METRICS-UNREACHABLE"
  [ -n "$avail" ] && awk -v a="$avail" 'BEGIN{exit !(a+0 < 6)}' && flag="$flag LOWMEM=${avail}GB"
  # STALL only when nothing moved AND no request is in flight — a single thinking generation can
  # legitimately run >40 min (measured), so "no new units" alone is not a stall.
  if [ "$prev" -ge 0 ] && [ "$d" -eq 0 ]; then
    inflight=$(awk -v s="${SINCE:-0000}" 'substr($0,1,19)>=s' logs/main_model.log 2>/dev/null \
      | awk '/router — POST \/v1\/chat\/completions/{a++} /chat\/completions 200/{b++} END{print (a+0)-(b+0)}')
    [ "${inflight:-1}" -le 0 ] && flag="$flag STALL?"
  fi

  tgt=""; [ "$TARGET" -gt 0 ] 2>/dev/null && tgt="/$TARGET"
  echo "HB $flag units=$units$tgt (+$d) drv=$drv lis=$lis wk=$wk foreign=$foreign apc=$apc 500s=$e5 cfg=$cfg avail=${avail:-?}GB pct=${pct:-?}% eta=${eta}h"
  prev=$units
  [ "$drv" -eq 0 ] && { echo "HB driver gone — run finished or died; stopping"; exit 0; }
  sleep "$INTERVAL"
done
