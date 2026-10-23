# Handoff — 2026-10-22 (session 6 checkpoint 17:25): Wave 1 A1–A4 full legs RUNNING on frozen v4; gate at releases; evidence backfilled

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P452, C215, P447, C214, P446, P444
addendum, C213, P445, C212, P443, P442, C211, P440 … C210), then `docs/specs/p426-fable-mtp-recert.md` and
`docs/specs/p434-local-gate.md` (v4). Model names: FULL registry names only, always.

## State of the world

- **Box `m5max-128`**, AC 140 W / 28 V. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Wave 1 RUNNING (A1–A4 only, P452)** — sequencer PID 55497 from `$STACK_WORKDIR/worktrees/stack-p426-seq` (`25cacd69`), legs
  from the FROZEN worktree `$STACK_WORKDIR/worktrees/stack-p426` at **v4 `556422b8`** (`src/mlx-vlm` `0b603d03`, `src/mlx-serve`
  `86921f02`, registry OFF `00a6263e…` / ON overlay `bb7fe3f0…`; `$STACK_WORKDIR/p426/frozen.json`; v1–v3 archived). 8 / 8
  A1–A4 smokes VALID + speed valid; full leg 1 `math500-p426-off-b1` VALID (50 / 50, 1 h 05); 15 more (≈ 12 h). Log
  `$STACK_WORKDIR/p426/wave1/sequence.log`. A background task (`scratchpad/commit_harvests.sh <seq pid> <log line>`) commits
  each harvested leg on `main` and exits on STOP / DONE. NOTE `9dee517e` is labelled `cjudge-p426-off-smoke` but holds
  `math500-p426-off-b1`'s rows (script fixed).
- **M1 not run** (P452, OPEN): the fork `qualify.py` preflight refuses its own ancestor leg / sequencer and pins production
  `7207179b`; proposal = fork dev-only fix + M1 mini-wave. M1 smoke attempt archived.
- **Test windows:** `touch $STACK_WORKDIR/p426/wave1/PAUSE`; tests only after `PAUSE: holding`; `rm` → 600 s gap restarts.
  Monitors never carry a `chain_ops.BUSY` string in their command line (P443).
- **Gate (P434 → P448 / C215):** `bench.local_gate`; machine-local shims in `${XDG_CONFIG_HOME}/mlx_local_stack/hooks/` are
  `core.hooksPath` for all three repos (installed; `install-hooks` raises `GATE_MIN_COMMIT` to HEAD). Branch pushes: PII +
  naming scans only (`evidence`: PII + orphan check). Releases: `release --version X.Y.Z` (operator's call) gates stack HEAD +
  both pins, then tags; tag pushes need the receipt. No release made yet.
- **Pushed this session:** stack `main` `cf11f931` (C212); `evidence` `9f4245aa` (P438 backfill, 1,798 files); HF dataset
  `caslca/mlx-local-stack-evidence` (330 `.npz`, 18.9 GB, sha-verified); fork `archive/p404-arm-a` (P451).
  **Stack `main` has ≈ 38 local commits since `cf11f931`, NOT pushed (ask).**
- Registry unchanged; daily driver not running. HF upload log `$STACK_WORKDIR/p441/`.

## Next work, in order

1. Watch Wave 1 (each leg committed by the background task; on STOP read the receipt, propose). After A1–A4: recalibrate
   the estimate (the vision OFF smoke wall includes the one-time COCO `load_dataset`).
2. Operator decisions: P452 (M1 fork fix), P450 (slim second backfill ≈ 35–50 MB), the `main` push.
3. In PAUSE windows: B8 pair verifier, B6 signals sheet, panel round 1 (P432), the P433 fix, B2 (tg1, Wave 2); a full stack
   suite on HEAD (last full: `b61a14f6`; later commits covered by targeted suites ×2).
4. Wave-2 re-freeze adds the G4 `gate/RUNNING` marker refused by the leg wrapper (C214).
5. Later: P440 fork style fix (first fork release); R6 plan; mlx-serve v0.3.0; stale worktrees (all clean, outputs on remotes:
   `mlx-vlm-p369*`, `-p400`, `-p404a`, `-p405`, `-p426-b1`, `-panel`, `/private/tmp/mlx-vlm-review-*`, `evidence-p438`).

## Rules learned (session 6)

- GitHub Actions are dead (minutes); the local gate is the only gate, at releases (P448).
- Hooks run with `GIT_DIR` set to the PUSHING repo — every hook git call must name its repo (shim unsets local env vars).
- macOS `pgrep` excludes the caller's ancestors — track a parent by pid (`bench_watch --driver-pid`).
- Unmocked integration tests must use the PRODUCTION topology (parent / child, real argv lengths, real env).
- `ChainOps.load` identity keeps the FULL worker cmdline (P449); receipts re-check flags on it.
- Run the stack suite WITH `STACK_WORKDIR` set (P445); without it the tg2 modules skip with the reason.
- Deliberate a design with the operator BEFORE Cursor review (memory `deliberate-before-review`).
- Everything citable lives in the repo (AGENTS.md, C211): rows / receipts on `main`, raw logs / transcripts on `evidence`.

Next decision id C216; discussion ids continue from P452.
