## Delivery 1b report: frozen tests revised for spec v3.2

Every s0 test passes on the baseline (32/32). Across s1–s9, 196 tests fail and 9 pass. All 9 passes are invariants that hold on the base commit. Every failure is the missing interface or the old behaviour, never a fixture error.

Chain-level `--p426` runs are still not covered (gap G1). The remaining gaps, and the points where v3.2 looks wrong, are in sections 3 and 4.

The working tree has only my 11 untracked test files, plus the designer's v3.2 change to `docs/specs/p426-b2-tg1-wave2.md`.

## 1. Per file

Classes: FIX = reproduces a failure the spec fixes, INV = preserves an invariant, NEW = new behaviour. Unless a row says P, the baseline outcome is F.

### `b2_frozen_support.py` (fixtures)

Added for v3.2:
- **Records (§16):** the self-hash recipe (`canonical_bytes`, `self_hashed`), `write_record` (exclusive create), and the three record builders: rehearsal manifest, v8 base, timeout amendment.
- **Rows and windows:** `golden_row` (the real P371 kill and inactivity rows), `summary`, `window` and `counters_after`.
- **Receipts:** `abort_manifest` (the real `arm_runner` stamp plus the §16.1 keys); `a4_receipt` (the `a4_v2_latest.json` shape, `session_pinning_gate.py:154-206`); `arm_receipt_doc` (the §16.1 receipt shape).
- **Legs:** `not_started_leg_root` (an attempt root `<leg>.a<n>`) and `occurrence`.
- **FakeOps seams:** `ops.repo`, `server_log_path()`, `read_log(path, start, end)`.
- **Harvest runner:** now uses the `wave2 --leg-root --main-root --evidence-stage` CLI.
- **Refusal harness:** always injects FakeOps, so a refusal that doesn't fire can never reach a real router.

Removed: `minimal_leg_root`.

### `test_b2_frozen_s0_support.py`: 32 tests, all INV, all pass

These are the 24 from delivery 1 plus 8 that validate the new fixtures:
- the record self-hash recipe, the amendment's link to v8 and exclusive create;
- the golden kill and inactivity row fields;
- the window and counter builders against `p426_leg.log_problems`;
- the FakeOps log seams;
- the receipt pair (ON = OFF plus the §6.3 delta, both pass `p426_leg.model_argv_problems`);
- the abort-manifest fixture as a superset of the real probe's stamp;
- the A4 receipt shape;
- the occurrence builder.

### `test_b2_frozen_s1_cli.py`: 46 tests, all F

