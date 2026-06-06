# mlx_local_stack

Local stack: mlx_vlm task model (port 8092), mlx-serve main models (port 8000), and OpenWebUI on docker compose (port 3000).

## Slash commands

- `/mlx start` — runs `./runserver.sh`, which syncs submodules, backs up OWUI data, launches both model servers, brings up the compose stack, and tails logs. Ctrl+C tears everything down via the script's trap.

## Entry points

- `runserver.sh` — full stack bring-up. Reads `.env` for `HF_TOKEN`.
- `main_models.yaml` — mlx-serve model registry.
- `openwebui_config.json` — seeded into `open-webui-data/config.json` on each start.
- `do_backup.py` — backs up `open-webui-data/` before start.

## Logs

`logs/mlx_vlm.log`, `logs/task_model.log`, `logs/main_model.log`, `logs/compose.log`.
