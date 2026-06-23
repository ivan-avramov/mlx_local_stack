#!/usr/bin/env bash
# BFCL AST single-turn H2H driver for the local mlx-serve endpoint.
#
# Wiring (validated 2026-06-22): benchmark/bfcl_shim/sitecustomize.py registers our
# mlx-serve registry names into bfcl_eval MODEL_CONFIG_MAPPING at interpreter startup
# (auto-imported because bfcl_shim is on PYTHONPATH). The OSS handler then sends
# model_name (== our registry name) to /v1/completions, so the mlx-serve proxy routes
# deterministically (it 404s unknown names). Tokenizer/template load offline from the
# model's HF snapshot via REMOTE_OPENAI_TOKENIZER_PATH (needs REMOTE_OPENAI_BASE_URL set).
#
# Run ONE model at a time — it must be the model currently LOADED on :8000.
# Usage:  ./run_bfcl_h2h.sh gemma   [--limit 3]
#         ./run_bfcl_h2h.sh qwen    [--limit 3]
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root

# Machine-local paths/hosts live outside the repo (see config.example.sh).
_cfg="${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
[ -f "$_cfg" ] && . "$_cfg"
: "${DISTILL_MODEL_PATH:=}"      # defined here so set -u doesn't trip when distill isn't configured

WHICH="${1:?usage: run_bfcl_h2h.sh <gemma|qwen|distill> [extra run_bfcl args...]}"; shift || true
case "$WHICH" in
  gemma)   MODEL="gemma-4-26B-A4B-it-OptiQ-4bit"; TOK="mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit" ;;
  qwen)    MODEL="Qwen3.6-27B-OptiQ-4bit";        TOK="mlx-community/Qwen3.6-27B-OptiQ-4bit" ;;
  # M5-only: locally-converted Opus-reasoning distill; tokenizer is its local snapshot dir.
  distill) MODEL="Qwen3.6-27B-Opus-Distill-OptiQ-4bit"; TOK="$DISTILL_MODEL_PATH" ;;
  *) echo "unknown model selector '$WHICH' (gemma|qwen|distill)"; exit 2 ;;
esac

export PYTHONPATH="benchmark:benchmark/bfcl_shim"
export REMOTE_OPENAI_BASE_URL="http://localhost:8000/v1"
export REMOTE_OPENAI_TOKENIZER_PATH="$TOK"
export HF_HUB_OFFLINE=1
export PATH="$PWD/.venv-bench/bin:$PATH"   # so the `bfcl` console script resolves to .venv-bench

echo "[bfcl-h2h] model=$MODEL tokenizer=$TOK  (must be the model loaded on :8000)"
exec .venv-bench/bin/python -m bench.run_bfcl --model "$MODEL" "$@"
