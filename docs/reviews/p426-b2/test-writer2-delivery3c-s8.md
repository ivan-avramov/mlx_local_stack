I recommend **fix then merge** for s8. The sequencer and freeze logic are mostly faithful to the spec, but two settle-bound rules aren't derived as §4.2 says (P60, P61), and several `ops` seams the spec doesn't name block a third of my sequencer and freeze tests. Those seams need your ruling before the remaining tests can judge s8.

## 1. Whole set on the s8 copy

```
../bin/run_candidate_s8_tests.sh <the 20 set files> --tb=no -rf
first run (my set as of 3b):  76 failed, 367 passed in 118.61s
after this delivery's fixes:  80 failed, 365 passed in 119.39s
```

The second run adds my two new P536 failing cases, and two freeze tests that now get past `STACK_WORKDIR` and hit `restore_diff_problems`.

| Failures | Class | Evidence |
|---|---|---|
| add_sequencer ×24 (all but the two refusal tests) | **(d)** | `p426_wave2.py:678: 'SeqOps' object has no attribute 'operator_emails'`. §16.5 says "the sequencer passes the main checkout's `git config user.email`"; the candidate routes it through `ops.operator_emails()`. Next the sequencer also calls `ops.worktree_state(path)`, `ops.identity(path)` and `ops.harvest_path(attempt)`; none is in §16.4 / §16.6's sequencer ops (`launch`, `wait`, `alive`, `power`, `harvest`, `publish_*`). Your decision: pin these seams; my fake then adds them. |
| s8 freeze ×7 (rehearsal manifest, failed precondition, dirty worktree, the three R1 tests, gitlinks) | **(a)** | `p426_freeze.py:253: 'FreezeOps' object has no attribute 'restore_diff_problems'`. §16.4 puts preconditions in `checks(kind, **inputs)` and gives `ops` only `worktree_state(path)`. A missing seam also crashes with a traceback instead of `REFUSED:`. |
| s8 `makeup_groups…` | **(d)** | The candidate orders items by `occurrence` as an ordinal and merges duplicates per (session, language, item, seed). My fixture used `occurrence` as a repeat count and kept two `grep`. The meaning of `occurrence` is unnamed; see call 6 below. |
| s7 DNF ×7, add_ledger, fix_cases R3 / P23 | (a), queued | the flat-layout DNF defect (`row_arm … None != 'oc'`) |
| s7 rehearsal smoke shape | (a), s1 | §16.3 shape not applied (P536) |
| fix_cases P510 ×5 | (a), queued | the s6 watcher crash |
| fix_cases `test_fix_p536_…` ×2 (new) | (a), P536 | make-up: the chain refuses `makeup` (rc 2); R2: the injection has no effect |
| s0 ×2 | (c), baseline-only by design | base-commit goldens; baseline argv |
| s9 ×25, add_scrub ×3 | (b) s9 | `wave2` harvest, `publish_*`, `Scrub(emails=)` absent |

No (b) is left in the s8 or add_sequencer files.

### Amendments (all tagged post-reveal 3c, all my defects)
| What | Change | Tests touched |
|---|---|---|
| `b2_frozen_add_support.write_leg` | Ready, item and DNF records are now sealed (§16 immutable records), with `ready_sha256` the file's sha. The ledger has the leg's full plan (§1: pilot / reload 5; s1 / s2 22 + 21; make-up from the occurrences file), one rows file and invocation (with `expected_slots`) per language. It used to be 5 items for every leg. | all add_sequencer tests; `add_support_check::test_the_sequencer_fakes_write_a_leg_in_the_frozen_formats` |
| `seq_argv` and `sequencer_records` | The worktrees lie under `$STACK_WORKDIR` and v8 names them (`$STACK_WORKDIR/stack-p426-{off,on}`); the rehearsal `--out-base` is under `p426/rehearsal/` (§1). | all add_sequencer tests |
| s8 freeze | Autouse `STACK_WORKDIR=<tmp>/wd`; worktrees under it; new `leg_record` writes a sealed leg record. `leg_root_with` builds complete R1 / R2 / R3 legs (R2: one `p426_invalid` at `done` for the injected mismatch; R3: one `kill_boundary` item record). `_v8_argv` replaces the ON receipt only when a test overrides it. The rehearsal test expects `$STACK_WORKDIR/p426/rehearsal/r1`. | all `p426_freeze` tests in s8 |
| `test_b2_frozen_fix_cases.py` | **New:** `test_fix_p536_a_makeup_leg_runs_one_invocation_per_group_in_the_canonical_order` and `test_fix_p536_the_r2_injection_invalidates_the_rehearsal_leg_for_the_reconciliation_mismatch`, plus the `_invs` helper; `A` imported at the top. | — |

