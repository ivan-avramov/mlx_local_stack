# P369 run plan v11 — round 2 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`)

Round-1 verification

- V1 — Not fully resolved. `7207179b` and the separate reviewed-head binding are correct, but the inherited paragraph still asserts `4e6d0e03` is the production pin. See V8.
- V2 — Resolved for per-entry authorization and budgeting. The incomplete campaign list is a separate scope defect; see V9.
- V3 — Resolved at plan level. The fixture requirements cover target structure, recorder/probe/emission hooks, routed projections, width-2/3 equivalence and negative controls.
- V4 — Resolved. The reviewed borrowed-panel fixture closes reconstruction circularity and correctly limits E7 to synthetic incidence.
- V5 — Not resolved. §3.1 is byte-exact, but §5 remains field-based, and the three-state model cannot support per-entry restoration. See V10.
- V6 — Not resolved. Current-artifact pinning is reproducible but does not establish identity with M6b/M27; Ornith’s extraction manifest remains optional. See V11 and V12.
- V7 — Resolved as sequencing: worker PASS performs no registry mutation and router-chain recertification precedes restoration. The registry state model nevertheless makes independent restoration impossible; see V10.

Borrowed-panel assessment: sound for E2’s within-model ON/OFF claim. It loses model-specific C84 history and traffic representativeness, but the source-bundle hash, dataset/content identity, canonical message hash and per-entry token digest prevent silent reconstruction drift. Calling E7 synthetic and descriptive is necessary and sufficient.

V8 — HIGH  
Problem: The plan still contains two active-looking production pins. The v11 header correctly names `7207179b`, but the inherited introduction still says “Production source pinned … `4e6d0e03`” and describes its refusal guard in present tense.  
Failure scenario: An implementer or reviewer updates tests or operational instructions against the stale paragraph even though the existing harness uses `7207179b`, producing contradictory evidence documentation.  
Change: Remove or historicalize the entire `4e6d0e03` paragraph so only `7207179b` defines production code. Keep prior pins solely in an explicitly historical run ledger.

V9 — BLOCKER  
Problem: The executable campaign scope does not unambiguously include all four entries. The v11 campaign order and 9–10-hour total name only Qwen3.8 uniform, Qwen3.6 and Ornith, omitting Fable. Although §3 still says “Fable first,” it is not assigned its own v11 campaign or included in the new total.  
Failure scenario: The three listed campaigns pass on `7207179b`, the operator treats phase 2 as complete, and Fable is restored without having passed this phase on the required P400+P401+P405 production tree.  
Change: Pre-register exactly four independently authorized campaigns and their order: Fable, Qwen3.8 uniform, Qwen3.6 and Ornith. Require the CLI and smoke/full binding to contain exactly one entry. State that no entry can be restored using evidence from an older production pin.

V10 — BLOCKER  
Problem: The three-state registry whitelist is incompatible with independent per-entry qualification and restoration. Starting with all four entries OFF, restoring any one C177 or P406 entry creates a mixed state outside `{golden, complete C177, complete C177+both P406}`. Section 5 also still specifies field-by-field marker matching rather than §3.1’s byte-exact derivation.  
Failure scenario: Qwen3.6 passes worker and router qualification and is restored while Ornith remains OFF. The resulting registry is rejected by `Campaign.prepare` and the live-registry test. If Ornith later fails, there is no accepted permanent state representing the correct outcome. The same issue applies to independently restoring Fable versus Qwen3.8 uniform.  
Change: Model each entry’s OFF transformation as an atomic byte substitution—Fable’s three-line C177 block, uniform’s C177 pair, and each P406 pair—and accept the exact Cartesian product of those substitutions. “Partial” must mean half of one atomic entry block, not one complete entry remaining OFF. Use one shared byte-state generator for `Campaign.prepare`, overlays and §5; delete the stale field-based rules.

V11 — BLOCKER  
Problem: Pinning whatever snapshot exists at review time proves reproducibility, not identity with the M6b/M27-certified predictor. Ornith’s extraction manifest is optional, and the plan permits merely recording its absence. E1c and greedy E2 can still pass with a wrong or degraded drafter because target verification corrects its proposals; positive draft rounds establish engagement, not predictor fidelity or usefulness.  
Failure scenario: A mutable drafter repository has changed since M27. The new artifact has compatible dimensions and generates proposals, so E1c/E2 pass, but its weights or architecture differ from the certified transplant and acceptance/speed collapse. The registry is then restored by inheriting an inapplicable M27 certification.  
Change: Make certified artifact identity mandatory: recover exact target/drafter revisions and hashes plus Ornith’s Qwen3-Next extraction manifest, or reproduce byte-identical output. If that cannot be established, rerun the applicable M6b/M27 predictor quality, acceptance and performance qualification rather than record a gap. Assert the loaded drafter—not only the target—has the certified dense/MoE architecture, depth, 256/8 routing, int4/g64 quantization, block size 3/effective two-token proposal width, target embedding/head binding and acceptance baseline.

V12 — HIGH  
Problem: The tiny-fixture plan validates the target’s MoE verifier but not Ornith’s `qwen3_next` extraction-to-drafter path. The splitter preserves the nested text model type, while `qwen3_5_mtp` selects a MoE decoder only when that value contains `moe`. Existing splitter coverage checks packed tensors but does not strict-load, bind or execute the result.  
Failure scenario: A reconstruction retains nested `model_type: qwen3_next`; runtime constructs dense drafter layers and strict loading rejects the routed-expert weights only when the worker boots. Shape-only manifest review did not expose the incompatibility.  
Change: Before GPU use, add a tiny Qwen3-Next split → strict load → bind to a tiny `qwen3_5_moe` target → one draft/verify round test. Assert `Qwen3_5MoeDecoderLayer`, expert counts/top-k, all three routed projections and quantization. Apply the same architecture assertions to the pinned real Ornith drafter.

V13 — MEDIUM  
Problem: `smoke wall_s × 6` is not a defensible full-run projection for the expanded workload. The full campaign grows reconstruction and E2 from 2 to 20 items, adds 20 E7a requests, expands E7b, and exposes full-budget heavy tails absent from the smoke. The stated 9–10 hours also excludes Fable.  
Failure scenario: A 30-minute smoke authorizes a nominal three-hour run, but one or more E7a runaways add several hours while the campaign has no default total-wall limit.  
Change: Estimate each phase from measured smoke components and full-run cardinalities, add an explicit E7 tail reserve, and report both nominal and operational upper bounds. Four nominal campaigns imply roughly 12–14 GPU hours before heavy tails, subject to smoke calibration.

VERDICT: DISAGREE V9 V10 V11
