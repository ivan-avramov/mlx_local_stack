# Model Pruning Tournament: Reasoning, Coding, and Throughput at 256K

This is a pruning tournament, not a leaderboard. The output is a keep/drop decision for
each of the 7 locally-served models in `main_models.yaml`. Three things get measured for
every model: reasoning quality, coding quality, and decode throughput in tokens/sec. The
deliverable is a decision matrix that names the deciding metric for each keep/drop call.

The subject codebase under test is the owner's mlx-vlm fork at `src/mlx-vlm/mlx_vlm`.
Deep ground-truth knowledge of it, and it's large enough to stress 256K context. Context
is built from distinct real source across three repos, never by padding with repeated
content (see Context depths).

## Execution model

Everything runs through the live stack. Bring it up with `./runserver.sh`. Models are
served by mlx-serve, an OpenAI-compatible router at `http://localhost:8000/v1`. The
harness is pure HTTP. There is no in-process MLX anywhere in this plan: no `mlx.core`, no
`make_prompt_cache`, no `generate_step`, no `mx.metal.*`. The old in-process bench is
deleted.

Three facts drive the whole harness loop:

1. Request a model by its `name` from `main_models.yaml` in the `model` field. The router
   auto-instantiates it on demand.
2. Exactly one model is resident at a time. Requesting a different model triggers a full
   unload + reload, a "swap." So the harness loops model-OUTER, task-INNER: preload one
   model, run all its tasks and depths, then swap. One swap per model, never per task.
   Models cannot run in parallel; all eval is sequential.
3. Warmup matters. `POST /v1/models/load` blocks until the model is ready, so use it to
   exclude load time from throughput, and discard the first timed request per depth
   (prompt-cache warmup). The metrics `cold_start` flag lets you filter those out after
   the fact.

## Endpoint contract

Verified against the live router and the upstream mlx_vlm server, then validated against
the running stack. Decode throughput and per-request peak memory come from the upstream
`timings` object in the chat-completions response body, not from the metrics endpoint. The
metrics row is still the source for TTFT and `cold_start`, used for cross-checking only.

| Endpoint | Body / params | Returns |
|---|---|---|
| `GET /v1/models` | — | `{"data":[{"id": <name>, ...}]}` — enumerate the roster from live config, never hardcode |
| `POST /v1/models/load` | `{"model": <name>, "keep_alive": "180m"}` | `{"model","status":"ready"}`, blocks until ready |
| `POST /v1/chat/completions` | standard OpenAI, `stream:false` for speed probes | `usage.{prompt_tokens, completion_tokens}` plus `timings.{predicted_per_second, predicted_ms, prompt_ms, prompt_per_second, peak_memory}` passed through from the upstream server |
| `GET /v1/metrics/requests` | `?model=&last_n=` | `{"requests":[...]}` newest-first; also in `requests.jsonl`. TTFT/cold_start cross-check only; decode now comes from `timings` |
| `GET /v1/status` | — | `memory.{total_gb,used_gb,available_gb}`, `metal.{active_mb,peak_mb,cache_mb}` |

Each `/v1/metrics/requests` row: `model, endpoint, timestamp, total_duration_ms,
ttft_ms, tokens_per_second, prompt_tokens, completion_tokens, status_code, error,
cold_start`. Do not read decode from this row's `tokens_per_second` (see Speed methodology).

On `/v1/status`: `metal.*` is populated for in-process models only. The owner's models
run as subprocesses, so `metal.peak_mb` is null/0 for them. Use `timings.peak_memory` from
each response body for per-request peak memory. For whole-stack RAM, use system `used_gb`
plus subprocess RSS, not the metal counters.

## The roster: 7 models, 3 families

Read this from the live config; the table below is the current `main_models.yaml`. The
families are organized around redundancy questions, because that's what the tournament
decides.

### Family D — Dense Gemma-4-31B

| ID | name | Source / recipe | Notes |
|---|---|---|---|
| D-6 | `gemma-4-31b-it-6bit` | mlx-community, standard 6-bit | |
| D-6Q | `gemma-4-31B-it-qat-6bit` | mlx-community, QAT 6-bit | capped at 192K in registry (~31GB weights trip the RAM backstop at 256K) |
| D-4U | `gemma-4-31b-it-UD-MLX-4bit` | unsloth, UD 4-bit | |

Redundancy questions. Does QAT-6bit beat standard-6bit at the same size? This is the
cleanest controlled test in the whole set: same arch, same bits, QAT vs not. And is
UD-4bit good enough to make any 6-bit redundant for daily use?

