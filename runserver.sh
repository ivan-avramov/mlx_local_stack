#!/bin/bash
set -euo pipefail

ENV_FILE="$(dirname "$0")/.env"
TASK_MODEL_HOST="127.0.0.1"
MAIN_MODEL_HOST="127.0.0.1"
export TASK_MODEL_PORT="8092"
# Exported: openwebui-init needs it to mark the main router's OWUI connection
# 'local', without which OWUI routes every task call to the chat model.
export MAIN_MODEL_PORT="8000"
TASK_MODEL_URL="http://${TASK_MODEL_HOST}:${TASK_MODEL_PORT}"
MAIN_MODEL_URL="http://${MAIN_MODEL_HOST}:${MAIN_MODEL_PORT}"

# the task model should be defined in the openwebui-init/models_config.json.
export TASK_MODEL="mlx-community/Qwen2.5-1.5B-Instruct-4bit"

OWUI_URL=http://localhost:3000
export HF_HOME="${HOME}/.cache/huggingface"
export MLX_VLM_LOG_FILE="logs/mlx_vlm.log"
export MLX_VLM_LOG_LEVEL="INFO"
export TASK_MODEL_LOG_FILE="logs/task_model.log"
export TASK_MODEL_LOG_FILE0="logs/task_model_0.log"
export TASK_MODEL_LOG_LEVEL="INFO"
export OWUI_ADMIN_EMAIL="admin@a.a"
export OWUI_ADMIN_PASSWORD="admin"

log_ok()   { printf "\e[32m✓\e[0m $*" >&2; }
log_fail() { printf "\e[31m✗\e[0m $*"; }

mkdir -p logs;
mkdir -p open-webui-data

if [[ ! -f "$ENV_FILE" ]]; then
  log_fail "WARNING: .env file not found at $ENV_FILE. Crate the file and add your HuggingFace token there HF_TOKEN=<your_token>. See https://huggingface.co/docs/hub/security-tokens for more info"
else
  set -a; source "$ENV_FILE"; set +a
fi
echo
echo "Syncing submodules..."
git submodule update --init --recursive --remote

echo "Bootstrapping uv..."
uv sync

# Drift guard: client configs (opencode/aider/vscode/zed/OWUI) are GENERATED from
# main_models.yaml by configgen — if main_models.yaml changed without re-running
# `configgen generate`, the checked-in configs are stale. Fail fast (set -e) rather
# than launch clients against an out-of-date model list/sampling.
echo "Checking generated client configs for drift..."
uv run python -m configgen check
log_ok "Client configs match main_models.yaml.\n"

echo "Backing up OpenWebUI data..."
uv run python do_backup.py docker-compose.yml open-webui-data/
log_ok "Backup completed.\n"

# --- Start task model server ---
echo "Starting task model (mlx_vlm, ${TASK_MODEL_URL})..."
uv run python -u -m mlx_vlm.server \
  --model $TASK_MODEL \
  --host $TASK_MODEL_HOST \
  --port $TASK_MODEL_PORT \
  --log-level $TASK_MODEL_LOG_LEVEL \
  --log-file $TASK_MODEL_LOG_FILE \
  --quantized-kv-start 0 &>$TASK_MODEL_LOG_FILE0 &
TASK_MODEL_PID=$!

