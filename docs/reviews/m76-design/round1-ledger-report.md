# M76 spec — cold design review round 1 of 3 (strict) — ledger

Material: `docs/specs/m76-tq4-certification.md` v1 (`7620adae`); brief `brief-r1.md`; context `checkout` (a read-only copy of the
repository with the stack's rule files renamed; the fork sub-trees' own rule files left in place as content).

| member | runtime | model run | session | context | status | raw |
|---|---|---|---|---|---|---|
| sol | cursor-agent `--mode ask` | `gpt-5.6-sol-high` (alias resolved from the listing) | unreported | checkout, user instructions unconfirmed | exit 0, valid | `opinion-r1-sol.md` |
| glm | cursor-agent `--mode ask` | `glm-5.2-high` | unreported | checkout, user instructions unconfirmed | exit 0, valid | `opinion-r1-glm.md` |
| sonnet | claude -p, setting sources none, tools Read / Grep / Glob | `claude-sonnet-5-5` | `eff3681e-b658-46f0-8c98-5d6bc9abee76` | checkout | exit 0, valid | `opinion-r1-sonnet.md` |

Sonnet shares the driver's vendor (Anthropic): it removes anchoring, not vendor bias.

## Findings (distinct; driver's dispositions)

| # | raised by | finding | disposition |
|---|---|---|---|
| 1 | Sol P1 | B0 misses `tq4_attention.require_policy_stamps` (every module must carry `joint_v1`); XO would refuse at load | **adopt** (verified `tq4_attention.py:345-357`): B0 accepts an absent verify stamp only with no drafter, keeps `fused_v1`; XO load test |
| 2 | Sol P2 | PASS and LOSS SHOWN overlap (−3 pp, CI [−4, −2]) | **adopt**: mutually exclusive ordered verdicts; a shown sub-tolerance loss is a PASS annotation |
| 3 | Sol P3, GLM F2, Sonnet 2 | A5 at 5 / 10 prompts per rung can never PASS (zero-discordance exact bound 45 / 26 pp); tier 2 unbudgeted | **adapt**: A5 is one axis of 40 prompts (rung, task as strata), single look (exact bound 7.2 pp at zero discordance); per rung descriptive + effective-context ≥ 0.85 |
| 4 | Sonnet 3 | the 260,096 A5 rung leaves a 2,048-token budget (1,638 thinking): both arms floor | **adopt**: rungs 131,072 / 159,744 / 196,608; 260,096 stays in stages 1–2 |
| 5 | Sol P4 | A5 runner / verifier / signals / panel adapters and the A8 panel packet are missing; A4 dropped from the panel | **adopt**: B5 adds the `longctx` axis end to end, B4 the A8 packet; A4 keeps its P426 panel role |
| 6 | Sol P5 | P369 `PICKS` is keyed by model; `prepare` requires the 16 states, an MTP-OFF root and `overlay_on` | **adopt**: a campaign-tuple key beside the unchanged native16 tuple; X / XO validated by `classify_kv_arm`, no overlay |
| 7 | Sol P6 | M1 via `qualify --kv-arm --predictor on` refuses a KV delta (P475a v4.1); OFF would confound | **adopt**: M1 both arms ON; the full ON qualification bound to the arm's stage-2 PASS record + exact argv |
| 8 | Sol P7, Sonnet 4 | stage 4 cannot get paired tier-2 X coverage; no V − N16 bound; time confound of reused X legs | **adopt**: X legs added where stage 4 needs them (the operator's "extra coverage on older subjects"); V must PASS vs X and vs N16; a 5-item X reuse sentinel; V speed from stage 1 only. Touches S22-P3 → reported to the operator |
| 9 | Sol P8 | `paired_delta` resamples each arm's draws independently within an item: sessions-as-draws loses the session pairing | **adapt** (verified `stats.py:283-295`): resample items, keep each item's per-session paired differences together (B7); per-session deltas + a disagreement flag. Sol's outer-session clustering with 2–3 sessions is not estimable; this keeps S22-P8 → reported to the operator |
| 10 | Sol P9, GLM F1, Sonnet 1, Sonnet 6 | the fixed 99.4 / 95.2 % boundaries ignore per-axis information fractions; `stats` has no level parameter; the zero-discordance bound is fixed at 95 % | **adopt**: B7 (level parameter, per-axis Lan–DeMets spending, a CPU simulation of the rule); a look is kept only if its simulated PASS probability at no loss ≥ 0.5, else the axis runs full size with one 95 % look; error-control claim made only from the simulation |
| 11 | Sol P10 | P475 scratch / state / harvest / matrix paths are campaign-global; `u4` not isolated | **adopt**: campaign-scoped paths, `u4` goldens |
| 12 | GLM F3 | tg2's screen is not an O'Brien–Fleming look | **adopt**: screen = trigger, decider = one look at 95 % |
| 13 | GLM F4 | no branch on a stage-2 FAIL | **adopt**: stage 3 does not start; the operator chooses halt or a deconfounded MTP-OFF stage 3 |
| 14 | GLM F5 | `28235601` reads as a flag hash | **adopt** (reworded) |
| 15 | GLM F6 (scope request) | noise floor for Math500 / A5 too | **decline**: P426 §3 blocks hold disjoint items, so no within-arm repeat exists; stated in §8 |
| 16 | Sonnet 5 | S22-P3 says "V MTP ON vs OFF", §1 / §7 say V vs X | **adopt** (reworded) |
| 17 | Sonnet 7 | A5 / tg2 walls have no measured basis | **adopt**: labelled unmeasured; timed smokes before stage 3's Go |
| 18 | Sonnet 8 | stage 2's claim overreaches (greedy, short windows) | **adapt**: E1c does compare transformed target distributions (P369 §1), so the claim is wider than greedy, but only at the tested cells — reworded to that scope; the skip of OFF quality legs rests on the C258 precedent at those cells |
| 19 | Sonnet 9 | shared fork dev code could shift `u4` / native16 fingerprints | **adopt**: byte-identity goldens for every existing pick |
| 20 | Sonnet (scope request) | report the look-1 PASS rate before committing tier 2 | **adopt** as part of B7's report |

Driver-only concern: the expected-path budget rises to ≈ 79–82 GPU h (≈ 105 h with allowance) because dropped looks are now likely
for Math500 and tg1.
