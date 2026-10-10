#!/bin/bash
W="$HOME/ws/mlx_local_stack_workdir/m48"; cd $STACK_REPO/benchmark
export PYTHONPATH=. MLX_SERVE_CONFIG=main_models.yaml
M=gemma-4-31B-it-qat-6bit
../.venv/bin/python -m bench.session_cache_probe --model "$M" --legs C --sizes 8000,32000 --tag m48-cov --workdir "$W/cov_$M" --out "$W/legC_after_$M.json" > "$W/legC_after_$M.log" 2>&1; echo "rc=$?" >> "$W/legC_after_$M.log"
../.venv/bin/python -m bench.stack_smoke --model "$M" --tag m48-cov > "$W/smoke_cov_$M.log" 2>&1; echo "rc=$?" >> "$W/smoke_cov_$M.log"
echo "gemma done" >> "$W/gemma_cov.log"
