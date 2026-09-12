# Vision smoke for the seeing contenders (M39) — spec of record

Status: BUILD approved by the operator 2026-09-12 ("why not 1 now?"); GPU arm needs an explicit go.
Closes the C67 gap: vision is a hard gate for the C first pick but is verified only by a one-image
"sees" probe. Agent-facing: rules, not rationale.

## Purpose

Rank the four vision-capable contenders on mechanical visual-QA accuracy so vision can rank, not
just gate. No judges.

## Contenders (deployed tunes, thinking ON, predictor OFF, `--sampling-profile deployed`)

`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-mlx-uniform-4bit`,
`Ornith-1.0-35B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`.
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is text-only and excluded.

## Corpus `visionqa` v1 (40 items; ids + answers committed at `benchmark/corpora/visionqa_v1.jsonl`;
## images fetched at load time into the HF cache, NEVER committed)

| source (HF) | license | n | grading |
|---|---|---|---|
| ChartQA val (`HuggingFaceM4/ChartQA`) | GPL-3.0 (ids-only storage) | 15 | relaxed: numeric within ±5 %, else normalized exact match |
| RICO ScreenQA-Short (`rootsautomation/RICO-ScreenQA-Short`) | CC BY 4.0 | 10 | normalized exact match OR token-F1 ≥ 0.5 |
| AI2D (`lmms-lab/ai2d`) | CC BY-SA | 10 | option letter exact match |
| TextVQA val (`facebook/textvqa`) | CC BY 4.0 | 5 | VQA accuracy: match ≥ 3 of 10 references → 1, else min(matches/3, 1) |

- Seeded selection (seed 39) after filtering: image ≤ 2 MP, question ≤ 60 words, answer non-empty,
  no duplicate images. Row: `{id, source, source_id, image_ref, question, answer(s), choices?, meta}`.
  Provenance file `visionqa_v1.provenance.json` (dataset revisions, filters, seed, counts, sha256).
- Prompt suffix: "\n\nAnswer with the final answer only, inside \\boxed{}." (reuses the math extractor).
  AI2D prompts list the options as `A) … D) …` and ask for the letter.
- Loader: `bench/benchmarks.py` SPECS `"visionqa": {"kind": "vision", "answer_type": "visionqa", "gated": False}`;
  `build_messages` emits an OpenAI content list: text part + `image_url` data URL (base64 PNG/JPEG),
  mirroring `benchmark/probe_vision.py`. Never wrapped by the depth harness.
- Grader: per-source rule above; `acc` and `acc_strict` (non-converged → wrong) as elsewhere.

## Generation (GPU)

Chain runner `$STACK_WORKDIR/queue/m39_visionqa/run.py` (pattern: `queue/m38_cjudge/run.py`):
idle-box check, per model: fresh draft-OFF overlay, router with the mandatory env, C35 check,
seeded 5-item pilot (`--limit visionqa=5 --seed 0`), full 40, `bench_watch`, grade, RESULT, router
stop; tune `m39`; ends `=== M39 VISIONQA QUEUE DONE ===`. Record image-token count and prefill
time per item (first vision cost measurement on this stack).

## Reporting

Four numbers per model: `acc`, `acc_strict@81920`, conv %, tokens/task; paired deltas with
`stats.cluster_bootstrap` over items; MDE at n=40 ≈ ±20pp — state it. Per-source breakdown.
campaign-results entry, README C table evidence, PLAN M39 row. Rank changes → operator.
