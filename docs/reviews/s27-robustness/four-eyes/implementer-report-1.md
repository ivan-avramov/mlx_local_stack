I built the whole S27 bundle in the copy and nothing is committed. Two things are open. First, the interrupt positive (§4.5) can't run end to end: the probe entry scripts only accept the old three inject kinds on the command line, and those files are outside the directories the brief lets me change. Second, the broad run showed six failures outside the clone's known-broken test families; two of them pass in isolation and I couldn't explain why they fail in the big run.

## Files
**Code changed**
- `bench/proc_guard.py` — §3: the ownership tests a→d, `foreign_new` (capped at 64, plus counts), receipt schema 2, one kill-and-verify loop, `CleanupUncertain`; `_sweep_excluded` removed; `_resolve` no longer counts a path match alone as owning a process.
- `bench/chain_incident.py` — one cleanup validator for schema 1 and schema 2; `orphans_unattributed` taken out of `CLEANUP_LISTS`.
- `bench/token_turn_gate.py` — the END offset of each step, the `interrupt` kill outcome, the closed list of grader infrastructure faults, `GraderInfraAbort`.
- `bench/arm_runner.py` — the kill-time offsets, `row.cleanup_status`, `probe_session` in the manifest, hermetic HOME/XDG markers passed to the guard, the in-probe final-grade regrade (`final_grade`), the interim-fault abort, the C365 cancellable grade worker with a bounded join, typed abort stamps (cause, stage, outcome_present), the interrupt stop, a schema-2 `CLEAN_STATUS`.
- `bench/p426_reconcile.py` — `kill_boundary_late_record` in both shapes, the `order` / `signal_order` fields, the closed table (`fault_class`).
- `bench/p426_hooks.py` — item records keyed by rerun index, the accounting sidecar, the `accounting_fault` disposition, a check that reads `row.cleanup_status`.
- `bench/chain_hooks.py` — `harness_fault`, `accounting_fault` and `hold` added.
- `bench/chain_rows.py` — `harness_fault` disposition queues `(slot, 1)`; P426 rerun index bound ≤ 1; `p426_harness_dnf` read and scored strict 0; the accounting flag is exposed.
- `bench/chain_core.py` — ready faults rerun once, then a `harness_fault_dnf`; done faults become accounting faults; the typed abort route; the chain's second scan; harness DNF cap with a hold; hold and pause episodes with release and resume checks; the ledger check covers both DNF lists; the new counts.
- `bench/chain_ops.py` — `owned_scan`, the chain's second scan (needed by §5.8).
- `bench/p426_freeze.py` — `PASS_NO_INFLIGHT`, the interrupt rule, `proof_of`, `positives_proofs` in v8, `leg_items_problems` for rerun indexes, harness DNFs and accounting faults.
- `bench/p426_wave2.py` — PAUSED state, harness DNF cap, `held_s` deadline suspension, `--pause-file` passed to the chain, the interrupt run, `PASS_NO_INFLIGHT`, a PAUSED leg stops before any harvest.
- `bench/p426_harvest.py` — §7.1 symlinks (`portable_link`), PAUSED never harvested, references and barrier checks for reruns, harness DNFs and hold stops.
- `bench/corpus_tg2.py` — §7.2 javascript lock files omitted; the interrupt prompt adds no text.
- `bench/local_gate.py` — §12 push binding (`push_binding_problems`, `PROTECTED_PUSH_PATHS`).
- `m62/inject_verify.py` — `PASS_NO_INFLIGHT`, the `interrupt` kind, the suite now requires the interrupt PASS.
- `m1/bench_watch.py` — `BoxSampler`, `box_alerts`; ALERTs and holds make a leg speed-invalid.
- Modules outside the named list, each needed by §4.5 or §8.2:
  - `bench/run_config.py` (`INTERRUPT_KIND`, `ALL_INJECT_KINDS`)
  - `bench/tg1_runner.py` and `bench/tg2_runner.py` (templates allow `interrupt`)
  - `bench/corpus_tg1.py` (no interrupt prompt text)
  - `chains/c147/run_inject.py` (tg1 interrupt run on the stall item)
  - `chains/c147/run_tg1_chain.py` and `chains/c147/run_tg2_chain.py` (`--pause-file`)
