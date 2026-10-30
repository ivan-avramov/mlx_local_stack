The s6 watcher is close to mergeable, but I recommend **fix then merge**, mainly because three of its paths can report a leg speed-valid when the window was never proven off-battery. My view of the whole set on the s6 copy is mostly blocked: 139 of 222 failures come from a missing pins file in that copy, not from the candidate.

## 1. Fixture amendment (P510)

`test_b2_frozen_s6_watch.py::test_new_the_watcher_takes_its_power_reading_only_from_the_injected_source` now passes `on_battery_intervals` as `[[start, end]]` in epoch seconds on the watcher's clock, tagged post-reveal (P510).

I also found and fixed a robustness defect of mine in s5: the pins were read when the module was imported, so a missing pins file stopped the whole run at collection. They are now read at run time. Tests touched:
- `test_new_the_pair_dossier_is_self_hashed_and_keyed_by_arm` (`DIFFERENCES` became `differences()`)
- `test_fix_any_other_difference_between_the_arms_refuses[snapshot-target]` (its value is now built inside the test)

| Where | Command / result |
|---|---|
| Baseline, support checks | `54 passed in 18.87s` |
| Baseline, s6 file | 3 failed, 1 passed (the baseline has no s6 mode; the `[INV]` passes) |
| Baseline, s5 file | collects, `56 failed in 1.18s` (no `p426_receipt` module) |
| s6 copy, s6 file | 4 of 4 passed, the amended test included |

## 2. Whole set on the s6 copy (synced with `../bin/sync_to_s6.sh`, 23 files)

```
../bin/run_candidate_s6_tests.sh <the 20 set files> --tb=line -rfE
222 failed, 221 passed in 87.73s
```

| Failures | Class | Evidence |
|---|---|---|
| **139** across s0, add_support_check, s4 hooks, s5, s7, s8 (R1), add_pair, add_argv, add_census, add_ledger and the fix cases (incl. P38 drift) | **Environment, not classifiable** | `FileNotFoundError … eval-s6/mlx_local_stack/src/mlx-vlm/dev/p369_phase2/pins.json`. The world copies the fork's real pins (§3). The s1–s5 fixed copy had the file; the s6 copy's fork tree doesn't. |
| fix_cases `test_fix_p510_…` ×5 | (a), queued (P510) | `bench_watch.py:507` TypeError (str vs float, None vs float); `:506` IndexError (list, string) |
| s0 base-commit goldens, baseline-argv barrier probe (2) | (c), baseline-only by design | `tg1() missing … 'picks'`; `run_tg1_chain.py` exits 2 |
| s7 locks (5) | (b) s7 | `GateReached()`, lock asserts |
| s8 (16), sequencer (25) | (b) s8 | `cannot import name 'p426_wave2'` / `'p426_freeze'` |
| s9 (25), add_scrub (3) | (b) s9 | No `HARVEST.json`; `publish_*` absent; `Scrub(emails=)` unknown |

To classify the rest, the s6 copy needs its fork tree populated, then a rerun. The alternative is to rule that the pins become a committed test fixture, copied from the fork.

**Legacy behaviour is unchanged.** The four existing watcher test files (`test_work_queue`, `test_p426_watcher`, `test_p426_bench_watch`, `test_agentbench_watch`) pass on both sides: 199 passed on the baseline, and 204 passed on the s6 copy (those 199 plus the 4 s6 tests and the P38 invariant). The frozen legacy-argv `[INV]` test passes too.

## 3. Review of the s6 diff (`m1/bench_watch.py`, `chain_core.py`)

| Id | Diff lines | Severity | Finding and failure scenario |
|---|---|---|---|
| P47 | 689–693, 610 | **High** | **Zero observations can be speed-valid.** If `ps -o lstart` fails at bind time, `bound` is None, the first tick is `driver_alive=False` and the loop ends. `_verdict` skips the power check on that tick, the gap check passes and the window is tiny, so the journal can say `speed_valid: true` with no in-run observation. If `ps` fails transiently mid-run (a 30 s timeout, for instance), the watcher stops early with `driver_exited`, and a later on-battery interval is never seen. The identity fix is queued (`proc_guard.start_time()`, C151); this fail-open consequence must close with it. |
| P48 | 475–497, 500–512 | **High** | **The `pmset -g log` pattern fails open** (judgement call 1). If `_SRC` never matches the real log format, the parser returns `[]`, which reads as "no on-battery interval", and a leg that ran on battery is speed-valid. It should return None (unproven) when no `Using AC/BATT` line is recognized at or before the window start. The pattern should also be validated against a known positive (an unplug) in the rehearsal before certifying. |
| P49 | 677–683, 714–717 | Medium (a), queued P510 | `_overlap` crashes on any malformed element. The watcher dies without its `exit_state`, which the fix cases above reproduce. |
| P50 | 505–508, 695 | Low–medium | `pmset -g log` runs on every tick, with a 120 s timeout. §8 asks for `pmset -g ac` per tick and the log once, at exit. A slow log read stretches tick spacing and works against the gap rule. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P51 | 543 | Low | **Progress without `--planned` is wrong** (judgement call 2). Before the later invocations register, "planned" is only the registered slots, so progress reads 5/5 after the pilot. §7 freezes the schedule in `chain.json` before launch, so the plan can be derived from it instead of requiring `--planned`. This affects ETA and the correction note, not speed validity. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P52 | 715–720, 596–628 | Info / (d) | **Exit-line fields** (judgement call 3). The added fields are harmless, but the watcher now writes its own `speed_valid` while §16.6 gives the verdict to the sequencer, so there are two sources. Its verdict also requires a numeric `t`: my s8 fake journal (`add_support.write_watch`, `at="t0"`, no `t`) would judge speed-invalid. The tick time field is unpinned; I suggest pinning `t` in epoch seconds, as for the intervals, and I'll then align the fixture. |
| P53 | 557 | Low | `budget_hits` searches for the substring "budget" in `nonconv_kind` and `nonconv_flags`. This is the same heuristic family as P16; the counter is descriptive only. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| — | `chain_core.py` 7–13 | Sound | The P469 fix prefixes bare prior ids with `lang/`, and the frozen P469 test passes. |
| — | whole module | Sound (C235 G2) | The watcher only reads (chain.json, rows, pmset) and never signals the driver; in-run power marks speed only. The watcher-death rule (missing or extra `exit_state` is invalid), the gap rule (last tick to exit line included) and the 140 W / 28 V / battery > 20 % tick gate follow §8. |

**Judgement calls:** (1) and (2) are wrong as built (P48, P51). (3) is acceptable, with the field pin in P52. (4) is queued, and P47 is its fail-open consequence.

**Verdict for s6: fix then merge.** Fixes: P47 together with the queued `proc_guard` identity, P48, P49 (queued), P50. P51 can wait for the final round.

## 4. P38 coverage (`test_b2_frozen_fix_cases.py`)

| Test | Baseline | s6 copy |
|---|---|---|
| `test_fix_p38_a_snapshot_that_drifts_after_load_stops_the_leg_before_item_one` | fails (the baseline refuses `--p426`) | fails on the missing pins file (environment): not yet judged |
| `test_inv_p38_a_legacy_chain_runs_none_of_the_receipt_checks` | fails (the baseline rejects `--models`; C221 arrives in s1) | **passes** |

New tests this delivery: `test_fix_p510_a_malformed_on_battery_interval_leaves_the_watcher_alive_to_write_its_exit_state` (5 cases: ISO strings, short pair, not a pair, dict, not a list) and the two P38 tests above.
