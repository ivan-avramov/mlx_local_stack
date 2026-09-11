# Judge panel for role C (M38) — spec of record

Status: APPROVED by the operator 2026-09-11 (P334; "you drive it fully including the domain
prompts"). Supersedes the 2026-08-17 D2 spec (git `b723bde`), which targeted code style; role C
is research, brainstorming and design. This file is agent-facing: rules, not rationale.

## Purpose

Rank the C contenders on subjective research/design quality with a blind, mixed-family,
pairwise judge panel that must pass a pre-registered reliability gate before any ranking
is admissible. Math500 stays a proxy; this is the role's real axis.

## Contenders (deployed tunes, thinking ON, predictor OFF, `--sampling-profile deployed`)

`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`,
`Qwen3.8-27B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. k=1, seeded per
(item, sample). Budgets unchanged (thinking_budget 81920, max_tokens per registry).

## Corpus `cjudge` (v1, 40 prompts, committed at `benchmark/corpora/cjudge_v1.jsonl`)

- 30 public prompts: a permissively licensed pairwise-judged prompt set (Arena-Hard-style or
  WildBench), filtered to software/system design, ML/AI research, planning and brainstorming;
  English; text-only; no tool use; no images; prompt ≤ 1,500 tokens. Selection is seeded and
  recorded (`source`, `source_id`, `license`, `category`, `selection_seed`) in
  `benchmark/corpora/cjudge_v1.provenance.json` with the file sha256.
- 10 domain prompts (`source: "operator-domain"`, ids `dom-01..10`), verbatim from the
  "Domain prompts" section below.
- Row schema: `{id, source, source_id, category, prompt}`. Loader: `bench/benchmarks.py`
  SPECS entry `"cjudge": {"kind": "open", "answer_type": "none", "gated": False}`; no
  system prompt suffix; `grade` records n/convergence only (no accuracy).

## Generation (the only GPU stage)

Chain runner in `$STACK_WORKDIR/queue/m38_cjudge/` following `queue/c_second_reference/run.py`:
waits for the predecessor DONE marker and an idle box; per model: fresh draft-OFF overlay,
router with `MLX_VLM_CACHE_SESSION_MAX=2`, `MLX_SERVE_CONFIG` in the driver env, C35 check on
the first manifest, seeded 5-item pilot (`--limit cjudge=5 --seed 0`, sized from mean AND max),
then full 40, `bench_watch` alongside, tune label `m38`. One resident model; unload between.

## Anchors (built from the generated outputs, seeded; `bench/judge_anchors.py`)

30 pairs, 10 per type, drawn across models and items with seed 38:
- `degrade`: original vs mechanically degraded copy — headings/lists flattened into run-on
  prose, two sentences negated, final section dropped. Expected: original wins.
- `verbosity`: original vs 3× padded copy (paragraphs duplicated with filler transitions).
  Expected: preference for the SHORTER must not exceed the `degrade` accuracy.
- `identity`: A == B. Expected: "no preference".
Anchor pairs are presented to the panel mixed with candidate pairs, blind.

## Panel and protocol (`bench/judge_pairwise.py`, `bench/run_judge_pairwise.py`)

- Judges: `claude-opus-5` and `claude-sonnet-5` (Anthropic API, adaptive thinking, reuse
  `bench/judge.py` backends) and GPT-5.5 via `codex exec` (existing backend). Mixed family
  is mandatory; report per-family splits.
- Pairwise forced choice `A` / `B` / `tie`, both orders for every pair, every judge. Blind:
  no model names; outputs whitespace-normalised; self-identifying strings stripped.
- Rubric (system prompt, versioned by sha in every verdict row): judge research/design
  quality only — soundness of reasoning, depth and insight, structure and clarity,
  actionability, calibrated uncertainty; ignore length except where it hurts clarity; reply
  with ONLY JSON `{"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}`.
- Verdict per (pair, judge) = agreement of the two orders, else `tie`. Panel verdict =
  majority over judges, tie → `tie`. `tie` counts 0.5 in preference rates.
- Persistence: one JSONL row per call with `pair_id, anchor_type|null, item_id, a_key,
  b_key, order, judge, prompt_sha, raw, choice, ts`; resumable; retries ≤ 2 with backoff;
  transport failures escalate after retries (never graded). Cost log (calls, tokens).

## Reliability gate (pre-registered; computed by `bench/judge_gate.py`; FAIL → no ranking)

- Anchor accuracy on `degrade` ≥ 0.85.
- Per-judge order flip rate ≤ 0.30; panel Cohen's kappa between orders ≥ 0.6.
- Krippendorff's alpha across judges on anchors ≥ 0.5.
- `verbosity`: shorter-preference rate ≤ `degrade` accuracy.
- `identity`: `tie` rate ≥ 0.80.
Gate result is recorded in campaign-results whatever the outcome. On FAIL: revise rubric or
panel, re-run the gate only (anchors cost judge calls, not GPU).

## Ranking (only after the gate passes)

- Units: (item, A output, B output) over the 40 items, all 6 model pairs, both orders,
  3 judges (≈1,440 calls + 180 anchor calls).
- Endpoint: paired preference rate per pair with `stats.cluster_bootstrap` over items;
  Holm across the 6 pairs; TOST ±5pp for `equivalent`; report tokens/task, latency and
  runaway share alongside (the four numbers). MDE at n=40 ≈ ±16pp — state it.
- Output `benchmark/results/judge_c_v1/{gate.json, ranking.json}`; campaign-results dated
  entry; README C table update; rank changes → operator approval (C67 pending).

## Domain prompts (verbatim corpus text; ids dom-01..dom-10)

dom-01: You run a 64 GB Apple-silicon machine as the only inference host for a coding agent that needs 256K tokens of context. A lossy KV-cache quantization would free memory. Design the measurement protocol that decides whether it is acceptable: what to measure, on which tasks, with what sample sizes, how to separate retrieval depth from reasoning depth, and the pitfalls that would make a "no loss" result untrustworthy.

dom-02: Speculative decoding with a multi-token-prediction head sometimes speeds a local model up 1.8× and sometimes slows it down. Analyse the economics as a function of acceptance rate, target decode speed, verify cost and batch size, state when it cannot pay off, and propose the smallest experiment that predicts the outcome for a new model before building its draft head.

dom-03: A team ranked candidate models by "successes per hour" on a coding benchmark. Critique this metric thoroughly. Then propose a reporting scheme that keeps capability, edit competence, latency and runaway behaviour separate, and explain how a decision-maker should trade them off.

dom-04: Design the architecture of a local model-serving router for one machine that can hold only one large model at a time, serving both an interactive daily-driver client and unattended benchmark traffic. Cover session caching, model swap policy, request cancellation, memory accounting and the failure modes you would instrument first.

dom-05: Summarise what is known about layer-wise sensitivity to weight quantization in transformer language models, and design a procedure to allocate mixed precision (some layers 8-bit, most 4-bit) for a new model without labelled evaluation data. State the assumptions and how you would validate the result.

dom-06: Long-thinking models sometimes fall into verbatim repetition loops until a token budget ends the response. Brainstorm ways to reduce these runaways without lowering answer quality, group them by where they intervene (sampling, decoding, prompting, training, serving), and rank them by expected effectiveness and by cost to test.

dom-07: You developed an evaluation methodology for local models on a laptop and will reuse it on H200 and B200 servers. Write the transfer study: which findings are mechanisms that transfer, which are hardware-specific verdicts that do not, what must be re-measured, and how to structure the report so a reader cannot mistake one for the other.

dom-08: Plan an evaluation of an agentic coding harness across five programming languages with a fixed budget of about 200 model runs. Choose how to spend the runs across languages, task difficulty and repeats, justify the split with a power argument, and specify how you would report results that are inconclusive.

dom-09: A proposed metric defines "effective context length" as the longest context at which a model still answers a retrieval question correctly. Critique it and propose a better definition that separates retrieval depth from reasoning depth, including how each curve should be measured and what threshold semantics to use.

dom-10: Write a design document for a fail-fast funnel that evaluates new open-weight model releases each week on one machine: stages, the cheapest disqualifying test at each stage, what evidence promotes a candidate, how to avoid re-testing what is already known, and how to keep the process honest when a favourite candidate is failing.
