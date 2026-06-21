# Model benchmark harness

Reasoning + coding benchmarks for the local models served by **mlx-serve** (`:8000`).
Everything runs over HTTP against the router — no in-process MLX. Grading is mechanical
(no LLM judge), so you can run it unsupervised.

## How it works

Two phases, deliberately separated:

| Phase | Cost | Resumable | What it does |
|-------|------|-----------|--------------|
| `generate` | slow (model inference) | **yes** | For each (model, benchmark, item) it calls `:8000`, strips the thinking trace, and appends the completion to `results/<model>/<bench>.jsonl`. |
| `grade` | fast (seconds) | n/a | Reads the saved completions and scores them: integer/MC exact-match, math equivalence, or running the official coding test suites. No model calls. |

Because every completed item is written to disk immediately, generation is **safe to
interrupt** — Ctrl+C, close the laptop, change locations — and rerunning the same command
resumes where it left off (already-done items are skipped; errored items are retried).

### Chunks and overnight runway

Generation runs in time-boxed **chunks** (default 30 min). At each breakpoint it prints
progress + ETA and either continues or stops:

```bash
# Run one ~30-min chunk, then stop (good for a quick session before moving):
uv run python benchmark/run.py generate --tier light --chunks 1

# Auto-run 8 chunks (~4h of runway) overnight, then stop:
uv run python benchmark/run.py generate --tier light --chunks 8

# Run to completion:
uv run python benchmark/run.py generate --tier light --chunks all
```

Only one model is resident in the router at a time. How items interleave across models is set by `--order` (see Ordering).

## Quick start

```bash
# 0. (once) install grading deps into the stack venv
uv pip install -r benchmark/requirements.txt
uv pip install "git+https://github.com/LiveCodeBench/LiveCodeBench.git"   # lcb_runner

# 1. see which benchmarks load and which models are served
uv run python benchmark/run.py list

# 2. generate (chunked, resumable). Defaults to ALL served models.
uv run python benchmark/run.py generate --tier light --chunks all

# 3. check progress anytime
uv run python benchmark/run.py status --tier light

# 4. grade (mechanical, no model)
uv run python benchmark/run.py grade --tier light
```

## Benchmarking a NEW model

1. Add the model to `main_models.yaml` (so the router serves it) and restart the stack
   (`./runserver.sh`) — or just ensure it appears in `GET /v1/models`.
2. Generate only that model (others are untouched; results are per-model):
   ```bash
   uv run python benchmark/run.py generate --models <new-model-name> --tier light --chunks all
   uv run python benchmark/run.py grade   --models <new-model-name> --tier light
   ```
   Once light looks reasonable, escalate the same model to `--tier mid`.
The harness reads the roster from `/v1/models`, so no code change is needed for new models. A new model with no entry in `model_params.PARAMS` inherits the Gemma-4 parameter set (see Generation parameters).

## Benchmarks

| Name | Kind | Grading | Notes |
|------|------|---------|-------|
| `aime` | reasoning (math) | integer exact-match | AIME 2024+2025, 60 problems. Fully mechanical, ungated. |
| `math500` | reasoning (math) | `math_verify` equivalence | MATH-500. Falls back to normalized string match if `math-verify` absent. |
| `gpqa` | reasoning (science) | MC letter exact-match | GPQA-Diamond, 198. **Gated** — needs `HF_TOKEN` + accepting terms at huggingface.co/datasets/Idavidrein/gpqa. |
| `humanevalplus` | coding | official `evalplus` (pass@1) | HumanEval+ (164). |
| `mbppplus` | coding | official `evalplus` (pass@1) | MBPP+ (~378). |
| `livecodebench` | coding | official `lcb_runner` | Contamination-resistant; pin a release window. |

### GPQA auth
GPQA is gated. Put `HF_TOKEN=hf_...` in `.env` (the stack already sources it) and accept the
dataset terms once on the Hub. Until then `list` shows it UNAVAILABLE and it is skipped.

## Retrieval probe (dedicated)

`bench/run_retrieval.py` measures multi-needle NIAH retrieval as an
accuracy-vs-context curve at full production params — distinct from the capacity
probe, whose retrieval number is a thinking-starved co-signal (256-token answer budget).
Five distinct codes are planted at depths {0.1, 0.3, 0.5, 0.7, 0.9}; the model is asked
to list all of them; accuracy = fraction returned, with a per-depth breakdown.