| Test | Class | First failure line |
|---|---|---|
| retired flags ×4, `C147_OVERLAY`, missing required flags ×7, out-root exists, >1 model, `--inject` without `--rehearsal` ×2 | NEW | `:55 AssertionError: usage: …` (no `REFUSED:` line; the baseline's argparse rejects the new flags) |
| wrong record kind ×5, bad self-hash, missing record file, amendment ≠ its sibling v8 | NEW | same |
| P426 ChainConfig is its own flat config | NEW | `argparse SystemExit: 2` |
| `--models` required ×2 | FIX | `:55 AssertionError: …WATCH… pred=244s…` (the baseline ran the chain) |
| duplicate or empty `--models` ×4; unknown model | NEW | `:55` / `SystemExit: 2` |
| generic schedule with 1, 2, 3 models | NEW | `SystemExit: 2` |
| P223, M63 and pilot goldens; ChainConfig static fields; M63 family | INV | `SystemExit: 2` | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| registry served verbatim | FIX | `SystemExit: 2` |
| `--predictor` is an assertion ×4 | NEW | `:55` (no `REFUSED:`) |
| `generic_pred_s` = 250 recorded in `chain.json` | NEW | `SystemExit: 2` |
| WATCH shows `pred=250s` before a pilot mean (not the M59 table's 244 s) | FIX | `SystemExit: 2` |

### `test_b2_frozen_s2_probe.py`: 13 tests, 4 P / 9 F

| Test | Class | Baseline |
|---|---|---|
| `TG1_P426_EVIDENCE` | NEW | `AttributeError: … no attribute 'TG1_P426_EVIDENCE'` |
| `--evidence p426` selects the policy and the barrier | NEW | `:37 assert 2 == 0` |
| policy not in the probe identity | INV | `:60 assert 2 == 0` |
| P426 arm returns the cause ×4 | NEW | `TypeError: … unexpected keyword argument 'p426'` |
| abort manifest carries the §16.1 keys (`session_id == "ses_test"`, `in_flight_message_id`, termination, `gate.request_usage`) ×2 | NEW | `:89 no manifest: the probe refused before item one (rc 2)` |
| `TG1_EVIDENCE` unchanged; no flag means the tg1 policy; tg1 / m64 cause rules; tg1 abort shape | INV | P |

### `test_b2_frozen_s3_core.py`: 8 tests, 2 P / 6 F

| Test | Class | Baseline |
|---|---|---|
| `invalidate` in all three disposition vocabularies | NEW | `assert ('invalidate' in (…))` |
| `from_dict` round trip; both hooks may return `invalidate` | NEW | `ValueError: disposition kind must be one of …` |
| `p426_continue` is a third transport policy | NEW | `:74 assert {…} == {…'p426_continue'}` |
| `slot_file` mapping; `slot_file` keeps slots distinct | NEW | `AttributeError: … no attribute 'slot_file'` |
| legacy hooks unchanged; legacy `HookInfrastructureError` | INV | P |

### `test_b2_frozen_s4_reconcile.py`: 54 tests, all F

All fail with `:22 ImportError: cannot import name 'p426_reconcile' from 'bench'`. Classes are NEW for green cases and FIX for red ones. They cover:

| Area | Tests |
|---|---|
| `parse_log` | kinds, fields, byte offsets; drafter counters |
| `reconcile_item`, green cases | completed; kill at a boundary; kill in flight, server failed; kill, `completed_unaccounted`; `client_inactivity` |
| `reconcile_item`, red cases | count, tokens, prompt, order, session, backend, overlap, start before the previous terminal line, worker delta ×5, a failed line on a completed item, a failed line not last, another error, two failed lines, kill count ≠ gate, an unparseable line |
| `reconcile_dnf` | boundary, in flight failed, `completed_unaccounted` (green); missing completed line, wrong session, two unaccounted lines (red) |
| `engagement_problems` | ON good; ON bad ×7 (missing, `draft_n=0`, rounds 0, accepted > proposed, kind ≠ mtp, non-integer ×2); 1-token exemption; OFF present (red); OFF absent |
| `decode_time` | the §4.1 computation, 0 when no rate |
| `decode_rate` | with 0- and 1-token requests; `None` when ΔD = 0 |
| `settle` | settles (2 s polls); a start without its terminal line; in-flight never drains |
| `a4_window_problems` | match; mismatch ×4 |
| item report | the §16.1 request and total fields |

### `test_b2_frozen_s5_receipt.py`: 39 tests, all F

All fail with `:19 ImportError: … 'p426_secrets'` (24) or `:24 … 'p426_receipt'` (15). All NEW except the pair-gate refusals (FIX). They cover:
- **Classifier:** `is_credential_key` (8 yes, 5 no).
- **Credential values:** come from the token files, the config and the environment, skipping placeholders and values under 12 characters; absent files are fine; an unreadable file raises without the value.
- **Scans:** `scan` finds each of the 7 formats and the finding never carries the value; `TOKENIZERS_PARALLELISM=false` and a `1`-valued key never match; `exact_hits` finds a 40-character token.
- **Pair gate (`pair_problems`):** an allowed-only pair passes; volatile keys pass; 8 other differences refuse; an inventory difference refuses; the frozen allowed list passes; the HMAC is never echoed.
- **Dossier (`write_dossier`):** self-hashed and names its two attempts; immutable.

### `test_b2_frozen_s6_watch.py`: 4 tests, 1 P / 3 F

| Test | Class | Baseline |
|---|---|---|
| P469: the WATCH line reads `1/2` | FIX | `SystemExit: 2` |
| JSON tick lines, then `exit_state`, in `<out-root>/watch.jsonl` | NEW | `SystemExit: 2` |
| the power reading comes only from `power=` | NEW | `SystemExit: 2` |
| the legacy watcher argv | INV | P |

### `test_b2_frozen_s7_locks.py`: 5 tests, unchanged from delivery 1, all NEW, all F

| Test | First failure line |
|---|---|
| gate refuses while `SEQUENCER.lock` / `LEG.lock` is held ×2 | `:22 assert (GateReached() == 1)` |
| gate holds `gate/RUNNING` while it works | `:29 assert (True and False is True)` |
| acquisition is serialized by the arbiter | `:40 assert True is False` |
| a second gate refuses while `gate/RUNNING` is held | `:50 assert (GateReached() == 1)` |

### `test_b2_frozen_s8_freeze.py`: 15 tests, all NEW, all F

12 fail with `:20 ImportError: … 'p426_wave2'` and 3 with `:25 … 'p426_freeze'`. They cover:
- `leg_argv` for legs 1–8 (common flags taken from v8, mode tokens, out-root `<leg>.a<n>`, campaign core = the arm's commit);
- one out-root per attempt;
- `deadline_s`, T = 1.5 × Σ n·w + 1800 s;
- `makeup_groups`: order and duplicates; each session keeps its own seed;
- `freeze rehearsal`: writes the self-hashed manifest once, then a second run gets `REFUSED` rc 2;
- `amend` refuses a v8 base with a bad self-hash; `v8` refuses a rehearsal manifest of the wrong kind.

### `test_b2_frozen_s9_harvest.py`: 18 tests, 2 P / 16 F

All F tests fail on assertions about absent `REFUSED:` / `HARVEST.json`, because the baseline module has no `wave2` entry and exits 0 silently. First failure lines are `:48 AssertionError`, `:67 assert (None is not None)`, `:80 the first harvest published no HARVEST.json`, `:120`, and `:175 no HARVEST.json published`.

| Test | Class | Baseline |
|---|---|---|
| a NOT_STARTED attempt yields a self-hashed `HARVEST.json` (`leg.json` → main, `RUNLOG.md` → evidence) | NEW | F |
| a verified destination is done and idempotent | NEW | F |
| an unmatched file fails | NEW | F |
| a symlink outside a final tree fails, never followed | NEW | F |
| a symlink inside a final tree is excluded as `symlink`, not a failure | NEW | F |
| an exact secret quarantines its file ×4 sources | NEW | F |
| a credential format quarantines its file ×6 | NEW | F |
| placeholders and the allowlist never quarantine (rc 0) | NEW | F |
| an unreadable token file refuses | NEW | F |
| the leg root is never modified | INV | P |
| the Wave-1 entry points are kept | INV | P |

## 2. Commands and summary lines (verbatim)

```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py
32 passed in 18.94s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s1_cli.py bench/tests/test_b2_frozen_s2_probe.py bench/tests/test_b2_frozen_s3_core.py bench/tests/test_b2_frozen_s4_reconcile.py bench/tests/test_b2_frozen_s5_receipt.py bench/tests/test_b2_frozen_s6_watch.py bench/tests/test_b2_frozen_s7_locks.py bench/tests/test_b2_frozen_s8_freeze.py bench/tests/test_b2_frozen_s9_harvest.py -rA --tb=line
196 failed, 9 passed in 13.92s
```

Before the final run I found 3 tests that passed on the baseline for the wrong reason:
- s4 unparseable-line: a broad `except` swallowed the module's `ImportError`;
- s5 unreadable-secret-file: `pytest.raises(Exception)` caught the same `ImportError`;
- s5 receipt fixture check: it only checked the fixture.

I fixed the first two and removed the third.

## 3. Remaining gaps

- **G1, chain-level `--p426` runs: still blocked, and this is the biggest hole.** The entry checkpoint re-verifies the worktree's HEAD, a clean `git status`, the gitlinks, `--print-identity`, `LAST_LEG_END`, the locks and power (§3). §16.2 names no seam for the worktree's git state or `LAST_LEG_END`. So no hermetic positive leg is possible, and these tests are still owed:
  - ready record before `.go`;
  - `invalidate` at ready / done through `P426Hooks`;
  - DNF then the remaining items in order; the third DNF is systemic; a changed worker with a DNF stamp is systemic;
  - the ledger and `check_realized`; s2 Go first at `--items`;
  - the chain passes `--evidence p426`, and refuses a manifest without it;
  - pair comparison before item one; busy census;
  - the chain side of the locks and the gate-vs-chain race; a spawned child holds no lock;
  - the production-topology test.

  I recommend adding one seam, e.g. `ChainOps.worktree_state() -> {head, clean, gitlinks}` and `ChainOps.last_leg_end()`.
- **G2:** the keys of `P426Hooks`' `context` argument are unnamed, so the hooks aren't tested directly.
- **G3:** `arm_receipt` doesn't say where the router / worker / probe pids and argv come from, or how the HMAC pipe is passed, so it isn't tested.
- **G4:** the spelling of `engagement_problems(arm)` is open. I used `"on"` / `"off"` (the Wave-1 `p426_leg` convention), not `"mtp"`.
- **G5, `p426_reconcile` input shapes (I chose the closest named form):**
  - `before` / `after` and `decode_time`'s snapshot: I pass the `/metrics` summary dict, as the ready record stores it;
  - `settle`'s `read_log`: I pass a callable taking any arguments that returns bytes;
  - its `cursor`: I pass the ready record's `log_cursor` dict;
  - `parse_log` on a torn line: raise or not ok are both accepted;
  - `fields` values may be strings or ints.
- **G6:** where `gate.request_usage` sits is open. I read it from `transport_abort.gate`, falling back to the top level.
- **G7, s8 shapes:**
  - `leg_argv`'s `worktrees`: assumed `{"off": …, "on": …}`;
  - `deadline_s`'s `langs`: assumed `{lang: n}`;
  - `makeup_groups` output: assumed keys `session` / `seed` / `language` / `items`;
  - `p426_freeze`'s `checks` contract and its `ops`: unnamed;
  - the rehearsal test assumes OFF and ON may name the same commit.
- **G8:** `bench_watch` with `--chain-json`: I still pass `--out`, pointing it at `<out-root>/watch.jsonl`. There are no tests yet for the speed-valid verdict, the pair rule, the watcher-death poll, `OVERRUN_PAUSED`, PAUSE, resume or the pilot gate (the sequencer's `main` ops are unnamed).
- **G9, harvest:**
  - the matching `HARVEST.json` entry is found by the end of its `source` path;
  - `SCRUB_MANIFEST.json` is still not on `main`, so the operator-email refusal and the P437 scrub source are untested, and my clean-leg tests assume the harvest doesn't require that file;
  - `<WT>/.env` has no parameter in `credential_values`;
  - where foreign emails are listed is unnamed.
- **G10:** the committed rehearsal row + log-slice pairing fixture still doesn't exist (P499 on S′ is future work).
- **G11:** s0's legacy-chain checks run without `--models`, so they hold only on the baseline. That fits §16.3's "a record, not part of the committed suite".

## 4. Possible errors or contradictions in v3.2

1. **The A4 window (§4.3).** It requires the window's "3 `anon:*` requests + its own 4-request `ses_*` session" to equal the A4 receipt. The receipt the chain binds (`a4_v2_latest.json`) holds only the `ses_*` turns; the anon requests are A6's and appear only in `gate.json`.
2. **Two DNF record locations.** §4.5 puts the DNF record at `items/<slot>.dnf.json`, while §16.1 puts the `p426_dnf` sidecar at `<out-root>/<session>/p426_dnf/<slot_file>.json`. It's unclear whether these are one record or two.
3. **The amendment link (§16.1).** `v8_base_sha256` is "the sha256 of `v8_base.json`", which could mean the file's bytes or the record's self-hash field; the two always differ. I used the file bytes.
4. **Harvest destination name.** §11.2 says `benchmark/results/p426/wave2/<leg>/`, while §1 (attempts) says `<leg>.a<n>/`. I used `<leg>.a<n>`.
5. **Hashing secrets.** §11.3 says secret values are never "hashed into any output", while §6.4 records an HMAC of each credential value in `receipt.json`. With the key discarded this is safe in practice, but the two sentences contradict.
6. **§3 vs §16.** §3's entry re-verification needs seams that §16 doesn't name, despite §16's stated aim of testability "blind" (see G1).
