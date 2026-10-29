I read `BRIEF.md` and `VERIFY.md`, then traced the repair (`repair.diff`) against the post-repair source (`orchestrate.py.txt`, `test_p369_phase2_orchestrate.py.txt`) and the worker/observer (`worker.py.txt`, `observe.py.txt`).

## Disposition of the opinion's findings

**1. E2 straddle requests used the T−64 prompts — resolved.** `e1c` now stores the accepted prompt per thresholded cell in `self.accepted_prompts[pick]` (orchestrate.py.txt:2426-2433), and `run_pick` passes `e2_prompts(prompts, accepted_prompts.get(pick, {}))` into `e2` (orchestrate.py.txt:2714-2719). `e2_prompts` substitutes the accepted prompt only for thresholds E1c accepted, falling back to the sized prompt otherwise (orchestrate.py.txt:591-593). Since `e2` runs only when `e1c == PASS` (every thresholded cell accepted), every threshold has an accepted prompt, so the fallback is dead in the live path. `test_the_retry_sends_the_re_sized_prompt_and_the_accepted_prompt_feeds_e2` confirms both the re-sized text is sent and the accepted prompt feeds E2.

**2. A re-size with no exact prompt raised and lost its attempts — resolved (with one edge, see new finding N1).** `size` gained `strict=False` (orchestrate.py.txt:2247-2273); re-sizes call it with `strict=False` (orchI read `BRIEF.md`, `VERIFY.md`, traced `repair.diff` against the post-repair source, and cross-checked `worker.py.txt`/`observe.py.txt`.

## Dispositions

**1 (E2 used T−64 prompts) — resolved.** `e1c` records accepted prompts in `self.accepted_prompts[pick]` (orchestrate.py.txt:2426-2433); `run_pick` feeds `e2_prompts(prompts, accepted_prompts.get(pick, {}))` to E2 (2714-2719); `e2_prompts` substitutes the accepted prompt per threshold (591-593). E2 only runs when every thresholded cell is accepted, so the fallback path is dead live.

**2 (no-exact-prompt re-size raised) — resolved.** `size(..., strict=False)` parks a threshold instead of raising (2247-2273); parked cells are re-sized at the next offset's first seed (2287-2297); a cell no offset can size ends INCOMPLETE with `no exact prompt at offset N` (2442-2456). `test_a_re_size_that_finds_no_exact_prompt_parks...` and `test_a_cell_that_no_offset_can_size_is_incomplete...` cover it.

**3 (re-size overwrote size dir) — resolved.** `name = "size" if offset == 64 else f"size-o{offset}"` (2262); `test_each_sizing_offset_has_its_own_job_directory` confirms `["size", "size-o65"]`.

**4 (P527 tested only the helper) — resolved.** `registry_off_problems` is wired into `prepare` after `classify`, before any `worker_argv` (2178-2180). `test_prepare_refuses_a_pick_that_is_on_in_the_stack_root_registry` builds an ON-in-stack-root registry and asserts `Refused` with `built == []`.

**5 (retry test didn't check re-sized prompt sent) — resolved.** `test_the_retry_sends_the_re_sized_prompt...` captures `e1c_pair` payloads and asserts `["x"]*k + ["prompt-1024-65"]`, plus `accepted_prompts[FABLE]`. <!-- allow-shorthand: test constant name, verbatim member output -->

**6 (projection omits retries) — resolved (adapted).** `phase_projection` docstring now disclaims retries up to 15 attempts / two re-sizes (1894-1896). No wall cap, per the operator ruling.

**7 (n≥65 doesn't track offset) — declined, consistent with the disposition.** `straddle=True` already implies enough tokens to cross T at every offset; no consequence traced.

**8 (multi-cell test) — not applied (scope), as reported.**

## New findings

**N1 — minor — initial offset-64 sizing is strict, so "no offset can size" can end as HARNESS_ERROR, not INCOMPLETE.**
- Location: `orchestrate.py.txt` run_pick `prompts = self.size(pick, thresholds)` (2688), which uses the default `strict=True`.
- Evidence: confirmed. `size` defaults to `strict=True` (2247); only re-sizes pass `strict=False` (2290). So if the offset-64 sizing yields no exact prompt for some threshold, `size` raises `RuntimeError` → `HARNESS_ERROR` before `e1c` ever runs. Finding 2's disposition states "a cell no offset can size ends INCOMPLETE with `no exact prompt at offset N`," which implies all three offsets are tried leniently; the implementation only tries 65/66 leniently.
- Problem: under the unsupported case where offset 64 cannot size a threshold but 65 or 66 could, the run aborts as a harness error instead of recovering via the schedule. Under assumption A1 (T−64 sizes exactly, as do T−65/T−66) this never bites, so the consequence is nil in supported conditions — hence minor.
- Failure scenario: a model whose tokenizer cannot land exactly T−64 tokens for one threshold (closest ≠ target) but can land T−65; `run_pick`'s `self.size` raises before `e1c`, so the pick is HARNESS_ERROR rather than INCOMPLETE with a size-failure record.
- Proposed change: either size the initial prompts with `strict=False` and let `e1c` park offset-64 failures too (so the "no offset can size → INCOMPLETE" path covers all three offsets), or narrow finding 2's disposition to "a re-size with no exact prompt…".

**N2 — minor (test realism, no production impact) — the parametrized "invalid on every seed" test carries a stale `prompt_end` for offset-65/66 attempts.**
- Location: `test_p369_phase2_orchestrate.py.txt:1885-1912` (`test_e1c_cells_invalid_on_every_seed_keep_their_attempts_evidence`).
- Evidence: confirmed. The test clones the base entry (whose `prompt_end = straddle_target(1024) = 960`) for all 15 attempts without re-stamping `prompt_end` per offset, so attempts 5-14 are judged against `straddle_target(1024, 65/66)` and accrue a spurious `prompt_end … != …` evidence line in their `problems`. The real worker records `prompt_end` = the actual cache offset (= T − offset), so this mismatch cannot occur in production.
- Problem: the test exercises the retry schedule but its attempt records are not faithful to what the worker would emit; it still passes only because `pick_outcome` decides on `rejected[].c1/neutral`, not `problems`.
- Failure scenario: a future change that makes `pick_outcome` or the smoke gate inspect per-attempt `problems` would make this test assert on noise it never intended.
- Proposed change: in the loop, set `attempt["prompt_end"] = orchestrate.straddle_target(1024, orchestrate.STRADDLE_OFFSETS[k // len(orchestrate.SEEDS)])` so each attempt's `prompt_end` matches the offset that sized it.

Nothing else breaks: `pick_outcome`, `smoke_gate`, `binding`/`binding_problems`, and the manifest/summary writers consume `attempts`/`rejected` generically (no `len(SEEDS)` assumption, no offset assumption), so >5 attempts and non-64 offsets flow through; `e1c_verdict`'s `offset` defaults to 64 so existing callers are unaffected; the worker computes `straddle` from `key_lengths.blocks` and `prompt_end` from the cache offset, both independent of the harness offset, so no `worker.py`/`observe.py` change is needed; and both diffs touch only `dev/p369_phase2/orchestrate.py` and `mlx_vlm/tests/test_p369_phase2_orchestrate.py`, leaving the production tree untouched.
