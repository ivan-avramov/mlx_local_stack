# Handoff — 2026-10-23 (session 6 END): Wave 1 COMPLETE (30 / 30 VALID); next B2 → Wave 2, B8 → B6 meanwhile

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C217, P455, P454, C216, P453, P452,
C215, P448, P447, C214, P446, P445, P444, C213, C212, P443, P442, C211, P438, P439, P440, P437, C210), then
`docs/specs/p426-fable-mtp-recert.md` (§6 Wave 2, §8 signals, §9 B2 / B6 / B8) and `docs/specs/p434-local-gate.md` (v4).
Model names: FULL registry names only, always.

## m5max (64 GB) session 2026-10-18 — CLOSED (operator: GPU work is dispatched on m5max-128)

- Pulled: stack `main` fast-forwarded to `origin/main` `4fde8482`; `../mlx-vlm` `main` `24551869` (= pin; upstream is 61 commits
  ahead incl. `1a4ddb68` "Fix remaining affine QMV precision mismatches on MLX 0.32.4 (#2527)" — relevant to the mlx 0.32.3 pin,
  a separate reviewed sync item after P369); `../mlx-serve` `main` `e6a7a5a` (operator merged upstream v0.3.0 2026-10-17:
  `POST /v1/systemone`, `/v1/decisions` deprecated alias) while the stack pin is `86921f0` — **bump needs a go** (serving change).
- Fork docs commit `f8a91f67` on `../mlx-vlm` `main` (UNPUSHED): `docs/proposals/nemotron-rerank-head.md` draft 4, not approved for
  build; base = the fork head after P369 merges (P372: one fork branch in flight).
- Plan for this box + codex review: `docs/reviews/m5max-plan-2026-10-18/` (P1–P6 adjudicated). When this box reopens: P383 build,
  Pi / dsh adapters (unit completion; D2 integration gated), per-box two-judge config. Rules adopted from the review: full suite on
  the frozen candidate AFTER fetch + rebase; a shared runner/scoring change is pushed (on a go) before the other box starts a phase
  that consumes it; `p369-mtp` pushed as a WIP fork branch would let P369 development run on either box.
- This box: codex 0.163.0, no cursor-agent, OrbStack installed but stopped (docker-backed tests skip), mlx 0.32.3, no chain, no router.
- Unpushed here: stack `main` (this handoff + the review record), `../mlx-vlm` `main` (`f8a91f67`). Push needs a go.

## State of the world

