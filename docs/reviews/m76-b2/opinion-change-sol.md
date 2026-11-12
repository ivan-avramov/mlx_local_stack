P1 — Location: `qualify.py:1335-1339,1508-1514`; `orchestrate.py:33,73,1547-1604`  
Severity: blocker  
Evidence: confirmed, source-traced  
Problem: mode-arm `qualify` runs default to old production `b26fa7c9`; M77 production is `f9bf743f`.  
Failure scenario: stage-0 predictor-OFF runs for X/V/XO and engagement-only runs for X/V refuse on the production diff. Tests mock preflight. M1 works only with the errata’s explicit `--production-ref f9bf743f`.  
Proposed change: select `M77_PRODUCTION` automatically when `--kv-arm` classifies a `tq4_attention` arm, and add an unmocked production-preflight test.

P2 — Location: `tq4_attention.py:306-321`; `mtp_verify_scan.py:278-290,338-349`; `orchestrate.py:1450-1471`  
Severity: blocker  
Evidence: confirmed, source-traced  
Problem: below 2,048, `m72_exact` records `per_query:short` then delegates to `joint_v1`, which records expected reason `cache`. `e1c_verdict` rejects every non-empty `verify_fallback_reasons`.  
Failure scenario: smoke cell T1024 is always INCOMPLETE, so smoke cannot pass, full cannot start, and no valid M1 certificate can be produced. Tests fabricate `verify_fallback_reasons={}`.  
Proposed change: for tuple runs, accept `cache` only when exactly accounted for by `per_query:short`; continue rejecting unexplained `cache` and every other fallback reason. Add a real TQ-cache policy test.

P3 — Location: `qualify.py:224-247,319-370,1145-1185,1354-1435`; `orchestrate.py:398-451`  
Severity: major  
Evidence: confirmed, source-traced  
Problem: `--certified-by` does not verify that `summary.binding` equals the sibling manifest. It ignores the binding’s argv, registry hashes, parameters, weights, harness tree and dependencies, and does not enforce the tuple’s production pin directly.  
Failure scenario: after a stack-venv/argv change at the same stack commit, a PASS summary from argv A can be paired with a replacement manifest containing current argv B; qualification certifies B although exactness ran A. The tests’ accepted records omit `binding.picks`, masking this.  
Proposed change: require `summary["binding"] == orchestrate.binding(manifest)`, cross-check `summary["manifest"]`, enforce `TUPLES[label]["production"]`, and record hashes of both files.

P4 — Location: `orchestrate.py:850-898,2755-2795`  
Severity: major  
Evidence: confirmed, source-traced  
Problem: rejected E1c retries gate C1 and neutrality only; their TQ4 engagement failures are discarded.  
Failure scenario: an invalid-straddle attempt has no required route or moves `fallback:*`; a later retry passes, allowing overall E1c PASS despite the earlier unengaged ON trajectory. Tests cover only accepted attempts.  
Proposed change: retain `evidence_ok` for rejected attempts and make any engagement failure INCOMPLETE, after existing C1/neutrality precedence.

P5 — Location: `worker.py:1176-1214`  
Severity: major  
Evidence: confirmed, source-traced  
Problem: route requirements are inferred from prompt/generated counts using a two-block margin, rather than observed verify lengths. This is weaker than errata v1.1’s one-block crossing rule.  
Failure scenario: prompt 2,040 plus 18 generated tokens crosses ten tokens beyond 2,048, but the code requires only `per_query:short`; PASS is possible without `d2_verify`.  
Proposed change: derive requirements from recorded verify-block `lengths[0]`; test crossings wider than one draft block.

P6 — Location: `orchestrate.py:1232-1311,2234-2253`  
Severity: major  
Evidence: confirmed, source-traced  
Problem: smoke projection still models the old four thresholds and 3.5-hour gate. It omits T2048, both scale cells, and their E2 repetitions; M76’s required 8-hour scale-cell ruling is absent.  
Failure scenario: after P2 is fixed, smoke can authorize full while materially underestimating the 260,096-token work and bypassing the operator ruling.  
Proposed change: project from `tuple_cells(..., smoke=False)` and enforce M76’s 8-hour ruling; add tuple projection tests.

P7 — Location: `qualify.py:1593-1617`; `worker.py:1783-1795`  
Scope request  
Evidence: confirmed, source-traced  
Problem: stage-0 `--engagement-only` verifies the hook name and drafter manifest, but never TQ4 route counters.  
Failure scenario: it can complete with the correct named hook while all TQ4 layers fall back.  
Proposed change: if stage 0 must prove TQ-mode engagement, record per-request route deltas and require the expected route with zero `fallback:*`.

P8 — Location: `worker.py:1198-1199`  
Severity: minor  
Evidence: confirmed, source-traced  
Problem: the candidate adds dormant `m72_v1`/`mma` P369 engagement support although only `m76-x`/`m72_exact` is specified. No existing-pick behavior change was traced; defaulted paths and existing goldens remain unchanged.  
Failure scenario: future modes would silently inherit the `mma` rule through the generic `else`.  
Proposed change: restrict the helper to `m72_exact`, or explicitly enumerate supported modes.
