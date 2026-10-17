S1 (high) — The detection formula is only a rough large-sample approximation.  
Location: P356 opening arithmetic.  
Failure scenario: \(2.8\sqrt{p_d/n}\) is correct near \(\Delta=0\), but at \(n=40,p_d=.15\) it gives 17.2 pp, which is infeasible because \(|\Delta|\le p_d=15\) pp. With only six expected discordant pairs, exact McNemar discreteness dominates. Exact 80%-power MDEs are approximately:

- n=100: 11.0 pp at \(p_d=.15\), 12.2 pp at .182, 16.0 pp at .303.
- n=120: 10.1, 11.2, and 14.6 pp respectively.
- n=40: no attainable 80%-power effect at \(p_d=.15\); at \(p_d=.303\), MDE ≈24.4 pp.

Ten items/language have nominal MDE ≈34 pp even under \(p_d=.15\), not 17 pp.  
Fix: size with exact paired-binary simulation, report pooled and per-language power separately, and use sensitivity values at least .182 and .303.

S2 (blocker) — The ±5 pp equivalence size is materially understated.  
Location: P356 opening; `benchmark/bench/stats.py` `paired_delta`.  
Failure scenario: formal α=.05 TOST uses a 90% CI. At true \(\Delta=0,p_d=.15\), 80% joint power requires approximately:

- 514 paired items for formal TOST;
- 630 items for the repository’s actual rule—95% percentile CI entirely inside ±5 pp.

At n=350, formal TOST power is only about 56–60%. At \(p_d=.182\), requirements rise to 623/765; at .303, 1,038/1,273.  
Fix: distinguish formal TOST from the repository’s “95%-CI-inside-margin” rule and replace 350 with method-specific sizing. Neither is feasible on tg2.

S3 (high) — \(p_d=.15\) is a sensitivity case, not a defensible planning estimate.  
Location: P356; `benchmark/results/m55_polyglot_gap_report.md`; `benchmark/m64/POWER_SIM.md`.  
Failure scenario: M55 gives top-pick same-model s1-vs-s2 discordance 24/132=.182, while between-pick, within-session discordance is 40/132=.303. The tg1 7/172=.041 comes from a saturated 95–100% corpus and is not transferable. Planning at .15 makes the n=100 decider look like 11 pp when a between-pick comparison is closer to 16 pp.  
Fix: use .182 for same-model/config sensitivity and .303 for pick comparisons; retain .409 as a stress case.

S4 (high) — The M64 simulation cannot calibrate this design as written.  
Location: `benchmark/m64/power_sim.py:60-69`; `POWER_SIM.md`; P347.  
Failure scenario: `sim_cell` symmetrically flips a fixed high-accuracy reference. Its supposed \(\Delta=0\) scenario actually has expected delta \(p_d(1-2r)\): about −3.7 pp at \(r=.955,p_d=.041\), and −4.1 pp at \(r=1\). P347 also says 11/172=.041, while the script and rows show 7/172=.041; 11/172 is .064.  
Fix: regenerate feasible paired joint tables with \(P(D=+1)=(p_d+\Delta)/2\), \(P(D=-1)=(p_d-\Delta)/2\), then rerun exact/clustered power simulations. P347’s qualitative conclusion remains credible, but its numerical simulation should not size P356.

S5 (blocker) — Pooling k=2 as additional independent observations violates both the rules and the variance structure.  
Location: P356c; `AGENTS.md` Benchmark validity; tg2 spec “Protocol” and “Estimand”; `benchmark/bench/stats.py:226-300`.  
Failure scenario: two loaded sessions over the same items are clustered repetitions, not \(2n\) items. Only two sessions cannot estimate session-level variance, and the existing bootstrap treats repeated arm draws as independent within item. That misses loaded-instance effects which motivated the k=2 rule.  
Fix: retain per-session primary inference. Treat session two as replication/robustness evidence, not power doubling. Any pooled-session estimand requires an explicit rule amendment and a simulation preserving item, language, session, arm, and seed blocks.

S6 (blocker) — “Look at 50/100” is not a group-sequential design.  
Location: P356c.  
Failure scenario: fixed-sample bootstrap intervals inspected twice inflate error. The proposal does not specify superiority versus non-inferiority, one- or two-sided α, information fractions, spending, multiplicity, futility, or whether screen rows enter the final analysis. Outcome-driven escalation while retaining screen rows also creates selection bias. Fifty items cannot be balanced over four languages.  
Fix: define one nominated contrast and endpoint. Prefer a balanced 40/80 or 48/100 nested order. Use futility-only stopping at the diagnostic screen, or simulation-calibrated Lan–DeMets/O’Brien–Fleming efficacy boundaries. Nonbinding futility must yield HOLD, never equivalence. Sequential TOST should not be used here.

