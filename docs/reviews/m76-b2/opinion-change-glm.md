## Findings

I traced the certification binding (`qualify.py:1145-1185`, `1329-1446`), the tuple arm validation (`orchestrate.py:688-760`, `1645-1696`), the engagement/verdict path (`worker.py:1176-1260`, `1818-1910`; `orchestrate.py:902-1030`, `1404-1478`), the classifier (`registry_states.py:265-360`), and the goldens. Answers to the three posed questions first, then findings.

**Can a run certify/pass on the wrong arm, mode, commit, or argv?** No.
- Arm/mode: `kv_arm_gate` accepts only a `KV_ARM_ROWS` row for the pick; `certification_problems` (`qualify.py:1166-1170`) requires `spec["pick"]==name` and `spec["tq4_attention"]==mode`. V against X's record is refused (`test_v_is_never_certified_by_xs_record`); a non-tuple summary is refused (`NOT_TUPLE`).
- Commit: `certification_problems` (`qualify.py:1178-1183`) requires `stack_head` and `fork_head` in both binding and manifest equal this run's `_tree_state`. The C199 gate (`entry_problems:330-338`) additionally binds `production` (binding and manifest) and `reviewed_head==fork_head`.
- Argv: `argv_binding_problems` (`qualify.py:236-247`, applied at `1437`) requires the served argv to equal `manifest picks[name].argv_on` element-wise; `_argv_mutations` covers value/flag/order/truncation/off-argv.

**Can the exactness verdict be PASS without `m72_exact` routes serving the ON trajectory?** No. `tq4_engagement` (`worker.py:1176-1213`) reads `tq4_fast.route_counts()` immediately before/after the ON trajectory only; `tq4_engagement_problems` (`orchestrate.py:1404-1411`) is added to E1c evidence and forces `engaged[n]=False` in E2 (`orchestrate.py:1006`), yielding INCOMPLETE (not PASS) if `d2_verify`/`per_query:short` didn't move or any `fallback:*` moved. A boot-time `tq4_mode_problems` check (`worker.py:1226-1234`, `1722-1727`) refuses a mis-named hook before any trajectory.

**Is any existing pick's behaviour changed?** No. `KV_ARM_KEYS` stays 2-key (errata v1.1; pinned by `test_p475a_kv_arm.py:217`); `fingerprint_of` emits `tq4_attention` only with a mode and appends it last (`qualify.py:1830-1837`); `reference_comparison` counts it only where one side has it (`qualify.py:846-849`); `FINGERPRINT` omits it. Goldens (`test_m76_b2_impl_golden.py`) pin fingerprints, expected configs, classify results, reports, plans, manifests, jobs, and tables byte-for-byte, recorded before the change.

---

### F1 — minor, confirmed — `kv_arm_gate` refusal message names the wrong key set
`qualify.py:1112` refuses with `"... only {name}'s KV keys {list(registry_states.KV_ARM_KEYS)} ..."` but the actual check (`classify_kv_arm`) allows the third delta key `tq4_attention`. For a TQ4 arm refused for an unrelated reason (e.g. a non-KV change), the message says "only kv_bits, kv_quant_scheme" and never mentions `tq4_attention`, so an operator debugging a refused X/V/XO arm is pointed at the wrong key set.
*Scenario:* an X registry with a stray `prefill_step_size` edit is refused; the message omits `tq4_attention` though that key is the one the arm carries.
*Proposed change:* say `KV_ARM_DELTA_KEYS` (or "the arm keys") in the message.

### F2 — minor, hypothesis — `tq4_engagement` "either-moved" band is wider than "one draft block"
`worker.py:1188-1197` sets the indeterminate band to `limit ≤ prompt+block` and `prompt+generated ≤ limit + 2*block` (≈2043–2058 for limit=2048, block=5). The errata says "within one draft block of 2,048 → either moved", which reads as ±block (≈2043–2053). A trajectory at prompt≈2056, generated≈2 (total 2058, ~2 blocks above) falls in the band and passes if `per_query:short` moved instead of `d2_verify`. This can only be confirmed on the GPU (acceptance 5) and the spec wording is loose, so the impact is that a borderline-high trajectory is held to the weaker "either" rule.
*Proposed change:* tighten the upper bound to `limit + block` if "one draft block" is meant literally; otherwise document the `2*block` choice.

### F3 — minor, confirmed — certifying run silently requires `--production-ref f9bf743f`
`qualify.py:1335` defaults `production` to `orchestrate.PRODUCTION` (the existing picks' `b26fa7c9`). The C199 gate (`entry_problems:331`) then requires the record's `production` to equal the run's; a tuple record's production is `f9bf743f`, so a certifying run without `--production-ref f9bf743f` is refused (fail-closed, safe). The `--certified-by` help text says to pass it, but nothing sets it automatically.
*Scenario:* an operator runs `qualify --kv-arm --predictor on --certified-by <record> --entry <pick>` without `--production-ref` and gets a `production` mismatch refusal with no hint that `--production-ref` is the missing piece.
*Proposed change:* when `--certified-by` is accepted, default `production_ref` to the bound tuple's `production` (the `TUPLES[label]["production"]`), mirroring `orchestrate.main`'s `args.production_ref = TUPLES[args.tuple]["production"]` (`orchestrate.py:3341`).

### F4 — minor, confirmed — `certification_problems` does not bind `off_stack_head`
The check (`qualify.py:1178`) iterates only `("stack_head","fork_head")`. The P369 smoke/full binding does bind `off_stack_head` (`orchestrate.py:447-454`), but the `--certified-by` binding does not. This matches errata v1.1 (b) as written, so it is not a deviation; noting it because the qualify run therefore never verifies the XO arm commit the record was produced with. The XO arm is only certified transitively via the P369 run's E2 cross-load. No action required unless the operator wants the certify path to also pin the OFF arm.

---

### Scope requests (beyond the request; no severity)
- **S1:** `tq4_mode_problems` (`worker.py:1226-1234`, applied at boot `1722-1727`) asserts the served hook's `name` equals the expected mode. The spec only asks for the same-instance hook *identity* check across ON/OFF1/OFF2; this is an additional boot-time mode check. It is beneficial (refuses a mis-wired hook before any trajectory) and I'd keep it, but it is beyond the spec.
- **S2:** The implementer's four `test_m76_b2_impl_*` files were written after the implementation (P10), not red-first. The independent `test_m76_b2_fe_*` files were written from the spec before the implementation (per their docstring) and amended only for the errata schema, so independent red-first coverage exists. No action; flagging the process note.

### Hazards introduced
None. No production file changes; the patch touches only `dev/p369_phase2/{qualify,registry_states,orchestrate,worker}.py` and the eight test files; no scratch files in the patch; the suite passes with identical skip lists per both reports.

NOTHING OF SUBSTANCE blocks or materially fails the request.
