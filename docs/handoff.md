# Handoff — 2026-09-21: C91 CLOSED; C99 fork hardening pushed + bumped; C100 seed file retired; M17 DROPPED

Read this first, then `docs/PLAN.md` and `docs/open-questions.md`. Reports this session:
[C91 real-server validation](c91-real-server-validation-2026-09-21.md),
[C98(c) seed audit](c98c-seed-audit-2026-09-21.md).

## Operator rulings 2026-09-21

Shut the daily driver down for testing; approved P10 (C91 cold review + bounded live validation) and
P11 (C98 c audit). Asked for M17 background (answered from history; PLAN row corrected). Later: C99 → (a)
executed; C100 → (b) executed; M17 DROPPED.

## Runtime state

**Stack is DOWN** (torn down after validation: 0 listeners on 8000/8091/8092/3000, no `mlx` processes,
stack containers down; `memvault-myvault` is not ours). Bring it back with `/mlx start` or `./runserver.sh`.
The next start runs the C91 fix (`4d4575a7`, validated live) AND the C99 hardening (`b2e0d979`, tests only —
not yet exercised on a live worker) and is the first start WITHOUT the config-file seed (C100): verify
`init.py` readbacks (`/api/v1/retrieval/config` web search `searxng`/enabled, `/api/v1/tasks/config` task
model) look as before. Note `pull_policy: always`
on the OWUI image: the running image was `018046a13da7` (2026-09-04 build).

## C91 — CLOSED

Fork `4d4575a7` bumped in `f623b6d`. Cold review PASS-WITH-GAPS (five findings, none blocking the seam
fix). Live validation through `runserver.sh` on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`:
calibration shape 1/1, `max_tokens 64` 64/64, stop 27/27 (non-stream/stream), `/v1/responses` and
`/v1/messages` 1. Historical C84/C89 counts untouched. Private captures
`$STACK_WORKDIR/scratch/c91-validation-20260921/`. **C99 (open)**: small fork hardening for the review
findings. **EXECUTED (operator took a)**: fork `b2e0d979` pushed, stack bumped; 4-failing-first + 7 endpoint
body-level tests, full fork suite 4915 pass.

## C98 — (a) and (c) DONE; C100 open

No `openwebui_config.json` row reaches the flat config table (the export holds 185 nested blob leaves equal
to the seed beside 468 flat rows the code reads). Six seed intents are not live: `channels.enable`,
`ui.enable_user_webhooks`, three authored task prompt templates, `models.default_metadata.*`. Everything
else is live via defaults / compose env / `init.py`. **C100 (open)**: recommend retiring the seed file (drop
the `cp` in `runserver.sh`, delete the file); promote the task templates into `init.py` only if wanted.
**C100 EXECUTED (operator took b)**: `openwebui_config.json` deleted, `runserver.sh` copies nothing, all references
reworded; the three authored task templates were dropped, not promoted. Init tests 31 pass.
Instrument + defaults under `$STACK_WORKDIR/scratch/c98c/`. Instrument trap recorded in the notebook:
`configs/export` mixes flat and legacy rows; separate them before reading "live".

## M17 — DROPPED (operator 2026-09-21)

`Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit` was acquired, converted and Stage-2 screened in
August (hep 92.0/90 strict, mbpp 74.0/74, 0 DNFs, +6.2pp hep at 3× speed vs the representative,
INCONCLUSIVE n=50, pre-O36 profile). Never re-run at the deployed profile, never uploaded, no C-ladder axes.
Operator: no need to pursue. Registry placeholder removed (operator go, same day); `model_settings.json` regenerated,
`configgen check` clean, 104 configgen + provenance tests pass. Historical Stage-2 rows and the
`benchmark/bench/model_params.py` map entry stay (grading of old rows). The converted weights in
`$STACK_WORKDIR/models/` were NOT deleted (operator call).

## Parked / deferred (unchanged)

S1 NVSY (awaiting go), D12 (lands with the next opencode run), C77/C78/C87 (deferred).

## Git

Fork `b2e0d979` PUSHED (operator-approved C99 (a) includes the GitHub-first push + bump). Stack commits:
docs `b2a9d55`, bump, C100 + rulings (see `git log`). Stack NOT pushed; push only on explicit in-turn instruction.

## Resume discipline

One resident model; APC absent; retained sessions 2; full active preallocation; deployed sampling and
explicit served-overlay environment. Never alter source/config during a live run; preserve real data and
recorded failures. Commit coherent units; push only on explicit current-turn instruction. Next decision id
C101; discussion ids continue from P12 (this session used P10–P12).