- `chains/m64/fake_arm_probe.py` — schema-2 receipt; its `orphans` variant stays schema 1.

**Existing tests changed** (each pins a rule the spec changes):
- `test_c157_proc_guard.py`, `test_g1_round2_proc_guard.py`: their obligations now apply to processes the guard may claim (§3.2). A fixture makes the session id unreadable, and a few strangers are marked as another session.
- `test_proc_guard`, `test_c151_start_time`, `test_m62_v5a`, `test_c147_cancel`: §3.2 / §3.5.
- `test_p371_m64_incidents`, `test_p371_review_r1_f5` (through `CLEAN_STATUS`): schema 2.
- `p371_baseline/compare.py`: table additions for the S27 fields.
- `test_m76_b4b1_impl_golden_tg1`: named S27 differences allowed (`args.pause_file`, `row.cleanup_status`, `inject_allowed`, `scaffold_policy_sha256`).
- `test_b2_s3_core`, `test_b2_s4_reconcile`: §5.2 / §5.3.
- `p586_frozen/test_p586_invariants`: S27 optional record keys and the accounting disposition.
- `test_c147_inject_verify`, `test_c147_inject`, `test_c147_chain_runner`, `test_m76_b4b1_impl_wave2`, `test_m76_b4b1_fe_chain`, `s26_frozen/test_s26_positives`: §4.5 interrupt.
- `test_p541_push_level`: §12 `pushed_base`.

**Added**
- `bench/tests/test_s27_impl_{guard,reconcile,chain,runner,positives,harvest,gate,watch,scan}.py`
- `fixtures/s27_impl/sgf_parsing_d1.json` (numbers only, no paths)
- `docs/reviews/s27-robustness/change-ledger-impl.md`

## Commands and results
- Baseline, before any edits: 7 failures in `test_m62_v5a_identity` / `test_c147_cancel`, all `missing grader interpreter/runtime … .venv-bench/bin/python`. These are the clone's own.
- My 9 test files plus the tg1 golden: **138 passed**.
- Final run: `../fe_test.sh stack bench/tests -k "<the touched modules>" --continue-on-collection-errors` gave **315 FAILED**.
  - 309 are in the `test_b2_*`, `test_t3_*`, `s26_frozen/test_s26_sequencer` and `s26_frozen/test_s26_round2` families. The ones I inspected fail with `FileNotFoundError … src/mlx-vlm/dev/p369_phase2/pins.json` (or `registry_states.py` / `qualify.py`) — the `src/mlx-vlm` submodule isn't checked out in this clone. Note that this masks frozen B2 tests that pin "count mismatch → invalidate", which S27 now makes an accounting fault: `test_b2_frozen_s4_reconcile::test_fix_the_done_hook_invalidates_a_server_count_that_differs_from_the_client`. That one would need updating once it can run.
  - 4 are the clone's own:
    - `test_s26_positives::test_fix_an_exception_message_never_carries_the_absolute_home_path` — TMPDIR in the copy is under `$HOME`.
    - `test_m64_arm_closure` — needs a canonical origin.
    - `test_m76_b4b1_fe_golden_tg1::test_b8_regenerates_byte_identical` — `git rev-parse failed` on a frozen head.
    - `test_p426_plan::test_k3…` — `qualify.py` missing.
  - 2 are **not explained**: `test_p585_proc_guard_systemerror::test_the_scan_skips_a_process_it_cannot_construct_and_keeps_the_rest` and `test_proc_guard::test_real_rapid_fork_detach_chdir_is_attributed_or_diagnostic`. They fail in the broad run but pass when run alone: 33 passed for `test_p585` + `test_proc_guard` together. I couldn't tell whether this is cross-test interference or timing under load.
