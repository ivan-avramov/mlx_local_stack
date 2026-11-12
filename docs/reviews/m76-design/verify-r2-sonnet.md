Status: I've checked the v1.1 diff and the ledger against the source, including `require_policy_stamps` and the call chain in `server/generation.py`. Here are the verdicts.

## Round-1 findings

Numbers follow the ledger. All the code facts for findings 1, 9 and 10 below check out against the source.

| # | Status | Reason |
|---|---|---|
| 1 | Resolved in intent; new defect N4 | The policy-stamp check at `tq4_attention.py:345-357` does require `joint_v1`. The plumbing for the "no drafter" condition is unspecified. |
| 2 | Resolved | PASS, LOSS and UNDECIDED are now ordered and exclusive. A point estimate ≥ −5 pp with an interval that excludes 0 and a bound > 10 pp falls to UNDECIDED, which is acceptable. |
| 3 | Partly resolved | The 40-prompt A5 is decidable. The α inconsistency and the missing simulation are N3. |
| 4 | Resolved | The 260,096 rung is dropped from A5. |
| 5 | Resolved in text | B5 and B4 now carry the adapters. The CPU estimate is not updated (N5). |
| 6 | Resolved | The campaign-tuple key sits beside the unchanged native16 tuple. |
| 7 | Resolved | M1 runs both arms ON, bound to the stage-2 PASS record. |
| 8 | Not resolved | Only X coverage is added, not N16 (N1). The sentinel is narrow (N2). |
| 9 | Resolved | `stats.py:283-295` does draw each arm independently. Resampling items and keeping per-session differences together is sound. The unit becomes the item-mean difference. |
| 10 | Mostly resolved | There is still no level parameter in the shipped code; B7 adds it. The remaining issues are N3 and N7. |
| 11, 12, 14, 16, 19, 20 | Resolved | |
| 13 | Resolved, with a design caveat (N6) | |
| 15 | Decline accepted | |
| 17 | Resolved | A5 and tg2 are labelled unmeasured, with a timed smoke before the Go. |
| 18 | Resolved | The wording is limited to the tested cells. I did not verify the claim that E1c compares transformed target distributions. |

## New findings

**N1. Stage 4 cannot form V − N16 on added tier-2 items (major, confirmed from the text)**
- Location: §7 stage 4, S22-P3, §8.
- Problem: V is now read against X and against N16, and PASS needs both. Where stage 3 stopped early on an axis, stage 4 adds only "an X leg". The N16 legs for those items do not exist.
- Failure scenario: Math500 passes at a stage-3 look, or stage 3 runs only tier 1. Stage 4 adds items 101–300 for V and X, but N16 has no outputs on them. V − N16 is then undefined or unpaired on those items. Either the recommendation rule cannot be evaluated, or the V − N16 interval covers fewer items than V − X.
- Proposed change: state that added coverage covers all three arms (N16, X and V), or define V − N16 on the common items only. Budget the added N16 legs in §9.

**N2. The reuse sentinel covers one axis and its failure branch is unbudgeted (minor, hypothesis)**
- Location: §7 stage 4.
- Problem: the sentinel is 5 tg1 pilot items. It is used to license reuse of every X leg: Math500, A2, A3, A5, tg2 and tg1. Failure means "X rerun with V in order-balanced blocks", which is up to a full stage-3 cost again. That is not in §9's worst case.
- Proposed change: add a sentinel item from each reused axis family, or limit the claim to tg1. Put the failure branch in §9.

**N3. A5 is the one axis that can block the ship rule, and it is neither simulated nor consistently specified (major, hypothesis)**
- Location: §7 A5 row; §8 loss bound; B7.
- Problem 1: §8 and B7 set the total one-sided α to 0.025. The exact zero-discordance bound at n = 40 is then 1 − 0.025^(1/40) ≈ 8.8 pp. The A5 row quotes 7.2 pp, which is the α = 0.05 value.
- Problem 2: a percentile bootstrap at n = 40 gives about −7.5 pp with one N16-better discordance and about −12.5 pp with two. So two N16-better discordant prompts fail the rule.
- Problem 3: B7's simulation covers tg1, Math500 and tg2 but not A5.
- Failure scenario: A5 has no look, so a failure reaches the operator as "loss not ruled out above X pp" on 40 prompts. The recommendation's "every mechanical axis PASS" then fails for a reason the pre-registration never sized.
- Proposed change: fix the 7.2 / 8.8 figure. Add A5 to the B7 simulation across discordance 0.05–0.20. Pre-register what is reported if A5's PASS probability at zero true loss is below 0.5.
- Related: it is unclear whether "effective-context ≥ 0.85 per rung" is a gate or descriptive. With about 6–7 prompts per rung × task it is not estimable. Say which.

**N4. B0's "no drafter" condition has no plumbing (minor, confirmed)**
- Location: §5 B0; `server/generation.py:204-245`, `tq4_attention.py:58-91, 345-357`.
- Problem: `_resolve_tq4_mode_from_env`, `require_environment` and `_apply_tq4_attention_from_env` take no draft information. The scan value passed in is the string `"per_query"` when the env var is absent. `draft_kind` is available only in the later call at lines 1576-1582, and the stamp check runs after it.
- Failure scenario: a naive widening that accepts a missing stamp or `per_query` would also accept TQ4 mode + drafter + no `joint_v1`. That is the pairing the guard exists to refuse.
- Proposed change: pass `draft_kind` into both functions and treat absent, `per_query` and no-drafter as the only accepted OFF state. Add a red test that mode + drafter + no scan is still refused.

**N5. The CPU budget and acceptance were not rescoped for the new builds (minor, confirmed)**
- Location: §9, the "B1–B5 ≈ 2 days" line, and the §11 acceptance list.
- Problem: B5 now adds a full `longctx` axis. B2 adds a tuple, M1 binding and goldens. B7 is a statistics build with a simulation. The CPU estimate is unchanged. The new sentinel and the extra stage-4 legs are not budgeted either.
- Proposed change: re-estimate and cap the CPU days.

**N6. The stage-2 FAIL branch offers an alternative that does not test the candidate (minor, hypothesis)**
- Location: §7 stage 2, FAIL / ABORT.
- Problem 1: stage 3 compares X MTP ON against N16 MTP ON, the shipped state, so a stage-2 FAIL does not confound it. The "deconfounded" alternative, XO versus N16-OFF, would certify an arm that is not the candidate.
- Problem 2: ABORT means the C1 control failed. That is an instrument failure, not an X failure, and it is grouped with FAIL.
- Proposed change: on FAIL, offer to run the planned stage 3 anyway, with the exactness failure reported. On ABORT, repeat stage 2.

**N7. The look-keeping gate has an ambiguous decision value (minor, hypothesis)**
- Location: §8 "Looks", B7.
- Problem: "PASS probability ≥ 0.5 at the planning discordance" gives tg1 a range of 0.06–0.10. Which value decides is not fixed.
- Consequence: the Math500 look at t₁ = 1/3 (≈ 99.9 %) and the tg1 look at 2/3 (≈ 98.4 %) will almost certainly be dropped, as §9 itself says. The funnel then collapses to full-size tier 1 for A1 and A7, which is the disclosed trade, not a defect.
- Proposed change: fix the single decision value, e.g. the upper end of the range, in the pre-registration. Also define the "sign disagreement between sessions" flag, since a per-session interval over 43 items is not otherwise specified.