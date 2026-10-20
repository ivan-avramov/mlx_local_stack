# Handoff — 2026-10-20 (session 3, in progress): `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` P369 phase-2 FULL RUN live on the reviewed head `3a92943d`; P400 (TurboQuant × width-2 verify) plan v4 APPROVED (C188), build started on `p400-tq-width2` (CPU parts done, Metal tests wait for the idle GPU); P401 root-caused + hardened

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C188, C187, P402, P401, P400, P399, P398,
P397, P396, C186, C185 …), then `docs/specs/p400-tq-width2-fix.md` (**v4, approved**), `docs/specs/p369-phase2-run-plan.md` (v9).
Model names: FULL registry names only, always (operator 2026-10-19: no shorthand).

## State of the world

- **Box `m5max-128`**, 140 W / 28 V. **No `.env`** (the shell carries `HF_TOKEN`). Machine config:
  `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **GPU: the P369 phase-2 FULL RUN** for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (pid 49598, started 2026-10-19 23:41,
  ≈ 2.7 h projected): `$STACK_WORKDIR/p369/phase2/20261019-3a92943d-full` (+ `.log`), bound to the passing smoke 8
  (`…-3a92943d-smoke8-reviewed`, SMOKE_PASS) and `--reviewed-head 3a92943d` (C187: operator-accepted). A watchdog in the session
  logs `monitor.log` every 5 min to the scratchpad and stops only on an error / power / exit. **Nothing else may use the GPU or
  load the CPU until it ends** (P400 plan T4). Smoke 8 is CONTAMINATED as timing evidence (CPU probes + a 30 s Metal check ran
  during it); its correctness gate stands.
- **Fork:** `p369-mtp` = `3a92943d` (local = origin, pushed with the operator's go). Production pin `4e6d0e03`, production diff
  empty. Green at `3a92943d`: suite run 2 6420 / 17 / 0 (run 1 hit the P401 flake — now root-caused), audits green.
  **`p400-tq-width2`** (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p400`, off `3a92943d`, local only): P401 red + fix (CPU,
  27 / 27 green in `test_lazy_embeddings.py`), P400 Metal tests written (`tests/test_p400_tq_width2.py`, E1c TurboQuant cases in
  `test_p369_phase2_observe.py`) — **red not yet observed**; fix A NOT yet applied. Tests there run with
  `PYTHONPATH=<p400 worktree>` and the p369 worktree's venv (verified to import the p400 tree). Side worktree
  `…/mlx-vlm-p369-r2` (branch `p369-r2`) is stale (= an older head) — remove when convenient.
- **Stack `main`** ≈ 65 commits ahead of origin (docs only). Push needs the operator's in-turn go.
- Daily driver MTP-OFF (C177).

## Rulings / findings this session (open-questions)

- C186 harness review closed; C185 E2 same-instance built; C187 (`3a92943d` reviewed head, full run for
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` only, push); **C188 P400 plan v4 approved** (fix A; P401 hardening bundled;
  bounds ≤ 3 % median decode tok/s, ≤ 1 % median decode-phase peak).
- Lead calls: P396 (grace-loop ps margin), P397 (vacuous E1c identity), P398 (forced positions; amended after Cursor round 4:
  plain forcing schedule observed and compared), P399 (rejected attempts count).
- **P400** (production): the `qwen3_5` verifier's length-2 shortcut is not exact on TurboQuant KV → `Qwen3.8-27B-mlx-uniform-4bit`
  MTP not lossless; root cause confirmed; fix A approved. **P401**: the warm-session lazy-embedding flake = an unprimed warm
  prefill (suffix-local positions sliced at the absolute offset → short / empty RoPE positions reading uninitialized memory); no
  production exposure (all warm prefills prime absolute positions); hardened on `p400-tq-width2`. **P402** (latent, opt-in
  EpiCache): physical vs logical offset for the position slice.

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

1. **When the full run ends:** read its summary (the watchdog prints it): E1c (pair, C1, C2, forced positions + schedules,
   rejected attempts), E2 (verdict, C1-E2, cross_load), E7a (Clopper–Pearson per class), E7b (descriptive). Check
   `verify_blocks_per_query` on every ON request (P400 §5.2 carry-over). Report → P369 entry + handoff + campaign results.
2. **P400 build on the idle GPU** (`docs/specs/p400-tq-width2-fix.md` v4): run the Metal tests on `p400-tq-width2` and OBSERVE
   red (expected: TurboQuant cases fail; native cases pass); apply fix A (`speculative_verifier.py`: delete the
   `length == 2` branch, `# Fork (P400):` marker); green; the B = 2 left-padded characterization test; the Qwen4 regression;
   the harness `tq_norm` / `old_prefix_k` live-leaf detection fix (inspect the live leaf classes first — likely a
   `BatchTurboQuantKVCache` with tuple keys); `PRODUCTION` pin move; hygiene (formatting hooks, collect-only counts); fork suite
   ×2 + 8 audits; Cursor code review (≤ 3 rounds); operator approval of the production change.
3. Then §5 re-certification: phase 2 for `Qwen3.8-27B-mlx-uniform-4bit` (smoke + full) on the new pin;
   `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` carry-over iff `verify_blocks_per_query == 0`, + regression smoke; the
   pre-registered ABBA performance probe; then the fork main merge + submodule bump, M6d on real chains, MTP-ON restore.
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

Next decision id C189; discussion ids continue from P403.
