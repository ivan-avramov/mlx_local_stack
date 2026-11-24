P1  
Location: `benchmark/bench/p426_wave2.py::_recorded_ack`  
Severity: major  
Evidence: confirmed  
Status: not resolved.  
Problem: `_recorded_ack` accepts a matching acknowledgement from any re-check gate, rather than the gate being resumed.  
Concrete failure scenario: `rechecks.s2` contains the supplied SHA and acknowledgement while `rechecks.s1` remains unacknowledged. The legacy bare command passes argument validation, violating the requirement that actor and ruling be required before proceeding unless that gate already records the acknowledgement.  
Proposed change: Check only `rechecks["s1"]` (or pass the intended gate explicitly) and add a negative cross-gate test.

P2  
Location: `benchmark/bench/p426_panel.py::KV_FROZEN_RUBRICS`, `_kv_rubric_ok`, and `kv_check_frozen`  
Severity: major  
Evidence: confirmed  
Status: resolved.  
Problem: The exception is now conditioned on the old rubric pair and the frozen A3 `FROZEN.json` SHA.  
Concrete failure scenario: A modified or newly assembled A3 `FROZEN.json` carrying the old rubric pair receives a different SHA and is rejected.  
Proposed change: None.

P3  
Location: `benchmark/bench/p426_wave2.py::recheck_ack_actor`  
Severity: minor  
Evidence: confirmed  
Status: resolved.  
Problem: Rulings containing control characters or Unicode line/paragraph separators are now rejected before recording or logging.  
Concrete failure scenario: A ruling containing newline, carriage return, escape, NUL, tab, bidi control, or a Unicode line separator raises `Refusal` without changing `sequence.json`.  
Proposed change: None.
