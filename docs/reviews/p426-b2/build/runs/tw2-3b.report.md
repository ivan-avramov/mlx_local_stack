I couldn't stop the holder myself: the `kill` and `ps` commands need approval. It is a `time.sleep(1500)` started about 23:10, so it exits on its own by about 23:35, and the lock file it holds is already deleted. If you want it stopped sooner, its PID is 17425.

I recommend **fix then merge** for s7. The locks, the arbiter, the entry row and the ready-barrier checks are sound, and the gate does not refuse itself: no test in the suite takes or probes a lock under the real `STACK_WORKDIR`. The main gap is that the Item `done` barrier still skips the registry / lifecycle / worktree checks the spec requires.

## 1. Whole set on the s7 copy

```
../bin/run_candidate_s7_tests.sh <the 20 set files> --tb=line -rf
94 failed, 349 passed in 125.40s
```

One of the 94 was a test defect of mine, now amended. Every other failure has a class, and the s7 file has no (b):

| Failures | Class | Evidence |
|---|---|---|
| s7 `records_destined_for_main…`, `p426_dnf_record…fields`, `transport_dnf…` ×3, `dnf…rebaselines…`, `third_dnf…`; add_ledger `dnf_is_ledgered…`; fix_cases `r3_…`, `p23_…` (10) | (a), queued flat-layout DNF defect | `CHAIN ABORT: DNF refused: … row_arm: python/p1 None != 'oc'` |
| s7 `the_rehearsal_runs_the_smoke_shape_of_s1s_p426_python_order` (1) | (a), inherited from s1 | It ran the full s1 shape (`python [p1…p5]`, then `go`). §16.3 (line 518) says `--rehearsal` selects one pilot item plus two full items of s1's Python order. That is a leg-schedule rule for s1, not s8, as the s1–s5 fix report had claimed. |
| fix_cases `test_fix_p31_a_worktree_that_turns_dirty…` (1) | **(c) mine, amended** | `leg INVALID at …python|p1: worktree is not clean`. The new Item `ready` check caught my fixture's dirty flip at the first item, before any item ran. That is correct s7 behaviour, but it isn't the between-invocations case the test is for. |
| fix_cases `p510_…` ×5 | (a), queued P510 | the watcher crash on malformed intervals (s6) |
| s0 base-commit goldens; baseline-argv barrier probe (2) | (c), baseline-only by design | the legacy `tg1()` signature; the baseline argv without `--models` |
| s8 (21), sequencer (26) | (b) s8 | `p426_wave2` / `p426_freeze` absent |
| s9 (25), add_scrub (3) | (b) s9 | `wave2` harvest, `publish_*`, `Scrub(emails=)` absent |

**Amendment (post-reveal 3b):** `test_b2_frozen_fix_cases.py::test_fix_p31_a_worktree_that_turns_dirty_between_invocations_stops_the_next_one` now turns the worktree dirty only after the first Python invocation's `item4.continue`.
- s7 copy, both P31 cases after re-sync: `2 passed in 3.84s`.
- Baseline support checks: `54 passed in 19.32s`.

No other test was touched or added.

## 2. Review of the s7 diff

