# Test-writer delivery 3: P475 stage 1, fixed candidate

**Verdict: merge.** Everything I ran passes on `candidate-fix.diff`. I found no new candidate defect, only the observations at the end.

## Results on the fixed candidate

- **Frozen directory (`bench/tests/p475s1`):** `512 passed in 85.26s (0:01:25)`. I then added one more test (the P651 receipt test) and ran it alone: `1 passed`. I did not re-run the whole directory after that addition.
- **Implementer suites (`test_p475_impl_*.py`):** `242 passed in 19.81s`.
- **Touched suites (`test_run_capacity`, `test_capacity_*`, and the `bench_watch` / `chain_ops` / `p426` files):** `557 passed in 31.55s`.

## Fixture amendments (v1.2 facts)

- **N16:** now `kv_bits: 0` with the base's turboquant scheme line kept.
- **Instrument files:** the five instrument files are written byte-identical into the orchestrator checkout and every fake arm worktree.
- **`FakeOps.group_alive(pgid)`:** driver children that outlive the driver, TERM-ignoring and unkillable children, an extra router-group member, and an unreadable group state.
- **`FakeOps.scrub()`:** a hermetic harvest scrub with a fixed operator address. Before this, the candidate read `git config user.email` from this box, which made the harvest tests environment-dependent.
- **`worker_log_extra`:** a knob so the evidence-gate tests can plant a line in the worker log.
- **Two fake bugs of mine fixed on the way:**
  - A trailing comment had swallowed the rest of the `ARM_FACTS` line.
  - A failed spawn left a ghost process in the fake.

## The four amended tests

| Test | Old reading | New reading |
|---|---|---|
| `test_leg_precheck.py::test_n16_must_drop_the_scheme_key_not_keep_turboquant` | N16 removing the scheme line passes, keeping it refuses | Inverted, and split in two. The v1.2 N16 shape is VALID. N16 with the scheme line removed is NOT_STARTED. |
| `test_run_control.py::test_the_smoke_run_is_one_n16_leg_and_writes_no_matrix` | Smoke is one N16 leg | Now `test_the_smoke_run_is_n16_then_tq4_and_writes_no_matrix`: N16 then TQ4, no matrix. |
| `test_harvest.py::test_resume_replays_the_harvest_of_a_receipt_without_a_dossier` | The PII row injection applied to every arm, and no new stack may start | The injection is scoped to N16. The assertion is that no N16 stack starts again (the TQ4 smoke legitimately runs). |
| `test_harvest.py::test_a_stale_stage_directory_from_a_crash_is_replaced_not_merged` | Same injection | Same scoping fix. |

## New tests (`test_v12_fixes.py`, 60 collected, plus 18 in `test_rung_problems.py`)

"Red on round-1" was checked by running them against the round-1 candidate with a throwaway plugin that served N16 in round-1's own shape. That way each test fails for its own defect, not for the shared fixture difference. I deleted the plugin afterwards.

| Defect | Tests | On round-1 |
|---|---|---|
| Sol P1 (instrument files) | differs ×5, missing in the arm worktree ×5, missing in the orchestrator ×1; identical starts (invariant) | red |
| Sol P2 (N16 shape) | N16 as v1.2 defines it is VALID end to end | red |
| Sol P4 (peak, decode rate) | leg level: 5 bad values × 2 keys, absent ×2, OFF arm; unit level: `rung_problems` | red |
| Sol P5 / TW F3 (process groups) | child left after a clean exit is signalled; TERM → KILL; unkillable child is INVALID; unreadable group state is INVALID; router-group member surviving is INVALID | red. The empty-group-not-signalled and clean-router-group tests are invariants and pass on both. |
| Sol P6 (e-mail gate) | foreign address refused; operator address refused in a dossier file; operator address in an evidence log refused; refused harvest leaves `LAST_LEG_END` untouched | red. The reserved `example.org` address is an invariant and passes on both. |
| TW F2 (evidence-stage) | an existing directory refuses the leg; a replay never overwrites differing evidence | red |
| TW F1 (INVALID smoke is terminal) | TQ4 smoke INVALID stops the run and a resume stops again; the frozen `test_an_invalid_canonical_receipt_wins_over_a_valid_variant` | red |
| TW F6 (unresolved instability) | `--max-deciding 0` exits nonzero and the table says `UNRESOLVED` | red. A flag settled by the deciding block (exit 0, no label) is an invariant. |
| Sol P7 (block plan) | raising `--blocks` to 3 after a leg exists refuses (rc 2) | red. Lowering to 1 refuses on both candidates. |
| Sol P3 (dossier binding) | 7 receipt tampers with the manifest re-signed (model, base, arm, attempt, leg, gitlinks, arm commit); a second usable dossier for one slot; an arm re-committed mid-run | red |
| Sol P8 (one table) | complete → partial and partial → complete regeneration | red |
| Two-arm smoke | the amended smoke test; INVALID N16 smoke stops before TQ4 | the amended test is red. The N16-stops-before-TQ4 test is an invariant and passes on both. |
| P651 (receipt records the watcher's `--capacity-rows`) | receipt carries the watcher argv with the leg's own rows file | red by reading round-1's `run_leg`; not re-run on round-1 |

I fixed one of my own tests along the way. The re-committed-arm test lowered `--max-not-started` on resume, so round-1 refused it for the wrong reason.

**Checked by inspection only (not reproducible through the Ops interface):**
- **P651 mismatch branch:** the code builds the watcher argv itself, so a wrong rows path can't be injected through the fake. The implementer's monkeypatch tests cover it.
- **Sol P3 and P7:** I did not test the persisted identity and plan records directly, because their shapes aren't fixed by the contract. I tested the observable refusals.
- **Smoke receipt contents:** the worker-env and telemetry fields live in `fix-report.md` and the dispositions. The smoke legs themselves are tested.
- **Live-only:** GLM F1 (the worker-environment assumption) and GLM F3 (the two telemetry identities).

## Findings on the fixed candidate

No defects. Observations, none blocking:
- **O1:** A speed-invalid smoke leg is still re-attempted without a cap (`p475_kv.py:1832-1837`, status `speed_invalid` is neither `valid` nor `invalid`). The fix report says this is intentional.
- **O2:** If `--operator-email` is not given, the harvest falls back to `git config user.email` in the main checkout (`p475_kv.py:1073-1086`) and refuses an empty set. My tests are hermetic through `FakeOps.scrub()`. The live run must pass the flag or have the git setting.
- **O3:** `RealOps.group_alive` parses `ps` output and is covered only by the implementer's two fake-`ps` tests, not on a live box.
- **O4:** the NOT_STARTED cap is still one counter for the whole run, as dispositioned.

**Deviations from the contract:** none new. The driver timeout still adds 900 s, as noted in delivery 2.

**Not verified:** nothing in the fixed candidate is exercised on a live router, model or GPU.
