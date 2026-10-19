I cannot approve v1. The worker-level approach is feasible, but several acceptance paths can pass without proving the parent claims.

Q15 — BLOCKER — §2 E1c row alignment  
Problem: “rejected-draft rows are not compared” is unsafe if it excludes the first rejection row. In `_mtp_rounds`, `base_position=emitted`; verifier row 0 corresponds to the next emitted position. The first rejected draft’s target replacement is emitted and output-relevant. Only rows after that rejection are counterfactual. Position 0—the initial prefill bonus—is not observed by the proposed verifier wrappers.  
Fix: Compare position 0 separately. For every round, persist `emitted_before`, `verify_input`, `accepted`, `n_emit`, terminal index, and compare every emitted target row: accepted drafts plus the first rejection replacement, or the bonus when all drafts accept. Exclude only unreachable tail rows.

Q16 — BLOCKER — §2 Q12 checkpoints  
Problem: Q12 says after each commit; v1 checks only the first commit past each threshold and request end. This misses ordinary block commits and width-one `_mtp_commit_pending_token` commits used for forced and terminal tokens. “One fixed probe token” is also ambiguous.  
Fix: Check prompt-end state and every target commit. At each aligned logical offset compare every cache leaf’s offset, shape/dtype, valid K/V—including TurboQuant scales/biases and metadata—every recurrent/GDN state component, and the full next-token logit vector produced from a fixed input token through a transactional forward followed by abort. Never hash preallocated tails.

Q17 — HIGH — §2 E1c replay/comparator  
Problem: The OFF forcing processor is viable only if it records logits before modification and is injected solely into the OFF arm. It does not change the T>0 target forward kernel, but it can silently force any accidentally retained drafter to fall back to plain decoding. Comparing `_filter` output bitwise is sufficient but stronger than distributional equality; additive-logit constants could false-fail. Raw max-|Δ| does not provide the promised non-neutrality bound.  
Fix: Assert OFF has no loaded drafter and ON has positive MTP rounds. Compare canonical transformed log-probabilities/probabilities after `_filter` and temperature, with bit-level support/value checks. On mismatch report support changes, worst per-token probability delta and TV distance; near-tie margins remain diagnostic only.

Q18 — BLOCKER — §2 Q14 and engagement  
Problem: “Which kernels the tuples hit is recorded” weakens Q14 from an acceptance criterion into telemetry. The manifests describe all 498 text modules as quantized for both picks—4-bit uniform or mixed 4/8-bit—so the dense `exact_speculative_verify` kernel may not be reachable on either real target; the bf16 vision sidecar is outside verifier decoding. Spying on the source module can also miss aliases imported into `speculative.ops.linear`. E1c/E2 could otherwise pass after an unnoticed plain fallback.  
Fix: Before GPU approval, inventory eligible real modules and state which tuple must hit each kernel. Spy on the aliases actually called in `speculative.ops.linear`; require quantized verifier hits and positive MTP rounds per request. If no real tuple can hit the dense kernel, Q14 cannot be satisfied as written: amend the parent claim/operator scope or explicitly retain it as phase-1 fixture evidence.

Q19 — HIGH — §3 E1c straddles  
Problem: `T−64` must be the final post-template token count, not source-text length. Fable has per-request straddle counters; uniform/per-query has no policy object, so merely recording intended boundary lengths does not prove a real verifier block crossed a threshold. Early natural termination can also prevent crossing.  
Fix: Construct and assert the exact templated token count. Capture actual verifier key lengths and planner classifications. Require a per-request Fable counter delta and, for uniform, observed per-query TurboQuant calls spanning both sides of every threshold. A prompt that terminates before coverage is invalid and must not pass.

Q20 — HIGH — §2 worker fidelity  
Problem: Intercepted `uvicorn.run` plus `TestClient` is sound for CLI environment export, lifespan preload, endpoint templating, and cached-session generation. It does not exercise process isolation, uvicorn/SSE cancellation, router header forwarding, readiness, or inherited-environment behavior. `cli.main` only conditionally writes draft model/kind, so stale ambient values matter.  
Fix: Call this worker conformance, not router conformance. Start each arm in a sanitized subprocess; resolve the `"mlx_vlm.server:app"` uvicorn string after CLI setup; assert imported source paths resolve to the reviewed checkout, backend is `cached_session`, APC is disabled, the expected drafter state is loaded, and final draft counters are positive only in ON. Keep router claims for the later real-chain plan.

