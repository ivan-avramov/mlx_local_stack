# M76 B4b-2 — implementer fix round 3 report (candidate 3 → candidate 4, working tree)

The working tree was edited; nothing was staged, committed, reset or pushed. No changes to `chain_core.py`, the runner or chain
modules, the frozen tests or the specification.

## Changes

Files touched: `benchmark/bench/p426_verify.py` and `benchmark/bench/tests/test_m76_b4b2_impl_r1fix.py`. New file:
`benchmark/bench/tests/test_m76_b4b2_impl_r3fix.py`.

### E1 — exactly one ledger entry per slot, with a matching kind (`p426_verify._a8_ledger`, new)
- Every `p426_ledger` entry is checked before any filtering. It must be an object with a string `slot` and a `kind` of `row` or
  `dnf`, and any `rerun_index` it carries must be valid. Otherwise the record refuses. This covers entries for unscored slots.
- Each scored slot of the attempt has exactly one entry, counted over ALL entries. That covers rows, harness DNFs and transport
  DNFs (candidate 3 checked rows only).
- The entry's kind matches the slot's scored source: a row needs `row`; a transport or harness DNF needs `dnf`.
- The rerun index: a `row` entry's index (0 when absent) equals the accepted attempt's index. A `dnf` entry's index is checked only
  when the entry carries one. The runner writes DNF ledger entries without a `rerun_index`, even for a harness DNF at rerun 1
  (`chain_core.py:2705`, `:2853`). Keying DNF entries by (slot, 0) would therefore refuse real runner records.
- Counting per slot is stricter than "one per (slot, rerun index)" and implies it. It matches the runner's own invariant:
  `check_p426_ledger` requires the ledger to equal the plan, one entry per slot. Faulted attempts get no ledger entry.

### E2 — the chain's accounting record is the recorded fact (`_a8_accounting`)
- When chain.json carries `p426_accounting_faults` (the runner always writes it in P426 mode, `chain_core.py:1151`):
  - a row is an accounting fault iff its list entry AND its sidecar exist;
  - a list entry without its sidecar, or a sidecar without its list entry, refuses ("accounting record is incomplete");
  - markers are checked only where the key is present: the raw slot-attempt record, the ledger entry and the row. A present
    marker must equal the record: True for an accounting fault, not True otherwise. So a True marker without the record refuses,
    and so does an explicit `accounting_fault: false` beside the record;
  - the sidecar still goes through `p426_hooks.accounting_problems`, and the orphan checks are unchanged.
- When chain.json does not carry the list, candidate 3's exact-agreement rule applies unchanged (see Q1).
- `_a8_accounting` now runs before `_a8_load_items`. It writes the recorded fact into `slots[iid]["accounting_fault"]`, so the
  missing-item-record exemption in `_a8_load_items` follows the chain's record and not the unmarked slot attempt. The real
  abort-route record passes `item_record=None` to `p426_write_accounting`.

### E3 — mechanism and fix
- **Mechanism:** this is not test interference, and the verifier had no bug here. In this copy,
  `test_b2_a_rows_file_changed_after_validation_refuses` fails on its own: `DID NOT RAISE`, both as the whole r1fix file and as a
  single node id. The test changes the rows through `World.edit_row` and assumes the invocation record's sha256 is left stale.
  But the frozen v4 support's `edit_row` re-hashes that sha (`test_m76_b4b2_fe_support.py:412–433`, `_rehash_invocation`; the
  frozen `test_m76_b4b2_fe_r2.py` notes "the v3 `World.edit_row` re-hashes"). The edited record is therefore consistent and
  correctly accepted. Most likely the test passed alone only against an earlier support version whose `edit_row` did not re-hash
  (Q2). I could not reproduce "passes alone" in this tree.
- **Fix (test only):** the test now writes the changed bytes directly, without re-hashing, like the frozen
  `test_b2_a_rows_file_changed_behind_its_invocation_record_refuses`. The r3fix test
  `test_e3_the_frozen_support_edit_row_re_hashes_its_invocation_record` pins the mechanism.
