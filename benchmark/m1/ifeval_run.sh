#!/usr/bin/env bash
# IFEval, full 541 items, both winners — the daily-driver instruction-following axis.
#
# WHY NOW: IFEval was recorded as BLOCKED ("datasets: Feature type 'List' not found") and that was
# FALSIFIED — it loads 541 items on both boxes; the real gap was four missing verifier deps, since
# installed. It is a named daily-role axis, its harness is functional, and it needs zero new code, so
# it is the cheapest informative thing available. It also validates the mechanical constraint-checking
# machinery that Benchmark B (daily-driver session depth) depends on.
#
# ⚠️ MUST RUN FROM THE REPO ROOT. run.py resolves both `main_models.yaml` and the results root
# CWD-relative. From `benchmark/` it writes to `benchmark/benchmark/results/`, fails EVERY row with
# "cannot read the model registry", and still prints "COMPLETE — 5 items generated". (Verified
# 2026-08-13. `--sampling-profile deployed` at least fails LOUD per row rather than silently falling
# back to the drifted `production` table.)
#
# ONE RESIDENT MODEL: the arms are strictly sequential with an explicit unload between them.
set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH
R=$HOME/ws/mlx_local_stack
cd "$R" || exit 1                      # repo root, deliberately — see above

LOG=/tmp/ifeval_run.log
PY=$R/.venv-bench/bin/python
say(){ echo "[$(date +%H:%M:%S)] $*" >> "$LOG"; }

# Ornith first: ~4x faster decode, so a config error surfaces in minutes rather than hours.
MODELS="Ornith-1.0-35B-mlx-uniform-4bit
Qwen3.6-27B-Opus-Distill-OptiQ-4bit"

say "=== IFEval START (541 items x 2 models, deployed sampling, APC absent)"
while IFS= read -r M; do            # `for M in $MODELS` runs ONCE in zsh (no word splitting)
  say "--- MODEL $M generate"
  PYTHONPATH=benchmark "$PY" benchmark/run.py generate \
    --models "$M" --benches ifeval --sampling-profile deployed \
    >> "/tmp/ifeval_${M}.log" 2>&1
  rc=$?
  say "--- MODEL $M generate rc=$rc"

  # Grade immediately: mechanical, no model time, and it makes a partial run readable.
  PYTHONPATH=benchmark "$PY" benchmark/run.py grade \
    --models "$M" --benches ifeval >> "/tmp/ifeval_${M}.grade.log" 2>&1
  say "--- MODEL $M graded rc=$?"

  curl -s -m 300 -X POST localhost:8000/v1/models/unload \
       -H 'Content-Type: application/json' -d "{\"model\":\"$M\"}" >/dev/null 2>&1
  say "--- unloaded $M"
done <<< "$MODELS"
say "IFEVAL COMPLETE"
