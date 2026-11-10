P1 — Sol P1 / GLM F3: NOT RESOLVED
- Location: `material/candidate2/m72_mma_verify.py:133,179-250`; `material/context_pass2_kernel.py:23-65`
- Severity: major
- Evidence: confirmed, source-traced and range-proved.
- Problem: `-1e30` remains both a score bound and empty-partial sentinel; finite bf16 inputs can produce smaller logits.
- Concrete failure scenario: opposing Q/K near `2^50` produce finite logits around `-2e31`; valid rows are treated as empty and return zero.
- Proposed change: enforce an explicit input-magnitude bound, or use `-INFINITY` with explicit emptiness tracking and a compatible pass-2 reduction.

P2 — Sol P2: NOT RESOLVED
- Location: `material/candidate2/m72_mma_verify.py:36-40,166-175`
- Severity: major
- Evidence: confirmed, source-traced and range-proved.
- Problem: TQ4 rotated queries are still cast to half without a documented magnitude restriction.
- Concrete failure scenario: finite bf16 components of `2^20` can rotate above half’s 65,504 limit, producing Inf/NaN.
- Proposed change: use float TQ4 Q/K fragments, or explicitly constrain and validate query magnitude.

P3 — Sol P3 / GLM F2: RESOLVED
- Location: `material/candidate2/m72_tq4_probe.py:447-454`
- Severity: major (original)
- Evidence: confirmed, source-traced and tested.
- Problem: the production reference formerly read the T+1 bait token.
- Concrete failure scenario: no longer occurs; `_slice_state` now creates a real prefix slice.
- Proposed change: none for the original consecutive-length case; see P17.

P4 — Sol P4: RESOLVED AS ADAPTED
- Location: `material/candidate2/m72_run_mma.sh:8-13`; `material/candidate2/m72_mma_report.py:81-103`
- Severity: major (original)
- Evidence: confirmed, source-traced and tested.
- Problem: reused output directories could combine new and stale passes.
- Concrete failure scenario: the launcher now refuses existing pass JSON, while the report rejects the provenance mismatches required by v1.2.
- Proposed change: none.

P5 — Sol P5: RESOLVED AS DISPROVED
- Location: `material/candidate2/m72_tq4_probe.py:562-570`
- Severity: major (original claim; no defect)
- Evidence: confirmed from the supplied state-layout trace.
- Problem: the alleged full-cap TQ4 byte accounting does not occur because `tq.state` is sliced to offset T.
- Concrete failure scenario: none.
- Proposed change: none.

P6 — Sol P6: RESOLVED
- Location: `material/candidate2/m72_tq4_probe.py:407-409,606-609`; `material/candidate2/m72_run_mma.sh:29-32`
- Severity: major (original)
- Evidence: confirmed, source-traced and tested.
- Problem: both passes formerly used identical arm order.
- Concrete failure scenario: pass one now uses forward order and pass two reverse order.
- Proposed change: none.

P7 — Sol P7: RESOLVED
- Location: `material/tests/test_m72_mma_verify.py:463-486`
- Severity: major (original)
- Evidence: confirmed, source-traced; the supplied run reports 427 passing tests.
- Problem: nonexistent `mx.random.bits` prevented the TQ4 A5 test from running.
- Concrete failure scenario: the amended test now generates int32 data and views it as uint32.
- Proposed change: none.

P8 — Sol P8 / GLM F4: RESOLVED FOR V1.2
- Location: `material/candidate2/m72_mma_verify.py:356-387`; `material/candidate2/m72_tq4_probe.py:663-673`; `material/tests/test_m72_mma_verify.py:534-536`
- Severity: minor (original)
- Evidence: confirmed, source-traced and tested.
- Problem: the mapping check was previously neither asserted nor gating.
- Concrete failure scenario: the probe now exits 6 before measurement when it fails.
- Proposed change: none.

P9 — Sol P8 typed/transpose extension: DECLINED SCOPE REQUEST
- Location: `material/candidate2/m72_mma_verify.py:356-387`
- Evidence: confirmed.
- Problem: the dedicated diagnostic does not separately test typed/transposed loads and known MMA products.
- Concrete failure scenario: none established; end-to-end GPU tests exercise those paths.
- Proposed change: add typed/transposed product diagnostics only if broader portability assurance is required.

P10 — Sol P9: RESOLVED
- Location: `material/candidate2/m72_mma_report.py:59-78`
- Severity: minor (original)
- Evidence: confirmed, source-traced and tested.
- Problem: incomplete controls could previously certify A3.
- Concrete failure scenario: missing, duplicate, unexpected, or passing controls now produce “A3 NOT shown.”
- Proposed change: none.

