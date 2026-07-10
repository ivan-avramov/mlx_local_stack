# Config generator — single source of truth → per-agent configs

**Date:** 2026-07-09. **Status:** design, approved (design §1–§3 + max_kv rule signed off; spec pending user review → writing-plans).
Depends on / supersedes the hand-maintenance model documented in `AGENTS.md` ("Client/agent integrations").

## Goal & context

Today the same per-model config is duplicated across **6 carriers** — `main_models.yaml` (router),
`openwebui-init/models_config.json` (OWUI), `opencode_config/opencode.json`, `aider_config/*`,
`vscode_config/chatLanguageModels.json`, `zed_config/settings.snippet.jsonc` — and kept in sync by
hand (the AGENTS.md "update ALL carriers" ritual). This has repeatedly drifted: `Qwen3.6-27B-OptiQ-4bit`
missing web_search in OWUI, aider's default pointing at a cut model, stale 404 friendly-name aliases
(`gemma-4-31b-6-128`), OWUI/opencode disagreeing on the input-limit convention.

**Goal:** make `main_models.yaml` the single source of truth and **generate** every client config from
it. One emitter per target encodes that format's quirks once; adding a future agent = add one emitter
("output sink"). Editing a model = edit the source + regenerate. Kills the drift-tax bug class.

## Non-goals
- Not generating `main_models.yaml` itself (it IS the source; the router reads it directly).
- Not changing KV pre-allocation behavior — see the **max_kv** section + the separate handoff
  `docs/kv-prealloc-handover.md`. This spec only sets `max_kv_cache_size = context` (the cap).
- Not touching bench scaffolding (`bench/model_params.py`, `bfcl_shim`) — eval infra, out of scope.

## §1 — Source schema (`main_models.yaml`, enriched)

`main_models.yaml` stays the router config and the source; mlx-serve ignores keys it doesn't know, so
presentation metadata rides along free. Structural fields (`hf_path`, `kv_bits`, `kv_quant_scheme`,
`max_kv_cache_size`, `draft_kind`, `prefill_step_size`, …) and `generation_defaults` stay as-is. Add a
per-model `presentation:` block + a top-level `agent_defaults:` map:

```yaml
agent_defaults:                       # per-agent default model (agents that have the concept)
  opencode: Ornith-1.0-35B-mlx-uniform-4bit
  aider:    Ornith-1.0-35B-mlx-uniform-4bit

models:
  - name: Ornith-1.0-35B-mlx-uniform-4bit
    hf_path: caslca/Ornith-1.0-35B-mlx-uniform-4bit
    max_kv_cache_size: 262144         # == presentation.context (the cap; see max_kv section)
    kv_bits: 0
    draft_kind: suffix
    generation_defaults: { temperature: 0.4, top_p: 0.95, top_k: 20, min_p: 0.0,
                           presence_penalty: 0.0, max_tokens: 102400,
                           thinking_budget: 81920, enable_thinking: true }
    presentation:                     # consumed by the generator; ignored by mlx-serve
      role: main                      # main | task
      family: qwen                    # qwen | gemma → penalty style + edit_format default
      display_name: "Ornith-1.0-35B (256K agentic, MoE)"
      context: 262144                 # total window (== max_kv_cache_size)
      output: 102400                  # == generation_defaults.max_tokens
      capabilities: [tools, vision, thinking, web_search, code_interpreter]
```

