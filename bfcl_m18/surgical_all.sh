#!/bin/zsh
# Chained surgical re-runs + full parallel_multiple re-run + re-scores. ONE resident
# model at a time (unload between). Runs under the O41-fixed harness.
set -e
cd "$HOME/ws/mlx_local_stack/benchmark"
PY=../.venv-bench/bin/python
W="$HOME/ws/mlx_local_stack_workdir/bfcl_m18"
unload() { curl -s -m 30 -X POST localhost:8000/v1/models/unload >/dev/null || true }

M_NEM="NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
M_ORN="Ornith-1.0-35B-mlx-uniform-4bit"
M_QWE="Qwen3.6-27B-Opus-Distill-OptiQ-4bit"

echo "=== SURGICAL START $M_NEM $(date +%H:%M:%S) ==="
set +e
PYTHONPATH=. $PY "$W/surgical_rerun.py" "$M_NEM" "results/$M_NEM/bfcl_fc" \
  '{"parallel": ["parallel_169"]}' > "$W/surgical_$M_NEM.log" 2>&1
echo "=== SURGICAL DONE $M_NEM rc=$? $(date +%H:%M:%S) ==="
set -e
unload

echo "=== SURGICAL START $M_ORN $(date +%H:%M:%S) ==="
set +e
PYTHONPATH=. $PY "$W/surgical_rerun.py" "$M_ORN" "results/$M_ORN/bfcl_fc" \
  '{"parallel": ["parallel_80","parallel_81","parallel_104","parallel_105"], "parallel_multiple": ["parallel_multiple_70","parallel_multiple_71","parallel_multiple_91","parallel_multiple_92"]}' \
  > "$W/surgical_$M_ORN.log" 2>&1
echo "=== SURGICAL DONE $M_ORN rc=$? $(date +%H:%M:%S) ==="
set -e
unload

echo "=== FULL parallel_multiple START $M_QWE $(date +%H:%M:%S) ==="
set +e
PYTHONPATH=. $PY -m bench.run_bfcl_fc --model "$M_QWE" --test-category parallel_multiple \
  --out "results/$M_QWE/bfcl_fc" > "$W/full_pm_$M_QWE.log" 2>&1
echo "=== FULL parallel_multiple DONE $M_QWE rc=$? $(date +%H:%M:%S) ==="
set -e
unload

for M in "$M_NEM" "$M_ORN" "$M_QWE"; do
  echo "=== RESCORE $M $(date +%H:%M:%S) ==="
  set +e
  $PY "$W/rescore_m18.py" --model "$M" --out "results/$M/bfcl_fc" \
    > "$W/rescore_final_$M.log" 2>&1
  echo "=== RESCORE DONE $M rc=$? ==="
  set -e
done
echo "=== SURGICAL ALL DONE $(date +%H:%M:%S) ==="
