# opencode config for the mlx_local_stack

Points [opencode](https://opencode.ai) (the SST terminal agent) at this stack's local models via a native OpenAI-compatible provider.

- **mlx-serve** — multi-model server on `http://localhost:8000/v1` (gemma-4 family + Qwen3.6). Loads **one model at a time**, swaps on demand (~10s cold start).
- **task model** — standalone, always-on server on `http://localhost:8092/v1` (`Qwen2.5-1.5B-Instruct-4bit`), used as opencode's `small_model` (lightweight tasks like title generation).

## ⚠️ Read first: known open bug

[opencode#5674](https://github.com/anomalyco/opencode/issues/5674) reports that in some recent versions the bundled `@ai-sdk/openai-compatible` provider **doesn't forward the `options` block (including `baseURL`) to the API** — the reporter calls custom OpenAI-compatible endpoints "currently unusable," and the fix PR was still open at time of writing. Many setups work fine, so it's version-dependent.

**Verify before investing:** after configuring, confirm requests actually reach `localhost:8000` (watch `logs/mlx_vlm.log` for a request when you send a message). If they don't, this bug is the likely cause — check your opencode version against the issue/PR, upgrade, or front the stack with a gateway (e.g. litellm) as a fallback.

## Install

1. Start the stack: `./runserver.sh` (from the repo root); wait for both servers.
2. Copy `opencode.json` to your project root (per-project) or `~/.config/opencode/opencode.json` (global). Merge into an existing config if you have one.
3. `apiKey` is `not-needed` (mlx-serve ignores it). Depending on version you may also need `opencode auth login` for the `mlx-local` / `mlx-task` provider ids — use a dummy key.
4. **Restart opencode** after editing config.
5. The default model is `mlx-local/gemma-4-31b-6-128`. Switch with `--model mlx-local/<id>` or the `/models` command.

## Param mapping (and how it differs from the other editors)

| Concern | This config | Note |
|---|---|---|
| Context window | `limit.context` = **window − output** (98304 / 229376 / 180224) | opencode treats `context` as the prompt budget; sizing it this way keeps `prompt + output ≤ window` so mlx-serve never clamps. Same numbers as the aider config (NOT Zed's full-window). |
| Output cap | `limit.output` (32768 gemmas / 81920 Qwen) | |
| Weak model | **`small_model`** → the :8092 task model | The real weak-role analog (titles/summaries) — pinning to the always-on :8092 server avoids swapping the agent model. opencode is the only one of the four with a clean weak-model setting like aider's. |
| Tool calls | `tool_call: true` on all agent models | opencode is a tool-driven agent; all your models are tool-capable (mlx-serve auto-infers the parser from the chat template). |
| Reasoning | `reasoning: true` on **all six** | gemma-4 *and* Qwen3.6 are reasoning families in the fork (`generation.py` thinking-format registry covers `gemma4`/`gemma4_unified` as well as Qwen). The flag tells opencode to parse the `reasoning` field instead of dumping `<think>` into content — it does **not** force the model to think (that's the template / `enable_thinking`), so it won't slow gemma down. Qwen thinks by default; gemma's thinking is lighter/prompt-driven. |
| Vision | `attachment: true` on all six | All are VLMs (`/v1/models` reports `vision`; Qwen3.6 is natively multimodal). `attachment` is the models.dev field for image/file input. Task model is text-only → `false`. |
| Thinking control | Qwen `options: { enable_thinking, thinking_budget, max_tokens }` | **Best-effort, verify.** opencode's per-model `options` *may* forward as body params (which mlx-serve reads) — but per #5674 forwarding is flaky and the AI SDK may nest them where mlx-serve won't see flat fields. If they don't land, Qwen still thinks by default, bounded by `limit.output` (same as Zed/VS Code). The `max_tokens` here is insurance against the 2048-default truncation trap (the aider bug) — *if* options forward. |

## Gotchas

- **#5674 (above)** is the big one — verify the endpoint is actually hit.
- **Double-slash model id:** `small_model` is `mlx-task/mlx-community/Qwen2.5-1.5B-Instruct-4bit` — opencode must split on the *first* `/` (provider `mlx-task`, model `mlx-community/…`). The model key must match exactly what the :8092 server accepts. If it doesn't resolve, this is why.
- **[opencode#16154](https://github.com/anomalyco/opencode/issues/16154):** the openai-compatible path can auto-inject reasoning-control params (gpt-5-style) that don't fit other models. mlx-serve ignores unknown params, so likely harmless, but watch for request errors after enabling `reasoning: true`.
- **2048-truncation trap:** if Qwen truncates mid-thought, opencode isn't sending a real `max_tokens` (mlx-serve fell back to its 2048 default). The `options.max_tokens` here is meant to prevent it — but only works if opencode forwards model `options` (see #5674).
- **Single-model swap:** switching the agent between two :8000 models reloads (~10s). `small_model` on :8092 sidesteps it for titles/summaries.
- **models.dev:** opencode normally pulls capabilities from models.dev, but your custom model IDs aren't in that DB, so all capability fields are specified manually here. (A `use_models_dev` option exists but won't help for custom IDs.)
