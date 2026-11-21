I traced every finding through the call chains in candidate 2 (the working tree = baseline + candidate 1 + fix round 1). Here is the per-finding verdict, then the hazard / weight check, then anything else.

## Per-finding (B1–B16)

**B1 — resolved.** `verify_a8_kv(results_root, base_b8_sha256=None, draw_path=None)` at `p426_verify.py:2930`. When `None`, it derives the sha from `<results_root>/B8.json` and refuses on `OSError` (`:2947`); an explicit value is the CLI's seam (`main` passes `hashlib.sha256(text.encode()).hexdigest()` at `:3065`). Both call forms produce the same record (`test_b1_*`).

**B2 — resolved.** `_a8_inventory` at `:2435` replaces the three hand-rolled helpers (grep confirms `_a8_session_rows`/`_a8_harness_dnf`/`_a8_slots` are gone) and sits on `cr.load_slots(chain, path, check_unregistered=False)` (`:2447`), with `ChainRowsError → RefusalError` (C2). On top: unregistered rows file with content refuses, empty tolerated (`:2455`); slot of another session refuses (`:2458`); harness-DNF sidecar must be `sealed_ok` AND `== s.row` (`:2482`); transport DNF beside a row/harness DNF refuses (`:2490`); rule-9.3 "earlier attempts = range(k)" reason kept (`:2468`). `load_slots` re-hashes each rows file (`chain_rows._counted_rows:326`), so `test_b2_a_rows_file_changed_after_validation_refuses` fires through `load_slots`.

**B3 — resolved.** `discarded_runs(reader, att)` at `:2156` iterates `slot_attempts` with `disposition == "harness_fault"`, resolves the attempt's `invocation` → its manifest's `run_id` → membership in `seen_run_ids`, and returns `{(item, run)}`. Set on both loaders (`_kv_load_attempt:2290`, `_a8_load_attempt:2629`). `final_tree_reasons:2186` exempts only `(rid, other) in discarded` (`:2205`).

**B4 — resolved.** `A8_V8_IDENTITY` at `:2657` lists the 7 keys. `a8_v8_pin_reasons` (`:2674`, called once at `:2964`) checks `tg2_draw_sha256 == TG2_DRAW_SHA256 == file sha` and `tg2_universe_sha256 == TG2_UNIVERSE_SHA256`. `a8_v8_identity_reasons` (`:2689`, called at `:2794`) iterates `_kv_a7_manifests`, checks each key per manifest and `man["model"] == schedule.picks[0]`; rows' model checked at `:2701`. Each mismatch is one REASON.

**B5 — resolved (C1 deviation accepted, spec corrected).** `_a8_accounting` at `:2540` builds `marks = {slot_state, ledger, sidecar}` always, adds `row` when `"accounting_fault" in rows[iid]` and `chain_list` when `listed is not None`, refuses on `len(set(marks.values())) != 1` (`:2571`). Orphan sidecar and orphan list entry refuse (`:2586`). The shared validator `ph.accounting_problems` is run (`:2582`). Spec §9.4 wording corrected to "an item the chain records as an accounting fault … a row marker or `p426_accounting_faults` entry, where present, must agree too; … the runner never writes a row marker" (`docs/specs/m76-b4b2-a8-consumers.md` diff). `_a8_speed_invalid` at `p426_signals.py:1906` adds the accounting-fault tier (`:1913`). Per-session `tax` with accounting rows excluded at `:2069` (C5, within §7.2 projection).

**B6 — resolved.** `main` writes `B8.json` first via `write_atomic({args.out: text})` (`:3063`), then `verify_a8_kv` + `write_atomic` for `B8-A8.json` (`:3065`). A `RefusalError` from either is caught at `:3076`, returns `rc 2`; `B8.json` stays. `test_b6_b8_json_is_written_when_b8_a8_refuses` confirms.

**B7 — resolved.** `a8_utc_seconds` at `:2914` returns `float(t)` for finite non-negative numbers, parses ISO `Z`/offset strings as UTC via `datetime.fromisoformat(...).timestamp()` (tz-aware → epoch, naive → None). `_a8_latency` at `:2884` refuses a row whose `t` doesn't parse or whose `fresh_ms/repeat_ms/true_ms/threatlocker_cpu` are not finite, non-negative, non-bool (`:2903`). `p426_signals._a8_time:1933` delegates to it.

**B8 — resolved.** `B4B2_CHANGED_INPUTS` at `test_m76_b4b1_impl_golden_tg1.py:31` enumerates exactly 16 paths (2 arms × pilot L0, reload L0, s1/s2/s3 L0+L1), no wildcards. The allowance in `test_regen_or_compare` matches only these exact paths (`:239`); the assertion message now lists every diff.