- **Box `m5max-128`**, AC 140 W / 28 V. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`. GPU IDLE
  since 11:26; no sequencer, router or worker running.
- **Wave 1 COMPLETE 2026-10-23 11:26, ALL VALID + speed valid, harvested and committed**
  (`benchmark/results/p426/wave1/<leg>/`, rows under `benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/`):
  - A1–A4 on frozen v4 (`556422b8`): 8 smokes + 16 legs. ON outputs BYTE-IDENTICAL to OFF on 166 / 166 pairs; Math500
    acc_strict 0.98 / 0.98 (graded, `math500.p426-*-b[12].score.json`); reasoning strict 1.0; walls ≈ 1.5–1.7× faster ON;
    acceptance 0.75–0.89. cjudge / vision / reasoning NOT graded beyond that (cjudge = panel-only; P455 → identical = tie).
  - M1 on frozen v7 (`968ea082`, mlx-vlm `0f30522c`, production_ref `0b603d03`): 2 smokes + 4 legs. Peaks at 256K OFF
    37.65 / 37.68 / 37.94 GB vs ON 37.97 / 38.00 / 38.25 GB (+0.31 GB; ON = R7 exactly; stable to 0.01 GB); decode
    13.4 → 17.0 tok/s (1.26×); prefill ≈ 395 tok/s both.
  - All descriptive until B8 / B6 exist. Registry still has MTP OFF for the entry (no ship decision yet).
- **Pushed:** stack `main` `c974e4ae`; fork `main` `0f30522c` (P452: qualify inside the P426 wrapper; production identical
  to S); `evidence` `aad18f8d` (P438 + P450 backfills); HF dataset `caslca/mlx-local-stack-evidence` (330 p369 `.npz`).
- **Worktrees:** `$STACK_WORKDIR/worktrees/stack-p426` (frozen, v7 at `968ea082`; has `.venv`, `.venv-bench` and the fork's
  own `src/mlx-vlm/.venv`) and `stack-p426-seq` (the sequencer's code). `frozen.json` v7 at `$STACK_WORKDIR/p426/`; v1–v6
  archived there and under `benchmark/results/p426/wave1/run/archive/`. Wave 2 re-freezes (it carries B2 / the G4 marker).
- **Skills:** four-eyes 0.6.6 + review-panel 0.4.1 in `~/.claude/skills` (sources `~/ws/four-eyes`, `~/ws/review-panel`);
  `~/.claude/CLAUDE.md` has the four-eyes trigger; `~/.config/review-panel/panel.toml` = sol / glm (cursor-agent), sonnet.
- **Gate (P448 / C215):** branch pushes = PII + naming scans (shims in `${XDG_CONFIG_HOME}/mlx_local_stack/hooks/`, all three
  repos); releases via `bench.local_gate release --version X.Y.Z` (operator's call). No release yet (v1.0.0 with the P426
  ship decision, after the P440 fork style fix).
- Daily driver not running. Last full stack suite: `b61a14f6` (later changes covered by targeted suites ×2).

## Next work, in order (recommended)

1. **B2 — tg1 for Wave 2** (plan §6 / §9; four-eyes, light unless it touches a data boundary): `run_tg1_chain.py`
   `--model` single-entry filter, the `invalidate` policy, the P426 outer sequencer + frozen record, the MTP overlay
   validated for this entry only, the reversed s2 item order; ALSO the C214 G4 marker (`$STACK_WORKDIR/gate/RUNNING`
   refused by the leg wrapper) and the P433 fix (v2 pre-check plugin proof from the activation call). Deliberate the spec
   with the operator first; then four-eyes (cast shown at Go). Then re-freeze (v8: stack + fork venv + entry-point checks,
   see Rules) and **run Wave 2**: pilot OFF / ON → s1 OFF / ON → s2 ON / OFF (reversed order) → reload ON / OFF, 600 s
   idle, ≈ 12.5 h GPU. Why first: it is the only GPU work left and the plan's primary agentic axis.
2. **B8 — pair verifier** (per-axis adapters: rows, vision, reasoning, qualify, chain records; exact three-key registry delta
   + runtime delta; equality of everything else; P455 byte-identity gate → identical pairs = tie, labelled). Build while
   Wave 2 runs; four-eyes helpers ONLY inside PAUSE windows (P454).
3. **B6 — signals sheet** `benchmark/results/p426/SIGNALS.md`, generated (never hand-copied) from receipts / rows / logs for
   B8-accepted pairs: per-axis quality, panel (P455), memory, speed (paired ratio + two-stage bootstrap, seed 426),
   acceptance, coverage, attention flags (§1); pre-registered tests + Holm (§8). Wave 1 first, Wave 2 rows as they land.
4. **Operator ship call** (C204) from SIGNALS.md → P426 §11 restore (or not) → README / campaign-results → release v1.0.0
   (P440 fork style fix first).
5. Later: R6 (codec quality), mlx-serve v0.3.0 bump, P383 / P385 / tg2 / M64, remaining entries per §11.

## Rules learned (session 6)

- GitHub Actions are dead; the local gate (P434 / P448) is the only gate, at releases.
- A freeze is written only after: stack + fork venvs synced; the frozen harness's real entry points run (`qualify --help`,
  `fork_versions`); the stack's K3 test passes against the bumped submodule. After ANY submodule bump, run K3 first.
- An in-process fork harness (M1 `qualify`) needs the FORK's own `.venv` inside the frozen submodule.
- Before fixing one instance of a check, sweep for every other site of the same check (P452: two process censuses).
- Unmocked integration tests must use the PRODUCTION topology (real entry points, parent / child, real argv lengths, env).
- During a GPU campaign: tests, four-eyes helpers and review panels only inside PAUSE windows (P454); monitors never carry
  a `chain_ops.BUSY` string in their command line (P443); waiters read only log lines after the current launch.
- Hooks run with `GIT_DIR` set to the pushing repo; every hook git call names its repo. macOS `pgrep` excludes ancestors.
- Run the stack suite WITH `STACK_WORKDIR` set (P445). Everything citable is committed (AGENTS.md, C211).
- Reviewer suggestions beyond the agreed scope go to the operator before they are built (C216).

Next decision id C218; discussion ids continue from P455.
