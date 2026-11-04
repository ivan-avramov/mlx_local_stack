**Verdict: merge.** Nothing needs fixing in the candidate. There is one test-side defect in my frozen driver tests, which I did not edit.

## What ran
- I applied the candidate diff, and it touches only `registry_states.py` and `qualify.py`. The two test files are byte-identical to the frozen copies.
- Frozen tests: **389 passed, 7 failed** (`test_p475a_kv_arm.py` and `test_p475a_qualify_driver.py`). All 296 tests in `test_p475a_kv_arm.py` pass.
- Neighbours (the nine files you listed): **698 passed, 2 skipped, 0 failed**. This matches the implementer's number.
- Black, isort and autoflake have not been run on the candidate or on my tests.

## The 7 failures are my test's fault, not the candidate's
The failures are the 6 third-entry tests (Ornith, Opus, Nemotron, each with and without a KV change) and `test_refuses_an_unknown_entry_listing_the_registry`. All 7 fail inside my `control()` helper, before the candidate's refusal logic is reached.   <!-- allow-shorthand: verbatim helper output -->

- `control(rig, kv.FIXTURE)` registers the committed TQ4 registry, but `serve(...)` returns an AF8 manifest. The control entry therefore fails with `layer 1: served {'kind': 'aff…`.
- Evidence the candidate is fine: I ran a scratch copy of those scenarios with a matching TQ4 control. All 6 third-entry cases and the unknown entry passed, and the unknown-entry message names `No-Such-Model`. The same probe also passed `--kv-arm` with no `--predictor` and with a duplicated `--entry`. The scratch file is deleted.
- The control bug also meant those tests never exercised the refusal path in delivery 1. It was hidden because the baseline failed earlier, on the missing flag.

## Review against spec v4
- **P1. Interface.** `classify_kv_arm` and `KV_ARM_KEYS` match the spec. `KV_ARM_ENTRIES` is the two picks, and the five rows are exact. Widths are integer-only (`type(bits) is int`, so `true` is refused), and malformed input returns `None`.
- **P2. `quantized_kv_start` rule.** It is enforced only by the settings comparison, with no second check (the AST test passes).
- **P3. Driver.**
  - The gate runs before `registry_states.settings()`, so `models: [null]` is refused instead of crashing.
  - `--predictor on` plus an MTP-OFF entry refuses without building an overlay.
  - `report["kv_arm"]` is set before the entry loop and survives an entry failure.
  - The reference label is added only under the flag and never refuses.
  - Without the flag the report is unchanged (the invariant tests pass).
- **P4. Changes without `--kv-arm`.**
  - The attention rule is now: with `fused_v1`, forced calls are required iff the expected manifest has a native leaf. A missing manifest skips the check, so only the manifest problem is reported. Without `fused_v1` it still requires 0 forced calls. For the committed registries this matches today.
  - `kv_bits` keeps its exact width. Probe results with the candidate:

    | `kv_bits` | result |
    |---|---|
    | 4, 8 | unchanged |
    | 0, 0.0 | `None` |
    | 4.5 | 4.5 |
    | 0.5 | 0.5 (previously `int()` gave 0, i.e. native) |
    | `"4"` (string) | `ValueError` |

  - The `0.5` row is a behaviour change without the flag, an improvement in my reading. The implementer reported that float values change the fingerprint (`turboquant4.0`).
  - The string `"4"` row looks the same as before the candidate, but I didn't test that on the baseline.
- **P5. Implementer's disclosures.** All three are accurate, and I accept them:
  - There is no 16-state gate for `--predictor off` at the baseline, so `--kv-arm` adds a stricter gate rather than relaxing one.
  - `--kv-arm --predictor on` will in practice only work for an arm whose argv equals the certified one, since P542's argv binding is kept. P475's preflight uses `--predictor off`, so it is unaffected.
  - The `--kv-arm` reading of no `--predictor` is a refusal.
- **P6. One spec deviation to note.** The spec says to replace every `classify` use with `classify_kv_arm`. The candidate keeps the P542 `classify()` closure and makes it return the arm's `off` set. The behaviour is equivalent, and my spy test (no `classify` call from `qualify`) passes.

## Before merging
- Run the pinned black 26.3.1 and isort on `qualify.py` and `registry_states.py`, and on my two test files. Neither of us could run them.
- Run the fork's audits. In particular, `qualify.py` and `registry_states.py` live under `dev/`, so confirm the gate stays green.
- Fix the `control(rig, kv.FIXTURE)` bug in my two driver files, in a follow-up, so the third-entry and unknown-entry refusals are actually exercised.
- I would also add a test where the attention rule is exercised through the driver for a no-manifest record.
