The legacy chain harnesses now serve the pinned OFF registry by default, and every file you listed passes under both the live ON registry and a swapped-in OFF copy. `main_models.yaml` is restored; `git diff HEAD --stat -- main_models.yaml` is empty.

The change was small:

- **Shared helper:** `pinned_off_registry()` and the sha256 assert now live in `test_c147_chain_runner.py`.
- **Default registry:** `FakeOps.__init__` sets `self.overlay` to the pinned copy. The runner's `served_registry` falls back to `ops.overlay`, so every harness built on `FakeOps` follows. That covers the c147, p371, p311, p364, p290, p279 and isolation harnesses, and the baseline `new_side` harness through its `T.FakeOps` subclass.

## Files changed in this follow-up

- `benchmark/bench/tests/test_c147_chain_runner.py`: adds `OFF_REGISTRY_FIXTURE`, `OFF_REGISTRY_SHA256` and `pinned_off_registry()` (the sha256 assert stays), plus `import hashlib`; `FakeOps.__init__` sets `self.overlay` to the pinned copy.
- `benchmark/bench/tests/test_b2_s1_cli.py`: drops its own copy of the helper and imports the shared one.
- `benchmark/bench/tests/test_m63_predictor.py`: `test_m3_production_wiring_off_is_the_c147_layout` now passes `registry=pinned_off_registry()` and expects that path instead of `R.REPO / "main_models.yaml"`.
- `benchmark/bench/tests/test_b2_s7_locks.py`: adds `test_no_chain_harness_serves_the_live_registry`.

## Hermeticity test

It runs a legacy chain through `run()` with no `registry=` and records what `served_registry` returns. It asserts that is the pinned copy and not `REPO / "main_models.yaml"`, and that `FakeOps().overlay` is the pinned copy. A control line asserts that without ops the runner would pick the live file, so the guard can fail. I did not run it red against the old `FakeOps`.

## Goldens

No golden or expected value changed. The one expectation I rewrote, in `test_m63_predictor.py`, was a path comparison to the live file. The p371 baseline goldens pass unchanged.

## Commands and results

- **Before the fix:** the six files outside the main set (`test_p290_docker_gate.py`, `test_p279_smoke.py`, the three `test_p371_review_*_tg1` files, `test_m63_predictor.py`) failed with 15 failures, all the live-registry refusal.
- **After the `FakeOps` change:** `test_c147_chain_runner.py`, those six, `test_b2_s1_cli.py` and `test_b2_s2_probe.py` left one failure, the production-wiring test above. `test_p371_chain_core.py`, `test_p311_chain.py`, `test_p364_chain.py`, `test_p371_isolation.py`, `test_p371_baseline.py` and `test_m63_predictor.py` then ran clean (all `.`, no failures).
- **Full list, live registry (MTP ON):** `../bin/run_stack_tests.sh` over the 18 files:
  - the 12 files you listed
  - `test_b2_s7_locks.py`, `test_b2_s1_cli.py`, `test_b2_s2_probe.py`
  - `test_local_gate.py` (the only match for `test_local_gate*.py`)
  - `test_b2_fix_chain.py`
  - `test_t3_wave1.py`
  - Result: `791 passed in 442.96s (0:07:22)`
- **Same list with the pinned OFF copy copied over `main_models.yaml`:** `791 passed in 446.16s (0:07:26)`.

I did not run `test_m61_web_audit.py` or the full suite, and I did not touch non-test code, frozen files, `src/` or the spec.
