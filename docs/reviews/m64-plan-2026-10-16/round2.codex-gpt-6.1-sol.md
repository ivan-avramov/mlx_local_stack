**P330 — V2 is suitable for approval to write the E2 specification, with corrections below. It is not yet a build or launch specification.** E1 and G1 are sound directions with narrower wording; R1 needs a verified restart recipe before execution.

Read-only review completed; no files changed or benchmarks run. This checkout is `7e7cdee4`, rather than the round-1 `170af9c0`. The aborted-chain artifacts and runnable `d4319705…` checkout were not verified here.

**P331 — Round-1 review A: finding-by-finding**

| Finding | Addressed? | Assessment |
|---|---|---|
| P319: decision-family ladder | **Partly** | One epoch per family fixes the main issue; “without bridge evidence” still permits overclaiming from a gross-drift bridge. |
| P320: C154 estimands/accounting | **Partly** | Censoring reporting improves, but operational versus matched-budget capability remains unresolved; accelerated timer testing is absent. |
| P321: unsafe ownership downgrade | **Yes** | P317 is withdrawn and live unreadable-order candidates remain uncertain; descendant obligations must explicitly survive delayed reconciliation. |
| P322: scheduling | **Partly** | Williams counterbalancing is appropriate, but randomization, block size, cache preparation and realized-order recording remain unspecified. |
| P323: immutable dependency snapshots | **Partly** | Dependency/runtime identity and repeated verification are added; atomic adoption, extension inventory and immutable active-chain resolution need explicit requirements. |
| P324: acceptance/power | **Partly** | Contrasts, accounting and power work are added; subjective equivalence, missing judges, token primary endpoint and full multiplicity rules remain undefined. |
| P325: common arm contract | **Partly** | A real adapter contract is proposed, but several required runtime proofs are implicit rather than mandatory contract fields. |
| P326: fairness boundary | **Partly** | Native prompts/tools are declared treatment; web policy remains undecided and recording roles/history does not define their permitted handling. |
| P327: work order/opencode boundary | **Yes** | Specification first, identity split, shared validation, unchanged generation implementation and a separate current dsh adapter address it. |
| P328: cheaper designs/cost | **Partly** | Shared contemporary reference and gross-drift anchors are adopted; screening is omitted, and the bridge cost remains unsupported. |
| P329: aborted-chain evidence | **Partly** | Rerunning s2 preserves the intended replication; preservation of every artifact, exact restart identity and lossless archival still need a concrete recipe. |

**P332 — Round-1 review B: finding-by-finding**

| Finding | Addressed? | Assessment |
|---|---|---|
| P1: unsafe ownership downgrade | **Yes** | Fail-closed uncertainty and exact process identities are retained. |
| P2: cumulative model selection | **Partly** | Decision families are frozen; the cross-epoch bridge exception is still too permissive. |
| P3: adoption canary limits | **Partly** | Exact snapshots, offline tests and two-model anchors are added; release-specific timeout testing and adoption rules remain incomplete. |
| P4: opencode-only runner | **Yes** | An `ArmAdapter` contract replaces scattered client-specific conditionals as the proposed architecture. |
| P5: estimand/fairness | **Partly** | Controlled external settings and native treatment are declared, but C154 and the web-policy choice prevent a fully controlled opportunity claim. |
| P6: order/thermal/cache | **Partly** | Counterbalancing and separate latency capture address most concerns; cache reset/warmup and actual sequence generation remain open. |
| P7: censored token endpoint | **Partly** | Union-exclusion and lower bounds are added; neither alone validates all-task token superiority. |
| P8: generation identity | **Yes** | Snapshot identity remains in a combined generation identity rather than becoming a covariate. |
| P9: historical dsh | **Yes** | The historical runner remains frozen; the new adapter has a separate entry point. |
| P10: untouched opencode boundary | **Yes** | Thin wrapping plus regression, replay and injected-positive checks is the right boundary. |
| P11: acceptance/power | **Partly** | Per-language/session reporting and power simulation improve it; complete decision rules and valid equivalence inference remain unfinished. |
| P12: C164/resume | **Partly** | Resume is restored and s2 reruns fully; explicit operator supersession and verified artifacts/identity are still required. |
| P13: optimistic cost | **Partly** | The estimate is corrected and made smoke-dependent, but its numerical range remains a planning assumption. |
| P14: external provenance | **Partly** | Durable sources are promised for the spec, rather than attached and verified in v2. |

**P333 — E1 still leaves a ranking loophole.** E1.3 correctly says the bridge cannot certify equivalence, while E1.4 permits transitive rankings with “bridge evidence.” Those statements conflict. An 8–12-item bridge can establish compatibility and reveal gross drift; passing it cannot transport an unmeasured finalist’s ranking across epochs.

Also, `$STACK_WORKDIR/<tool>-<ver>` does not uniquely identify a snapshot: the same version can have different resolved dependencies, runtime or extensions. Use a content-addressed snapshot directory and resolve it once into the chain manifest. Adoption must never retarget an active chain.

**P334 — E2 still conflates equal configured ceilings with equal opportunity.** The current gate explicitly recognizes opencode’s 60-minute interruption and missing trailing usage ([token_turn_gate.py](mlx_local_stack/benchmark/bench/token_turn_gate.py:30)). V2 cannot call the resulting primary comparison matched-budget capability merely because identical numbers reach the wire.