### Family M — MoE Gemma-4-26B-A4B

~26B total params, ~4B active per token, so fast decode but big RAM.

| ID | name | Source / recipe |
|---|---|---|
| M-8 | `gemma-4-26b-a4b-it-8bit` | mlx-community, standard 8-bit |
| M-4O | `gemma-4-26B-A4B-it-OptiQ-4bit` | mlx-community, OptiQ 4-bit |
| M-4Q | `gemma-4-26B-A4B-it-QAT-MLX-4bit` | lmstudio-community, QAT 4-bit |

Redundancy questions. OptiQ-4bit vs QAT-4bit: which 4-bit recipe wins at identical size?
And is the 8-bit worth ~2x the RAM over the best 4-bit?

### Family Q — Qwen3.6-27B

| ID | name | Source / recipe | Notes |
|---|---|---|---|
| Q-6U | `Qwen3.6-27B-UD-MLX-6bit` | unsloth, UD 6-bit | lone cross-family wildcard, no internal redundancy |

## Pruning rule

Within a family, drop the heavier or slower sibling when it lands within 5% of the
lighter one on the weighted coding+reasoning score. The MoE decode advantage is itself a
pruning input: if dense 31B is N x slower than the MoE for no quality gain, the dense
model is redundant. Qwen stays unless a Gemma dominates it on both speed and quality.

## Speed methodology

Throughput is first-class and always run. It's the #1 explicit goal, so it gets measured
for all 7 models regardless of how the quality stages shake out.

Speed probes use non-streaming requests (`stream:false`). The upstream mlx_vlm server
passes a `timings` object through in the response body, and that is the source of truth for
throughput, not the router metrics and not TTFT.

Decode tok/s is `timings.predicted_per_second` from the response body. That figure is
authoritative. Do not use the router's `/v1/metrics/requests` `tokens_per_second` for
decode: it is `completion_tokens / total_duration` and conflates prefill into the rate,
under-reporting decode by roughly 2x. (An earlier version of this plan read decode from the
metrics endpoint; that was wrong.)

Prefill tok/s is not reported. `timings.prompt_ms` and `timings.prompt_per_second` come
back 0.0 even for thousands of prompt tokens, so the server does not measure it. Derive it
client-side as `prompt_tokens / (wall_clock_seconds - timings.predicted_ms/1000)` and label
it derived/approximate everywhere it appears. (An earlier version derived prefill from
`ttft_ms`; that was wrong, because the thinking trace precedes the first content token, so
TTFT is unusable as a prefill proxy.)

Peak memory per request is `timings.peak_memory` (GB), present in every response body. Use
it for the memory pass/fail, not the `/v1/status` metal fields, which are null for these
subprocess-served models.

## Thinking-token handling

Every model has `enable_thinking: true`, and each Gemma-4 model emits its reasoning trace
into a separate `reasoning` field, not `content`. Disabling it per request via
`chat_template_kwargs: {enable_thinking: false}` is not honored: the trace comes back
regardless.

The trace can run to hundreds of tokens. With a small `max_tokens` it consumes the whole
budget and the model returns a canned `"Thinking used the entire token budget..."` string
in `content` with no real answer (verified at `max_tokens=400` on a code-summary prompt).

Three implications:

1. Speed is unaffected. Decode tok/s measured over the thinking tokens is the correct
   real-world number, so keep it.
2. Stage 1/2 quality tasks must set a large `max_tokens` (>= ~2048) so the answer survives
   the trace, and must strip the `reasoning` field plus any `<think>...</think>` block from
   `content` before judging.
3. Open question: whether a `thinking_budget` knob exists upstream. The canned
   budget-exhaustion message hints at one; find it before running long quality passes.

## Context depths

Nominal 16K / 64K / 128K / 256K. Build context from distinct real source: mlx-vlm,
mlx-serve, and mlx-lm. Never pad by repeating content. Repetition creates
induction-friendly patterns that flatter long-context scores, so a repeated-content
256K is a fake 256K.

The true size is read from `usage.prompt_tokens`, so the depth label is nominal, not
exact. Max-usable-context is a measured output per model, not an assumption: push depth
until a request errors or the subprocess dies, and record where that happened. D-6Q caps
near 192K by config, so it never sees a real 256K depth.

Probe cost matters at depth. Calibration on the live stack: dense Gemma-4-31B prefill runs
~65 tok/s, so a 64K probe takes ~16 min and 128K/256K probes 30+ min each. So the cheap
Stage-0 triage covers depths [2K baseline, 16K, 64K] only; 128K and 256K speed probes are a
deliberate opt-in follow-up, not part of cheap triage.

