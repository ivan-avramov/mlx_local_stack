# Handoff — rewritten 2026-08-22 ~21:50 (M19 CLOSED: t0.6 certified; M20 deployed ladder live)

Single box (M5 Max 64 GB), SINGLE attended session owns everything (operator ruling
2026-08-22). If generate processes you didn't launch appear (`pgrep -f "run.py generate"`),
investigate ownership before acting — do not adopt or kill on sight.

## O36 (context, still awaiting operator ruling)

`run.py generate` DEFAULTS to the retired `production` profile. **Every generate command
must carry `--sampling-profile deployed` EXPLICITLY.** The original M19/M20 "t0.5" rows are
quarantined as tune `t0.5prod`.

## M19 — CLOSED 2026-08-22: t0.6 STANDS on both benches

`Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`, deployed gate-3 2×50, paired seeds, budget 81920:
- hep: t0.5 acc 89.1 [78,98] / strict 82.0 / 4 DNFs vs t0.6 95.6 [89,100] / 86.0 / 5 DNFs
- mbpp: t0.5 acc 82.6 [69.6,93.5] / strict 76.0 / 4 DNFs vs t0.6 86.7 [75.6,95.6] / 78.0 / 5 DNFs

t0.5 shows no advantage on any endpoint; DNF sets churn non-monotonically (hard cores:
hep {32,99}, mbpp {306,440}); **zero loops in 96 deployed-t0.5 rows** → the t0.5prod loop
plague was production-knob artifact, not temperature. Full entry: ledger
(`docs/campaign-results.md`, "M19 deployed redo COMPLETE"). t0.6 mbpp re-certified zero-GPU;
t0.5 mbpp graded clean first pass (the evalplus late-file flake did not recur — but the
retry-before-trusting-a-null rule stands).

## Live next: M20 deployed ladder — `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`

t0.55 rung candidate operator-approved. Sequence (every command `--sampling-profile
deployed`): capped scan on old t0.6 DNF set {HumanEval/83,32,99,151,132,86,81;
Mbpp/620,306,757,564,429,739,440} + 5 clean sentinels, `--max-tokens 8192 --probe-timeout
900`, probe artifacts mv'd OUT of `benchmark/results/` when done → DNF-first → n=15 rung →
gate-3 2×50. Expectation from M19: its t0.5prod loop catastrophe evaporates; t0.6 likely
stands. Capped verdicts are clamp-aware and split repetition-signature (trustworthy) from
indeterminate.

## After M20 (queue per docs/PLAN.md §3)

M3/M4 opencode — roster ruling 2026-08-22: `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`
ADDED at the certified tune (t0.6) → M5 remnant → M18 BFCL → M7 → M21 → M22 → D10 → F1/F2
→ M11/M12 → D11 → D6 → M14.

**mlx-vlm submodule bump PENDING at the M20→M3/M4 seam** (operator merged upstream
2026-08-22; fork `0be496bf`, submodule pins `0c1c8b17`, 125 commits, output-determining
paths touched). Do NOT bump before M20 closes — its arms must share the t0.6 baseline sha.
At the seam: bump commit → `git submodule update --force` → router restart → `--limit 5`
smoke + resolved-sampling readback (use a value differing from registry default) + verify
worker flags via `ps -o command=` (new `server/runtime_config.py` in the delta).
`THINKING_BUDGET_CLAMP_RATIO` still 0.8 (now `generation.py:537`) — harness mirror valid.

## Push state

Local-only commits (NO push without explicit in-turn operator approval): 495279a, bf11b6c,
4d24722, ad9d194, 2e25f39 + the M19-closeout commit. origin/main = a2869a8. Verify pushes
with `git ls-remote`, commits with `git log` — never rtk output. `transcript.md` in repo
root is the operator's — never commit it. NVSY stays untracked.

## Traps refreshed today

evalplus-in-docker can return null then land the results file late (retry, zero-GPU).
bench_watch needs `PYTHONPATH=$STACK_REPO/benchmark`. Watcher ">20% harness errors" fires
on prefixes where errors are known hard-core runaways — check item IDs first. Probe
artifacts never live in `benchmark/results/`.

**Order of resumption: this file → `docs/PLAN.md` → `$STACK_WORKDIR/status/` (live runs).**
