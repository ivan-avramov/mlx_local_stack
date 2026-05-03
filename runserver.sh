#!/bin/bash
set -euo pipefail

ENV_FILE="$(dirname "$0")/.env"
TASK_MODEL_HOST="127.0.0.1"
export TASK_MODEL_PORT="8092"
TASK_MODEL_URL="http://${TASK_MODEL_HOST}:${TASK_MODEL_PORT}"

# the task model should be defined in the openwebui-init/models_config.json.
export TASK_MODEL="mlx-community/Qwen2.5-1.5B-Instruct-4bit"

OWUI_URL=http://localhost:3000
export HF_HOME="${HOME}/.cache/huggingface"
export MLX_VLM_LOG_FILE="logs/mlx_vlm.log"
export MLX_VLM_LOG_LEVEL="INFO"
export TASK_MODEL_LOG_FILE="logs/task_model.log"
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


echo "Backing up OpenWebUI data..."
uv run python do_backup.py docker-compose.yml open-webui-data/
log_ok "Backup completed.\n"

# --- Start task model server ---
echo "Starting task model (mlx_vlm, port 8092)..."
uv run python -u -m mlx_vlm.server \
  --model $TASK_MODEL \
  --host $TASK_MODEL_HOST \
  --port $TASK_MODEL_PORT \
  --log-level $TASK_MODEL_LOG_LEVEL \
  --log-file $TASK_MODEL_LOG_FILE \
  --quantized-kv-start 0 &>$TASK_MODEL_LOG_FILE &
TASK_MODEL_PID=$!

# --- Start main multi- model server ---
echo "Starting task model (mlx_vlm, port 8092)..."
MLX_SERVE_CONFIG=main_models.yaml uv run mlx-serve start &>logs/main_model.log &
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
docker compose wait open-webui-init
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
  log_fail "OpenWebUI initialization failed. Check logs/compose.log for details.\n"
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