S7 (high) — Stored-reference reuse needs stricter conditions than “same decision epoch.”  
Location: P356b; C165/E1; P352; c144-base campaign section.  
Failure scenario: seeds do not reproduce outputs across loaded instances. `prompt_date` changes the opencode prompt, and P352 requires it in pairing identity. c144-base versus P223 still showed 7/172 discordance and all four P223 `client_inactivity` failures disappeared. Software identity alone therefore does not remove temporal/session confounding. A reference reused across days can make drift look like a treatment effect.  
Fix: require identical epoch, model, items, seeds, fingerprint, wall policy, prompt date, box class, and scoring. Freeze prompt date within the epoch or rerun the reference. Add contemporaneous reference sentinels; any drift red flag triggers HOLD/re-baselining. Cross-epoch rows remain descriptive.

S8 (high) — A k=1 screen is diagnostic, not a reliable negative screen.  
Location: P356c; M55 “Session repeatability”; `docs/metrics.md` Seeds.  
Failure scenario: M55 same-model session discordance ranges from 1/22 to 9/22; language accuracy shifts reach 18 pp. One challenger load versus one historical reference load confounds arm and session. A clean screen cannot exclude a large regression, while an apparent regression may disappear on reload.  
Fix: allow k=1 only with “no PASS/ADOPT/REJECT” semantics. It may report headroom, catastrophic failures, nonconvergence, tokens and candidate mechanisms. Material findings trigger k=2; absence of findings is not safety evidence.

S9 (high) — Single-turn evidence does not establish transfer to agentic behavior.  
Location: P356a; PLAN M63; campaign M40/M57/M63 sections.  
Failure scenario: M40 covered Math500, cjudge, depth, vision and some coding, but explicitly omitted paired opencode agentic testing. M63 was commissioned for that gap and found all four OFF `client_inactivity` cases passing ON, with 5 ON-favoured and 3 OFF-favoured discordances and changed trajectories. M57 had strong single-turn/long-context evidence but only a 5-item AgentBench smoke. These results show complementary failure surfaces, not transfer.  
Fix: single-turn axes may enforce ≤5 pp on their own estimands, but must not certify agentic safety. Require at least the diagnostic agentic screen for trajectory-, timeout-, scaffold-, tool-, or serving-changing levers; waive it only with a validated output-identity argument.

S10 (high) — The pooled-language proposal conflicts with tg2 and can hide language regressions.  
Location: P356c; tg2 “Estimand”; `AGENTS.md` reporting rules; `docs/box-notes.md` corpus provenance.  
Failure scenario: raw pooling weights languages by available item count and permits Simpson-type decisions. A 20 pp loss in one language can be hidden by gains elsewhere. N=120 also cannot be equally balanced: C++ has only 26 valid candidates before exclusions, so four-language balance tops out near 104. Existing frozen draws support 20 or 25 per language, not 10/language or a 50-item interim.  
Fix: if formally amended, use an equal-language macro-average with stratified item bootstrap, sessions still separate. Report every language and add a pre-registered large-harm HOLD rule. Freeze nested balanced draws before model outcomes.

S11 (medium) — Cost is understated, and several valid economies are missing.  
Location: P356c; tg2 “Sizing”; M55 wall times.  
Failure scenario: M55 means are about 351 and 382 seconds/item for the two picks. Including tg2’s 20-call reload control per arm:

- n=40, k=1: 3.9–4.2 GPU h.
- n=80, k=2 plus reload: 17.6–19.1 GPU h.
- n=100: 21.5–23.3 GPU h.
- n=120: 25.4–27.6 GPU h.

These exclude loads, audits, recovery and the mandatory subjective panel. A shorter thinking budget is prohibited. A 45-minute wall cap would have saved 6.1% on P223 with no lost strict pass; a 30-minute cap saved 12.6% but would have converted one 36.9-minute pass to DNF. M55 had no item over 30 minutes, so either cap saved nothing there.  
Fix: pre-stratify outcome-blind by language and structural complexity; use frozen nested draws; consider a matched 45-minute operational wall estimand; use tg1 rows only as descriptive sensitive anchors. Never select items using current-model failures or incumbent reference outcomes.

Recommended plan: keep the two-tier architecture, but make SCREEN n=40/k=1 explicitly diagnostic at about 4 GPU h per new tuple. Under a binding 20-hour target, use DECIDER n=80, 20/language, k=2 plus reload at approximately 18–19 GPU h base cost; honestly label its exact 80%-power MDE about 14 pp for same-model/config comparisons and 18 pp between picks. Use per-session inference, equal-language reporting, futility-only early stopping, and immutable same-epoch references with frozen prompt date. A 10 pp between-pick decider is not affordable here; n≈120 still detects only about 15 pp and costs roughly 25–28 GPU h per new arm.

VERDICT: AGREE WITH CHANGES S1 S2 S4 S5 S6 S7 S8 S9 S10 S11Exact paired-MDE calculation completed successfully; its results were already incorporated into S1 and the recommended sizing. No follow-up is needed.
