**D1–D4 are resolved in candidate 3, and D5's declined reasoning holds.** I found no new hazard in fix 2. I traced the code and did not run the tests. The implementer's report gives 21/21 on the new r2fix tests and 153 passed, 1 skipped on the impl files.

**Per finding**

- **D1: resolved.** `_a8_accounting` (`p426_verify.py:2556-2592`) now does the following:
  - **Ledger:** it requires exactly one `kind=="row"` ledger entry per accepted slot at `(slot, s["index"])`, and that entry's marker joins the agreement check in place of `any(...)`. This fits the runner. `check_p426_ledger` (`chain_core.py:1488-1497`) forces one ledger entry per planned slot, and `chain_core.py:3231-3236` and `:2914-2915` omit `rerun_index` only at rerun 0, which `_a8_rerun_index(e.get("rerun_index", 0))` accepts.
  - **Chain list:** it must be a list of objects, each with a str `slot`, an explicit `rerun_index`, and `sidecar == "items/" + ph.record_name(...)`. The runner writes exactly this at `chain_core.py:2916-2917` and `:3209-3211`, and `ph.record_name` is identical to `p426_record_name`. Duplicates refuse. The orphan check at `:2608` can no longer hit a non-str slot.
  - **Real records:** a real runner record is not refused by any of these checks. An absent `p426_accounting_faults` key still passes, as the pre-list pilot chains need.
- **D2: resolved.** `a8_utc_seconds` (`:2940-2954`) returns None for any pre-epoch or non-finite result and for `OverflowError`. The only other caller, `p426_signals.py:1935`, handles None, and the exact-epoch value 0 is still accepted.
- **D3: resolved.** `want_model = ENTRY` (the `p426_verify.py:639` constant, equal to `p426_ids.ENTRY`). A schedule whose first pick is not `ENTRY` is a REASON, and manifest and row models are compared against `ENTRY`. It is a REASON and not a refusal, which matches the other rule-3.6 bindings in that validator. The old `want_model is None` branch is gone because `ENTRY` is never None. The new test fails on candidate 2, where all three records agreed on `another-model`.
- **D4: resolved.** `_a8_rerun_index` (`:2540-2544`) refuses a non-int, a bool or a negative value. It is applied to both ledger and list entries, so the ledger path no longer reaches `int(None or 0)` or `int("x")` tracebacks.
- **D5 (declined): the reasoning holds.**
  - A typed abort at stage `"done"` comes from the worker before the chain's barrier answer, and `chain_core.py:3229-3236` writes the ledger entry only at that answer.
  - Hook failures at `done` become accounting dispositions inside the barrier handler (`:3195-3211`), where the ledger entry and the list entry are written together.
  - So a slot cannot have an unmarked ledger entry when a list entry is later added for it. The `if not any(e["slot"] == failing …)` guard at `chain_core.py:2910` looks defensive, for example against resume.

**Hazard check**

- **Real records refused:** none found. The strictness added in D1 is limited to checks the runner already satisfies.
- **Contradictory record accepted:** none found. The accounting agreement still has to hold across slot state, ledger, sidecar, row marker and chain list.
- **Verdict path and byte-identity:** the diff touches only the verifier's record and identity checks plus tests. No A8 verdict is computed outside `axis_verdict`, and the diff does not touch `B8.json` or the no-A8 sheet and panel paths.
- **Weight:** nothing is heavier than its intent needs.

**Minor, no severity: coverage not shown in this clone.** `test_m76_b4b2_impl_golden.py` skipped because the tg2 pilot pair's evidence is not on `origin/evidence` here. The four `f2b61127…` goldens also failed in this clone before reaching changed code, because that commit does not resolve here. The D1 ledger strictness is therefore verified here only on synthetic worlds, and the implementer's report says the real pilot has 4 rows and 4 `kind:"row"` ledger entries per arm. ledger D6 already assigns this to B11 (the designer's real-record acceptance before the panel freeze) and to the stack gate, and that step must still run.

**Process note.** The implementer edited two tests in `test_m76_b4b2_impl_r1fix.py` to add the `sidecar` field, as the runner writes it. They were implementer-owned tests from candidate 2, and no frozen test changed, so I found no problem with it. Their question Q1 on scope is for the operator.