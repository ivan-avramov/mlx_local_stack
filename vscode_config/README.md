# VS Code (GitHub Copilot) config for the mlx_local_stack

Points VS Code's built-in agent — **GitHub Copilot Agent Mode** — at this stack's local models via Copilot's "bring your own key" (BYOK) **Custom Endpoint** provider.

- **mlx-serve** — multi-model server on `http://localhost:8000/v1` (gemma-4 family + Qwen3.6). Loads **one model at a time**, swaps on demand (~10s cold start).
- BYOK requests are billed by your provider (here: free/local), **not** against your Copilot quota. Code completions stay on Copilot's own infra regardless.

`chatLanguageModels.json` is the config Copilot's Custom Endpoint provider reads.

## ⚠️ Read first: Insiders vs Stable

The rich, per-model **Custom Endpoint** provider + `chatLanguageModels.json` format here is currently **VS Code Insiders only**. It *replaces* the now-deprecated "OpenAI Compatible" provider.

- **VS Code Insiders** → use this folder as-is (Custom Endpoint + `chatLanguageModels.json`). ✅ recommended.
- **VS Code Stable** → the Custom Endpoint provider isn't available yet. Options:
  1. Use the deprecated `github.copilot.chat.customOAIModels` setting (works, but fewer per-model controls — no `thinking`, limited token fields).
  2. Install the community extension **"OAI Compatible Provider for Copilot"** (johnny-zhao) from the Marketplace.
  3. Switch to VS Code Insiders.

  Check **Code → About** (or `code --version` vs `code-insiders --version`) to confirm which you're on before configuring.

## Install (Insiders)

1. Start the stack: `./runserver.sh` (from the repo root); wait for both servers.
2. Command Palette → **Chat: Manage Language Models** (or the gear/“Manage Models” in the model picker).
3. **Add Models** → **Custom Endpoint** → API type **Chat Completions**. VS Code opens `chatLanguageModels.json`.
4. Paste the `models` from this folder's `chatLanguageModels.json` (or merge the whole array). Save.
5. API key: mlx-serve ignores it, but Copilot wants *a* value — `not-needed` is fine (it may be moved to your OS keychain depending on version).
6. Open Copilot Chat, switch to **Agent** mode, and pick one of the `mlx-local` models.

## How this differs from the aider and Zed configs

| | aider | Zed | VS Code Copilot |
|---|---|---|---|
| Token field meaning | `max_input_tokens` = prompt budget | `max_tokens` = **full window** | `maxInputTokens` = **prompt budget** |
| → numbers used here | 98304 / 229376 / 180224 | full-window (131072 / 262144) | **match aider** (98304 / 229376 / 180224) |
| Thinking control | `enable_thinking` + `thinking_budget` (full) | `interleaved_reasoning` only | `thinking: true` flag — **but no `thinking_budget`** |
| Weak/summary model | pinned to :8092 task model | per-role keys → :8092 | **no per-role model** — Copilot uses your picked model for everything |
| Edit mechanism | text diffs | tool calls | tool calls |

Three things to internalize:

1. **Use the aider numbers, not the Zed numbers.** `maxInputTokens` is the prompt budget, so it's set to `window − output` (98304 for 131k-window models, 229376 for 256k, 180224 for Qwen). That keeps `prompt + output ≤ window`, so mlx-serve never has to clamp.
2. **Qwen thinking is bounded, not budgeted.** `thinking: true` lets Copilot parse/display the `<think>` reasoning, but Copilot can't forward `thinking_budget` to the server — thinking is capped only by `maxOutputTokens` (81920). Same practical limit as Zed.
3. **No "weak model" role.** Unlike aider/Zed, Copilot doesn't expose a separate summary/commit-message model, so the always-on :8092 task model has no role to fill here. Copilot (and its built-in sub-agents) use the model you select. The `chatLanguageModels.json` here therefore only lists the :8000 agent models.

## Agent-mode requirements & gotchas

- **Tool calling + streaming are required for Agent mode.** A model without tool calling won't even appear in the agent model picker. All our models are tool-capable (mlx-serve auto-infers the parser from the chat template), so every entry sets `toolCalling: true`.
- **No 2048-truncation trap here.** Because each entry sets `maxOutputTokens`, Copilot sends a real cap — mlx-serve won't fall back to its 2048 default (the bug that truncated Qwen in aider).
- **Model-ID collision** ([vscode#318968](https://github.com/microsoft/vscode/issues/318968)): a custom model whose `id` matches a built-in Copilot name gets hidden from the picker (`toolCalling:false`) or fails with 502 (`toolCalling:true`). Ours don't collide — just never name one `gpt-5.5`, `claude-…`, etc.
- **Tool-call payload shape:** if a model's `tool_calls` output doesn't match Copilot's expected shape, the chat can hang after the first turn. Verify one agent edit completes before relying on a model.
- **Single-model swap:** switching the agent between two :8000 models triggers a ~10s reload (mlx-serve serves one model at a time).
- **Sign-in / org policy:** BYOK historically required signing into Copilot; recent VS Code relaxed this. Copilot Business/Enterprise can disable BYOK by policy — if the provider doesn't appear, check your org settings.
- **`apiType`:** `chat-completions` matches mlx-serve's OpenAI-compatible endpoint. Selecting "Chat Completions" in the Add-Models UI sets this for you.
