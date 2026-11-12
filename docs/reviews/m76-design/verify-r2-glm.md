# Cold design review — round 2 of 3 — M76 spec v1.1 — verify

## Round-1 findings: resolution status

1. **B0 `require_policy_stamps`** — RESOLVED. §5 B0 [r1] widens the rule to accept an absent verify stamp only with no drafter, keeps `fused_v1` on every module, adds an XO load-to-READY test. Verified against `src/mlx-vlm/mlx_vlm/tq4_attention.py:345-357` (today both `fused_v1` and `joint_v1` are required on every module, so XO would refuse without the change). `mtp_verify_scan.require_environment` (`mtp_verify_scan.py:516-517`) is correctly left unchanged (still refuses `joint_v1` without `draft_kind: mtp`).

2. **PASS / LOSS SHOWN overlap** — RESOLVED. §8 verdicts are now mutually exclusive and ordered: PASS (point ≥ −5 pp AND bound ≤ 10 pp, with a "loss shown, within tolerance" annotation when the CI excludes 0 favouring N16); LOSS (point < −5 pp AND CI excludes 0); UNDECIDED (else). The −3 pp / CI [−4, −2] case now lands as PASS with annotation, not both.

3. **A5 unattainable at 5/10 prompts** — RESOLVED in structure, but see new finding F1 below on the stated bound. A5 is now one axis of 40 prompts (20 retrieval + 20 chain-4), rung × task as strata, single look; tier-2 budget removed.

4. **260,096 A5 rung floors both arms** — RESOLVED. §7 A5 rungs are 131,072 / 159,744 (full budget) and 196,608 (resolved 65,536, equal between arms); 260,096 stays in stages 1–2 only.

5. **A5 adapters / A8 panel packet / A4 panel role** — RESOLVED. §5 B5 [r1] adds the `longctx` wave-1 axis end to end (AXES, plan_leg, pair-verifier, signals, panel adapter, red tests), B4 the A8 packet, and §7 panel execution-passing set now includes "A4 strict draws".

6. **P369 `PICKS` keyed by model; `prepare` requires 16 states / OFF root / `overlay_on`** — RESOLVED. §5 B2 [r1] adds `TUPLES["m76-x"]` beside the unchanged model-keyed native16 tuple; X/XO validated by `classify_kv_arm`, no overlay (both are commits).

7. **M1 `qualify --kv-arm --predictor on` refuses KV delta; OFF confound** — RESOLVED. §5 B2 [r1] binds the full ON measurement to the arm's stage-2 PASS record + exact argv; §7 M1 makes both arms MTP ON with legs N16 / X / X / N16.

8. **Stage-4 paired tier-2 X coverage / V − N16 / time confound** — RESOLVED. §7 stage 4 [r1] adds X legs where tier-2 needs them, the 5-item X reuse sentinel (P640), reads V against both X and N16 (recommend V only when both PASS), and takes V speed from stage 1 only. S22-P3 touched as required.

9. **`paired_delta` resamples each arm independently** — RESOLVED (adapted). §5 B7 and §8 statistic resample items keeping each item's per-session paired differences together; per-session deltas reported with a sign-disagreement flag. Verified `benchmark/bench/stats.py:283-295` draws each arm independently today, so the change is real.

10. **Fixed 99.4 / 95.2 % boundaries; no `level` param; zero-discordance bound fixed at 95 %** — RESOLVED. §5 B7 adds the `level` parameter (defaults byte-identical), per-axis Lan–DeMets spending, and a CPU simulation of the whole §8 rule gating each kept look (PASS probability ≥ 0.5 at true loss 0). §8 spends α per axis at the pre-registered information fractions. The error-control claim is now simulation-backed, not asserted.

11. **P475 campaign-global paths; `u4` not isolated** — RESOLVED. §5 B1 [r1] scopes scratch / state / dossiers / harvest / matrix per-campaign (`p475` vs `m76`), with `u4` goldens pinning paths, receipts and `MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` byte-identical.

12. **tg2 screen is not an O'Brien–Fleming look** — RESOLVED. §8 A8: screen = trigger (not a look), decider = one formal look at 95 %; C324 confirms tg2 keeps its harm-detection role.

13. **No branch on stage-2 FAIL** — RESOLVED. §7 stage 2 [r1]: on FAIL or ABORT stage 3 does not start; the operator chooses halt or a deconfounded stage 3 (XO vs an N16-OFF arm).

14. **`28235601` reads as a flag hash** — RESOLVED. §3 now says "classifies `--tq4-attention` (added in companion commit `28235601`)".

15. **Noise floor for Math500 / A5 (scope request)** — RESOLVED by decline, recorded in §8 ("Math500 / A5 blocks hold disjoint items, P426 §3, so they have no within-arm repeat"). Consistent with P426 §3's seeded split.

