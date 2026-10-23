# Handoff — 2026-10-23 (session 6 checkpoint 11:30): Wave 1 COMPLETE — 30 / 30 legs VALID (A1–A4 + M1); next B8 / B6 and B2

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P452, C215, P447, C214, P446, P444
addendum, C213, P445, C212, P443, P442, C211, P440 … C210), then `docs/specs/p426-fable-mtp-recert.md` and
`docs/specs/p434-local-gate.md` (v4). Model names: FULL registry names only, always.

## State of the world

- **Box `m5max-128`**, AC 140 W / 28 V. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Wave 1 COMPLETE 2026-10-23 11:26** — A1–A4 (frozen v4 `556422b8`) 8 smokes + 16 legs; M1 (frozen v7 `968ea082`, mlx-vlm
  `0f30522c`, production_ref `0b603d03`) 2 smokes + 4 legs: ALL VALID and speed valid, all harvested and committed.
  Descriptive: ON outputs byte-identical to OFF on 166 / 166 A1–A4 pairs (Math500 acc_strict 0.98 both arms; reasoning
  strict 1.0); M1 at 256K: peaks OFF 37.65 / 37.68 / 37.94 GB vs ON 37.97 / 38.00 / 38.25 GB (+0.31 GB; ON = R7's
  reference exactly), decode 13.4 → 17.0 tok/s (1.26×), prefill ≈ 395 tok/s both. Panel on 0 pairs (C217 / P455).
  M1 needed four fixes / setup steps (P452 + fork venv in the freeze; see C216 / C217 and the archived attempts).
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

1. B8 pair verifier (with the P455 byte-identity gate) + B6 signals sheet → `benchmark/results/p426/SIGNALS.md` for the
   operator's ship call (C204); four-eyes applies (new components).
2. B2 (tg1 for Wave 2, the primary agentic axis) — four-eyes; then Wave 2 (8 legs, ≈ 12.5 h).
3. Stack `main`: 46 local commits since `02f1154e` — ask the push.
4. P433 fix; full stack suite on HEAD; P440 fork style fix before the first release (v1.0.0 with the P426 ship decision).

## Rules learned (session 6)

- A freeze for an in-process fork harness (M1 `qualify`) needs the FORK's own `.venv` in the frozen submodule; the freeze
  record is written only after the frozen harness's real entry point runs (`--help`) and its venv answers.
- After any submodule bump, run the stack's K3 real-entry-point test before launching.
- four-eyes / review-panel (installed in `~/.claude/skills`): dispatch helpers and panels ONLY inside a PAUSE window during a GPU campaign (P454).
- GitHub Actions are dead (minutes); the local gate is the only gate, at releases (P448).
- Hooks run with `GIT_DIR` set to the PUSHING repo — every hook git call must name its repo (shim unsets local env vars).
- macOS `pgrep` excludes the caller's ancestors — track a parent by pid (`bench_watch --driver-pid`).
- Unmocked integration tests must use the PRODUCTION topology (parent / child, real argv lengths, real env).
- `ChainOps.load` identity keeps the FULL worker cmdline (P449); receipts re-check flags on it.
- Run the stack suite WITH `STACK_WORKDIR` set (P445); without it the tg2 modules skip with the reason.
- Everything citable lives in the repo (AGENTS.md, C211): rows / receipts on `main`, raw logs / transcripts on `evidence`.

Next decision id C216; discussion ids continue from P452.
