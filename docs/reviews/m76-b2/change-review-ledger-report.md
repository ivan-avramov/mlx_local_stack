# M76 B2 — change review (four-eyes light, opinion) — ledger

Implementer Claude Opus (`claude -p`), test-writer Claude Sonnet (session `20f27118-9adf-49ee-ad2b-cc4e68468b8d`, continued; delivery 2
verdict merge, 311 amended frozen tests passed). Panel: Sol (`gpt-5.6-sol-high`) and GLM (`glm-5.2-high`) via `cursor-agent --mode
ask`, read-only snapshot (candidate applied, spec v1 + errata v1.1, both reports, frozen tests); user instructions unconfirmed. Both
exit 0, valid. Raw: `opinion-change-{sol,glm}.md`. GLM answered the three questions (no wrong-arm / mode / commit / argv
certification; no PASS without the `m72_exact` routes; no existing-pick change) and found nothing blocking; Sol found two blockers the
mocked tests could not see.

| # | raised by | finding | disposition |
|---|---|---|---|
| 1 | Sol P1 (blocker), GLM F3 | `qualify` on a mode arm defaults to the old production ref `b26fa7c9`; stage-0 runs refuse on the production diff | **adopt**: a mode arm / `--certified-by` run defaults to M77's production; an explicit ref wins |
| 2 | Sol P2 (blocker) | below 2,048 keys `m72_exact` hands verify to the per-query loop and `joint_v1` records reason `cache`, which `e1c_verdict` rejects: the smoke can never pass | **adopt** (verified in `tq4_attention.py:306-321`, `mtp_verify_scan.py` `classify`): tuple runs accept `cache` only when equal to the `per_query:short` delta |
| 3 | Sol P3 (major) | `--certified-by` does not bind the summary to its sibling manifest (argv, registry hashes, weights, harness) nor the tuple's production directly | **adopt**: `binding == orchestrate.binding(manifest)`, the summary's manifest block cross-checked, the tuple's production enforced, both sha256 recorded |
| 4 | Sol P4 (major) | rejected E1c retries drop their engagement failures | **adopt**: any attempt's engagement failure → INCOMPLETE (after C1 / neutrality precedence) |
| 5 | Sol P5 (major), GLM F2 | the engagement band is wider than errata v1.1's one draft block | **adopt** (one-block band per edge; observed verify lengths are not recorded per trajectory, so the span rule stays) |
| 6 | Sol P6 (major) | the smoke projection ignores the tuple's cells and M76's 8 h ruling | **adopt**: project from the full tuple cells; > 8 h needs `--operator-approved-hours` |
| 7 | Sol P7 (scope request) | stage-0 `--engagement-only` checks no TQ4 route counters | **decline**: route engagement is proven per leg in stage 1 (B1 mode proof) and per trajectory in stage 2; stage 0 proves the cache manifest and the drafter |
| 8 | Sol P8 (minor) | dormant `m72_v1` support in the engagement helper | **adopt**: `m72_exact` only, others refused |
| 9 | GLM F1 (minor) | the refusal message names `KV_ARM_KEYS` | **adopt** |
| 10 | GLM F4 (minor) | `--certified-by` does not bind `off_stack_head` | **decline**: the errata's (b) as written; the XO commit is bound by the P369 run's own binding, which fix 3 now requires equal |
| 11 | GLM S1 / S2 (scope / process) | boot-time mode check beyond spec; implementer tests written after the code | **accept** the check; the test-writer's frozen tests are the red-first coverage |
