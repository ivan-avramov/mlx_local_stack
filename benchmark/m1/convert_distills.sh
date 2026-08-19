#!/bin/bash
# M15/M16/M17 distill conversions — quiet-window/overnight runner (2026-08-18). <!-- allow-shorthand -->
# Converts the three downloaded checkpoints (see JOBS below for full names) to the proven uniform
# {4-bit, gs64, affine} recipe via the fork's mlx_vlm.convert. Serial, RAM-heavy:
# REFUSES to start while a model server is up (:8000 or :8091) unless --force.
#
# Sources are already in the HF cache (downloads completed 2026-08-18); the
# convert step reads the cached snapshots and should not need network.
# Outputs + logs stay inside $STACK_WORKDIR (containment rule).
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG_SH="${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
[[ -f "$CONFIG_SH" ]] && source "$CONFIG_SH"
: "${STACK_WORKDIR:?STACK_WORKDIR not set — source config.sh or export it}"

OUT_ROOT="$STACK_WORKDIR/models"
LOG_DIR="$STACK_WORKDIR/status"
mkdir -p "$OUT_ROOT" "$LOG_DIR"

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

# Quiet-window guard: conversions must never run beside a served model.
for port in 8000 8091 8092; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    if [[ $FORCE -eq 1 ]]; then
      echo "WARNING: listener on :$port but --force given — continuing." >&2
    else
      echo "REFUSING: a model server is listening on :$port. Conversions are" >&2
      echo "RAM-heavy and run only in a quiet window. Stop the stack first" >&2
      echo "(or pass --force if you know the listener is not a model server)." >&2
      exit 2
    fi
  fi
done

# name|hf_source  (names per docs/PLAN.md M15/M16/M17 rows)
JOBS=(
  "Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit|TeichAI/Qwen3.8-27B-Fable-Distill"
  "Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit|barozp/Qwen3.8-27B-Opus-Distill-v2"
  "Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit|armand0e/Qwen3.6-35B-A3B-Fable-5-Distill"
)

SUMMARY="$LOG_DIR/convert_distills_summary.log"
echo "=== convert_distills start $(date '+%F %T') (fork sha: $(git -C "$REPO/src/mlx-vlm" rev-parse --short HEAD 2>/dev/null || echo unknown)) ===" >>"$SUMMARY"

overall_rc=0
for job in "${JOBS[@]}"; do
  name="${job%%|*}"; src="${job##*|}"
  out="$OUT_ROOT/$name"
  log="$LOG_DIR/convert_${name}.log"
  if [[ -f "$out/config.json" ]]; then
    echo "SKIP $name — $out already has config.json" | tee -a "$SUMMARY"
    continue
  fi
  echo "[$(date '+%F %T')] CONVERT $src -> $out" | tee -a "$SUMMARY"
  set +e
  "$REPO/.venv/bin/python" -m mlx_vlm convert \
    --hf-path "$src" \
    --mlx-path "$out" \
    -q --q-bits 4 --q-group-size 64 \
    >"$log" 2>&1
  RC=$?
  if [[ $RC -ne 0 ]]; then
    echo "[$(date '+%F %T')] FAIL $name rc=$RC — see $log (tree left for inspection)" | tee -a "$SUMMARY"
    overall_rc=1
    continue
  fi
  # Verify the artifact, never trust rc alone.
  if [[ -f "$out/config.json" ]] && ls "$out"/*.safetensors >/dev/null 2>&1; then
    sz=$(du -sh "$out" | cut -f1)
    bpw=$(grep -Eo 'Quantized model with [0-9.]+ bits per weight' "$log" | tail -1)
    echo "[$(date '+%F %T')] OK $name  size=$sz  ${bpw:-bpw-not-reported}" | tee -a "$SUMMARY"
  else
    echo "[$(date '+%F %T')] FAIL $name — rc=0 but artifact incomplete at $out" | tee -a "$SUMMARY"
    overall_rc=1
  fi
done

echo "=== convert_distills done $(date '+%F %T') rc=$overall_rc ===" >>"$SUMMARY"
exit $overall_rc
