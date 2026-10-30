## Delivery 1c report: the frozen set

The set is complete for everything §16.4 names, except the sequencer's `main`: §16.4 names its `ops` but not its argv, so the sequencer tests can't be written without inventing a CLI. That is the one blocker left; everything else in the brief is covered.

- **s0:** 40/40 pass on the baseline.
- **s1–s9:** 250 tests collected; 241 fail and 9 pass. All 9 passes are invariants that genuinely hold on the base commit. Every failure is a missing module or flag, or the old behaviour. None is a fixture error or a refusal that passes by accident.

The chain-level `--p426` tests run a hermetic leg built from FakeOps with the §16.2 / §16.4 seams, the item-barrier fake probe, and records written with the §16.1 recipe. They live in the s7 file, because a positive leg needs slices 1–7.

Working tree: only my 11 untracked test files, plus the designer's spec change.

## 1. Per file

Classes: FIX = reproduces a failure the spec fixes, INV = preserves an invariant, NEW = new behaviour. Baseline outcome is F unless marked P.

### `b2_frozen_support.py` (changes for this delivery)
- **Registry and records:** registry entries carry `type: vision` (mlx-serve requires it); the amendment's `v8_base_sha256` is v8's self-hash (ruling 3); the abort manifest has the ruled `in_flight` dict.
- **Fake probe:**
  - `--print-identity` is shaped like the real one (`arm_runner.py:926-956`) and carries the same composite as the fake's manifests;
  - unknown flags are tolerated;
  - new knobs: `B2_SKEW_ITEMS`, `B2_ABORTS` (boundary / in-flight failed / in-flight completed, written as the §16.1 abort manifest plus the server-side lines and counters), `B2_ABORT_CAUSE`, `B2_LOCK_PROBE` (does the child hold an fd on the lock file).
