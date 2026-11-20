# S27 robustness design review — ledger (round 3 of 3, final verify)

Sol / GLM fresh, Sonnet resumed (`88a8a519`); all exit 0, read-only, checkout at `ac3609d3` (v1.2). Raw: `design-verify-{sol,glm,sonnet}-r3.md`.
r2 status: Sol P1, P2 resolved, P3 not (W1); GLM all resolved, NOTHING OF SUBSTANCE (one sharpness note, W6); Sonnet 7 resolved,
F3 / F4 mechanism gaps (W2, W4), F9 one literal (W5).

| W | finding (raised by) | disposition | change in v1.3 |
|---|---|---|---|
| W1 | abort routing lacks the lifecycle stage: an interim grader fault during generation and a `done` hook fault have no route (Sol P3) | ADOPTED | §5.8 stamps carry `stage` + `outcome_present`; routing by stage; §5.2 includes interim grader faults; §5.3 covers `done` hook faults (or PAUSED). |
| W2 | "regrade the retained snapshot" has nowhere to run: the probe aborts and its scratch is removed (Sonnet N1) | ADOPTED | §5.1 the regrade is an in-probe retry with the snapshot kept for the item; only the exhausted case stamps `grader_infra` with the generation evidence persisted. |
| W3 | the new DNF kinds' storage and the ledger / `_dnf_rows` / `leg_items_problems` reads (Sonnet N2) | ADOPTED | §5.7 `chain.p426_harness_dnf` + sidecars; every reader reads both lists. |
| W4 | the chain scan's kill authority; `foreign_new` flooded by old unreadable processes (Sonnet N3) | ADOPTED | §5.8 same kill-and-verify, else PAUSED; §3.4 list only not-provably-older unreadable processes, count the rest. |
| W5 | §12's "closure test's own list" does not exist in `local_gate.py` (Sonnet N4) | ADOPTED | §12 imports the existing four-file constant; equality test. |
| W6 | independent consumption of the per-arm harness-fault and cheat caps not restated (GLM note) | ADOPTED | §5.7 one clause. |

No open finding remains after round 3. Pending with the operator (raised after round 3 by a side-agent note): the deterministic
interrupt positive (option b) or the in-flight-PASS requirement (option a), to make sure the cancel path's "interrupts a generation"
link is proven on the new identity.
