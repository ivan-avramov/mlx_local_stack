P1 — Q35: NOT CLOSED (§2.5). `MLX_VLM_CACHE_SESSION_MAX=1` only removes the old entry from `_session_caches`; eviction does not clear it or release references retained by the harness recorder. Explicitly drop recorder/session references and verify retirement before starting the next trajectory.

P2 — Q36: CLOSED (§2.5, §§1/6). E1c is correctly limited to same-loaded-instance plain decoding; C2 is non-causal and non-decisional.

P3 — Q37: CLOSED (§2.5/§3). C1 coverage, invalidity conditions, and precedence are now explicit and consistent.

P4 — Q38: NOT CLOSED (§2.5). “Request queue empty and `in_flight == 0`” does not prove GPU-worker idleness. The endpoint stops at the final token, while `_process_cached_request` can still be closing the stream, stopping its heartbeat, and enqueueing the sentinel. Require a harness-observed exit/completion acknowledgement after `_process_cached_request` returns before detaching or restoring fields.

P5 — Q39: CLOSED (§§2.1–2.2/§3). Assertions and terminology now distinguish process arms from ON/OFF trajectories.

P6 — Q40: CLOSED (§§2.5/4). Four trajectories, approximately 430K prefill tokens and 3.2K decode/replay positions correctly account for the two added same-instance replays; smoke recalibration bounds the remaining uncertainty.

P7 — New Q41+ problems: none. The two objections above are incomplete closures of Q35 and Q38, not newly introduced categories.

VERDICT: DISAGREE Q35 Q38
