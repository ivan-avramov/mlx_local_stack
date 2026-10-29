I found two real defects, three minor ones and one scope request. I only read the files and didn't run anything, so every finding comes from reading the source.

**1. A failed re-size aborts the whole E1c step and loses the recorded attempts**
- Location: `Campaign.e1c`, `orchestrate.py.txt:2275-2281`, calling `Campaign.size` at `:2255-2259`. The caller is `run_pick` at `:2661-2667`.
- Severity: major. Evidence: confirmed in the source.
- Problem: when a cell is invalid on all five seeds, the retry calls `size()` for `T−65` or `T−66`. `size()` raises `RuntimeError("no exact prompt…")` if `size_prompt` returns `None`, which is what `worker.py:741` does when no filler/nudge hits the target exactly.
- This is A1. The `T−64` target was presumably tested on these tokenizers. The new targets have no such evidence, and the exact-count search is a heuristic.
- `run_pick` catches only `JobTimeout`. A `RuntimeError` therefore goes to `execute()` and is recorded as HARNESS_ERROR.
- Scenario: T=8192 is invalid on five seeds, `size(8192−65)` finds no exact prompt, and the pick ends with no `record["e1c"]`. The five attempts exist only on disk. Other thresholds' cells that had already passed are not in `summary.json` either.
- Fix: catch the sizing failure inside `e1c`. Record it as an evidence problem on the pending cells (INCOMPLETE, with an attempt entry that says why). Do not raise. Or size all three offsets for the thresholded cells up front, so a sizing failure appears before any GPU E1c attempts. The schedule stays fixed.

**2. E2 straddle requests still use the `T−64` prompts**
- Location: `run_pick`, `orchestrate.py.txt:2646` and `:2671`, and `Campaign.e2` at `:2517-2533`.
- Severity: major. Evidence: confirmed in the source. This goes against A2.
- Problem: E2 builds its per-threshold "straddle" requests from the original `prompts`, sized at `T−64`. The E1c cell was accepted at 65 or 66, and E2 never uses that prompt. In the case the change exists for, the `T−64` prompt is the one known not to straddle, because a block commits exactly at 8192.
- The projection comment says the E2 straddles run "at the E1c rate".
- E2 has no straddle validity check, and E2 runs only after E1c passes. So the run can pass with an E2 "straddle" cell that never straddles.
- Scenario: T=8192 is valid only at offset 65. E2 sends the `T−64` prompt, and the report lists a threshold-8192 E2 straddle that was never one.
- Fix: have `e1c` return, or record, the accepted prompt per threshold, and pass those prompts to `e2`. Alternatively, record that E2's straddle cells are not straddle-checked. The first is a scope request, and I'd prefer it.

**3. Re-sizing overwrites the original size job's directory**
- Location: `Campaign.size`, `orchestrate.py.txt:2253`. The job is always named `"size"`, so `out_dir` is `out/<pick>/size`.
- Severity: minor. Evidence: confirmed.
- Problem: `run_job` reuses the directory and rewrites `job.json`, `result.json`, `worker.log` and the progress files. After a retry, the on-disk record of the `T−64` sizing is gone, and the last offset's record replaces it. Only the final offset is left.
- Fix: name the job per offset, for example `size` for 64 and `size-o65` for 65. Keep the offset-64 name unchanged.

**4. The P527 test covers only the helper, not the refusal**
- Location: `test_p369_phase2_orchestrate.py`, last test, and `prepare()` at `orchestrate.py.txt:2168-2171`.
- Severity: minor. Evidence: hypothesis, because `registry_states.classify` is not in the material.
- Problem: the test calls `registry_off_problems` directly with hand-made sets. Nothing checks that `prepare()` raises `Refused` when a pick is ON in the live registry, or that `classify`'s return value really is "the set of picks that are OFF". The test suite already stubs `classify` with a spy, so a wiring test is cheap.
- The `registry_off` manifest entry is `sorted(off)`, which suggests the set meaning is right, but it is untested.
- Fix: add a `prepare()` test with a registry fixture that has the pick ON, and assert `Refused`.

**5. The retry test doesn't check that the re-sized prompt is sent**
- Location: `test_e1c_retries_a_cell_invalid_on_every_seed_at_the_next_offset`.
- Severity: minor. Evidence: confirmed.
- Problem: `size` is stubbed and `run` is mocked. The test checks the `size` call arguments and the attempt labels. It never checks that the `e1c_pair` job at attempt 5 carries the text `prompt-1024-65` instead of the old text. If the `pending = list(self.size(...).items())` assignment were dropped, the test would still pass: the attempt files are fabricated, and the labels come from the schedule.
- Fix: capture the job requests in the stubbed `run`. Assert that the payload content at attempt `k` is the re-sized text and that earlier attempts used the original text.

**6. Unbounded wall time in the smoke projection**
- Location: `phase_projection`, `orchestrate.py.txt:1886-1903`.
- Severity: minor. Evidence: hypothesis.
- Problem: the projection scales E1c from the smoke's measured time, with at most five attempts assumed. The new schedule allows 15 attempts plus two sizing jobs per invalid thresholded cell. `fits` and the projected total are therefore optimistic in exactly the case this change addresses. A campaign without `--wall-limit-s` has no cap.
- Fix: report the worst case, or state that the retries are excluded from the projection.

**Checked and no defect found**
- The verdict and attempt offsets are consistent: each accepted cell carries the offset of the attempt that accepted it, and `e1c_verdict` is given that offset for both the attempt and the final verdict.
- The short cell is always valid at attempt 0, so it never re-enters the retry path.
- `pick_outcome` reads only `rejected[].neutral` and `rejected[].c1`, so it handles more than five attempts and a non-64 offset.
- Nothing outside `dev/p369_phase2/` and the test file changes.
