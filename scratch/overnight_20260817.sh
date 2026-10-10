#!/bin/bash
# Overnight queue 2026-08-17 (operator-approved): capacity ladders for the three Qwen3.8-27B
# recipes, then the Qwen3.6-27B-Opus-Distill-OptiQ-4bit ifeval cap pilot (10 silent-clamp DNF
# rows re-run at cap 262144). Gated: starts at 01:00 AND only when no generate/screen is running.
# Scope decisions recorded in the session log: Ornith-1.0-35B-mlx-uniform-4bit coding re-runs
# DROPPED (provable no-op: resolved budget 81920 identical at both caps + inert seeds); the 3
# gemma coding rows DEFERRED to a supervised window (RAM-backstop risk at higher caps).
set -u
REPO="$HOME/ws/mlx_local_stack"
WD="$HOME/ws/mlx_local_stack_workdir"
LOG="$WD/status/overnight_20260817.log"
PY="$REPO/.venv-bench/bin/python"
say() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

say "orchestrator armed (pid $$). Waiting for 01:00 + idle box."

# --- gate: sleep until 01:00 ---------------------------------------------------------------
now_s=$(date +%s)
target_s=$(date -j -f "%F %H:%M" "$(date -v+1d +%F) 01:00" +%s 2>/dev/null)
# if it's already past midnight but before 01:00, target today instead
if [ "$(date +%H)" = "00" ]; then target_s=$(date -j -f "%F %H:%M" "$(date +%F) 01:00" +%s); fi
sleep_s=$(( target_s - now_s )); [ "$sleep_s" -gt 0 ] && sleep "$sleep_s"

# --- gate: wait for idle (no benchmark generation running) ---------------------------------
while pgrep -f "run.py generate" >/dev/null; do say "box busy (generate running); waiting 10m"; sleep 600; done
say "gates passed; starting."

# --- 1. fresh router -----------------------------------------------------------------------
restart_router() {
  pkill -9 -f "mlx-serve start" 2>/dev/null; pkill -9 -f "mlx_vlm.server" 2>/dev/null; sleep 3
  cd "$REPO" && set -a; . ./.env 2>/dev/null; set +a
  export MLX_VLM_CACHE_SESSION_MAX=2
  MLX_SERVE_CONFIG=main_models.yaml nohup "$REPO/.venv/bin/mlx-serve" start >"$REPO/logs/main_model.log" 2>&1 </dev/null &
  sleep 10
  curl -s localhost:8000/v1/models >/dev/null && say "router up" || say "ROUTER FAILED TO START"
}
restart_router

# --- 2. capacity ladders (quiet-box; baseline recorded per ruling 8) -----------------------
for M in Qwen3.8-27B-mlx-uniform-4bit Qwen3.8-27B-static-mixed-4bit Qwen3.8-27B-OptiQ-4.5bpw-mixed; do
  say "capacity ladder: $M — concurrent baseline follows"
  ps -axm -o rss=,comm= | sort -rn | head -5 >> "$LOG"
  ( cd "$REPO/benchmark" && "$PY" -m bench.run_capacity --model "$M" ) >> "$WD/status/overnight_capacity_${M}.log" 2>&1
  say "capacity ladder done: $M (rc=$?)"
done

# --- 3. pilot: restore winner caps to shipped 262144 ---------------------------------------
cp -p "$REPO/main_models.yaml" "$WD/archive/main_models.yaml.pre-pilot-$(date +%s)"
"$PY" - <<'PYEOF' >> "$LOG" 2>&1
import re
p = "$STACK_REPO/main_models.yaml"
src = open(p).read()
for name in ("Ornith-1.0-35B-mlx-uniform-4bit", "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"):
    blk_at = src.index(f"hf_path: caslca/{name}")
    tail = src[blk_at:blk_at+400]
    tail2 = re.sub(r"max_kv_cache_size: 131072", "max_kv_cache_size: 262144", tail, count=1)
    tail2 = re.sub(r"kv_prealloc_tokens: 131072", "kv_prealloc_tokens: 262144", tail2, count=1)
    src = src[:blk_at] + tail2 + src[blk_at+400:]
open(p, "w").write(src)
print("registry: winner caps restored to 262144 (both cap + prealloc)")
PYEOF
restart_router

# --- 4. pilot: backup + delete the 10 silent-clamp DNF rows, resume, regrade ---------------
mkdir -p "$WD/archive/pilot_backup_$(date +%F)"
if ! cp -p "$REPO/benchmark/results/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/ifeval.jsonl" \
      "$REPO/benchmark/results/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/ifeval.manifest.json" \
      "$WD/archive/pilot_backup_$(date +%F)/"; then
  say "PILOT BACKUP FAILED — aborting pilot (rows untouched)"; exit 1
fi
"$PY" - <<'PYEOF' >> "$LOG" 2>&1
import json
p = "$STACK_REPO/benchmark/results/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/ifeval.jsonl"
dnf = {"3428","1691","279","332","1580","2305","1823","3048","2596","1139"}
rows = [l for l in open(p) if str(json.loads(l).get("id")) not in dnf]
assert len(rows) == 138, f"expected 138 keepers, got {len(rows)}"
open(p, "w").writelines(rows)
print(f"deleted 10 DNF rows; {len(rows)} keepers")
PYEOF
say "pilot generate: 10 ifeval rows at cap 262144 (resume WITHOUT clean-stale)"
( cd "$REPO/benchmark" && "$PY" run.py generate --models Qwen3.6-27B-Opus-Distill-OptiQ-4bit \
    --benches ifeval --limit ifeval=148 --sampling-profile deployed --order roundrobin \
    --chunks all ) >> "$WD/status/overnight_pilot_ifeval.log" 2>&1
say "pilot generate done (rc=$?); grading"
( cd "$REPO/benchmark" && "$PY" run.py grade --models Qwen3.6-27B-Opus-Distill-OptiQ-4bit \
    --benches ifeval --limit ifeval=148 ) >> "$WD/status/overnight_pilot_ifeval.log" 2>&1
say "pilot grade done (rc=$?)."
say "OVERNIGHT COMPLETE. Artifacts: capacity logs + pilot log in status/, registry at shipped caps."
