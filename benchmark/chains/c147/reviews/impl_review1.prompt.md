You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. The working tree holds
an UNCOMMITTED implementation of docs/specs/c147-tg1-chain-clearance.md (revision 3 plus §9 build findings). Read
the spec, then your two earlier design reviews at $STACK_WORKDIR/c147/codex_design_review1.md and
codex_design_review2.md (findings P1–P22), then the implementation: `git status --short` lists it — changed:
benchmark/bench/{tg1_runner,token_turn_gate,proc_guard,structured_grade}.py, benchmark/run_opencode_probe_v2.py,
scripts/session_pinning_gate.py; new: benchmark/bench/chain_ops.py, benchmark/chains/c147/*, benchmark/m62/
{inject_verify,tmp_escape_clean}.py, tests benchmark/bench/tests/test_c147_*.py, test_chain_ops.py, fixtures
benchmark/bench/tests/fixtures/opencode_2.0.20_*.json. Tests run with:
`cd <repo> && env -u STACK_WORKDIR OPENCODE_PROBE_BIN=$STACK_WORKDIR/opencode-2.0.20/bin/opencode .venv-bench/bin/python -m pytest -q -p no:cacheprovider <files>`
(you may run them; they start no router or model; a TMPDIR under $STACK_WORKDIR/c147/tmp is set for you).

Lens: for each of P1–P22 state whether the CODE now answers it (answered / partial / not answered) with file:line
evidence, not whether the spec text does. Then verify the §9 build findings against the code (B1 SIGTERM-first stop
and the two tolerated transport errors; B1b interrupted_charged; B2 alloc 512 MiB; B3 killed-command fixture) and
judge whether any of them weakens §3a of docs/specs/m62-token-turn-gate.md beyond what the spec states. Then hunt
for: any path that kills a process the probe/runner does not own; any way a chain leg can be declared complete
without the full validation; any way inject rows could pool with campaign rows; the campaign policy hash moving;
/tmp deletion of anything the model's write/edit tool did not create; PII/home paths in committed-to-be files;
load-bearing behaviour without a test. Output numbered findings Q1, Q2, ... (severity blocker / should-fix / nit,
file:line, concrete change), then a one-line verdict: "cleared", "cleared after fixes" (list the ids), or "not
cleared". Do not write files.
