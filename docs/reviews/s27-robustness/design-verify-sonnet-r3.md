**Round 3 verification of spec v1.2.** I read the diff, the r2 ledger, `arm_runner.py` (item and scratch lifetime, final grade, final tree), `local_gate.py`, and the §12 paths against the tree. I did not re-read `p426_hooks.py`, the harvest or `classify_leg` this round.

### Round-2 findings

| R2 finding | Status | Why |
|---|---|---|
| F1 late-record reference | Resolved | §4.1–4.2 take `ingested_offset_at_count` under the lock `terminate_client` already holds (`arm_runner.py:499`), and the ingester feeds under that same lock. The rule now covers the ingest-lag order, and §10 adds a test for it. |
| F2 accounting vs integrity | Resolved | §5.9 is a closed table, and unlisted checks default to integrity. |
| F3 candidate-caused grader faults | Policy resolved, mechanism not | §5.1 gives a closed infrastructure list, with timeout, `mem_kill`, OOM and tamper kept as outcomes. Where the regrade runs is a new finding (N1). |
| F4 abort route and hold | Mostly resolved | §5.8 gives typed stamps, a chain-side scan and a PAUSED state that needs no live probe. The scan's authority is a new minor (N3). |
| F5 `PASS_NO_INFLIGHT` consumers | Resolved | All four consumers are named and a freeze test is added. |
| F6 rerun-index bound | Resolved | §5.7 states that P426 has no cheat rerun, so the index is 0 or 1. |
| F7 denied start-order or liveness reads | Resolved | §3.2 now covers every denied read on an unclaimed process. A side effect is noted in N3. |
| F8 settle on a kept accounting-fault item | Resolved | §5.3 requires `in_flight == 0`, the same identity and the `:8000` owner before continuing, and a failed settle holds. |
| F9 §12 | Resolved except one literal (N4) | The paths exist. The helper reads the receipt document, any git error refuses, and the hazard and scope are stated. |

### N1 — "Regrade the retained final snapshot" has nowhere to run
- **Severity:** major. **Evidence:** confirmed.
- **Location:** spec §5.1, §5.8; `arm_runner.py:745-751`, `1202`, `1252`, `1292-1328`.
- **Problem:**
  - The final grade runs inside `run_item`, the last step before the result is built. A grader infrastructure fault raises `TransportAbort` there and the probe aborts. §5.8 does the same: it writes a `grader_infra` abort stamp "that ends the probe", then says "→ §5.1's regrade".
  - The snapshot is the context manager `corpus.snapshot(...)` and closes with the `with`.
  - The final tree is built only after `run_item` returns (`:1252`).
  - The work tree lives under `with p._item_scratch_dir(name)` and is removed when the abort leaves that block.
  - Nothing is retained for a chain-side regrade. The generation's results are also lost: the receipt fence, transcript export, reconciliation and gate report exist only inside the aborted `_run_item`.
- **Scenario:** The docker daemon drops at the final grade of a one-hour item. The probe aborts, the scratch tree is removed, and the chain sees `grader_infra` with nothing to regrade. It has to regenerate the item, which is the pre-outcome rerun F3 was meant to avoid. Alternatively the chain records a `grade_fault` DNF on the first fault.
- **Proposed change:** Make the regrade an in-probe retry.
  - On a closed-list infrastructure fault the final grade retries inside `_run_item` (same guard, same snapshot taken once), up to 2 times.
  - Only after the third fault does it write the `grade_fault` stamp, with the generation evidence (gate report, receipts, export) persisted so the `grade_fault` DNF record can carry the tokens.
  - Then §5.8's `grader_infra` cause is only the exhausted case, and no chain-side regrade is needed.
  - State that the snapshot is kept for the duration of the item.

### N2 — Storage and hook-stage coverage for the new DNF kinds
- **Severity:** minor. **Evidence:** confirmed for the existing structures.
- **Location:** spec §5.2, §5.7; `chain_core.py:1477-1479`, `2644-2645`; `chain_rows.py:311-346`.
- **Problem:**
  - Existing DNF handling is tied to `p426_dnf` (the `MAX_P426_DNF` cap and the ledger consistency check) and to `chain_rows._dnf_rows`, which requires `nonconv_kind == "transport_dnf"`.
  - §5.7 says the new DNFs are "separate from `MAX_P426_DNF`" and sit in the ledger as kind `dnf`, but not in which list or schema they are stored. If they go into `p426_dnf`, they consume the transport cap of 2. If they go into a new list, `check_p426_ledger`'s DNF equality check fails.
  - §5.2 covers a hook infrastructure error "at `ready`". A hook infrastructure error at `done` is not mentioned. Today it invalidates (`pump_barrier`, the `done` stage). It is an outcome-bearing stage, so invalidate or accounting is the likely intent.
- **Proposed change:** Name a second list (for example `p426_harness_dnf`) and its sidecar. Update the ledger equality check, `_dnf_rows` and `leg_items_problems` to read both. State the `done`-stage hook-error disposition explicitly.

### N3 — The chain-side second scan: authority, and flooding of `foreign_new` by unreadable old processes
- **Severity:** minor. **Evidence:** hypothesis.
- **Location:** spec §5.8, §3.2, §3.4.
- **Problem:**
  - §5.8 says the chain runs a "scan". It does not say whether the chain may SIGKILL OURS processes it finds and re-scan, or only reports them. If it only reports, every uncertain cleanup with a live survivor goes straight to PAUSED, which is safe but means the rerun path is almost never taken.
  - §3.2 now sends every unclaimed process with a denied read, whatever its age, to `foreign_new unreadable`. A box has dozens of same-uid system processes that deny reads. The cap of 64 plus a count keeps the list bounded, but real young foreign processes can be crowded out of the sample.
- **Proposed change:** State that the chain scan uses the same kill-and-verify rule for OURS, with the 60 s deadline, and pauses if anything cannot be verified. For `foreign_new unreadable`, record only processes not provably older than the guard when age is readable, and count the rest separately without listing them.

### N4 — §12 refers to a "closure test's own list" that is not in `local_gate.py`
- **Severity:** minor. **Evidence:** confirmed.
- **Location:** spec §12 (`PROTECTED_PUSH_PATHS` "beside the closure test's own list"); `arm_opencode.py:55`, `arm_specs.py:71`.
- **Problem:** `local_gate.py` has no such list. The four-file set already exists in `arm_opencode.py` and `arm_specs.py`. A second constant in `local_gate.py` can drift from them. All four paths named in §12 exist in the tree.
- **Proposed change:** Either import the constant from the existing definition, or add a test that `PROTECTED_PUSH_PATHS` equals it.
