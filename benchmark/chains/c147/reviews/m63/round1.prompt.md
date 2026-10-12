You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Context. The tg1 chain runner (benchmark/chains/c147/run_tg1_chain.py, benchmark/bench/chain_ops.py; spec
docs/specs/c147-tg1-chain-clearance.md) drives k=2 agentic chains predictor-OFF for model selection. M63 (spec
docs/specs/m63-mtp-on-tg1-arm.md; docs/open-questions.md C155; AGENTS.md rules on predictor states and the C71 rule
in docs/PLAN.md Phase 2) adds the predictor-ON arm: the same schedule with the shipped MTP registry, paired to the
OFF chain. The change under review is the HEAD commit of this branch (`git show HEAD`).

A live OFF chain is running on this box from another checkout. Run ONLY these mocked suites (fake probe, no router,
no model, no real opencode client):
`cd benchmark && env -u STACK_WORKDIR <repo-of-main>/.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_m63_predictor.py bench/tests/test_c147_chain_runner.py bench/tests/test_chain_ops.py bench/tests/test_p279_smoke.py`
where <repo-of-main> is the parent checkout of this worktree's `git worktree list` main entry. Do not run the full suite.

Lens:
1. OFF arm unchanged: is every OFF code path (overlay, tmpdir, A4 logs, tripwire, barrier, validation, chain.json
   apart from the added `predictor` key, out-root) byte-for-byte equivalent in behaviour to the parent commit?
2. ON arm correctness: the overlay is the registry verbatim; can the ON chain ever serve or record anything other than
   the shipped MTP state for both picks (stale overlay reuse, C147_OVERLAY override, a registry without the drafter,
   a worker without `--draft-kind mtp`, a manifest/registry sha mismatch, the M50/C35 checks in
   benchmark/bench/provenance.py)? Does the staleness check compare the right thing?
3. Isolation: can an ON run write into or read from the OFF chain's directories (out-root, tmp, A4 logs, STOP file,
   overlay), or vice versa? drive_m63.sh: argument handling, out-root selection, exit-code propagation.
4. Pairing: same items, seeds and order as the OFF chain? Anything that would make ON and OFF rows pool or fail to
   pair (identity fields, `probe_code_sha256` equal by design, `registry.sha256` differing by design)?
5. Tests: do they bite on the parent commit; are the fake-probe changes faithful to the real probe's C35 record;
   anything missing.

Output numbered findings M1, M2, ... (severity blocker / should-fix / nit, file:line, concrete change), then a
one-line verdict: "cleared", "cleared after fixes" (list the ids), or "not cleared".
