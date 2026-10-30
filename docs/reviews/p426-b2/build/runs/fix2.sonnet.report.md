All 12 items are fixed test-first, and the check suites pass: `benchmark/control/` no longer appears after the run, and the changes are uncommitted. Two things you should know first:

- **Frozen tests not run.** I did not run the `test_b2_frozen_*` files, as instructed. They stay unverified against my changes, and I read the ones around the changed seams only to keep signatures compatible.
- **Red coverage is partial.** I saw red before the fix on every item except P530, P67 and the first-written R3/P23 unit tests; where red came after the fix I say so below.

## Per item

Failing line first, then the change.

1. **Flat DNF refusal.** Red: `CHAIN ABORT: DNF refused: … runtime_epoch_id: None != '3dcf…'; row_arm: python/p1 None != 'oc'`.
   - `validate_partial` now applies `arm_row_problems` only when `self.per_arm`.
   - R3 (the limit counts the whole leg) and P23 (item record written as a path string) hold. My DNF limit unit test is green but never failed.
2. **P39.** Red: `HookInfrastructureError: worker /metrics unreadable`.
   - `after_attempt` and `settle` use a `_snapshot_or_none`.
   - An unreadable `/metrics` writes an invalid item record (`worker_after: None`) and invalidates.
3. **P40.** Red: stderr had 0 `REFUSED:` lines.
   - `Chain.run` also prints `REFUSED: …` to stderr for an `EntryRefused`.
   - The main-entry refusal still goes through `Refused` and the `__main__` print.
4. **P41.** Red: `DID NOT RAISE SystemExit`. `p426_settle_bound` now raises `Refused("REFUSED: --frozen-record …")` on a `RecordError`.
5. **P42.** Red: signatures and call shapes.
   - `ChainOps.worktree_state(path)` takes a required path, and the chain passes `p426_worktree()`.
   - `ChainOps.interpreter_inventory(pid, *, site_packages=None)` takes a pid only.
   - The probe's launch interpreter has no process yet, so I added a new seam `interpreter_inventory_at(exe)`. That is not in spec §16.2.
   - The seam is in `P426_SEAMS`, used by `p426_receipt`, and the fakes were updated. Say if you'd rather drop it.
6. **P43.** Red: `DID NOT RAISE ValueError`. `write_dossier` refuses `verdict == "PASS"` when `pair_problems` on its two receipts is non-empty. A failing dossier still records the failure.
7. **P44.** Red: `'kill_boundary' == 'completed'`.
   - In the real probe, `termination.killed` is written only inside `terminate_client`, after the count and reason markers. So a `killed` list without `requests_completed_at_kill`, `in_flight_at_kill`, `termination.reason` or `client_inactivity` is not a kill.
   - Such an item now reconciles as `completed`, strictly.
   - I changed one existing assertion in `test_b2_fix_chain.py` that said the opposite.
8. **s6 watcher** (`benchmark/m1/bench_watch.py`):
   - **Driver start time** comes from `proc_guard.start_time(psutil.Process)`, never `ps -o lstart`.
   - **P510:** `_overlap` returns `None` for any malformed element. Only `[start, end]` pairs of ordered finite numbers are accepted, so a dict is now malformed. The watcher stays alive and writes `battery_intervals: None`, which is speed-invalid.
   - **P47:** a failed liveness read gives `driver_alive: None` and is not an exit. A late first start-time read binds the driver. The verdict needs at least one tick with the driver alive and power observed.
   - **P48:** `parse_battery_log(..., since=)` returns `None` when no source line is at or before the window start.
   - **P50:** the default per-tick power read is `pmset -g ac` / `-g batt` only. `pmset -g log` is read once at exit by `pmset_battery_intervals`. An injected `power()` keeps its contract.
   - **P51:** s8b already removed `--planned` from the sequencer's watcher argv. In the watcher, planned slots now come from the leg's frozen `schedule.json`, checked against `chain.json`'s `schedule_sha256`. `--planned` only overrides.
   - **P52:** `t` is epoch seconds and the ISO `at` fallback is gone. The exit line no longer carries `speed_valid` / `speed_reason`.
9. **P530.** `FakeOps.env_base()` drops `MLX_SERVE_CONFIG`. I applied the fix before its test. I then saw the test go red with the line removed, and put it back.
10. **P532.** Red: the subprocess run of `test_work_queue.py` recreated `benchmark/control`. An autouse fixture in `test_work_queue.py` sets `STACK_WORKDIR` under `tmp_path`.
11. **P67.** The fake probe's stall row is now a real kill record (`termination.killed`, `requests_completed_at_kill`, `reason: stalled`). Its row-shape test and the `kill_boundary` item-record test both went red with the old stall row restored. Two other things I touched:
    - I fixed a stray fixture-only `x_unused` marker I used while checking.
    - The first run of the item-record test hung because the fake probe waits for a barrier answer. I couldn't kill it, so it timed out at 10 minutes; the test now cancels the probe on failure.