P11 — Sol P10 / executable portion of GLM F7: RESOLVED IN CANDIDATE 2
- Location: `material/candidate2/m72_run_mma.sh`; `material/tests/test_m72_run_mma.py:124-139`
- Severity: minor (original)
- Evidence: confirmed; candidate file mode is 755 and direct invocation is tested.
- Problem: direct invocation formerly failed.
- Concrete failure scenario: no longer occurs in the full candidate.
- Proposed change: see P19 for the repair diff.

P12 — Sol P11: RESOLVED
- Location: `material/tests/test_m72_run_mma.py:84-96`
- Severity: minor (original)
- Evidence: confirmed, source-traced and tested.
- Problem: the old test rejected the monitor’s `sleep 60`.
- Concrete failure scenario: it now requires one `sleep 600` between passes while allowing monitor sleeps.
- Proposed change: none.

P13 — Sol P12 / GLM F6: RESOLVED
- Location: `material/candidate2/m72_mma_verify.py:36-40`
- Severity: minor (original)
- Evidence: confirmed.
- Problem: documentation incorrectly claimed exact half representation.
- Concrete failure scenario: wording now states that values are rounded.
- Proposed change: none.

P14 — GLM F1: RESOLVED AS DISPROVED
- Location: `material/candidate2/m72_mma_verify.py:356-387`
- Severity: blocker (original claim; no defect)
- Evidence: confirmed, source-traced.
- Problem: `arange(64)` encodes both row and column, and the comparison includes `fm * 8`.
- Concrete failure scenario: a changed row mapping would fail the check.
- Proposed change: none.

P15 — GLM F5: RESOLVED
- Location: `material/fix-fork.diff:79-99`
- Severity: minor (original)
- Evidence: confirmed.
- Problem: unused mutable `last_kv_inputs` state.
- Concrete failure scenario: the state and writes were removed.
- Proposed change: none.

P16 — monitor-child portion of GLM F7: NOT RESOLVED
- Location: `material/candidate2/m72_run_mma.sh:18-20`
- Severity: minor
- Evidence: confirmed, source-traced.
- Problem: the EXIT trap kills the monitor shell but may orphan its active `sleep 60` child.
- Concrete failure scenario: a sleep process survives launcher exit for up to 60 seconds.
- Proposed change: terminate and wait for the monitor process group or explicitly kill its children.

P17 — GLM F8: RESOLVED AS SPEC-CONFORMANT
- Location: `material/candidate2/m72_mma_report.py:172-173`
- Severity: minor (original claim; no defect)
- Evidence: confirmed against v1.2.
- Problem: min-per-checkpoint followed by interpolation is exactly the registered formula.
- Concrete failure scenario: none.
- Proposed change: none.

P18 — NEW: TQ4 production reference mishandles gapped lengths
- Location: `material/candidate2/m72_tq4_probe.py:312-317,447-454`
- Severity: major
- Evidence: confirmed, source-traced.
- Problem: for k>1, `tq_production()` only uses `lengths[-1]`; causal `per_query_attention` infers consecutive prefixes instead of honoring every supplied length.
- Concrete failure scenario: lengths `[100, 8191, 8192]` compare against prefixes near 8192, potentially inflating `prod_rel_err` and weakening A1 for legal inputs.
- Proposed change: run each query against a real state slice ending at its own `lengths[j]`, then concatenate; add a gapped-length test.

P19 — A6 ACCEPTANCE NOT ESTABLISHED
- Location: `material/spec.md:141-144`; `material/implementer-fix-report.md`; `material/testwriter-3-report.md`
- Severity: major
- Evidence: confirmed; both reports state that the full stack suite and baseline comparison were not run.
- Problem: targeted suites pass, but the pre-registered full-stack regression criterion remains unchecked.
- Concrete failure scenario: an unrelated stack regression could survive while the candidate is declared merge-ready.
- Proposed change: run the complete stack suite on candidate 2 and baseline and record the comparison.

P20 — NEW: repair diff omits the executable-mode transition
- Location: `material/fix-stack.diff`, `m72_run_mma.sh` hunk
- Severity: minor
- Evidence: confirmed; the candidate file is mode 755, but the diff has no mode metadata.
- Problem: applying the supplied repair diff to candidate 1 preserves mode 0644.
- Concrete failure scenario: a diff-reconstructed candidate still fails direct invocation with permission denied.
- Proposed change: regenerate a mode-aware git patch containing the 100644→100755 transition, or record an explicit `chmod 755` step.