- **Baseline support checks:** `54 passed in 20.12s`.
- **The two new cases on the baseline:** `2 failed in 0.42s`, as expected.

## 2. Review of the s8 diff

| Id | File:line (diff) | Severity | Finding and failure scenario |
|---|---|---|---|
| P59 | `p426_freeze.py` 246–260 | Medium (a) | The restore-diff precondition goes through an unnamed `ops.restore_diff_problems`, not `checks`. With spec-named `ops` the freeze crashes, a traceback rather than `REFUSED:` / rc 2. |
| P60 | `p426_freeze.py` 436–441 | Medium (a) | **v8's `settle_bound_s` is an operator input** (≥ 900 s). §4.2 defines it as max(900 s, 2 × the largest single-request elapsed of this entry's items in the rehearsal and the M63 / P456 rows). Any typed value ≥ 900 passes underived: a bound below a long prefill falsely invalidates items. |
| P61 | `p426_freeze.py` 477–479 | Medium (a) | **The amendment never raises the bound.** It copies v8's `settle_bound_s`; §4.2 raises it to max(that, 2 × the largest single-request elapsed over both pilots). A pilot with a request longer than half the v8 bound leaves the session legs with too small a bound. |
| P62 | `p426_freeze.py` 395–412 | Medium / (d) | **"Fork production tree == the serving build's"** (§10.1) is only checked as the gitlinks and an operator-typed `production_ref` matching a table in code (`p426_plan.EXPECTED_BUILDS`). No tree is compared, so a wrong ref string that matches the table passes. Comparing the production ref's tree with the gitlink's tree in the fork would actually check it. |
| P63 | `p426_wave2.py` 613–634, 1000 | Low | **Planned slot counts are hard-coded** (5 / 43 / 43 / 5). §5.1 VALID requires the ledger to equal the plan, and the plan is frozen in `chain.json`. If the universe changes, every leg classifies INVALID. Read the plan from `chain.json` instead. | <!-- allow-shorthand: severity word -->
| P64 | `p426_wave2.py` 1076 | Info | `LAST_LEG_END` is also written after a NOT_STARTED leg, so a refused entry restarts the 600 s gap. Harmless. |
| P65 | `p426_wave2.py` 1220–1224 | Low / (d) | The rehearsal takes its frozen prompt date from the sequencer's clock and its identity from `ops.identity`. Neither is named; the rehearsal's records carry no date. | <!-- allow-shorthand: severity word -->
| — | §9, C151 | Sound | The sequencer takes `acquire("sequencer")` only, never `LEG.lock`, and makes no kill or signal call. Identities use `co.default_create_time` (`proc_guard.start_time`); handles carry `(pid, start)`. |
| — | §1, §6.5, §8, §10.3, §16.6–16.7 | Sound | The pilot gate's conditions; one dossier per pair attempt, named with off/on attempts, receipt / harvest file sha256s and published (rehearsal: not published); `sequence.json` with `previous_sha256`; `OVERRUN_PAUSED` with its fields, waited out and never killed; canonical occurrences per arm at `<out-base>/makeup/occurrences.<arm>.jsonl`; speed from the s6 `speed_verdict`; resume skips VALID + harvested; R2 INVALID expected, not a stop. |

## 3. The implementer's judgement calls

