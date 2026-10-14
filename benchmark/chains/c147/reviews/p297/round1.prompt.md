You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Context. The tg1 probe's process guard (benchmark/bench/proc_guard.py, cleanup()) marks any same-uid process whose start
order cannot be read as uncertain (C151 R10: "could be ours, never a clean clearance") and aborts the leg; the chain
runner (benchmark/chains/c147/run_tg1_chain.py, check_restart_eligible) then refuses its one automatic block restart.
On 2026-10-13 the live M63 chain died this way: a Spotlight mdworker (pid 87652) vanished between listing and the
start-order read (fixture benchmark/bench/tests/fixtures/p297_real_uncertain_vanished_manifest.json). The probe must
stay byte-identical (its files are hashed into probe_code_sha256, which pairs rows across chains), so the fix is
runner-side only. Change under review: HEAD (`git show HEAD`).

No chain is running. You may run:
`cd benchmark && env -u STACK_WORKDIR <main-checkout>/.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_p297_uncertain_gone.py bench/tests/test_c147_chain_runner.py bench/tests/test_chain_ops.py`
(<main-checkout> = the main entry of `git worktree list`).

Lens: (1) Safety: can the new rule ever authorise a restart while a process of ours could still be alive or able to
touch the next attempt (pid reuse, zombies, a process that exits and is replaced by a child, a process outside the
listed uncertain set, the probe's error string not reflecting all failures, an uncertain record without reasons)?
Read proc_guard.cleanup fully and enumerate every path that sets uncertain=True; confirm each non-pid path still
refuses. (2) Is the restart itself safe after such an abort (block archival, fresh instance, leftovers listing)?
(3) Is anything in the probe identity touched? (4) Tests: do they bite on the parent commit; is the fake faithful to the
real guard's record and message.

Output numbered findings U1, U2, ... (severity blocker / should-fix / nit, file:line, concrete change), then a one-line
verdict: "cleared", "cleared after fixes" (list the ids), or "not cleared".
