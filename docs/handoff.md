# Handoff — 2026-10-23 (session 6 checkpoint 01:50): Wave 1 A1–A4 DONE (24 / 24 VALID); M1 pending the P452 fork push

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P452, C215, P447, C214, P446, P444
addendum, C213, P445, C212, P443, P442, C211, P440 … C210), then `docs/specs/p426-fable-mtp-recert.md` and
`docs/specs/p434-local-gate.md` (v4). Model names: FULL registry names only, always.

## State of the world

- **Box `m5max-128`**, AC 140 W / 28 V. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Wave 1 A1–A4 DONE 2026-10-23 01:42** — 8 smokes + 16 full legs, ALL VALID and speed valid, all harvested and committed
  (frozen v4 `556422b8`; sequencer worktree `stack-p426-seq`). Rows NOT yet graded; B6 / B8 not built.
- **M1 not run**: P452 approved (C216); fork branch `p452-qualify-p426` (7 local commits, production identical to S) done after
  3 Cursor rounds + C216; fork suite ×2 + 8 audits running (`$STACK_WORKDIR/p452/fork_checks.out`); then ASK the fork push →
  stack bump → M1 freeze (frozen.json + `production_ref` = `0b603d03…`) → 2 M1 smokes + 4 legs.
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

1. P452: read the fork checks; ask the fork push; stack bump (`src/mlx-vlm` → the P452 head) + M1 freeze; M1 mini-wave
   (`--axes m1`; the sequencer's resume skips nothing for M1).
2. Grade A1–A4 rows (generation done, graders not run); build B8 (pair verifier) + B6 (signals sheet) → SIGNALS.md.
3. B2 (tg1, Wave 2) as the first four-eyes run (installed 0.6.6; helpers only in PAUSE windows / with no campaign running, P454).
4. P433 fix; panel (B3 / P432 round 1); a full stack suite on HEAD.
5. Later: P440 fork style fix (before the first release, v1.0.0 with the P426 ship decision); R6; mlx-serve v0.3.0.

## Rules learned (session 6)

- four-eyes / review-panel (installed in `~/.claude/skills`): dispatch helpers and panels ONLY inside a PAUSE window during a GPU campaign (P454).
- GitHub Actions are dead (minutes); the local gate is the only gate, at releases (P448).
- Hooks run with `GIT_DIR` set to the PUSHING repo — every hook git call must name its repo (shim unsets local env vars).
- macOS `pgrep` excludes the caller's ancestors — track a parent by pid (`bench_watch --driver-pid`).
- Unmocked integration tests must use the PRODUCTION topology (parent / child, real argv lengths, real env).
- `ChainOps.load` identity keeps the FULL worker cmdline (P449); receipts re-check flags on it.
- Run the stack suite WITH `STACK_WORKDIR` set (P445); without it the tg2 modules skip with the reason.
- Everything citable lives in the repo (AGENTS.md, C211): rows / receipts on `main`, raw logs / transcripts on `evidence`.

Next decision id C216; discussion ids continue from P452.
