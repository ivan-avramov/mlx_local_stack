You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Context. The tg1 chain runner (benchmark/chains/c147/run_tg1_chain.py, benchmark/bench/chain_ops.py; spec
docs/specs/c147-tg1-chain-clearance.md) runs ~20 h agentic chains whose Go legs grade in docker. A rehearsal's first
Go leg aborted because the docker daemon was down after a reboot (docs/box-notes.md P291). The change under review is
commit 518896ac (`git show 518896ac`): `ChainOps.docker_ok()` and two gate calls in the runner.

A live chain is running on this box from another checkout. Run ONLY:
`cd benchmark && env -u STACK_WORKDIR <main-checkout>/.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_p290_docker_gate.py bench/tests/test_chain_ops.py bench/tests/test_c147_chain_runner.py bench/tests/test_p279_smoke.py`
(<main-checkout> = the main entry of `git worktree list`). Do not run the full suite and do not call docker.

Lens: (1) can the gate pass while Go grading would still fail for docker reasons (wrong context/socket, PATH
differences between the runner and the probe's grader subprocess, image missing), and is any of that in scope;
(2) can it fail spuriously and abort a healthy 20 h chain (slow `docker info` under load, transient errors) — is
30 s and no retry right, given the chain's fail-closed design; (3) placement: before the router at start, before each
Go leg launch; any path that launches a Go probe without the gate (restarts, reload control, pilot steps);
(4) is the existing behaviour otherwise unchanged; (5) do the tests bite and are they non-vacuous.

Output numbered findings D1, D2, ... (severity blocker / should-fix / nit, file:line, concrete change), then a
one-line verdict: "cleared", "cleared after fixes" (list the ids), or "not cleared".
