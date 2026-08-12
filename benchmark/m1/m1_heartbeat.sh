#!/usr/bin/env bash
# 15-min heartbeat + self-check for the M1 run. One stdout line per tick (each becomes a
# notification). Emits deltas so a stall is visible rather than inferred, and projects an ETA so
# "is this going in the direction we care about" is answerable from the line alone.
export PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH
R=${REPO:?set REPO}
BM=${AIDER_REPO:?set AIDER_REPO}/benchmark/tmp.benchmarks
TAG=${TAG:-m1e}      # must match the driver, else progress counts VOID cases
TARGET=220          # 110 matched cases x 2 models
# Memory and 500s are tracked because the FIRST M1 attempt died on a Metal GPU OOM: the shipped
# APC_NUM_BLOCKS=16384 pool cost ~33GB, leaving 4.1GB free, and aider then retried the failures
# against its 24h RETRY_TIMEOUT while cases were being scored as model failures. Both are now
# first-class alarms rather than something to notice afterwards in a log.
FIRST_500=0
prev_cases=-1; prev_calls=-1; quiet=0; start=$(date +%s)
while true; do
  cases=$(find "$BM" -path "*${TAG}-*" -name ".aider.results.json" 2>/dev/null | wc -l | tr -d ' ')
  # SINCE ("YYYY-MM-DD HH:MM:SS") is REQUIRED for a trustworthy inflight figure: killing a previous
  # driver leaves an arrival with no completion, so an unfiltered count carries a permanent +1 offset
  # and `inflight>0` would suppress the STALL check forever — a silently disabled alarm.
  if [ -n "${SINCE:-}" ]; then
    calls=$(awk -v s="$SINCE" 'substr($0,1,19) >= s' "$R/logs/main_model.log" 2>/dev/null | grep -c "router — POST /v1/chat/completions")
    donecalls=$(awk -v s="$SINCE" 'substr($0,1,19) >= s' "$R/logs/main_model.log" 2>/dev/null | grep -c "/v1/chat/completions 200")
    errs=$(awk -v s="$SINCE" 'substr($0,1,19) >= s' "$R/logs/main_model.log" 2>/dev/null | grep -c "chat/completions 500")
  else
    calls=$(grep -c "router — POST /v1/chat/completions" "$R/logs/main_model.log" 2>/dev/null || echo 0)
    donecalls=$(grep -c "/v1/chat/completions 200" "$R/logs/main_model.log" 2>/dev/null || echo 0)
    errs=$(grep -c "chat/completions 500" "$R/logs/main_model.log" 2>/dev/null || echo 0)
    fi
  inflight=$(( calls - donecalls ))
  last=$(tail -1 /tmp/m1_run.log 2>/dev/null | cut -c1-90)
  driver=$(pgrep -f m1_driver.sh >/dev/null && echo up || echo DOWN)
  conts=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -c '^aider-' || echo 0)
  router=$(curl -s -o /dev/null -m 8 -w '%{http_code}' localhost:8000/v1/models 2>/dev/null)
  freegb=$(python3 -c "import psutil;print(f'{psutil.virtual_memory().available/1e9:.1f}')" 2>/dev/null \
           || $R/.venv-bench/bin/python -c "import psutil;print(f'{psutil.virtual_memory().available/1e9:.1f}')" 2>/dev/null)
  el=$(( ($(date +%s) - start) / 60 ))
  if [ "$prev_cases" -lt 0 ]; then dc=0; dk=0; else dc=$((cases-prev_cases)); dk=$((calls-prev_calls)); fi
  # progress rate + ETA from cases completed since this monitor started
  rate="-"; eta="-"
  if [ "$el" -gt 0 ] && [ "$cases" -gt 0 ]; then
    rate=$(awk -v c="$cases" -v m="$el" 'BEGIN{printf "%.1f", m/c}')
    eta=$(awk -v c="$cases" -v m="$el" -v t="$TARGET" 'BEGIN{printf "%.1f", (t-c)*(m/c)/60}')
  fi
  flag="OK"
  # A single thinking generation can run >10 min, so "no new cases and no new calls" is NOT a
  # stall while a request is still in flight (arrivals > completions). Without this the very first
  # tick of every batch would cry wolf.
  if [ "$prev_cases" -ge 0 ] && [ "$dc" -eq 0 ] && [ "$dk" -eq 0 ] && [ "$inflight" -le 0 ]; then
    quiet=$((quiet+1)); flag="STALL?x$quiet"
  else quiet=0; fi
  [ "$driver" = "DOWN" ] && flag="DRIVER-DOWN"
  # An OOM shows up as 500s long before the run visibly stops, so treat any as an alarm.
  [ "${errs:-0}" -gt "$FIRST_500" ] && flag="HTTP500x$errs"
  awk -v f="${freegb:-99}" 'BEGIN{exit !(f+0 < 8)}' && flag="$flag LOWMEM=${freegb}GB"
  [ "$router" != "200" ] && flag="$flag ROUTER=$router"
  echo "HB $flag cases=$cases/$TARGET (+$dc) calls=$calls (+$dk) inflight=$inflight free=${freegb}GB 500s=${errs:-0} ${rate}min/case eta=${eta}h driver=$driver cont=$conts | $last"
  prev_cases=$cases; prev_calls=$calls
  [ "$driver" = "DOWN" ] && { echo "HB driver exited — M1 finished or died; stopping heartbeat"; exit 0; }
  sleep 900
done
