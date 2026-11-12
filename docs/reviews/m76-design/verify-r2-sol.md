P2 — Round-1 resolution status

| # | Status | Why |
|---|---|---|
| 1 | Not resolved | B0 mentions the policy-stamp check, but its drafter-state condition cannot be evaluated safely at the current call point; see P3. |
| 2 | Resolved | PASS and LOSS are explicitly ordered and mutually exclusive; a shown sub-tolerance loss is annotated PASS. |
| 3 | Resolved | A5 is now one 40-item, single-look axis, eliminating the original 5/10-item impossibility. The stated 7.2 pp bound is inconsistent with §8’s α, however; see P4. |
| 4 | Resolved | The 260,096-token A5 rung was removed. |
| 5 | Resolved | B5 specifies the A5 runner, verifier, signals and panel adapters; B4 adds A8 packets; A4 remains panelled. |
| 6 | Resolved | P369 receives a separate campaign tuple and validates committed X/XO arms without `overlay_on`. |
| 7 | Resolved | M1 uses MTP-ON arms and is bound to the matching stage-2 PASS record and argv. |
| 8 | Not resolved | Added X coverage does not ensure N16 tier-2 coverage, and the five-item sentinel does not control known tg1 temporal variation; see P8–P9. |
| 9 | Not resolved | The desired paired-session statistic is stated, but B7 does not define a compatible API or preserve existing independent-draw consumers; see P6. |
| 10 | Not resolved | Per-axis spending is proposed, but α semantics conflict and simulation validity is not an acceptance gate; see P4–P5. |
| 11 | Resolved | P475 state, harvest and output paths are campaign-scoped, with `u4` goldens. |
| 12 | Resolved | tg2 SCREEN is only a trigger; DECIDER is the single formal look. |
| 13 | Not resolved | A FAIL branch exists, but its proposed N16-OFF comparison has no arm or harness design; see P7. |
| 14 | Resolved | `28235601` is clearly identified as the companion commit. |
| 15 | Resolved | The scope request was explicitly declined because those blocks have no within-arm repeats. |
| 16 | Resolved | Stage 4 consistently describes V MTP ON versus X MTP ON. |
| 17 | Resolved | A5/tg2 estimates are labelled unmeasured and require timed smokes. |
| 18 | Resolved | Stage 2’s claim is limited to tested cells, distributions and token windows. |
| 19 | Resolved | Existing classifier, fingerprint and report behavior receives byte-identity goldens. |
| 20 | Resolved | B7 reports look-1 PASS probability before the stage-3 Go, although P5 still leaves validity ungated. |

P3 — Location: `docs/specs/m76-tq4-certification.md` §5 B0; `src/mlx-vlm/mlx_vlm/server/generation.py:1569-1686`; `src/mlx-vlm/mlx_vlm/tq4_attention.py:345-357`  
Severity: major  
Evidence: confirmed — traced in source.  
Problem: B0 permits an absent verify stamp “only when no drafter is loaded,” but `require_policy_stamps(model)` runs before drafter loading and receives no configured predictor state. A literal implementation therefore sees no loaded drafter for both X and XO.  
Concrete failure scenario: X is configured MTP ON, but verify stamping silently fails. The widened check accepts the absent stamp because the drafter has not yet loaded; loading then continues without the required `joint_v1` protection.  
Proposed change: pass the configured `draft_kind`/predictor state into the check. Require `joint_v1` for configured MTP ON and absence for OFF, then assert the same invariant after drafter loading. Test both X and XO load-to-READY paths.

P4 — Location: §5 B7, §7 A5, §8 “Loss bound” and “Looks”  
Severity: major  
Evidence: confirmed — source and arithmetic.  
Problem: the α contract is contradictory. Current `paired_delta` uses 2.5/97.5 percentiles but an exact bound with α=.05. Section 8 instead declares total one-sided α=.025 and requires the exact bound at the same α, while A5’s stated 7.2 pp bound uses α=.05. At α=.025, 40 zero-discordance items give 8.8 pp, not 7.2 pp.  
Concrete failure scenario: one implementation preserves the current exact bound while another applies §8’s α=.025; both conform to parts of the spec but produce different bounds and potentially different PASS decisions.  
Proposed change: specify separate default-compatible parameters for interval tails and exact-bound α, then explicitly supply the M76 spent α to both. Correct A5’s bound and state whether fixed-look C173 uses .05 or .025 one-sided α.

