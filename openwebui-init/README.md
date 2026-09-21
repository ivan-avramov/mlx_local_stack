# OpenWebUI configuration

`main_models.yaml` is the source of truth. From the stack root:

```sh
uv run python -m configgen generate
uv run python -m configgen check
```

The existing generator writes:

- `models_config.json`: registered main/task models, capabilities and explicit sampling/thinking parameters.
- `model_settings.json`: main-model allowlist, excluded candidate/router-only IDs, task model, default/pinned selection and ordering. A hash binds it to the model file.

`openwebui.models` declares the ordered four-entry C menu independently of other clients. `agent_defaults.openwebui` chooses its default. The task entry remains active for internal routing but carries `meta.hidden: true`, so the normal chat selector omits it. Web Search and Code Interpreter are enabled and selected by default on every visible chat model, from registry presentation capabilities. KV precision, MTP and cache allocation remain server-side registry settings.

`runserver.sh` checks generated files before launch and reads the task model from those settings. `init.py` and `publish_models.py` share `reconcile_models.py`. They reconcile both connections, model defaults, global default selection and task routing, then verify saved state and the refreshed combined model list. An empty router allowlist is not used: it exposes benchmark-only registrations.

There is no config-file seed (the legacy `openwebui_config.json` was retired in C100, 2026-09-21: its nested rows never reached OWUI's flat config table). `init.py` and the compose environment own every setting. Existing chats and explicit user/chat overrides can still select different parameters; profile filters are intentional overrides, not registry defaults.

## Update a running instance

Set `OWUI_URL`, `OWUI_ADMIN_EMAIL` and `OWUI_ADMIN_PASSWORD` in your local environment. The publisher checks generated files against the registry when run from this checkout.

```sh
uv run python openwebui-init/publish_models.py
uv run python openwebui-init/publish_models.py --apply \
  --backup-dir "$STACK_WORKDIR/openwebui-backups"
```

Dry-run is the default. Apply saves a private, non-overwriting pre-change snapshot; it may contain connection credentials. Do not commit it. Existing access grants and unrelated provider connections/custom models are preserved. Global model parameters are cleared so they cannot silently override per-model registry defaults.

Previously managed models removed from the registry, and saved candidate/router-only registrations, stop reconciliation with an explicit stale-model error. Review the dry-run and add `--prune` to remove only those registrations, with the required backup. This does not delete model files or chats. Startup fails on unresolved stale entries rather than deleting them silently.

The current OpenWebUI API splits saved provider defaults (`/models/base`) from custom models (`/models/export`). Both are inspected. HTTP errors, HTML fallback responses and successful writes that fail readback are errors. [Repair and verification](../docs/openwebui-reconciliation-2026-09-14.md).