16. **S22-P3 "V MTP ON vs OFF" vs §1/§7 "V vs X"** — RESOLVED. §4 S22-P3 reworded to "stage 4 (V MTP ON vs X MTP ON) reads `m72_v1`'s lossy verify against the exact one".

17. **A5 / tg2 walls unmeasured** — RESOLVED. §5 B5 [r1] and §9 label both unmeasured; a timed smoke (one A5 prompt per rung, one tg2 item per language, both arms) recalibrates before stage 3's Go.

18. **Stage-2 claim overreaches (greedy, short windows)** — RESOLVED (adapted). §7 stage 2 [r1] claim wording is scoped to "the tested cells — transformed target distributions (E1c, 160 tokens) and greedy tokens (E2, 512 / 160 tokens)"; the OFF-quality-leg skip rests on the C258 precedent at those cells.

19. **Shared fork dev code shifts `u4` / native16 fingerprints** — RESOLVED. §5 B2 [r1] pins byte-identity goldens for every existing pick / arm; the mode field is emitted only when present.

20. **Report look-1 PASS rate before tier 2 (scope request)** — RESOLVED. Folded into B7's simulation report (§5 B7, §8 looks), delivered with the stage-3 Go.

All twenty round-1 findings are resolved in v1.1.

## New failures introduced or left by the diff

**F1 — A5's stated exact bound (7.2 pp) is inconsistent with §8's one-sided α (0.025).**
- Location: `docs/specs/m76-tq4-certification.md` §7 A5 row ("exact bound 7.2 pp") vs §8 ("Total one-sided α = 0.025 per axis").
- Severity: major.
- Evidence: confirmed by arithmetic. `1 − α^(1/n)` at n = 40: α = 0.05 → 7.22 pp; α = 0.025 → 8.81 pp. The 7.2 pp figure in §7 corresponds to α = 0.05, but §8 fixes total one-sided α at 0.025 (the 95 % two-sided interval C173 uses). The same 7.2 pp appears in the round-1 disposition for finding 3, so the error was carried in, not caught.
- Problem: A5 is one of the four mechanical axes whose PASS is required for the ship recommendation (§8). Its verdict threshold is wrong by ≈ 1.6 pp, and the spec is internally inconsistent on whether A5 spends α = 0.025 or α = 0.05. If B7 implements the §8 α (0.025), A5's real zero-discordance bound is 8.8 pp, not 7.2 pp, and any pre-registered "≤ 10 pp" reading the operator does against the 7.2 pp figure overstates A5's resolving power. If A5 is instead meant to use α = 0.05 (one-sided 95 %), it exceeds the per-axis budget §8 declares and breaks the familywise error-control claim the simulation is meant to certify.
- Failure scenario: B7 is built to §8 (α = 0.025). A5 returns zero discordance at n = 40; the harness reports bound 8.81 pp. The operator, having read "7.2 pp" in §7, treats 8.81 pp as a regression and either halts A5 or flags it incorrectly; or, worse, B7 is built to reproduce "7.2 pp" (α = 0.05) and the simulation's reported one-sided error no longer matches the α = 0.025 budget §8 claims, so the look-1 PASS-probability gate and the familywise error are misstated to the operator.
- Proposed change: pick one. Either (a) A5 uses one-sided α = 0.025 like every other axis, and §7 A5 is corrected to "exact bound 8.8 pp at zero discordance"; or (b) A5 is explicitly excepted from the §8 budget with a stated reason and the familywise error is recomputed to include the extra 0.025. (a) is the smaller change and keeps the C172/C173 convention the rest of the spec relies on.

