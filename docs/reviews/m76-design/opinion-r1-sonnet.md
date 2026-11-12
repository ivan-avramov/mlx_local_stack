**Findings, M76 spec v1.** Nine findings: five major, four minor, plus one scope request. Findings 1, 4 and 5 are confirmed in the source. The rest I could only trace or argue, so they carry the evidence label stated in each.

**1. §8 intervals and bounds cannot be produced by the existing instruments (major, confirmed)**
- Location: §8 "Looks", "Verdict per axis"; §5 B3 "Signals".
- Evidence: `benchmark/bench/stats.py:301` hard-codes the percentile interval to 2.5 / 97.5, and `paired_delta` has no level parameter. The zero-discordance bound at `stats.py:315` is the fixed one-sided 95 % `1 − 0.05^(1/n)`. `compare_predictor._loss_bound` (`:359-364`) and `p426_signals._paired` (`:89-94`) consume exactly those values. No build B0–B5 lists a stats change. B3's "Signals (B6 / `p426_signals*`)" points at B6, which is the CPU audit.
- Problem: the 99.4 % and 95.2 % levels, the level-matched exact bound and the sessions-as-draws cluster statistic have no home.
- Failure scenario: look 1 is computed at 95 % and passes axes it should not. Or the builder improvises an untested statistic.
- Separately, a 99.4 % percentile bound from 10,000 resamples rests on about 30 resamples per tail, on a 1/43 grid for tg1.
- Proposed change: add a build item. It adds a `level` parameter to `paired_delta` / `cluster_bootstrap` and to the discordance bound, with red tests. Fix the B6 label.

**2. A5 can never PASS at n = 5 or 10 per rung, so the "every mechanical axis PASS" ship rule is unattainable (major, confirmed arithmetic)**
- Location: §7 stage 3 table A5; §8 recommendation.
- Evidence:
  - With 5 prompts and zero discordance, the exact bound is 1 − 0.05^(1/5) ≈ 45 pp. At 10 prompts it is ≈ 26 pp.
  - Any discordance gives a larger bound.
  - A5 is "mechanical (per rung)" and "ship X when every mechanical axis is PASS".
- Failure scenario: every run ends at "per-axis signals → operator". Tier 2 for A5 adds 5 prompts per rung, which still cannot decide. It spends GPU on an axis that can never resolve.
- Proposed change: define A5's decision unit as prompts pooled over rungs, with per-rung results descriptive. Even then n = 20 gives about 14 pp, so size it to be decidable. Otherwise mark A5 descriptive and keep it out of the ship rule.

**3. The 260,096 A5 rung leaves a 2,048-token budget (major, confirmed arithmetic; the effect on outcomes is a hypothesis)**
- Location: §7 A5.
- Evidence: `resolved_thinking_budget` gives effective = min(102,400, 262,144 − 260,096) = 2,048, and a thinking budget of 1,638 (`convergence.py:47-48`). With thinking ON, `acc_strict@budget` counts DNF as a fail.
- Failure scenario: the 5-code retrieval and chain-4 prompts mostly hit the budget in both arms. The rung floors at 0 with zero discordance. Each prompt costs a 260K prefill in four legs.
- Proposed change: drop the 260,096 rung from A5. Stage 1 and stage 2 already cover that length. Alternatively, run that rung only if a smoke shows N16 converges at that budget.

**4. Stage 4 recommends V over X with no V-versus-N16 bound (major, confirmed rule)**
- Location: §8 "Recommendation", §7 stage 4.
- Problem: each of X − N16 and V − X is allowed up to −5 pp point / 10 pp bound, so V can be −10 pp or worse versus the incumbent and still get both PASSes.
- Second problem: V legs run later than stage 3 and outside the order-balanced blocks, paired against X legs run at a different time. That breaks the order balance and thermal handling that C218 / C233 rely on, with no stated control.
- Proposed change: report and require V − N16 as well. It is free, because the N16 legs and items already exist. State the time-confound control, or interleave V into the stage-3 blocks.

**5. S22-P3 contradicts §1 and §7 on what stage 4 is (minor, confirmed)**
- Location: §4 S22-P3, against §1 item 4 and §7 stage 4.
- Problem: S22-P3 says "stage 4 is `m72_v1` MTP ON vs OFF". §1 and §7 say V versus X, and §7 says V ON-vs-OFF exactness is not claimed. No V-OFF arm exists.
- Proposed change: reword S22-P3 to "V MTP ON vs X MTP ON (≡ TQ4 OFF)".

