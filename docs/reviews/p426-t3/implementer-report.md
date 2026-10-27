The full stack suite on the candidate venvs passes: `6835 passed, 12 skipped, 1 xfailed`. Acceptance 1, 2, 4, 7 and 8 hold in this copy, and the local-gate change is tested. Three things fall short of what the brief asked for; they are listed under 4.

## 1. Files

**Changed**
- `uv.lock`: re-locked with `uv lock`, no `--upgrade`.
- `benchmark/requirements-bench.lock`: regenerated, with the header updated.
- `benchmark/bench/local_gate.py`: `current_parity` reads `.upstream-sync-ref` at the sha, else the workflow. The new `audits_at` parses the fork's `dev/ci.py` `AUDITS` at that sha (nine on S′, the fixed eight otherwise). The audit list is threaded through `audit_argvs`, `steps_for`, `policy_digest`, `digest_for` and `run`.
- `benchmark/bench/p426_plan.py`: label grammar, `EXPECTED_BUILDS["s2"]`, labelled names and paths, live worktree state, record validation, and the patch-level restore-diff assertion.
- `benchmark/bench/p426_wave1.py`: `--build`, `--stack-root-off` and `--stack-root-on`, the `--out` marker, validation before any harvest, and each leg run from its arm's worktree.
- `benchmark/bench/p426_leg.py`: `--build` and `--stack-root-off`, no `--registry-on` under a label, the frozen-record path per label, entry and exit checks of heads, locks and venv versions, and the M1 `overlay-<entry>.yaml` sha check.
- `benchmark/bench/p426_harvest.py`: `wave1_dir(build)`, used by `harvest` and `harvest_run_files`.
- `benchmark/bench/p426_panel.py`: `tunes(build)`, with `build` accepted by `pairs`, `make_pairs` and `item_scores`.
- `benchmark/bench/modelnames.py`: the harvested-evidence exemption now matches `wave1(\.[a-z][a-z0-9]{0,7})?/`.
- `benchmark/bench/tests/p371_baseline/new_side.py`: `rederive` accepts a changed `toolchain/lock_sha256` only when it equals the sha256 of the live bench lock. Without it, the 12 `p371` differential tests fail after any lock change.
- `docs/specs/p426-fable-mtp-recert.md`: R11 now names S′.
- `docs/box-notes.md`: the 2026-10-17 note is kept verbatim with a scope line, plus a new 2026-10-27 note.
- `docs/specs/p405-kv-scheme-precedence.md`: line 60 now reads `draft_model` / `draft_kind`.

**Added**
- `benchmark/bench/tests/test_t3_local_gate.py`: 7 tests, fixtures of both fork layouts.
- `benchmark/bench/tests/test_t3_wave1.py`: 94 tests covering the §6 list.

Nothing deleted. `scripts/bootstrap_machine.sh` and `benchmark/README.md` needed no change.

## 2. Version changes

**`uv.lock`** (causes: the fork requires `mlx-audio>=0.6.2` and `datasets>=4.0.0`, and the S′ pins require mlx 0.32.4)
- Updated: `mlx` 0.32.3 → 0.32.4, `mlx-metal` 0.32.3 → 0.32.4, `mlx-audio` 0.5.6 → 0.6.2, `miniaudio` 1.70 → 1.71 (pulled in by `mlx-audio`).
- Added: `datasets` 5.0.1, with its transitive dependencies `aiohappyeyeballs` 2.7.1, `aiohttp` 3.14.5, `aiosignal` 1.4.0, `attrs` 26.1.0, `dill` 0.4.1, `frozenlist` 1.8.0, `multidict` 7.2.1, `multiprocess` 0.70.19, `pandas` 3.1.0, `propcache` 0.5.4, `pyarrow` 26.0.0, `python-dateutil` 3.0.0, `six` 1.17.0, `tzdata` 2026.5, `xxhash` 4.0.2, `yarl` 1.25.1.
- `transformers` stayed at 5.15.0 and `huggingface-hub` at 1.12.0.

