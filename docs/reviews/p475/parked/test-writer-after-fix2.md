## Report — Candidate `candidate3.stack.diff` (fix round 2)

### 1. Apply
`git -C mlx_local_stack apply ../candidate3.stack.diff` → exit 0, no output, **no rejections**. Files touched (5 modified, 7 new): `benchmark/bench/{capacity_ladder,chain_ops,run_capacity}.py`, `benchmark/m1/bench_watch.py`, `docs/specs/p475-kv-matrix.md` (amendment already in the baseline, not in the candidate diff), plus new `benchmark/bench/p475_kv.py` and 6 test files. The frozen `bench/tests/test_p475_frozen.py` is read-only (`-r--r--r--`) and untracked — provided by the baseline, untouched by the candidate.

### 2. Frozen tests
`./run_stack_tests.sh bench/tests/test_p475_frozen.py` → **58 passed in 16.12s**. No failures, so no (a)/(b) classification needed.

### 3. Listed files, then full suite
Listed set (`test_p475_kv.py test_p475_fix_round.py test_p475_round3.py test_p475_bench_watch.py test_p475_capacity_strict.py test_bench_watch.py test_p426_bench_watch.py test_capacity_ladder.py test_run_capacity.py test_chain_ops.py test_driver.py`) → **556 passed in 29.46s**. No failing ids.

Full stack suite `./run_stack_tests.sh` (foreground, 0:34:51):
```
7685 passed, 6 skipped, 1 xfailed, 4 warnings in 2091.09s (0:34:51)
```
Final line: `sys:1: DeprecationWarning: builtin type swigvarlink has no __module__ attribute` (a SWIG/`psutil` deprecation, pre-existing, unrelated). No failures, no failing ids.

### 4. Review against `docs/specs/p475-kv-matrix.md`

**Correctness vs spec.** Stage-1 instrument is `bench.run_capacity` with `--grid 8192,131072,196608,260096`, `--sampling-profile deployed`, `--seed 0`, fresh `--out-tag` (`p475_kv.py:669` `driver_argv`). Backend timings (`prompt_ms/prompt_per_second/prompt_n`, `predicted_per_second/predicted_ms/predicted_n`), `cache_n == 0`, unique session id, 256-token carrier with `finish_reason == "length"`, cumulative high-water memory, and the 2% reconciliation are all enforced in `capacity_ladder.p475_rung_problems` (`capacity_ladder.py:51-100`) and `run_capacity.py` (`--p475-strict` opt-in, requires `MLX_BENCH_SESSION_PREFIX`). ABBA order (`block_arms`, `p475_kv.py:112`), Fable first (`PICKS` insertion order), ≥600 s idle (`IDLE_S`), two speed-valid legs with replacement, instability rule with the `max(0.03, 0.5·|mean−1|)` floor applied to reversals too (`instability_flags`, `p475_kv.py:861`), deciding block with its own cap (`MAX_DECIDING_REPLACEMENTS`), per-pick `MATRIX.<pick>.md` delivered on pick completion and combined `MATRIX.md` only when both picks complete (`write_matrices`), refused preflight retried then recorded with others continuing and exit 5, atomic harvest + replay, resume from validated harvested dossiers — all match the spec and the round-2 findings list. <!-- allow-shorthand: verbatim reviewer output -->

**`chain_ops.py` effect on other ChainOps users.** The change is purely additive and backward compatible:
- `_own_targets`/`_terminate_own`/`_group_alive` are factored out of `stop_stack`; `stop_stack`'s body and return are unchanged (verified by diff and by `test_chain_ops.py`, `test_m64_chain_ops.py`, `test_p371_chain_core.py`, `test_c147_chain_runner.py`, `test_p426_leg.py` all passing in the full suite).
- `teardown_verified` is a new method called only from `p475_kv.run_leg` (`p475_kv.py:1089`, guarded by `hasattr(ops, "teardown_verified", None)` with a `stop_stack` fallback). Every other ChainOps consumer (`run_m62_live.py`, `run_m61*.py`, `c137_replay.py`, `run_inject.py`, `p426_leg.py`, `chain_core.py`) calls `stop_stack` and is unaffected. No regression surface for other chains.

