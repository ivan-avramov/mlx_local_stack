# P369 v13 build — code review round 1 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p369-v13` `64afc7dd..5f407d5d`

P1 Production code is byte-identical across the requested range. The referenced plan path is not present at `5f407d5d`, so I’m treating the inline v13 §3.1 text as authoritative and checking whether another commit/tree contains the cited document before relying on it.Production diff check passed: no non-test `mlx_vlm` changes.

M1 — HIGH — `dev/p369_phase2/orchestrate.py:1961`  
Problem: `Path.read_text()` normalizes CRLF to LF before the 16-state classifier, contradicting byte-exact refusal.  
Failure scenario: a CRLF or mixed-newline registry is accepted as a valid LF state.  
Fix: load using `read_bytes().decode("utf-8")` and test `Campaign.prepare()` with CRLF input.

M2 — HIGH — `dev/p369_phase2/orchestrate.py:938-949`  
Problem: the smoke gate trusts only `draft_kernels["pass"]`; it does not validate `moe`, non-empty invocations, expected parts, or selected experts. The test explicitly accepts an effectively empty inventory.  
Failure scenario: `{"pass": true}` or `invocations=[{}]` authorizes Ornith without the required positive draft-path evidence.  
Fix: schema-check the complete inventory against the expected MoE parts and require selected experts in every invocation.

M3 — HIGH — `dev/p369_phase2/worker.py:190-230`  
Problem: the loaded-drafter identity gate omits nested text type, configured/effective block size, proposal width, and exact target-head binding. `head_bound` only checks non-`None`; the unit fixture uses unrelated callable `len`. Its global quantization set also does not prove all three routed banks are int4/g64.  
Failure scenario: a wrong-head, wrong-width, partially dense, or incorrectly typed drafter passes as certified.  
Fix: record and compare these fields explicitly, including callable ownership and each `switch_mlp.{gate,up,down}_proj` type/bits/group size.

M4 — HIGH — `mlx_vlm/tests/test_p369_phase2_moe.py:84-102,181-187,251-272`  
Problem: the accepted split → strict-load → bind → draft/verify chain is split across unrelated fixtures. The split-loaded artifact is never bound or executed; the executed drafter is freshly constructed and dense. The uploaded-shape test also omits top-k, all three projections, quantization, block size, and effective width.  
Failure scenario: splitting/loading succeeds but the resulting artifact fails binding or real MoE execution while the direct-construction round remains green.  
Fix: execute the actual `_split_and_load()` result through target binding and one draft/verify round, asserting the complete certified shape.

M5 — MEDIUM — `dev/p369_phase2/telemetry.py:282-336`  
Problem: fused-helper instrumentation can double-count. Helpers such as `exact_quantized_switch_linear` call the already-wrapped bank and then `_routed_helper` records it again. Batch affine gate/up similarly records bank calls plus the helper. Additionally, `exact_affine_switch_gate_up` is classified from its `SwitchGLU` container as dense although its eligible banks are quantized.  
Failure scenario: a correct fused route reports duplicate projections or the wrong family and fails; alternatively its inventory is misleading.  
Fix: suppress nested bank recording or have helpers record only deltas, and derive family from each underlying bank. Add direct fused-helper tests.

M6 — MEDIUM — `dev/p369_phase2/telemetry.py:664-676`  
Problem: `verdict()` does not require any routed invocation frames. If the `_switch_glu`/`SwitchGLU` frame hook is absent but bank hooks remain, complete bank attributions satisfy coverage and the verdict can pass. Existing sabotage removes bank hooks instead, so it does not prove this hook fails closed.  
Failure scenario: the per-invocation exactly-once observer is disabled while all banks still run; evidence passes without proving invocation counts.  
Fix: require verify-scope frames and bind each routed attribution to exactly one frame; add an invocation-hook-only sabotage.

M7 — MEDIUM — `mlx_vlm/tests/test_p369_phase2_moe.py:251-337`  
Problem: the “fully observed” test asserts only rows, commits, blocks, and broad verdicts. It does not prove accepted/rejected/bonus emission cuts or neutral probes, and there are no independent router/shared-expert sabotage cases. The shared-only sabotage overwrites the MoE-block observer itself, proving absence of the whole observer rather than omission within an observed block.  
Failure scenario: probe neutrality or individual router/shared hooks regress while the test remains green.  
Fix: assert concrete cut categories and every snapshot’s probe/neutral fields; sabotage each observer while preserving the enclosing MoE-block hook.

M8 — MEDIUM — `mlx_vlm/tests/test_p369_phase2_moe.py:375-422`  
Problem: the quantized V3(d) case uses g32 although Ornith is certified g64 and asserts only that any routed bank is quantized. It does not capture routed outputs directly. Cache comparison uses truncating `zip`, omits cache offsets and key-list equality, and ignores leaves present only on the right.  
Failure scenario: g64-only divergence, a dense routed projection, wrong cache offset, or an added/missing state leaf passes.  
Fix: use a g64-capable fixture, assert every routed bank is int4/g64, compare routed outputs, cache counts/types/offsets/keys, and all leaves bidirectionally.

M9 — MEDIUM — `dev/p369_phase2/orchestrate.py:129-188`  
Problem: the panel omits the required dataset revision, and `panel_problems()` never compares `source_pick` with `items_source(pick)[0]`; it feeds the panel’s own source value back into reconstruction.  
Failure scenario: an incorrectly labelled source or unrecorded dataset revision passes despite violating the reviewed binding.  
Fix: record a pinned dataset revision and compare both it and `source_pick` against independently derived expectations; add drift tests.

M10 — MEDIUM — `dev/p369_phase2/orchestrate.py:976-985`  
Problem: phase timings are checked only for numeric type, not finiteness or non-negativity.  
Failure scenario: negative or `-Infinity` timing evidence can reduce the projection and make an over-budget campaign appear to fit.  
Fix: reject every timing unless finite and non-negative, with authorization tests for negative and non-finite values.

VERDICT: NOT CLEARED M1 M2 M3 M4 M5 M6 M7 M8 M9 M10
