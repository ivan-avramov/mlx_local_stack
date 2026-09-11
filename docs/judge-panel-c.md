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
`Qwen3.8-27B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`,
`Ornith-1.0-35B-mlx-uniform-4bit` (added under C67, 2026-09-11; deployed tune t0.4, native expert
routing, draft-OFF). k=1, seeded per (item, sample). Budgets unchanged (thinking_budget 81920,
max_tokens per registry).

## Corpus `cjudge` (v1, 40 prompts, committed at `benchmark/corpora/cjudge_v1.jsonl`)

- 18 public prompts (hand-curated from a seeded draw of 30): a permissively licensed pairwise-judged prompt set (Arena-Hard-style or
  WildBench), filtered to software/system design, ML/AI research, planning and brainstorming;
  English; text-only; no tool use; no images; prompt ≤ 1,500 tokens. Selection is seeded and
  recorded (`source`, `source_id`, `license`, `category`, `selection_seed`) in
  `benchmark/corpora/cjudge_v1.provenance.json` with the file sha256.
- 22 domain prompts (`source: "operator-domain"`, ids `dom-01..22`), verbatim from the
  "Domain prompts" section below (dom-11..22 added 2026-09-11 after the first public draw
  proved too generic for the role: the public pool is kept to the 18 prompts that are genuinely
  design/research tasks).
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

- Units: (item, A output, B output) over the 40 items, all 10 model pairs (five contenders,
  `Ornith-1.0-35B-mlx-uniform-4bit` added under C67), both orders, 3 judges
  (40 × 10 × 2 × 3 = 2,400 calls + 180 anchor calls).
- Endpoint: paired preference rate per pair with `stats.cluster_bootstrap` over items;
  Holm across the 10 pairs; TOST ±5pp for `equivalent`; report tokens/task, latency and
  runaway share alongside (the four numbers). MDE at n=40 ≈ ±20pp (`stats.mde(40)` = 19.8pp) — state it.
- Output `benchmark/results/judge_c_v1/{gate.json, ranking.json}`; campaign-results dated
  entry; README C table update; rank changes → operator approval (C67, the contender-set/reorder
  ruling, is closed 2026-09-11; M38's own ranking output is a separate approval).

## Domain prompts (verbatim corpus text; ids dom-01..dom-22)

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

dom-11: A team wants retrieval-augmented generation over a corpus of internal engineering documents that changes daily. Design the system end to end: chunking, embedding refresh, retrieval strategy, how the model is grounded, how to evaluate answer faithfulness, and the three failure modes you would expect first in production.

dom-12: Compare the main approaches to compressing or evicting the KV cache in long-context transformer inference. For each, explain the mechanism, what it costs in quality and where, and which workloads it suits. Finish with a recommendation for a coding agent that reads whole repositories.

dom-13: Design a public HTTP API for a service that runs long, cancellable jobs on a single GPU host with a queue. Cover resource naming, job lifecycle and state machine, idempotency, cancellation semantics, back-pressure, observability, and versioning. Give the tradeoffs you rejected.

dom-14: You must review a proposed A/B test of a new ranking model where the metric moved by 0.8 percent with a p-value of 0.03 after three weeks. Write the review: what would make you trust or distrust the result, what additional analyses you would demand, and how you would decide whether to ship.

dom-15: Propose a research agenda for reducing hallucinated citations in language-model outputs. Structure it as three to five concrete experiments with hypotheses, datasets or how you would build them, metrics, expected outcomes, and what each result would change about the next step.

dom-16: Design the data pipeline and storage layout for benchmark results produced by dozens of model-configuration runs per week, where any result may need to be regraded later without regeneration. Address provenance, immutability, schema evolution, deduplication and how a reader reconstructs exactly what was run.

dom-17: Write a threat model for a local developer tool that lets an autonomous coding agent execute shell commands and edit files on a workstation. Enumerate assets, trust boundaries, realistic attackers, the highest-risk attack paths, and the mitigations you would ship first versus later, with reasoning.

dom-18: A startup asks whether to fine-tune an open-weight model or rely on prompting and retrieval for a customer-support assistant. Lay out how you would reach a decision: the questions to answer first, the experiments that discriminate between the options, the cost model, and the conditions under which each answer is right.

dom-19: Design an observability strategy for an inference server that runs one large model with speculative decoding, session caching and a memory cap. Say what to measure, at what granularity, which signals detect a stalled generation versus a legitimately long one, and how alerts avoid paging on healthy long requests.

dom-20: Critique the practice of ranking models on a single aggregate leaderboard score. Then propose an alternative reporting design for a team choosing a model for a specific role, including how to present uncertainty and conflicting evidence so that the decision is defensible six months later.

dom-21: Explain the tradeoffs between mixture-of-experts and dense transformer architectures for local inference on a memory-constrained device, covering memory, latency, quantization behaviour, and quality per parameter. Recommend how a practitioner should decide between them for an interactive assistant.

dom-22: Plan the first ninety days of a technical program that migrates a research group from ad hoc notebooks to a reproducible experimentation platform. Include the sequencing, what you would deliberately not build, how you would measure adoption, and the organisational risks that usually sink such efforts.
