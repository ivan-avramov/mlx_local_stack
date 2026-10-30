The s4 reconciliation core is mostly sound, but I recommend **fix then merge**. Two defects mean that in a real run every DNF would be treated as systemic and every completed item would be classified as a probe kill. On top of that, three of part a's s1–s3 findings are still open.

## 1. Run results (copy `eval-s4` = baseline + s1–s4 + `frozen4`)

| Command | Result |
|---|---|
| `../bin/run_candidate_s4_tests.sh bench/tests/test_b2_frozen_s1_cli.py bench/tests/test_b2_frozen_s2_probe.py bench/tests/test_b2_frozen_s3_core.py bench/tests/test_b2_frozen_s4_reconcile.py --tb=no -rf` | `60 failed, 80 passed in 44.20s` (s1: 39 failed; s2, s3: 0 failed; s4: 21 failed) |
| `../bin/run_candidate_s4_tests.sh bench/tests/test_b2_frozen_add_a4.py bench/tests/test_b2_frozen_add_ledger.py` | `10 failed in 2.39s` |
| `../bin/run_candidate_s4_tests.sh bench/tests/test_b2_s4_reconcile.py bench/tests/test_b2_s1_cli.py bench/tests/test_c147_chain_runner.py bench/tests/test_p371_chain_hooks.py` | `258 passed in 68.24s` (the candidate's own tests, plus the legacy tests it touched) |

I didn't run `add_argv` and `add_census`, because they test s7 behaviour (the entry checks and the busy census). The other `add_` files need s5 or later.

### Classification of every failure

**s1 (39), all from s1 code; the s4 diff doesn't touch `parse_args`**

| Tests | Class | Evidence |
|---|---|---|
| retired flags ×4, missing flag ×7, `--models` required ×2, duplicates/empty ×4, more than one model ×1 (18) | (a), inherited from s1 | The chain refuses with exit 2 and names the flag, but prints argparse's `__main__.py: error: --p426 refuses --smoke` and similar, never `REFUSED: <reason>`. That format is the §16 preamble (spec lines 445–446), which is not a [d2] addition. |
| `rehearsal_injections_refuse_without_rehearsal` ×2, `wrong_kind[mode4-v8]` (3) | (a), inherited | `unrecognized arguments: --inject …` / `--rehearsal`. §16.1 says `--frozen-record` with `--rehearsal` takes a `p426_rehearsal` record (s1). |
| `wrong_kind` ×4, `bad_self_hash`, `missing_record_file`, `amendment…sibling`, `leg_dot_a_n` ×4 (11) | **(c) my test defect** | `CHAIN ABORT: --campaign-core 'campaign-p426' does not resolve to a commit`. My s1 fixture (`test_b2_frozen_s1_cli.py:20, 32`) passes an unresolvable tag and no fake `campaign=`, so the baseline's `campaign_core._resolve` (campaign_core.py:87–91) aborts first. These 11 can't observe the record check (part a's R2) or the `<leg>.a<n>` rule (§16.1 [d2], which would be (b)). |
| `refuses_an_out_root_that_exists` | (a), low | Prints `REFUSED: --p426 out-root tg1-p426-off-pilot.a1 exists`; the flag `--out-root` isn't named as such. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| `m63_argv…golden_item_order`, `predictor_mtp…complete_entry`, `predictor…served_entry` ×2, `model…not_an_entry…` (5) | (a) = part a's **R5, unfixed** | The registry with the C177 keys is passed as `ops.overlay`, yet the candidate reports `lacks ['draft_kind', 'draft_model', 'mtp_verify_scan']`, and the off-predictor and unknown-model cases run instead of refusing. It reads the repo registry, not `ChainOps.overlay` (§3, spec line 112). |
| `generic_prediction_is_recorded_in_chain_json` | (a), inherited | `assert 250 in []`: `generic_pred_s` isn't in `chain.json`. |

**s4 (21)**

| Tests | Class | Evidence |
|---|---|---|
| `normally_completed_item_reconciles_positionally`, `failed_line_on_a_normally_completed_item_is_off_table` | **(a) high** | Case `kill_boundary` / `kill_inflight_failed` on a normal row. Cause: `killed = … or "kill" in str(row.get("termination")).lower()` (diff line 715–716). The real row's `termination` dict always has the keys `in_flight_at_kill` and `killed` (fixture `c147_real_tg1_pilot_row.json`). |
| `dnf_at_a_request_boundary`, `dnf…in_flight…failed`, `dnf…completed_unaccounted` | **(a) high** | `len(request_usage)=0`. `reconcile_dnf` reads `abort_manifest["gate"]` and `transport_abort.in_flight_message_id` (diff line 729–732). s2 as built, and §16.1 line 476, put `gate` and `in_flight.message_id` inside `transport_abort`. |
| `log_field_values_are_strings_as_logged` | (b) | `99 == '99'`; strings as logged are in §16.4 (spec line 540). |
| A4 ×7 | (b), with an (a) part | 2-argument `a4_window_problems(lines, a4_receipt)` against the 3-argument [o4] signature (§16.2 line 493). Even within 2 arguments it only counts requests; §4.3 (line 167) requires equality with `gate.json` and with the receipt. |
| `ready_hook…accepts`, `done_hook…accepts`, `done_hook_invalidates…server_count`, `…on_item_without_drafter_counters`, `done_hook_accepts_an_engaged_on_item`, `unreadable_metrics…hook_infrastructure_error` (6) | **(c) my test defect** | The disposition is `invalidate('log_bounds.json is missing or unreadable')`. `P426Hooks` checks `<out_root>/log_bounds.json`, which the chain writes before the router (§4.2). My hook fixture (`s4:432–457`, `b2_frozen_support.make_ops`) never writes it. Once fixed, the done tests still hit the kill misclassification above (they assert `case == "completed"`). |
| `hooks_called_without_a_context…` ×2 | (b) | `context or {}` leads to `invalidate`, not `HookInfrastructureError` (§16.7). |

**add_ (10)**

| Tests | Class | Evidence |
|---|---|---|
| add_a4 ×7 | (b), plus the (a) part above | Same 2-argument signature. |
| add_ledger `valid_leg…`, `invalidated_item…` | (b), arguably (d) | `p426_invalid` is a single dict, or `None` on a clean leg; §16.5 line 565–566 says "`p426_dnf` and `p426_invalid` likewise", i.e. list-shaped like the ledger. The invalidation itself is correct: stage `done`, the skewed item, reason `pairing … tokens differ`. |
| add_ledger `dnf_is_ledgered…` | (d) | Expected rc 0, got 2. The chain log isn't printed, so I couldn't extract the cause. The most likely cause is the `reconcile_dnf` manifest-shape defect: my fake probe writes the s2 shape, so `request_usage` would be empty and the "section 4.3 DNF row" check would fail. Not confirmed. |

### Part a's s1–s3 findings against s4
- **Fixed:**
  - R1 (`tg1_config` gives `p426_continue` under `--p426`; diff line 1689). All s3 tests pass.
  - The missing `chain_rows.slot_file` (diff 216–218).
- **Passing now because I fixed my tests in 1f, not the candidate:** the s2 client-abort fixture and the s3 config construction.
- **Still open:**
  - R5, the served registry is not `ChainOps.overlay`: 5 s1 failures.
  - R3, the DNF limit is still counted per `(session, lang, arm)`: diff context line 142.
  - R4, router identity: see P20.
  - R2 (`--frozen-record`) can't be observed, because my campaign fixture defect masks it.

## 2. Review of the s4 diff

| Id | File:line (diff) | Severity | Finding and failure scenario |
|---|---|---|---|
| P16 | `p426_reconcile.py` (diff 715–716) | High | **Kill detection matches dict key names.** Every real row has the `termination` keys `in_flight_at_kill` and `killed`, so every completed item is reconciled as `kill_*`. Consequences: every item record's `case` is wrong, and a normally completed item with a trailing `stream_closed` failed line is accepted (kill row 3), where §4.3 says systemic. Decide from `gate.requests_completed_at_kill is not None`, `nonconv_kind`, or a non-empty `termination.killed` / non-null `in_flight_at_kill`. |
| P17 | `p426_reconcile.py` (diff 726–732) | High | **The DNF reconciliation reads the wrong manifest keys** (`gate` and `in_flight_message_id` at the top level). With s2's real manifest, `request_usage` is always `[]` and `inflight_possible` is always False. Every DNF fails `boundary_count`, `p426_dnf_eligible` returns a reason, and the chain aborts: a single transport DNF kills the leg. The candidate's own fake probe never writes this manifest shape, which is why its own tests pass. |
| P18 | `chain_core.py` (diff 26–34) | Medium | **The settle bound never comes from the frozen record.** It uses `getattr(args, "settle_bound_s")` (no such argument) or 900 s. The v8 base and the timeout amendment raise the bound (§4.2), so an item whose long prefill settles after 900 s is falsely invalidated. |
| P19 | `p426_reconcile.py` (diff 736–755); chain | Medium | **A4 window:** it only counts `anon:*` and `ses_*` requests and never compares them with `gate.json` or the receipt (§4.3). No caller in the chain runs it "per load, before the first item", so the per-load A4 check is absent. |
| P20 | `p426_hooks.py` (diff 326–336) | Medium | **Router identity:** `_identity_problems` uses `ops.router_ok()`, which compares the config sha, not the owned `{pid, start}`. `router_identity()` is only recorded in the ready record. A restarted router with the same config passes. Part a's R4 remains. |
| P21 | `p426_hooks.py` (diff 396–399) | Medium | **No item record when the window or identity check fails.** `after_attempt` returns `invalidate` without writing `items/<slot>.json`. §4.5 says the record is written before the barrier answer, so the evidence of the failure is lost. |
| P22 | `p426_hooks.py` (diff 385) | Low / unclear | `ready_sha256` is the ready record's self-hash, but the frozen test expects the file's sha256 (§4.5: "the ready record's sha256"; the spec doesn't say which). | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P23 | `chain_core.py` (diff 170–176) | Low | **`item_record` is a dict `{path, sha256}`.** §16.1 says `item_record` names `items/<slot_file>.dnf.json`. Expect the s7 test to fail on this. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P24 | `chain_core.py` (diff 46, 96–101) | Low | **`log_bounds.json` paths are absolute** (against [d2]'s portable records, so the harvest's byte-identity check refuses them). It is also not finalized when `stop_stack()` raises: `close` is inside the `try`, before the `finally`. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P25 | `p426_hooks.py` (diff 339–341) | Low | (b) `context=None` is coerced to `{}` (§16.7 requires `HookInfrastructureError`). | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P26 | `p426_reconcile.py` (diff 506–537) | Low | (b) Fields are converted to int and float, against §16.4 "strings as logged". | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P27 | `p426_reconcile.py` (diff 698–700) | Cosmetic | The `pairing` check's detail says "positional pairing fails at position 3" even when it passes, so item records carry a misleading string. |
| P28 | `test_c147_chain_runner.py` (diff 1531) | Info | The legacy `FakeOps` default metrics now come from the fake probe's counter file. The legacy tests run still pass (258 passed above). |

Sound as built:
- The started / completed / failed parsing and the trailing-partial-line rule.
- The serial check, the worker deltas and `|S| = |C| + |F|`.
- The `stream_closed` last-line rule and the `completed_unaccounted` branch structure.
- The 2 s settle poll, with not-settled treated as systemic.
- The ON / OFF engagement rule (§4.4).
- Exclusive, self-hashed ready and item records.
- `log_bounds.json` exclusive-created before the router and checked on device / inode / truncation.
- `p426_continue` installs `P426Hooks` only in that mode.

## 3. Verdict for s4: fix then merge
1. **P16:** kill detection from the structured fields, not a substring of `termination`.
2. **P17:** read the s2 manifest shape (`transport_abort.gate.request_usage`, `transport_abort.in_flight.message_id`, `transport_abort.session_id`), and add a test using a real s2-written manifest.
3. **P18:** take the settle bound from the frozen record (amendment, else v8 base).
4. **P19:** the 3-argument `a4_window_problems` with equality against `gate.json` and the receipt, wired per load before the first item.
5. **P20:** compare the router's `{pid, start}` with the owned identity.
6. **P21:** write the item record on every `done` outcome.
7. Before merge, the (b) items: `context=None` raises (P25), fields stay strings (P26), `p426_invalid` is a list, `item_record` is a path string (P23), `log_bounds.json` is portable (P24).
8. The inherited s1 items belong to the s1 slice: `REFUSED:` for argparse refusals, `--rehearsal` / `--inject`, R5 overlay, `generic_pred_s`, R3.

Two of my own test defects affect this run: **17 failures are class (c), mine.** Both are in frozen files, which I haven't edited:
- **s1:** an unresolvable `--campaign-core` with no fake campaign. This masks 11 tests, including R2 and the `<leg>.a<n>` rule.
- **s4:** the hook fixture lacks the `log_bounds.json` the chain guarantees. This masks 6 hook tests.

They should be fixed in a re-freeze before the s1 and s4 fixes are judged against these files.
