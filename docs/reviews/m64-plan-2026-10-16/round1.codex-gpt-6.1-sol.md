1. **P319 — BLOCKER: P315 defines valid individual comparisons, but does not preserve a model-selection ladder across comparisons.**  
   Comparing models A/B on harness V1 and B/C on V2 does not establish A/C: harness changes can interact with model, language, tool use and context length. Re-running B controls the local comparison; it does not make B a stable bridge. Calling harness version a “covariate” does not solve this when version is confounded with comparison.

   **Fix:** freeze the complete harness snapshot vector for each decision family, including follow-up confirmation runs. Permit adoption between families. Label conclusions by that vector and forbid transitive rankings across vectors without bridge evidence. “No automatic full re-baseline on every release” is sound; “only cross-version pooling is lost” understates the loss.

2. **P320 — BLOCKER: C154 prevents an unqualified claim of matched token budgets across arms.**  
   The gate specifies 81,920 thinking tokens and 102,400 maximum tokens, but explicitly recognizes opencode’s inactivity interruption and missing trailing usage (`benchmark/bench/token_turn_gate.py:9`, `:30`). The project record documents genuine reasoning cut below budget, with model-dependent effective caps (`docs/open-questions.md:48`). Such a completion might have stopped successfully between the client cut and the token limit; its strict failure is not provably equivalent to a budget hit.

   This also threatens “lower tokens/task”: opencode can omit substantial trailing generation from charged usage.

   **Fix:** distinguish two estimands:
   
   - **Operational scaffold performance:** retain each client’s limitations, count cuts as failures, disclose unequal effective opportunity.
   - **Matched-budget capability:** require clients that can actually deliver the prescribed budget.

   Report complete generated-token accounting, or explicit missingness/bounds, for interrupted requests. An exclusion sensitivity analysis is useful but cannot repair outcome-dependent censoring. A two-item smoke cannot establish absence of a 60-minute cutoff; add an accelerated timer contract test where feasible and explicit release-specific timeout evidence.

3. **P321 — BLOCKER: P317’s ownership argument is false.**  
   Start order also participates in ancestry validation: `tick()` rejects a parent younger than its child before propagating tracked ownership (`benchmark/bench/proc_guard.py:396`). More importantly, **absence of tracking or path attribution does not establish that a process is unrelated**.

   Concrete escape path under the proposal:

   - A tracked client spawns a helper.
   - The helper’s start/order inspection fails before ancestry propagation; `tick()` records it and skips it (`:375–386`).
   - The helper changes cwd outside the run roots, has generic argv, and is reparented to PID 1.
   - Cleanup sees readable cwd/argv but still-unreadable start order. It is untracked and path-negative, so P317 would record a diagnostic orphan and succeed.

   That helper can be ours. A second path is an unreadable intermediate parent whose descendants outlive it; current code deliberately retains transitive descendant identities (`:702–747`) and reconciles them independently (`:786–829`). Downgrading the root must not erase those obligations.

   **Fix:** reject the universal downgrade. Preserve uncertainty for unresolved ancestry/identity candidates. If reducing false positives, require affirmative evidence of non-ownership or strengthen ownership capture at spawn. Add tests for both escape paths, PID reuse, unreadable parentage, and descendants surviving a vanished root. Neighbouring system services do not identify PID 89820.

4. **P322 — SHOULD-FIX: “interleaved legs” is insufficiently specified.**  
   The existing runner groups both languages into model blocks; s2 reverses model order (`benchmark/chains/c147/run_tg1_chain.py:30`, `:92–110`). Adding arms in a fixed order can confound scaffold with hours of thermal, background-load and web-content drift. Two sessions cannot fully balance three arm positions.

   **Fix:** pre-register a constrained randomized block schedule with balanced arm positions across item blocks and sessions. Keep one loaded model while comparing its arms; use distinct worker loads for s1/s2. Record the realized schedule and state. For latency claims, enforce the project’s power, battery and idle rules; merely running arms back-to-back does not satisfy them. Treat cache reset/warmup as part of the schedule.

