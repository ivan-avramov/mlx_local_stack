Cold CODE review — the P369 phase-2 GPU worker-conformance harness (fork `mlx-vlm`, branch `p369-mtp`).

Workspace: the `mlx-vlm` fork checkout at the base `24551869`; the branch commits are in this repository's object store —
read any file with `git show <HEAD>:<path>` (read-only; modify nothing). The production code under test is pinned at
`4e6d0e03` (code review cleared, round 8); the harness is `4e6d0e03..<HEAD>` and touches ONLY `dev/p369_phase2/` and
`mlx_vlm/tests/test_p369_phase2_*.py` (production diff empty — verify). The approved plan (v7, stack
`docs/specs/p369-phase2-run-plan.md`, Cursor plan rounds 1–7) is inline after the diff.

What the harness must do (summary; the plan is authoritative): E1c — per pick, on real weights, the MTP-ON request's
emitted-position target distributions after the production sampling transforms, the complete valid cache state at every
commit and a probe's logits must be bit-identical to a forced plain replay on the SAME loaded instance (drafter detached in
process), with a within-instance control (C1, a second replay) and a cross-load / configuration comparison (C2, a separate
OFF process, report-only); runtime kernel telemetry proves which verifier kernels ran; straddle prompts are sized exactly
and the straddle is proven from observed key lengths; E2 greedy ON vs OFF identity; E7 the pre-fix M3 / M4 conditions,
the classes bound to measured pre-fix defects (isolated checkouts `88724023` / `0b43dae4`).

Review adversarially, file by file, for:
1. Fidelity: does any observer change production behaviour (patch / restore correctness incl. on exceptions; side effects
   of hashing, probing, recording; thread interaction between the harness thread and the server's GPU thread; leaked
   patches between tests)? Is the observation point (`_PositionedTargetSampler.sample_target`) complete for E1c — can any
   emitted position be sampled elsewhere (greedy paths, the forced-token branch, batched paths) so a row is missing or
   misattributed? Is forcing in the OFF replay exactly "the ON tokens, nothing else changed"?
2. Exactness of the checks: `compare.py` (canonical transform = production; bit comparison; row selection), `observe.py`
   (`state_hash` completeness — every valid component of KVCache / PreallocKVCache / QuantizedKVCache / TurboQuantKVCache /
   ArraysCache incl. metadata, no tails, no side effects; probe neutrality; snapshot alignment ON vs OFF offsets),
   `telemetry.py` (every consuming alias and nested implementation; exactly-once classification; the verdict rules),
   `worker.py` (`smoke_positives` — do they prove what they claim on the live cache types; `c1_acceptance`;
   `release_trajectory`; `wait_ack` / `wait_idle`; `DetachedGuard`; dry-run sizing via `DryRun`), `classes.py` /
   `oracle*.py` (predicates vs the pre-fix code).
3. Worker boot and served state: `boot()` (the fork's `cli.main` with `uvicorn.run` intercepted, `TestClient` lifespan) —
   anything the real worker does that this skips; `assert_served`; `check_sources`; the sanitized env (orchestrator
   `worker_env`); the argv from mlx-serve's `_build_command`.
4. Orchestrator: overlay exactness, preflight (processes, ports via lsof, disk, power, production diff), lock, watchdogs /
   timeouts, artifact paths, the E1c seed retries, the precedence (`pick_outcome`), the smoke gate, the summary; crash /
   partial-result behaviour; anything that could let a run PASS without establishing the claim, or FAIL / ABORT for a
   harness reason that gets reported as an MTP finding.
5. Tests: do the red-then-green commits prove each behaviour; any vacuous assertion; determinism (seeds, order, GPU vs CPU
   skips); privacy (no home paths / user names in committed files).

Findings ids H1 onward, each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line, the problem, a concrete failure scenario,
the fix. End with exactly one line: `VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.

The harness diff (`git diff 4e6d0e03..<HEAD>`):

```diff
