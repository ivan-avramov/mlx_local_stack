`--engagement-only` is in place and acceptance criteria 1–6 are met. Criterion 7 is not fully met: the pinned formatters (black, isort, autoflake) never ran on the changed files, because running them needed approval I didn't have. There is also one failure that shows up only in parallel runs, described below. The production diff is empty. Nothing is committed and HEAD is still `d94e38a9`.

## Files changed
- `dev/p369_phase2/qualify.py` — adds the `--engagement-only` flag. Without `--kv-arm` and `--predictor on`, or with `--p369-summary`, it refuses before the lock using the spec's exact messages.
  - Under the flag, `kv_arm_gate` accepts any delta `classify_kv_arm` accepts; an MTP-OFF entry still refuses.
  - Under the flag, `entry_problems` drops the P369 summary requirement and `argv_binding_problems` is not applied. `command_problems` and `binding_problems` still bind the served argv.
  - Under the flag, the run: sets `job["drafter_manifest"] = True`; adds a new `drafter_manifest_problems(rec)` (wrapping `kvmanifest.drafter_problems`) to the entry's problems; writes `engagement_only: true` and `certifies: false` in the report; sets `reference` to `None`; copies `drafter_manifest` into each entry's final state.
- `dev/p369_phase2/worker.py` — `qualify_request(..., *, drafter_manifest=False)` records `{observed, template}` after the response finishes and before `release_session`. `run_job` passes the keyword only when the job has `drafter_manifest: true`, so the no-flag call is unchanged.
- `dev/p369_phase2/orchestrate.py` — adds `"bench.p475_kv"` to `LAUNCHER_MODULES`.
- `mlx_vlm/tests/test_p658_impl_engagement.py` (new) — 44 tests covering criteria 1–6, including a real-process test (skipped if psutil is missing) for a `bench.p475_kv` parent, a non-ancestor `bench.p475_kv` sibling and a `bench.other` parent.

## Commands and results
- New tests on the unchanged baseline: 34 failed, 10 passed, 1 skipped (red first; the 10 are the no-flag checks).
- New tests after the change: 44 passed.
- The existing qualify / orchestrate / worker / kvmanifest tests (`test_p369_phase2_*`, `test_p415_qualify`, `test_p426_qualify_predictor`, `test_p452_qualify_in_wrapper`, `test_p475a_*`, `test_p542_*`) plus the new file, unmodified: 1292 passed, 1 skipped (an existing opt-in skip).
- `dev/ci.py audits`: 9 ok, 0 failed.
- Full suite, serial (how `dev/ci.py` runs it), twice: 9893 passed, 18 skipped, 22 xfailed, 0 failed both times, with identical skip lists.
- Full suite with `-n 4`: run 1 had 0 failures. Runs 2 and 3 each had 1 failure, `test_speculative.py::test_qwen3_5_ragged_decode_attention_matches_two_pass_singleton`. It passes alone (several runs), passes with the whole of `test_speculative.py`, and passes in both serial runs. That file doesn't reference `dev/` or `p369_phase2`, so I don't think my change causes it, but I didn't check it against the baseline under `-n 4`.
- `git diff --stat d94e38a9 -- mlx_vlm ':!mlx_vlm/tests'`: no output.

## Not satisfied
- **Formatting:** `uvx black/isort/autoflake` and reading the venv's `bin/` both needed approval, so neither ran. I checked by hand that every added line over 88 characters is a comment or string, which black leaves alone. Run `pre-commit` (or `dev/ci.py style`) before committing.

## Ambiguities and how I resolved them
- **Refusal order:** with `--engagement-only`, the "needs `--kv-arm --predictor on`" check runs first, then the `--p369-summary` check. Both run before the lock.
- **Arm check:** `entry_problems` under the flag also refuses any arm other than `served_on`. The gate already blocks that case, so this is a second safeguard.
- **Malformed drafter records:** list items that aren't `{path, kind}` dicts give `"no drafter cache manifest (malformed leaf record)"` instead of crashing. The spec only covers absent, empty or not-a-list.
- **Missing drafter in the worker:** I followed the spec literally (`rg.draft_model._cache or []`). If `rg.draft_model` is `None`, this raises and the entry ends as an error, which is FAILED.
- **Capacity under the flag:** only `reference` becomes `None`; `capacity_gb` and `vs_guidance_gb` are still recorded. I read "no capacity comparison" as referring to the reference comparison only.
- **Call compatibility:** the new keyword arguments to `kv_arm_gate` and `entry_problems` are passed only when the flag is set, so existing fakes with the old signatures still work.