Make the primary estimand **operational scaffold performance under common configured ceilings**, counting client cuts as failures and disclosing unequal effective opportunity. Reserve matched-budget capability claims for releases demonstrated to deliver the prescribed opportunity. Add an accelerated timeout contract test and release-specific long-request evidence.

Token lower bounds do not establish token savings. A challenger’s apparently lower total can reflect missing generation. Require complete accounting or bounds sufficient to establish the claimed direction; otherwise label token superiority unresolved. Union-exclusion remains a sensitivity analysis, not the primary repair.

**P335 — The statistical prescription can falsely certify equivalence.** “Two-stage cluster bootstrap” alone is insufficient. With zero observed paired discordances, ordinary empirical resampling produces a degenerate zero-difference interval even though unseen discordance remains possible. Power simulations using only observed near-ceiling discordance can repeat that optimism.

The spec must validate interval coverage and equivalence error rates under sparse/zero discordance, plausible unseen discordance and shared loaded-instance effects. Report session-specific inference; two loads do not support precise population inference over loads.

Other necessary definitions:

- One primary token quantity and denominator; the other token categories remain reported components.
- Whether accuracy equivalence must hold in every language/session cell, and how those gates combine.
- Multiplicity across accuracy, token and subjective claims—not merely the four scaffold contrasts.
- Subjective equivalence margin, confidence interval, missing-judge policy and minimum coverage.
- Dependence between judges and the two presentation orders. They are repeated measurements, not extra independent items.
- A tie-compatible length-adjustment estimator; “logistic regression, ties 0.5” is not yet a complete analysis rule.

The committed [M64 acceptance rule](mlx_local_stack/docs/PLAN.md:178) still requires subjective equivalence; v2 does not explicitly preserve its margin.

**P336 — V2 introduces an enforcement mismatch.** “Egress = loopback only” cannot be verified by intermittent socket sampling. Sampling can miss short connections, and loopback can reach an outbound proxy. Either enforce the policy at a defined boundary or describe socket sampling as observation with limited coverage.

Choosing no web is reasonable, but it creates a new reference treatment. Regression parity should therefore mean: **the old carrier reproduces the old path; the new carrier differs only by the approved web restriction**. Do not demand output parity between those treatments.

The common contract should explicitly enumerate M50 entry/exit checks, registry/model/predictor/worker identity, corpus/grader integrity, per-request sampling and resolved headroom, session routing, and cancellation reconciliation. Current A4 is indeed opencode-specific ([chain_ops.py](mlx_local_stack/benchmark/bench/chain_ops.py:576)).

**P337 — G1 is acceptable as a proposal, with two edits.** Preserve all recorded descendant reconciliation obligations even after a root disappears. Use one monotonic, globally bounded reconciliation deadline, then fail uncertain if any obligation remains unresolved. The existing regression already requires a live unreadable eligible process to cause uncertain cleanup ([test_c151_start_time.py](mlx_local_stack/benchmark/bench/tests/test_c151_start_time.py:243)).

Remove the claim that the observed offenders are harmless mdworker/XPC services unless the exact process identities and evidence support it. That claim is unnecessary to justify bounded rechecking.

**P338 — R1 is conditionally sensible, not yet executable from this review.** “GPU idle” does not prove zero decision cost: another long tail or residual abort could overlap the next launch window. Describe resumption as a bounded evidence investment.

Before launch, require:

- A verified runnable checkout whose computed probe identity exactly matches `d4319705…`, plus matching carrier, dependencies, registry and runtime provenance.
- A hashed archive inventory preserving s1, validated partial s2, failed outputs, manifests, logs, receipts and exit status. Preserve referenced evidence paths or document their relocation.
- A concrete restart command/output layout that cannot overwrite the original attempt; link the replacement s2/reload record to s1.
- Clean process/router checks and the normal runtime preflights.

The runner overwrites `chain.json` when writing state ([run_tg1_chain.py](mlx_local_stack/benchmark/chains/c147/run_tg1_chain.py:212)), so archival must precede relaunch. C164’s old baseline ruling must be explicitly superseded by the operator’s approval of E1/E2, not declared superseded merely by drafting v2.

**P339 — Concrete approval recommendation and edits**

| Item | Operator go now? | Required edit |
|---|---|---|
| E1 | **With changes** | Forbid ranking transport from gross-drift anchors; use content-addressed snapshots and atomic adoption; label bridge cost unmeasured. |
| E2, specification only | **Yes** | Make P334–P336 mandatory questions and acceptance requirements in the spec; choose web policy before freezing it. No build approval implied. |
| G1 | **With changes** | Preserve descendant obligations, define the global deadline, retain fail-closed behavior and add adversarial tests. |
| R1 | **Conditional** | Explicitly approve the C164 amendment and verify the archive/restart/provenance checklist before launch. |

Replace E1.4 with: “Cross-epoch results remain descriptive. Adoption anchors do not authorize transitive rankings. A selection decision requires all finalists under one epoch, or a separately approved, adequately powered transport design.”

Replace E2’s endpoint wording with the operational estimand above, and state: “No token-superiority claim from incomplete lower-bound accounting; no equivalence claim from an interval method unvalidated for sparse discordance.”

AGREE WITH CHANGES: close the cross-epoch ranking loophole; distinguish operational from matched-budget performance; validate sparse-data inference and censored-token claims; complete enforcement and arm contracts; preserve G1 descendant obligations; verify and authorize R1’s exact restart provenance
