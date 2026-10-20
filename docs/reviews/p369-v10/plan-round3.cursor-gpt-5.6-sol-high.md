# P369 run plan v12 — round 3 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`)

Round-2 verification

- V8 — Resolved. `4e6d0e03` is explicitly historical; `7207179b` is the sole production pin.
- V9 — Resolved on its merits. C188 authorizes carry-over, P400’s changed path was unused by Fable (`verify_blocks_per_query = 0`), P401 only added fail-loud validation, and P405 does not change native-KV behavior. Requiring a passing `7207179b` regression smoke—and escalating to a full run on failure—is proportionate.
- V10 — Resolved. The exact 16-state Cartesian product supports every independent restoration order and replaces the stale field-based classifier.
- V11 — Resolved for qualification, though not literal provenance. Upload/current bytes are pinned; architecture, binding and runtime parameters are asserted; E1c/E2 establish neutrality; router acceptance/speed reproduction replaces the missing local-directory hash. V16 tightens that future gate.
- V12 — Not fully resolved; see V14. The strict split/load/round test is right, but its input configuration is underspecified against the exact discriminator that caused the concern.
- V13 — Resolved. Projection is per campaign and phase, with explicit tail allowance and a wall cap. V17 corrects terminology and total-wall presentation.

Round-1 residuals

- V1 — Resolved through the production/reviewed-head separation and V8 historicalization.
- V5 — Resolved by the shared exact-byte 16-state generator.
- V6 — Resolved for safe enablement by immutable upload pins, loaded-drafter assertions, worker neutrality evidence and mandatory router utility reproduction.

Borrowed items are sound for E2. A templated-token digest and count alone would remain circular, but v12 additionally pins the source bundle, dataset content, canonical built messages and precomputed per-entry digests. What is lost is model-specific historical C84 evidence and traffic representativeness; v12 correctly labels E7 synthetic and descriptive.

The restore sequence is also correct: worker PASS mutates nothing, and each entry requires reviewed integration plus router-chain recertification before its exact C177/P406 restoration.

V14 — HIGH  
Problem: The `qwen3_next` split test does not pin the critical input configuration shape. At `6911b17f`, `Qwen3NextMTPSplitter` preserves the nested `text_config.model_type`; `Qwen3_5MTPConfig` constructs MoE layers only when that value contains `moe`. The existing splitter fixture uses nested `qwen3_next`, while the uploaded Ornith drafter contains nested `qwen3_5_moe_text`.  
Concrete failure scenario: The new test is made green by starting with the uploaded `qwen3_5_moe_text` configuration, thereby never testing the dangerous nested-`qwen3_next` path. Alternatively, testing that path exposes a production defect whose fix moves the supposedly immutable `7207179b` pin without a declared disposition.  
Change to the plan: Specify the exact root and nested model types for the source fixture. Add an adversarial nested-`qwen3_next` case that must either be rewritten deterministically to the MoE runtime type or fail during splitting—never emit a dense-runtime artifact containing expert weights. State that any required production fix creates a new production pin and reopens the C188 carry-over assessment.

V15 — HIGH  
Problem: Ornith’s target verifier is observed, but its drafter’s distinct MoE execution path is not explicitly observed. Target verification uses `Qwen3_5BatchInvariantForward._switch_glu` and direct `SwitchLinear` calls; drafting uses `Qwen3_5MTPDraftModel.draft_block` through `Qwen3_5MoeSparseMoeBlock` and `SwitchGLU.__call__`. Positive MTP rounds plus architecture inspection do not prove those routed drafter projections executed.  
Concrete failure scenario: The real Ornith drafter loads with `Qwen3_5MoeDecoderLayer`, but a routing regression executes only the shared expert or bypasses one routed gate/up/down bank. Draft rounds remain positive and target-side E1c/E2 still pass because target verification corrects proposals.  
Change to the plan: Give the tiny round a separate draft scope and assert runtime calls to its router, shared expert and all routed gate/up/down projections, including selected-expert evidence. Add sabotage negatives for each path. Require the real Ornith smoke to record the same positive draft-path inventory, separately from target-verifier telemetry.

V16 — MEDIUM  
Problem: “Within the certified value’s 95% interval or above” is not executable from the listed point estimates `0.923` and `0.778`. The panel, denominator, interval endpoints and speed statistic are absent.  
Concrete failure scenario: Router recertification treats the point estimate as a lower bound, or computes a fresh incompatible interval, changing the intended pass threshold.  
Change to the plan: Delegate these details explicitly to the reviewed router plan: pin prompts/seeds, block size, acceptance estimator and denominator, numeric historical interval endpoints, and the exact speed statistic used for the `1.3×` gate.

V17 — MEDIUM  
Problem: One 1–2-hour runaway per entry is an operational allowance, not an upper bound; several E7 requests can independently reach their watchdogs.  
Concrete failure scenario: The reported “upper bound” is read as worst-case capacity even though a second tail forces the campaign wall cap and an incomplete result.  
Change to the plan: Call it the authorized wall cap, state that exhausting it yields ABORT/INCOMPLETE and operator disposition, and report approximately 10.5 GPU-hours nominal versus 13.5–16.5 hours with one reserved tail per full campaign.

VERDICT: DISAGREE V14 V15