| # | Call | Judgement |
|---|---|---|
| 1 | Exit codes 0 / 1 / 2 / 3 / 4 | **Accept.** The spec fixes only refusal = 2. Pin the rest, and say that 3 / 4 never mean a lost leg. |
| 2 | `OVERRUN` only when an overrun leg also ended INVALID; otherwise normal state + `overrun: true` | **Spec gap → you.** §16.1 lists `OVERRUN` as a leg state; my frozen test expects `OVERRUN` for an overrun leg that finished. Rule whether a leg that finishes past its deadline is OVERRUN (excluded from pairs) or VALID with a flag. |
| 3 | `NOT_STARTED` = rc 2 and no `chain.json` | **Accept.** It matches s7's refused entry (out-root with only `RUNLOG.md`) and the s9 NOT_STARTED harvest shape. |
| 4 | R2 = exactly one `p426_invalid` whose reason matches `reconcil` | **Accept, then pin the marker.** The chain's `--inject reconcile-mismatch` should write a fixed reason, so the match isn't free text; my fixture uses "reconciliation mismatch (injected)". |
| 5 | R3 = VALID, no DNF, an item with a `kill_*` case | **Accept** (§1 "scored strict fail with its failed-line case"). |
| 6 | `occurrence` = the item's ordinal; de-duplication per (session, language, item, seed) with arms merged | **Spec gap → you.** I'd accept the de-duplication: the union of DNF'd slots across both arms, so a slot DNF'd in both arms runs once per make-up leg (§5.5 "the whole union"). For order I'd change it: take "original order" from the session's P426 schedule order (`Random(seed).sample(sorted(pool))`, §7), derivable from the fields, rather than an ordinal field. My s8 test changes after the ruling. |
| 7 | 900 s watcher-finalize window | **Accept** (3 × the 300 s interval). |
| 8 | Low power before a launch stops without consuming an attempt | **Accept.** Nothing is launched; the chain's own entry check still makes a real NOT_STARTED attempt. | <!-- allow-shorthand: severity word -->
| 9 | `--build-inputs` / `--historical-walls` JSON inputs | **Accept** for the box ops. Pin `ops.historical_walls()` (§16.7 names only `build_inputs`), then my `FreezeOps` adds it. |
| 10 | `settle_bound_s` from build inputs, 900 s floor | **Change:** derive it (P60, P61). |
| 11 | Production tree == serving build via gitlinks + `production_ref` | **Change:** compare trees (P62), or rule that the table check is enough. |
| — | `--r1-off` / `--r1-on`; rerun flags; make-up under `<out-base>/makeup/`; `--out-base` rules; 30 s tick | **Accept.** §16.7 names `--r1-off` / `--r1-on`, and §1 says rehearsals write only under `p426/rehearsal/`. Make-up out-roots under `makeup/` are (d) against my add_sequencer test, which expects `<out-base>/tg1-p426-off-makeup.a1`; §5.5 "own out-root namespace makeup" allows both. Please rule. |

## 4. P536 gaps: owner and coverage

| Gap | Owner | Covered by |
|---|---|---|
| Chain `makeup` mode and `--occurrences` | s1 (CLI) + s3 (leg loop: one invocation per group) | **New:** `test_fix_p536_a_makeup_leg_runs_one_invocation_per_group_in_the_canonical_order` (red: the chain refuses with rc 2) |
| `--rehearsal` smoke shape | s1 / s3 | frozen s7 `test_new_the_rehearsal_runs_the_smoke_shape_of_s1s_p426_python_order` (red) |
| R2 `--inject reconcile-mismatch` | s3 / s4 (the chain perturbs one item's reconciliation) | **New:** `test_fix_p536_the_r2_injection_invalidates_the_rehearsal_leg_for_the_reconciliation_mismatch` (red: no invalidate) |
| R3 `--inject stall-kill` | s2 (probe: "a lowered stall limit on one item") + s3 | **Not written; spec gap.** How the chain hands the lowered limit to the probe (flag or env, which item) is unnamed, and the fake probe needs it. |
| Unmocked topology test (§13) | a new mini-slice after the chain gaps | **Not written; spec gap.** The real chain's `ChainOps` would start the router, which tests may not do. You need to define "unmocked": a real chain subprocess with injectable fake ops, real locks and real `chain.json`, but no router. |
| s9 contract (`--operator-email`, `publish_*`) | s9 | `publish_dossier` / `publish_run_files`: frozen s9 tests (signatures, returns, byte-identity, refusals); `Scrub(emails=)`: add_scrub. **`--operator-email`** is unnamed; I wrote no test for it, so the s9 CLI flag needs naming. |

## 5. Verdict for s8: fix then merge
1. P59: restore diff through `checks`.
2. P60 / P61: derive the settle bound in v8 and in the amendment.
3. Your rulings on the unnamed seams: sequencer `operator_emails`, `worktree_state`, `identity`, `harvest_path`; freeze `identity`, `historical_walls`.
4. Your rulings on OVERRUN and `occurrence`.
5. Then a rerun of my sequencer and freeze tests. They can't judge the sequencer's behaviour until the seams are pinned: 31 of them stop at a missing seam today.