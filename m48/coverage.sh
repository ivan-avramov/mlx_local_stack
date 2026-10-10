#!/bin/bash
W="$HOME/ws/mlx_local_stack_workdir/m48"; cd $STACK_REPO/benchmark
export PYTHONPATH=. MLX_SERVE_CONFIG=main_models.yaml
for M in Qwen3.8-27B-mlx-uniform-4bit Ornith-1.0-35B-mlx-uniform-4bit NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit; do
  ../.venv/bin/python -m bench.session_cache_probe --model "$M" --legs C --sizes 8000,32000 --tag m48-cov --workdir "$W/cov_$M" --out "$W/legC_after_$M.json" > "$W/legC_after_$M.log" 2>&1; echo "rc=$?" >> "$W/legC_after_$M.log"
  ../.venv/bin/python -m bench.stack_smoke --model "$M" --tag m48-cov > "$W/smoke_cov_$M.log" 2>&1; echo "rc=$?" >> "$W/smoke_cov_$M.log"
done
echo "coverage done" >> "$W/coverage.log"
