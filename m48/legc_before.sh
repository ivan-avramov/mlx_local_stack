#!/bin/bash
cd $STACK_REPO/benchmark
W="$HOME/ws/mlx_local_stack_workdir/m48"
export PYTHONPATH=. MLX_SERVE_CONFIG=../main_models.yaml
../.venv/bin/python -m bench.session_cache_probe --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --legs C --tag m48-before --workdir "$W/probe" --out "$W/legC_before_pick.json" > "$W/legC_before_pick.log" 2>&1
echo "pick rc=$?" >> "$W/legC_before_pick.log"
../.venv/bin/python -m bench.session_cache_probe --model Ornith-1.0-35B-mlx-uniform-4bit --legs C --tag m48-before --workdir "$W/probe" --out "$W/legC_before_ornith.json" > "$W/legC_before_ornith.log" 2>&1
echo "ornith rc=$?" >> "$W/legC_before_ornith.log"
