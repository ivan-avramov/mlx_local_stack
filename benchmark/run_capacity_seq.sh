#!/usr/bin/env bash
# Run the capacity+retrieval ladder for a sequence of models, ONE AT A TIME,
# unloading each before the next so only one big model is resident per machine.
# Usage:  bash run_capacity_seq.sh MODEL1 MODEL2 ...
# Logs progress with START/DONE/FAILED markers; prints ALL_DONE at the end.
set -u
cd "$(dirname "$0")"   # -> benchmark/ (where the `bench` package lives)

for m in "$@"; do
  echo "=== START $m $(date '+%F %T') ==="
  if uv run python -m bench.run_capacity --model "$m"; then
    echo "=== DONE $m $(date '+%F %T') ==="
  else
    echo "=== FAILED $m (exit $?) $(date '+%F %T') ==="
  fi
  # Unload so the next model loads into a clean footprint (best-effort).
  curl -s -X POST localhost:8000/v1/models/unload \
    -H 'Content-Type: application/json' -d "{\"model\":\"$m\"}" >/dev/null 2>&1 || true
done
echo "=== ALL_DONE $(date '+%F %T') ==="
