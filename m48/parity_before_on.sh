#!/bin/bash
while kill -0 81303 2>/dev/null; do sleep 10; done
cd $STACK_REPO/benchmark
W="$HOME/ws/mlx_local_stack_workdir/m48"; mkdir -p "$W/parity"
export PYTHONPATH=. MLX_SERVE_CONFIG=../main_models.yaml
../.venv/bin/python -m bench.parity_replay run --frozen "$HOME/ws/mlx_local_stack_workdir/upstream/2026-09-14-activation/quality-v2/frozen-after.json" --tag m48-before-mtp-on --out "$W/parity/before_on.json" > "$W/parity/before_on.log" 2>&1
echo "rc=$?" >> "$W/parity/before_on.log"
