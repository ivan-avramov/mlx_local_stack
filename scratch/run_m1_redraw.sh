#!/bin/bash
# M1: re-draw test on the 13 OFF-only degenerate Ornith-1.0-35B-mlx-uniform-4bit items
# (--samples 3: sample 0 = determinism check, 1-2 = fresh draws), probe tree ONLY —
# then the canonical repair of Qwen3.6-27B-Opus-Distill-OptiQ-4bit Mbpp/430.
set -uo pipefail
source "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
REPO="$STACK_REPO"
PY="$REPO/.venv-bench/bin/python"
PROBE="$STACK_WORKDIR/redraw-2026-08-17"
STATUS="$STACK_WORKDIR/status"
mkdir -p "$PROBE" "$STATUS"
cd "$REPO/benchmark"

HE_IDS='HumanEval/101:HumanEval/109:HumanEval/131:HumanEval/157:HumanEval/159:HumanEval/163:HumanEval/38:HumanEval/71:HumanEval/86:HumanEval/96'
MB_IDS='Mbpp/428:Mbpp/430:Mbpp/775'

echo "[$(date '+%F %T')] M1 phase 1: Ornith-1.0-35B-mlx-uniform-4bit probe (13 items x3 samples) -> $PROBE"
PYTHONPATH=. nohup "$PY" m1/bench_watch.py \
  --models Ornith-1.0-35B-mlx-uniform-4bit --bench humanevalplus --total 30 \
  --driver-pattern 'run.py generate' --out "$STATUS/m1_redraw_watch.md" --interval 300 \
  >/dev/null 2>&1 &
WATCH=$!

MLX_BENCH_RESULTS="$PROBE" "$PY" run.py generate \
  --models Ornith-1.0-35B-mlx-uniform-4bit \
  --benches humanevalplus,mbppplus \
  --limit humanevalplus=100,mbppplus=100 \
  --ids "humanevalplus=${HE_IDS},mbppplus=${MB_IDS}" \
  --samples 3 --sampling-profile deployed --order model --chunks all
RC1=$?
kill "$WATCH" 2>/dev/null
echo "[$(date '+%F %T')] phase 1 rc=$RC1; unloading Ornith-1.0-35B-mlx-uniform-4bit"
curl -s -X POST localhost:8000/v1/models/unload \
  -H 'Content-Type: application/json' \
  -d '{"model":"Ornith-1.0-35B-mlx-uniform-4bit"}' >/dev/null

echo "[$(date '+%F %T')] M1 phase 2: canonical repair Qwen3.6-27B-Opus-Distill-OptiQ-4bit Mbpp/430"
"$PY" run.py generate \
  --models Qwen3.6-27B-Opus-Distill-OptiQ-4bit \
  --benches mbppplus --limit mbppplus=100 \
  --ids mbppplus=Mbpp/430 \
  --sampling-profile deployed --order model --chunks all
RC2=$?
echo "[$(date '+%F %T')] phase 2 rc=$RC2; unloading Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
curl -s -X POST localhost:8000/v1/models/unload \
  -H 'Content-Type: application/json' \
  -d '{"model":"Qwen3.6-27B-Opus-Distill-OptiQ-4bit"}' >/dev/null
echo "[$(date '+%F %T')] M1 COMPLETE rc1=$RC1 rc2=$RC2"
