# Handoff — 2026-09-11 13:50 PDT

Rewritten in place this session (Claude Code; architect/worker/reviewer host-model split per the operator's workflow preference). The previous Codex-driven
session ended 2026-09-11 05:26 PDT when its credits ran out mid-heartbeat; its raw log is kept
out of the repo at `$STACK_WORKDIR/devthread_codex_2026-09-11.md`.

## Resume checklist

1. `ps -eo pid,etime,command | grep -E 'run.py|mlx-serve|mlx_vlm.server|bench_watch'` — expect
   runner 59156 (`queue/c_second_reference/run.py`), router 64537, worker 64649 serving
   `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, watcher 71306. If the runner is gone, read
   `queue/c_second_reference/queue.log` for `=== C63 REFERENCE QUEUE DONE ===` or `FATAL`.
2. `wc -l benchmark/results/Qwen3.6-27B-Opus-Distill-OptiQ-4bit/math500.m37ref.jsonl` = C63 progress.
3. Supervision is the DAEMON (`bench_watch.py`, 5-min ticks into
   `queue/c_second_reference/watch_*_full.json`) plus one event-driven Monitor in the session
   (fires on END/RESULT/DONE/FATAL, watcher errors, ≥24 flat ticks, runner exit). Do NOT
   narrate ticks conversationally — that is what exhausted the previous session.
4. `git status`: `main_models.yaml` carries EIGHT intentional local-path overrides — NEVER
   stage it from the worktree (edit the HEAD blob for registry commits). Untracked
   `benchmark/results/**` M34/M34a/M35 files are being audited for a data(bench) commit.
5. No `git push` without in-turn approval. Unpushed commits: check `git log origin/main..main`.

## Current checkpoint (C63)

- C63 = matched Math500 100×1 control for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
  (approved C second choice), deployed t0.3, native routing, draft-OFF, same seeded 100-item set
  as M37/C48, thinking budget 81920, max_tokens 102400. Seeded 5-item pilot passed
  (1 degenerate_repetition, max 4827 s). Full arm started 2026-09-10 23:24:52.
- 09:20 PDT: 59/100, 0 transport errors, 3 degenerate_repetition non-convergences (35 % of
  wall), mean 693.6 s/item (median 289 s) → ~7.9 h remaining from the mean, plus tail
  uncertainty (longest item 82,237 tok / 4827 s). Expected finish late afternoon 2026-09-11.
- On completion the runner grades, logs `RESULT`, stops the router, logs the DONE marker.
  Owed then: paired same-item comparison against M37 (`Qwen3.8-27B-mlx-uniform-4bit` medium
  99 % strict; `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` medium 97 %) and C48
  (`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` t0.5 97 %), quality/tokens-per-task/latency/
  runaway tax, README evidence tables + campaign-results + PLAN C63 row, and a B/C ladder
  recommendation for operator approval (no automatic reorder).
- SUCCESSOR ARMED: M38 judge-panel generation chain, runner pid 57189,
  `$STACK_WORKDIR/queue/m38_cjudge/run.py` (queue.pid/queue.log/start.log there). Waits for
  `=== C63 REFERENCE QUEUE DONE ===` + idle box, then per model (`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`,
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-mlx-uniform-4bit`,
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`): fresh draft-OFF overlay, seeded 5-item pilot, full 40 on
  `cjudge` (tune `m38`), grade (acc null by design), router stop; ends `=== M38 CJUDGE QUEUE DONE ===`.
  Lower-bound cost ~1–4 h each for the first three, ~13 h for the last. A session Monitor watches it.
  Stop the waiting successor BEFORE intentionally stopping C63.

## Recently landed (for context, details in campaign-results / PLAN)

- C62 RULED 2026-09-10: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` production default t0.5
  (commit c01a0c5), applied to registry + both benchmark carriers. Temperature ladder C48/C48b
  complete: coding strict 84/85/87/85/87 % and math 96/97/97/95/98 % at t1.0/0.7/0.5/0.4/0.3.
- M37 complete 2026-09-10: medium-effort Math500 for `Qwen3.8-27B-mlx-uniform-4bit` and `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 99 % and
  97 % strict, all converge. No approved reorder.
- C61/M36 2026-09-10: repaired MTP certified for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`.

## M38 judge panel (approved P334; spec `docs/judge-panel-c.md`)

- Committed: corpus `benchmark/corpora/cjudge_v1.jsonl` (18 public + 22 domain), loader, spec.
- Uncommitted, under final cold confirmation: `bench/judge_anchors.py`, `judge_pairwise.py`,
  `run_judge_pairwise.py`, `judge_gate.py`, `judge.py` (ids `claude-opus-5`/`claude-sonnet-5`) +
  tests (suite 1449 passed). Commit after the confirmation pass; if the session dies first, run the
  suite and commit them as `feat(bench): M38 judge panel modules`.
- After generation completes: build anchors (`judge_anchors.py`, seed 38) → `run_judge_pairwise.py`
  (API judges; needs ANTHROPIC key in env + codex CLI) → `judge_gate.py` (gate FIRST; no ranking on
  FAIL) → campaign-results entry, README C table, operator approval for any rank change (C67).

## Open operator items

- C64 DONE (164f2a5). C65 RULED (M7 dropped; judge panel next). C67 PROPOSED: vision-gated C reorder
  (first `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, second `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`) — awaiting ruling.
- D11 DONE: three HF cards published 2026-09-11 (receipt in benchmark/results/).
- Next discussion point P335; next C id C68.

## Ladder of record (unchanged)

B: 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (t0.5, medium, repaired MTP), 2nd
`Qwen3.8-27B-mlx-uniform-4bit` (t0.6, medium, MTP), 3rd `Ornith-1.0-35B-mlx-uniform-4bit`
(native, MTP), 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. C (provisional): 1st
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (t0.5, native, draft-OFF), 2nd
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. README holds the evidence tables.