- **`p426_world` (FakeOps seams):**
  - `worktree_state`, `last_leg_end`, `proc_argv`, `proc_environ`, `interpreter_inventory`, `loaded_images`, `snapshot_hashes` (from the fork's real `pins.json`);
  - the worker's argv is built by mlx-serve itself (`process_manager._build_command`);
  - `a4_gate` writes the A4 window, the receipt and `gate.json` in the order and formats of `session_pinning_gate.py`.
- **Runner:** `p426_argv` (with `--hmac-fd` over a real pipe) and `run_p426` (captures stderr and the `REFUSED:` lines).

### `test_b2_frozen_s0_support.py`: 40 tests, all INV, all pass
New validations for this delivery:
- the fake identity equals its manifests for both arms, both languages and both seeds;
- mlx-serve's ON argv adds exactly the three §6.3 flags;
- the world's records and seams agree;
- the fake A4 gate's 7-request window parses cleanly with the baseline parser;
- the DNF knob's three modes give the §16.1 stamp and the right server-side counts;
- the lock knob detects an inherited fd, and reports none otherwise.

### `test_b2_frozen_s1_cli.py`: 46 tests, all F
The tests are as in delivery 1b, with a valid `--hmac-fd` added to every non-rehearsal argv. First failure lines:
- refusal tests: `:55 AssertionError: usage: …` (no `REFUSED:` line);
- tests needing the new flags: `argparse SystemExit: 2`;
- "`--models` required": `:55 …pred=244s…` (the baseline ran the chain).

### `test_b2_frozen_s2_probe.py`: 13 tests, 4 P / 9 F
The abort-manifest test now asserts the ruled shape (`gate.request_usage`, `session_id`, and `in_flight.{in_flight, message_id, requests_started}` consistent with each other). The P426 tests fail with `:89 no manifest…`, `TypeError: … 'p426'` and `AttributeError: … TG1_P426_EVIDENCE`; the 4 invariants pass.

### `test_b2_frozen_s3_core.py`: 8 tests, 2 P / 6 F
Unchanged. First lines: `ValueError: disposition kind…`, `AttributeError: … 'slot_file'`, and the `TRANSPORT_POLICIES` assert.

### `test_b2_frozen_s4_reconcile.py`: 62 tests, all F
55 fail with `:24 ImportError: cannot import name 'p426_reconcile'` and 7 with `:417 ImportError: … 'p426_hooks'`.

| Change | Tests |
|---|---|
| `parse_log` per the ruling (FIX/NEW) | `ValueError` on an unparseable complete line; no entry for a trailing partial line; field values are strings |
| A4 window | now in the gate's real order; the anon-count case dropped (see G2) |
| `P426Hooks` (new, NEW/FIX) | ready writes the record (cursor offset, worker snapshot, owned identity) and accepts; done reconciles, writes the item record (`ready_sha256`, `log_range.start`) and accepts; a skewed count invalidates (record `invalid`); an ON item without counters invalidates; an engaged ON item is accepted; unreadable metrics raise `HookInfrastructureError`; a missing ready record at done is systemic |

### `test_b2_frozen_s5_receipt.py`: 46 tests, all F
26 fail with `:19 ImportError: … 'p426_secrets'` and 20 with `:24 ImportError: … 'p426_receipt'`. New `arm_receipt` tests (all NEW), using the §16.4 signature over the fake seams:
- `<WT>` canonicalized, and the worker argv is mlx-serve's;
- volatile keys are recorded as keys only;
- credentials are recorded only as HMAC-SHA256 under the pair key, and `TOKENIZERS_PARALLELISM` is recorded as is;
- a different key gives a different HMAC;
- an OFF and an ON receipt of one build pass the pair gate;
- `credential_values(env_files=…)` reads `.env`.

### `test_b2_frozen_s6_watch.py`: 4 tests, 1 P / 3 F
Unchanged, using the §16.4 CLI. The 3 fail with `SystemExit: 2`.

### `test_b2_frozen_s7_locks.py`: 34 tests, all F
**Gate side, 5 tests (NEW).** Unchanged: `:27/:55 assert (GateReached() == 1)`, `:34`, `:45`.

**Chain-level `--p426` leg, 29 tests (NEW unless noted).** On the baseline each fails on `assert 2 == 0` (argparse rejects `--p426`), on an absent `.stop` / invocation / `REFUSED:` line, or at `:280 / :343 … and []`.

| Area | Tests |
|---|---|
| positive leg | the pilot leg is VALID; probe `--items` are the first 5 of the P426 Python order; 5 ready records written before each `.go`, named by `slot_file`, with the §16.1 fields; 5 item records `reconciled` / `completed` |
| probe argv and records | the chain passes `--evidence p426`; `schedule_sha256` frozen; `log_bounds.json` finalized; the receipt is self-hashed and the secret appears nowhere in the out-root |
| leg shapes | rehearsal smoke shape (1 + 2 items of the s1 order, under `p426/rehearsal/`); s2 runs Go first and both P426 orders exactly |
| invalidate | at done (skew on item 2 → `.stop`, nothing after it, one `invalid` record); at ready (dirty worktree after item 1 → `.item2.stop`, no `.go`); an ON leg without counters |
| DNF | ×3 modes: a `p426_dnf` sidecar linked to an `items/…dnf.json` with the right `case`, the remaining items relaunched in order on the same load, never `invalidate`; DNF then a normal item re-baselines its window; the third DNF is systemic; a changed worker with a DNF stamp is systemic (no DNF record); a non-DNF cause is systemic |
| manifest and entry | a manifest without the P426 evidence policy is refused (no ACK); entry refusals ×6 before the router: foreign busy process, `LAST_LEG_END` < 600 s, power, HEAD ≠ record, dirty worktree, probe identity ≠ record |
| locks | the chain refuses while `gate/RUNNING` is held; it holds `LEG.lock` while running; the spawned probe inherits no lock fd; of a simultaneous gate and chain, exactly one runs |

### `test_b2_frozen_s8_freeze.py`: 18 tests, all F
12 fail with `:20 ImportError: … 'p426_wave2'` and 6 with `:25 … 'p426_freeze'`. All NEW.
- **`p426_wave2` (unchanged):** `leg_argv` ×8, the attempt out-roots, the deadline, make-up grouping ×2.
- **`p426_freeze`, rewritten to §16.4:**
  - the rehearsal manifest is written once from `ops.worktree_state` commits (a second run is refused);
  - a failed `checks` precondition refuses, naming it, and writes nothing;
  - a dirty worktree refuses;
  - `amend` refuses a v8 base with a bad self-hash;
  - `v8` refuses a manifest of the wrong kind;
  - `v8` refuses arms whose gitlinks differ.

### `test_b2_frozen_s9_harvest.py`: 19 tests, 2 P / 17 F
Entries are now matched by `source` relative to the leg root; a foreign email must go to `review.emails` with rc 0 (new, NEW). First failure lines: `:48`, `:67`, `:80`, `:120`, `:175` (no `REFUSED:` / no `HARVEST.json`; the baseline module exits 0 silently).

## 2. Commands and summary lines (verbatim)

```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py
40 passed in 17.20s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s1_cli.py bench/tests/test_b2_frozen_s2_probe.py bench/tests/test_b2_frozen_s3_core.py bench/tests/test_b2_frozen_s4_reconcile.py bench/tests/test_b2_frozen_s5_receipt.py bench/tests/test_b2_frozen_s6_watch.py bench/tests/test_b2_frozen_s7_locks.py bench/tests/test_b2_frozen_s8_freeze.py bench/tests/test_b2_frozen_s9_harvest.py -rA --tb=line
241 failed, 9 passed in 11.60s

(same nine files) --collect-only
250 tests collected in 0.33s
```

## 3. Remaining gaps

- **G1, the sequencer's argv.** `p426_wave2.main(argv, *, ops, clock, sleep)` has named `ops` but no named argv. The pilot gate, the speed-valid verdict, the pair rule, the watcher-death poll, `OVERRUN_PAUSED`, PAUSE, resume and the voided pair on restart are all untested. The unmocked production-topology test needs the same.
- **G2, the A4 anon check.** The ruling puts the 3 `anon:*` requests in `gate.json`, but `a4_window_problems(lines, a4_receipt)` has no `gate.json` parameter. The anon check is therefore untested, and the chain's location for `gate.json` is unnamed; my fake writes it to the gate's default, `$STACK_WORKDIR/c102a/gate.json`.
- **G3, the pair comparison inside the chain.** The flag that hands the chain the first leg's receipt path (§6.5) is still unnamed, so "pair comparison before item one" is tested only through `pair_problems`.
- **G4, the after-load busy census.** It has no seam. I used the existing `start_state()["busy"]` for the entry census only; "owned vs foreign after load" is untested.
- **G5, the ledger in `chain.json`.** Its key is unnamed, so I assert `schedule_sha256` and the invocation order only. Tamper tests for a reordered, missing or duplicated slot are not written.
- **G6, how the chain gets the pins and the expected worker argv.** It has to read `pins.json` and build the expected argv itself. My fakes copy the fork's `pins.json` to `<WT>/src/mlx-vlm/dev/p369_phase2/` and return mlx-serve's own argv. If the chain reads either from somewhere else, the positive legs would fail for fixture reasons.
- **G7, the operator email.** Wave 1's `Scrub` carries no email, so the operator-email refusal is untested.
- **G8, `RECORD` mutation.** The "mutated installed file" refusal now lives in `ChainOps.interpreter_inventory`, which takes a real pid. It is untested; testing it means hashing a real interpreter's `site-packages`.
- **Environment note.** The bench venv's `mlx_serve` is installed from the operator's main checkout, not this copy. My argv fixture therefore follows that tree.

## 4. Possible errors or contradictions in v3.2 + §16.4

1. **§4.3 vs §16.2.** The A4 window must match `gate.json` for the anon requests, but `a4_window_problems`' signature can't receive it.
2. **§6.3 wording.** "ON = OFF + exactly the three flags" reads as an append. mlx-serve inserts `--mtp-verify-scan joint_v1` mid-argv, before `--draft-kind` / `--draft-model`. My tests compare as a multiset with OFF's order preserved; the spec should say so.
3. **§16.1.** The rehearsal manifest must now carry two commits that "differ by exactly the restore diff". R1's ON side is a throwaway commit, so whether its diff must equal the P426 plan's §11 restore exactly is unstated.
4. **§1 / §16.4.** `--hmac-fd` is "absent in `--rehearsal`, where a fresh key is drawn", but R1 is a positive *pair* whose pair gate must pass. Two chains that each draw their own key give different HMACs for the same credential, so R1's pair gate can't pass on credentials.