- Two candidate-3 tests in r1fix (`test_b5_the_chains_accounting_list_must_agree`, both assertions) still refuse, but their
  message regex now also accepts "accounting record is incomplete", which is the new message for that case.

## Red tests (`test_m76_b4b2_impl_r3fix.py`, 17 tests)
I ran the file against the INDEX `p426_verify.py` (swapped in temporarily, restored, and checked with `cmp`):

- **15 failed on candidate 3:**
  - Behaviour reds (the core findings):
    - `test_e2_the_abort_routes_record_on_an_unmarked_ledgered_slot_is_an_accounting_fault`: candidate 3 REFUSED the runner's own
      branch shape (unmarked ledger entry, accepted attempt, no row marker, list entry, sidecar) with "records disagree".
    - E1 tests that `DID NOT RAISE`:
      - `…_second_entry_of_another_kind_for_a_row_slot_refuses`
      - `…_second_entry_for_a_dnf_slot_refuses`
      - `…_dnf_slot_ledgered_as_a_row_refuses`
      - `…_malformed_entry_of_an_unscored_slot_refuses`
  - Message-only reds: the other E2 negatives and E1 kind / malformed-kind cases. Candidate 3 already refused them, under
    "records disagree" or "0 p426_ledger row entries".
- **2 passed on candidate 3:** the controls `test_e1_control_a_harness_dnf_world_is_accepted` and the E3 mechanism test.
- **On the working tree:** all 17 pass.

## Test runs (`../fe_test.sh stack …`)

| run | result |
|---|---|
| r1fix + r2fix + r3fix | 76 passed (after the r1fix regex updates) |
| full B4b-2 set (`test_m76_b4b2_impl_*` + `test_m76_b4b2_fe_*`, 15 files), one invocation, run 1 | 361 passed, 1 skipped |
| same, run 2 | 361 passed, 1 skipped |
| same, reverse file order | 361 passed, 1 skipped |
| `test_m76_b4b1_*` (12 files) | 480 passed, 1 failed |
| `test_m76_b3_*` (25 files) | 589 passed, 3 failed |
| `test_p426_*` (13 files) | 207 passed |

- The skip is `test_m76_b4b2_impl_golden.py:127`: "the tg2 pilot pair's evidence objects are not on origin/evidence in this clone".
- An earlier one-invocation B4b-2 run, before the second r1fix regex update, had 1 failure (`test_b5_the_chains_accounting_list_must_agree`,
  message only), and it was fixed.
- **Failures outside the B4b-2 set are environmental:**
  - The 4 tests: `test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical` and three in `test_m76_b3_impl_golden_mtp.py`.
  - The cause, in all 4: `REFUSED: frozen stack_head_on f2b61127c55f … does not resolve: git rev-parse failed`. That commit is not
    in this copy's object store (`git cat-file` fails).
  - The same tests fail identically against the INDEX `p426_verify.py`.

## Questions / judgement calls for the designer
- **Q1:** Should a chain with no `p426_accounting_faults` key refuse? I kept candidate 3's rule for that case (slot state, ledger
  and sidecar agree exactly) because the frozen world never writes the key, and frozen `test_accounting_fault_row_is_accepted_and_listed`
  requires that world to be accepted with an accounting fault. The runner always writes the key, so a P426 chain without it is
  not a real runner shape. Refusing it would be stricter but would break that frozen test.
- **Q2:** The brief says the E3 test passed alone. In this tree it fails alone. Whatever environment showed it passing probably
  had a pre-v3 support module.
- **Q3:** E1 does not refuse ledger entries for slots the attempt does not score, such as slots of another session or slots whose
  invocation is still `running`. A PAUSED leg can legitimately hold a ledger entry for a slot decided at the barrier but not yet
  counted. Only their shape is checked.