Rules the generator enforces:
- **`generation_defaults` is the sole sampling source.** Emitters transform it per format: opencode
  writes it directly (`repetition_penalty`), aider puts non-OpenAI knobs in `extra_body`, OWUI uses the
  Ollama alias `repeat_penalty` + `meta.capabilities`/`defaultFeatureIds`, vscode/zed **drop sampling**
  (their formats can't carry it — registration-only).
- **`family`** drives arch quirks: `gemma` → `repetition_penalty` (+ suffix stays off, stateful penalty)
  and `edit_format: whole` default; `qwen` → `presence_penalty`/`min_p` and `edit_format: diff` default.
  Optional per-model `presentation.edit_format` overrides.
- **`role: task`** routes the model to the :8092 provider + the weak/small-model slots (opencode
  `small_model`, aider `weak_model_name`), never as a primary chat model.
- **The M5-local `hf_path` override never leaks** — client configs use model *names/ids*, not `hf_path`.

## §2 — Generator architecture

A small Python package (matches the existing `openwebui-init` tooling), the single writer of all client
configs:

```
configgen/
  source.py        # load + VALIDATE main_models.yaml → typed models (fail-loud: missing presentation
                   #   field, unknown family/role, agent_defaults→missing id, duplicate names)
  emitters/
    opencode.py    # provider.mlx-local.models dict + mlx-task provider; sampling in options; model: from agent_defaults
    aider.py       # 3 files: settings.yml (extra_body, edit_format, weak_model→:8092), metadata.json, conf.yml (default)
    vscode.py      # chatLanguageModels.json (registration-only, no sampling)
    zed.py         # settings.snippet.jsonc (registration-only; max_tokens = full window)
    owui.py        # models_config.json (repeat_penalty alias, meta.capabilities + defaultFeatureIds, params)
  __main__.py      # `generate` (write all) | `check` (regen in-memory, diff vs committed → nonzero on drift)
```

- **Committed outputs + `check` drift guard** (decision §Q1=a): generated files live in git (reviewable
  diffs); `runserver.sh`/`preflight` run `configgen check` and fail on drift.
- **Each generated file carries a header:** `# GENERATED by configgen from main_models.yaml — do not edit by hand.`
- **Runs on M2** (committed source) → commit outputs → M5 pulls. `publish_models.py` stays as the OWUI
  *pusher* downstream of the generated `models_config.json`.
- **Adding an agent = add one emitter module + register it.**

## §3 — Per-target emitter quirks (encoded once each)

| target | file(s) | sampling carried | input-limit convention | default model |
|---|---|---|---|---|
| opencode | `opencode.json` | yes (options, `repetition_penalty`) | `limit.context` = context, `limit.output` = output | `model:` from `agent_defaults` |
| aider | `settings.yml` + `metadata.json` + `conf.yml` | yes (`extra_body` for non-OpenAI knobs) | `max_input_tokens` = context − output | `conf.yml model:` |
| vscode | `chatLanguageModels.json` | **no** | `maxInputTokens` = context − output, `maxOutputTokens` = output | — (list) |
| zed | `settings.snippet.jsonc` | **no** | `max_tokens` = **full context**, `max_output_tokens` = output | — (list) |
| owui | `models_config.json` | yes (`repeat_penalty` alias) + `meta.capabilities`/`defaultFeatureIds` | n/a | — (user picks) |

## §4 — Keep-list + params (source content for first generation)

Five models (campaign winners + references + task):

| model | family | role | context | max_tokens | thinking_budget | notes |
|---|---|---|---|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` | qwen | main | 262144 | 102400 | 81920 | pick; fp16 KV; suffix; temp 0.4 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | qwen | main | 262144 | 102400 | 81920 | alt; tq-4bit KV; suffix; temp 0.3 |
| `gemma-4-26B-A4B-it-OptiQ-4bit` | gemma | main | 262144 | **49152** | **32768** | MoE ref; temp 0.7; 32K thinking *ceiling* (max_tokens bumped so 0.8× clamp doesn't bite) |
| `gemma-4-31B-it-qat-6bit` | gemma | main | 196608 | 32768 | 16384 | dense ref; temp 0.7; 192K (31 GB weights) |
| `mlx-community/Qwen2.5-1.5B-Instruct-4bit` | — | task | 30000 | 2048 | — | :8092 task/weak/small model |

Gemma sampling (both): `temperature 0.7, top_p 0.95, top_k 64, min_p 0.0, repetition_penalty 1.08,
enable_thinking true`. Both gemmas are `mlx-community/…` → already on HF, no upload. `agent_defaults`:
opencode + aider → Ornith (independently settable per agent).

## §5 — Testing (TDD)

- **Source loader:** valid parses; invalid fails loud (missing required presentation field, unknown
  `family`/`role`, `agent_defaults` → nonexistent model, duplicate names).
- **Per-emitter** against a small fixture: right models present; sampling transformed correctly
  (gemma→`repetition_penalty`+suffix-off; qwen→`presence_penalty`/`min_p`; owui→`repeat_penalty`; aider
  non-OpenAI knobs in `extra_body`; vscode/zed carry no sampling); task model → :8092 + weak/small slots;
  per-agent default applied; input-limit convention per target (incl. zed = full window).
- **Output validity:** every emitted file parses (JSON / YAML / JSONC-tolerant).
- **Drift guard:** `check` asserts committed == freshly generated (also the CI/preflight check).
- **Integrity:** every model in every output ∈ source; no orphans; `agent_defaults` ids exist.

## §6 — max_kv / limits rule (verified against mlx-vlm)

`max_kv_cache_size` → `--max-kv-size` → `MAX_KV_SIZE` is the **total window (prompt + generation)**;
mlx-vlm reserves generation room at runtime (`_resolve_generation_budget`: `remaining = MAX_KV_SIZE −
prompt`; `max_tokens` soft-clamped; `thinking_budget` capped to 0.8× effective). So:
- `max_kv_cache_size = presentation.context` — **no subtraction** (subtracting generation would shrink
  the real window; `thinking_budget ⊆ max_tokens`, don't double-count).
- Client **input limits** are where the generation reservation belongs: `context − output` (opencode/
  aider/vscode); **zed = full context** (Zed reserves output itself).
- **KV pre-allocation is a separate concern** (`turboquant.py:5351` pre-allocs the TQ cache to the global
  `max_kv_size`; fp16/Ornith uses stock step-grow). Right-sizing that to `min(prompt + max_tokens,
  max_kv_size)` is an mlx-vlm worker change tracked in `docs/kv-prealloc-handover.md` — **out of scope
  here**; the generator only sets the cap.

## §7 — Sequencing
Build generator + tests → `configgen generate` → its output **is** the cleaned 5-model config set (the
cleanup happens by construction) → commit → deploy M2+M5 (sync + router restart + OWUI re-seed) →
`publish_models.py --prune` to drop the 5 cut models from the live OWUI DB.

## Risks / open
- **Format fidelity:** each emitter must produce configs the client actually accepts — mitigated by
  output-validity + (optional) a manual smoke per client after first generation.
- **OWUI prune:** `init.py` doesn't remove models absent from the config; the cut models need
  `publish_models.py --prune` (or a stale-model cleanup) to leave the live DB.
- **README drift:** the hand-written `README.md` in each client dir stays manual; only config files are
  generated.
