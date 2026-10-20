# Handoff — 2026-10-20 (session 3, in progress): P405 implemented test-first on `p405-kv-scheme` (F1–F3; plan v4 escalated after Cursor round 3 of 3); P400 code round 3 of 3 running; smoke 11 (affine, harness validation) on the GPU

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P407, P408, P406, P405, P404, C189 …),
then `docs/specs/p405-kv-scheme-precedence.md` (v4, escalated), `docs/specs/p400-tq-width2-fix.md` (v4, approved),
`docs/specs/p369-phase2-run-plan.md` (v9). Model names: FULL registry names only, always (operator 2026-10-19).

## State of the world

- **Box `m5max-128`**, AC back since ≈ 07:50 (140 W / 28 V). **No `.env`**. Machine config:
  `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **GPU: smoke 11** — P369 phase-2 smoke, `Qwen3.8-27B-mlx-uniform-4bit` as served today (affine), harness `ce04439b`
  (validates the C2 gate + the affine `quantized_scale` positive live): `$STACK_WORKDIR/p369/phase2/20261020-ce04439b-smoke11-uniform-affine`
  (+ `.log`), pid at launch 48255, started 08:01. The p369 worktree is DETACHED at `ce04439b`; a waiter restores `p369-mtp`
  afterwards — verify.
- **Fork `p400-tq-width2`** HEAD `ce04439b` (production unchanged since `da27f0ef`): round 2 C2–C7 fixed (`2f14e7af` red,
  `ce04439b` green); suites ×2 6470 / 17 / 0 identical skips, 8 audits green. **Code round 3 of 3 running** (Cursor,
  `$S/p400-code-r3.jsonl`, prompt head `docs/reviews/p400/code-round3.prompt-head.md`).
- **Fork `p405-kv-scheme`** (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p405`, off `ce04439b`, local only): `ad36e941` T1–T5
  red → `0163f212` F1 (cli rebuilds `runtime.config` before `uvicorn.run`) + F2 (`KV cache resolved:` log; env-derived lifespan
  line removed); F3 red (`kvmanifest` + integration) → green (`dev/p369_phase2/kvmanifest.py`: argv codec, every resolved KV
  field, exact per-layer manifest; worker / orchestrator / smoke gate / perf probe wired). Targeted 272 tests green; **full
  suites ×2 + audits NOT yet run on it** (GPU smoke running; C188 no overlap). `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` not yet in
  harness `PICKS` (plan v4 R3, `verify_policy=None`).
- `p369-mtp` = `3a92943d` (= origin). Stack `main` ≈ 90 commits ahead of origin (docs only). Daily driver MTP-OFF for the two
  Qwen3.8-27B picks (C177); `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` still MTP-ON (P406).

## Waiting on the operator

1. **P405 plan v4 escalation** (round 3 T13 / T14 / T15) — lead rec: accept v4 without a fourth round.
2. **P406** — `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` MTP-OFF now (lead rec, as C177) or leave ON until the fixed bump.
3. Approve the P400 production change (after code round 3). P404 deferred to the TurboQuant re-measurement (C189).
4. Pushes (`p400-tq-width2`, `p405-kv-scheme`, stack `main`) — each needs an in-turn go.

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

1. Smoke 11 result → record (P369 entry / P405 F3 context); fix any live harness bug test-first.
2. P400 code round 3 result (last round) → CLEARED, or the operator table.
3. P405: suites ×2 + 8 audits on `p405-kv-scheme` (after the smoke); add `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` to the harness
   `PICKS` test-first; Cursor code review round 1 of 3 on `ce04439b..p405 HEAD`.
4. GPU (on P400 + P405, after a reviewed head): R3 P369 phase 2 smoke → full for `Qwen3.8-27B-mlx-uniform-4bit` on TurboQuant
   (F3 manifest + `tq_norm` must fire) and `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`; R4 P404 ABBA (P405 both arms); R5 codec ABBA;
   R7 six-entry 256K qualification. R6 (matched quality arms) gets its own plan + operator GPU go.
5. Then: fork main merge (P400 → P405) → candidate stack worktree bump (main unchanged until R6) → M6d / M63 on the chosen
   codec → MTP-ON restore → P383, P385, tg2, M64. Remove the stale `mlx-vlm-p369-r2` worktree.

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

Next decision id C190; discussion ids continue from P408.
