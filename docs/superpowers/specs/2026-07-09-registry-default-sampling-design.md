# FU-2 — Registry-side default sampling (unified, opaque `generation_defaults`)

**Date:** 2026-07-09. **Status:** design, approved (execution authorized; no review pause).
Phase-2 follow-up FU-2. Handover: `docs/phase2-followups-handover.md`. Forks: `../mlx-serve`,
`../mlx-vlm` (edit parents, not `src/*` submodules).

## Goal & the concrete gap

Five clients target the router; three (opencode, aider, OpenWebUI) carry full per-model sampling,
two (**VS Code, Zed**) carry **none** — their config formats can't. The router (`mlx-serve`) is a
pure proxy that holds **zero** sampling defaults, so a request that omits sampling runs at the
worker's fallback. Measured today, that fallback is *wrong* for both winners:

- **distill** (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`): its checkpoint `generation_config.json`
  bakes `temperature: 1.0, presence_penalty: 1.5`. Since temp *is* read from the checkpoint config
  as the default, VS Code/Zed run it at **temp 1.0** — not the tuned **0.3**. For a Qwen-arch model
  that meanders hot, this is a severe regression (the whole campaign settled it at 0.3).
- **Ornith** (`Ornith-1.0-35B-mlx-uniform-4bit`): ships **no** `generation_config.json` → falls
  through to the hardcoded `DEFAULT_TEMPERATURE = 0.0` (**greedy**), `top_p 1.0`, `top_k 0`. Tuned
  is 0.4 / 0.95 / 20.

Goal: make `main_models.yaml` the registry-side carrier of per-model generation defaults, applied
by the worker **only when the request omits a field**, so all five clients run the tuned config
(and suffix engages via `presence_penalty 0.0`). Explicit request params are always honored.

## Current precedence (traced)

Highest wins: **`per-request > cmdline > env > checkpoint generation_config.json > hardcoded`**.
cmdline and env are distinct: a worker flag seeds its argparse default *from* the env var, then an
explicit cmdline value overwrites it. Coverage is uneven and `main_models.yaml` is absent from the
chain entirely:

| field | request | cmdline/env | checkpoint config | hardcoded |
|---|---|---|---|---|
| temperature / top_p / top_k | ✓ | — | ✓ | ✓ (0.0 / 1.0 / 0) |
| min_p / presence / frequency / repetition_penalty | ✓ | — | — | ✓ (0.0 / None) |
| enable_thinking / thinking_budget / max_tokens / thinking_*_token | ✓ | ✓ | — | ✓ |

The omission-detection + cascade machinery already exists and is unit-tested:
`_build_gen_args` (`../mlx-vlm/mlx_vlm/server/app.py:168`), `_request_field_or_default`
(uses Pydantic `model_fields_set` to distinguish an explicit client value from a schema-filled
default), and the `get_server_*()` env getters (`generation.py:335+`). FU-2 extends this — it is
not new infrastructure.

## Design

**Target precedence:** **`request > main_models.yaml > checkpoint > hardcoded`** (A). Required, not
just preferred: without the registry beating the checkpoint, Qwen3.6-27B-Opus-Distill-OptiQ-4bit's baked `1.0` still wins.

### Partition (registry schema)
Per-model config splits into two categories:

- **`generation_defaults:`** — a new **opaque, unified** block holding every **per-request-
  overridable generation param**: `temperature, top_p, top_k, min_p, presence_penalty,
  frequency_penalty, repetition_penalty, max_tokens, thinking_budget, enable_thinking,
  thinking_start_token, thinking_end_token`. `enable_thinking` moves in here too — one place, no
  top-level `enable_thinking:`. mlx-serve **never enumerates these keys.**
- **Structural, load-time flags stay typed on the model entry** (not request-overridable):
  `kv_bits, kv_quant_scheme, kv_quant_mode, draft_kind, draft_block_size, suffix_min_match,
  draft_cooldown, draft_model, prefill_step_size, quantized_kv_start, max_kv_cache_size,
  cache_limit_gb, memory_limit_frac`, plus `name/type/hf_path/on_demand`. These are fixed at model
  load and genuinely need coordinated mlx-serve↔mlx-vlm wiring, so leaving them typed loses nothing.

The principle: **defaults for what a request can override** go in the opaque block; **structural
instantiation flags** stay typed. New generation params → yaml only (zero mlx-serve edits). New KV
scheme → the rare coordinated structural change.

```yaml
- name: Qwen3.6-27B-Opus-Distill-OptiQ-4bit
  type: vision
  on_demand: true
  hf_path: caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit
  max_kv_cache_size: 262144
  kv_quant_scheme: turboquant
  kv_bits: 4                 # structural (typed, unchanged)
  prefill_step_size: 512
  quantized_kv_start: 0
  draft_kind: suffix
  draft_block_size: 16
  suffix_min_match: 2
  generation_defaults:       # OPAQUE, unified — forwarded verbatim
    temperature: 0.3
    top_p: 0.95
    top_k: 20
    min_p: 0.0
    presence_penalty: 0.0
    max_tokens: 102400
    thinking_budget: 81920
    enable_thinking: true
```

### Transport — one opaque JSON arg
`generation_defaults` is passed as a single `--generation-defaults '<json>'` worker flag. JSON
preserves int/float/bool/list/dict natively (no string coercion), it's one line, and the full blob
is greppable in the spawn log. (Chosen over flat `k=v` cmdline strings — awkward for lists, needs
coercion — and over a temp yaml file — lifecycle/cleanup.)

### Fail loud and fast
- **mlx-serve:** if a stale top-level `enable_thinking:` key remains after migration → **raise** at
  config load (so nothing silently disables thinking). This is a targeted guard for the one
  migrated key, not a broad unknown-top-level-key check (`on_demand` etc. are legitimately
  untyped today).
- **mlx-vlm:** at startup, if any `generation_defaults` key is not a field of `GenerationArguments`
  → **raise** with the offending key (a typo would otherwise mean silently-wrong sampling).

## Components & data flow

1. **`../mlx-serve`**
   - `config.py`: add `generation_defaults: dict = field(default_factory=dict)` to `ModelConfig`;
     read it in `_load` (`generation_defaults=entry.get("generation_defaults", {})`); **remove**
     the typed `enable_thinking` field + its `_load` read; add the stale-`enable_thinking`-key
     raise.
   - `process_manager.py:_build_command`: **remove** the `--enable-thinking` append; add
     `if model_cfg.generation_defaults: cmd += ["--generation-defaults", json.dumps(model_cfg.generation_defaults)]`.
   - That is the **entire, final** mlx-serve change — it never learns a generation-param name again.

2. **`../mlx-vlm`**
   - `server/cli.py`: add `--generation-defaults` (JSON string). Parse once; store (module global
     or env var, mirroring the thinking-flag pattern). **Remove nothing** — keep the existing
     `--enable-thinking/--thinking-budget/--max-tokens/--thinking-*-token` flags as a deeper
     fallback (back-compat for standalone `mlx_vlm.server` use).
   - `server/generation.py` (or `app.py`): add `get_server_generation_defaults()` returning the
     parsed dict; **validate keys against `GenerationArguments.__dataclass_fields__` at startup →
     raise on unknown.**
   - `server/app.py:_build_gen_args`: after the base build, overlay:
     ```python
     for k, v in get_server_generation_defaults().items():
         if not _request_explicitly_set(request, k):   # request wins
             setattr(gen_args, k, v)
     ```
     `_request_explicitly_set(request, k)` returns True iff the client sent the key, via
     `request.model_fields_set` — **and for `max_tokens` it also returns True when the
     `max_output_tokens` alias is set** (the request schema aliases them; `_build_gen_args`
     already resolves the alias at line 172-176). Yields uniform `request > yaml > checkpoint >
     hardcoded` for every field. Because the overlay mutates `gen_args` before the caller invokes
     `to_template_kwargs()`, a yaml `enable_thinking` also reaches the chat template correctly.

**Correctness dependency (verified):** the router forwards the request body verbatim, rewriting
only `body["model"]` and injecting no sampling — so `model_fields_set` on the worker reflects
exactly the client's keys, and the request-override check is sound end-to-end.

## Registry migration (both boxes)
- Add `generation_defaults` blocks to the two winners in `main_models.yaml`, mirroring the
  opencode/aider/owui full-sampling set (Ornith t0.4, distill t0.3; top_p 0.95, top_k 20,
  min_p 0.0, presence_penalty 0.0, max_tokens 102400, thinking_budget 81920, enable_thinking true).
- Move every model's top-level `enable_thinking: true` into its `generation_defaults` block (atomic
  with the mlx-serve field removal, so no model loses thinking).
- M5 keeps its uncommitted local distill entry — migrate it in place, do not commit local hf_paths.
- This makes `main_models.yaml` a **4th carrier** in the AGENTS.md config-propagation rule
  (opencode / aider / owui / **main_models.yaml generation_defaults**), finally covering VS Code +
  Zed. Update that note in AGENTS.md.

## Testing (TDD, both forks)

- **mlx-serve** (`process_manager` / `config`): a `generation_defaults` block emits exactly one
  `--generation-defaults <json>` arg with the round-tripped dict; empty/absent block emits nothing;
  `--enable-thinking` is no longer emitted; a top-level `enable_thinking:` key raises at load.
- **mlx-vlm** (`test_server.py`, extending the existing `_build_gen_args` tests): request value
  overrides a `generation_defaults` value; a `generation_defaults` value overrides the checkpoint
  config; an omitted field takes the `generation_defaults` value; an unknown key raises at startup;
  `max_tokens` alias (`max_output_tokens` in request) suppresses the overlay.
- **Integration (M2, the real check):** start a worker via the router with a `generation_defaults`
  block, POST a request with **no sampling**, and confirm the served/echoed sampling matches the
  yaml (not the checkpoint's temp 1.0). Drive the affected flow, not just unit tests.

## Risks / known
- **enable_thinking migration** — the one field that changes shape. Mitigated by the atomic yaml
  move + the mlx-serve stale-key raise; verified by the "thinking still on" integration check.
- **`max_tokens` aliasing** — handled explicitly in the overlay; covered by a test.
- **Back-compat for direct `mlx_vlm.server` users** — the existing CLI flags are retained as a
  deeper fallback; only mlx-serve stops using them.

## Rollout
Edit forks → TDD to green → integration-verify on M2 → **present diffs + test output and confirm
before** committing/pushing fork remotes, bumping the stack submodule, and redeploying the M5/M2
routers (the outward, cross-box, hard-to-reverse step). Sanity-check staged diffs for PII (no
`/Users/`, hostnames, usernames, tokens) before any commit.
