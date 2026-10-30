P1
- Location: §2, §11.2; `benchmark/bench/arm_runner.py:1038–1056`; `benchmark/bench/arm_opencode.py:660–663`
- Severity: blocker
- Evidence: confirmed
- Problem: P426 retains tg1’s global `$STACK_WORKDIR/opencode_transcripts` evidence root, but harvest permits sources only inside the leg root or bounded server logs.
- Scenario: A successful item writes transcripts, events, stderr and final-tree evidence outside `$STACK_WORKDIR/p426/wave2/<leg>`. Transitive harvest must reject them.
- Proposed change: Add a P426-only evidence root inside each leg root and verify every row, abort, grade, web and final-tree reference resolves there.

P2
- Location: §6.5, §11, §12
- Severity: blocker
- Evidence: confirmed
- Problem: A pair dossier contains both `HARVEST.json` hashes and therefore is created after both leg harvests, but only leg-root harvests exist. B8/B6 require the dossier while also resolving files exclusively through harvest manifests.
- Scenario: Both legs harvest successfully; `pairs/s1.json` is then written outside both immutable inventories and remains uncitable.
- Proposed change: Define a pair-level harvest, manifest, destination, scrub gate and commit lifecycle.

P3
- Location: §4.3
- Severity: major
- Evidence: confirmed
- Problem: The unconditional equality says `C` equals `request_usage` in count and order, while the supported `completed_unaccounted` case requires one trailing completion absent from `request_usage`. It also refers to a DNF “row’s” session although a DNF has no row.
- Scenario: The server completes an in-flight request immediately before client disconnection. The permitted DNF table matches, but the preceding equality makes it systemic.
- Proposed change: State outcome-specific equations: for this case require `C[:-1] == request_usage`, `len(C) == len(request_usage)+1`, and bind sessions to the abort manifest’s session ID.

P4
- Location: §6.4–6.5
- Severity: major
- Evidence: confirmed
- Problem: Credential values are neither recorded nor hashed, yet the second chain receives only the first receipt path and must compare those values before item one. No in-memory transfer protocol is defined.
- Scenario: A credential rotates between paired legs. Persisted receipts still match, and the second chain cannot detect the change.
- Proposed change: Make the sequencer retain first-leg credential values and perform a one-shot in-memory comparison before authorizing the second chain.

P5
- Location: §1, §2, §6.5, §11.2, §13
- Severity: major
- Evidence: confirmed
- Problem: A restart between paired legs voids both legs and requires fresh roots, but roots and publication destinations use fixed leg names, existing roots are refused, and harvested destinations are immutable.
- Scenario: The sequencer crashes after OFF-s1 is harvested. Restart cannot reuse its root or destination, while skipping it violates the pair rule.
- Proposed change: Add immutable attempt IDs to roots and destinations, with a pair transaction selecting one complete pair and marking older attempts superseded.

P6
- Location: §11; `benchmark/bench/p426_harvest.py:100–126`
- Severity: major
- Evidence: confirmed
- Problem: No crash-atomic or resumable harvest protocol is specified; the existing harvester publishes files sequentially and writes its manifest last.
- Scenario: A crash after several files are published leaves no `HARVEST.json`; retry encounters immutable existing destinations and cannot complete.
- Proposed change: Require staged, journaled, idempotent publication, with verified artifacts promoted atomically and `HARVEST.json` finalized last.

P7
- Location: §9
- Severity: major — settled-constraint conflict with C227
- Evidence: confirmed
- Problem: A P426 chain checks the gate lock but not the sequencer lock. A standalone chain can therefore run during the sequencer’s idle interval without updating `LAST_LEG_END`.
- Scenario: A hand-launched chain completes midway through the 600-second gap. The sequencer sees no busy process and starts its next leg before ten quiet minutes have elapsed.
- Proposed change: Re-rule C227 to require sequencer-bound authorization for each chain, or make every P426 chain update a shared last-run-end record.
