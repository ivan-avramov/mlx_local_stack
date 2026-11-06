**Verdict: merge, with two conditions that are not code fixes.** The candidate passes all 112 of my frozen tests. The full suite has one failure, which I believe comes from this copy's venv rather than from the candidate. Before the fork's gate counts it, run `dev/ci.py style` (the implementer never ran the formatters) and the full suite in the real checkout.

## 1. Candidate applied
`git status` shows `orchestrate.py`, `qualify.py` and `worker.py` modified, plus my three test files, `test_p658_impl_engagement.py` and `.p658-material/` untracked. `git diff --stat` reads 82 insertions and 8 deletions in `dev/p369_phase2/`. The candidate touches nothing under `mlx_vlm/` outside `tests/`. I could not run the `git diff d94e38a9 -- mlx_vlm` check myself because the tool needed approval.

I did not record a hash of my three test files, so "frozen" rests on my not editing them since the first delivery. A reverse-apply I tried from `mlx_vlm/` did not take effect, and I confirmed the candidate is still fully in place.

## 2. Frozen tests: `112 passed, 2 warnings in 34.9s`
No failures and no errors, and the same named tests ran as in the first delivery. 79 tests moved from fail to pass and 33 passed both before and after.

| File / group | Class | Baseline | Candidate |
|---|---|---|---|
| `test_p658_engagement_only.py`: refusals, gate rules, 10 arm cells × (completes, argv), tamper, registry-change, target manifest, job flag, drafter judgement (quantized, TQ, batch, mismatch, absent, ignored field, 14 malformed forms), report fields | exercises new behaviour | 53 fail (the "keeps the pick rule" and "tampered argv" tests are among them after my strengthening) | all pass |
| `test_p658_engagement_only.py`: `command_problems` tamper, no-flag job, no-flag report, `request_problems` ignores drafter, uncertified refusal without the flag, P369 summary still needed | preserves an invariant | 21 pass | all pass |
| `test_p658_launcher.py`: p475_kv ancestor exempt, chain exempt, sibling not exempt, real-topology parent, `LAUNCHER_MODULES` tuple | reproduces a failure the spec fixes / new behaviour | 6 fail | all pass |
| `test_p658_launcher.py`: non-ancestor and other `bench.*` still refuse, caller never foreign, P426 launcher still exempt | preserves an invariant | 11 pass | all pass |
| `test_p658_worker_drafter_manifest.py`: record gains `drafter_manifest`, read before release, quantized leaf recorded, empty observed, target part unchanged | exercises new behaviour | 5 fail | all pass |
| `test_p658_worker_drafter_manifest.py`: no job field gives today's keys, falsy field (False / None / 0) records nothing | preserves an invariant | 4 pass | all pass |

## 3. Full fork suite
```
FAILED tests/test_p369_phase2_worker.py::test_check_sources_refuses_a_module_outside_the_reviewed_tree
1 failed, 10004 passed, 18 skipped, 22 xfailed, 10 warnings, 685 subtests passed in 508.98s (0:08:28)
```
This was serial, from `mlx_vlm/`, with the command you gave. The implementer reported 9893 passed with 0 failed. Adding my 112 tests gives 10005, which equals my 10004 passed plus the 1 failure, so the counts reconcile.

**The failing test.** The only failure fails at its first call, `worker.check_sources(root, DEV)` (test line 204), with `RuntimeError: modules outside the reviewed sources`. The modules it names (`mlx_vlm.quant_utils`, `mlx_vlm.models.cache`, `mlx_vlm.turboquant`, …) are loaded from `<fork>/mlx_vlm/`. The venv I was told to use is an editable install of the main checkout, so `import mlx_vlm` resolves there, not to this worktree. It also fails when run alone.

The candidate does not touch `check_sources`, so I believe this is a worktree artifact. I did not confirm that on the baseline because my revert attempt did not work. Please re-run this test in the real checkout.

## 4. Review

**What works.** I read the full diff and found no defect against the spec's interfaces.
- The two refusals run before the lock (`qualify.py:1211-1218`).
- `kv_arm_gate` drops only the non-empty-delta refusal; the MTP-OFF refusal stays (`qualify.py:1097-1105`).
- `entry_problems` skips the summary requirement and does not apply `argv_binding_problems` (`qualify.py:306-312`, `1314-1315`). `command_problems` and `binding_problems` still bind the argv.
- The worker records the drafter after the `finally` that restores patches and before `release_session` (`worker.py:1577-1582`). `run_job` passes the keyword only when `job["drafter_manifest"] is True` (`worker.py:1688-1691`), so the no-flag call and record are unchanged.
- `reference` is `None` under the flag (`qualify.py:1532`), and `capacity_gb` is still recorded.
- Report fields and the launcher tuple match the spec.

**R1 (unproven, medium).** Nothing here shows the real MTP drafter has a populated `_cache` when read at `worker.py:1578`. My worker tests use a fake drafter, and I could not run a GPU model. If serving resets or clears that cache at request end, every engagement run fails with `drafter cache [] vs template`. That would fail loudly, not give a false pass. The first live N16 or TQ4 run is the real test, and it is worth doing before spending a long TQ8 run.

**R2 (low).** A missing `rg.draft_model` raises after the full 256K-class request has run (`worker.py:1578`). The spec's literal form makes this the expected behaviour, and `check_loaded_drafter` already guards the MTP case earlier. A check before the request would only save wall time.

**R3 (low, design).** Under the flag an entry still reports `status: COMPLETED`. Only the report's top level says `certifies: false`, so a consumer that reads per-entry status could treat the run as certification. The spec chose this, and the stack side should read `certifies` before relying on it.

**R4 (beyond spec, benign).**
- `entry_problems` also refuses any arm other than `served_on` under the flag (`qualify.py:307-311`). This duplicates the gate.
- `drafter_manifest_problems` returns `"no drafter cache manifest (malformed leaf record)"` for entries that are not `{path, kind}` dicts (`qualify.py:1124-1129`). The spec covers only absent, empty or not-a-list, and the alternative would be a `KeyError` that ends the entry as an error. No frozen test covers this wording.

**R5 (process).** Formatting was not run, per the implementer's report. I eyeballed the longest added lines at roughly 85 characters, but black has not checked them.

**What my tests miss.**
- The live drafter cache (R1).
- The real `orchestrate.preflight` end to end. Only the census path is covered.
- A missing `draft_model`.
- The malformed-leaf wording.
- Any run of `dev/ci.py audits`. I did not run it; the implementer reports 9 ok.

I changed no source file and none of my frozen test files.
