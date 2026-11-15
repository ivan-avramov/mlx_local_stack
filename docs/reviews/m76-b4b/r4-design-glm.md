Based on my thorough review of the v4 spec, the v3→v4 diff, the round-3 ledger, the tg1 path map, and the relevant source files (`tg2_grade.py`, `corpus.py`, `chain_core.py`, `chain_ops.py`, `p426_freeze.py`, `p426_wave2.py`, `p426_hooks.py`, `p426_harvest.py`, `m76_sim.py`, `run_config.py`, `inject_verify.py`, `tg2_materialize.py`), my assessment is:

**NOTHING OF SUBSTANCE**

The v4 spec correctly resolves all round-3 findings (G1–G15):
- **G1** (snapshot outside `grading-private`): correctly named — `tg2_grade._disjoint` (line 952) confirms the work tree must be disjoint from `private`, so the `grading-snap/` sibling is the right seam.
- **G2** (doubled path): fixed — prompt reads from `source_root(lang)/<slug>/.docs/` directly, not via `exercise_dir(source_root(lang),…)`.
- **G3** (`--evidence p426`): correctly named — `chain_core` line 1995 gates on `config_id == P426_CONFIG_ID`; extending to `config_id in P426_CONFIG_IDS` is the stated behaviour.
- **G4** (rehearsals): `p426_hooks` line 277 (`_is_go`) and `chain_core.p426_inject_stall` line 1179 (hard-coded `python`) are correctly named as seams to parameterize by corpus.
- **G5** (re-check sealing): `ph.seal` (line 38) + `publish_run_files` (line 1140) is the correct path.
- **G8** (v8 positives comparison): correctly named.
- **G9** (grade call `snap.path`): `grade_item` signature (line 961) confirms `snap.path` as `work`.
- **G10/G11** (ChainConfig/sequencer wiring): correctly named.
- **G12** (Java `junit-*.xml` pattern): correctly named.
- **G13/G14/G15** (prompt/final-tree literals): correctly fixed.

The spec names every seam the implementer needs. The guarantees tg1's A7 has (provenance, reconciliation, engagement, pair gate, transport aborts, fail-closed refusals) are all preserved. tg1's plan/argv/schedules/harvest/B8/signals outputs are unchanged; only the closure-derived identity fields rotate (C178, explicitly asserted). No GPU-wasting design choice — the spec drops make-up legs (C345) and the screen leg (C346), and the s1 re-check gate prevents s2 from running on invalid s1.

On over-engineering: nothing in v4 is over-engineered for the goal. The `TG2_BOOKKEEPING_RE` regex with "near-match refuses" is fail-closed (a guarantee). The second re-check is part of the stated goal ("gated by the two nuisance re-checks"). The `pilot_deadline_s = REHEARSAL_DEADLINE_S` (6 h) is necessary because pilot walls aren't known yet. The `leg_deadline_s` 3660 s margin is one P223 maximum item — a reasonable safety bound.