- Collection errors (clone's own): `test_t3_wave1.py` (`registry_states.py` missing), plus errors in some `test_b2_s8c` / `test_b2_s9` / `test_t3_frozen_names` tests.

## §10.1 coverage (all pass)
- **Guard (§3)** — `test_s27_impl_guard`:
  - foreign-session process → `foreign_new`
  - denied start-order / cwd / environ read → `foreign_new` with `unreadable: true`
  - path-only match → not killed
  - non-leader probe → ownership by ancestry only
  - owned survivor → killed, verified, certain
  - schema 1 and schema 2 validation
- **Reconciliation (§4.2, §5.9)** — `test_s27_impl_reconcile`:
  - the recorded sgf-parsing numbers → `kill_boundary_late_record` with `order: "unpublished"`
  - the trailing-failed variant
  - the ingest-lag order
  - a count mismatch → accounting
  - a worker-delta mismatch → integrity
- **Grading and abort (§5.1, §6)** — `test_s27_impl_runner`:
  - a grader transport fault → regraded and accepted; two faults then a pass on the one kept snapshot; three faults → `GraderInfraAbort` (the chain turns it into a `grade_fault` DNF)
  - a timeout, mem_kill, OOM or tamper → the outcome, never regraded
  - an interim fault → the generation stage
  - the C365 slow-grader case
- **Chain (§5, §8.2)** — `test_s27_impl_chain`:
  - ready fault → rerun once; twice → `harness_fault_dnf`, leg continues
  - a `done` hook fault → accounting fault, or PAUSED when the sidecar can't be written
  - the accounting fault's settle check
  - the abort route: scan certain → rerun, else PAUSED with no live probe
  - harness DNFs pass the ledger check beside a transport DNF
  - the 4th DNF holds
  - an integrity fault still invalidates
  - the hold round trip, including the outer deadline
- **Chain scan** — `test_s27_impl_scan`, using real processes.
- **Positives (§4.3, §4.5)** — `test_s27_impl_positives`: a stall with nothing in flight → `PASS_NO_INFLIGHT`, and it freezes in v8; a loop without the descendant kill → not observed; the interrupt rule.
- **Harvest (§7)** — `test_s27_impl_harvest`: the npx-cache links are excluded with portable targets; the nested lock is omitted. This is checked at inventory level; the scrub step inside `harvest_wave2` is not exercised end to end.
- **Push binding (§12)** — `test_s27_impl_gate`: all five red cases, plus the equality pin on `PROTECTED_PUSH_PATHS`.
- **Watcher (§8.1)** — `test_s27_impl_watch`.

## §4.6 list
It's in `docs/reviews/s27-robustness/change-ledger-impl.md`, rows L1–L11. Row L1 needs your call: making `kill_inflight_failed` order-tolerant (accept the stream's open-step evidence when the `/metrics` sample read 0) is built-and-reverted, because frozen B2 test `test_fix_a_kill_with_a_trailing_failed_line_but_no_in_flight_marker_is_off_table` pins that check.

## Not satisfied
- **Interrupt positive end to end.** `benchmark/run_tg1_probe.py`, `run_tg2_probe.py` and `run_oc_probe.py` hard-code `--tg*-inject` choices to stall, loop and alloc. Everything else supports `interrupt`. Can I add it there?
- **`fake_probe.py` (c147) unchanged.** Its four-key receipt only feeds the schema-1 path.
- **Sensitivity analysis and accounting-fault aggregate exclusion** (§5.3 / §5.6). Only the counts and flags are recorded; the analysis itself is left to the consumers (§11).
- **"`run_m62_live.py`'s results"** — the frozen file has no verdict consumer. The real tg1 consumer is `run_inject.py`, which I updated.

## Choices where the spec left room
- Rerun records use the suffix `.r1.`; attempt 0 keeps today's file names.
- There is one interrupt run per tg2 record, on the first tg2 language's pilot item, run first. For tg1 it runs on the stall item.
- `kill_boundary` records `order` and `signal_order` as separate fields.
- Env markers only count when their value is under the run directory.
- An unreadable session id counts as a claim and stays uncertain (§3.2 "as today").
- A failed settle after an accounting fault, a done sidecar that can't be written, the 4th harness DNF, and an unproven second scan all PAUSE. A pause writes `<out_root>/PAUSED`; the designer releases it by deleting that file, and STOP leaves the leg PAUSED.
- Harness-fault episodes go in `chain.p426_harness_faults` rather than the ledger, so ledger counts stay one per slot.
- Pause episodes are recorded with epoch `start_t` / `end_t`.
- The chain's deadline suspension is implicit: nothing is launched or supervised while held.
- The watcher's box sampler runs only from `main`; the exec probe writes to `$TMPDIR`.
- `classify_leg` keeps its return shape; the tiers are in a separate `speed_tiers`.
- The grader infrastructure list is the marker tuple in `token_turn_gate.GRADER_INFRA_MARKERS`.