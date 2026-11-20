# Fix round, clarification (same session) — two items within findings X18 and X6

1. X18 is not complete: `benchmark/bench/tests/test_b2_frozen_s0_support.py` fails twice on the candidate and would fail the gate.
   (a) `test_the_frozen_runner_and_serving_pin_identities_of_the_base_commit`: `chains/c147/run_inject.py` changes by spec §4.5 (the
   tg1 interrupt run) and §9 (identity rotation) — update its pin in `b2_frozen_support.FROZEN_RUNNERS` to the candidate's bytes
   with a comment naming S27 §4.5 / §9; no other pin changes. (b) `test_the_abort_manifest_fixture_extends_the_real_probe_stamp`:
   the cleanup key set grows by §3.5 (schema 2: `schema`, `foreign_new`, `foreign_new_count`, `unreadable_count`) — make the fixture
   / expectation follow the probe's real stamp for schema 2 while schema-1 stamps still validate (§3.5). Run the file; list both
   edits with their clause.
2. X6 scope extended: `benchmark/bench/structured_grade.py` (tg1 Go: `parse_go`'s "Docker infrastructure failure") is now in scope.
   Raise the typed `GraderInfraError` there for the harness's own docker failure (never from tool / test output), so tg1 Go docker
   faults are regraded as tg2's are. Red test first; run the existing structured_grade / tg1 grading tests.

Report as before (facts only), for these two items. The brief's constraint block still applies.
