The detached request does select the plain decode path: `_inline_draft_kwargs(None, None, ...)` returns `{}`, speculative prefill captures are absent, and `generate_step` uses its ordinary loop. The stamped verify policy is consulted only under `speculative_verify=True`; the retained drafter caches and target bindings are not read. Thus it is a valid same-loaded-target plain-path comparison, but not a deployed-OFF-worker equivalent.

Q35 — HIGH — §2.5 — Cache identity is incorrect. A fresh chat ID creates a fresh `PromptCacheState`; reusing ON’s target cache would replay from mutated state and invalidate independence. Require the same target/model/policy objects but fresh, identity-disjoint, initially empty cache trees for ON, OFF1, and OFF2. Release prior session/recorder references before the next trajectory.

Q36 — HIGH — §2.5, §§1/6 — C2 cannot be attributed specifically to reload nondeterminism. The deployed OFF process also differs by having no drafter load, no Fable policy stamping/self-test, different resident memory and allocator history, and a new process rather than same-PID unload/reload. Rename it a cross-load/configuration comparison. A difference is consistent with P391 but does not identify its mechanism; a match is only evidence for the sampled cells. Keep E1c explicitly scoped to “plain decoding on the same MTP-loaded target instance.” If causal reload attribution is required, add matched repeated loads with identical argv/configuration.

Q37 — HIGH — §2.5/§3 — Control acceptance and precedence need definition. C1 must compare raw rows, transformed distributions, emitted forced-token sequence, commit-state hashes, probe logits, finish reason, and expected request counts. Early termination, timeout, missing offsets, or failure to emit every forced token is INVALID. State precedence explicitly:
- C1 failure/incompleteness: abort that pick; no E1c verdict or measured bound.
- C1 passes, primary pair differs: finish that pick’s E1c for the bound, then skip E2/E7.
- Primary passes, C2 differs: same-instance E1c passes, but deployed cross-load equality is unestablished.
This resolves §2.5’s stop rule against §3’s finish-on-failure rule.

Q38 — MEDIUM — §2.5 — Detachment must span the complete request. `ResponseGenerator.generate()` reads drafter fields on the caller thread, while `_process_cached_request` reads them later on the GPU thread; `generate()` can return its iterator before completion. Hold both fields at `None` from before submission through full response exhaustion/closure and worker-idle confirmation, exclude concurrent ingress, and restore both saved objects in `finally`. Assert `_inline_draft_kwargs == {}`, no speculative prefill captures, and no production verifier calls; separately tag the intentional transactional probes.

Q39 — MEDIUM — §§2.1–2.2/§3 — v4 wording is now stale. E1c ON and primary OFF are no longer separate subprocess arms, “ON has positive rounds on every request” is false for detached requests in the ON process, and §2.2 still calls the primary reference a fresh subprocess. Rewrite assertions per trajectory and update smoke’s “both arms” terminology.

Q40 — MEDIUM — §§2.5/4 — Cost accounting is wrong. Relative to v4’s ON plus one cross-load OFF, v5 adds OFF1 and OFF2 while retaining cross-load OFF: approximately +2 replays per cell, not +1. For five 160-token E1c cells, generated/replayed positions rise from roughly 1.6K to 3.2K per pick, with three OFF-side hash/probe passes. Recalibrate the estimate and watchdog budget accordingly.

VERDICT: DISAGREE Q35 Q36 Q37 Q38 Q39 Q40
