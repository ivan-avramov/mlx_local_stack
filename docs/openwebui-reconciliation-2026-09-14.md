# OpenWebUI reconciliation — 2026-09-14

**C94 follow-up:** the operator subsequently narrowed OpenWebUI to the four-entry C menu in `openwebui.models`, with the task entry hidden from the normal selector. The eight-entry inventory below is the historical C93 checkpoint. [Current verification](openwebui-c-menu-2026-09-14.json).

**C93 complete.** The existing YAML generator was correct about which models belonged in its OpenWebUI registration file, but startup left the main connection's model allowlist empty. OpenWebUI consequently discovered all router registrations, including two candidates and three router-only models. The screenshot's 13 entries were the 12 router models plus the task model; the intended client inventory is seven main models plus that task model.

The earlier C90 generated-file audit did not establish deployment correctness. Initial live inspection here found eight saved model configurations with matching parameters, but unrestricted discovery. The legacy seed also contained obsolete default/pinned models; the live global selection was unset.

## Repair

`python -m configgen generate` now produces both `openwebui-init/models_config.json` and `model_settings.json`. The latter binds the former by SHA256 and declares main/task allowlists, excluded model IDs, default selection and order. `agent_defaults.openwebui` in the registry explicitly selects `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. Other main models retain registry order; the task model follows them. The generator now carries `enable_thinking` and declared `reasoning_effort` explicitly. KV format, MTP and cache allocation continue to be applied by the server.

Startup and the manual publisher share one reconciler. It reads saved native provider defaults and custom models through the installed API's separate `/models/base` and `/models/export` routes. It preserves existing access grants and unrelated connections/custom registrations, reconciles the two stack connections and their allowlists, updates model parameters/default selection/task routing, and verifies saved state plus the refreshed combined model list. Optional null metadata fields are normalized without discarding non-null differences. Global model parameters are cleared so they cannot supersede registry defaults silently.

Generated registrations carry an ownership marker. Saved excluded models, or previously managed registrations removed from the registry, cause a clear stale-model error. The manual publisher can prune those exact registrations after a dry-run, with a required private backup. Startup does not silently delete them. Backup files refuse overwrite and use mode0600. Model files and chats are unaffected.

The legacy UI seed no longer contains competing model defaults. `runserver.sh` checks generated files and obtains the task model from them. Authentication/configuration failures are no longer treated as successful initialization; authentication responses are not printed. The shared API client has bounded requests and treats HTML fallback responses and unsuccessful readback as failures.

## Verification

- **63 CPU tests pass**, including candidate exclusion, explicit thinking parameters, mismatched generated-file rejection, duplicate/legacy connections, stale ownership, scoped pruning/backups, retained access grants, ignored successful writes, visible-list leakage and repeat-run idempotence. New behavior was exercised with failing tests before its fixes. Generator drift check and shell syntax check pass.
- The stack was stopped externally during implementation. Only OpenWebUI was temporarily started from the cached image `sha256:018046a13da78bac17fe677c7f86b028cc4e931487cef9cf896cafc3d76aadc6`. No model server was started. At this verification startup the saved model table was empty; reconciliation created the eight intended entries.
- The first live attempt exposed obsolete publisher API assumptions: the old list route returned HTML, and `/models/export` alone omitted native provider defaults. Verification rejected these attempts. The final code reads both saved-model categories, and the corrected repeated apply made **zero changes** and passed all readback checks.
- Live combined inventory is exactly **eight** entries. All saved model parameters, active flags, default/pinned selection, ordering, allowlists and task-model routes match the generated policy. The actual startup model-reconciliation function and its task-routing assertion also pass against this instance.
- The installed OpenWebUI payload-transform functions were executed on all eight generated parameter sets. They preserved the outgoing parameters, including declared thinking settings, while preserving explicit request overrides. Payload source SHA256: `db0f6c53f240fab6709f7e273d0945aa507e8a8d1b811e197e91c4b4a8809694`.
- **Zero inference calls.** This is configuration, API reconciliation and payload-transform verification; no new model-quality or full chat-generation claim. Existing per-chat settings and explicitly selected profile filters remain user overrides.

OpenWebUI was stopped again after verification, restoring the stopped service state. Corrected settings persist in its database for the next startup. Private pre-change snapshots and readback are under `$STACK_WORKDIR/qualification/c93-owui`; [sanitized verification](openwebui-reconciliation-2026-09-14.json). No fork change, Git push or HF publication occurred in this repair.

See [configuration and publisher usage](../openwebui-init/README.md). Models still declared `presentation.role: main`, including `gemma-4-31B-it-qat-6bit` and `gemma-4-26B-A4B-it-OptiQ-4bit`, remain visible intentionally.
