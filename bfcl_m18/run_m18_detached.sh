#!/bin/zsh
# M18 BFCL — DETACHED relaunch 2026-08-24 (survives Claude session restarts; the first
# attempt was session-attached). Model 1 resumes at its REMAINING categories: parallel(200)
# and multiple(200) already have complete result files on disk from run 1 and are NOT
# regenerated; parallel_multiple restarts from scratch (bfcl generation has no partial
# resume — allow_overwrite rewrites the file).
#
# CONSEQUENCE: model 1's bfcl.json will summarize only the categories THIS script passes.
# The four raw result files all persist, so the full 4-category score is a mechanical
# re-score with no model time (see handoff).
set -e
cd "$HOME/ws/mlx_local_stack/benchmark"
ALL="simple_python,multiple,parallel,parallel_multiple"
M1="Qwen3.6-27B-Opus-Distill-OptiQ-4bit"

echo "=== M18 START $M1 (remaining cats) $(date +%H:%M:%S) ==="
set +e
PYTHONPATH=. ../.venv-bench/bin/python -m bench.run_bfcl_fc \
  --model "$M1" --test-category "parallel_multiple,simple_python" \
  --out "results/$M1/bfcl_fc" \
  > "$HOME/ws/mlx_local_stack_workdir/bfcl_m18/full_$M1.log" 2>&1
echo "=== M18 DONE $M1 rc=$? $(date +%H:%M:%S) ==="
set -e
grep -E "^\[bfcl_fc\]" "$HOME/ws/mlx_local_stack_workdir/bfcl_m18/full_$M1.log" | tail -1

for MODEL in Ornith-1.0-35B-mlx-uniform-4bit NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit; do
  echo "=== M18 START $MODEL $(date +%H:%M:%S) ==="
  set +e
  PYTHONPATH=. ../.venv-bench/bin/python -m bench.run_bfcl_fc \
    --model "$MODEL" --test-category "$ALL" \
    --out "results/$MODEL/bfcl_fc" \
    > "$HOME/ws/mlx_local_stack_workdir/bfcl_m18/full_$MODEL.log" 2>&1
  echo "=== M18 DONE $MODEL rc=$? $(date +%H:%M:%S) ==="
  set -e
  grep -E "^\[bfcl_fc\]" "$HOME/ws/mlx_local_stack_workdir/bfcl_m18/full_$MODEL.log" | tail -1
done
echo "=== M18 ALL DONE $(date +%H:%M:%S) ==="
