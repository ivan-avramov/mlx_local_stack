# Handoff — 2026-09-12 (session close; Phase 1 CLOSED — C70 applied; Phase 2 queued, M40 approved, arm pending go)

Rewritten in place this session (Claude Code; Fable architect / Opus judges as subagents). Previous <!-- allow-shorthand -->
handoff state (box idle, C68 open) was resumed 2026-09-12 and is superseded by this file.

## Resume checklist

1. Box should be IDLE: `ps -eo pid,etime,command | grep -E 'run\.py|mlx-serve|mlx_vlm\.server|bench_watch'`
   → nothing; `lsof -nP -iTCP:8000 -sTCP:LISTEN` → 0 listeners. No GPU job was armed this session.
2. `git status`: `main_models.yaml` carries EIGHT intentional local-path overrides — NEVER stage it
   from the worktree (HEAD-blob technique, `docs/qualify-a-model.md` Stage 1). Everything else clean.
3. `git log origin/main..main` — pushed through `fa8368c` (operator approval 2026-09-12); the P341/P342
   commit after it is unpushed unless the log says otherwise. Push ONLY on explicit in-turn approval.
4. **Next work = M40** (`docs/PLAN.md` Phase 2 section): MTP-ON certification of both picks across every
   axis (Math500, cjudge + paired judge pass, vision gate, 128K depth rung, pick B MBPPPlus). Scope APPROVED
   2026-09-12; **arming needs an explicit operator go** (propose the pick-A Math500 5-item seeded pilot first).
   Then M41 (capacity + depth on pick A), M42 (KV lever), D14 (transfer write-up), all in the shipped
   predictor state (C71). P343 dropped. No other open decision.
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

- Next discussion point P345; next C id C72.
- P343 DROPPED 2026-09-12 (kept for the record — scope was: `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`
  (M16) — vision tower present, MTP head NOT split, Stages 0–1 + tune ladder done (t0.55, hep 86 / mbpp 74
  strict); missing: matched Math500, cjudge generation + judging vs the five (≈1,140 verdicts, ~15M judge
  tokens), vision gate, Stage 9 MTP split/probe if promoted).
- P344 DONE: Phase 1 closed, Phase 2 section written into PLAN (M40/M41/M42/D14) with pre-registered criteria; C71 rule amendment ruled.
- M40 mechanics: ON arms need a fresh overlay per pick with `draft_kind: mtp` + the certified sidecar path, `MLX_SERVE_CONFIG` on the driver, C35 check that the first manifest reads `runtime.draft_kind: mtp` AND the worker cmdline carries `--draft-*`; tune labels `m37ref-mtpon` / `m38-mtpon` / `v1-mtpon` / `d128k-mtpon`; the OFF rows they pair with are `math500.m37med` (pick A) / `math500.m37ref`-equivalent (pick B: check the M37 tune label), `cjudge.m38`, `vision_gate.v1`, `reasoning.json` (pick B M11 128K draws). `compare.py` refuses across draft state by design — the ON-vs-OFF read is a paired analysis, run it with the fingerprint check consciously overridden for that one seam and say so in the entry.
- Judge subagent recipe that worked (for any future panel): export packets with
  `run_judge_pairwise --export-packets`, write group files of ≤20 packet paths, one general-purpose
  subagent per group with the `README_JUDGE.md` rules inline, ingest with `--ingest-packets`, then
  `judge_gate --pairs <anchors+candidates> --verdicts … --judges … --models …`. `judge_gate` needs a
  pairs file that CONTAINS the candidate pairs (`pairs.jsonl` from `judge_anchors` holds anchors
  only) — otherwise it writes an empty ranking silently.
