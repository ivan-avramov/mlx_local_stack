# Handoff — 2026-09-12 (session close; M38 COMPLETE, C70 applied, PLAN hygiene done, P343 dropped)

Rewritten in place this session (Claude Code; Fable architect / Opus judges as subagents). Previous <!-- allow-shorthand -->
handoff state (box idle, C68 open) was resumed 2026-09-12 and is superseded by this file.

## Resume checklist

1. Box should be IDLE: `ps -eo pid,etime,command | grep -E 'run\.py|mlx-serve|mlx_vlm\.server|bench_watch'`
   → nothing; `lsof -nP -iTCP:8000 -sTCP:LISTEN` → 0 listeners. No GPU job was armed this session.
2. `git status`: `main_models.yaml` carries EIGHT intentional local-path overrides — NEVER stage it
   from the worktree (HEAD-blob technique, `docs/qualify-a-model.md` Stage 1). Everything else clean.
3. `git log origin/main..main` — pushed through `fa8368c` (operator approval 2026-09-12); the P341/P342
   commit after it is unpushed unless the log says otherwise. Push ONLY on explicit in-turn approval.
4. No open operator decision: **C70 RULED** 2026-09-12 (mixed first, uniform second) and applied. No
   measurement is queued; PLAN hygiene pass 2026-09-12 tagged every stale row. **P343 (one more C candidate,
   `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`) DROPPED by the operator 2026-09-12.** Next block is P344
   (Phase 2 plan) once the operator approves its scope.
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
- **C69 RULED (operator "i take your picks")**: C 1st `Qwen3.8-27B-mlx-uniform-4bit`, 2nd
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, shortlist `Ornith-1.0-35B-mlx-uniform-4bit` (3rd) and
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (4th; keeps role main as the fast text-only tool).
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` off the C table. Applied via the HEAD-blob technique
  (`git hash-object -w` + `update-index --cacheinfo`, worktree overrides untouched). No tune or
  predictor changed, so no carrier edits were needed.

## Ladder of record


B (C57, unchanged): 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (t0.5, medium, repaired MTP),
2nd `Qwen3.8-27B-mlx-uniform-4bit` (t0.6, medium, MTP), 3rd `Ornith-1.0-35B-mlx-uniform-4bit`
(native, MTP), 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. C (C70, provisional): 1st
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`; shortlist
`Ornith-1.0-35B-mlx-uniform-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`. README holds the
evidence tables.

## Bookkeeping

- Next discussion point P345; next C id C71.
- P343 DROPPED 2026-09-12 (kept for the record — scope was: `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`
  (M16) — vision tower present, MTP head NOT split, Stages 0–1 + tune ladder done (t0.55, hep 86 / mbpp 74
  strict); missing: matched Math500, cjudge generation + judging vs the five (≈1,140 verdicts, ~15M judge
  tokens), vision gate, Stage 9 MTP split/probe if promoted).
- P344: declare Phase 1 closed and write the Phase 2 (Optimization) plan — awaiting operator scope approval.
- Judge subagent recipe that worked (for any future panel): export packets with
  `run_judge_pairwise --export-packets`, write group files of ≤20 packet paths, one general-purpose
  subagent per group with the `README_JUDGE.md` rules inline, ingest with `--ingest-packets`, then
  `judge_gate --pairs <anchors+candidates> --verdicts … --judges … --models …`. `judge_gate` needs a
  pairs file that CONTAINS the candidate pairs (`pairs.jsonl` from `judge_anchors` holds anchors
  only) — otherwise it writes an empty ranking silently.
