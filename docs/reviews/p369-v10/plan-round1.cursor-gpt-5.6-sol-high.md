# P369 run plan v10 — round 1 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p405-kv-scheme` `6911b17f`

V1 — BLOCKER  
Problem: The production pin is contradictory. The header names the P405 head, the inherited plan still pins `4e6d0e03`, while `6911b17f`’s harness actually defines production as `7207179b`; `6911b17f` only adds later harness fixes.  
Failure scenario: The run either refuses because the production-tree guard compares against the wrong commit, or reports evidence against a different tree than the plan claims.  
Change: Distinguish and state exactly: production-code pin `7207179b`, harness/reviewed head = the eventual reviewed descendant of `6911b17f`. Remove every `4e6d0e03` assertion and bind both hashes independently.

V2 — BLOCKER  
Problem: The estimate and authorization gate were not expanded for four models. The existing smoke gate sums `wall_s * 6` across picks and requires ≤3.5 hours. Yet v10 adds approximately 3.2 hours for Qwen3.6 and at least 2–2.5 hours for Ornith to the existing 3–3.5-hour full run.  
Failure scenario: A successful four-pick smoke projects above 3.5 hours, so `fits=False` prevents the full run. Operationally, the stated 3–3.5-hour reservation is also short by roughly 5–7 hours.  
Change: Choose explicitly between independently authorized per-pick campaigns or one four-pick campaign. For one campaign, budget roughly 9–10 GPU hours before heavy-tail E7 requests and revise `ESTIMATE_LIMIT_S`, monitoring ETA, and operator escalation accordingly. Ornith’s 3B active parameters do not by themselves establish a two-hour wall time because prefill, verifier routing, repeated full-state hashing, and E7 runaways remain.

V3 — BLOCKER  
Problem: “The static manifest gains the MoE verify-path kernels” is insufficient to ensure that Ornith’s routed experts are observed. Current telemetry inventories `nn.Linear`/`QuantizedLinear` and embeddings. The verifier’s `_switch_glu` calls `SwitchLinear` or `QuantizedSwitchLinear` projections directly, outside the instrumented linear dispatcher. Dense/shared projections could therefore satisfy the existing positive-call checks while all three routed projections remain invisible.  
Failure scenario: Ornith loads and produces MTP rounds, recorder/probe hooks fire, and the kernel verdict passes based on gates and shared experts, but the batched routed-expert path under review is never classified. A regression in expert dispatch is then attributed only indirectly—or missed by the inventory entirely.  
Change: Require the tiny `qwen3_5_moe` fixture to prove:

- The loaded target is structurally MoE: expected model class, layer count/type census, FA/GDN split, MoE block count, expert count and top-k.
- A complete MTP request exercises recorder rows, accepted/rejected or bonus emission cuts, commit snapshots, neutral probes, and verifier block boundaries.
- Gate, shared expert, and each routed bank projection—gate/up/down—are classified exactly once per invocation in verifier scope for both `SwitchLinear` and `QuantizedSwitchLinear`.
- Coverage is per routed bank invocation, not “all 256 experts observed.”
- Width-2/3 verifier execution is bitwise compared with sequential singleton execution on independent caches, including routed output, target rows, selected indices and final state.
- Negative tests disabling each new hook or omitting a routed projection make the harness fail.

V4 — HIGH  
Problem: Borrowing the uniform model’s item IDs is acceptable for E2’s within-model ON/OFF conformance, but the proposed digest/count replacement is circular. A digest generated during reconstruction only binds later requests to whatever was reconstructed; it does not prove that the intended dataset row and builder output were reconstructed. The source bundles must also be included explicitly in smoke/full attestation because they live under another pick.  
Failure scenario: A dataset changes while retaining an item ID, or the builder changes message formatting. The harness records a new digest and count, all trajectories match it, and the run passes while silently testing different content.  
Change: Add a reviewed borrowed-panel fixture containing source bundle path and SHA, item ID, seed, dataset revision/content hash, and canonical built-message SHA. Precompute and pin each entry’s templated token count and digest before GPU execution, then bind them into smoke-to-full authorization. Call E7 a “synthetic borrowed-panel incidence record,” not historical traffic exposure; it cannot estimate how often events occurred while these entries previously served.

V5 — BLOCKER  
Problem: The P406 registry state and overlay are not specified byte-exactly. Marker-prefix matching plus an adjacent commented `draft_model` can restore a modified drafter path, and the current campaign does not require the opt-in P387 live-registry classifier before constructing its overlay. “Exactly two P406 marked lines” is also inaccurate: only `draft_kind` is marked; `draft_model` is an adjacent unmarked line.  
Failure scenario: The live registry contains the expected marker but a changed adjacent drafter, modified generation default, partial P406 application, or unrelated edit. The overlay still launches and records that altered tuple instead of refusing.  
Change: Define the third state as one deterministic raw-byte substitution of the golden fixture: complete C177 interim plus both complete P406 pairs. `Campaign.prepare` must require one of the three exact byte states—not rely on an opt-in test. Reject partial P406, altered comments/paths, whitespace/newline changes, extra edits, duplicate markers and non-adjacency. Build each overlay by replacing the exact fixture pair and assert that the selected entry’s restored block equals the certified fixture block.

V6 — BLOCKER  
Problem: Recording the current Hugging Face revision and hashes does not pin the certified target or predictor. Both smoke and full can bind to the same newly moved `main` revision. This is especially material for Ornith’s transplanted Qwen3-Next head: E1c can pass with a wrong or degraded drafter because target verification preserves correctness.  
Failure scenario: The drafter repository is updated with compatible dimensions but wrong transplanted weights. It loads, drafts positively, and E1c/E2 remain exact, but acceptance and speed collapse; the plan then re-enables an artifact different from M27.  
Change: Pin reviewed target and drafter revisions plus expected file hashes, including every prompt/template-affecting file. Assert loaded drafter configuration and effective runtime parameters: `qwen3_5_mtp`, block size/depth, dense versus MoE text type, hidden/vocabulary compatibility, Ornith’s 256/8 expert shape and quantization, observed verify widths, and effective `per_query` policy. For Ornith, bind an extraction manifest identifying the Qwen3-Next source revision and resulting drafter hashes.

V7 — BLOCKER  
Problem: “Restore after PASS” conflicts with §6, where worker conformance is followed by fork/submodule integration and router-chain recertification before restoration. Section 6 also mentions only the C177 lines, omitting P406.  
Failure scenario: A worker PASS causes P406 lines to be uncommented before real router rewriting, registry loading, process management and endpoint behavior are recertified. MTP ships despite this phase explicitly making only worker-level claims.  
Change: State that worker PASS causes no registry mutation. Per entry, require: worker PASS → reviewed fork push/submodule bump → reviewed router-chain ON/OFF recertification against the pinned tuple → exact restoration of that entry’s C177 or P406 pair and associated tests. FAIL, ABORT or INCOMPLETE leaves it MTP-OFF.

VERDICT: DISAGREE V1 V2 V3 V5 V6 V7
