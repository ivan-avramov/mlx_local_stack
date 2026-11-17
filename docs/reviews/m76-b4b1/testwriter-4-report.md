**Verdict: merge.** V1 and V2 are fixed on candidate 3. Everything I ran passes: 485 tests, 0 failures, 0 errors, 0 skipped.

## New tests (added to `test_m76_b4b1_fe_fix1.py`, 6 tests)

I wrote these from your V1 and V2 text. I did not use the implementer's tests as a guide.

**V1:**
- **Recorded re-check, another selection (a):** a re-check is sealed and recorded for s1 attempt 1. One arm's s1 leg is then rerun, so attempt 2 is VALID and harvested. This runs for `n16` and `x`. On resume the sequencer stops with rc 1, the sealed file is byte-identical, the `sequence.json` record is unchanged, and `m76_sim.recheck` is never called.
- **Crash window, another selection (a):** the same rerun with a sealed file but no record, for both arms. It stops with rc 1, writes no record and does not re-run.
- **Current selection (b):** the unchanged selection still resumes, re-verifying only.

**V2 (a):** the same item bytes under another checkout sha. A prepared item of the real checkout gives a prompt under the pinned sha. A corpus on those same bytes that reports another sha raises `TransportAbort`. On candidate 2 this test would fail, because only the inputs were checked there.

I did not run these on candidate 2 or on the pre-fix tree. The (a) and (b) classes come from the implementer's red run and from reading the code.

## Counts on candidate 3

Full output is in `../scratch/d4_*.txt` and `d4_*.xml`.
- My six files (`_corpus`, `_grade`, `_chain`, `_wave2`, `_golden_tg1`, `_fix1`): 348 passed, 0 failed.
- The implementer's five `test_m76_b4b1_impl_*.py` files plus `test_registry_published_set.py`: 137 passed, 0 failed.

I ran only the named files. I did not run the full `bench/tests` suite or the importer files. That gate is yours.

## Review

- **V1:** this closes the residual I flagged in delivery 3. The selection check now runs on every sealed re-check, with or without its record, before the sha comparison, and it fails closed with rc 1. I found nothing it breaks. The current-selection resume, the outside re-check with its ack, and the crash-window recovery all still pass.
- **V2:** the prompt path now checks the checkout sha before the inputs. The only cost is one `git rev-parse` per prompt. Identity-only callers are unaffected, as the delivery-3 test shows.
- **Still open, unchanged:** the box-side seams still ran only through fakes (ledger L17, acceptance criterion 3). The tg1 widening from L1 awaits the designer's or operator's confirmation.