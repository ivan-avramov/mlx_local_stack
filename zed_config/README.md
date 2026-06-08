# Zed config for the mlx_local_stack

Configures the [Zed](https://zed.dev) agent + assistant to use this stack's local models:

- **mlx-serve** — multi-model server on `http://localhost:8000/v1` (gemma-4 family + Qwen3.6). Loads **one model at a time**, swaps on demand (~10s cold start).
- **task model** — standalone, always-on server on `http://localhost:8092/v1` (`Qwen2.5-1.5B-Instruct-4bit`), used for the lightweight agent roles.

`settings.snippet.jsonc` holds the keys to **merge** into your Zed settings — it is not a standalone file.

## Install

1. Start the stack: `./runserver.sh` (from the repo root); wait for both servers.
2. Open Zed settings: `cmd-,` → **Edit in settings.json**, or edit `~/.config/zed/settings.json` directly.
3. **Merge** the `language_models` and `agent` keys from `settings.snippet.jsonc` into your settings (don't replace the whole file — deep-merge these two top-level keys).
4. **Set an API key for each provider — REQUIRED, or the models stay hidden.** Zed treats an `openai_compatible` provider as "not configured" until a key is registered, and silently hides its models from the picker (no error shown). mlx-serve ignores the key's value, but Zed needs *a* non-empty one. Add it via the Agent panel's configuration view: Command Palette → **`agent: open configuration`** (or the gear icon in the Agent panel) → find **`mlx-local`** → enter any string, e.g. `not-needed` → confirm. Repeat for **`mlx-task`**. (Confirmed working with `not-needed`.)
5. In the Agent panel, pick a model under the **mlx-local** provider (or just use the configured default).

> **Symptom if you skip step 4:** the model picker shows only the frontier/hosted models, not the `mlx-local` ones. That's the missing key, not a config error — the `available_models` list won't surface until a key is set.

## Model roles

Zed runs different features on different models — pinned here to avoid swapping the agent model out of mlx-serve's single GPU slot:

| Role (`agent.*`) | Model | Why |
|---|---|---|
| `default_model` | mlx-local / `gemma-4-31b-6-128` | Primary agent model. |
| `inline_assistant_model` | mlx-local / `gemma-4-31b-6-128` | Same as primary → no swap between agent and inline edits. |
| `subagent_model` | mlx-local / `gemma-4-31b-6-128` | Same model → subagents don't trigger a swap. |
| `commit_message_model` | mlx-task / `Qwen2.5-1.5B` | Light role on the always-on :8092 server → never evicts the agent model. |
| `thread_summary_model` | mlx-task / `Qwen2.5-1.5B` | Same. |

Switch `default_model` to `gemma-4-31b-4-256` for 2× context, or `Qwen3.6-27B-UD-MLX-6bit` for reasoning-heavy work.

## How this differs from the aider config

| | aider | Zed |
|---|---|---|
| `max_tokens` meaning | n/a (aider uses `max_input_tokens` = window − output) | **full context window** (Zed reserves output itself) |
| Editing mechanism | text diffs (no tools needed) | **tool calls** (the agent edits via function calls) |
| Custom request params | `extra_params` forwards anything (`enable_thinking`, `thinking_budget`, per-model `api_base`) | **not supported** — can't send thinking knobs or per-model base URLs |
| Default model | Qwen3.6 (fine — no tools used) | a gemma (snappier tool-calling); Qwen3.6 also works |

## Notes & caveats

- **All models are tool-capable.** mlx-serve auto-infers the tool parser from each model's chat template, so every entry is `tools: true`. (The `tool_call_parser: gemma4` lines in `main_models.yaml` are legacy overrides, not capability gates.)
- **No `max_tokens` truncation trap here.** Because each entry sets `max_output_tokens` / `max_completion_tokens`, Zed sends a real cap and mlx-serve won't fall back to its 2048 default (the bug that truncated Qwen in aider).
- **Thinking is bounded, not budgeted.** Zed can't send `thinking_budget`, so Qwen3.6 thinks until it naturally stops, capped only by `max_completion_tokens` (81920). `interleaved_reasoning: true` keeps the `<think>` content out of the answer body.
- **Qwen3.6 in the agent:** tool support is real, but its thinking + tool-call interaction can stall or loop in some clients. Verify one agent edit completes before relying on it; prefer a gemma for routine agent work.
- **`agent.model_parameters`** can set `temperature`/`top_p` per provider+model if you want, but it cannot carry the mlx thinking knobs.
- **`capabilities` must be complete.** Zed's deserializer requires every field in the `capabilities` object — a partial object fails with e.g. `missing field 'parallel_tool_calls'`. Each entry here sets all four: `tools`, `images`, `parallel_tool_calls`, `prompt_cache_key`. If your Zed version complains about a further missing field, add it to every entry. Older builds used flat `supports_tools` / `supports_images` instead of the nested object.
- **`parallel_tool_calls: true`** on the agent models — verified safe: mlx-serve's `process_tool_calls` (`re.findall` over every `<tool_call>` block) returns *all* tool calls the model emits in one turn, so the agent can fan out (e.g. read several files at once). If the model emits only one, you still get one — no downside. The task model keeps `false` (it has no tools). `prompt_cache_key: false` because mlx_vlm does its own server-side prefix caching, not client-keyed caching.
