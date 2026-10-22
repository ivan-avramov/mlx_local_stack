# Handoff — 2026-10-22 (session 6 checkpoint 09:55): S bumped + suite green, frozen worktree built, Wave 1 RUNNING

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P440, P439, P438, P437, C210, C209, C208,
P433, P432 …), then `docs/specs/p426-fable-mtp-recert.md`. Model names: FULL registry names only, always.

## State of the world

- **Box `m5max-128`**, AC 140 W / 28 V. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Wave 1 RUNNING** since 09:44 — sequencer `bench.p426_wave1` PID 46223, run from the frozen worktree
  `$STACK_WORKDIR/worktrees/stack-p426` (stack `95646f3c`, `src/mlx-vlm` `0b603d03`, `src/mlx-serve` `86921f02`);
  `$STACK_WORKDIR/p426/frozen.json` (exclusive create), ON overlay `$STACK_WORKDIR/p426/registry-on.yaml` (exactly the three
  C177 lines). Log `$STACK_WORKDIR/p426/wave1/sequence.log`; receipts `…/wave1/receipts/`; leg stdout `…/wave1/<leg>.stdout`.
  Order: 10 smokes (math500 → cjudge → vision → reasoning → m1, OFF then ON), then 20 legs (per axis b1 OFF→ON, b2 ON→OFF);
  600 s idle before every leg; stops on ANY non-VALID leg (rc 1), harvest failure (rc 4), overrun (rc 3, leg not killed).
- **Test windows:** `touch $STACK_WORKDIR/p426/wave1/PAUSE`; start tests only after `sequence.log` shows `PAUSE: holding`
  (the harvest is done by then); `rm` it after; the 600 s gap restarts.
- **Harvest (P437):** after every leg the sequencer copies its evidence into the MAIN checkout (`benchmark/results/<entry>/`
  rows + `benchmark/results/p426/wave1/<leg>/` dossier, scrubbed, `SCRUB_MANIFEST.json`). Commit each as `data(bench)`.
  NEVER remove `worktrees/stack-p426` before every leg's manifest verifies.
- **Stack `main`** (local, NOT pushed): S bump `399984a6`; P435 hooks (`b07ca065`; `core.hooksPath githooks` now ON here);
  sequencer + harvest (`443a4b56`); naming exemption for harvested evidence (`94653515`); run records `e88b25c1`. Stack suite on
  S: 7132 passed / 27 skipped / 1 xfailed / 0 failed. Fork `main` `0b603d03` pushed (session 5).
- Registry unchanged (all four MTP entries OFF); daily driver not running.

## Next work, in order

1. Watch Wave 1: on each `HARVESTED` line commit the dossier + rows (`data(bench)`); on a STOP, read the receipt, propose.
   Smokes ≈ 3 h; then recalibrate the estimate from smoke walls (receipts' `started` / `ended`).
2. In PAUSE windows (C210): P434 local gate (receipt-only pre-push hook; fork / mlx-serve / stack `local_gate`), then the gate
   on S, then ASK for the S push. B8 pair verifier, B6 signals sheet, panel round 1 (P432), the P433 fix, B2 (tg1, Wave 2).
3. Operator decisions open: P438 (evidence backfill of local-only cited dirs), P439 (AGENTS.md amendment), P440 (fork style
   debt — lead call: fix after P426).
4. Later: R6 plan; mlx-serve v0.3.0 bump; P383, P385, tg2, M64; stale worktrees (only after checking their outputs are in the
   repo); `docs/README.md` index additions.

## Rules learned (session 6)

- GitHub Actions minutes are exhausted: nothing remote checks a push; the local gate (P434) is the only gate.
- The naming / PII hooks were OFF on this clone until 2026-10-22 (`core.hooksPath` unset); history since 10-15 has 171
  naming violations (left), zero real PII.
- Run the stack suite as the bootstrap prints it: `env -u STACK_WORKDIR` (an exported `STACK_WORKDIR` breaks test isolation).
- The main checkout has no `.env`; `ChainOps.env_base` treats it as optional.
- `uvx pre-commit run --all-files` in a scratch worktree is the fork's style check (it rewrites files — never in the live tree).

Next decision id C211; discussion ids continue from P440.
