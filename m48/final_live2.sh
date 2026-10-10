#!/bin/bash
W="$HOME/ws/mlx_local_stack_workdir/m48"
cd $STACK_REPO/benchmark; export PYTHONPATH=. MLX_SERVE_CONFIG=main_models.yaml
../.venv/bin/python -m bench.stack_smoke --model Qwen3.8-27B-mlx-uniform-4bit --tag m48-after > "$W/smoke_after_second3.log" 2>&1; echo "rc=$?" >> "$W/smoke_after_second3.log"
rm -rf "$W/probe_after_b4"
../.venv/bin/python -m bench.session_cache_probe --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --legs B --turns 6 --big-file-tokens 20000 --tag m48-after-b4 --workdir "$W/probe_after_b4" --out "$W/legB_after_pick4.json" > "$W/legB_after_pick4.log" 2>&1; echo "rc=$?" >> "$W/legB_after_pick4.log"
echo "final_live2 done" >> "$W/final_live2.log"
