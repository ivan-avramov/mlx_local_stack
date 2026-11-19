Verify, round 2 of 3. Read-only. Your round-1 findings on S26-P15b (P1 blocker: an unreadable / unsealed earlier leg.json counted as
"not clean"; P2 blocker: only attempts named by surviving superseded pair records were checked; P3 major: multi-hop reruns checked only
the final hop's reason; P4 major: a superseded record's name used as a path unvalidated). The redesign (fix2.diff): `_supersede_reasons`
is anchored on each arm's CHOSEN attempt `<leg>.aN`: every earlier attempt `<leg>.a1 … a(N-1)` must have a self-hash-verified leg.json
that is not clean, and every hop k -> k+1 needs a non-empty `reruns` reason; names are built from the chosen (member-validated) name.
Tests: test_v2.py (incl. tampered seal, removed old pair record, a multi-hop rerun missing its middle reason). The real data
(benchmark/results/m76/wave2/) still passes: x-pilot.a1 speed-invalid, rerun reason recorded.
For each round-1 finding state resolved or not, and why. Then anything else this breaks (both levers; a legitimate single rerun; a
rerun of an attempt that was INVALID). Numbered findings with severity, file:line, scenario; "no findings" if none. Do not modify files.
