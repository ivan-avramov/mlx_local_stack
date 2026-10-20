# Handoff — 2026-10-20 (session 3, in progress): P405 fix decided (C189: TurboQuant engages; re-measure) — plan v1 in Cursor review; P400 code round 2 NOT CLEARED → C2–C7 fixed (`ce04439b`), round 3 next; box on BATTERY (no GPU work)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P405, P404, P403, C189, C188, C187 …),
then `docs/specs/p405-kv-scheme-precedence.md` (v1, in review), `docs/specs/p400-tq-width2-fix.md` (v4, approved),
`docs/specs/p369-phase2-run-plan.md` (v9). Model names: FULL registry names only, always (operator 2026-10-19).

## State of the world

- **Box `m5max-128`**: **on battery since ≈ 04:00 2026-10-20 (AC disconnected, 79 %)** — every GPU run's power preflight
  refuses until 140 W / 28 V is back; verify `pmset -g batt` / `pmset -g ac` first. **No `.env`** (the shell carries
  `HF_TOKEN`). Machine config: `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`. GPU idle.
- **Fork `p400-tq-width2`** (local only, worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p400`), HEAD `ce04439b`: P401 guard
  (`06101c24`), P400 fix A (`da27f0ef`; production unchanged since), harness + perf probe. Cursor code round 1 CLEARED
  `d4150165`; **round 2 of 3 NOT CLEARED** (C2–C7, `docs/reviews/p400/code-round2.*`) → all fixed test-first (`2f14e7af` red,
  `ce04439b` green). Suites ×2 + audits on `ce04439b`: see below / rerun if unknown. **Round 3 of 3 is the last** before the
  operator.
- `p369-mtp` = `3a92943d` (= origin); its worktree is back on the branch.
- **Stack `main`** ≈ 85 commits ahead of origin (docs only). Push needs the operator's in-turn go.
- Daily driver MTP-OFF (C177).

## New this stretch (2026-10-20 04:00–)

- **C189 (operator): fix P405 so TurboQuant engages, rerun what that invalidates.** Plan v1
  `docs/specs/p405-kv-scheme-precedence.md`: F1 rebuild `runtime.config` from the final env in `cli.main` before `uvicorn.run`
  (also fixes the frozen `--vision-cache-size` and the `/v1/settings` replace restore point), F2 effective-codec load log;
  T1–T5 red-first; branch `p405-kv-scheme` off `p400-tq-width2`. Rollout R1–R7: both main picks PROVISIONAL from the bump until
  re-certified on TurboQuant; P404's affine −3.93 % superseded by a TurboQuant ABBA (P405 in both arms); the
  `Qwen3.8-27B-mlx-uniform-4bit` P369 phase 2 runs on P400 + P405 (TurboQuant leaves, `tq_norm` positive). Defect window: stack
  bump `111bb538` (2026-08-23) onward. **Cursor plan review round 1 of 3 running** (`$S/p405-plan-r1.jsonl`, prompt head
  `docs/reviews/p405/plan-round1.prompt-head.md`).
- P400 round-2 fixes include a served-KV-codec assertion in the perf probe (would have caught P405 at boot); the P405 plan
  should add the same to the P369 worker's `assert_served`.

## Waiting on the operator

1. **Approve the P400 production change** (fix A + the P401 guard) — after code round 3.
2. **P404** — now deferred to the TurboQuant re-measurement (C189); no decision on the affine number.
3. Push `p400-tq-width2` (and stack `main`) — each needs an in-turn go.

## Smoke-found bugs (fixed test-first; P394: smoke iterations need no review round)

- Smoke 1: requests carried the registry name; mlx-serve's router rewrites `body["model"] = hf_path` (`router.py:483`) → the
  worker unloaded its target and tried an offline load. Fix: `routed()` in `post` / `prompt_ids` (`f0bfce29`).
- Smoke 2: the dry-run `DryRun(BaseException)` unwound through `@app.middleware("http")` as a `BaseExceptionGroup` and killed the
  TestClient portal (reproduced on CPU). Fix: plain `Exception`, ids recorded on the side (`7b87192e`).
- Smoke 3: **P398** — E1c compared a stale ON row at a thinking-budget forced position (E1c `max_tokens` 160 → budget 128 →
  forced `\n</think>`). Fix: rows cut at each block's emission decision, forced positions proven and excluded (`8d1cf115`).
- Smoke 4: P399 (rejected attempts' evidence dropped) and P400 (production defect) — open-questions.
- Observed, not a bug: Fable T = 1,024 seed a0 had no observed key-length straddle (a block boundary landed on 1,024) while the
  production counter read 16 → that cell retries the next seed (by design). T = 65,536 E1c cell > 11 min (hash cost).

## Next work, in order

1. Read the P405 plan review; fix the plan (≤ 3 rounds); then implement P405 test-first on `p405-kv-scheme`.
2. P400 code round 3 of 3 on `78c9f99d..ce04439b` (one Cursor run at a time) — after the suites / audits are green.
3. When AC power is back: P369 phase 2 for `Qwen3.8-27B-mlx-uniform-4bit` on P400 + P405 (smoke, then full run on a reviewed
   head); the P404 TurboQuant ABBA (arm A = `p369-mtp` + the P405 commit on a dev branch, arm B = P400 + P405); 256K peaks
   for both main picks on TurboQuant.
4. Then: fork main merge (P400 → P405) + submodule bump (both main picks PROVISIONAL) → M6d re-certification (own plan,
   Cursor review, operator GPU go) → MTP-ON restore → P383, P385, tg2, M64. Remove the stale `mlx-vlm-p369-r2` worktree.

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

Next decision id C190; discussion ids continue from P405.