5. **P323 — SHOULD-FIX: version plus executable SHA is inadequate for npm harness snapshots.**  
   A CLI entrypoint hash can remain constant while imported packages change. Pi’s published installation guidance explicitly distinguishes installations with pinned dependencies from ordinary npm installation ([package documentation](https://www.npmjs.com/package/%40earendil-works/pi-coding-agent?activeTab=code)).

   Also, harness version is **already outside** the tg1 policy dictionary: `identity()` records it separately (`benchmark/bench/tg1_runner.py:303–355`). The version constants still affect `probe_code_sha256` because the adapter source is hashed. P315 therefore needs P311’s identity split, not simply relocation of a field.

   **Fix:** snapshot package tarball integrity, resolved dependency lock/tree, runtime version, plugins/extensions and generated configuration. Make installations immutable; verify before each leg and at exit, including resume. Store the adopted manifest hash in `chain.json`. Adoption must be atomic and cannot retarget an active chain. A canary proves an exact snapshot, not an untested version range.

6. **P324 — BLOCKER: M64 lacks sufficiently precise acceptance and power definitions.**  
   `docs/PLAN.md:178` requires accuracy equivalence and lower tokens/task, plus subjective equivalence. With 43 items and only two independently loaded sessions, ±5pp equivalence is not assured even near ceiling. Repeated seeds and judges do not manufacture additional independent items or loads. Three arms introduce multiple comparisons, and “lower tokens/task” lacks a declared denominator and significance rule.

   **Fix:** before implementation, specify:
   
   - Pi–opencode and dsh–opencode as primary contrasts; whether Pi–dsh is exploratory.
   - Accuracy endpoint, interval construction, multiplicity family and realistic power simulations.
   - Tokens over **all assigned tasks**, including failures, retries, auxiliary requests and interrupted generation; separate input/cache/output/reasoning totals.
   - Whether token improvement requires an interval excluding zero and any minimum worthwhile reduction.
   - Subjective score scale, ties, missing judges, length-adjustment model and equivalence target.

   Both-pass judging measures quality conditional on joint success. Report its coverage and exclusive solves; use pair-specific intersections rather than unnecessarily requiring all three arms to pass.

7. **P325 — SHOULD-FIX: the arm-aware runner needs a contract, not an expanded map of opencode fields.**  
   Existing barriers verify scaffold, policy, seeds, registry, predictor and worker identity (`benchmark/chains/c147/run_tg1_chain.py:487–520`). Existing A4 is explicitly opencode-only (`benchmark/bench/chain_ops.py:576–598`).

   **Fix:** require each arm to prove, before scored work:
   
   - Exact snapshot, adapter/generation identity, effective configuration and prompt/tool-schema hashes.
   - Correct sole router, served registry, model, predictor state and loaded worker identity.
   - Identical corpus/grader, paired `sampler_seed` schedule and actual wire seed/sampling fields.
   - Thinking ON, resolved thinking budget, maximum generation, context headroom and all token/request/progress limits.
   - Compaction and retries disabled, bounded tools, cancellation and cleanup semantics.
   - Hermetic HOME/config, declared extensions/skills, endpoint and egress policy.
   - Session isolation, session-ID routing, within-task reuse and absence of cross-task cache contamination.

   Normalize client events into a common accounting contract, and reconcile them with server observations. An exit code of zero must never establish success. Validate injected stall/loop/allocation positives for every arm, not just happy-path fixtures.

8. **P326 — SHOULD-FIX: fairness requires declaring what belongs to the scaffold treatment.**  
   Current opencode disables compaction, denies subagents and web search, but permits filtered web fetch (`benchmark/opencode_bench_v2_web_tg1.json:10`). Pi without a fetch capability would receive a different information surface. Identical numerical seeds also do not imply identical random trajectories after prompts diverge.

   **Fix:** keep deployed sampling, thinking limits, context allowance, retries, tool deadlines, corpus access and web resources controlled. Preserve native system prompts and editing tools if evaluating deployable scaffold packages, but hash and disclose them as treatment components. Standardizing prompts answers a different question. Define treatment of `developer` roles and thinking-history echo, since both affect server templates and session-cache reuse.

9. **P327 — SHOULD-FIX: the proposed work order is backwards, and “untouched opencode” needs qualification.**  
   Keeping opencode’s generation behavior stable is sensible. Keeping its orchestration, validation and accounting exempt from the common contract is not. Its current identity hashes grading and audit modules alongside generation (`benchmark/bench/tg1_runner.py:319–342`).

   **Fix:** order the work as follows: approved estimand/acceptance specification → P311 identity boundaries and adapter contract → golden opencode regression verification → Pi adapter → current dsh adapter → arm-aware scheduler → adoption tooling. Keep the frozen dsh adapter available for historical reproduction; build a new current adapter, reusing audited components where useful. “0.1 → 0.2 likely breaking” alone does not justify a wholesale rewrite.

10. **P328 — SHOULD-FIX: cheaper valid designs exist, but anchors cannot certify no drift.**  
    Use a small, preselected, stratified anchor set to detect gross changes and prioritize work. Include long reasoning, tool-heavy, context/cache-sensitive and known timeout cases. Passing anchors supports adoption engineering; it does not establish ±5pp model-ranking stability on unmeasured items.

    **Fix:** keep the currently adopted reference frozen while evaluating both challengers, sharing that reference run. Screen challengers on paired blocks, then expand survivors using pre-registered stopping rules. Sequential inference needs valid stopping-adjusted intervals or a separate confirmation set. Partial re-baselines can support explicitly limited conclusions; they cannot silently refresh the full ladder.

    Also correct the cost model: three equal-cost arms cost 50% more than two, while adding a fresh reference to one challenger doubles that comparison’s work. Existing reload is only a seeded Python pilot for the first model, not a full third session (`benchmark/chains/c147/run_tg1_chain.py:33`, `:79–80`). The 27-hour estimate needs an explicit schedule and pilot-based heavy-tail allowance.

11. **P329 — SHOULD-FIX: stopping c144-base loses useful evidence, though resuming need not be worthwhile.**  
    Not resuming forfeits a completed second-load replication, reload control and a completed repeat on the old identity. The validated s2 Python leg still contributes descriptive evidence; the chain is not merely “s1 in hand.”

    **Fix:** archive all validated legs, partial artifacts, failure evidence and the exact stopping rationale. Report their unequal coverage without promoting them to completed k=2 evidence. Do not salvage selectively completed items from the aborted leg for ranking. Stop for a prospective methodology decision, not because observed scores look sufficient.

    I could verify the checkout is `170af9c0`. The cited run directory, abort artifacts, C164/P311 approvals and Pi source snapshot were not available in the reviewed repository. The npm search results did not reliably establish the stated release counts. Treat those claims as unverified until their exact evidence is attached. The opencode distribution source, however, is already documented: a SHA-pinned Homebrew bottle (`scripts/install_bench_opencode.sh:1–10`).

**Revised P315 recommendation:** adopt deliberate snapshot updates between decision families, with exact dependency snapshots and canaries. Retain within-family reference versions and explicit bridge requirements. Drop “only pooling is lost” and “supported range proven by canary.”

**Revised P316 recommendation:** specify estimands, statistical gates and the common arm contract first. Preserve opencode generation behavior while testing it through shared validation. Add current dsh alongside its frozen historical adapter. Resolve timeout and token-accounting asymmetry before matched-budget certification.

**Revised P317 recommendation:** reject as written. Preserve descendant reconciliation and fail closed where ownership remains unresolved; propose a narrower fix backed by adversarial process-tree tests.

**Revised P318 recommendation:** stopping is reasonable if C164 is explicitly superseded and M64 gets a fresh concurrent reference. Preserve every validated leg and acknowledge the lost replication/control. Resume only if completing that old-identity repeat remains decision-relevant.

AGREE WITH CHANGES: decision-family snapshots, C154 estimand and accounting controls, explicit arm contract and balanced scheduling, powered acceptance criteria, rejection of P317 as written, preservation of aborted-chain evidence