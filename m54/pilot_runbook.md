# M54 pilot runbook (executed step by step; each step verified before the next)

R=$STACK_REPO ; W=$STACK_WORKDIR/m54 ; OV=$W/overlay_m54_draft_off.yaml
MODEL=Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed

1. Stop the daily driver stack:      $R/scripts/stack_stop.sh   → must print ":8000 free"; lsof -nP -iTCP:8000 shows nothing.
2. Start the lean router (APC_ENABLED absent):
   cd $R && set -a; . ./.env 2>/dev/null; set +a; MLX_VLM_CACHE_SESSION_MAX=2 MLX_SERVE_CONFIG=$OV nohup uv run mlx-serve start >logs/main_model.log 2>&1 </dev/null &
   verify: lsof shows the NEW pid on :8000; ps -Eww <pid> shows MLX_SERVE_CONFIG=$OV, MLX_VLM_CACHE_SESSION_MAX=2, no APC_ENABLED.
3. Warm: one tiny chat completion to $MODEL (loads the worker); record worker cmdline (`ps -o command=`): no --draft-kind, --kv-bits absent (native16), cap 262144.
4. Watcher calibration during a known-active generation: start a 2-minute generation request in background, then
   cd $R/benchmark && PYTHONPATH=. ../.venv-bench/bin/python -m bench.agentbench_watch --calibrate ... (per its CLI) → record busy %cpu; repeat idle → record idle %cpu.
5. Launch the pilot (explicit timeout: UNVALIDATED override, basis: draft-off TQ4 m37med floor 23.06 tok/s → 102400/23.06+300 ≈ 4740 s; rounded 5000 s):
   cd $R/benchmark && MLX_SERVE_CONFIG=$OV PYTHONPATH=. nohup ../.venv-bench/bin/python -m bench.run_agentbench_os --model $MODEL \
     --pilot-seed 54 --pilot-n 5 --llm-timeout 5000 --out $W/pilot/$MODEL/agentbench_os.v1.pilot.jsonl \
     --transcripts-dir $W/transcripts > $W/pilot/driver_$MODEL.log 2>&1 </dev/null &
   verify first manifest: router.pid == new router pid, router.config == $OV, config_sha256, runtime.draft_kind off, timeout_derivation.observable == "override".
6. Watcher daemon alongside (interval 300): --rows <out> --manifest <stem>.manifest.json --total 5 --driver-pid <pid> --router-log $R/logs/main_model.log --out $W/pilot/watch_$MODEL.log
7. Every 5 min: read the watcher block + by hand: pgrep driver, worker %cpu, tail router log, inspect the newest transcript for quality (answer plausibility, tool usage, degenerate loops).
8. On completion: summary → mean/max wall_total_s → size the 142-task arm (lower bound; add tail budget) → report to operator with status/learnings/trends/recommendation.