**`bench_watch.py` / `capacity_ladder.py` / `run_capacity.py` backward compatibility.** `assess` gained a trailing defaulted `expected_s=None`; the `walls` comprehension prefers `wall_s` and falls back to `elapsed_s` only when `wall_s` is absent, so tg1/p426 watchers are unchanged. `--driver-create-time` and `--expected-s` are optional CLI flags; `_driver_alive`/`_proc_start` are new helpers. `run_ladder` gained `strict_p475=False` (opt-in); the default ladder path is unchanged. All confirmed by `test_bench_watch.py`, `test_p426_bench_watch.py`, `test_capacity_ladder.py`, `test_run_capacity.py` passing.

**Security.** `kv_env_problems` (`p475_kv.py:323`) reports KV override **names only** via `_KV_ENV_RE`, never values; the full `ps -E` text from `proc_env` is never logged. Receipts carry argv/cmdline (paths, no secrets). No environment variables or credentials are printed or logged. ✓

**Unhandled errors.** Fail-closed posture throughout: external calls in `run_leg` are wrapped and recorded as `problems`/`speed_problems`; `harvest_leg` raises `HarvestError` on any scrub/size/existence problem; `validated_dossier_metrics` raises `ValueError`; `run()` maps harvest failure → exit 4, unusable receipt → 1, exhausted main cell → 3, refused preflight → 5, table delivery failure → 6; `_load_harvest` raises on a dossier with ≠1 ladder file. `main`'s final `write_matrices` failure → `rc or 6`.

**Findings (file:line).**
1. **Dead code** — `benchmark/bench/p475_kv.py:1171`: `refused = {}` is initialized and never read. The preflight-refused set is `refused_arms` (`p475_kv.py:1270`); the `refused` inside `cell` (`p475_kv.py:1215`) is an unrelated local int counter for NOT_STARTED retries. The outer dict is a leftover. Minor.
2. **Argv-check gap** — `benchmark/bench/p475_kv.py:288` `expected_kv_argv` emits only `--kv-bits`, `--kv-quant-scheme`, `--quantized-kv-start`; it does not include `--kv-group-size`, so `worker_argv_problems` would not flag a non-default group size in the worker argv. The KV-line check (`kv_line_problems`, `p475_kv.py:341`) does catch a group-size mismatch as the secondary record, so engagement is still proven, but the argv check is not exhaustive over KV flags. Minor.
3. **Live-run risk on KV-line field presence** — `benchmark/bench/p475_kv.py:341-402` `kv_line_problems` treats every split field (`kv_key_bits`, `kv_value_bits`, `kv_key_scheme`, `kv_value_scheme`) as mandatory, even for non-split arms (where they must read `None`). If the fork's `KV cache resolved:` line omits these fields for non-split arms (N16/AF8/TQ8/AF4/TQ4), every non-split leg would be INVALID. The implementer's report flags this as "verified only against fakes"; the frozen tests pass because they feed lines that carry the fields. Not a code-correctness bug, but a real risk for the live run that depends on the fork's exact log format — worth confirming against a real worker log before the full run.
4. **`teardown_verified` group-SIGKILL pid recycling** — `benchmark/bench/chain_ops.py:719` escalates to `killpg(spawned["pid"], SIGKILL)` when the owned group survives. The router is spawned with `start_new_session=True` (pgid == spawned pid), and `_group_alive` is checked first, so the pgid is the original group; recycling risk is low but inherent to `killpg` by pgid. Acceptable given the ownership proof, noted for completeness. <!-- allow-shorthand: verbatim reviewer output -->

No deviations from the amended spec were found; the per-pick delivery and "none by default" quality language in the amended spec matches `deliver_pick`/`write_matrices`.

### Verdict
**PASS.** The candidate applies with no rejections; the 58 frozen tests pass; the 11 listed files pass (556 tests); the full stack suite passes (7685 passed, 6 skipped, 1 xfailed, 0:34:51). The `chain_ops.py` change is additive and backward compatible — no other ChainOps consumer is affected. The only findings are minor (one dead variable, one non-exhaustive argv check) and one live-run risk the implementer already disclosed (KV-line split-field presence, fake-verified). No fix performed, per the brief.