**`requirements-bench.lock`**
- `mlx` and `mlx-metal` 0.32.3 → 0.32.4 (equal to `uv.lock`).
- `mlx-audio` 0.4.8 → 0.6.2 (fork requirement).
- `datasets` 3.6.0 → 5.0.1 (fork requirement, equal to `uv.lock`).
- `miniaudio` 1.70 → 1.71 (from `mlx-audio`).
- Nothing else changed. `uv pip install` first drifted `datasets`, `huggingface-hub`, `click` and `hf-xet`; I pinned them back before freezing.

## 3. Commands and results

- `uv lock` resolved 82 packages. `uv lock --check`: `Resolved 82 packages in 7ms`. `uv sync --frozen`: `Installed 80 packages`.
- Fresh bench venv: `uv venv --clear --python 3.12 --python-preference only-managed .venv-bench`, then `uv pip sync --python .venv-bench/bin/python benchmark/requirements-bench.lock` succeeded. `../bin/py_stack.sh -c "import mlx.core as m, mlx_vlm, mlx_serve, pytest; print(...)"` printed `0.32.4 9.1.1`.
- First full-suite run on the candidate: `12 failed, 6823 passed, 12 skipped, 1 xfailed in 2475.67s`. All 12 were the `p371` lock-sha differential tests.
- After the `new_side.py` fix: `bench/tests/test_p371_baseline.py` and `test_p371_hermetic_scan.py` gave `108 passed in 146.52s`.
- Final `../bin/run_stack_tests.sh` with no arguments: `6835 passed, 12 skipped, 1 xfailed, 4 warnings in 2130.47s (0:35:30)`.
- New files: `test_t3_local_gate.py` `7 passed`; `test_t3_wave1.py` `94 passed`.
- The touched existing tests (`test_p426_wave1`, `leg`, `plan`, `harvest`, `panel`, `test_local_gate`, `test_model_name_check`) passed unchanged in the combined run (`474 passed` alongside the 12 `p371` failures, before the fix).

I did not run a full suite on B0's venvs; I overwrote `.venv-bench` before a baseline existed.

## 4. Not satisfied

- **No failing-on-B0 demonstration.** The brief asked to see each new test fail on B0 first. The commands to export B0 into a scratch tree were refused, and I wrote tests and code together. The new tests call functions that don't exist on B0 (`check_build`, `claim_out`, `restore_diff_problems`, `audits_at`), but I did not run them against B0.
- **No `--build s` edit to the existing sequencer test.** The test directory was read-only for edits to existing tests, so `test_main_refuses_a_workdir_that_is_not_stack_workdir` is unchanged. I enforce `--build` in code (missing value gives rc 2), not with argparse `required=True`, so that test passes unchanged. If you want the spec's literal wording, change the test and the argparse flag together.
- **`new_side.py` change.** The brief lists "tests the suite shows broken" as in scope, so I edited this existing test helper. It is a harness exception for `/runtime/policy/toolchain/lock_sha256`; the helper's docstring states that policy value changes are otherwise never accepted. Please review that exception.
- **Frozen-record field names are my choice.** The spec lists the contents but not the exact keys. My code expects:
  - `build`
  - `stack_head_off`, `stack_head_on`
  - `stack_clean_off`, `stack_clean_on`
  - `mlx_vlm`, `mlx_serve`, `production_ref`
  - `registry_off_sha`, `registry_on_sha`
  - `uv_lock_sha256`, `bench_lock_sha256`
  - `venvs.{off,on}.{.venv,.venv-bench}.{mlx, mlx-metal, transformers, huggingface-hub, datasets, mlx-audio}`
  
  The designer who writes `frozen.s2.json` must use these names.
- **Run files harvested under a label:** only `frozen.s2.json`. The ON registry is the ON commit, and its sha is in the record.
- **Not done, by the brief:** acceptance 3, 5 and 6, and §1.
