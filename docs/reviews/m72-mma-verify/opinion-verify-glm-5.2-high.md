I have completed my review. Here are my findings.

## Resolution of each listed finding

**Finding 1** (k=1 TQ4 production reads bait token; A1 vacuous). **Resolved.** `tq_production` now slices the TQ4 state for real via `tq_mod._slice_state(ksr, T)` before building the proxy (`m72_tq4_probe.py:447-454`). The implementer's smoke shows prod rel error dropped from 1.71 to 2.604e-3 at T=8193. Covered by `test_tq4_production_reference_reads_exactly_the_prefix` and `test_recorded_accuracy_uses_a_sane_production_error_on_the_planted_layout`.

**Finding 2** (A1 floor 2⁻⁸ too loose). **Resolved.** `A1_FLOOR = 2.0 ** -12` (`m72_tq4_probe.py:407`); report heading updated; fork test `FLOOR = 2.0**-12`. Covered by `test_a1_floor_is_two_to_the_minus_twelve` and the bound-scaling tests.

**Finding 3** (stale `mma-2.json` averaged). **Resolved.** Launcher refuses exit 10 before `mkdir` when either pass file exists (`m72_run_mma.sh:7-10`); report's `provenance_mismatch` refuses on differing fork head / MLX / arch / checkpoint T list (`m72_mma_report.py:84-101`). Covered by `test_launcher_refuses_an_out_dir_holding_a_previous_pass`, `test_report_refuses_passes_with_differing_provenance`, `test_report_refusal_names_the_differing_field`.

**Finding 4** (fixed arm order confounds drift). **Resolved.** `ARM_ORDERS` + `--arm-order` flag (default forward), pass 1 forward / pass 2 reverse, `meta.arm_order` recorded (`m72_tq4_probe.py:408-409, 629-630, 668`). Covered by `test_launcher_pass_one_forward_pass_two_reverse`, `test_meta_records_arm_order_and_mapping_result`, `test_timed_arms_run_in_the_requested_order`.

**Finding 5** (probe continues on mapping self-check failure). **Resolved.** Probe calls `fragment_mapping_ok()` before `fork_sha` and the sweep; exits 6 on False (`m72_tq4_probe.py:664-667`). Covered by `test_probe_exits_6_before_measured_work_when_the_fragment_mapping_fails` and `test_fragment_mapping_gate_is_specific_to_mma_mode`.

**Finding 5b** (extend self-check to transposed/half/bfloat loads). Scope request, declined. Reasonable: the A1 sweep exercises the half (TQ4) and bfloat (native16) operand types end to end, and the native16 K load uses the transpose path. Not a defect.

**Finding 6** (A3 holds for any non-empty all-failing list). **Resolved.** `a3_verdict` requires exactly the six `(N1–N3) × (mma_tq4, mma_n16)` controls, none duplicated, each `pass is False` (`m72_mma_report.py:59-77`). Covered by `test_report_states_a3_holds_for_exactly_the_six_failing_controls` and the six bad-variant tests.

**Finding 7** (launcher mode 644; formatting). **Resolved.** `m72_run_mma.sh` is mode 755 (`test_launcher_is_executable_mode_755` asserts `0o755`); blank line removed; implementer reports `fe_test.sh fmt` clean.

**Finding 8** ("exact in half" wording). **Resolved.** Comment now says centroids are "rounded to half (about 2^-11 relative), as are the rotated queries and P; not exact" (`m72_mma_verify.py:38-40`).

**Finding 9** (`last_kv_inputs` dead state). **Resolved.** Removed from `m72_mma_verify.py` (the `_run` function no longer writes it).

**Finding 10** (sentinel −1e30 vs logits below it). Declined — residual. Confirmed: the kernel still uses `bool empty = m_run == NEG;` (`m72_mma_verify.py:241`). Under supported inputs (bf16 Q/K, bounded TQ4 norms) scores cannot reach −1e30, so the equality test is safe. GLM rated this minor and safe. Not a defect under supported conditions.

**Finding 11** (TQ4 queries in half overflow ≥ 2¹⁶). Declined for the prototype — residual. Confirmed: TQ4 Q fragment is still `half` and rotated queries are cast via `static_cast<QT>(x)`. Under supported bf16 activations the rotated components are orders of magnitude below 2¹⁶. Not a defect under supported conditions; the disposition explicitly carries it to 1.3 for production to decide.

**Finding 12** (TQ4 `eff_GBps` uses full-cap bytes). Declined — false. Confirmed by tracing: `tq_bytes = tq_state_bytes(ks_raw) + tq_state_bytes(vs_raw)` where `ks_raw, vs_raw = tq.state`, and `tq.state` is the property that slices to `offset` (= T at a checkpoint). Not a defect.

**Finding 13** (mapping self-check verifies only columns). Declined — false. Confirmed: `fragment_mapping_ok` loads `mx.arange(64)` (row-major 8×8), where element value `i = row·8 + col` encodes both row and column. The expected pair `[fm·8+fn, fm·8+fn+1]` would mismatch if either the row mapping `fm` or column mapping `fn` were wrong. Not a defect.

**Finding 14** (monitor `sleep 60` child survives ≤ 60 s). Declined. Confirmed: `trap "kill $mpid" EXIT` still kills only the monitor, not its `sleep 60` child. No material consequence; the orphaned child dies within 60 s. Not a defect.

**Finding 15** (MTP OFF min-then-interpolate). No change, spec-conformant. The report's `gmin` takes min per checkpoint then interpolates, matching the spec wording "per checkpoint the faster of…". Not a defect.

**Finding 16** (test defects: `mx.random.bits`, over-strict sleep list). **Resolved.** `test_a5_reads_nothing_beyond_the_last_length` now uses `mx.random.randint(..., dtype=mx.int32).view(mx.uint32)`; the launcher test now asserts exactly one `sleep 600` between the passes in a shared `seq.log`, allowing monitor `sleep 60`. Testwriter-3 report confirms all 427 fork + 81 stack + 30 stack-gpu tests pass.

## Anything else the diff breaks or leaves failing

I traced the new `a3_verdict` and `provenance_mismatch` logic against every test variant (missing, duplicated-seven, duplicated-six, one-passing, unexpected-extra, none; and each provenance field), and the arm-order dispatch in `measure_checkpoint_mma` (closure capture is safe because the per-arm functions are called within the same `for k` iteration). The amended tests and the A7 smoke both pass per the reports. The four declined residuals (10, 11, 14, 15) hold under the supported conditions stated in the spec. I found no new defect introduced by the fix round.

NOTHING OF SUBSTANCE
