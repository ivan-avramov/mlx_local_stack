**Verdict: merge.** All six adopted rows (L1–L6) resolve as the ledger dispositions state, and I found nothing candidate 2 broke or silently widened beyond what is listed below.

## Tests and counts (candidate 2)

New file `bench/tests/test_m76_b4b1_fe_fix1.py`: 50 tests, all passing. One test in my frozen `_wave2.py` also changed (listed after the table).

| Row | Tests | Class |
|---|---|---|
| L1 | A real-shaped v2 row verifies through the real `inject_verify.check_files`, with and without `toolwindows` (2). A missing, extra or mismatched key fails (7 mutants). A tg1 three-key row is unchanged. A tg1 row that records `datefreeze` now verifies, and its two failing variants still fail. | Real-shaped row: (a). Mutants: (a), pinning that the fix did not loosen the check. tg1 three-key: (b). tg1 `datefreeze`: (c). |
| L2 | A drifted checkout sha refuses before anything is materialised (3 variants), and so does a drifted item input. A drifted checkout never produces a prompt. An unchanged copy prepares. Identity still works without a checkout. | Refusals: (a). Unchanged copy and identity: (b). |
| L3 | Both files absent computes once. A record without its file stops with rc 1 and never re-runs. A sealed file without its record is recorded from the file (inside continues, outside stops with rc 5 until acked). A changed sealed file stops with rc 1 (with and without a record). A sealed file of another selection is not adopted. | Record-without-file, file-without-record (inside and outside): (a). Compute-once and changed-file: (b). Other-selection: (c). |
| L4 | A stray row, a stray DNF and a row/DNF overlap each refuse. A DNF of another session is ignored and the plain case scores 80. | The three refusals: (a). The other-session guard: (b). |
| L5 | `--r1-off` / `--r1-on` under `--corpus tg2` refuse with an R1 message. The same command without them is not refused for R1. | Refusals: (a). Without them: (b). |
| L6 | Rehearsal and v8 refuse `n16,v`, `x,v`, `v,x` and `x,n16`. The leg table, positives (x and v), the sequencer, the chain `--kv-arm v` and records of another pair all refuse. The `n16,x` record is accepted. | Mostly (a). Some already held on candidate 1: the sequencer's `n16,v` and `x,v`, and the `n16,x` record accept. |

The class labels come from the implementer's red run on candidate 1 and from reading the code, not from my own run on candidate 1. I could not build candidate 1 here without touching the baseline, so I did not run these tests on it.

**One amended delivery-2 test:** the stray-row test is now the restored refusal, as the ledger asks for. It had asserted the opposite. Its duplicate-row refusal is kept.

**Counts, full output in `../scratch/d3_*.txt`:**
- My six files (`_corpus`, `_grade`, `_chain`, `_wave2`, `_golden_tg1`, `_fix1`): 342 passed, 0 failed.
- The implementer's five `test_m76_b4b1_impl_*.py` files plus `test_registry_published_set.py`: 133 passed, 0 failed. The registry test, which failed 2 on candidate 1, now passes.
- Nothing was skipped, and no test failed for the missing `.venv-bench`.
- I did not run the importers of the changed modules or the full suite. That is the designer's gate.

## Review of the fix round

- **L1:** The fix is correct. The real tg1 probe already wrote `datefreeze` into `evidence_sha256` (`arm_opencode.row_fields`), so tg1 inject rows failed `FAIL:evidence_sha256_keys` before the fix too. `test_c147_inject_verify` only passed because its fixtures were unrealistic three-key rows.
  - The key set must now equal the row's recorded artifacts exactly, with each path present and hashing to its digest. tg2 requires `datefreeze`.
  - tg1 rows without `datefreeze` are checked as before. The widening is limited to a tg1 row whose recorded artifacts are hash-verified. It is not a loosening, and I would confirm it (deviation 1).
- **L2:**
  - **Resolves L2 as dispositioned:** `prepare` calls `verify_source`, which checks the checkout sha, then `verify_inputs`, before materialisation. `spec_text` does the same before any prompt.
  - **Where the checks sit:** not in `load_universe` (deviation 2), so identity-only callers keep working, as my test shows.
  - **Closure side effect:** the static `m65.tg2_universe` import (deviation 3) puts that module in the tg2 probe's code closure and rotates the tg2 closure identities. That matches C178, and the tg1 closure is untouched.
- **L3:**
  - **Recovery rules:** the three resume states behave as dispositioned, and the implementer's extra comparison works. A sealed file whose `attempts` differ from the current selection is refused rather than adopted. This is an addition to the ledger, and it is safe because it only ever refuses.
  - **Residual risk:** an operator rerun of an s1 leg after a re-check was recorded changes the selected attempts. The record-plus-file path compares only the sha, so it is not blocked. This is the same as before, so I do not count it as new.
- **L4, L5, L6:** these resolve as dispositioned. L6 also holds below the CLI (`kv_tg2_legs` raises `ValueError`; the freeze, rehearsal, v8 and amendment paths check the pair). `--kv-arm` choices are the tg2 pair.

**Open points (none block the merge):**
- The L1 and L3 box-side seams are still exercised only through fakes. L17 stays acceptance criterion 3.
- The implementer's question on L1, whether tg1 should keep the strict three-key set, is the operator's or designer's call. My recommendation is to keep the exact-recorded-artifacts rule, because the strict three-key rule fails every real tg1 inject row.