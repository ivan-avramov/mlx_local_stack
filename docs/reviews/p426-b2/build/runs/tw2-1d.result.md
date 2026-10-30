## Delivery 1d report: the tests owed by G1–G8

I wrote the G1–G8 tests in 10 new files and left the 11 frozen files untouched. There are 53 new tests, plus 8 fixture checks.

- **Fixture checks:** 8/8 pass on the baseline.
- **New tests:** 52 fail and 1 passes (an invariant that holds today). Every failure is a missing module or interface, or the base chain refusing `--p426` before any load.
- **Frozen set (unchanged):** still 40/40 in s0, and 241 failed / 9 passed in s1–s9.

The most important finding is that §16.5 contradicts part of the frozen set. The frozen chain-level fixture lacks the census and expected-argv seams, so 29 frozen chain tests will fail for fixture reasons once s5 / s7 land (§4, item 2). That needs a designer decision before the build starts.

Nothing is committed. The working tree has only untracked test files plus the designer's spec change.

## 1. Per file

Classes: FIX = reproduces a failure the spec fixes, INV = preserves an invariant, NEW = new behaviour.

### `b2_frozen_add_support.py` (new fixtures; imports the frozen support, never changes it)
- **`world`:** the frozen P426 world plus `expected_worker_argv` (mlx-serve's own builder), `busy_procs` (`"<pid> <command>"` lines, as `chain_ops.py:335`), `descendants`, and `create_time` returning the owned worker's real start time. It also gives both legs of a pair one box's environment.
- **Pair and A4:** `keyed_argv` (a fixed pair key over the `--hmac-fd` pipe, plus `--pair-receipt`); `a4_gate_doc` (`gate.json` as `session_pinning_gate.py:284-304` writes it).
- **`RECORD` fixtures:** `site_tree` (a pip-format `RECORD` and the venv's editable `direct_url.json` shape), `verify_record`, and `chain_ops` (a real `ChainOps` with inert shell and process seams).
- **Sequencer fakes:** `SeqOps` implements `launch` / `wait` / `alive` / `power` / `harvest`. Its fake chain reads the HMAC key from the inherited fd and writes the leg's artifacts in the frozen formats (`chain.json` with `p426_ledger` / `p426_dnf` / `p426_invalid`, the receipt, ready and item records, rows with `wall_s`). Its fake watcher writes `watch.jsonl`. Plus a fake `Clock`, the argv and record builders, and a local copy of the `slot_file` rule, because `chain_rows.slot_file` doesn't exist until s3.

### `test_b2_frozen_add_support_check.py`: 8 INV, all pass on the baseline
It checks:
- the world's seams agree;
- the keyed argv carries exactly its key;
- the `gate.json` shape matches the gate's source;
- the `RECORD` tree verifies, and a mutation is detected (its line format matches the venv's PyYAML `RECORD`);
- the real-`ChainOps` fixture spawns nothing;
- the fake chain and watcher write a leg in the frozen formats, with `alive` bound by pid and start;
- the watcher-death script leaves no `exit_state`;
- the argv and record builders.

### `test_b2_frozen_add_sequencer.py` (G1): 21 NEW, all F
All fail with `:22 ImportError: cannot import name 'p426_wave2'`. They cover:
- **Pilot pair:** each leg's argv is `leg_argv`'s, one key for both legs, `--pair-receipt` set to the first leg's `receipt.json`; a watcher bound to each chain; harvest of each leg; 600 s between legs and `LAST_LEG_END` recorded; a self-hashed pair dossier naming both attempts; the sequencer holds `SEQUENCER.lock` and never `LEG.lock`.
- **Pilot gate:** stops on a DNF, on unproven ON engagement, on a speed-invalid pilot (watcher death) and on an INVALID pilot. When it passes, the sequencer writes `amendment.json` (its `v8_base_sha256` is v8's self-hash, and `w_python_s` covers the largest pilot wall), and legs 3+ use it.
- **Full run:** legs 1–8 in order, the 4 pairs each with their own key and dossier.
- **Stops:** an INVALID leg stops the sequencer (`leg.json` records it); an overrun writes `OVERRUN_PAUSED`, never kills, waits the chain out, harvests and stops.
- **Pause and resume:** `PAUSE` and `--pause-file` hold the next launch; resume skips VALID legs; a restart between the two legs of a pair voids it (`voided/…a1.json`) and both legs run again as `.a2`.
- **Make-up and rehearsal:** make-up runs OFF then ON as a keyed pair; the rehearsal runs R1 as a keyed pair, then R2 and R3 each with its own key and its `--inject`.
- **Refusals:** while `gate/RUNNING` is held, and without `v8_base.json`.

### `test_b2_frozen_add_pair.py` (G3): 5 NEW, all F
First failures: `:31 AssertionError: 2` (the first leg doesn't run on the baseline) and `:76`. They cover:
- the second leg passes the gate with `--pair-receipt` and the same key;
- refused after load and before item one when the key differs (credential HMACs differ), when the environment differs, and when a loaded library differs;
- a missing pair receipt refuses.

### `test_b2_frozen_add_census.py` (G4): 3 NEW, all F
The owned router, the worker and the chain's descendants are exempt. A foreign model worker or a foreign benchmark driver after load is systemic. First failures: `:33`, `:38`, `:44`.

### `test_b2_frozen_add_ledger.py` (G5): 3 NEW, all F
- A valid leg ledgers 5 rows in plan order, in one invocation, with consecutive indexes.
- A DNF is ledgered in its place, the rest land in the next invocation, and `p426_dnf` names the slot.
- An invalidated item appears in `p426_invalid` and ends the ledger.

First failures: `:39`, `:48`, `:61`.

### `test_b2_frozen_add_a4.py` (G2): 7 tests, all F
All fail with `:19 ImportError: … 'p426_reconcile'`. They are written against the 3-argument `a4_window_problems`:
- a matching window has no problem (NEW);
- bare requests differing from `gate.json` are a problem ×4: one missing, a different prompt, another anon session, a non-anon session (FIX);
- a `gate.json` listing other requests is a problem (FIX);
- the `ses_*` requests are still checked against the receipt (FIX).

### `test_b2_frozen_add_argv.py` (G6): 6 tests, all F
- **ON passes position-free (NEW):** an ON argv with the three pairs appended is accepted.
- **Systemic after load, before item one (FIX):** an ON argv missing a pair; ON with OFF's tokens reordered; OFF with an extra flag; OFF with drafter flags.
- **Pins (NEW):** a snapshot differing from `<WT>/…/pins.json` refuses at entry.

First failures: `:46`, `:51 … :71 assert (2 == 2 and [])`, `:82`.

### `test_b2_frozen_add_scrub.py` (G7): 4 tests, 1 P / 3 F
- **F:** the operator's address and the operator's domain refuse and are never published ×2 (NEW); a foreign address goes to `review.emails` (NEW). All 3 fail with `:29 TypeError: Scrub.__init__() got an unexpected keyword argument 'emails'`.
- **P:** the Wave-1 `Scrub` constructor still works without emails (INV).

### `test_b2_frozen_add_record.py` (G8): 4 tests, all F
All fail with `:19 AssertionError: ChainOps.interpreter_inventory (§16.2) is missing`.
- an intact tree gives a stable hash (NEW);
- a file mutated without its `RECORD` refuses (FIX);
- a changed file with a matching `RECORD` changes the hash (NEW);
- editable metadata differing only in the worktree path gives the same hash (NEW).

## 2. Commands and summary lines (verbatim)

```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_add_support_check.py
8 passed in 0.28s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_add_sequencer.py bench/tests/test_b2_frozen_add_pair.py bench/tests/test_b2_frozen_add_census.py bench/tests/test_b2_frozen_add_ledger.py bench/tests/test_b2_frozen_add_a4.py bench/tests/test_b2_frozen_add_argv.py bench/tests/test_b2_frozen_add_scrub.py bench/tests/test_b2_frozen_add_record.py
52 failed, 1 passed in 0.80s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py
40 passed in 16.59s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s1_cli.py bench/tests/test_b2_frozen_s2_probe.py bench/tests/test_b2_frozen_s3_core.py bench/tests/test_b2_frozen_s4_reconcile.py bench/tests/test_b2_frozen_s5_receipt.py bench/tests/test_b2_frozen_s6_watch.py bench/tests/test_b2_frozen_s7_locks.py bench/tests/test_b2_frozen_s8_freeze.py bench/tests/test_b2_frozen_s9_harvest.py
241 failed, 9 passed in 12.83s
```

On the first run, 5 negative chain tests in the new files passed on the baseline for the wrong reason: argparse rejecting `--p426` also gives rc 2 with no item started. I tightened them to require that the leg actually loaded before it was refused. After that, only the invariant passes.

## 3. Remaining gaps

- **Sequencer fake contract.** §16.4 says `launch` returns a "handle" but doesn't name its fields. My fake handle has `pid` / `start` / `argv`, and the sequencer presumably passes `(handle.pid, handle.start)` to `alive()`.
- **Fake-chain artifacts vs what the sequencer reads.** §16 doesn't name the inputs the sequencer classifies a leg from. I chose them; if the build reads others, the sequencer tests fail for fixture reasons:
  - the pilot gate reads `chain.json` (status, rc, the ledger, `p426_dnf`), the item records' draft counters, and `watch.jsonl`'s `exit_state`;
  - the pilot walls come from the rows file named in `chain.json` `progress.invocations`.
- **Unnamed paths and formats:**
  - where `OVERRUN_PAUSED` is written (I search under `$STACK_WORKDIR`);
  - the speed-invalid field in the leg record (I test it only through the pilot gate stopping);
  - the occurrences file format (I used JSON lines);
  - the pair dossier's file name (I search `<out-base>/**/pairs/*.json`).
- **Remaining untestable points:**
  - how a `harvest_wave2` refusal is signalled (raise vs return): I accept either, provided nothing is published;
  - the sequencer passing the operator email: `ops.harvest(leg_root)` carries no email;
  - check-realized tampering: an existing P426 out-root is refused, so it can't be exercised;
  - the live `RECORD` check in R1.
- **Census matching.** The census matches the owned worker by `(pid, create_time(pid))`. My fixture answers the worker's real start time; the frozen FakeOps answers 1.0.

## 4. Frozen tests that contradict §16.5 (not edited)

1. **`test_b2_frozen_s4_reconcile.py`:** `test_new_the_a4_window_matches_its_receipt` and `test_fix_an_a4_window_whose_session_differs_from_its_receipt_is_a_problem[prompt|session|missing]` call `a4_window_problems(lines, a4_receipt)` with two arguments. §16.5 makes the signature `(lines, a4_receipt, a4_gate)`, so these raise `TypeError` unless `a4_gate` gets a default.
2. **Every chain-level test in `test_b2_frozen_s7_locks.py` (29 tests) builds its leg with the frozen `p426_world`.** That world lacks the §16.5 `expected_worker_argv`, `busy_procs` and `descendants`. Its FakeOps also answers `create_time(pid) = 1.0`, so the census would treat the owned worker as foreign. Once s5 / s7 wire those seams, the positive legs fail with `AttributeError` or a census refusal, and the negative ones fail at the wrong checkpoint.

   The new files carry the corrected world (`b2_frozen_add_support.world`), but the frozen tests can't use it. Either the designer amends the frozen `p426_world` (adding the three seams and a `create_time` that answers the worker's start, as `b2_frozen_add_support.world` does), or the frozen s7 chain tests are superseded by equivalents on the new world.
3. **`test_b2_frozen_s7_locks.py::test_new_the_rehearsal_runs_the_smoke_shape_of_s1s_p426_python_order`** runs `--rehearsal` without `--hmac-fd`. That is still valid under §16.4 (a fresh key is drawn), but under §16.5 R1's real legs always receive one. It isn't a contradiction, but the frozen set never exercises a rehearsal leg with a key.