**B9 — resolved.** `status = "complete" if all(by[s]["accepted"] is True for s in confirm) else "incomplete"` at `:2981`.

**B10 — resolved.** `a8_seed_reasons` at `:2712` checks `row.sampler_seed == rowschema.sample_seed(rid, 0, schedules.TG2_P426_LEGS[session][1])`, one REASON per attempt. Called at `:2794`. The reload seed mismatch is now a B8-A8 REASON (C2 of the report); `_a8_reload_control` returns "not computed" when reload is rejected (`p426_signals.py:1965`).

**B14 — resolved.** `STACK_REPO` at `:2991`; `check_b8_a8(rows_root, b8_a8, b8_sha256, repo_root)` at `:2994` iterates `(rows_root, inputs)` and `(repo_root, repo_inputs)`, refuses naming the input and its root (`:3008`). Callers: `p426_signals.py:1627` (`V.STACK_REPO`), `p426_panel.py:1867` (`kv_a8_context` passes `repo_root`), `p426_panel.py:2139` (`V.STACK_REPO`).

**B15 — resolved.** `a8_applies` at `:2411` returns `lever == "kv" and corpus == "tg2"` only. The arms check is a REASON in `verify_a8_kv:2956` (`v8.get("arms") != [ref, test]`).

**B16 — resolved.** `compute_kv` at `p426_signals.py:1630` refuses when `b8_a8` is given without a 64-hex `b8_a8_sha256`; no canonical-JSON fallback. The panel already bound the file sha (`_kv_b8_a8:1851`).

## Hazards

- **Real record refused (C1/C2):** none. C1 — the accounting agreement binds slot_state/ledger/sidecar always and the row marker / chain list only when present, so a real accounting fault (slot+ledger+sidecar+`p426_accounting_faults` list, no row marker) agrees. C2 — `load_slots` errors refuse (corrupted/contradictory), which a real record is not.
- **Contradictory accepted:** none — disagreement on any of the accounting marks, orphan sidecar/list, unregistered-rows-with-content, wrong-session slot, harness-DNF sidecar mismatch, transport-DNF-beside-row, v8 identity mismatch, seed mismatch, two-accepted-attempts, harness-fault-without-reason all refuse or reject.
- **Verdict from anywhere but `axis_verdict`:** none — `_kv_a8_section` calls `kv_axis_verdict("A8", …)` (`p426_signals.py:2029`), which delegates to `m76_rule.axis_verdict` (`:1348`). The sensitivity line uses the same call (`:2056`).
- **`B8.json` or no-A8 sheet changed:** none — `verify_all_kv` never adds A8 (`:2370-2379`); `compute_kv` adds the A8 section only `if b8_a8 is not None` (`:1718`). The committed `B8.json` and `SIGNALS*.md` byte-identity goldens are the frozen real-record tests, which pass.
- **Panel judging an unbound item:** none — `_a8_packet` refuses when the session is not a B8-A8-accepted confirmatory session or the (session, rid) is not a B8-A8-accepted key (`p426_panel.py:2028-2037`); `kv_panel_members` binds A8 FROZEN to `b8_a8_sha256` (`:2212`); `kv_export` builds A8 ctx via `kv_a8_context` which re-verifies B8-A8 (`:2139`).

## Heavier than intent

No. `_a8_inventory`, `_a8_accounting`, `discarded_runs`, `a8_v8_identity_reasons`, `a8_seed_reasons` are each one function at the granularity their finding requires; the C5 per-session `tax` is the §9.4 runaway-tax aggregate the spec names. The A7 `discarded_runs` computation (C8) is a no-op on real A7 legs (no harness faults).

## Anything else the diff breaks or leaves failing

- The 35 frozen-suite failures documented in the implementer's report §3 are fixture conflicts the test-writer's v2 still carries (the synthetic `World` v8 lacks the identity its manifests carry; `World.seed` is not `rowschema.sample_seed`; the `harness_fault` slot attempt names no invocation; `edit_row` rewrites without re-hashing). They are not defects of the fix — the fix correctly enforces the rules; the real harvested pilot pair passes (`test_m76_b4b2_fe_real.py` green). Delivery 3 amends the fixtures.
- The `f2b61127…` failures in `test_m76_b3_impl_golden_mtp.py` and `test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical` name a commit absent from this clone; pre-existing, not caused by the diff.

NOTHING OF SUBSTANCE
