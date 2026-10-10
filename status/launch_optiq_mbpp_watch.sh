#!/bin/bash
cd $STACK_REPO/benchmark || exit 1
export PYTHONPATH=$STACK_REPO/benchmark
exec ../.venv-bench/bin/python m1/bench_watch.py \
  --models Qwen3.8-27B-OptiQ-4.5bpw-mixed \
  --bench mbppplus --tune t0.6 --total 50 \
  --driver-pattern "run.py generate" \
  --out "$HOME/ws/mlx_local_stack_workdir/status/stage2_optiq_mbpp_n50.watch" \
  --interval 300
