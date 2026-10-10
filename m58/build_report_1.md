Implementer's ten judgement calls (M58 build, 2026-10-06):
1. Counter partition: verify_blocks_{joint_v1, per_query, straddle, len1} disjoint; verify_fallback_reasons histograms only the per_query bucket (straddle not in the histogram).
2. Reason names: cache, batch, mask_form, prefix, gqa_bound, domain, mask_rows.
3. 4-D bool incoming mask: effective mask must have every row non-empty and a single contiguous True run (reason mask_rows); one sync on that rare path.
4. Counters count only blocks reaching _attention with output is None; ragged helper blocks are not counted.
5. A straddling length-2 block runs the per-query decomposition under joint_v1 (differs from today's shipped joint call = C120); per_query unchanged.
6. --draft-kind mtp checked against the configured kind (flag/env) at the M57 hook position, before drafter load; not re-checked against the resolved drafter.
7. Self-test fails if the model shape has no eligible cell (e.g. GQA 8): a model outside the domain refuses to load under joint_v1 instead of silently falling back.
8. Counters travel as one verify_counters: Optional[dict] through StreamingToken/GenerationMetrics/GenerationTimings/StreamingTimings; serializers flatten to top-level verify_* keys, omitted when None.
9. "Request completed" line appends verify_*=… tokens only when counters are present.
10. AB end_block() materialises flags with one mx.eval at the end of the verifier __call__ (mid-graph eval in the AB gate path; gate rows only).
Stack: conftest autouse fixture _pin_unresolved_mtp_scan maps the "unknown" outcome to per_query for tests with fake model names; tests opt out with the real_mtp_scan marker.