12. **s9 boundary.** Red on all five.
    - **Foreign addresses:** `Gate.check(..., dest)` quarantines a non-reserved address in a `main`-bound file, including `HARVEST.json` and published records. RFC 2606 names pass: `example.com`/`.net`/`.org` and their subdomains, `*.example`, `*.test`, `*.invalid`, `localhost`. Evidence-bound files keep the review-file rule.
    - **Empty operator-email set:** `Sequencer.run` and `BoxSeqOps.operator_emails` raise `Refusal`, giving `REFUSED:` and rc 2. `BoxSeqOps.operator_emails` refuses on an empty, unset or failing read.
    - **rc-4 stop:** `BoxSeqOps.harvest` returns the harvest's `REFUSED:`/`ERROR:` stderr line as `message`, and the sequencer logs it. `harvest_wave2` itself does not refuse an empty email set, so existing and frozen callers that pass none are unaffected.
    - **`watch.jsonl`:** a VALID or VALID_WITH_DNF leg without it fails the harvest.
    - **`finalized`:** `_log_slices` rejects `finalized: false` or null with "not finalized". "records problems" is now a separate message.

## Files changed

Source:
- `benchmark/bench/chain_core.py`: flat DNF validation, stderr `REFUSED:`, settle-bound refusal, seam calls, `P426_SEAMS`.
- `benchmark/bench/chain_ops.py`: `worktree_state(path)`, `interpreter_inventory(pid)`, `interpreter_inventory_at`.
- `benchmark/bench/p426_hooks.py`: tolerates unreadable `/metrics` at `done`.
- `benchmark/bench/p426_reconcile.py`: kill-marker rule.
- `benchmark/bench/p426_receipt.py`: probe interpreter seam, PASS-dossier consistency.
- `benchmark/bench/p426_harvest.py`: main-bound address gate, `watch.jsonl` rule, `log_bounds` reasons.
- `benchmark/bench/p426_wave2.py`: empty-email refusal, harvest message logged.
- `benchmark/m1/bench_watch.py`: all P47–P52 and P510 watcher changes.
- `benchmark/chains/c147/fake_probe.py`: real kill row for the stall.

Tests:
- `benchmark/bench/tests/test_b2_fix2.py` (new): one or more tests per item.
- `test_b2_fix_chain.py`: P44 assertion, `interpreter_inventory_at` fake, seam-set assertion.
- `test_b2_s5_receipt.py`: `ProcOps` fake gets `interpreter_inventory_at`.
- `test_b2_s6_watch.py`: exit-line speed fields, pair-form interval.
- `test_c147_chain_runner.py`: P530 and `interpreter_inventory_at` on `FakeOps`.
- `test_work_queue.py`: P532 fixture.

`docs/specs/p426-b2-tg1-wave2.md` was already modified before I started, and I did not touch it.

## Commands and results

All via `../bin/run_stack_tests.sh`, with no summary line printed because of the wrapper's `-q`; I report the exit code and the dot count.

- **Batch 1:** `bench/tests/test_b2_fix2.py` plus every `test_b2_s*.py`, then `test_b2_fix_chain.py`, `test_b2_fix_goldens.py`, `test_c147_chain_runner.py`, `test_p311_chain.py`, `test_p364_chain.py`, `test_local_gate.py`, `test_p426_wave1.py`, `test_p426_harvest.py`, `test_t3_wave1.py`, with `-q --tb=short -p no:cacheprovider`. Exit code 0, 1226 dots, 0 F/E/s/x.
- **Batch 2:** `test_p371_*.py` (via glob), `test_work_queue.py`, `test_status.py`, `test_m63_predictor.py`, `test_p279_smoke.py`, `test_c151_start_time.py`, `test_tune_provenance.py`, `test_samples_resume.py`, `test_p426_watcher.py`, `test_p426_session_ids.py`, `test_p426_leg.py`, `test_p426_bench_watch.py`, `test_p311_closure.py`, `test_p276_real_manifest.py`, `test_m64_chain_ops.py`, `test_m64_chain.py`, `test_m64_arm_closure.py`, `test_generate_run.py`, `test_evidence_backfill.py`, `test_conftest_fakes.py`, `test_chain_ops.py`, `test_bootstrap_lock.py`, `test_bench_watch.py`, `test_agentbench_watch.py`, with the same flags. Exit code 0, no F/E/s/x.

## Not satisfied

- Frozen tests not run, as noted above.
- I did not run the full suite, as instructed.
- I made no commit and no push. `.b2-slices.md` and the frozen tests were already untracked.
