P1 — Q35: CLOSED. Explicit state clearing, session removal, recorder-reference release, and weakref collection verification establish retirement before the next trajectory.

P2 — Q38: CLOSED. The GPU-thread acknowledgement occurs only after `_process_cached_request` completes its stream close, heartbeat shutdown, and sentinel enqueue. Waiting again before restoration closes both transition races.

P3 — New Q41+ problems: none.

VERDICT: AGREE
