# Handoff — 2026-10-19 (session 3, in progress): H34 H36 H38 + P396 fixed (harness review closed, C186); C185 same-instance E2 built, Cursor review round 1 of 3 running; fork push awaits the operator

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P396, C186, C185, P395 (closed), P394,
P393, C184, P392, C183, P391 …), then `docs/specs/p369-phase2-run-plan.md` (**v8**: §3 E2 on the same-instance design, C185),
`docs/specs/p387-build-note.md` (v2), `docs/specs/p383-build-plan.md` (v4).

## State of the world

- **Box `m5max-128`.** 140 W / 28 V adapter attached. No router, no chain, no pytest running. **No `.env` on this box** (the
  shell already carries `HF_TOKEN`; never `. ./.env`). Machine config: `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Fork `../mlx-vlm` branch `p369-mtp` at `f4c841be`, local only**, worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369`, clean.
  Production diff vs `4e6d0e03` EMPTY. Since `d9027a60`: P396 (`fc2dbb7e` red, `59b32042` fix), H34 / H36 / H38 (`5157af6a` red,
  `508bab78` green), C185 E2 (`6b69ed85` red, `f4c841be` green). Green: at `508bab78` fork suite
  **6357 / 17 / 0 twice**; at `f4c841be` **6361 / 17 / 0 twice**, identical skips; eight audits green at both, exclusions
  268 (symbols) / 675 (deletions) / 34 (alignment) / 50 (registries) / 16 (call arguments) — the handoff's earlier "269" was a
  recording slip (`d9027a60` also gives 268).
- **Cursor C185 review round 1 of 3** running (prompt `docs/reviews/p369-c185/code-round1.prompt-head.md` + plan v8 §3 E2 +
  `git diff 508bab78..f4c841be`; output → `docs/reviews/p369-c185/code-round1.cursor-gpt-5.6-sol-high.md`).
- **Stack `main` 39+ commits ahead of origin** (docs only). Push needs the operator's in-turn go.
- **Fork push:** the operator asked (2026-10-19) "are you done with the p369-mtp branch? if so, push it" — not done then; lead
  recommendation: push after the C185 review closes (the smoke needs C185 anyway). Ask before pushing.
- Daily driver MTP-OFF (C177) until P369 ships + re-certification.

## Rulings / calls this session

- **C186 applied:** the harness review is CLOSED; closure note appended to `docs/reviews/p369-harness/code-round6…` (H34 H36 H38
  fixed, H35 accepted, H37 residual).
- **P396 (lead call):** the `ignore-term` supervise test flake (≈ 4 / 15) was a real harness bug — `_stop()`'s grace-loop ps scan
  bounded by the grace end alone timed out and a TERM-ignoring worker became a harness error; scans now keep `PS_MARGIN_S`.
- **C185 built** per plan v8 §3 E2 (lead decisions D1–D4 in the review prompt): worker mode `e2_pair`; precedence C1-E2 ABORT >
  INCOMPLETE > FAIL > PASS; cross-load OFF arm reported, never decides; v7's reload-control OFF process dropped; triple budget 3×.

## Next work, in order

1. **C185 review**: read round 1; fix test-first; suites ×2 + audits; round 2 / 3 as needed (each prompt states "round k of 3");
   after round 3 escalate the open findings to the operator as a table (finding + context; recommendation + justification +
   strongest counterpoint, 2–3 sentences each). The closing commit is the `--reviewed-head`.
2. **Ask the operator for the fork branch push** (`p369-mtp`) — then the **GPU smoke** (C175 go): from the stack root, detached,
   background waiter: `nohup .venv/bin/python <fork-worktree>/dev/p369_phase2/orchestrate.py --stack-root . --fork-root <fork-worktree>
   --out $STACK_WORKDIR/p369/phase2/<run-id>-smoke --phase smoke [--reviewed-head <closed sha>] > <log> 2>&1 &`. `--out` must be under
   `$STACK_WORKDIR/p369/phase2/`; lock `$STACK_WORKDIR/p369/phase2/.lock` (flock). Watch `monitor.log` (5 min) + job dirs; exit 0
   SMOKE_PASS / 2 not pass / 1 harness error. Expect live-boot fixes (dry-run tokenization via `_preprocess_request`, kernel coverage
   on real weights, E7b continuity numbers, E2 `cached_tokens` / detached-replay telemetry) — fix test-first; smoke iterations need no
   review round (P394), the full run needs the reviewed head + a passing smoke on it. Then `--phase full --smoke-summary
   <smoke>/summary.json --reviewed-head <sha>` (the summary is re-validated and its gate recomputed, H36); report per pick E1c (pair,
   C1, C2), E2 (verdict, C1-E2, cross_load), E7a (Clopper–Pearson), E7b (descriptive) → P369 + handoff.
3. Then: fork main merge + submodule bump (suites in both repos) → per-pick re-certification (own plan, operator GPU go) → restore
   MTP-ON (C177 lines = `test_mtp_verify_scan.INTERIM_LINES` reversed) → P368 layers 2–3; P383 build (+P389, P388 snapshot); P385
   with Cursor; tg2 steps 3–4; M64.

## Known gaps / owed

- Residuals (disclosed): a helper that spawns and escapes between two ps polls; pid reuse within one lstart second; a cache
  symlink swap during model load restored before the re-hash; H37 (total ps failure after a setsid helper); H12 (CI oracle
  `fetch-depth: 0` + `MLX_REQUIRE_P369_ORACLE=1`) with the fork main merge. E2/E7 link to the original C84 runs is count-only.
  `tq_norm` positive and the kernel coverage set unproven on real weights until the smoke. E7 tool-session exposure not measured.
- `docs/README.md` index additions (P311 v4, P364, P369, P371, m65 tg2, M65 pilot, `docs/reviews/p371/`, `docs/reviews/p369-harness/`,
  `docs/reviews/p369-c185/`, `docs/reviews/p387/`, the phase-2 plan, the P387 note); one pre-existing pyflakes note in
  `test_mtp_verify_scan.py` (`harness`).

## Rules learned

- Suites: fork `(cd mlx_vlm && ../.venv/bin/python -m pytest -q ./tests --ignore=tests/test_smoke.py -rs -p no:cacheprovider)` ≈ 2.5 min;
  stack from `benchmark/`: `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 -rs`.
  Never two suites at once; never edit a worktree while its suite runs. Audits: the 8 `dev/check_*.py --upstream-ref 952d4f6b`
  (`--strict` for deletions) from the worktree with `.venv/bin/python`.
- **Cursor:** `cursor-agent -p --output-format stream-json --model gpt-5.6-sol-high --mode ask --sandbox enabled --force --trust
  --workspace ~/ws/mlx-vlm "<prompt>" > out.jsonl`, review text = the `type=="result"` event's `result`. One run at a time; state
  "round k of 3".
- Formatting: `uvx --offline black@26.3.1` (its "Python 3.12 cannot parse" warning is harmless), `isort@5.13.2 --profile=black`,
  `pyflakes`. BSD sed chokes on the em dash — use Python for exact-line edits.
- A deadline-capped `ps` (H33) needs a margin wherever a loop's own deadline bounds it (P396); a test that flakes is a bug report.
- Tests that start processes own them in fixtures that kill the PGID and any self-recorded child pid at teardown.
- Zero flakes; red-first honesty (say "helper absent" vs behavioural); check `git show --stat` after every commit.

Next decision id C187; discussion ids continue from P397.
