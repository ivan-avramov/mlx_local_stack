# M55 — Polyglot language gap: Rust / Java / JavaScript for the first pick

Queued 2026-10-03 (P17 ruling after Codex cold review 9; operator approval). Terse; rationale in `docs/open-questions.md` C109/P17 and
`docs/lab-notebook.md` 2026-10-03.

## Scope

- Models, same chain, same session pair: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (t0.5, medium), `Qwen3.8-27B-mlx-uniform-4bit`
  (t0.6, medium), `Ornith-1.0-35B-mlx-uniform-4bit` (deployed). Deployed sampling via `params_for(model, profile="deployed")`.
- Items: the M9 22-exercise draws for rust, java, javascript (66 items); same seeds as the existing M9/M32 rows (`rowschema.sample_seed`).
- Harness: `benchmark/run_opencode_probe.py`, opencode pinned (V4), `OPENCODE_DISABLE_EXTERNAL_SKILLS=true`, M9 grading containers.
- Serving: lean router, draft-OFF overlay, `MLX_VLM_CACHE_SESSION_MAX=1`, APC absent, M50/C106 provenance; one resident model.
- Sessions: k=2 independent loaded instances per model with distinct paired seed schedules + a 5-item same-seed reload control (C109).

## Pre-registered acceptance criteria

- AC1 Box gate before each session: 0 orphan `bash --login` shells, load < 3, `pmset -g ac` = 140 W / 28 V, battery > 20 %, router owner verified.
- AC2 Pilot: 5 seeded items (random across the three languages) run twice on the loaded instance; sizing from the pilot's MEAN and MAX as a
  lower bound. **Amended 2026-10-03 after the pilot:** the opencode loop is NOT byte-deterministic (unseeded sampling, O30; C37 rows had no
  such gate) — the gate is pass-identity with the discordance RECORDED. Measured: 4/5 pass-identical (javascript/wordy pass→fail), wall per
  item diverging up to 1.8× (mean 379 s, max 636 s). Within-instance repeatability is therefore part of the noise the k=2 sessions must cover.
- AC3 Every row carries the M50 router block, `config_sha256`, opencode version, polyglot sha; drivers re-verify at exit.
- AC4 Report per language: pass count with paired cluster-bootstrap CI vs each other model, exact McNemar, exclusive-solve sets,
  stall-kill count, tokens/task, wall/task (clean-box only); never a blended number across languages.
- AC5 Session repeatability: discordant items per model between the two sessions reported; acc never pooled across sessions.
- AC6 Interpretation rule (pre-registered): this axis is a coverage/rank-reversal SCREEN (nominal MDE ±27 pp per language); it can only
  (a) reveal a language where the first pick is clearly behind (CI upper < −5 pp vs a baseline) → open-questions item, or (b) confirm coverage.
  No ladder change without operator approval.

## Cost

~226 s/item (Python precedent) → ~4 h per model-session pair at 66 items; ~12 h for three models. Runaways bounded by derived timeouts.