---

## Stage 0 — Triage (automated, all 7 models)

Cheap and fully automated. Prune here before spending judge tokens.

### 0a — Speed

Load time, prefill tok/s (derived), decode tok/s, and TTFT at the cheap-triage depths
[2K baseline, 16K, 64K]. Decode and peak memory from the `timings` body, TTFT from
`/v1/metrics/requests`, first timed request per depth discarded via `cold_start`. The
128K/256K probes and each model's measured max-usable-context are the opt-in deep follow-up
(see Context depths), not part of this cheap pass.

Note the MoE-vs-dense decode gap explicitly: the M family should decode much faster than
the D family at comparable RAM, and that gap is a pruning input for the dense models.

| Model | Load s | Prefill tok/s @64K (derived) | Decode tok/s @64K | TTFT @64K | Decode tok/s @128K | Max ctx |
|---|---|---|---|---|---|---|
| D-6 | | | | | | |
| D-6Q | | | | | | ~192K (cap) |
| D-4U | | | | | | |
| M-8 | | | | | | |
| M-4O | | | | | | |
| M-4Q | | | | | | |
| Q-6U | | | | | | |

### 0b — Long-context retrieval (needle-in-haystack)

Insert a needle at controlled depths AND positions so it actually exposes lost-in-the-
middle. Position is the fraction through the context where the needle sits: ~0.1 (start),
0.5 (mid), 0.9 (end). The old plan asked fixed factual questions without controlling
needle position, which can't separate "lost in the middle" from "didn't read at all."

The needle is a synthetic fact that cannot be answered from parametric knowledge (e.g.
an invented attribute name or constant planted in the source stream). Score = hit rate
across the depth x position grid.

| Model | 16K (0.1/0.5/0.9) | 64K (0.1/0.5/0.9) | 128K (0.1/0.5/0.9) | 256K (0.1/0.5/0.9) |
|---|---|---|---|---|
| D-6 | | | | |
| D-6Q | | | | n/a (cap) |
| D-4U | | | | |
| M-8 | | | | |
| M-4O | | | | |
| M-4Q | | | | |
| Q-6U | | | | |

### Stage 0 prune

Any model that is both slower AND lower-retrieval than a same-family sibling at equal RAM
is dropped here, before Stage 1. Record the deciding numbers; those carry into the
decision matrix.

---

## Stage 1 — Reasoning + coding (family survivors, LLM-judged)

Roughly 4-5 models reach this stage. Run within-family head-to-head first (apples-to-
apples on the quant recipe), then promote the family winners to a cross-family round.

Judge via the Anthropic API with `claude-sonnet-4-6`, escalating to `claude-opus` for
close calls. Rubric 1-5, reference-anchored, judge temperature 0. Model temperature 0
for all Stage 1 tasks so outputs are deterministic and comparable. Strip `<think>` blocks
before judging.

### T1.1 — Pattern-conformant feature implementation

Context: full `mlx_vlm/` source tree.

```
You are implementing a new feature in the mlx-vlm codebase. Study the existing
model plugin architecture carefully before responding.

Task: Add support for a new `MemoryTrackingKVCache` class in models/cache.py.
This class should:
1. Wrap any existing cache type (KVCache, TurboQuantKVCache, etc.) via composition
2. Track total bytes written to K and V since initialization
3. Expose get_stats() -> dict with keys: k_bytes, v_bytes, total_bytes, n_updates
4. Follow the same interface contract as KVCache (same method signatures)
5. Match the code style and docstring format used elsewhere in cache.py

Provide the complete class implementation only. Do not modify existing classes.
```

Rubric: 5 compiles, correct interface, correct tracking logic, matches style. 4 compiles,
correct interface, minor logic issue or style drift. 3 compiles, interface partially
correct. 2 does not compile but logic is directionally right. 1 fundamentally wrong.

### T1.2 — Cross-file dependency trace

Context: full repo including tests, run at 128K.

```
In the mlx-vlm codebase, the model loading path connects several components.

Trace the complete execution path from a user calling:
    model, processor = load("some-hf-model-id")

through to the point where the model's first forward pass could be run. List:
1. Every function called in order, with the file it lives in
2. Any conditional branches (e.g. model_type routing)
3. The point at which the KV cache type is selected
4. Any places where the VLM processor diverges from a text-only LM processor
```

Rubric: 5 all 4 items correct, correct order, no invented functions. 4 mostly correct,
1 minor omission or invented detail. 3 correct skeleton, 2-3 errors. 2 partially correct
but significant gaps. 1 mostly hallucinated.