# --- Start main multi- model server ---
# APC (Automatic Prefix Caching) is DELIBERATELY NOT ENABLED — operator decision 2026-08-13, on
# measurement. Do not re-add `APC_ENABLED=1` without re-reading this.
#
# WHY IT IS OFF. Session caching already does the job, and it SHADOWS APC by construction.
# `mlx_vlm/server/generation.py:2455-2464` dispatches any request carrying a `prompt_cache_state` to
# `_process_cached_request` and `continue`s past the BatchGenerator — the ONLY place `apc_manager` is
# ever passed. Anonymous requests resolve to a session by chained per-message hashes, so effectively
# ALL traffic takes the session path and APC is never consulted. Measured with APC_ENABLED=1 and
# APC_NUM_BLOCKS=2048 present in both router and worker env: the worker reports `enabled: true` but
# `pool_used 0, lookups_hit 0, lookups_miss 0, stores 0, resident_bytes 0`, and one 9K-token prefix
# served three times gave prefill 3.10 / 3.00 / 3.00s — no reuse. Peak memory was bit-identical to
# APC-absent (22.957264336 GB both ways).
#
# The Phase-2 note that used to live here ("agentic multi-turn TTFT collapses 34-147x") does NOT
# reproduce on the current stack and should be treated as unreliable until re-measured.
#
# WHAT ACTUALLY MAKES MULTI-TURN CHEAP: the fork's session cache (`PromptCacheState`,
# `server/session_manager.py`), which prefills only the tokens after the common prefix and needs no
# `chat_id` from the client. Measured on a growing conversation: cost per NEW token flat (0.82 ->
# 0.91 ms) while cost per TOTAL token fell 17x (2.55 -> 0.15 ms). That is independent of APC.
#
# THREE REASONS THE FLAG IS GONE RATHER THAN LEFT ON HARMLESSLY:
#  1. Zero benefit today, and only ~6s per NEW conversation even if repaired (its one reachable case
#     is a fresh conversation reusing a previous one's ~18K-token system prompt).
#  2. A demonstrated OOM class: APC_NUM_BLOCKS=16384 (a full 256K prefix) MEASURED ~33GB, leaving
#     this box 4.1GB free with Ornith-1.0-35B-mlx-uniform-4bit resident (54.2GB vs 20.8GB with APC
#     absent) and killing a benchmark arm on [METAL] Insufficient Memory — with those failures being
#     scored as MODEL failures.
#  3. It collapses a documented measurement hazard. This script enabling APC while the AGENTS.md
#     benchmark recipe omitted it is exactly why past benchmark runs silently differed from what we
#     serve. Served config == measured config is worth more than 6 seconds.
#
# The code, its `/metrics` counters and the <=4096 pool-size guard all stay: the counters are what
# made the inertness provable, and a future multi-tenant deployment could want it. Guarded by
# benchmark/bench/tests/test_provenance_fingerprint.py::test_runserver_does_NOT_enable_apc.
echo "Starting main model (mlx_vlm, ${MAIN_MODEL_URL})..."
# Cap retained per-conversation KV caches (operator-approved 2026-08-18): with
# kv_prealloc_tokens = cap, each retained session floors at the FULL cap (~4 GB TQ4 at
# 262144), and the default of 8 puts both winners over the 46 GB gate on floors alone —
# measured 58 GB + heavy swap. MLX's memory-limit backstop cannot reclaim these floors
# (they are live referenced arrays, not pool buffers). See D6 audit.
MLX_VLM_CACHE_SESSION_MAX=2 MLX_SERVE_CONFIG=main_models.yaml uv run mlx-serve start &>logs/main_model.log &
MAIN_MODEL_PID=$!

echo -n "Waiting for main model to be ready..."
spinner='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
i=0
until curl -sf http://localhost:8000/health >/dev/null 2>&1; do
  printf "\r\033[2K  ${spinner:$((i % ${#spinner})):1}  Waiting for main model..."
  ((i++))
  sleep 0.1
done
log_ok "Main model ready.\n"

echo -n "Waiting for task model to be ready..."
spinner='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
i=0
until curl -sf $TASK_MODEL_URL/health >/dev/null 2>&1; do
  printf "\r\033[2K  ${spinner:$((i % ${#spinner})):1}  Waiting for task model..."
  ((i++))
  sleep 0.1
done
log_ok "Task model ready.\n"

# --- Teardown on exit ---
cleanup() {
  trap - EXIT INT TERM
  echo
  echo "Shutting down..."
  kill $TASK_MODEL_PID 2>/dev/null || true
  wait $TASK_MODEL_PID 2>/dev/null || true
  kill $MAIN_MODEL_PID 2>/dev/null || true
  wait $MAIN_MODEL_PID 2>/dev/null || true
  docker compose down
  echo "Cleaned up. Goodbye!"
}
trap cleanup EXIT INT TERM

echo "Seeding OpenWebUI config..."
cp openwebui_config.json open-webui-data/config.json

# --- Start the compose stack (foreground, so script stays alive) ---
docker compose build open-webui-init
docker compose pull --ignore-pull-failures --ignore-buildable
docker compose up -d

echo -n "Waiting for openwebui-init..."

#docker compose logs -f open-webui-init &>logs/open-webui-init.log &
# `|| EXIT_CODE=$?` matters: under `set -e` a nonzero `docker compose wait` would
# abort the script before the check below, so the actionable message never printed
# and a failed init looked like a bare teardown.
EXIT_CODE=0
docker compose wait open-webui-init || EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
  log_fail "OpenWebUI initialization failed (exit $EXIT_CODE). Run 'docker compose logs open-webui-init' — a nonzero exit here also means the task-model routing assertion failed.\n"
  exit 1
fi
log_ok "OpenWebUI initialization completed.\n"

echo -n "Waiting for OpenWebUI to be ready..."
i=0
until curl -sf "${OWUI_URL}/health" >/dev/null 2>&1; do
  printf "\r\033[2K  ${spinner:$((i % ${#spinner})):1}  Waiting for OpenWebUI..."
  ((i++))
  sleep 0.1
done
log_ok "OpenWebUI ready.\n"

echo "Opening OpenWebUI at ${OWUI_URL} ..."
open "$OWUI_URL"
printf "\nYou can log in with:\n  Email: ${OWUI_ADMIN_EMAIL}\n  Password: ${OWUI_ADMIN_PASSWORD}\n\n"
echo "All services started. Press Ctrl+C to stop."
docker compose logs -f &>logs/compose.log