Q21 — HIGH — §3 E2 corpus  
Problem: The uniform artifact names are wrong: they are `*.c84bundle-after-tq4-20260914.jsonl`, not `after-native16`. More importantly, matching only `prompt_tokens` cannot establish that reconstructed requests equal the frozen private C84 requests; different prompts can tokenize to the same length.  
Fix: Retrieve the canonical raw requests or compare a canonical serialized-request/token-id hash retained from C84. If neither exists, pin builder commit, dataset artifacts and token IDs, and rename the evidence “C84-item reconstruction,” not the frozen C84 set. A missing reconstruction must fail coverage rather than be silently removed.

Q22 — HIGH — §3 E2 greedy path  
Problem: T=0 does exercise a distinct path: `_mtp_verify_target(sample_target_tokens=True)` reaches `speculative_argmax_from_hidden` and quantized argmax, unlike E1c’s projected logits. Token identity alone can pass if ON falls back to plain. The 1,024/8,192 prompts do not cover the upper threshold regimes.  
Fix: Require spies on `speculative_argmax_from_hidden` and the actual quantized-argmax alias, plus positive verifier rounds for every ON request. Retain OFF/ON/OFF-reload. Report E2 as first-512-token identity, and add 32,768/65,536 straddles or explicitly narrow “long context” to the tested regimes.

Q23 — BLOCKER — §2/§3 E7 classification  
Problem: The proposed classes do not reconstruct the pre-fix bugs precisely:
- `_mtp_plain_emission` never sees the initial first bonus, so its wrapper cannot count first-token M4b.
- M4a requires a token committed after the stop, not merely any verified row after it. A trailing rejected/bonus row was not committed pre-fix.
- M3 overshoot requires at least one token emitted after the criterion requested a forced token; triggering on the block’s final token is not overshoot.
  
Fix: Reconstruct against `0b43dae4^`: M4a iff the stop lies among accepted drafts and at least one later accepted draft would have committed; M4b separately observes initial-token terminal and a terminal pending replacement/bonus; M3 records trigger index and pre-fix overshoot count. Add live scripted positives for each exact predicate.

Q24 — HIGH — §3 E7 statistics and continuity  
Problem: Clopper–Pearson over blocks treats correlated blocks within a request as independent. Also, replaying recorded assistant history while generating a different assistant answer can break prefix reuse, turning E7b into repeated cold prefills rather than session continuity.  
Fix: Use request-with-event/request as the inferential CP rate. Report class-specific eligible-block rates descriptively, or use request-clustered bounds. For E7b, append each newly generated assistant turn to the next request and assert nonzero cached-token reuse after turn one; otherwise label it teacher-forced exposure, not continuity. Report time-boxed sessions as censored.

Q25 — HIGH — §4–§5 operations  
Problem: The refusal checks are incomplete and `:8000` is not the worker port (`8091` in the stack); interception binds neither. There are no per-request hang/runaway stop rules. The 100-minute estimate is optimistic: E1c alone contains roughly 215K prefill tokens per pick, E2 has three potentially 10K-token arms, and one 102,400-token E7 runaway can take hours.  
Fix: Add an exclusive run lock; inspect full command lines and ports 8000/8091; verify disk space, temperature/power, source paths, and post-lifespan model/thread cleanup. Add per-request and total-wall watchdogs, atomic exit-status/result files, and a rule that timeout/censoring cannot pass E7. Reserve roughly 2–3 hours plus full-suite/setup time.

Q26 — HIGH — §6 P387  
Problem: The proposed hybrid—MTP tuple from the pin, sampling from live—leaves tests dependent on a sibling checkout and obscures which registry is certified. `_stack_registry()` currently selects the sibling by default, while `deployed_sampling()` then requires live `draft_kind == mtp`, causing C177 failures.  
Fix: Make ordinary tests deterministic: both certified MTP tuple and sampling come from the pinned fixture. Add a separate opt-in live-registry integration test that semantically compares all fields, accepting either exact ON or the narrowly normalized C177 absence of `draft_kind`, `draft_model`, and Fable `mtp_verify_scan`, while also requiring the C177 marker. Do not let sibling presence alter the normal suite.

Q27 — HIGH — status/provenance  
Problem: The plan names round-7 tip `124de41f`, but the reviewed code is `4e6d0e03`. Building the harness creates a later test-only commit, further separating harness provenance from production provenance.  
Fix: Pin production source `4e6d0e03`, record the harness commit separately, and fail unless the production-code diff from `4e6d0e03` is empty. Record stack, mlx-serve, fixture/overlay, executable, and imported-module paths in the manifest.

VERDICT: DISAGREE Q15,Q16,Q17,Q18,Q19,Q20,Q21,Q22,Q23,Q24,Q25,Q26,Q27No follow-up needed.