| Id | File:line (diff) | Severity | Finding and failure scenario |
|---|---|---|---|
| P54 | `chain_core.py` 92–101 and hooks 143–146 | **Medium (a)** | **The Item `done` row is missing** (call vi). §3's table (line 104) says "`done` barrier: the `ready` checks + reconciliation". The registry / lifecycle / worktree checks run only at `ready`. A worktree edit during the last item of an invocation is seen only at the next invocation's checks; during the leg's last item, only by the exit drift check, if at all. |
| P55 | `chain_core.py` 77–79 | Low | **The `:8000` check is optional** (call iii). It runs only if `ops` has `listeners`; real `ChainOps` has it (`chain_ops.py:331`), so production checks. A fake without it passes the Entry row silently, against "a missing seam is systemic" (§16.7). Put `listeners` in `P426_ENTRY_SEAMS`. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P56 | `p426_locks.py` 275–282, 336–339 | Low | **The lock probe creates files** (call viii). Probing an opposing lock with `O_CREAT` creates empty `gate/RUNNING` / `p426/*.lock` files and directories as a side effect. It is harmless to exclusion, since `flock` decides, but every gate run plants `p426/` files under the real `STACK_WORKDIR`. Opening without `O_CREAT` and treating ENOENT as free has no side effect. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P57 | `run_tg1_chain.py` 1200–1226 | Info | The Entry row runs while `LEG.lock` is held, after `out_root` and `RUNLOG.md` exist, before `chain.run()` and the router. A refusal prints `REFUSED:` and exits 2, leaving NOT_STARTED with only `RUNLOG.md` (call v). That matches §5.1 and the s9 NOT_STARTED harvest shape (the sequencer's `leg.json` plus `RUNLOG.md`). |
| P58 | `chain_core.py` 2551–2555 | Low | **`hook_disposition` on the invocation record** (call i). Acceptable: §3 says "both are persisted", and the frozen s3 tests and the implementer's tests pass. The risk is an unknown key in a resumed `chain.json`; I saw no refusal of it. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| — | `p426_locks.py` 318–349 | Sound | The arbiter is bounded at 30 s and released on every path; opposing locks are probed, then the own lock is taken; fds are `O_CLOEXEC`. The frozen race test, the child-holds-no-fd test and all four lock-direction tests pass. |
| — | `chain_core.py` 58–90 | Sound | Entry row: seams, record, HEAD, clean, gitlinks against v8, registry readable, probe identity, idle gap, busy, power, all before the router. `LAST_LEG_END` being garbled, NaN or in the future refuses; absent means no previous leg. Busy via `start_state()["busy"]` (call ii) is `busy_procs()` filtered by `BUSY`, which includes `session_cache_probe` and `opencode run` (`chain_ops.py:24`), so the survivors are covered. |
| — | process identity (C151) | Sound | Owned identities still go through `ops.create_time` → `same_identity` (the s1–s5 fix); s7 adds no `ps`-based identity. Locks are `flock`, not pid-based. |

**The other calls:**
- (iv) `LAST_LEG_END` as one decimal epoch-seconds number is (d): the spec says "epoch seconds" (§16.4, line 528) but not the file format. My add_sequencer test reads `float(text.strip())`, which agrees; s8 should write it the same way.
- (vii) `P426_ENTRY_SEAMS` beside `P426_SEAMS` is fine, apart from P55.
- (ix) The tests were never run red against the old code. My frozen s7 lock and entry tests were red on every earlier copy and are green here, which partly closes this. The hermeticity test has a working control line.

## 3. Gate self-exclusion

**Run:** a separate process held `flock` on `<scratch>/gate/RUNNING` (inside my copy). I then ran on the s7 copy with `STACK_WORKDIR=<scratch>`: the 20 set files, the implementer's `test_b2_s1…s7`, `test_b2_fix_chain`, `test_b2_fix_goldens`, `test_local_gate`, `test_c147_chain_runner` and `test_p371_baseline`.

**Result:**
- **Failures:** 93 distinct failed tests, exactly the classified set above minus the now-fixed P31. None of them is in the implementer's files, local gate, legacy chain or goldens.
- **Scratch after the run:** only `gate/RUNNING` and `HOLDING`. No `locks/ARBITER.lock`, no `p426/LEG.lock`, no `p426/SEQUENCER.lock`; any test that took or probed a lock under that `STACK_WORKDIR` would have created one through `O_CREAT`.
- **Static cross-check:** every lock-taking test uses `tmp_path` or sets `STACK_WORKDIR` itself. That covers the implementer's `pl.acquire(…, tmp_path)` tests, the local-gate test (`monkeypatch.setenv`) and my `chain_env` world. <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->

**No test refuses the gate.**

**Two limits of this run:**
- The pass count wasn't captured; the wrapper's quiet mode printed only the `FAILED` lines.
- I assumed the wrapper passes `STACK_WORKDIR` through. A real gate run is the definitive check.

## 4. Legacy behaviour and goldens

- **Legacy chains and local gate:** unchanged, by the run above, with zero failures in `test_c147_chain_runner`, `test_p371_baseline` and `test_local_gate`. `check` still takes no lock.
- **s7b changed no golden:** the s7 diff's files are `chain_core`, `chain_ops`, `local_gate`, `p426_hooks`, `p426_locks`, the tests and the runner, with no golden file among them, and `test_p371_baseline` passes against the unchanged goldens.

**Verdict for s7: fix then merge.** The fixes are P54, P55 and P56. The rehearsal smoke shape (an s1 defect) and the flat-layout DNF defect stay queued for the final round.
