I've completed a thorough trace of the change. The core P537 retry/resize logic and the P527 refusal are sound; I found no blocker or major defect. Findings below.

## Summary

The change correctly implements P537 (re-size an invalid-on-every-seed cell to the next pre-registered offset and re-take the seeds, recording the offset used) and P527 (refuse when a pick is MTP-ON in the stack-root registry). I traced:

- **No cell can pass without a real straddle at the recorded offset.** `e1c_verdict` requires both `prompt_end == straddle_target(threshold, offset)` (orchestrate.py.txt:1191) and the per-query `straddle` flag (1201) — or the `verify_blocks_straddle` timings counter for `joint_v1`. The accepted cell's verdict is re-run with `offset=cell["offset"]`, the offset at which it actually became valid (2364).
- **Attempts/seeds are labelled correctly.** Each attempt records `seed` and `offset` from the schedule (2318–2326); `accepted[name]` stores the offset of the one valid attempt (2333).
- **The short cell never retries.** It is always `valid` (`t is None`, 2305) on attempt 0 → accepted, never enters `still`; the `if t is not None` resize filter (2276) is only a safety net.
- **No downstream consumer breaks on >5 attempts or a non-64 offset.** `pick_outcome` (612–661), `smoke_gate` (991), `overall_status` (1142), `binding` (373) all iterate or read named cells; none counts attempts or assumes offset 64. The two `camp.size = lambda pick, thresholds: {}` mocks (test:770, 1228) are safe because `e1c` is also mocked there.
- **P527 fires correctly and cannot be bypassed.** `self.registry = read_registry(self.stack / "main_models.yaml")` (2108), `off = classify(self.registry, fixture)` (2163), and `if problems: raise Refused` (2170) sit in `prepare()`, which `execute()` calls before any pick runs (2704). The OFF arm itself reads the same `main_models.yaml` (2180).
- **Production tree unchanged.** The diff touches only `dev/p369_phase2/orchestrate.py` and `mlx_vlm/tests/...` (the latter is permitted).

## Findings

### F1 — minor (confirmed): the P527 test does not test the refusal it claims
`test_a_pick_that_is_on_in_the_stack_root_registry_is_refused` (test_p369_phase2_orchestrate.py.txt:2733) is named and documented as testing that the run *is refused*, but its body only calls the `registry_off_problems` helper directly — it never invokes `Campaign.prepare()` nor asserts `orchestrate.Refused` is raised. A regression that removes the `registry_off_problems(self.picks, off)` call from `prepare()` (orchestrate.py.txt:2169) would leave this test green.
- *Failure scenario:* someone refactors `prepare()` and drops the `if problems: raise Refused` block; the P527 protection silently disappears while its "test" still passes.
- *Proposed change:* add a case that builds a stack-root `main_models.yaml` with a pick ON and asserts `pytest.raises(orchestrate.Refused, match="MTP-ON")` from `Campaign(args).prepare()`, mirroring `test_m1r2_prepare_itself_hands_the_classifier_the_registry_bytes` (2561), which already proves `prepare()` is the right place to test.

### F2 — minor (hypothesis): the change depends on driver assumption A1, which no test exercises
The resize calls `self.size(pick, [...], offset=65/66)` (2280). `size` raises `RuntimeError` if no exact prompt exists at `T − 65` / `T − 66` (2256). Every new test mocks `camp.size`, so the assumption that the size step yields an exact prompt at the new offsets is unverified. This does *not* weaken evidence — a failure surfaces as `HARNESS_ERROR` (caught by `execute`'s `except Exception`, 2710), not a false PASS — but for a model whose tokenizer cannot hit `T − 65` exactly, the cell becomes un-certifiable rather than re-tried.
- *Proposed change:* add a test that drives the real `Campaign.size` against a stub server returning exact tokens for `T − 65` and non-exact for `T − 66`, asserting the run refuses/harness-errors rather than passing.

### F3 — minor (hypothesis): the `n >= 65` validity floor is a literal that does not track the offset
`valid = t is None or (straddle and n >= 65)` (2306). For offset 64, straddle implies `n >= 65`; for offset 66, straddle implies `n >= 67`, so `n >= 65` is always implied by `straddle` and the literal is harmless. No false-valid result is possible. Flagging only because the change introduces offsets 65/66 while the floor stays pinned at 64+1; a future reader could mis-read it as the validity bound for the new offsets.
- *Proposed change:* either leave a comment that `n >= 65` is a redundant floor implied by `straddle`, or make it `n >= offset + 1` for clarity. No material consequence either way.

## Scope requests (no severity)
- S1: A test exercising the non-smoke path with two thresholded cells that pass at *different* offsets (one at 64, one at 66) together with the short cell, asserting the short cell appears once in `attempts` and each accepted cell carries its own offset. The current tests all use `smoke=True` with a single thresholded cell, so the multi-cell resize and the short-cell-never-retries invariant under the new schedule are not directly covered.

NOTHING OF SUBSTANCE at blocker or major severity.
