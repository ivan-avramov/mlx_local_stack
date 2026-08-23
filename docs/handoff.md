# Handoff — rewritten 2026-08-22 ~20:30 (single-session consolidation; M19 deployed redo: hep verdict in, mbpp leg live)

Single box (M5 Max 64 GB), SINGLE attended session owns everything (operator ruling
2026-08-22: "this is all you"). A stray 3-day-old background session ("Prevent system
pollution outside workdir") had inherited the pre-restart context, ran the retraction and the
first deployed-redo probes concurrently (→ the 10:00–10:22 contention, below), delivered a
full state dump, and STOOD DOWN. If processes you didn't launch appear (`pgrep -f "run.py
generate"`), investigate before acting; do not assume they are yours or dead.

## O36 RETRACTION (context for everything below)

All original M19/M20 "t0.5" work (scans, DNF-first, rungs, gate-3 2×50) omitted
`--sampling-profile deployed` and silently ran the RETIRED `production` profile (min_p 0.03,
presence_penalty 0.3, silently clamped thinking_budget 49152). Rows quarantined as tune
**`t0.5prod`** (graded; real measurements of a config we don't ship). The t0.6 arms are clean
deployed rows. O36 (run.py default-profile footgun) awaits an operator ruling.

## Live right now (RESTART-SAFE)

- **M19 deployed gate-3, mbpp leg**: `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`, driver pid
  36174, **nohup-detached — survives a claude-code restart**, resumes on done rows. 36/50 at
  20:15; 3 errors, all known hard-core runaways; zero loops. Log:
  `$STACK_WORKDIR/status/gate3_m19_deployed.log`. Relaunch if dead (from `$STACK_REPO/benchmark`):
  `nohup $STACK_REPO/.venv-bench/bin/python run.py generate --models
  Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit --benches humanevalplus,mbppplus --limit
  humanevalplus=50,mbppplus=50 --sampling-profile deployed --temp 0.5 --tune t0.5
  --probe-timeout 3600 --order model > $STACK_WORKDIR/status/gate3_m19_deployed.log 2>&1 </dev/null &`
- Two `bench_watch` watchers (nohup, survive): `$STACK_WORKDIR/status/gate3_dep_{hep,mbpp}.watch`.
  ⚠️ Relaunching bench_watch requires `PYTHONPATH=$STACK_REPO/benchmark` in the env.
- Session-tracked waiters die with a restart; the watchers + this file carry the state.

## M19 deployed-redo results so far (all `--sampling-profile deployed` EXPLICIT)

- Ladder: scan `HumanEval/2` CONV at t0.5 (1,693 tok); DNF-first 5/10 conv + 4
  capped-indeterminate + `Mbpp/440` length-fail; sentinels 5/5 CONV; n=15 rung acc 92.9
  [79,100] / strict 86.7 / conv 100% + `HumanEval/108` DNF (new item, clean at t0.6).
- **Gate-3 hep GRADED: t0.5 acc 89.1% [78,98] / strict 82.0% / 4 DNFs
  {HumanEval/108,32,99,132} vs t0.6 acc 95.6% [89,100] / strict 86.0% / 5 DNFs
  {2,82,32,99,39}.** DNF rate flat, set churns non-monotonically (fixed 3, kept hard core
  {32,99}, minted 2). **The production-profile "knee" does NOT exist at the deployed config —
  t0.6 stands on hep**; mbpp seals it.
- **Attribution finding:** the t0.5prod loop plague (17+16 degenerate_repetition/50) does NOT
  reproduce at deployed t0.5 (zero loops in 86+ items) → loops were a PRODUCTION-KNOB artifact
  (clamped 49152 budget and/or min_p 0.03 / presence_penalty 0.3), not temperature.

## On mbpp completion (the closeout)

1. Grade mbpp t0.5 in docker; **evalplus flake pattern**: "no results"/"timed out" thrice
   today, each time the results file landed LATE and a zero-GPU re-grade certified clean —
   always retry before trusting a null. Regrade t0.6 mbpp (zero GPU) for the pair.
2. State the M19 verdict (expect t0.6 stands both benches; cite CIs, MDE ±18pp; knee
   RETRACTED as profile artifact). Update `docs/PLAN.md` M19/M20 rows + ledger entry.
3. Commit rows/manifests/scores (hep artifacts committed at this checkpoint; the
   `humanevalplus.t0.5.manifest.json` in results/ is now the LEGITIMATE deployed manifest).
4. **M20 deployed ladder** for `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` (t0.55 rung
   candidate operator-approved): capped scan on old t0.6 DNF set {HumanEval/83,32,99,151,132,
   86,81; Mbpp/620,306,757,564,429,739,440} + 5 clean sentinels, `--max-tokens 8192
   --probe-timeout 900`, self-cleaning mv OUT of results/ → DNF-first → rung → gate-3.
   Expectation after M19: its t0.5prod loop catastrophe also evaporates; t0.6 likely stands.
5. Then the queue: M3/M4 opencode (roster ruling 2026-08-22:
   `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` ADDED, at whatever tune the deployed ladder
   certifies) → M5 remnant → M18 BFCL → M7 → M21 (still justified: D13 family-matched cells,
   `benchmark/m1/dnf_sweep.py`) → M22 → D10 → F1/F2 → M11/M12 → D11 → D6 → M14.

## Contamination audit (2026-08-22, settled)

Overnight gate-3 t0.5prod arms: SINGLE-TENANT (router log: zero switches, zero foreign POSTs
Aug 21 13:02→Aug 22 10:00). Poisoned window: **10:00–10:22 only** (two sessions, 4 model
switches in 15s, one TTFT 292s) — wall-times from that window are unusable; all artifacts from
it are either quarantined (`m20b_scan/prod_*`) or token-verdict-only. No campaign verdict
consumes contaminated timing.

## Push state

Local-only commits (NO push without explicit in-turn operator approval): 495279a (D13 tool),
bf11b6c (retraction), 4d24722 (probe cleanup), ad9d194 (ledger retraction entry) + this
checkpoint's. origin/main = a2869a8. Verify pushes with `git ls-remote`, never rtk output.

## Traps refreshed today

evalplus-in-docker returns null then lands the results file late (retry, zero-GPU). bench_watch
needs PYTHONPATH. The watcher's ">20% harness errors — stop and fix" fires on prefixes where
the errors are known hard-core runaways — check the item IDs before acting. `run.py generate`
DEFAULTS to the retired production profile (O36) — every command must carry
`--sampling-profile deployed`. Probe artifacts never live in `benchmark/results/` (mv out).

**Order of resumption: this file → `docs/PLAN.md` → `$STACK_WORKDIR/status/` (live runs).**