This task is a strong signal on whether the model is truly reading the repo vs drawing on
generic transformer knowledge. Write the correct trace yourself first as ground truth.

### T1.3 — Bug localization

Context: full repo plus a synthetic bug description. Plant a real bug of this type in a
branch and verify the correct answer before running.

```
A user reports the following bug in mlx-vlm:

  "When I use make_prompt_cache() with max_kv_size=65536 and then run a multi-turn
   conversation, the second turn always produces garbage output if the first turn
   used more than 32768 tokens. The first turn output is correct."

Without modifying any code, identify:
1. The most likely root cause based on the codebase
2. The specific file and function where the bug would manifest
3. What invariant is being violated
4. The minimal fix
```

Rubric: 5 correct root cause, location, and fix. 4 correct root cause and location, fix
is off. 3 correct area, wrong specific location. 2 plausible but wrong. 1 wrong.

### T1.4 — Architecture design (64K vs 256K)

Context: full repo. Run at 64K and 256K, compare answers. This is the closest proxy for
the owner's actual use, so it carries the highest weight.

```
You are a senior engineer reviewing the mlx-vlm codebase.

The team wants to add support for running two different models simultaneously
(e.g., a VLM for image understanding + a large text model for reasoning), sharing
the same Metal GPU without exceeding 60 GB of peak RAM.

Based on the existing architecture:
1. What are the 2-3 biggest obstacles to this today?
2. What would you change in the server.py MultiCacheManager to support model
   switching with minimal re-prefill overhead?
3. Would TurboQuantKVCache help or hurt this use case? Why?
4. Sketch the interface changes needed (no code, just method signatures and data flow).
```

Rubric: 5 correct identification of actual obstacles in the code, feasible design. 4
correct obstacles, design has one unrealistic assumption. 3 identifies obstacles but
design is generic. 2 generic "how to run two models" answer, ignores codebase specifics.
1 wrong.

The 64K-vs-256K delta is the point. A model that scores 5 at 64K but 3 at 256K can
retrieve facts at depth but can't synthesize across them.

### T1.5 — Multi-turn incremental implementation

Tests whether design intent survives across turns. Run as a 3-turn conversation.

Turn 1:
```
I want to add chunked prefill to stream_generate() in generate.py to cap peak memory
during long-context processing. Before I write any code, walk me through the risks
and invariants I need to preserve. Focus on the KV cache and PromptCacheState.
```

Turn 2 (after the model responds):
```
Good. Now implement the chunked prefill as a standalone function
chunked_prefill(model, input_ids, cache, chunk_size=2048) that I can drop in
before the existing generate loop. Preserve all existing behavior for chunk_size=None.
```

Turn 3 (after the model responds):
```
The function you wrote doesn't account for the case where the model uses a
RotatingKVCache with a window smaller than chunk_size. Fix this.
```

Rubric: 5 all three turns coherent, turn 3 fix is correct and doesn't regress turn 2. 4
turns 1-2 correct, turn 3 fix partially correct. 3 turn 2 functional but turn 3 reveals
it missed basics. 2 loses context between turns, turn 3 contradicts turn 2. 1 wrong
throughout.

---

## Stage 2 — Finalist qualitative (top 2-3, human judgment)

Run only for the top 2-3 models out of Stage 1. Grade these yourself; they need deep
codebase knowledge to score accurately. Model temperature 0.6 here, closer to interactive
use and better at surfacing incoherence or repetition over long sessions.

### T2.1 — Open-ended architecture critique

256K context, full repo.
```
You have full access to the mlx-vlm codebase. Give me your honest assessment of
the biggest architectural weaknesses in the KV cache and generation pipeline, and
what you would prioritize fixing if you owned this codebase. Be specific about
code locations, not generic about "LLM inference."
```
Grade on depth of code-grounded insight, correctness of claimed issues, quality of fixes.

### T2.2 — Design document generation

256K context.
```
Write a design document for adding support for speculative decoding (draft model
acceleration) to mlx-vlm. The document should cover:
- Interface changes to the generate pipeline
- How to share the KV cache between draft and target models
- Interaction with TurboQuantKVCache
- Failure modes and fallback strategy
Format: 4-6 sections, each grounded in specific parts of the existing code.
```
Grade on technical correctness, grounding in the actual codebase, completeness.

### T2.3 — Sustained-context session

256K context, 10-turn conversation. Run a full design-and-implementation session for a
moderately complex feature (a new model architecture, or refactoring the server for
multi-model support). Does the model drift from the established design across 10 turns?
Does it contradict earlier decisions? Does it hallucinate API surfaces that don't exist?

