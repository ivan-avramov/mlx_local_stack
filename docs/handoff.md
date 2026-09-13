# Handoff — 2026-09-12 ~23:25 PDT (session restart; M40 chain LIVE, pick A 3 of 6 arms done)

Rewritten in place. Phase 1 is closed (B ladder C57, C ladder C70). Phase 2 has started: **M40 (MTP-ON
certification of both picks) is RUNNING unattended** under a reviewed chain runner. The previous session's
Monitor died with that session; the runner did not (nohup, detached).

## Resume checklist (do these FIRST, in order)

1. **Runner alive?** `. ${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh; Q=$STACK_WORKDIR/queue/m40_mtp;
   ps -o pid,etime,command -p $(cat $Q/queue.pid)` — expect `run.py` (pid 74875, started 2026-09-12 20:58 PDT).
   If gone: `grep -E 'FATAL|=== M40' $Q/queue.log` — a FATAL preserves state; read the traceback before touching
   anything. NEVER restart the runner while a `run.py generate`, `vision_gate.py` or `bench.run_reasoning` driver
   or an `mlx_vlm.server` worker is alive (`pgrep -fl`).
2. **Progress**: `tail -20 $Q/queue.log` (line grammar: RUN / C35 check / worker cmdline / PILOT / END / SUMMARY /
   SCORE / RESULT / WARN / FATAL / `=== M40 <pick> DONE ===` / `=== M40 MTP QUEUE DONE ===`), the per-arm
   `$Q/watch_*.json` bench_watch ticks (5-min), and row counts under `benchmark/results/<pick>/`.
   **At session close (2026-09-12 23:25 PDT), pick A results already logged (RESULT lines in queue.log):**
   math500 `m40on` **99 % strict, 100/100 converged** (OFF `m37med`: 97 %; +2pp point, paired CI owed via
   compare_predictor); cjudge `m40on` 40/40 converged (acc=None is expected, kind=open); vision_gate `m40on`
   **20/20** (OFF `v1` 20/20). Pilot decode 50–57 tok/s vs 24.6 OFF (≈2.2×). In flight at close: pick A depth
   128K ON (`reasoning.m40on-d128k`, 3 draws, bound 8 h) → then OFF overlay: depth OFF, vision OFF → pick A DONE
   → pick B. Every C35 check so far OK (draft_kind=mtp, overlay sha match, worker carries the normfix sidecar).
3. **Re-arm supervision in the new session** — one event Monitor on `$Q/queue.log` (tail -F + `/usr/bin/grep
   --line-buffered` alternation incl. FATAL/TIMEOUT/WARN/MISMATCH/RESULT/DONE + a runner-exit line; include a
   SELFTEST known-positive echo). Never narrate ticks.
4. `git status`: `main_models.yaml` carries intentional local-path overrides — NEVER stage it from the worktree
   (HEAD-blob technique: `git hash-object -w` + `update-index --cacheinfo`, see `docs/qualify-a-model.md`).
5. Unpushed: `git log --oneline origin/main..main` (at close: a15d62f, cad8fbb, 9450670, a214366 + this handoff commit).
   Push ONLY on explicit in-turn approval.

## M40 — what is running and what is owed

- Runner + spec + README: `$STACK_WORKDIR/queue/m40_mtp/{SPEC.md,run.py,helpers.py,README.md}` (Sonnet-built from
  spec, two cold Opus review rounds, all defects fixed; `run.py --dry-run` is safe and prints the whole plan). <!-- allow-shorthand -->
  Overlays `on_<pick>.yaml` (pick keeps `draft_kind: mtp` + local sidecar, every other entry stripped) and
  `off_<pick>.yaml` (all draft stripped); shas logged per arm. Docker (OrbStack) + `mlx-evalplus-native:recovery`
  are prechecked at start (both were verified up at 20:58).
