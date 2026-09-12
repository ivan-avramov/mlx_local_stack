# Handoff — 2026-09-12 15:05 PDT

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
- SUCCESSOR ARMED: M38 judge-panel generation chain, runner pid 77605 (five contenders + an Ornith-1.0-35B-mlx-uniform-4bit matched Math500 leg; arm with the stack config.sh sourced — STACK_WORKDIR must be in env),
  `$STACK_WORKDIR/queue/m38_cjudge/run.py` (queue.pid/queue.log/start.log there). Waits for
  `=== C63 REFERENCE QUEUE DONE ===` + idle box, then per model (`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-mlx-uniform-4bit`, `Ornith-1.0-35B-mlx-uniform-4bit` (+ its math500 m37ref leg), `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`):
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

## M38 judge panel (approved P334; spec `docs/judge-panel-c.md`) — GATE FAIL 2026-09-12

- Generation, anchor build and the panel run are COMPLETE. Reliability gate FAILED
  (`benchmark/results/judge_c_v1/gate.json`, commit `ec6555a`): `degrade_accuracy` 0.80 < 0.85;
  every other metric (order flip, panel kappa, Krippendorff alpha, verbosity, identity tie) passes.
  Panel ran with only TWO judges — Claude Opus 5 was dropped for cost (operator 2026-09-12), leaving <!-- allow-shorthand -->
  `sonnet` (Claude Sonnet 5 as Claude Code subagents, 820 verdicts, ~12M tokens) and
  `codex:gpt-5.6-terra:medium` (820 in-process calls) — so the majority-else-tie rule collapses any
  disagreement to a tie; `sonnet` alone scores 30/30 anchors, `codex:gpt-5.6-terra:medium` alone
  28/30 (misses only `degrade`, via two split-order ties, never a preference for the degraded copy).
  Per the pre-registered rule, `bench/judge_gate.py` refused to write `ranking.json` — **no ranking
  is reported**; a Sonnet-only diagnostic ranking exists in the workdir, not reported. Verdicts,
  pair manifest, `gate.json` and cost log are committed under `benchmark/results/judge_c_v1/`. Full
  table, mechanism and the verbosity-rule spec correction (dated 2026-09-12, does not rescue the
  run): `docs/campaign-results.md` 2026-09-12; PLAN M38 row updated to gate FAIL / ranking withheld.
- **C68 (OPEN, `docs/open-questions.md`)**: operator decision on (a) add Claude Opus 5 as a third <!-- allow-shorthand -->
  judge on all 820 packets (restores the designed three-judge majority; ~13M more tokens, ~2 h in
  waves of ten), (b) pre-registration amendment for a two-judge panel (a single judge's tie does not
  veto the other's verdict on anchors — post-hoc this run would pass 10/10, flagged as such), or
  (c) accept the FAIL, no panel ranking this round, C ladder stays as ruled in C67. Session
  recommendation: run M39 first; if vision already separates the seeing C contenders, (c) is fine,
  otherwise (a).

## M39 vision gate — DONE 2026-09-12

Re-scoped by the operator to a pass/fail gate ("a model that can do some vision", not a ranked
benchmark; spec `docs/vision-smoke-m39.md`). All four seeing contenders ran
`benchmark/vision_gate.py` (harness registered in `benchmark/README.md`): `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
20/20, `Ornith-1.0-35B-mlx-uniform-4bit` 20/20, `Qwen3.8-27B-mlx-uniform-4bit` 19/20,
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 18/20 — all ≥16/20, gate PASSED for all four;
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` untested (text-only). Results committed `04c097a`.
Vision now gates, does not rank; full table `docs/campaign-results.md` 2026-09-12, PLAN M39 row
DONE. The mechanically graded `visionqa` bench (committed `52425d3` on top of `2456ebf`) stays in
the repo, retained but not run. M38's C68 decision (three-judge vs two-judge-amendment vs accept
the gate FAIL) is still OPEN — vision no longer discriminates among the seeing C contenders, so it
doesn't resolve C68 on its own. The qualify-a-model playbook (`docs/qualify-a-model.md`) remains
under separate review; not touched here.

## Session close 2026-09-12 (state for the next session)

- BOX IDLE by design: no GPU job armed. Router down (0 listeners). Every authorized GPU item is done
  (C63, M38 generation, Ornith matched Math500, M39 vision gate). <!-- allow-shorthand -->
- Open operator decisions: C68 (judge panel: third judge / two-judge amendment / accept FAIL);
  nothing else blocks.
- Landed today: C63 + Ornith matched Math500 analyses; C67 reorder; M38 panel (gate FAIL, ranking <!-- allow-shorthand -->
  withheld, verdicts committed); M39 vision gate (all four seeing contenders pass; harness
  `benchmark/vision_gate.py` registered in `benchmark/README.md`); `docs/qualify-a-model.md`
  playbook (agent-facing, cold-verified). 66+ commits unpushed on main; push only on in-turn approval.
- Monitors/agents: none live. Judge packets + verdict files remain under `$STACK_WORKDIR/m38_packets/`.
- If the operator rules C68(a): export Opus packets exist already (`$STACK_WORKDIR/m38_packets/opus/`, <!-- allow-shorthand -->
  82 batches); run them as Claude Code subagents (model opus) with the same batch prompt used for <!-- allow-shorthand -->
  sonnet, ingest with `run_judge_pairwise.py --ingest-packets`, re-run `judge_gate` with
  `--judges sonnet opus codex:gpt-5.6-terra:medium`. <!-- allow-shorthand -->

## Open operator items

- C64 DONE (164f2a5). C65 RULED (M7 dropped; judge panel next). C67 PROPOSED: vision-gated C reorder
  (first `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, second `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`) — awaiting ruling.
- D11 DONE: three HF cards published 2026-09-11 (receipt in benchmark/results/).
- Next discussion point P335; next C id C69.

## Ladder of record (unchanged)

B: 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (t0.5, medium, repaired MTP), 2nd
`Qwen3.8-27B-mlx-uniform-4bit` (t0.6, medium, MTP), 3rd `Ornith-1.0-35B-mlx-uniform-4bit`
(native, MTP), 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. C (provisional): 1st
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (t0.5, native, draft-OFF), 2nd
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. README holds the evidence tables.
