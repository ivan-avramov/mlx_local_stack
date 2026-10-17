Q1 — blocker — E1 / Acceptance (`p369-mtp-certification.md:14-19,53-55`)

Failure scenario: the tiny random model passes while neither deployed target path is exercised. The picks use mixed affine 4/8-bit or uniform 4-bit weights, quantized sidecars, different KV modes, and different `mtp_verify_scan` policies. Production-only branches in `quantized_verifier.py`, `exact_speculative_verify.py`, and Metal shape gates can still alter verifier logits. Also, the existing tiny Qwen fixture is one full-attention layer, not hybrid recurrent+attention.

Fix: split E1 into:
- mechanism proof on a genuinely hybrid tiny model;
- quantized tiny fixtures for target and drafter;
- production conformance for each exact deployed `(target revision, quant, drafter revision, KV mode, verify policy)` using real weights and sidecars, shadow-comparing verifier logits/post-transform probabilities, cache state, and ordinary singleton decode.

Define matched as the actual sidecar per pick; mismatched as a compatible independently randomized/forced-low-acceptance drafter. Include a high-acceptance case because that is worst for M3/M4.

Q2 — blocker — E1 statistic and Acceptance (`:16-18,53-54`)

Failure scenario: a χ² test fails to reject and is reported as “exact.” That is not an equivalence result. The endpoint, whether `10^5` means per arm or total, prefix length, support size, multiplicity, and alternative distribution are unspecified. Position-wise marginals can pass while the joint first-k-token law differs. Even for a binary worst case, approximately 105k samples per arm are needed for 90% power against a 1% difference at α=.001; multinomial prefixes can require more.

Fix: use exact finite enumeration as the tiny-model primary result and paired, position-keyed RNG identity plus bitwise production conformance for real models. If frequency testing remains, pre-register one joint k-prefix endpoint, samples per arm, multiplicity correction, least-favourable alternative, and an upper confidence bound establishing `TV < 1%`; remove “no detectable shift” as an exactness acceptance criterion.

Q3 — blocker — E2 M58 classification (`:20-22`)

Failure scenario: a threshold divergence is labelled “expected” and certification passes. M58 established real representation differences at SDPA dispatch thresholds; at T>0 any surviving logit difference changes the distribution, even if greedy top-1 does not flip. Fable uses `joint_v1`; the uniform pick uses another serving configuration, so one classification cannot cover both.

Fix: threshold prompts must force actual verifier blocks to straddle each boundary and record the serving policy/counters. Compare verifier and singleton-decode logits after sampling transforms for each pick. Under an exactness claim, any output-relevant mismatch fails; “near tie” may diagnose the cause but cannot make it exact. Otherwise rename the claim to bounded non-neutrality.

Q4 — high — E3/E5/E6 serving-path scope (`:23-27`)

Failure scenario: tests pass on continuous batching while deployed chat remains broken. With session caching enabled (`MAX=1` lean, `2` daily), `/v1/chat/completions` resolves a `PromptCacheState` and uses cached-session inline B=1 MTP. Continuous batching is mainly the uncached/non-chat path.

Fix:
- E3 must make two router HTTP turns with one explicit forwarded session ID, assert backend `cached_session`, preserve message history, and compare token IDs, KV, recurrent snapshots, and next-turn output.
- Retain continuous-batch coverage as a secondary supported path.
- Add E5b proving cached requests with processors fall back and execute zero draft rounds.

Q5 — blocker — M4 fix (`:34-35`; `mtp.py:749-783,1190-1243`)

Failure scenario: code scans for EOS only after `accept_verified_tokens()` and `verify.commit()`. KV, recurrent state, drafter cache, shared-KV positions, and acceptance history have already advanced past the emitted stop.

Fix: determine the emitted prefix before both drafter acceptance and target transaction commit, truncate `accepted/new_tokens` consistently, then commit the shortened transaction. Apply this to singleton inline and batched loops; wire stopping criteria into inline MTP. E3 must cover stop at every accepted-draft position and assert recurrent/KV state, not only output text.

Q6 — blocker — M3 fix and E4 (`:25,36`; `ar.py:868-872`; `utils.py:2778-2831`)

Failure scenario: “per-token budget check” still differs from plain decode. Plain decoding uses `pop_forced_token_id()` and may force `newline` followed by `</think>`; current MTP directly emits only `thinking_end_token_id`. Criteria are currently advanced after yield, too late to decide the pre-commit prefix. A crossing on the verifier bonus also needs different cache handling from one on an accepted draft.

Fix: precompute the exact plain-decoding emission decision before commit without double-advancing criteria, preserve the entire forced sequence, and commit through the token preceding each forced output. Test every block position, mismatch/full-accept and bonus cases, plus next-turn state. Replace or narrow existing tests that explicitly bless suffix/MTP block overshoot.

Q7 — medium — M2/M5 minimality and tests (`:26-27,37-39`)

Failure scenario: larger state-carry implementations add risk, while weak tests pass even though seeds or processors were ignored.

Fix:
- M2: use the already-established fail-closed design—any continuous-batch processor selects plain `GenerationBatch`. Assert no speculative rounds.
- M5: plain fallback or explicit request rejection is the minimal fix for seeded continuous-batch speculation.
- E6 must use distinct seeds, changed admission/coalescing order, and a late second row; same-seed repeatability alone can pass when every request silently uses the default seed.

Q8 — high — E7 and interim rule (`:28-30,45-47`)

Failure scenario: zero events in C84 plus selected tg1 transcripts is called a real-traffic rate. This is a convenience replay, C84 is predominantly independent short requests, the denominator is undefined, and zero events only gives an upper bound of roughly `3/n` at 95% confidence. The interim decision also ignores M3 despite the deployed thinking budget.

Fix: define events and opportunities, report request- and accepted-block denominators with confidence bounds, validate counters with scripted positives, preserve tg1 multi-turn session continuity, and report M3/M4 separately. Because exactness is the requirement and both are known defects, keep the daily driver MTP-OFF until fixes ship; retaining ON would be an explicit risk acceptance, not certification.

Q9 — medium — nvfp4/full-suite gate (`:8-10,54-55`)

Failure scenario: acceptance requires a green full fork suite, but the recorded pristine baseline already fails `test_general_quantized_verifier_matches_decode[127-nvfp4-4-16]`. Execution either stalls or silently waives a verifier-exactness failure.

Fix: add an explicit gate: repair it, or document a tracked format-specific xfail with proof that neither deployed artifact uses nvfp4. Do not describe the suite as green while it remains an unrecorded exception.

Q10 — medium — release, recertification, and shared scope (`:42-50`)

Failure scenario: prior certification is reused across changed serving code or Fable’s changed KV/verify state; shared MTP-loop edits regress another MTP family; suffix’s documented budget overshoot is accidentally treated as certified.

Fix: re-certify both picks separately on their current model/drafter revisions, quant, KV mode, verify policy, cached-session backend, and all supporting quality axes, with fresh OFF controls and manifest/worker arm identity after the submodule bump. Run targeted shared-loop regressions for other MTP drafters. Explicitly state that suffix and non-MTP draft kinds are outside P369 and remain OFF/uncertified. Keeping M63 descriptive is correct.

VERDICT: AGREE WITH CHANGES Q1 Q2 Q3 Q4 Q5 Q6 Q7 Q8 Q9 Q10
