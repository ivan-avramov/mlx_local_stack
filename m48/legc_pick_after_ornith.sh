#!/bin/bash
while kill -0 80636 2>/dev/null; do sleep 10; done
cd $STACK_REPO/benchmark
W="$HOME/ws/mlx_local_stack_workdir/m48"
export PYTHONPATH=. MLX_SERVE_CONFIG=../main_models.yaml
../.venv/bin/python -m bench.session_cache_probe --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --legs C --tag m48-before2 --workdir "$W/probe2" --out "$W/legC_before_pick.json" > "$W/legC_before_pick2.log" 2>&1
echo "pick rc=$?" >> "$W/legC_before_pick2.log"
