# P369 v13 build — code review round 2 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p369-v13` `5f407d5d..d36d33c5`

I’ll review the committed objects directly, including the unchanged-production claim, red/green test honesty, and surrounding implementation beyond the inline diff. I’ll treat the corpus content hash as a revision proxy only if it is independently and consistently reconstructed.The review has found two lifecycle-level risks beyond the inline fixes: the worker may inspect the drafter before it is bound, and direct-script import mode may fail only for Ornith’s draft-inventory gate. I’m verifying both against the actual load/import paths before treating them as findings.Production-code checks are clean: both `64afc7dd..d36d33c5` and `7207179b..d36d33c5` are empty under `mlx_vlm ':!mlx_vlm/tests'`.

M1 — OPEN — HIGH — `mlx_vlm/tests/test_p369_phase2_orchestrate.py:2493`  
Problem: production correctly uses byte-preserving `read_registry()` in `Campaign.prepare()`, but the regression test calls only the helper. An unused helper would satisfy the test while `prepare()` could regress to `read_text()`.  
Failure scenario: reverting only `Campaign.prepare()` to universal-newline reading leaves the test green and restores CRLF acceptance.  
Fix: exercise `Campaign.prepare()` with a CRLF registry and assert refusal by the 16-state classifier.

M2 — OPEN — HIGH — `dev/p369_phase2/orchestrate.py:121-143`  
Problem: `draft_inventory_problems()` imports `p369_phase2.telemetry`, which fails in the documented direct-script execution mode where only `dev/p369_phase2` is on `sys.path`. Additionally, any truthy `selected_experts` and a missing `block` are accepted as well-formed evidence.  
Failure scenario: Ornith completes its smoke and then crashes during authorization with `ModuleNotFoundError`; alternatively, malformed evidence such as `selected_experts="forged"` authorizes the draft path.  
Fix: import `telemetry` through the existing package/script fallback and require a non-empty block plus a non-empty list of exact, in-range integer expert IDs. Add direct-script and malformed-schema tests.

M3 — OPEN — HIGH — `dev/p369_phase2/worker.py:1225-1232`  
Problem: identity is inspected before the drafter is bound. `Qwen3_5MTPDraftModel` initializes `_input_embed` and `_lm_head_fn` to `None`; binding occurs during `reset()`/generation, after this startup gate. Synthetic tests pre-populate both fields and mask the lifecycle error. `_callable_identity()` also omits bound-function identity.  
Failure scenario: every fresh MTP-ON worker refuses before its first request with `id(None)` binding evidence. A different same-named method bound to the target embedding can later collide with the expected identity.  
Fix: explicitly bind the loaded drafter before inspection, then compare the actual callable including `__func__`. Add a real fresh-drafter lifecycle test.

M4 — CLOSED  
The actual `_split_and_load()` artifact is now bound and executed through a draft/verify round. The surrounding tests and loaded-worker identity gate cover nested type, layer type, top-k, projections, block size, and real-artifact quantization.

M5 — OPEN — MEDIUM — `dev/p369_phase2/telemetry.py:346-357`, `mlx_vlm/tests/test_p369_phase2_moe.py:430-452`  
Problem: the test’s width is 64, so `exact_affine_switch_gate_up()` declines its fused branch, which requires an input width divisible by 512. It therefore does not test the corrected container-to-bank family classification. Nested successful helpers can also still record both inner and outer helper attributions.  
Failure scenario: reverting only the affine family fix leaves the test green; a successful nested helper can report the down bank twice.  
Fix: use width 512, assert an exact attribution `Counter`, and collapse nested helper records so one successful outer operation contributes exactly one bank attribution.

M6 — CLOSED  
The verdict now requires verify-scope frames and refuses routed attributions outside a frame. The invocation-hook-only sabotage fails for the intended reason. N3 covers a separate ownership gap.

M7 — OPEN — MEDIUM — `mlx_vlm/tests/test_p369_phase2_moe.py:477-515`  
Problem: full and partial cuts and commit neutrality are tested, but the prompt-end snapshot is not asserted to exist, carry a probe, or be neutral.  
Failure scenario: prompt-end snapshot/probe capture disappears while all new M7 tests remain green.  
Fix: assert `rec.prompt_end`, its probe, and its neutrality, and verify the expected cut cardinality/categories.

M8 — CLOSED  
The served routed banks are asserted int4/g64; width-2 and width-3 runs compare logits, experts, routed outputs, leaf counts/types/offsets/state keys, and all state arrays with strict bidirectional iteration.

M9 — CLOSED  
The full loaded axis corpus receives a stable content hash independently of the reviewed panel, while `source_pick` is independently derived from `PICKS`. Given that no revision ID exists, this content digest is an adequate—and stronger than a label—revision proxy.

M10 — CLOSED  
All projected phase timings must now be exact numeric values, finite, and non-negative; negative, NaN, and both infinities are covered.

N1 — HIGH — `dev/p369_phase2/orchestrate.py:1748,1824-1827,2690-2694`  
Problem: the withdrawn campaign wall cap remains executable through `--wall-limit-s`. C194 says there is no campaign hard stop and only per-request watchdogs stop the run.  
Failure scenario: an old v17 command supplies the option and censors the campaign contrary to the accepted v13 plan.  
Fix: remove or refuse `--wall-limit-s`, make the campaign deadline unconditional infinity, and retire the wall-cap tests.

N2 — MEDIUM — `mlx_vlm/tests/test_p369_phase2_moe.py:296-301,386-400,456-469`  
Problem: sabotage uses the function-scoped `monkeypatch` after telemetry has installed wrappers. Telemetry restores the original first; pytest teardown then restores the captured telemetry wrapper globally.  
Failure scenario: later tests run through stale wrappers retaining previous telemetry objects, making the suite order-dependent and no longer isolated.  
Fix: use `monkeypatch.context()` and undo sabotage before leaving the telemetry context.

N3 — MEDIUM — `dev/p369_phase2/telemetry.py:361-381,698-708`  
Problem: frames validate only projection names, not bank ownership.  
Failure scenario: swapping gate banks between two layers preserves global manifest coverage and `{gate, up, down}` in every frame, so the verdict passes despite each invocation using another layer’s bank.  
Fix: record each frame’s expected module prefix and require every attribution’s module to belong to that frame; add a cross-layer swap sabotage.

N4 — MEDIUM — `mlx_vlm/tests/test_p369_phase2_moe.py:190-232,587-593`  
Problem: the fixture claims every linear is bf16 affine int4/g64, but assertions cover only routed `SwitchLinear` banks. The manifest adapts to whatever modules exist, so dense ordinary linears can remain unnoticed.  
Failure scenario: a quantizer-predicate change leaves some verifier linears dense while the “served-shape” exactness tests remain green.  
Fix: inventory every eligible linear and assert quantized class, affine mode, 4 bits, group size 64, and bf16 scales/biases.

VERDICT: NOT CLEARED M1 M2 M3 M5 M7 N1 N2 N3 N4No further follow-up is needed; the relevant findings were already incorporated into the review.
