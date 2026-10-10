#!/bin/bash
W="$HOME/ws/mlx_local_stack_workdir/m48"
while ! grep -q "smoke second rc" /private/tmp/claude-501/-HOME-ws-mlx-local-stack/f1e106ac-b084-48e3-8e2b-f25e72396db3/tasks/b9qpis88r.output 2>/dev/null; do sleep 10; done
cd $STACK_REPO/benchmark; export PYTHONPATH=. MLX_SERVE_CONFIG=main_models.yaml
rm -rf "$W/probe_after_b3"
../.venv/bin/python -m bench.session_cache_probe --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --legs B --turns 6 --big-file-tokens 20000 --tag m48-after-b3 --workdir "$W/probe_after_b3" --out "$W/legB_after_pick3.json" > "$W/legB_after_pick3.log" 2>&1
echo "rc=$?" >> "$W/legB_after_pick3.log"