- Order: pick A = `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (t0.5 medium): ON overlay → math500 `m40on`
  (100, ids = `queue/resolution/ids.json`) → cjudge `m40on` (40) → vision_gate `m40on` (20) → depth 128K
  `reasoning.m40on-d128k.json` (3 draws) → OFF overlay → depth `m40off-d128k` → vision_gate `m40off` → DONE.
  Then pick B = `Qwen3.8-27B-mlx-uniform-4bit` (t0.6 medium): same, plus humanevalplus + mbppplus 100×1 in BOTH
  states (`m40on`/`m40off`, native ARM64 grading via `queue/resolution/native_grade.py`). Bounds: math 12 h,
  cjudge 8, coding 12, depth 8, vision 2; pilot projection guard WARNs at 60 % / FATALs over the bound.
  Lower-bound wall ≈5 h pick A, ≈7 h pick B (pilots suggest faster).
- **Analysis owed on each pick's DONE (pre-registered, PLAN M40 row):**
  - `cd benchmark && ../.venv-bench/bin/python -m bench.compare_predictor --model <pick> --bench math500 --tune-a m37med --tune-b m40on`
    (pick B coding: `--bench humanevalplus|mbppplus --tune-a m40off --tune-b m40on`). Verdict PASS/FAIL/INCONCLUSIVE
    on `acc_strict` at ±5pp; it REFUSES unless only `draft_kind` differs — a refusal is a finding, not a bug to bypass.
    `compare.py` is NOT the instrument (refuses across draft state by design).
  - cjudge: `run_judge_pairwise --models <pick> --pair-tunes m38 m40on --anchors benchmark/results/judge_c_v1/pairs.jsonl
    --export-packets $STACK_WORKDIR/m40_packets_<pick> --judges opus sonnet` (+ codex in-process), judge as <!-- allow-shorthand -->
    Claude Code subagents with the `README_JUDGE.md` rules (≤20 packets per agent, groups file, blind), ingest,
    `judge_gate --pairs <anchors+the 40 tune pairs> --judges sonnet opus codex:gpt-5.6-terra:medium`. <!-- allow-shorthand -->
    Read: FAIL only if OFF preferred with Holm p<.05; else "no detectable drift at n=40 (MDE ±20pp)".
  - vision: pass counts `vision_gate.m40on.summary.json` vs `vision_gate.m40off.summary.json` (ON ≥16/20, ≥OFF−2);
    provenance jsons beside them. depth: `reasoning.m40on-d128k.json` vs `m40off-d128k` (strict draws ≥ OFF−1 of 3,
    budget-hits not higher). Perf: acceptance (rows' `draft` field; pooled), decode_tps, wall — report separately;
    runaway tax in TOKENS.
  - Decision rule: all axes pass → pick ships ON (registry already ON; record certification comment) and Phase 2
    runs ON for it; any FAIL → flip that pick's `draft_kind` OFF in the registry (HEAD-blob technique, same commit as
    the campaign-results entry), reopen certification. Never auto-change picks; surface for the operator.
  - Then: campaign-results entry, README evidence, PLAN M40 row, open-questions if a decision arises.
- Known limitation to state in the write-up: depth/vision ON arms are certified by worker cmdline only (no reachable
  draft counter; `draft_counters: null` in their provenance jsons). Rerun hazards documented in the runner README
  (vision resume is provenance-guarded; coding re-grade needs the native_grade_archive dir removed).

## After M40 (Phase 2 queue, PLAN "Phase 2" section)

M41 capacity + depth ladders on pick A in the shipped predictor state (its first long-context evidence; 256K
`mx.get_peak_memory`, reasoning + retrieval ladders, decode/prefill per rung) → M42 KV-lever OFAT (fp16 vs
turboquant kv4; fp16 ≈16 GiB @256K on 16 full-attention layers) → D14 transfer write-up (zero GPU, parallel).
Each arm needs its own explicit go.

## Landed this session (2026-09-12, all committed)

C68 (a)-staged → M38 three-judge panel COMPLETE (gate PASS, all ten pairs decisive) → C69 → P342 length-controlled
re-analysis (top pair length-confounded) → **C70 RULED: C 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd
`Qwen3.8-27B-mlx-uniform-4bit`**, shortlist `Ornith-1.0-35B-mlx-uniform-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`;
P341 PLAN hygiene (27 rows); P343 dropped; **C71 RULED** (predictor-OFF for selection; shipped triple certified ON on
every axis; Phase 2 runs in the shipped state; AGENTS.md amended); Phase 2 section in PLAN; analysis tooling
`bench/compare_predictor.py` + `--pair-tunes` (9450670). Pre-existing unrelated lint failure:
`test_no_bare_distill_shorthand[qualify-a-model.md]` (docs debt, not touched).

## Ladder of record

B (C57): 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`, 3rd
`Ornith-1.0-35B-mlx-uniform-4bit`, 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. C (C70, provisional): 1st
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`; shortlist
`Ornith-1.0-35B-mlx-uniform-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`.

## Bookkeeping

- Next discussion point P345; next C id C72.
- Judge subagent recipe that worked (M38): export packets → group files of ≤20 paths → one general-purpose subagent
  per group with the blind rules inline → `--ingest-packets` → `judge_gate` with a pairs file that CONTAINS the
  candidate pairs (`pairs.jsonl` holds anchors only; otherwise the ranking is silently empty).
