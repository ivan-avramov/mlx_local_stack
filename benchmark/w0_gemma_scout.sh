#!/bin/bash
# W0 gemma quant-convergence SCOUT (M2): 1 agg + 1 coding sample per quant for a fast
# binary convergence read. Untested 4-bits first (OptiQ, vanilla), then 8bit, then the
# known-non-converger QAT last. Deep-sample the winner afterward. Realistic params
# (only sample COUNT is reduced — not a generation param).
set -u
cd "$(dirname "$0")"
for M in gemma-4-26B-A4B-it-OptiQ-4bit gemma-4-26b-a4b-it-4bit gemma-4-26b-a4b-it-8bit gemma-4-26B-A4B-it-QAT-MLX-4bit; do
  echo "===== $(date '+%H:%M:%S') START $M ====="
  PYTHONPATH=. ../.venv/bin/python -m bench.run_convergence --model "$M" --samples 1 --coding-samples 1 2>&1
  echo "===== $(date '+%H:%M:%S') UNLOAD $M ====="
  curl -s -X POST http://localhost:8000/v1/models/unload -H 'Content-Type: application/json' -d "{\"model\":\"$M\"}"; echo
done
echo "===== $(date '+%H:%M:%S') SCOUT DONE ====="
