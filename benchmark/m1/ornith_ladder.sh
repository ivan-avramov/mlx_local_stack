#!/usr/bin/env bash
# ORNITH TEMP-LADDER RE-CHECK (operator-approved 2026-08-11). Runs AFTER M1's two arms.
#
# WHY. Ornith's op-temp 0.4 was chosen from an LCB ladder under the OLD decision rule ("pass@1 is
# the hard constraint, convergence secondary"), which explicitly accepted conv 12/15 = 80%. Its
# recorded ladder NEVER reached 90% at any rung (0.6→33%, 0.5→20%, 0.4→80%, 0.3→73%), so the open
# question is whether that ~80% ceiling is REAL — a property of the model — or an artifact of how
# the rungs were selected. Either answer is load-bearing: it decides whether "Ornith does not
# self-terminate reliably" is a tuning gap or a documented capability limit.
#
# Uses the FAST mechanism (bench.run_convergence): aggregation@8K + one real coding prompt, only the
# SAMPLE COUNT reduced, never a generation param. Minutes per rung, not hours.
set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH
cd ${REPO:?set REPO}/benchmark
M=Ornith-1.0-35B-mlx-uniform-4bit
LOG=/tmp/ornith_ladder.log
say() { echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

say "=== ORNITH LADDER start (deployed budget; rungs 0.5 0.4 0.35 0.3 0.2)"
for T in 0.5 0.4 0.35 0.3 0.2; do
  say "--- rung temp=$T"
  PYTHONPATH=. ../.venv-bench/bin/python -m bench.run_convergence \
    --model "$M" --samples 5 --coding-samples 3 --temperature "$T" \
    >> "/tmp/ornith_ladder_t${T}.log" 2>&1
  say "--- rung temp=$T exit=$?"
  cp "results/$M/convergence.json" "results/$M/convergence.t${T}.json" 2>/dev/null
done
say "=== ORNITH LADDER done"
curl -s -m 300 -X POST localhost:8000/v1/models/unload -H 'Content-Type: application/json' \
     -d "{\"model\":\"$M\"}" >/dev/null 2>&1
say "=== unloaded"
