# aider config for the mlx_local_stack

Drop-in [aider](https://aider.chat) configuration for driving this stack's models:

- **mlx-serve** — the multi-model server on `http://localhost:8000/v1` (gemma-4 family + Qwen3.6). Loads **one model at a time** and swaps on demand (~10s cold start per switch).
- **task model** — a standalone, always-on server on `http://localhost:8092/v1` (`Qwen2.5-1.5B-Instruct-4bit`), used here as aider's "weak" model.

The files are checked in **without** the leading dot so they're visible in the repo. aider looks for them **dot-prefixed** in your home directory (or git repo root, or cwd), so installing means copying them with a `.` in front.

## Files

| Repo file | Install as | Purpose |
|---|---|---|
| `aider.model.metadata.json` | `~/.aider.model.metadata.json` | Context windows, costs (0 — local/free), and capability flags (`supports_vision`, `supports_pdf_input`, …) for the local models. aider/litellm don't know these custom model names otherwise. |
| `aider.model.settings.yml` | `~/.aider.model.settings.yml` | Per-model behavior: `edit_format`, pinned weak model, thinking knobs, and the `:8092` route for the weak model. |
| `aider.conf.yml` | `~/.aider.conf.yml` | Global defaults: the default model and the mlx-serve endpoint. |

## Install

```sh
cp aider.model.metadata.json ~/.aider.model.metadata.json
cp aider.model.settings.yml  ~/.aider.model.settings.yml
cp aider.conf.yml            ~/.aider.conf.yml
```

(Alternatively, copy them into a project's git root for per-project config, or point aider at them explicitly with `--model-metadata-file` / `--model-settings-file` / `--config`.)

For the **Opus** cloud fallback, also put your Anthropic key in the environment:

```sh
export ANTHROPIC_API_KEY=sk-ant-...   # or add it to ~/.env
```

## Use

1. Start the stack: `./runserver.sh` (from the repo root). Wait until both servers are up.
2. From your project directory: `aider`
3. It launches on the default model (`openai/Qwen3.6-27B-UD-MLX-6bit`). Switch any time:
   - `/model openai/gemma-4-31b-6-128` — highest-quality gemma
   - `/model openai/gemma-4-26b-moe-4-256` — fastest (4-bit MoE)
   - `/model anthropic/claude-opus-4-8` — cloud fallback (no local swap)
   - `/models <text>` — search what aider can switch to

`/model` changes **only** the main model; the weak model stays pinned. Tab-completion lists the full litellm catalog (there's no way to restrict it) — your models appear under the `openai/` prefix.

## How the three model roles map here

aider uses up to three model slots:

- **main** — your primary. In **architect mode** the main model is also the *architect*.
- **editor** — only used in architect mode, to turn the architect's proposal into file edits. Left **unset** here, so the main model fills it too → one `/model` switch moves both roles.
- **weak** — commit messages, chat summaries, titles. **Pinned** to the task model on `:8092`, so these never evict your primary from mlx-serve's single GPU slot.

Architect mode is **off by default** (it runs two generations per turn). Turn it on for a session with `/architect`, or uncomment `architect: true` in `aider.conf.yml`.

## Editing & tuning

- **Edit format** is `diff` for all models. If you see "failed to apply edit," change that model's `edit_format` in the settings file to `whole` (rewrites whole files; most reliable on smaller local models) or `diff-fenced`.
- **Thinking** (Qwen3.6) is controlled via `extra_params: {enable_thinking, thinking_budget}` in the settings file — these pass straight to mlx_vlm. Do **not** rely on `reasoning_effort` / aider's effort sliders; mlx-serve ignores them.
- **Token budgets** are set so `max_input_tokens + max_output_tokens` stays within each model's KV window (from `main_models.yaml`), so the server never has to clamp generation. See the main repo discussion if you change these.

## Why two model files (not one)?

They feed two different internal structures and can't be merged:

- `aider.model.metadata.json` → litellm **`ModelInfo`**: context window, costs, `supports_*` flags ("what the model *is*").
- `aider.model.settings.yml` → aider **`ModelSettings`**: `edit_format`, weak/editor model, `extra_params` ("how aider *uses* it").

`extra_params` only works in the YAML; context/cost/capability flags only work in the JSON. Opus needs **neither** file (litellm ships its info) — it appears here only as a behavior entry in the YAML so it inherits the pinned weak model and `diff` format.

## First-run sanity checks

Two aider behaviors worth confirming once (they're assumptions about aider, not the stack):

1. **Weak model routes to :8092** — write a change and let aider make a commit; confirm `logs/task_model.log` shows the request (not `logs/main_model.log`).
2. **Editor follows `/model`** — in architect mode, check aider's startup model summary shows the editor tracking your selected main model.
