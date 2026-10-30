P1
- Location: `benchmark/bench/p426_wave2.py:603-632`
- Severity: blocker
- Evidence: confirmed — source-traced.
- Problem: An existing pair dossier is trusted solely by its `verdict`; current receipts and computed pair problems are ignored.
- Scenario: A pre-created, self-hashed dossier says `PASS` while OFF/ON receipts differ. The sequencer publishes it and proceeds with a mismatched pair.
- Proposed change: Re-verify the existing dossier’s arms, receipt/harvest hashes, differences, and verdict against current inputs; refuse any mismatch.

P2
- Location: `benchmark/bench/p426_secrets.py:12-46`, `benchmark/bench/p426_receipt.py:73-82`
- Severity: blocker
- Evidence: confirmed — source-traced.
- Problem: The broad `KV_`/`TQ_` exemption fails to treat `KEY` or `TOKEN` in the suffix as credential words.
- Scenario: `KV_API_KEY=<opaque secret>` is recorded verbatim in the public receipt, omitted from exact-secret matching, and escapes format scanning.
- Proposed change: Exempt only committed exact configuration names, or include `TOKEN|KEY` in the hard-credential suffix check.

P3
- Location: `benchmark/bench/p426_hooks.py:264-285`, `benchmark/bench/p426_freeze.py:133-141`
- Severity: blocker
- Evidence: confirmed — source-traced.
- Problem: DNF requests are reconciled but never checked for ON/OFF engagement; final leg validation skips DNF item records entirely.
- Scenario: An ON request generates many tokens with no draft counters, then transport-aborts. The leg remains `VALID_WITH_DNF` despite unproven MTP engagement.
- Proposed change: Run `engagement_problems` for DNF reports, persist the check, and revalidate DNF item records during classification/freezing.

P4
- Location: `benchmark/bench/p426_reconcile.py:228-252`, `benchmark/bench/p426_reconcile.py:276-300`
- Severity: blocker
- Evidence: confirmed — source-traced.
- Problem: `*_inflight_failed` accepts a trailing failed request without evidence that the abort occurred in flight. Kill reconciliation always passes `inflight_possible=True`.
- Scenario: A boundary abort (`message_id=None`) plus a trailing `stream_closed_before_completion` line is accepted as an eligible DNF instead of a systemic contradiction.
- Proposed change: Require the structured in-flight marker for both failed and completed-unaccounted cases; derive it from kill evidence rather than hard-coding true.

P5
- Location: `benchmark/bench/p426_freeze.py:510-538`, `benchmark/bench/p426_wave2.py:636-650`
- Severity: blocker
- Evidence: confirmed — source-traced.
- Problem: The public `amend` command checks neither five-item realization, zero DNF, speed validity, nor the pair gate. The sequencer skips its pilot gate whenever an amendment already exists.
- Scenario: One-item, speed-invalid pilot roots produce an amendment; a subsequent Wave-2 run accepts it and starts full legs.
- Proposed change: Enforce the complete pilot gate inside amendment creation and reverify its supporting pilot dossier when loading an existing amendment.

P6
- Location: `benchmark/bench/p426_freeze.py:469-508`, `benchmark/bench/p426_freeze.py:183-237`
- Severity: blocker
- Evidence: confirmed — source-traced.
- Problem: v8 records the rehearsal-manifest hash but never binds that manifest or R1–R3 roots to the candidate arm commits/worktrees or expected leg names.
- Scenario: An old valid rehearsal and unrelated valid leg roots can authorize new arms that were never rehearsed.
- Proposed change: Verify manifest commits/worktrees against current arms and each leg’s name, frozen-record reference, arm, and injection argv.

P7
- Location: `benchmark/bench/p426_harvest.py:202-205`, `benchmark/bench/p426_harvest.py:620-659`, `benchmark/bench/p426_harvest.py:829-851`
- Severity: blocker
- Evidence: confirmed — source-traced.
- Problem: Harvest does not verify `leg.json` at all; missing hashes pass for receipts/items, and DNF sidecars are not self-hash-checked.
- Scenario: Changing `leg.json.speed_valid` to true while leaving its stale hash causes forged speed evidence to be published successfully.
- Proposed change: Require a present, valid self-hash for every immutable record and cross-check embedded DNF records against sidecars before staging.

P8
- Location: `benchmark/bench/chain_core.py:2608-2618`
- Severity: major
- Evidence: confirmed — source-traced.
- Problem: `p426_dnf` omits required `load`; its `attempt` is the probe invocation attempt, not the attempt number from `<leg>.a<n>`.
- Scenario: A DNF in leg attempt `a2` can claim attempt `1`, causing consumers to associate it with the wrong evidence.
- Proposed change: Add `load=load["idx"]` and parse the leg attempt from `self.out_root.name`.

P9
- Location: `benchmark/bench/p426_wave2.py:915-921`
- Severity: major
- Evidence: confirmed — source-traced.
- Problem: Failure to publish frozen records or `sequence.json` is logged but cannot change a successful exit code.
- Scenario: All legs finish and the command exits 0 although the public run contract is missing, permitting an incomplete result handoff.
- Proposed change: Convert publication failure to exit code 4 and only report `DONE` after successful run-file publication.

P10
- Location: `benchmark/bench/p426_harvest.py:442-493`
- Severity: major
- Evidence: confirmed — source-traced.
- Problem: A manifest’s run/evidence directory may have zero matches without producing a harvest error.
- Scenario: Deleting a run directory containing configuration and grading artifacts not referenced by rows still yields a successful harvest, silently losing files.
- Proposed change: Require each manifest run ID to resolve to its expected run/evidence roots and refuse missing or ambiguous roots.
