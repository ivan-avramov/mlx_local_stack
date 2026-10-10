**P1 — Decision 1, C109: AGREE-WITH-CHANGES.** Retain session-level reporting; allow a descriptive pooled event rate, but reject the proposed interpretation of its uncertainty.

1. **Decision and evidence.** The proposal combines chains 3+4 and mandates future replication. For `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, two budget hits disappeared, while 16/142 turn caps recurred; `Ornith-1.0-35B-mlx-uniform-4bit` repeated its 82,351-token budget hit. Reloading changed 55/142 token counts. This establishes instability across loaded instances, not a well-estimated population distribution. [campaign-results.md:39]($STACK_REPO/docs/campaign-results.md:39), [metrics.md:60]($STACK_REPO/docs/metrics.md:60)

2. **Strongest objections.**
   - **The endpoint is inconsistent.** The implementation counts `turn_cap OR exec_timeout`, excluding budget hits unless they overlap. Thus the reported 43% is not established as the two budget-hit tasks’ wall share. C109’s “43% → 0%” also differs from the table’s 43% → 27.6% because the definitions change. [agentbench_compare.py:196]($STACK_REPO/benchmark/bench/agentbench_compare.py:196), [open-questions.md:20]($STACK_REPO/docs/open-questions.md:20), [campaign-results.md:24]($STACK_REPO/docs/campaign-results.md:24)
   - **Contaminated time cannot become valid through pooling.** The record explicitly permits only chain 4’s wall-clock figures. [campaign-results.md:7]($STACK_REPO/docs/campaign-results.md:7)
   - **284 task-sessions are 142 repeated tasks across two sessions.** Item clustering alone misses shared session effects; two sessions cannot support a reliable interval for future-session variability. Same-seed reloads also do not measure fresh-seed variability.
   - Identical aggregate counts do not establish identical affected tasks or a fixed propensity. Two repeats likewise do not establish universal determinism.

3. **My recommendation.** Use **(b) as the primary presentation**, with an optional pooled descriptive event frequency explicitly labelled “142 tasks × two sessions.” First reconcile budget-hit, turn-cap and execution-timeout flags; report each separately and their deduplicated union. Define wall share as whole-task occupancy or offending-turn time.

   Exclude chain 3 from pooled wall estimates. Amend **(c)** to require independent loaded instances **and** distinct paired seed schedules, retaining a same-seed reload control. Treat two sessions as a minimum diagnostic, not a precision guarantee; pre-register additional replication where uncertainty could affect selection. Future inference must preserve both item and session dependence.

   Keep correctness and exclusive solves primary. A costly model’s uncertain quality advantage cannot be dismissed merely because it is costly. [metrics.md:30]($STACK_REPO/docs/metrics.md:30)

4. **What changes my mind.** Reconciled event labels, clean matched sessions, evidence supporting harness exchangeability, and enough independent sessions to demonstrate that the proposed interval captures between-session variation.

**P2 — Decision 2, P17: DISAGREE as the principal selection axis; approve EvoEval only as supplementary evidence.**

1. **Decision and evidence.** P17 proposes approximately 200 frozen `difficult`/`subtle` problems. Existing evidence leaves real gaps: five-item regression screens establish neither saturation nor equivalence; the leading model lacks Rust/Java/JavaScript coverage; bounded retrieval qualification reaches 128K, not general 256K coding competence. [handoff.md:38]($STACK_REPO/docs/handoff.md:38), [README.md:36]($STACK_REPO/README.md:36), [README.md:59]($STACK_REPO/README.md:59), [README.md:63]($STACK_REPO/README.md:63)

2. **Strongest objections.** EvoEval’s problems, reference solutions and tests are public: tests hidden from the inference prompt are not necessarily absent from training. Weighting `subtle` does not repair exposure. Its HumanEval ancestry also creates correlated problem families; 400 transformations need not provide 400 independent items. It measures short program synthesis, with limited evidence about repository navigation, repair or long-context integration. [EvoEval repository](https://github.com/evo-eval/evoeval)

   The LiveCodeBench rejection presents a false tradeoff: freeze each campaign’s window and artifacts, then refresh the window for subsequent campaigns. Reproducibility within a campaign survives.

3. **My recommendation.** Make **fresh, independently authored repository tasks with private tests** the strongest selection evidence; supplement them with temporally qualified LiveCodeBench and missing language coverage. Use EvoEval to diagnose specification sensitivity.

   Below, contamination risks are my assessments. Nominal MDEs use the repository’s paired approximation, α=.05, power=.80, discordance=.20; clustering and multiplicity generally worsen them. At n=200, MDE≈8.9 pp; n=400≈6.3 pp; roughly 628 independent items are needed for 5 pp. These are planning assumptions, not guarantees. [metrics.md:49]($STACK_REPO/docs/metrics.md:49)

   | Alternative | Contamination risk; available items; nominal MDE | Additional selection value |
   |---|---|---|
   | **EvoEval** | Substantial public exposure; 200 proposed, 400 expanded; 8.9/6.3 pp before ancestry clustering | Specification changes and composition; weak evidence for repository-scale work. |
   | **Rolling LiveCodeBench** | Lower only for problems demonstrably newer than every candidate’s final training. Official documented v6: **1,055 through April 2025**, not automatically fresh for 2026 models. Eligible n unknown; n=200 gives 8.9 pp. | Fresh algorithmic generalization, independent of HumanEval transformations. [Official versions](https://github.com/LiveCodeBench/LiveCodeBench#dataset-versions) |
   | **BigCodeBench-Hard** | Public since 2024; 148, 10.3 pp | Library composition and practical API usage; broader tasks, no freshness guarantee. [Official repository](https://github.com/bigcode-project/bigcodebench) |
   | **SWE-bench Verified** | Public issues, patches and benchmark exposure; 500, 5.6 pp; a 100-item subset gives 12.5 pp, before repository clustering | Stronger relevance to navigation, debugging and coordinated edits; scaffold and environment failures need isolation. [Official documentation](https://www.swebench.com/SWE-bench/) |
   | **Remaining polyglot languages** | Public Exercism exposure; Rust/Java/JavaScript **30/47/49**, MDE **22.9/18.3/17.9 pp**; combined 126, 11.2 pp before exercise-family clustering | Directly tests known coverage holes and language-specific rank reversals. Use the supported harness with matched baselines. [Official counts](https://aider.chat/2024/12/21/polyglot.html) |
   | **Private held-out set** | Lowest direct leakage if newly authored and isolated; no supplied inventory. Design target 628 independent tasks, ≈5 pp | Best match to actual repository/context workload; author bias and defective tests require independent validation. |
   | **No new axis** | Inherits existing exposure; zero additional items, no new MDE | Adds no information; preserves unresolved coverage and selection risk. |

   Pre-register task sampling, context strata, primary comparisons, budgets, exclusions, contamination checks and rank-change criteria. Validate tests independently; prohibit candidate-driven item filtering. Retain exclusive-solve sets. Certify any resulting winner in its shipped predictor configuration. [AGENTS.md:49]($STACK_REPO/AGENTS.md:49)

4. **What changes my mind.** Evidence that EvoEval remains unexposed, discriminates these finalists, and predicts performance on a fresh repository-task holdout would justify promoting it beyond a diagnostic axis.

**P3 — What the author under-weighted**

The central danger is **mistaking unresolved quality differences for equality, then letting speed decide**. The repository explicitly rejects that inference. Better uncertainty labels help, but independent, representative tasks reduce the risk of choosing the wrong model. [metrics.md:49]($STACK_REPO/docs/metrics.md:49)