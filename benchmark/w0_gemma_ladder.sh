#!/bin/bash
# W0 gemma quant-convergence ladder (M2). One model at a time; unload between.
# Order: QAT-4bit (re-confirm baseline) -> OptiQ-4bit -> vanilla-4bit -> 8bit (heaviest).
set -u
cd "$(dirname "$0")"
for M in gemma-4-26B-A4B-it-QAT-MLX-4bit gemma-4-26B-A4B-it-OptiQ-4bit gemma-4-26b-a4b-it-4bit gemma-4-26b-a4b-it-8bit; do
  echo "===== $(date '+%H:%M:%S') START $M ====="
  PYTHONPATH=. ../.venv/bin/python -m bench.run_convergence --model "$M" 2>&1
  echo "===== $(date '+%H:%M:%S') UNLOAD $M ====="
  curl -s -X POST http://localhost:8000/v1/models/unload -H 'Content-Type: application/json' -d "{\"model\":\"$M\"}"; echo
done
echo "===== $(date '+%H:%M:%S') LADDER DONE ====="