```bash
cd benchmark && uv run python -m bench.run_retrieval --model Qwen3.6-27B-UD-MLX-6bit
```

Writes `results/<model>/retrieval.json` with per-rung `accuracy` + `per_depth_acc` and a
headline `retrieval_effective_ctx` (largest context length with accuracy ≥ 0.85). It is a
full curve, not climb-to-cliff: a mid-context dip does not stop the ladder (retrieval can
recover); only a hard OOM at a context length stops it. Run Qwen's 192K/256K rungs on the
M5 (browser-closed/clean) profile.

## Tiers (escalating scope)

Pick scope with `--tier light|mid|heavy`. The three tiers nest: light's item set is a
prefix of mid's, which is a prefix of heavy's (the subsampling is seeded and prefix-stable),
and light's benchmarks are a subset of mid's, which are a subset of heavy's. So you can run
`light`, then `mid`, then `heavy` and each step regenerates only the items the previous tier
didn't cover — resume reuses everything already on disk.

| Tier | Coding | Reasoning |
|------|--------|-----------|
| `light` | humanevalplus 15, mbppplus 15 | aime 5 |
| `mid` | humanevalplus 15, mbppplus 15, livecodebench 15 | aime 30, math500 30 |
| `heavy` | humanevalplus 164, mbppplus 378, livecodebench 100 | aime 60, math500 200, gpqa 198 |

Light is coding-led on purpose: it gives a fast first read across all 7 models and calibrates
the real per-item cost of coding before you commit to anything larger. Mid adds livecodebench
and math500 and widens aime. Heavy is the full sets plus gpqa.

Recommended workflow: run `--tier light` across every model, grade, and see where you stand.
Then `--tier mid`. Then decide whether `--tier heavy` is worth it — and if some models are too
slow to be worth the full run, drop them with `--models`.

Cost: at production parameters, reasoning items run roughly 5 h/item across all 7 models, with
the dense Gemma-4 and Qwen3.6-27B as the bottleneck; coding is much cheaper. That's why light
is the cheap first read. Tune scope with `--limit` and `--models`, e.g.
`--benches aime,gpqa --limit aime=10,gpqa=10 --models A,B`.

## Generation parameters

The harness sends each model its production parameters from `bench/model_params.py`, sourced
from your `opencode.json` and `aider` configs — not neutral eval defaults. Two parameter sets:

- Gemma-4 family (every dense and MoE quant): temperature 0.7, top_p 0.95, top_k 64,
  repetition_penalty 1.08, max_tokens 32768, enable_thinking true, thinking_budget 16384.
- Qwen3.6-27B: temperature 0.7, top_p 0.95, top_k 20, min_p 0.03, presence_penalty 0.3,
  max_tokens 81920, enable_thinking true, thinking_budget 49152.

Override globally with `--thinking-budget`, `--temp`, and `--max-tokens` — useful to bound
eval time. A new model with no entry in `model_params.PARAMS` inherits the Gemma-4 set; add it
to `PARAMS` if it needs its own.

## Ordering

`--order roundrobin` (default) interleaves models item by item, so any stopping point is a
balanced comparison across all models — grade incrementally and the partial numbers stay fair.
`--order model` runs each model to completion before the next, which minimizes model swaps.

## Convergence (sat%)

`grade` reports `sat%` alongside accuracy: the share of items where the model spent ~all of its
`thinking_budget` (it did not self-converge and leaned on the budget to stop). A model near
100% sat% is reasoning inefficiently; one that finishes well under budget converges on its own.

## Reproducibility

Subsampling is seeded (`--seed`, default 0) and prefix-nested, so the same tier always selects
the same items and tiers escalate cleanly. Parameters are fixed per model at production values
(see Generation parameters), not greedy. Because temperature is 0.7, single-sample runs carry
some run-to-run variance — use these numbers for relative model comparison, not absolute
leaderboard parity.

## Output layout

```
benchmark/results/
  <model>/<bench>.jsonl        # one line per item: completion + token/timing telemetry
  <model>/<bench>_samples.jsonl # coding: official-format samples for the grader
  scores.json                   # written by `grade`
```
