#!/usr/bin/env bash
# Run the capacity+retrieval ladder for a sequence of models, ONE AT A TIME,
# unloading each before the next so only one big model is resident per machine.
# Usage:  bash run_capacity_seq.sh MODEL1 MODEL2 ...
# Logs progress with START/DONE/FAILED markers; prints ALL_DONE at the end.
set -u
# Set CAPACITY_OUT_TAG to a fresh tag when previous results exist.
extra_args=(--sampling-profile deployed)
if [[ -n "${CAPACITY_OUT_TAG:-}" ]]; then
  extra_args+=(--out-tag "$CAPACITY_OUT_TAG")
fi
cd "$(dirname "$0")"   # -> benchmark/ (where the `bench` package lives)

for m in "$@"; do
  echo "=== START $m $(date '+%F %T') ==="
  if uv run python -m bench.run_capacity --model "$m" "${extra_args[@]}"; then
    echo "=== DONE $m $(date '+%F %T') ==="
  else
    run_rc=$?
    echo "=== FAILED $m (exit $run_rc) $(date '+%F %T') ==="
    exit "$run_rc"  # leave the failed worker for inspection; never arm the next model
  fi
  # Require successful unloading before the next model; HTTP failures are errors.
  if curl --fail --silent --show-error -X POST localhost:8000/v1/models/unload \
    -H 'Content-Type: application/json' -d "{\"model\":\"$m\"}" >/dev/null; then
    :
  else
    unload_rc=$?
    echo "=== UNLOAD_FAILED $m (exit $unload_rc) ==="
    exit "$unload_rc"
  fi
done
echo "=== ALL_DONE $(date '+%F %T') ==="
