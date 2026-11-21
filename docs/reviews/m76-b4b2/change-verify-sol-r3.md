Resolution trace:
- D1: not resolved; see F1.
- D2: resolved. `_a8_latency → a8_utc_seconds` now rejects non-finite or pre-epoch ISO timestamps.
- D3: resolved. `_a8_session → a8_v8_identity_reasons` binds schedule, manifests, and rows to `ENTRY`.
- D4: resolved. `_a8_accounting → _a8_rerun_index` converts malformed row-ledger/list indices into `RefusalError`.
- D5: not resolved; its declined reasoning is contradicted by the runner. See F2.

F1
- Location: `benchmark/bench/p426_verify.py:2556-2585`
- Severity: major
- Evidence: confirmed
- Problem: D1’s ledger exactness is incomplete. Entries are filtered to `kind == "row"` before counting, while `chain_rows.load_slots` does not validate `p426_ledger`. A second entry for the same slot with `kind: "dnf"`—or malformed kind—is ignored, so a contradictory ledger is accepted.
- Concrete failure scenario: append a `dnf` ledger entry for an accepted accounting-fault row. `_a8_accounting` still sees exactly one row entry and accepts B8-A8.
- Proposed change: validate the ledger structurally and require exactly one entry per scored slot, with its kind matching the scored source; do not discard conflicting entries before uniqueness checks.

F2
- Location: `benchmark/bench/chain_core.py:2906-2917,3230-3247`; `benchmark/bench/p426_verify.py:2583-2592`
- Severity: major
- Evidence: confirmed
- Problem: D5’s “unreachable” disposition is false. The runner explicitly persists the ledger before `.continue`, and its done-stage abort route supports an already-ledgered slot. In that branch it adds the accounting sidecar/list entry but does not update the existing ledger or slot-attempt accounting marker. The verifier then refuses the runner-produced record as disagreement.
- Concrete failure scenario: the row is ledgered, but `.continue` is not successfully observed and the probe reports a typed done-stage harness fault. `p426_abort_route` takes the existing-ledger branch; B8-A8 sees `{slot_state:false, ledger:false, sidecar:true, chain_list:true}` and refuses.
- Proposed change: when routing a done-stage accounting fault for an existing row ledger, atomically mark the existing ledger and slot-attempt records `accounting_fault=True`, then add the sidecar/list record. Add an end-to-end producer-to-consumer test for this branch.
