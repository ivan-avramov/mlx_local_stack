**Dispositions**

1. E2 straddle prompts: resolved in the code, but the `run_pick` wiring has no test (see finding A). `e1c` records `accepted_prompts[pick]`, keyed by threshold, from each accepted cell's `text`. `run_pick` passes `e2_prompts(prompts, accepted)` to `e2`. Thresholds without an accepted cell fall back to the sized text, which only matters on paths where E2 doesn't run.
2. Re-size with no exact prompt: resolved. `strict=False` skips the threshold, and `parked` plus `size_failures` carry it to the next offset. A cell that no offset can size ends INCOMPLETE with the reason in its problems. The earlier attempts are kept, because the final loop reads `attempts[name]` and every cell has attempts from offset 64. The `attempt` counter now advances only when a job runs, so the `e1c-pair-a<N>` directory names stay contiguous. The loop terminates correctly.
3. Size job directory: resolved. Offset 64 keeps the name `size`, and other offsets use `size-o<offset>`.
4. `prepare()` wiring test for P527: resolved. The test refuses before `worker_argv` runs and asserts that nothing was built.
5. Re-sized prompt is sent: resolved. The test captures the sent request texts per attempt and the accepted prompt.
6. Projection: resolved as adapted. Only the docstring changed, which is acceptable under the stated ruling.
7. `n >= 65`: the decline is accepted.
8. The multi-cell scope request: not applied. This is acceptable because it was a scope request.

**Findings**

**A. The `run_pick` to `e2` wiring is untested**
- Location: `run_pick`, `orchestrate.py.txt` (the `e2_prompts(...)` call), and the new tests.
- Severity: minor. Evidence: confirmed. The grep shows no test that checks `e2` receives the accepted prompts.
- Problem: the tests exercise `e1c`'s `accepted_prompts` and the `e2_prompts` helper separately. Nothing checks that `run_pick` actually uses them.
- Scenario: a later edit reverts the call to `self.e2(pick, items, prompts, ...)`. All tests still pass, and E2 silently goes back to the `T−64` prompts, which was the original finding.
- Proposed change: extend the existing `test_run_pick_saves_each_step_as_it_finishes` fixture, or add a test, that stubs `e1c` to set `accepted_prompts` and asserts the prompts `e2` receives.

**B. The "parks" test has a no-op assertion**
- Location: `test_a_re_size_that_finds_no_exact_prompt_parks_the_cell_for_the_next_offset`.
- Severity: minor. Evidence: confirmed.
- Problem: `assert k` is always true, and `k` is otherwise unused. The comment "attempt files are written per attempt index" couples the test to a hard-coded `a5` path. It does not check the attempt labels, and it does not check that no job ran for offset 65.
- Proposed change: drop `k`. Assert `[a["offset"] for a in cell["attempts"]] == [64]*5 + [66]`, and assert that no `e1c-pair` job was sent at offset 65.

I found nothing that blocks the repair. The repair introduces no new wrong or mislabelled offset or seed, and no new bypass.
