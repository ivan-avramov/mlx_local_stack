The stage-1 build is in place: every component, lifecycle step, run-control rule and output in the contract is implemented, and all tests pass on fake ops. Nothing has run against a live router, model or GPU. I have not committed anything, per the brief.

Two things to know first. My tests were not written red-first; I wrote them after the code. And the frozen `p475s1/` tests are not in this copy, so I couldn't run them.

## Files

New:
- `benchmark/bench/kv_line.py` — `parse_kv_line` (takes a string or list of lines, uses the last line, refuses on a missing line, field or literal), `expected_kv`, `kv_line_problems`.
- `benchmark/bench/p475_kv.py` — the `Ops` protocol, `RealOps`, arm registry generation and the R1 identity check, `prepare`, `preflight`, `run_leg`, staged harvest and replay, run control, `matrix`, and the command line.
- `benchmark/bench/data/p475_decode_carrier.txt` — the fixed decode carrier, a Python continuation instruction.
- Tests: `test_p475_impl_{support,registry,instrument,default_identity,watch,leg,run}.py`. `support` is the fake box.

Changed (additive):
- `benchmark/bench/capacity_ladder.py` — `rung_problems` (R21), `p475_fields`, and an optional `carrier=` argument to `run_ladder`.
- `benchmark/bench/run_capacity.py` — `--p475-strict`: needs `MLX_BENCH_SESSION_PREFIX`, uses the carrier, `max_tokens` 256, persists the backend fields, records `rung_problems` on each row and exits nonzero if any rung has one. `calibrate_cpt` behaves as before.
- `benchmark/m1/bench_watch.py` — `--driver-create-time` works in every mode; new capacity mode (`--capacity-rows`, `--expected-rung-seconds`) writes JSON ticks with rate and ETA, then a closing exit line.
- `client.py` and `driver.py` are unchanged; `raw_timings` and `session_id` already carried what was needed.

## Commands run (from `benchmark/`)
- `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_p475_impl_*.py` → `161 passed in 9.73s`
- The five capacity suites plus every `bench_watch`, `chain_ops` and `p426_*` test file (22 files) → `557 passed in 31.84s`
- The other test files that import these modules (14 files, including `test_m50_entrypoints`, `test_run_cli_help` and the b2 watch tests) → `396 passed in 60.33s`
- Without `--p475-strict`, output matches the baseline `bc3ad13e` code byte for byte on the same fake driver (ladder and scorecard files; manifest `runtime`/`sampling`).

## What I could not satisfy
- **Acceptance 1, red-first:** not met; the tests came after the code.
- **Acceptance 3:** the box steps are yours by design.
- **`RealOps` is mostly unexercised.** Only its router environment stripping is tested. The `lsof`/`ps`/`pmset`/`psutil` paths, process spawning and `stop_watch` waiting for the watcher to finalize itself are untested.
- **Worker-environment check:** confirm on the smoke leg. I assume the fork's CLI setting `KV_BITS` in-process does not show in the environment `psutil` reads on macOS. If it does, every quantized arm will come back INVALID.

## Ambiguities and how I resolved them
- **P1 — preflight retries:** "retried at most N times" means up to 1+N attempts. A busy box, bound port or refused lock counts as a failed attempt. PASS needs qualify rc 0, `entries[<pick>].status == COMPLETED` (qualify writes no top-level status) and `kv_arm.entry` equal to the pick. `--production-ref` is passed only when given; otherwise qualify uses its default.
- **P2 — driver timeout:** 3 × the expected durations + 900 s for preload and calibration. Without the 900 s the smoke leg's timeout would be about 60 s.
- **P3 — expected rung durations:** the spec's per-leg estimates, split across rungs by each rung's share of prefill tokens. TQ4-OFF uses TQ4's. Override with `--expected-rung-seconds ARM=a,b,c,d`.
- **P4 — "caps monotonic on resume":** a resume may keep or raise a cap; lowering one is refused (exit 2). Used counts persist in `state.json`.
- **P5 — INVALID on resume:** a resume stops again at a standing INVALID leg. You decide by archiving that leg's directory.
- **P6 — strict mode:** keeps the deployed `thinking_budget` ("thinking as deployed") and fixes only `max_tokens` to 256. The predictor comes from the served registry entry, because the contract's driver argv has no predictor flag. The calibration request's session id is recorded in `manifest.runtime.p475_strict`.
- **P7 — worker argv:** exact match. `RealOps` reads the process's own argv and drops the shebang interpreter, as P426 already does (P581).
- **P8 — "process group verified gone":** `Ops` has no group check, so I verify the worker, router, router wrapper and `:8000` listener are gone and `busy()` is empty.
- **P9 — watcher checks:** "exited early" means its exit line is more than 5 s before the driver exit. Required ticks are (span − 2×interval) // interval, which is the contract's formula at 300 s.
- **P10 — native (N16) KV line:** only `kv_bits` is compared (`None` or 0), as written.
- **P11 — TQ4 and prepare:** TQ4 gets branch `p475-u4-tq4` at the base commit. `prepare` symlinks `<WT>/.env` to the repo's `.env`, like the P426 arm worktrees.
- **P12 — matrix completeness:** always requires blocks 1 and 2, even under `--blocks 1`. The deciding block is block 3, in block-1 order.
- **P13 — dossier ladder count:** an INVALID dossier may have zero ladder files; a VALID one must have exactly one (R19).
