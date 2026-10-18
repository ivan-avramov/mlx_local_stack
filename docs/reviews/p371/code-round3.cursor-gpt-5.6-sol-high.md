EXIT 0
F2 — resolved.

F6 — partially resolved — pre-manifest and between-item cancellation still lose or misattribute A12 evidence (`benchmark/bench/arm_runner.py:1070-1071,1140-1143,1244-1258`).

F7 — resolved.

F10 — resolved.

F11 — resolved.

F12 — resolved.

F13 — resolved.

F14 — partially resolved — post-exit hydration works, but unobserved foreign run IDs and crash-resume are unsafe (`benchmark/bench/chain_core.py:1008-1028,1533-1559`).

F15 — partially resolved — live tg1 stamping and A14 pointers are correct, but `progress.abort_evidence` is not crash-recoverable (`benchmark/bench/chain_core.py:1499-1503,1562-1568`).

F16 — high — `benchmark/bench/chain_core.py:1533-1559` — with `att.run_id == null`, any nonempty manifest run ID is accepted, including a reused/foreign ID, allowing foreign cleanup and abort state to drive recovery. Fix: read once, validate full invocation binding, reject previously seen IDs, and rebuild/persist seen IDs across resume.

F17 — high — `benchmark/bench/chain_core.py:1008-1028,1499-1503` — crash after probe exit but before `attempt-ended` leaves a `running` invocation; resume quarantines/archives it without hydrating its final manifest, losing cleanup and abort evidence. Fix: idempotently hydrate running records before salvage/quarantine and deduplicate evidence by invocation.

F18 — medium — `benchmark/bench/arm_runner.py:1070-1071,1127-1134`; `benchmark/bench/chain_core.py:1549-1568` — cancellation before initial discovery completes exits before any manifest exists; hydration records “missing” but emits no explicit unavailable abort evidence. Fix: establish an abort-capable manifest before cancellable setup, or synthesize unavailable evidence from inventory.

F19 — medium — `benchmark/bench/arm_runner.py:1140-1143,1244-1258` — cancellation between items occurs before prior context is cleared, so the new unconditional stamp attributes the previous committed item; the chain reports `covered=row` for the wrong slot. Fix: clear/set item context before checking cancellation and represent boundary cancellation explicitly.

VERDICT: NOT CLEARED F16 F17 F18 F19

[exited with code 0]
