No `FAILED` or `ERROR` line falls outside the `test_b2_frozen_*` files. All 281 failures are in my frozen and `add_` test files (s0 included); the candidate's own tests and the existing suite pass.

## Run and review of the s1–s3 candidate

**Verdict: fix, then merge as the s1–s3 reference.** The probe edits, the hook vocabulary, C221 for every tg1 mode and the legacy goldens are sound. But `--p426` never selects `p426_continue`, so all of the candidate's §5 DNF / `invalidate` / ledger code is unreachable from the entry. I also found three correctness defects. The candidate breaks no existing test.

### 1. Frozen s1–s3 on the candidate

`../bin/run_candidate_tests.sh bench/tests/test_b2_frozen_s1_cli.py bench/tests/test_b2_frozen_s2_probe.py bench/tests/test_b2_frozen_s3_core.py -rA --tb=line` → `42 failed, 26 passed in 39.29s`.

No `add_` test can pass on s1–s3 alone (each needs an s4+ module or the s5/s7 wiring), so I didn't run them separately; the full-suite run includes them.

The 26 passes are, by file:
- **s1:** the generic schedule with 1, 2 and 3 models; the P223 and pilot goldens with `--models`; the static ChainConfig fields; the registry served verbatim; `--predictor mtp` refused on a bare and on a partial entry; the WATCH prediction at 250 s.
- **s2:** everything except the two abort-manifest tests.
- **s3:** the `invalidate` vocabulary, its round trip, both hooks returning it, and the two legacy-hook invariants.

Classification of every failure: (a) candidate defect, (b) a §16 / v3.2 rule not built yet, (c) test defect, (d) unclear.

