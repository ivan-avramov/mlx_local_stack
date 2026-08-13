#!/usr/bin/env bash
# P2 Tier-0 sampling grid, REV B (2026-08-13) — supersedes /tmp/tier0_grid.sh.
#
# Rev A completed its Ornith arm (converged 1.0 / budget_hit 0.0 in all 11 cells) but its distill
# arm produced ZERO cells, and the audit of its Ornith data found two defects. Three changes, each
# forced by a measurement:
#
# 1. TASK: vartrack, not aggregation@8K.  Rev A's screen used the CWE word-tally, which is
#    *designed* to blow the thinking budget. Measured on the distill it emits ~39,479 tokens at
#    ~10 tok/s = 63.4 min for ONE sample -- so cell 1 hit the 3600s driver timeout, the worker kept
#    generating after the client gave up, and every later cell's 120s calibrate_cpt queued behind it
#    and died. vartrack (multi-hop variable tracking, no enumeration) probes the same rambling
#    behaviour: measured 550/558 tokens in ~31s, converged, accuracy 1.0. A full cell is 2m04s
#    instead of >2h. This is a SCOPE reduction (which task, how many samples), never a generation
#    param -- max_tokens and thinking_budget stay at their deployed values, since capping either
#    would MANUFACTURE the non-convergence the screen is trying to measure.
#
# 2. TRUNCATION HELD AT DEPLOYED (top_p 0.95 / top_k 20).  Rev A set top_k=0 / top_p=1.0 to make
#    min_p the single scale-free knob. Sound in principle, but at min_p 0.0 that leaves NOTHING
#    clipping the tail, and the untruncated path is NONDETERMINISTIC under suffix decoding: three
#    byte-identical unseeded requests returned three different outputs spanning 1.6x in length
#    (bench/probe_determinism.py, 2026-08-13). So 4 of rev A's 11 cells were measured on a
#    nondeterministic path at --samples 2. Holding top_p/top_k at the deployed values makes every
#    cell reproducible AND measures the path we actually serve.
#
# 3. min_p SPACING WIDENED to 0.0 / 0.05 / 0.15.  Rev A's 0.0/0.02/0.05 was inert: cells grouped
#    into only 8 distinct outputs across 11, with t*_mp0.02 == t*_mp0.05, and the deployed 3-knob
#    cell byte-equal to both. The three truncation knobs are mutually redundant in that range.
#
# The collapse test is also RE-SPECIFIED. Rev A's "collapse_minp_only" cell was min_p 0.0 with
# top_p 1.0 / top_k 0 -- i.e. nothing active, an exact duplicate of t0.4_mp0.0 rather than a
# min_p-only comparator. Here it is min_p 0.05 with top_p/top_k off, which is genuinely min_p-only
# and still truncated (hence deterministic).
#
# Both models, distill FIRST (it is the one that is already resident), one resident model at a time.
set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH
R=$HOME/ws/mlx_local_stack
cd "$R/benchmark" || exit 1

LOG=/tmp/tier0b_run.log
# DURABLE archive root -- rev A wrote to /tmp, which is volatile and nearly cost us the Ornith arm.
ARCH=$HOME/mlx_bench_snapshots/tier0b-2026-08-13
mkdir -p "$ARCH"
PY="$R/.venv-bench/bin/python"
CHECK="$R/benchmark/m1/tier0b_check.py"
say(){ echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

# cell <model> <temp> <min_p> <top_p> <top_k> <label>
cell() {
  local m="$1" t="$2" mp="$3" tp="$4" tk="$5" lab="$6"
  local out="$ARCH/${m}__${lab}.json"
  local live="results/$m/convergence_vartrack.json"
  [ -f "$out" ] && { say "SKIP $m $lab (already archived)"; return 0; }
  # Delete the live file FIRST: a STALE file from an earlier cell reads as success on copy, which
  # is how rev A once archived 11 copies of one result. Absence is the only valid pre-state.
  rm -f "$live"
  say "--- CELL $m temp=$t min_p=$mp top_p=$tp top_k=$tk ($lab)"
  PYTHONPATH=. "$PY" -m bench.run_convergence --model "$m" \
    --sampling-profile deployed --task vartrack --temperature "$t" \
    --samples 2 --coding-samples 1 \
    --set min_p="$mp" --set top_p="$tp" --set top_k="$tk" \
    >> "/tmp/tier0b_${m}_${lab}.log" 2>&1
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    say "!!! CELL $m $lab rc=$rc FAILED — not archived, not retried blindly"
    return 0
  fi
  if [ ! -f "$live" ]; then
    say "!!! CELL $m $lab rc=0 but NO OUTPUT FILE — investigate"
    return 0
  fi
  # Verify the run used the config we asked for -- ALL truncation knobs, not just temp/min_p.
  if ! "$PY" "$CHECK" "$live" "temperature=$t" "min_p=$mp" "top_p=$tp" "top_k=$tk" \
        >> "$LOG" 2>&1; then
    say "!!! CELL $m $lab OUTPUT PARAMS DO NOT MATCH REQUEST — not archived"
    return 0
  fi
  cp "$live" "$out"
  say "--- CELL $m $lab rc=0 archived + params verified"
}

say "=== TIER0B START (vartrack, deployed truncation, min_p 0.0/0.05/0.15)"
for M in Qwen3.6-27B-Opus-Distill-OptiQ-4bit Ornith-1.0-35B-mlx-uniform-4bit; do
  say "=== MODEL $M"
  for T in 0.2 0.4 0.6; do
    for MP in 0.0 0.05 0.15; do
      cell "$M" "$T" "$MP" 0.95 20 "t${T}_mp${MP}"
    done
  done
  # Collapse test at the grid centre: deployed 3-knob vs a GENUINE min_p-only comparator.
  cell "$M" 0.4 0.0  0.95 20 "collapse_3knob"
  cell "$M" 0.4 0.05 1.0  0  "collapse_minp_only"
  curl -s -m 300 -X POST localhost:8000/v1/models/unload \
       -H 'Content-Type: application/json' -d "{\"model\":\"$M\"}" >/dev/null 2>&1
  say "=== unloaded $M"
done
say "TIER0B COMPLETE"
