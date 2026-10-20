# Handoff — 2026-10-20 (session 3, in progress): P369 phase 2 FULL RUN PASS for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; P400 fixed + Cursor code review CLEARED on `p400-tq-width2` (awaiting the operator's approval of the production change); P400 ABBA performance probe running on the GPU

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P403, C188, C187, P402, P401, P400,
P399 … and the P369 entry), then `docs/specs/p400-tq-width2-fix.md` (v4, approved), `docs/specs/p369-phase2-run-plan.md` (v9).
Model names: FULL registry names only, always (operator 2026-10-19).

## State of the world

- **Box `m5max-128`**, 140 W / 28 V. **No `.env`** (the shell carries `HF_TOKEN`). Machine config:
  `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **GPU: the P400 §5.3 ABBA performance probe** (`dev/p400_perf_probe.py`, pid at launch 93299, started 2026-10-20 01:14,
  ≈ 1 h 40 min): `$STACK_WORKDIR/p400/perf/20261020-<p400 head>/` (+ `.log`; `report.json` per pick). A = old production tree
  (`$STACK_WORKDIR/worktrees/mlx-vlm-p369`, `3a92943d`), B = new (`…/mlx-vlm-p400`); both picks; bounds ≤ 3 % median decode
  tok/s, ≤ 1 % median decode-phase peak (C188).
- **P369 phase 2 for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: FULL RUN PASS** (`…/p369/phase2/20261019-3a92943d-full`,
  E1c / E2 PASS, E7a M4a 4/20 M4b 7/20, E7b 5/5; `verify_blocks_per_query = 0` on all 65 ON turns → carries over to the new pin
  with a regression smoke). Recorded in the P369 entry + campaign results.
- **Fork:** `p369-mtp` = `3a92943d` (= origin). **`p400-tq-width2`** (local only, worktree `…/mlx-vlm-p400`): P401 guard
  (`06101c24`), P400 fix A (`da27f0ef`), P403 production-numerics rerun, harness TurboQuant-leaf fixes, the pin move to
  `da27f0ef` (`PRODUCTION` in `orchestrate.py`), the perf probe. Green: fork suite **6447 / 17 / 0 twice** (with
  `PYTHONPATH=<p400 worktree>`), eight audits green (268 / 675 / 34 / 50 / 16). **Cursor code review round 1 of 3 CLEARED.**
- **Stack `main`** ≈ 75 commits ahead of origin (docs only). Push needs the operator's in-turn go.
- Daily driver MTP-OFF (C177).

## New this stretch (2026-10-20 01:00–04:00)

- P369 full run PASS for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (above). P400 perf probe → **P404** (operator decision:
  `Qwen3.8-27B-mlx-uniform-4bit` −3.93 % tok/s at forced width 2, outside the 3 % bound; worst case by construction).
- **P405 (operator decision, production):** `--kv-quant-scheme turboquant` is ignored by the server (runtime config frozen at
  import with the `uniform` default; upstream #1876, fork since 2026-08-22) → six registry entries incl. two main picks are
  served with AFFINE 4-bit KV labelled TurboQuant. Found by smoke 9's leaf census, root-caused on the live worker.
- Unbound smoke 9 (`Qwen3.8-27B-mlx-uniform-4bit` on the fix): E1c / E2 PASS (fix verified live on the affine KV actually
  served); gate failed only on the KV positive (affine leaf). Regression smoke 10 (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
  on the new pin) running. The p369 worktree is DETACHED at the P400 head while it runs; the smoke-10 waiter restores
  `p369-mtp` afterwards — verify.
- P400 tests now cover both codecs for `Qwen3.8-27B-mlx-uniform-4bit` (affine + TurboQuant); 441 related tests green.

## Waiting on the operator

1. **Approve the P400 production change** (fix A + the P401 guard; Cursor CLEARED; verified live by smoke 9).
2. **P404** — accept the worst-case width-2 slowdown (lead rec) or ask for an exact fast width-2 path.
3. **P405** — fix the scheme precedence (TurboQuant engages; re-measure six models) or align the registry with affine (lead rec: fix, own proposal).
4. Then: push `p400-tq-width2` (and stack `main`) — each needs an in-turn go.

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

1. When the perf probe ends: read `report.json` (per pick: arm medians, verdict vs the bounds); record in P400; OUTSIDE_BOUNDS →
   to the operator with the numbers.
2. On the operator's approval of the production change: P369 phase 2 for `Qwen3.8-27B-mlx-uniform-4bit` on the new pin
   (`da27f0ef`; the P400 worktree as the fork root): smoke, then — once a smoke passes bound to a reviewed head (the CLEARED P400
   head or a re-reviewed one) — the full run; the leaf census + fixed TurboQuant positives must fire (`tq_norm`). Plus a
   regression smoke for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on the new pin.
3. Then: fork main merge + submodule bump (suites in both repos) → M6d re-certification on real router chains for both picks
   (own plan, Cursor review, operator GPU go) → MTP-ON restore (C177 lines, CERTIFIED notes, client-config audit, README
   predictor column).
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

Next decision id C189; discussion ids continue from P404.