| # | Failing test(s) | Class | Evidence |
|---|---|---|---|
| 1–4 | `p426_refuses_each_retired_flag` ×4 | (b) | The candidate rejects `--hmac-fd` (§16.4) before reaching the check. The refusal itself exists (`run_tg1_chain.py` `check_p426`, diff 2647–2650), but through `ap.error`, not `REFUSED:` (§16). |
| 5 | `refuses_the_c147_overlay_environment_override` | (b) | Stops at `--hmac-fd`; the refusal is built (diff 2734, `REFUSED:` format). |
| 6 | `missing_required_flag[--models]` | (b) | Argparse "required" error: refuses correctly, wrong format (§16). |
| 7–12 | `missing_required_flag` (6 other flags) | (b) | `--hmac-fd` first; the refusals are built (diff 2651–2655, `ap.error`). |
| 13, 14 | out-root exists; more than one model | (b) | `--hmac-fd` first; built (diff 2736, 2656). |
| 15, 16 | `rehearsal_injections_refuse_without_rehearsal` ×2 | (b) / (d) | `--hmac-fd` first. `--inject` / `--rehearsal` don't exist at all. These are §1 R2/R3 flags, and it's unclear whether they belong to s1 or s8. |
| 17–24 | wrong record kind ×5, bad self-hash, missing record file, amendment ≠ sibling v8 | (b) | `--frozen-record` is parsed but never read (diff 2675, 2653): no kind, self-hash or existence check. The kinds and recipe are §16.1. One case stops at the unknown `--rehearsal`. |
| 25 | `the_p426_chain_config_is_its_own_flat_config` | (b) + (a) | Fails first on `--hmac-fd`, but the assertion `transport_policy == "p426_continue"` would fail too: `tg1_config` keeps `abort_restart` for `tg1-p426` (diff 2605; the candidate's own test, diff 1248, says "p426_continue is a later slice"). |
| 26–31 | `--models` required ×2; duplicate / empty names ×4 | (b) | The refusals fire (diff 2635–2640, argparse "required"), in `usage: … error:` format, not `REFUSED:`. |
| 32 | `a_model_that_is_not_an_entry_of_the_served_registry_refuses` | (a) | The served registry is read from `main(registry=)`, else `ops.registry`, else `REPO/main_models.yaml` (diff 2715–2718), never from `ChainOps.overlay` (§3). It read the real committed registry, which lists that model, so the chain ran. |
| 33, 36 | M63 golden with `--models`; `mtp` with a complete entry | (a) | Same root cause: refused against the real registry, where the C177 keys are commented out. |
| 34, 35 | `predictor_is_an_assertion[off-on1-partial1]`, `[off-on3-partial3]` | (a) | Same root cause: the real registry is OFF, so nothing is refused. The two `mtp` cases that passed passed for the same coincidental reason. |
| 37 | `the_generic_prediction_is_recorded_in_chain_json` | (b) | The value 250 is recorded, but as `schedule.params.pred_default_s` (diff 2592), not `generic_pred_s` (v3.2 §2). |
| 38, 39 | s2 `a_p426_client_abort_manifest_carries_…` ×2 | (c) | My fixture's fault. The `drop` / `refuse` events start with a `not json` line, so the probe aborts with "malformed complete event line" before the transport error, and no cause can be stamped. My s0 check missed this. The candidate's stamp code (`arm_runner.py`, diff 71–78) is correct by reading, but this test can't show it. |
| 40 | s3 `p426_continue_is_a_third_transport_policy_and_the_others_stay` | (c) | The membership assertion passes. The test then builds a `tg1-p426` config by copying a legacy one, which the candidate's own invariant rejects ("exactly one model, `p426: true`", `run_config.py`, diff 774–777). The spec doesn't require such a config to be valid. |
| 41, 42 | s3 `slot_file` ×2 | (b) | `chain_rows.slot_file` is §16.1. |

### 2. Review findings

| ID | Severity | Location | Finding and failure scenario |
|---|---|---|---|
| R1 | High | `run_tg1_chain.py` `tg1_config` (diff 2595–2606); `chain_core.py` `p426` property (diff 163–165) | `--p426` selects `config_id="tg1-p426"` but keeps `transport_policy="abort_restart"`. Every P426 path is gated on `transport_policy == "p426_continue"`, so none runs: no `p426_continue` leg loop, no DNF records, no `invalidate` handling, no ledger, no manifest evidence-policy check (diff 560–567), and hook errors aren't systemic. **Scenario:** a `connection` abort on item 7 of `tg1-p426-off-s1` archives and reloads the whole load (the legacy path), not a DNF that continues on the same load (§5.2). And because the evidence-policy check is gated on the same flag, a manifest without `TG1_P426_EVIDENCE` is accepted. |
| R2 | High | `run_tg1_chain.py` `--frozen-record` (diff 2675) | The record is required but never opened. **Scenario:** a pilot leg given the rehearsal manifest, a v8 base with a bad self-hash, or a path that doesn't exist runs anyway. Legs 1–10 run with no record check (§1, §2, §16.1). |
| R3 | Medium | `chain_core.py` `handle_p426_incomplete` (diff 421–424) | The ">2 DNF in the leg" limit counts DNFs per (session, language, arm), not per leg. **Scenario:** an s1 leg (Python then Go) can collect 2 Python DNFs plus 2 Go DNFs and stay VALID, against §5.1. |
| R4 | Medium | `chain_core.py` `handle_p426_incomplete` / `p426_dnf_eligible` (diff 408–416, 392–401) | Only the worker's identity (pid + start) is checked. For the router it calls `router_ok()`, a liveness check, not the owned router's pid + start. **Scenario:** a router restarted by something else at the same port passes as "unchanged", and the abort is recorded as an item DNF instead of systemic (§5.2: identities first). |
| R5 | Medium | `run_tg1_chain.py` `served_registry` (diff 2715–2718) | With injected ops, the chain checks `ops.registry` or the real `REPO/main_models.yaml`, not the `ChainOps.overlay` it serves (§3). In production `make_ops` sets both to the same path, so there's no live divergence. But an injected-ops run reads the operator's real registry: a hermeticity leak, and the cause of 5 frozen failures plus 2 coincidental passes. |
| R6 | Low | `chain_core.py` DNF sidecar (diff 455) | Named `slot.replace("\|", "_")`, not `slot_file` (§16.1); `item_record` is `None` (s4 fills it). It must be renamed when s4 lands. |
| R7 | Low | `test_p371_baseline.py:614` (diff 2382–2390) | The legacy chain differential now drops the `ensure_overlay` call from the old golden before comparing. That's consistent with C221 (no overlay generation), but §2 asks for "its golden refreshed with old → new recorded"; this filters in test code instead of recording the change. |
| R8 | — | `arm_opencode.py`, `arm_runner.py`, `tg1_runner.py`, `run_tg1_probe.py` | Probe edits are correct by reading:<br>• `p426=True` only in tg1 mode;<br>• the cause stamp for `m64 or p426`;<br>• `report_gate_on_abort` extended;<br>• `request_usage`, `session_id` and `in_flight{in_flight, message_id, requests_started}` added only when `report_requests_on_abort`;<br>• the previous item's gate report cleared between items;<br>• defaults unchanged.<br>The tg1 invariant tests pass. |
| R9 | — | `chain_hooks.py` | `invalidate` is in all vocabularies, needs a reason, and has a factory. The context is passed only when given, so legacy `(slot)` / `(slot, done)` hooks keep working. `systemic=True` re-raises `HookInfrastructureError`. Correct. |
| R10 | — | `schedules.py` | The P426 order is `Random(seed).sample(sorted(pool), len(pool))`, with pilot / reload = its first 5 and s2 reversing the language order. Only P426 schedules gain the `p426` key, so the legacy schedule sha is unchanged. The P223 and pilot goldens pass. (The M63 golden fails only through R5.) |

### 3. Candidate full suite

`../bin/run_candidate_tests.sh` (no arguments):
`281 failed, 6938 passed, 12 skipped, 1 xfailed, 4 warnings in 2315.02s (0:38:35)`

A second identical run, to list non-frozen failures, gave `281 failed, 6938 passed, 12 skipped, 1 xfailed, 4 warnings in 2487.36s (0:41:27)`.

Of those 281 failures, none is outside `test_b2_frozen_*`: there are zero `FAILED` / `ERROR` lines elsewhere. So the candidate breaks nothing in the existing suite, and its own `test_b2_s1/s2/s3` tests pass.

My first attempt passed extra pytest flags, which replaced the runner's default paths and stopped at a collection error in `lcb_budget_test.py`. That was my invocation error, not a candidate failure.

### 4. Verdict: fix, then merge as the s1–s3 reference

Fixes needed before merging:
1. **R1:** set `transport_policy="p426_continue"` in `tg1_config` for `--p426`, so the §5 / §7 paths and the evidence-policy check are live from the entry.
2. **R3:** count DNFs per leg, not per (session, language, arm).
3. **R4:** check the owned router's pid + start at the incident, not just its liveness.
4. **R5:** check the served registry from `ChainOps.overlay`, keeping production's equality between the checked and served files.
5. **R2:** at minimum refuse a `--frozen-record` path that doesn't exist now. Kind and self-hash come with §16.1.

The §16 items go to the planned fix round: the `REFUSED:` format, `--hmac-fd`, record kinds and self-hash, `slot_file`, and `generic_pred_s`. Two things need a decision from the designer:
- whether `--rehearsal` / `--inject` belong to s1 or s8;
- R7: whether recording the golden change is required in s1.

Two of the 42 failures are my test defects; both are in the frozen set, so the designer decides on them:
- **s2 abort-manifest fixture:** the events must not start with a malformed line.
- **s3 `p426_continue` test:** it should take the policy from a real `--p426` config instead of copying a legacy one.