**F2 — Stage-4 reuse sentinel covers only tg1 pilot items, not the X legs added for tier-2 paired coverage.**
- Location: `docs/specs/m76-tq4-certification.md` §7 stage 4 [r1] (the "X leg is added where stage 4's tier 2 needs coverage stage 3 did not collect" + the "5 tg1 pilot items" reuse sentinel).
- Severity: minor.
- Evidence: hypothesis from reading. The sentinel reproduces stage 3's X outputs on 5 tg1 pilot items to prove the X context is unchanged across the stage-3→4 gap. But the new X tier-2 legs (added for A1 +200, A5, A7 s3, A8 decider per the funnel) are on items stage 3 never ran on X, so there is no stage-3 X output to reproduce against — the sentinel cannot certify their X side is the same committed context as the V side's pair. The pairing for those new legs rests on the pair-verifier's commit/argv/fingerprint check alone.
- Problem: the time-confound guard finding 8 asked for is only partially implemented. For reused items the sentinel is sound; for the newly added tier-2 items the only thing certifying "same X context" is the pair verifier, which checks everything but the mode key/flag — i.e. it cannot detect a stage-3→4 build drift on the X side because X has no prior leg there.
- Failure scenario: a stack commit lands between stage 3 and stage 4 that changes a non-mode path on X. The 5 tg1 pilot items happen to be insensitive to it (or the change is on a tier-2-only axis like A8). The sentinel passes; the new A8-decider X legs run against a different X than their V pairs were paired against in spirit, and the V − X verdict is read against a shifted baseline.
- Proposed change: extend the sentinel to one reused item per axis that adds tier-2 X coverage (or state explicitly that the pair-verifier's commit/fingerprint match is the accepted guard for new items, and that the operator accepts that residual). The current spec leaves the gap implicit.

**F3 — §8 "sign disagreement between sessions whose intervals exclude each other's point" is undefined for a 2-session axis.**
- Location: `docs/specs/m76-tq4-certification.md` §8 statistic bullet ("a sign disagreement between sessions whose intervals exclude each other's point is flagged to the operator").
- Severity: minor.
- Evidence: hypothesis from reading. tg1 runs s1, s2, (s3). With two sessions, a "sign disagreement" is just s1's point and s2's point having opposite signs, which is common under a near-zero true effect and is not by itself evidence of a problem; the "whose intervals exclude each other's point" qualifier needs each session to have a tight enough interval to exclude the other's point, which at n = 43 per session with discordance ≈ 0.06 is ~14 pp wide (MDE) — two such intervals rarely exclude each other's point unless the sessions are far apart, in which case the flag is redundant with "look at the per-session deltas". With s3 the clause is also ambiguous: is the disagreement pairwise (s1 vs s2, s1 vs s3, s2 vs s3) or majority?
- Problem: the flag is the only per-session safeguard against a session-level confound (the cluster bootstrap's between-session variance is what makes the agentic bound wide, but a single anomalous session can still pull the point estimate past −5 pp while the bound stays under 10 pp and PASS fires). As written, the trigger condition is hard to operationalize and may never fire on a 2-session axis, so the protection finding 9's adaptation was meant to add is thinner than it looks.
- Failure scenario: tg1 s1 shows X − N16 = −6 pp (CI [−9, −3]), s2 shows +1 pp (CI [−4, +6]); the cluster bootstrap over items-with-sessions gives point −2.5 pp, bound −4 pp → PASS. Neither session's interval excludes the other's point (−6 is outside [−4, +6]? yes −6 < −4, so s2's interval excludes s1's point; +1 is inside [−9, −3]? no). The clause as written fires for one direction but not the other, and the operator gets a PASS with a buried session-level reversal.
- Proposed change: define the trigger concretely — e.g. "flag when any two sessions' point estimates have opposite signs AND each session's 95 % interval excludes the other session's point estimate" (pairwise over the sessions that ran), and say whether s3 enters pairwise or as a majority vote. State the per-session interval α (it should not be the OBF look α, which is for the combined statistic).

## Scope requests (no severity)

- **S1:** Add to §5 B7 a red test that the simulation's realized one-sided error at true loss 0 is ≤ the declared α for each axis (Math500, tg1, A5, A8 decider) at both looks. The spec asks for the realized error to be *reported* but not *asserted* against the budget; without a red test, a bug in the Lan–DeMets spending that inflates error can ship uncaught.

- **S2:** Add to §5 B2 a red test that `classify`, `classify_kv_arm`, `fingerprint_of` and the report are byte-identical for the existing `Qwen3.8-27B-mlx-uniform-4bit` and native16 picks *when the mode field is absent*. The spec asserts byte-identity; the golden tests are named but a red-first test that fails on any byte drift (not just a snapshot) is what finding 19's adoption wants.

- **S3:** §9's expected-path total (≈ 79–82 h) assumes the dropped-look branch for Math500 and tg1 (≈ +10 h) is taken. The §8 look-keeping gate is "PASS probability ≥ 0.5 at true loss 0 and the planning discordance". State the planning discordance values the gate is evaluated against for Math500 and tg1 (the §3 feasibility note gives ranges 0.03–0.20 for tg1/Math500 and 0.06 for Math500 in one place, 0.06–0.10 for tg1 in §8) — they are inconsistent and the gate's outcome (and therefore the budget) depends on which value is used.

## Summary

All twenty round-1 findings are resolved by v1.1. The diff introduces three new defects: one **major** (F1, A5's exact bound is inconsistent with §8's α budget — a deciding axis has the wrong threshold and the familywise error claim is internally contradictory) and two **minor** (F2 stage-4 sentinel gap on new tier-2 X items; F3 undefined session-disagreement trigger). Three scope requests (S1–S3) would harden the build. F1 should be fixed before the Go; F2 and F3 can be fixed in the build with red tests.
