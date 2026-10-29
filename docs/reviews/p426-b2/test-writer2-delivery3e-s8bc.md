I recommend **merging s8 (s8 + s8b + s8c)**. Every s8, sequencer, freeze and P536 chain-side test in my set passes on the s8c copy. What fails is the queued final-round work and s9, plus one open question (P66) for you. Nothing was committed.

## 1. Fixture fix and runs (all amendments tagged post-reveal 3e)

**Changes, all to my fixtures and tests:**
- **Tick time (your ruling):** `b2_frozen_add_support.write_watch` ticks carry `t` (epoch seconds). They also carry `interval_s`, as the s6 watcher records it, because the §8 gap rule needs the interval. That removes the `a_speed_valid_leg_records_it` failure.
- **Rehearsal date (your ruling):**
  - `S.rehearsal_manifest` now records `frozen_prompt_date` and the three identity keys; the world's manifest records the world's identity.
  - s8 `rehearsal_argv` passes `--frozen-prompt-date`, and `test_new_freeze_rehearsal_writes_a_self_hashed_rehearsal_manifest_once` asserts the date and identity are recorded.
  - New: `test_new_the_rehearsal_refuses_a_date_that_differs_from_the_manifests`.
- **Three of my own defects, found in this run:**
  - s1 `test_new_a_record_of_the_wrong_kind_for_the_mode_refuses[mode4-v8]`: its rehearsal out-root is now under `p426/rehearsal/`. Under `wave2` the new §1 out-root rule refused it before the record-kind check the test targets.
  - add_sequencer `seq()`: creates `wd` with its parents. This fixed `the_planned_slots_come_from_the_legs_frozen_schedule`.
  - add_sequencer `…restart_between_the_legs_of_a_pair…`: the prewritten first leg now has the sequencer's sealed `leg.json`.
- **New:** `test_fix_p536_topology_a_makeup_leg_that_stops_early_records_its_unrun_occurrences` (§5.5 `not_run`).

**Runs:**
```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py bench/tests/test_b2_frozen_add_support_check.py
55 passed in 18.61s
../bin/sync_to_s8c.sh; ../bin/run_candidate_s8c_tests.sh <the 20 set files> --tb=no -rf
45 failed, 421 passed in 129.03s
```

That full run came before I added the `not_run` case. Run on its own, that case gives `1 failed in 6.79s` on s8c and `1 failed` on the baseline, where the s8 modules don't exist.

| Failures | Class | Evidence |
|---|---|---|
| s7 DNF ×7, add_ledger ×1, fix_cases R3-limit / P23 ×2 | (a), queued | the flat-layout DNF defect |
| fix_cases P510 ×5 | (a), queued | the watcher crash (`bench_watch.py:506/507`) |
| s9 ×25, add_scrub ×3 | (b) s9 | harvest `wave2`, `publish_*`, `Scrub(emails=)` absent |
| s0 ×2 | (c), baseline-only by design | base goldens / baseline argv |
| fix_cases `…makeup_leg_that_stops_early…` (new, run separately) | **(d)** | `not_run` = `[p2, p3]`. p3 is unrun as expected, so slot matching works. p2 is the item that ran and was invalidated at `done`; my test counts only items that never ran. §5.5 ("its unrun occurrences") doesn't say whether the item the leg stopped on counts. Your decision. |

**Passing now:** every s8 freeze and add_sequencer test, the s1–s6 slice files, add_pair / argv / census / a4 / record, and these P536 chain-side cases: make-up mode, the R2 injection (exact reason, first item), the R3 stall injection (flags on the one invocation, kill scored, VALID), both topology tests (pilot pair end to end, one make-up leg VALID) and the s7 rehearsal smoke shape.

## 2. Review of s8b + s8c

| Id | File:line (diff) | Severity | Finding |
|---|---|---|---|
| P66 | s8c `chain_core.py` 153–159; `p426_wave2.not_run` | (d) | **`not_run` includes the invalidated item** (see the table above). If unrun means "no usable result", it's correct; if it means "never launched", the invalidated item shouldn't be listed. |
| P67 | s8c `fake_probe.py` 1277–1278 | Low | **The implementer's fake R3 kill isn't a kill.** It sets only `nonconv_kind="stalled"` (no `termination.killed`, no `requests_completed_at_kill`), so the chain reconciles the item as `completed`, not `kill_*`. Their own report says no test asserts a `kill_*` record. My fake does, and the chain side passes it. | <!-- allow-shorthand: severity word -->
| P68 | s8c `run_tg1_probe.py` 1355–1358, `arm_runner.py` 8–30 | Info | The probe gains `--inject-stall-item` / `--inject-stall-s`, refused without `--evidence p426`. This is a probe-code edit, so `probe_code_sha256` moves; R1–R3 and v8 must be frozen after it. |
| P69 | s8c `chain_core.py` 124–132 | Low | `tg1_schedule` now turns a schedule `ValueError` into `ChainAbort` for every mode, legacy included. Legacy behaviour is otherwise unchanged: my s1 legacy golden tests, M63 / P223 order and the C221 config diff pass, and `rehearsal=` / `makeup` are P426-only. | <!-- allow-shorthand: severity word -->
| — | s8c `run_tg1_chain.py` 1289–1320, 1341–1344 | Sound | `makeup` only with `--p426` and `--occurrences` (and the reverse); `--inject` only with `--rehearsal`; `--rehearsal` only in chain mode and only under `$STACK_WORKDIR/p426/rehearsal/`, refused before anything is written. |
| — | s8c `schedules.py` 461–503 | Sound | `makeup_canonical` is one implementation shared by sequencer and chain: s1 then s2, the session's language order, then `occurrence`, de-duplicated with arms merged. `tg1_makeup` builds one load with one invocation per (session, seed, language) group; the plan is the union. |
| — | s8c `p426_wave2.py` 326–332 | Sound | `planned_slots` sums the invocations' `names`, which is right for pilot-only legs whose `full_names` is the whole order. My planned-slots test (VALID at the frozen size, INVALID one slot short) passes. |
| — | s8c `p426_reconcile.py` 255–260; `p426_record.py` 271 | Sound | Item-record requests carry `elapsed_s` (from the logged `elapsed`, None for failed lines), which §16.8 names as the settle bound's input; `makeup` mode loads the timeout amendment (§1: legs 9–10 need v8 + amendment). |
| — | s8b `p426_freeze.py` 110–230, 488–530 | Sound | Missing seams refuse; restore diff and production tree go through `checks`; the derived v8 and amendment settle bounds; R2's exact reason; the rehearsal manifest records date + identity; `p426_wave2 rehearsal` refuses a date different from the manifest's. |

## 3. "Rehearsal launches nothing"

It passes now: `test_new_the_rehearsal_runs_r1_as_a_pair_then_r2_and_r3` is in s8c's 83 passing s1 + add_sequencer tests. It had two causes:
- **In 3c:** my fixture's rehearsal `--out-base` was under `wave2`.
- **In 3d:** the copy didn't yet accept `p426_wave2 rehearsal --frozen-prompt-date`. On the s8c copy before my manifest fixture fix, the refusal was the date check against a manifest that recorded no date.

## 4. Verdict for s8: merge

Still open: the queued final-round items (flat-layout DNF, P510, R3-limit / P23), s9, your ruling on P66, and P67, which is cosmetic for the implementer's own tests.