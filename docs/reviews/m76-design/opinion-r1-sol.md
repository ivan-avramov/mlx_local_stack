P1
- Location: §5 B0, lines 101–110.
- Severity: blocker.
- Evidence: confirmed — `tq4_attention.require_policy_stamps()` still requires every module to carry `joint_v1`, while MTP-OFF makes `_apply_mtp_verify_from_env()` return `None`.
- Problem: B0 relaxes configuration and `require_environment`, but not this later load-time refusal.
- Failure scenario: XO starts without `mtp_verify_scan`; model loading fails before READY, so stages 1–2 cannot run.
- Proposed change: make `require_policy_stamps()` accept absent verify policy only for drafter-OFF, while still requiring `fused_v1`; add a served XO load test.

P2
- Location: §8 verdict per axis, lines 222–227.
- Severity: blocker.
- Evidence: confirmed — PASS and LOSS SHOWN overlap. A delta of −3 pp with CI [−4, −2] satisfies both PASS (`point ≥ −5`, bound ≤10) and LOSS SHOWN (CI excludes zero favouring N16).
- Problem: implementations can produce opposite verdicts and funnel actions from the same evidence.
- Failure scenario: one implementation recommends X; another flags it and skips tier 2.
- Proposed change: define precedence and mutually exclusive states. Recommended: thresholds decide PASS; annotate a statistically shown sub-threshold loss separately. LOSS SHOWN applies only when a threshold fails.

P3
- Location: §7 A5 and §8 loss-bound rule, lines 200 and 217–238.
- Severity: blocker.
- Evidence: confirmed — A5 has only 5 prompts at look 1 and 10 final per rung. With zero discordances, the one-sided 95% exact upper bounds are 45.1% and 25.9%, both above 10%.
- Problem: no A5 rung can PASS, even with perfect agreement, yet every mechanical axis must PASS.
- Failure scenario: all A5 outputs match, tier 2 runs automatically, and X still cannot be recommended.
- Proposed change: provide enough independent prompts per rung for the adjusted exact bound—at least 29 for ordinary 95%, and more under the final sequential confidence—or define and justify a larger valid pooling unit.

P4
- Location: §5 B5, §7 A5/A8, and §7 panel paragraph.
- Severity: blocker.
- Evidence: confirmed — current `p426_wave1.AXES` and `p426_plan.plan_leg()` support only Math500, cjudge, vision, reasoning and M1; `p426_panel` supports those plus tg1. B5 only defines IDs and does not add A5 runner/verifier/signals/panel adapters; B4 does not add an A8 panel adapter. The spec also drops A4 from the panel despite the existing P426 reasoning panel and the standing subjective-quality rule.
- Problem: mandatory mechanical and subjective evidence cannot be generated.
- Failure scenario: execution reaches A5 and either rejects the unknown axis or produces no pair-verifiable rows; acceptance criterion 4 and the recommendation are unattainable.
- Proposed change: specify the A5 runner, strict scoring unit, seeds, plan/verifier/signals/panel adapters, and A8 panel artifacts; retain the A4 reasoning panel.

P5
- Location: §5 B2 and §7 Stage 2.
- Severity: blocker.
- Evidence: confirmed — `orchestrate.PICKS` is keyed only by model name and already contains this model’s native16 tuple. Preparation first requires `registry_states.classify()` against the 16 native states, requires the committed root to be MTP-OFF, and builds ON through `overlay_on()`, which also rejects KV-arm states.
- Problem: “PICKS gains a TQ4 tuple” cannot coexist under the current key, and X/XO are rejected before the cited preparation changes run.
- Failure scenario: using X fails the all-OFF gate; using XO fails strict classification/overlay generation; replacing the existing tuple breaks native16 P369 consumers.
- Proposed change: introduce a distinct campaign-tuple identity, preserve the existing native16 tuple, and explicitly teach preparation/overlay generation to validate committed X/XO through `classify_kv_arm`.

P6
- Location: §7 M1 and §5 B2/B3.
- Severity: blocker.
- Evidence: confirmed — full `qualify --kv-arm --predictor on` currently refuses any non-empty KV delta as uncertified; only `--engagement-only` bypasses that gate. Current P426 M1 passes the arm directly as `--predictor off|on`.
- Problem: X cannot run the required MTP-ON M1 leg, while running predictor OFF would confound KV format with MTP state.
- Failure scenario: X M1 refuses before measurement, or the reported N16/X memory comparison is actually MTP-OFF versus MTP-ON.
- Proposed change: define both M1 arms as predictor ON and permit full X qualification only when bound to Stage 2’s exact P369 PASS and exact committed argv.

P7
- Location: §4 S22-P3, §7 Stage 4, and §8 funnel.
- Severity: major.
- Evidence: confirmed — Stage 4 runs only V legs and reuses Stage 3 X legs, but tier 2 must add coverage to both arms. Stage 3 may not have collected X tier 2 for an axis that passed X–N16 at look 1.
- Problem: a V–X UNDECIDED result cannot receive paired tier-2 coverage.
- Failure scenario: X–N16 Math500 passes at 100; V–X is undecided at 100; the required additional 200 X rows do not exist.
- Proposed change: against settled constraint C323/S22-P3, permit new X tier-2 legs when Stage 4 needs them, or accept unconditional X tier-2 collection before Stage 4.

P8
- Location: §8 agentic statistic, lines 217–230.
- Severity: major.
- Evidence: confirmed — current `stats.paired_delta()` resamples items first and independently resamples each arm’s draws inside each item. It cannot preserve sessions as shared outer clusters or paired session schedules.
- Problem: treating sessions as per-item draws destroys session-level correlation and can materially narrow the loss bound.
- Failure scenario: one globally adverse loaded instance affects all 43 items, but itemwise resampling disperses that effect as 43 nominally independent observations and produces a false PASS.
- Proposed change: against settled constraint C323/S22-P8, use sessions as outer clusters with paired arms and items resampled within session; with only 2–3 sessions, report per-session bounds or collect enough independent loads for a defensible aggregate.

P9
- Location: §8 O’Brien–Fleming looks and zero-discordance handling.
- Severity: major.
- Evidence: confirmed — `stats.paired_delta()` hard-codes the zero-discordance bound at one-sided 95%; `_loss_bound()` consumes it unchanged. No confidence-level parameter exists.
- Problem: the degenerate-cell path bypasses the stated 99.4% look-1 boundary, so the claimed sequential error control does not hold.
- Failure scenario: tg1 look 1 with 0/43 discordances gets a 6.7 pp bound and PASS; at the look-1 spending level the exact bound is approximately 13%, requiring UNDECIDED and s3.
- Proposed change: parameterize bootstrap quantiles and exact discordance bounds by each look’s spent alpha; test degenerate and non-degenerate cells at both looks.

P10
- Location: §5 B1 and §7 Stage 1 output.
- Severity: major.
- Evidence: confirmed — `p475_kv.py` still hard-codes `$STACK_WORKDIR/p475`, `state.json`, `benchmark/results/p475`, harvest publication paths, and MATRIX paths. B1’s listed edits omit these, while the repository already contains the shipped u4 dossiers/table.
- Problem: f45 is not isolated from the existing P475 campaign, contrary to the promised byte-identical u4 consumer.
- Failure scenario: existing u4 state refuses the M76 base, or generalized harvesting mixes/archives u4 dossiers and regenerates the shipped table from the wrong campaign.
- Proposed change: make scratch, state, dossiers, harvest paths and matrix output campaign/pick-scoped; pin tests that the u4 paths and table remain byte-identical.