P5 — Location: §5 B7; §8 “Looks”; §11 acceptance item 1  
Severity: major  
Evidence: confirmed — traced in the specification; the repository also records percentile-bootstrap undercoverage in `docs/open-questions.md` P358.  
Problem: simulation only gates look retention on PASS power ≥.5 at no loss. There is no requirement that simulated false PASS remain within nominal α. The tg1 simulation also lacks a nominated discordance value and a cross-session dependence model.  
Concrete failure scenario: a plan shows 60% no-loss PASS probability but 4% false PASS under a >10 pp loss. The spec keeps the look and accepts B7 because the report was merely delivered. Assuming independent sessions can further understate the error when session outcomes are correlated by item.  
Proposed change: pre-register the joint paired-data/session model and tg1 discordance rule, report Monte Carlo uncertainty, and require the upper simulation bound on false PASS to meet nominal α over the harm boundary. Otherwise recalibrate or drop the sequential look.

P6 — Location: §5 B7; `benchmark/bench/stats.py:226-299`  
Severity: major  
Evidence: confirmed — current `paired_delta` deliberately resamples each arm’s within-item draws independently.  
Problem: B7 does not define how paired sessions are represented or whether changing this behavior is global. Replacing the current resampling globally would break valid consumers whose repeated draws are independent; leaving it unchanged loses M76’s session pairing. `cluster_bootstrap`, being single-arm, cannot establish cross-arm pairing itself.  
Concrete failure scenario: an existing benchmark’s unrelated draw indices become paired, narrowing its interval; alternatively, M76 calls the unchanged API and independently resamples X and N16 sessions.  
Proposed change: add a dedicated paired-session API or explicit mode keyed by identical item and session IDs. Keep each item’s session-difference vector together per C324, reject mismatched sessions, and leave existing APIs and goldens byte-identical.

P7 — Location: §7 Stage 2 FAIL branch; §6 arm table; §5 B3  
Severity: major  
Evidence: confirmed — traced in the spec.  
Problem: the deconfounded `XO vs N16-OFF` branch is not buildable. No N16-OFF arm, committed argv, qualification, P426 lever mode, fingerprint rule, coverage plan or budget is defined; B3 currently requires MTP ON for both quality arms.  
Concrete failure scenario: stage 2 FAILs and the operator chooses the offered deconfounded stage 3, but the harness refuses N16-OFF or execution invents an unreviewed arm and analysis.  
Proposed change: make FAIL return to the operator for a spec amendment, or fully specify an N16O arm and its OFF quality harness, validation, axes and budget before presenting the branch as executable.

P8 — Location: §7 Stage 4; §8 funnel and recommendation  
Severity: major  
Evidence: confirmed — direct coverage trace.  
Problem: when stage 3 stops at tier 1 but stage 4 V−X needs tier 2, v1.1 adds X coverage only. It does not add N16 coverage, yet V must also PASS against N16 and the text calls that comparison “free.”  
Concrete failure scenario: stage-3 A1 PASSes at 100 items; stage-4 V−X is undecided and adds 200 V/X items. V−N16 cannot be evaluated on the final 300-item tier because N16 has only the first 100.  
Proposed change: every stage-4 expansion needed for the final recommendation must add paired V, X and N16 coverage, with corresponding verifier rules and budget.

P9 — Location: §7 Stage 4 reuse sentinel; `docs/open-questions.md` P611/P640  
Severity: major  
Evidence: confirmed — P611 records that frozen seeds do not freeze tg1 tool contexts; P640 limits identity evidence to assistant messages generated before the first context divergence.  
Problem: five whole-output pilot reproductions cannot validate reuse of older X results across the remaining agentic items. The sentinel can both miss item-specific temporal drift and fail because timestamps, mtimes or ASLR changed rather than because the model changed.  
Concrete failure scenario: all five pilot items reproduce, but another tg1 item receives changed tool output and V−X attributes the resulting outcome difference to `m72_v1`. Conversely, a pilot mtime change forces an unnecessary full rerun.  
Proposed change: rerun X and V contemporaneously in order-balanced blocks for A7/A8, or freeze the tool-visible environment and compare only identical-context prefixes using P640’s criterion. Update the stage-4 budget accordingly.

P10 — Location: §7 A5; §8 recommendation; `PROJECT-RULES.AGENTS.md:61`  
Severity: major  
Evidence: confirmed — textual decision trace.  
Problem: A5 pools retrieval and chain-4 into one verdict while task×rung results and the ≥.85 effective-context requirement are only descriptive. The recommendation does not make those thresholds gating, so opposing task effects can cancel.  
Concrete failure scenario: X materially regresses retrieval below .85 at one rung but improves chain-4 enough for the pooled 40-item delta to PASS; the spec then permits shipping X. The both-correct panel subset excludes the retrieval failures.  
Proposed change: retain the settled aggregate axis if desired, but make each retrieval/reasoning curve’s effective-context threshold an explicit recommendation gate, with failure/hold behavior stated per rung.