**6. A4 (two-look O'Brien–Fleming control) is not supported as written (major, hypothesis)**
- Location: §8 "Looks".
- Problem:
  - The 2.797 / 1.977 boundaries assume two equally spaced looks on a two-sided test at zero effect. The pass decision is non-inferiority at a 10 pp margin on a percentile bootstrap.
  - Information fractions differ: Math500 100 → 300 is 1/3, tg1 2 → 3 sessions is 2/3, and tg2 uses a different design.
  - At look 1, tg1 has only 2 sessions as draws.
  - Using a feasibility figure of 7.0 pp for two discordant items (reproduced at 95 % in §3), a 99.4 % interval scales that to about 10 pp. So tg1 almost never passes at look 1.
- Consequence: "does not inflate the 5 % error" is unproven. The funnel saving on tg1 is near zero, so s3 is effectively always run.
- Proposed change: call the boundaries a conservative heuristic. State per-axis information fractions. Do not claim error control, or simulate the rule.

**7. §9 "lower bounds" lack a basis for A5 and tg2 (major, hypothesis)**
- Location: §9, stage 3 tier 1 and tier 2.
- Evidence: the cited walls (SIGNALS, receipts, P426 S′) contain no A5 or tg2 legs. tg2 has never run on the GPU (§3).
- Failure scenario: A5 means 5 prompts × 4 rungs × 2 task types per arm per block, at 131K–260K prefill. At a plausible 300 tok/s that is several hours per arm-block, against "Wave 1 + A5 ≈ 6.3 h" per arm. The tg2 decider "≈ 12 h" is also unsourced.
- Proposed change: label A5 and tg2 as unmeasured. Gate the rest on a timed smoke of one A5 rung and one tg2 item before committing.

**8. Stage 2 cannot support A1's seeded-sampling or "at scale" claims (minor, hypothesis)**
- Location: §7 stage 2; §3 and §8 "licenses skipping".
- Evidence:
  - E2 checks 512-token greedy outputs and E1c checks 160 tokens. Quality legs run up to 81,920 thinking tokens.
  - The m72-13 README's seeded check compares MTP ON against mode-absent MTP ON, not against OFF.
  - Speculative sampling consumes the RNG differently from plain decode, so equal seeded streams are not expected.
- Problem: a stage-2 PASS shows greedy identity over short windows only. It cannot show distribution identity.
- Consequence: the verdict wording overclaims. Stage 3 does not depend on it, because it measures the shipped MTP-ON state.
- Proposed change: word the verdict as "greedy-identical to N tokens at the tested cells". Drop "licenses skipping OFF legs" as a justification.

**9. B2 and B1 may disturb existing `u4` and `mtp`-lever consumers (minor, hypothesis)**
- Location: §5 B2 / B1, and B3 `fingerprint_of` (`:1709-1720`).
- Problem: adding the mode to `KV_ARM_KEYS`, `classify_kv_arm`, `fingerprint_of` and the report is shared code. The "byte-identical, tests unchanged" guarantee is stated only for `p475_kv` `u4` and the P426 `mtp` lever.
- Failure scenario: `qualify` fingerprints or `u4` report bytes shift, and old P475 receipts fail "never pool across fingerprints" comparisons.
- Proposed change: state the same byte-identical guarantee for `qualify` and `registry_states` on existing picks, and add a golden test that fixes the pre-change `u4` fingerprint.

**Verified accurate (no finding):** the `config.py:175-178` / `:256-260`, `tq4_attention.py:88-90`, `mtp_verify_scan.py:516-517`, `app.py:1241-1244` and `p475_kv.py` `PICK` / `ARMS` / `BASE_ARM` / `SMOKE_ARMS` / `LEG_RE` / `LEG_ESTIMATE_MIN` (`:27-47`) references match the source. I did not read the P426, `qualify`, `registry_states`, `orchestrate` and `worker` references. The spec's `p475_kv.py` edit-regex and registry-text line numbers (`:56`, `:108`, `:363`, `:378-411`) were also not checked.

**Scope request (no severity):** record the stage-1 timing of the funnel's look-1 PASS rate per axis from the smokes before committing tier 2. The 99.4 % level may make tier 2 mandatory for tg1, and the operator should see that before the GPU commitment.