# Handoff — 2026-10-19 (session 3, in progress): harness review closed (C186); C185 E2 built, review rounds 1–2 fixed (round 3 of 3 deferred until a smoke passes, operator agreed); GPU smoke iterations 1–3 found 3 live bugs (fixed); smoke 4 running

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P398, P397, P396, C186, C185, P395 (closed),
P394, P393, C184 …), then `docs/specs/p369-phase2-run-plan.md` (**v9**: v8 §3 E2 same-instance (C185) + §2.2 forced positions (P398)),
`docs/specs/p387-build-note.md` (v2), `docs/specs/p383-build-plan.md` (v4).

## State of the world

- **Box `m5max-128`.** 140 W / 28 V adapter attached. **No `.env` on this box** (the shell carries `HF_TOKEN`; never `. ./.env`).
  Machine config: `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Fork `p369-mtp` at `8d1cf115`** (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369`); **pushed to origin at `a44a8070`** (operator
  go 2026-10-19) — local is ahead by the smoke / round-2 fixes (push again only with a new go). Side worktree
  `$STACK_WORKDIR/worktrees/mlx-vlm-p369-r2` (branch `p369-r2`, = `8d1cf115`) used for edits while a smoke owns the main
  worktree (its tree guard refuses any change); its tests run with the main worktree's venv, whose editable `mlx_vlm` makes
  `test_check_sources_refuses_a_module_outside_the_reviewed_tree` fail there (artefact; green in the main worktree).
  Production diff vs `4e6d0e03` EMPTY. Green at `8d1cf115`: fork suite **6406 / 17 / 0 twice**, identical skips; eight audits
  green, exclusions 268 / 675 / 34 / 50 / 16.
- **GPU smoke 4** running: `$STACK_WORKDIR/p369/phase2/20261019-8d1cf115-smoke4` (+ `.log`), no `--reviewed-head` (P394 iteration).
  Smokes 1–3 (`…-a44a8070-smoke1`, `…-f0bfce29-smoke2`, `…-7b87192e-smoke3`): HARNESS_ERROR, HARNESS_ERROR, INTERRUPTED (stopped by
  the lead after P398 made its E1c FAIL certain).
- **C185 review:** round 1 (`f4c841be`) NOT CLEARED E1 E2 E3 (+E4) → fixed; round 2 (`a44a8070`) NOT CLEARED E5 (+E1 partial)
  → fixed on `p369-r2`. **Round 3 of 3 runs only after a smoke passes** (operator agreed 2026-10-19) so it covers E5 + every
  smoke fix and its closing commit is the `--reviewed-head`.
- **Stack `main` ≈ 45 commits ahead of origin** (docs only). Push needs the operator's in-turn go.
- Daily driver MTP-OFF (C177) until P369 ships + re-certification.

## Smoke-found bugs (fixed test-first; P394: smoke iterations need no review round)

- Smoke 1: requests carried the registry name; mlx-serve's router rewrites `body["model"] = hf_path` (`router.py:483`) → the
  worker unloaded its target and tried an offline load. Fix: `routed()` in `post` / `prompt_ids` (`f0bfce29`).
- Smoke 2: the dry-run `DryRun(BaseException)` unwound through `@app.middleware("http")` as a `BaseExceptionGroup` and killed the
  TestClient portal (reproduced on CPU). Fix: plain `Exception`, ids recorded on the side (`7b87192e`).
- Smoke 3: **P398** — E1c compared a stale ON row at a thinking-budget forced position (E1c `max_tokens` 160 → budget 128 →
  forced `\n</think>`). Fix: rows cut at each block's emission decision, forced positions proven and excluded (`8d1cf115`).
- Observed, not a bug: Fable T = 1,024 seed a0 had no observed key-length straddle (a block boundary landed on 1,024) while the
  production counter read 16 → that cell retries the next seed (by design). T = 65,536 E1c cell > 11 min (hash cost).

## Next work, in order

1. **Iterate the GPU smoke to SMOKE_PASS** (C175 go): from the stack root, detached, background waiter:
   `nohup .venv/bin/python <fork-worktree>/dev/p369_phase2/orchestrate.py --stack-root . --fork-root <fork-worktree>
   --out $STACK_WORKDIR/p369/phase2/<date>-<head>-smokeN --phase smoke > <out>.log 2>&1 < /dev/null &` (`--out` under
   `$STACK_WORKDIR/p369/phase2/`; flock `$STACK_WORKDIR/p369/phase2/.lock`; preflight refuses while any pytest runs). Watch
   `monitor.log` (5 min) + job dirs; exit 0 SMOKE_PASS / 2 not pass / 1 harness error. Fix live bugs test-first (in the side
   worktree while a smoke runs), suites ×2 + audits, relaunch. Still unproven live: kernel coverage on real weights, `tq_norm`,
   E2 triple telemetry (`cached_tokens == 0`, detached replay counters), E7b continuity, the uniform pick end to end.
2. **C185 review round 3 of 3** on `a44a8070..<smoke-passing head>` (E5 + E1 residual + every smoke fix incl. P398); fix; if
   anything stays open, escalate to the operator as a table (finding + context; recommendation + justification + strongest
   counterpoint, 2–3 sentences each). The closing commit is the `--reviewed-head`; if round 3 changes code, a confirming smoke on
   that head is still required (P394).
3. **Full run** (operator push go first for the reviewed head): `--phase full --smoke-summary <smoke>/summary.json
   --reviewed-head <sha>` (the summary is re-validated and its gate recomputed, H36; a projected wall > 3.5 h returns to the
   operator). Report per pick E1c (pair, C1, C2, forced positions), E2 (verdict, C1-E2, cross_load), E7a (Clopper–Pearson), E7b
   (descriptive) → P369 + handoff.
4. Then: fork main merge + submodule bump (suites in both repos) → per-pick re-certification (own plan, operator GPU go) → restore
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

Next decision id C187; discussion ids continue from P399.
