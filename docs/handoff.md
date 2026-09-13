# Handoff — 2026-09-12 (session close; M38 judge panel COMPLETE, C69 awaiting ruling)

Rewritten in place this session (Claude Code; Fable architect / Opus judges as subagents). Previous <!-- allow-shorthand -->
handoff state (box idle, C68 open) was resumed 2026-09-12 and is superseded by this file.

## Resume checklist

1. Box should be IDLE: `ps -eo pid,etime,command | grep -E 'run\.py|mlx-serve|mlx_vlm\.server|bench_watch'`
   → nothing; `lsof -nP -iTCP:8000 -sTCP:LISTEN` → 0 listeners. No GPU job was armed this session.
2. `git status`: `main_models.yaml` carries EIGHT intentional local-path overrides — NEVER stage it
   from the worktree (HEAD-blob technique, `docs/qualify-a-model.md` Stage 1). Everything else clean.
3. `git log origin/main..main` — unpushed commits from this session (stage-1 `b8f814d` + the M38
   completion commit). Push ONLY on explicit in-turn approval.
4. Open operator decision: **C69** (`docs/open-questions.md`) — the C ladder reorder proposed from the
   judge panel. Nothing else blocks; no measurement is queued.
5. Monitors/agents: none live. Judge packets + all 2,460 verdict files remain under
   `$STACK_WORKDIR/m38_packets/`; stage scratch under `$STACK_WORKDIR/m38_opus_anchor_stage/` and
   `$STACK_WORKDIR/m38_opus_item_stage/` (group lists only).

## What landed this session (2026-09-12, second session)

- Killed 47 orphaned `tail -F` Monitor leftovers (P335).
- **C68 ruled (a)-staged (P336)**: Claude Opus 5 added as the third judge via Claude Code subagents. <!-- allow-shorthand -->
  Stage 1: 60 anchor packets → three-judge gate PASS on every metric (commit `b8f814d`,
  `gate.anchors3.json`). Stage 2 (operator "go"): 760 item packets in 38 groups of 20, rolling waves
  of ten, ~9.6M tokens, ~80 min, 0 null verdicts.
- **M38 COMPLETE**: `gate.json` = three-judge PASS; `ranking.json` written; `pairs_full.jsonl`
  materialises the 380 candidate pairs (the committed `pair_manifest.jsonl` is a unit-test fixture,
  not this run's manifest). All ten pairs decisive after Holm on 38 shared converged items:
  `Qwen3.8-27B-mlx-uniform-4bit` > `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` >
  `Ornith-1.0-35B-mlx-uniform-4bit` > `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` >
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`. Caveats recorded: longer response wins 70 % of
  decided pairs (padding anchors never preferred; order not monotone in length); the uniform-vs-mixed
  `Qwen3.8-27B` pair is the only family-split one (Anthropic 0.342 vs GPT 0.605 for the mixed) and the <!-- allow-shorthand -->
  panel is 2-of-3 Anthropic. Full entry: `docs/campaign-results.md` 2026-09-12 (top). README C
  section + new judge-panel evidence matrix updated; PLAN M38 row DONE.
- **C69 filed (OPEN)**: proposed C ladder — 1st `Qwen3.8-27B-mlx-uniform-4bit`, 2nd
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, shortlist `Ornith-1.0-35B-mlx-uniform-4bit` and
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (last on the panel; text-only tool only).
  Alternative offered: mixed 1st for one-resident-model convenience, uniform 2nd. **Not applied**;
  README ladder is still the C67 order. On a ruling: edit the HEAD blob of `main_models.yaml`
  (C picks + `# CERTIFIED`/PROVISIONAL notes) in the same commit as the README/PLAN/open-questions
  updates.

## Ladder of record (unchanged this session)

B: 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (t0.5, medium, repaired MTP), 2nd
`Qwen3.8-27B-mlx-uniform-4bit` (t0.6, medium, MTP), 3rd `Ornith-1.0-35B-mlx-uniform-4bit`
(native, MTP), 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. C (C67, provisional): 1st
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`
(t0.5, native, draft-OFF); shortlist `Ornith-1.0-35B-mlx-uniform-4bit`,
`Qwen3.8-27B-mlx-uniform-4bit`. README holds the evidence tables.

## Bookkeeping

- Next discussion point P340; next C id C70.
- Judge subagent recipe that worked (for any future panel): export packets with
  `run_judge_pairwise --export-packets`, write group files of ≤20 packet paths, one general-purpose
  subagent per group with the `README_JUDGE.md` rules inline, ingest with `--ingest-packets`, then
  `judge_gate --pairs <anchors+candidates> --verdicts … --judges … --models …`. `judge_gate` needs a
  pairs file that CONTAINS the candidate pairs (`pairs.jsonl` from `judge_anchors` holds anchors
  only) — otherwise it writes an empty ranking silently.