---

## Harness

A pure-HTTP `eval_harness.py` already lives in the repo root. Stdlib only, run via
`uv run python eval_harness.py <speed|needle|tasks> ...`. It writes incremental JSONL to
`eval_results/`, loops model-outer / task-inner, reads decode tok/s and peak memory from
the `timings` response body, and cross-checks TTFT/cold_start against `/v1/metrics/requests`
per the endpoint contract above.

| Subcommand | What it runs |
|---|---|
| `speed` | Stage 0a: load + non-streaming request at each depth, read decode tok/s and peak_memory from `timings`, derive prefill from wall-clock, cross-check TTFT from metrics |
| `needle` | Stage 0b: needle-in-haystack across the depth x position grid |
| `tasks` | Stage 1/2: chat-completions task runner, captures response + usage, optional judge call |

The script is the implementation of record; read it rather than the snippets here.
Judging calls the Anthropic API directly (not through the local router).

---

## Scoring

Weighted, grouped by family. Design and reasoning weighted highest, then coding, then a
first-class speed column. Fill from runs. Speed is normalized within the table (decode
tok/s, higher better).

### Family D

| Task | Weight | D-6 | D-6Q | D-4U |
|---|---|---|---|---|
| 0b retrieval @128K | 2x | | | |
| T1.1 pattern impl | 2x | | | |
| T1.2 cross-file trace | 2x | | | |
| T1.3 bug localization | 2x | | | |
| T1.4 design @256K | 3x | | | (192K) |
| T1.5 multi-turn | 2x | | | |
| Decode tok/s @64K | 1x | | | |
| Weighted total | | | | |

### Family M

| Task | Weight | M-8 | M-4O | M-4Q |
|---|---|---|---|---|
| 0b retrieval @128K | 2x | | | |
| T1.1 pattern impl | 2x | | | |
| T1.2 cross-file trace | 2x | | | |
| T1.3 bug localization | 2x | | | |
| T1.4 design @256K | 3x | | | |
| T1.5 multi-turn | 2x | | | |
| Decode tok/s @64K | 1x | | | |
| Weighted total | | | | |

### Family Q (and cross-family round)

| Task | Weight | Q-6U | D winner | M winner |
|---|---|---|---|---|
| 0b retrieval @128K | 2x | | | |
| T1.1 pattern impl | 2x | | | |
| T1.2 cross-file trace | 2x | | | |
| T1.3 bug localization | 2x | | | |
| T1.4 design @256K | 3x | | | |
| T1.5 multi-turn | 2x | | | |
| Decode tok/s @64K | 1x | | | |
| Weighted total | | | | |

Stage 2 is qualitative; note findings but don't fold into the score.

## Decision matrix (the deliverable)

One row per model. The deciding metric is the column that settles the call.

| ID | Family / role | Key speed (decode tok/s, max ctx) | Quality verdict | KEEP / DROP | Deciding reason |
|---|---|---|---|---|---|
| D-6 | Dense, std 6-bit | | | | |
| D-6Q | Dense, QAT 6-bit | | | | |
| D-4U | Dense, UD 4-bit | | | | |
| M-8 | MoE, std 8-bit | | | | |
| M-4O | MoE, OptiQ 4-bit | | | | |
| M-4Q | MoE, QAT 4-bit | | | | |
| Q-6U | Qwen wildcard | | | | |

## What the results tell you

If D-6Q is within 5% of D-6, drop one. They're the same arch at the same bits, so the
only thing being tested is whether QAT earned its place. Keep the winner, drop the other.

If the best M-4 (OptiQ or QAT) is within 5% of M-8, drop the 8-bit. ~2x the RAM for a
margin under the pruning threshold isn't worth it.

If MoE decode is much faster than dense at equal quality, the dense 31B family is
redundant. The owner's #1 goal is throughput; a 4B-active MoE that matches dense reasoning
while decoding several times faster makes the dense models hard to justify.

If retrieval degrades sharply past 64K (0b drops at the 0.5 position especially), that
model isn't reliably using the full context. Disqualify it for 256K work regardless of
its Stage 1 scores.

If T1.4 scores higher at 64K than 256K, the model has a lost-in-the-middle problem for
reasoning specifically: it retrieves facts at depth but can't synthesize across them.

If T1.5 (multi-turn) diverges sharply between survivors, weight it heavily. Sustained
design coherence is the most practically relevant signal for real implementation sessions.

If Q-6U doesn't beat the surviving Gemma on either speed or quality, drop it. It has no
internal redundancy to fall back on, so it has to earn its slot outright.
