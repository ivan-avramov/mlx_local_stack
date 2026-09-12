# Vision GATE for the seeing contenders (M39) — spec of record

Status: RE-SCOPED by the operator 2026-09-12 ("I don't want any benchmarks for vision … I want a
model that can do some vision"): a PASS/FAIL gate, not a ranking. The mechanically graded
`visionqa` corpus/loader/grader below remain in the repo (committed 52425d3, 1055b6d) but are
NOT run. Agent-facing: rules, not rationale.

## Gate protocol (runs as `benchmark/vision_gate.py`)

- 20 COCO val2017 photos with 5 human captions each (`benchmark/corpora/vision_gate_v1.jsonl`,
  ids + captions only; images fetched at run time under `$STACK_WORKDIR/vision_gate_images/`).
- Per image, two turns at the deployed tune with thinking ON: (1) "Describe this image in detail."
  with the image; (2) the ground-truth captions shown, "Did your description correctly capture
  what is in the image? Reply with exactly one word: PASS or FAIL."
- Output per model: pass count / 20, fail, null (unparseable), raw descriptions kept for reading.
  Self-grades are lenient by construction: the report pairs the count with a by-eye read of five
  descriptions per model. Gate: a model "can do some vision" at ≥ 16/20 self-PASS with no
  contradicted PASS in the by-eye read; below that, flag to the operator.
- Chain `$STACK_WORKDIR/queue/m39_vision_gate/run.py`: per model fresh draft-OFF overlay, router,
  `probe_vision.py --model` SEES gate, the script, RESULT line, router stop; DONE marker
  `=== M39 VISION GATE QUEUE DONE ===`.

---

## (Retained, not run) Vision smoke — mechanically graded visual-QA
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
