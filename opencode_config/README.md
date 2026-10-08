# OpenCode config for mlx_local_stack

`opencode.json` is generated from [main_models.yaml](../main_models.yaml) in the native OpenCode v2 schema (verified on 2.0.20). Change the registry, then run `uv run python -m configgen generate`; `uv run python -m configgen check` checks all generated carriers. Keep personal additions in your installed config rather than in generated files.

`providers.mlx-local` uses `package: "@opencode/ai/providers/openai-compatible"` and `settings.baseURL: "http://localhost:8000/v1"`. It advertises the seven registry entries with `presentation.role: main`; candidates are available only in benchmark carriers. The default is `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; `Qwen3.8-27B-mlx-uniform-4bit` is the second approved pick. See the root README for current ranking and evidence. Switching main models can reload the router's single resident model.

Main models declare `capabilities.tools: true`, `capabilities.output: ["text"]`, and `capabilities.input: ["text", "image"]` for vision models or `["text"]` for text-only models. `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is text-only. The separate `providers.mlx-task` points to `http://localhost:8092/v1`, declares text-only input/output and `tools: false`, and supplies `mlx-community/Qwen2.5-1.5B-Instruct-4bit` through `agents.title.model`. This replaces v1's `small_model`; the v1 `reasoning`, `tool_call`, `attachment`, `modalities`, and `options` keys are absent.

## Install and select

1. Start the stack when you intend to use these clients; do not interrupt an active benchmark.
2. Merge `opencode.json` into your project config or `~/.config/opencode/opencode.json` (or `.jsonc`). **Migration warning:** a v1-shaped personal `provider.*.options` block in `~/.config/opencode/opencode.json` or `~/.config/opencode/opencode.jsonc` silently loses every sampling field on v2 (M59 FACTS row 1d). Migrate it to `providers.*.models.*.body`.
3. The local API key is `not-needed`; register that placeholder if your client requires provider authentication.
4. Restart OpenCode after changing its config. Select a model with `/models` or `--model mlx-local/<full-registry-name>`.

The task-model reference contains two slashes: `mlx-task/mlx-community/Qwen2.5-1.5B-Instruct-4bit`. The first component is the provider; the rest is the exact model ID.

## Limits and sampling

| Field | Registry mapping |
|---|---|
| `limit.context` | Full context window |
| `limit.input` | Context window minus output ceiling |
| `limit.output` | Output ceiling |
| `body` | `sampling_openai` plus `sampling_extra`: family-supported sampling and thinking parameters |
| `compatibility.maxTokensField` | `"max_tokens"`, the token-cap field honored by the serving fork |

For both approved picks, these limits are 262144 context, 159744 input, and 102400 output tokens. The four-carriers rule now lands in each model's `body`: temperature, top_p, max_tokens, top_k, min_p, presence_penalty, enable_thinking, and thinking_budget where declared and supported by the family. v2 sends this body overlay; putting sampling in v1 `options` silently loses it. An explicit `body.max_tokens` preserves the registry cap instead of relying on v2's room-based calculated cap. Task-model sampling is emitted only when the registry declares it.

Both approved picks carry `top_p: 0.95`, `top_k: 20`, `min_p: 0`, `presence_penalty: 0`, `thinking_budget: 81920`, and `enable_thinking: true`. Their temperatures are 0.5 and 0.6 respectively. The registry's `reasoning_effort: medium` applies when the client omits that field. Other models retain their own registry settings; family filtering does not invent unsupported sampling keys.

`compaction.auto: true` is deliberate for the daily driver: a human session can summarize context when it fills. The v2 benchmark carrier has compaction **OFF** so context overflow is a recorded generation outcome instead of an invisible summary. The retained `benchmark/opencode_bench.json` remains byte-identical v1 for the pinned 1.18 probe; the v2 carrier is `benchmark/opencode_bench_v2.json`. KV format, MTP configuration, cache retirement, and full-cap allocation belong to the server registry.

`plugins` removes `opencode.provider.vllm`, `opencode.provider.ollama`, `opencode.provider.lmstudio`, and `opencode.config.compatibility`. This disables provider discovery/polling. Removing `opencode.config.compatibility` stops BOTH `~/.claude/skills` and `~/.agents/skills` from loading in daily use, broader than the v1 `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` policy. To re-enable compatibility discovery, delete `-opencode.config.compatibility` from `plugins`. No external plugin is loaded: the superpowers plugin was uninstalled 2026-10-08 (operator), so the daily client now matches the bench carrier's plugin set. `update: "disable"` and `share: "disabled"` are explicit; the client imposes no permission denies.

Registration-only clients (VS Code and Zed) are unchanged.

## Config validation evidence

The CPU-only test in `configgen/tests/test_opencode.py` runs the brew binary only on 2.0.20, using redirected HOME/XDG/TMPDIR, an isolated git directory, disabled project config/model fetching, stdin DEVNULL, and `api GET /api/config --standalone`. All eight models (seven main plus task), every `body`, and the plugins list survive loading; model references are normalized into provider/model objects. No generation request is made.

The unknown-key control showed that 2.0.20 **strips** unknown top-level keys while retaining the document, unlike v1's strict rejection. A second control with malformed JSON silently drops the entire document with rc 0. A successful command exit alone therefore does not prove the config loaded: inspect the returned document and model bodies. Generated-file provenance stays in this README.

The P1a smoke on OpenCode 1.18.15 (2026-08-13) verified requests reaching the router and forwarding of `max_tokens`, `thinking_budget`, and `enable_thinking`; see [campaign results](../docs/campaign-results.md). Those measurements are historical and are not v2 server validation.
