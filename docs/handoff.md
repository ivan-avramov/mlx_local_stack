# Handoff — rewritten 2026-08-23 ~06:30 (M19 + M20 ladders COMPLETE; O37 awaits ruling; M3 next)

Single box (M5 Max 64 GB), SINGLE attended session owns everything (operator ruling
2026-08-22). If generate processes you didn't launch appear (`pgrep -f "run.py generate"`),
investigate ownership before acting — do not adopt or kill on sight.

## Standing footgun (O36, awaits ruling)

`run.py generate` DEFAULTS to the retired `production` profile. **Every generate command
must carry `--sampling-profile deployed` EXPLICITLY.**

## M19 — CLOSED 2026-08-22: t0.6 certified for `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`

Both benches; t0.5 beat t0.6 on no endpoint; zero loops in 96 deployed-t0.5 rows sealed the
production-knob attribution. Ledger: "M19 deployed redo COMPLETE". Committed `4dc2b76`.

## M20 — ladder COMPLETE 2026-08-23: t0.55 wins the ranking key; certification = **O37 (OPEN)**

`Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`, full deployed ladder (scan → DNF-first →
rung → gate-3 2×50). Gate-3: hep t0.55 strict **82.0 / 1 DNF** vs t0.6 76.0 / 7 DNFs;
mbpp t0.55 strict **70.0 / 5 DNFs** vs 68.0 / 7. Rung held pass@1 (13/15 paired both).
DNF set SHRINKS 14→6 (vs M19's churn); zero loops in 129 deployed-t0.55 rows. mbpp t0.55
first grade was the evalplus null-then-late flake (3rd time) — re-grade certified.
**Recommendation filed as O37: certify t0.55.** If ratified: fan out to all four sampling
carriers + `main_models.yaml` `generation_defaults` (currently ships t0.6). Probe/scan
artifacts: `$STACK_WORKDIR/status/m20_scan/` (never in `results/`).

## Next: M3/M4 opencode block (queue per `docs/PLAN.md` §3)

M3 = opencode Run A, 22 python items × {`Ornith-1.0-35B-mlx-uniform-4bit`,
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` at
**t0.6** (M19-certified; the PLAN row's old "t0.5" text was pre-retraction and is fixed)}.
V4 (provenance) and D7 (scoreboard role + progress-gated bound) are DONE — M3 is unblocked.
Smoke (5 items, one model) before the full run, per the pilot rule. Then M4
(`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`), M18 BFCL in the same block.

**mlx-vlm submodule bump PENDING at this seam** (fork `0be496bf`, submodule `0c1c8b17`,
125 commits, output-determining). Options: bump BEFORE M3 (all opencode arms on the new
sha — cleanest going forward) or serve-only later. NOT operator-confirmed yet — do not
bump without a go; if M20 needs any follow-up arm at the old sha, bumping first would
poison its comparability. `THINKING_BUDGET_CLAMP_RATIO` still 0.8 (`generation.py:537`).
Bump recipe: pointer commit → `git submodule update --force` → router restart → `--limit 5`
smoke + resolved-sampling readback (value ≠ registry default) + worker cmdline check
(`ps -o command=`; new `server/runtime_config.py` in the delta).

## Push state

Local-only commits (NO push without explicit in-turn operator approval): 495279a, bf11b6c,
4d24722, ad9d194, 2e25f39, 4dc2b76 + the M20 closeout commit. origin/main = a2869a8.
Verify pushes `git ls-remote`, commits `git log` — never rtk output. `transcript.md` is the
operator's — never commit. NVSY stays untracked.

## Traps refreshed

evalplus-in-docker null-then-late flake (retry zero-GPU; hit again on mbpp t0.55).
bench_watch needs `PYTHONPATH=$STACK_REPO/benchmark`. `--limit N` selects by the bench's
seeded order, NOT item-id order (an id<15 split of a "first 15" rung is wrong — burned
once, caught). Probe artifacts never in `benchmark/results/`. `===` as an echo arg breaks
zsh (equals-prefix globbing).

**Order of resumption: this file → `docs/PLAN.md` → `$STACK_WORKDIR/status/` (live runs).**
