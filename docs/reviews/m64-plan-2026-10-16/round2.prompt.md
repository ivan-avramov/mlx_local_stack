You are a cold, adversarial methodology and design reviewer (round 2). Round 1 had two independent reviewers (codex gpt-6.1-sol and Cursor gpt-5.6-sol-high); both reviews are appended below, followed by the lead's revised plan v2. Repository is the current directory, read-only — never edit, never run benchmarks; verify claims against code where possible.

Answer: (1) for EACH round-1 finding of BOTH reviewers, is it addressed by v2 (yes / partly / no, one line each)? (2) new problems introduced by v2; (3) anything still blocking an operator go on E1, E2 (as a spec to write, not yet a build), G1 and R1; (4) concrete edits to v2 that would make you agree.
End with exactly one verdict line: "AGREE", "AGREE WITH CHANGES: <list>", or "DISAGREE: <reason>".

==== ROUND-1 REVIEW A (codex gpt-6.1-sol) ====
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
==== ROUND-1 REVIEW B (Cursor gpt-5.6-sol-high) ====
## Findings

P1. blocker — P317’s ownership argument is false.

Evidence: `start_order()` is not merely a protected/skip optimization. An unreadable order prevents the normal cleanup classification (`benchmark/bench/proc_guard.py:864-871`), and a still-present process deliberately remains uncertain (`benchmark/bench/proc_guard.py:786-829`, `948-949`). C151’s regression explicitly requires this (`benchmark/bench/tests/test_c151_start_time.py:243-252`).

Concrete escaping path: a subprocess spawned by a tracked client after the last successful tick, then reparented or otherwise missed by ancestry tracking, with readable cwd/argv outside the run roots and unreadable start order. It is ours, but under P317 it is neither tracked nor path-attributed, so it becomes a non-uncertain orphan. Backward wall-clock movement makes fallback ordering unsafe (`test_c151_start_time.py:195-206`).

Fix: retain fail-closed uncertainty for every live eligible process with unreadable order. Reduce false aborts using a longer bounded final reconciliation window. Add a test for an unreadable, untracked owned descendant. Match tracked processes by `(pid, start_time)`, never PID alone.

P2. blocker — pure floating versions cannot support cumulative model selection.

Within-chain comparisons are valid, but P315 explicitly makes cross-chain results descriptive. That prevents comparing finalists evaluated under different harness epochs. Re-running one reference arm does not solve model×harness-version interaction: stable reference performance does not establish stable challenger behavior.

Current code correctly treats version and executable SHA as identity, not a statistical covariate (`benchmark/bench/chain_ops.py:717-757`; `benchmark/bench/tg1_runner.py:1054-1057`).

Fix: use decision epochs. All finalists for one selection decision must run under one immutable snapshot. Bridge releases with old/new versions on the same loaded instances, seeds, anchor items, and at least two models.

P3. should-fix — the proposed adoption canary proves compatibility, not behavioral safety.

A two-item smoke cannot detect modest accuracy/token drift, retries, compaction effects, or C154’s 60-minute behavior. C154 is specifically a long-request failure (`benchmark/bench/token_turn_gate.py:30-36`).

“Supported range proven by the canary” is also too broad: testing one release proves that exact `(version, executable SHA)`, not a semantic range.

Fix:
- Offline contract gate for wire/event compatibility.
- Old/new bridge on 8–12 deliberately sensitive anchors: long request, many turns, web/tool use, provider error, compaction pressure.
- Two active model anchors to expose interactions.
- Group-sequential early rejection for clear drift; never early acceptance of equivalence without adequate power.
- Exact tested-version allow-list.

P4. blocker — the current runner is structurally opencode-only.

It hardcodes:
- Scaffold and output stems: `run_tg1_chain.py:28-33`, `82-88`.
- Opencode-specific CLI arguments: `run_tg1_chain.py:124-131`.
- A4 v2 gate: `benchmark/bench/chain_ops.py:577-595`.
- Opencode runtime identity and evidence fields: `chain_ops.py:717-757`, `823-879`.

P316’s “arm-aware runner” needs a real adapter contract, not conditionals scattered through the existing runner.

Fix: define an `ArmAdapter` contract covering command construction, identity fields, preflight gate, evidence validation, progress events, transport classification, and transcript location. Keep router/model lifecycle shared.

P5. blocker — M64 has not defined its estimand or fairness boundary.

There are two different experiments:

1. Controlled loop comparison: equal retries, compaction, budgets, web policy, and tool bounds.
2. Product-bundle comparison: each scaffold’s native system prompt, tools, retry and compaction behavior.

The plan currently mixes them. Opencode tg1 has compaction off, webfetch enabled with denials, websearch disabled, retries vetoed, and shell bounds (`benchmark/opencode_bench_v2_web.json:9-97`; `benchmark/opencode_plugins/toolbounds.js:1-11`). Legacy dsh retries transport five times (`benchmark/run_dsh_probe.py:365-374`). The stated Pi defaults differ again.

Fix: pre-register one estimand. My recommendation is:
- Hold external controls fixed: server sampling, seed, thinking/max-token budgets, token/turn ceilings, web policy, shell timeout, one logical attempt, no ambient instructions.
- Treat native system prompt and core tool schemas as the scaffold treatment.
- Disable retries and auto-compaction across all arms; otherwise label the study a product-bundle comparison and record every retry/compaction event.

P6. should-fix — “interleaved legs” is insufficient protection against order and thermal confounding.

The current schedule is sequential by model/session (`run_tg1_chain.py:30-33`, `95-109`). A fixed opencode→Pi→dsh order would confound arm with elapsed time, thermal history, and server cache history.

Fix:
- Run complete item episodes atomically.
- Counterbalance arm order with a three-arm Williams/Latin-square schedule across items, sessions and picks.
- Use identical item order and seeds.
- Record per-arm start state and worker identity.
- Keep `MLX_VLM_CACHE_SESSION_MAX=1` verified (`chain_ops.py:192-198`, `252-265`); use fresh session IDs and prohibit cross-arm resume.
- Treat quality-chain wall time as descriptive. If latency is a decision axis, run a smaller dedicated order-balanced capture with the required ten-minute idle periods.

P7. blocker — C154 biases the proposed token endpoint as well as accuracy.

C154 loses the in-flight request’s usage. The gate only charges completed requests, and the existing report notes approximately 70–79K uncharged tokens (`benchmark/results/m63_mtp/M63_REPORT.md:111`).

Therefore “lower tokens/task” can reward the arm that censors work.

Fix: report:
- Primary strict result including all outcomes.
- Union-exclusion sensitivity where either arm has client-specific censorship.
- Tokens on the same union-excluded set.
- Censored-token lower bounds or server-side accounting separately.
- C154 incidence as its own endpoint.

P8. should-fix — version must remain generation identity, not merely a row “covariate.”

Version is constant within a chain and confounded with chain/time, so it cannot be statistically adjusted as an ordinary covariate. Moving it out of `scaffold_policy_sha256` is acceptable only if a combined generation identity still pins tool, version, executable SHA, adapter code, configuration and prompt/tool policy.

Fix: retain:
- Stable adapter-policy SHA.
- Per-arm immutable harness snapshot SHA.
- Combined `generation_identity_sha256`.
- Entry, pre-arm and exit executable-SHA verification.

P9. should-fix — do not unfreeze or rewrite the historical dsh probe.

`run_dsh_probe.py` is explicitly frozen, lacks M50, uses the legacy time gate and permits `--allow-version-drift` (`benchmark/run_dsh_probe.py:399-426`, `449-454`). Rebuilding it in place weakens historical reproducibility.

Fix: add a new tg1 adapter, e.g. `run_dsh_probe_tg1.py`, and leave the M35 runner frozen.

P10. should-fix — “leave opencode untouched” is right only at the probe-body boundary.

The opencode generation implementation should remain unchanged. The runner, A4 dispatch, manifest schema, stems, evidence roots and validation must change. Preserve the existing opencode path through a thin adapter and run all existing opencode chain tests plus replay/injected-positive tests.

P11. should-fix — the M64 acceptance rule is under-specified and usually underpowered.

At roughly 40 items, the documented nominal MDE is about ±20pp, not ±5pp (`docs/metrics.md:46-50`). TOST ±5pp can succeed in unusually low-discordance cells, but otherwise “not equivalent” will mostly mean inconclusive.

Also unspecified:
- Per-language and per-session analysis.
- Multiplicity across two picks and three scaffold pairings.
- Statistical definition of “lower tokens.”
- Pairwise-panel coverage when both-pass intersections differ.

Fix: pre-register per-session, per-language paired estimates; Holm families; superiority CI for tokens; explicit inconclusive handling; judge-specific results plus the two-judge mean; both-pass coverage and exclusive solves.

P12. should-fix — P318’s “stop” branch overturns C164 and loses real evidence.

The chain is finished with rc 2, not stopped: `$STACK_WORKDIR/c144-base/chain.json:1-8,509-770,1111-1140`; `driver.chain.rc:1`. Full s1 and one s2 Python leg are validated, but k=2 and reload are incomplete.

Not resuming loses:
- The second independent loaded-instance session.
- Same-seed reload control.
- A complete baseline under exact identity `d4319705…`.
- A bridge point for measuring later opencode drift.

The s1 slice is useful only as provisional single-session evidence, not a C164 or M64 baseline.

Fix: absent a new operator ruling, resume unchanged as C164 directs. “Resume” must be described accurately: archive the failed attempt and rerun the entire requested `s2 reload` schedule; the probe itself refuses a transport-aborted manifest (`tg1_runner.py:1092-1093`).

P13. should-fix — the 27-hour estimate appears optimistic.

The committed M64 estimate is 5–6 hours per pick for each additional arm (`docs/PLAN.md:178`), while the opencode chain was estimated near 18 hours and had already consumed about 13 hours before aborting partway through s2. Two new arms plus a fresh opencode arm suggests roughly 38–42 hours before heavy-tail allowance, not 27.

Fix: derive the queue estimate from the five-item random smoke per arm, then add observed p95/heavy-tail and C154 allowance.

P14. nit — several external facts lack durable provenance.

The repository confirms `origin/main=170af9c0`, opencode 2.0.20, and dsh 0.1.2-rc.1. It does not substantiate the release counts, latest Pi/dsh versions, or all Pi behavioral claims.

Fix: place dated source URLs, package metadata, lockfile/executable SHAs and source-tag SHAs in the M64 spec.

## Revised recommendations

P315: Replace pure floating with versioned decision epochs plus a cheap bridge:
1. Offline compatibility canary.
2. Old/new anchor crossover on two models and sensitive items.
3. Partial re-baseline when anchors are stable.
4. Full contemporaneous finalist comparison when drift appears or a selection decision changes.
5. Never pool across epochs; retain a connected evidence graph through overlap arms.

P316: Order the work as:
1. Define estimand, fairness matrix and acceptance rules.
2. Implement P311 generation/scoring identity split.
3. Define generic arm/manifest contracts.
4. Wrap the unchanged opencode probe and prove regression parity.
5. Build Pi tg1 adapter.
6. Build a new dsh tg1 adapter, leaving M35 frozen.
7. Add contract, wire, transport, retry, compaction and M50 tests.
8. Run randomized five-item smokes, then the balanced full chain.

Each arm must verify exact executable/version/SHA, config and prompt/tool SHAs, M50 destination and router hash at entry/exit, deployed sampling on every request, seed, budgets, retry/compaction state, progress accounting, worker identity, session-cache policy, evidence hashes, test integrity and transport classification.

P317: Reject. Keep live unreadable-order processes uncertain. Add bounded delayed reconciliation and the missing owned-descendant regression test.

P318: Resume by default because C164 still governs. Stop only after explicit adoption of the revised P315 and a commitment to rerun opencode contemporaneously in M64; then archive c144 as incomplete, single-session descriptive evidence.

P315/P316 should also add the explicit controlled-vs-product estimand, release bridge, arm-order schedule, C154 token handling, multiplicity/power rules and realistic cost. Drop “supported range proven by canary,” version-as-covariate, in-place dsh unfreeze and P317.

DISAGREE: P317 is unsafe, and P315/P316 need version bridges, an explicit fairness estimand, balanced arm ordering, and stronger per-arm verification before they can support model selection.

==== PLAN v2 ====
# Plan v2 (2026-10-16) — revised after round-1 reviews (codex gpt-6.1-sol: AGREE WITH CHANGES; Cursor gpt-5.6-sol-high: DISAGREE)

Context and facts are as in v1 (repo at the reviewed commit; key files tg1_runner.py, run_opencode_probe_v2.py,
run_dsh_probe.py, chains/c147/run_tg1_chain.py, chain_ops.py, proc_guard.py; PLAN M64; C154, C161, C164, P299, P311).
Corrections accepted from round 1: opencode's distribution is the SHA-pinned Homebrew bottle
(`scripts/install_bench_opencode.sh`); release counts and Pi facts get dated source URLs + package metadata in the
M64 spec (they were gathered from the npm registry and a source read of earendil-works/pi at 4954d76); the reload
leg is a seeded 5-item Python pilot of pick 1, not a full session. Operator constraint: harness pins cannot be held
for long — "these get updated often and we need to be able to move on."

## E1 (replaces P315) — Decision epochs, not long-lived pins and not free floating
1. **Epoch** = one immutable harness snapshot vector: per harness tool, version, npm tarball integrity + resolved
   dependency lock/tree hash (or the Homebrew bottle sha for opencode), executable sha, runtime (node) version,
   generated config + system-prompt + tool-schema hashes. Installed immutably under `$STACK_WORKDIR/<tool>-<ver>`,
   recorded in `chain.json`, verified at chain entry, before every leg (including resume) and at exit.
2. **Decision family** = all arms and models of one decision (e.g. M64's scaffold decision; one model-selection
   round incl. its follow-up confirmations). A family runs within ONE epoch, contemporaneously. No stored baselines
   reused across epochs.
3. **Between families we move to the latest releases** (answers the operator: no long pin). Adoption gate per new
   snapshot: (a) offline contract tests for that EXACT snapshot (mock provider, recorded event fixtures, first-request
   wire capture of sampling fields, roles, max-tokens, tool/extension surface, no egress) — an exact allow-list, never
   a "supported range"; (b) a bridge: old vs new snapshot interleaved on the same loaded instance and seeds, two
   models, 8–12 pre-registered sensitive anchors (long request, many turns, tool-heavy, timeout-prone, known C154
   items, provider error). The bridge detects gross drift only and is labelled so; it never certifies equivalence.
   Outcomes: adopt / fix adapter / hold the old snapshot.
4. **Never pool across epochs; no transitive rankings across epochs without bridge evidence** (overlap arms).
   README evidence carries its epoch label; older evidence is not deleted, it is "as of epoch E".
5. Harness snapshot is part of the GENERATION identity (P311): `generation_identity_sha256` = adapter code + snapshot
   vector + config/prompt/tool-schema hashes; `scoring_code_sha256` separate. Not a statistical covariate.
Cost: a bridge ≈ 1–2 h GPU per adoption instead of an ≈18 h re-baseline; every decision family re-runs its own
reference arm.

## E2 (replaces P316) — M64 design
1. **Estimand: controlled-loop scaffold comparison.** Held fixed across arms (verified on the wire per request):
   deployed server sampling (`params_for(model, "deployed")`), paired `sampler_seed` schedule, thinking ON with
   resolved budget 81,920 and max 102,400, context allowance, M62 token/turn ceilings, ONE logical attempt (client
   retries off), auto-compaction off, no ambient instruction files (Pi `-nc`, hermetic HOME/config), shell-tool
   deadline equal across arms (enforced by the harness, not by trusting the client), the same web policy for all arms
   (recommend: NO web for every arm — Pi has no fetch tool natively, dsh's web tool was disabled in M35; the opencode
   arm then uses a tg1 carrier with webfetch denied, i.e. a new opencode scaffold label; operator decision), egress =
   loopback only (C160 socket sampling in every smoke). **Treatment** = each scaffold's native system prompt, native
   tool schemas and loop logic — hashed and disclosed. The `developer` role / thinking-history echo behaviour is
   recorded per arm (it affects templates and the server session cache).
2. **Endpoints, pre-registered:** primary contrasts Pi−opencode and dsh−opencode per pick (Pi−dsh exploratory);
   per session and per language paired `acc_strict@budget`, two-stage cluster bootstrap, TOST ±5pp, explicit
   "inconclusive"; Holm over 2 picks × 2 contrasts. Tokens over ALL assigned tasks (input / cache / output / reasoning
   separately; failures and auxiliary requests included), superiority CI excluding 0 (no minimum effect unless the
   operator sets one). Censoring (C154 and any client cut): incidence as its own endpoint per arm; union-exclusion
   sensitivity for accuracy AND tokens; censored-token lower bounds from server-side accounting. Power simulation
   from the observed paired discordance (P223, M63, c144-base) BEFORE launch; if ±5pp TOST is unreachable the spec says
   so up front. Subjective (C161): two-judge blind pairwise over PAIR-SPECIFIC both-pass items, judge-specific results
   + their mean, both orders, length adjustment pre-specified (logistic regression of preference on log length ratio;
   adjusted intercept), ties as 0.5, coverage and exclusive solves reported.
3. **Schedule:** one loaded worker per (pick, session) shared by its three arms; arm order counterbalanced with a
   three-arm Williams design across item blocks × sessions × picks; identical item order and seeds; fresh session IDs,
   no cross-arm resume; `MLX_VLM_CACHE_SESSION_MAX=1` verified; per-arm start state logged. Wall time descriptive;
   latency, if ever a decision axis, gets its own order-balanced capture under the power/idle rules.
4. **Architecture and order of work:** (1) M64 spec with estimand, fairness matrix, acceptance and power; cold review
   → operator go. (2) P311 identity split. (3) `ArmAdapter` contract: command construction, identity fields, preflight
   (A4-equivalent per client), event normalization into one accounting contract reconciled against server usage,
   transport classification (exit 0 never means success), evidence/transcript validation, cancellation/cleanup
   semantics. (4) Wrap the UNCHANGED opencode generation path in a thin adapter; prove parity with the existing chain,
   replay and injected-positive tests. (5) Pi adapter. (6) New `run_dsh_probe_tg1.py`; M35 `run_dsh_probe.py` stays
   frozen for historical reproduction. (7) Per-arm injected positives (stall, loop, hard ceiling). (8) Snapshot +
   adoption tooling (E1.3). (9) Seeded-random 5-item smoke per arm → cost estimate with heavy-tail and C154 allowance.
   (10) The M64 chain.
5. **Cost:** the round-1 estimate (27 h) was low; current best guess 38–42 h GPU before heavy tail for 3 arms × 2
   picks × (s1, s2) + reload; the smokes fix it.

## G1 (replaces P317) — guard residual, fail-closed kept
P317 is WITHDRAWN (both reviewers: an unreadable-order process can be ours and untracked/path-negative — e.g. a
helper whose order read failed before ancestry propagation, or a descendant spawned after the last tick). New, smaller
proposal for later (never mid-chain): keep every live eligible unreadable-order process uncertain, but extend the final
reconciliation with a bounded delayed re-check (e.g. up to 10 s) because the observed offenders (mdworker / XPC
services) exit within seconds; match tracked identities by (pid, start_time), never pid alone; add the
unreadable-untracked-owned-descendant regression test. Own open question; test-first; cold review.

## R1 (replaces P318) — resume the aborted c144-base chain now, unchanged
The GPU is idle for the whole E2 build (≈2+ days), so resuming costs no decision time. Archive the failed attempt
(M63 precedent: chain.json/out/rc/RUNLOG/s2 → `archive.attempt1-c157-residual`), relaunch `chain s2 reload` on the
unchanged identity `d4319705…` (≈10 h; s2 re-runs from scratch). Gains: the second loaded-instance session, the reload
control, a complete repeat of P223's design on a new identity, and the paired discordance estimates the E2 power
simulation needs. Status: descriptive / power-input evidence, NOT the M64 baseline (C164's P310 is superseded by E1/E2:
M64 runs its own opencode arm contemporaneously). Risk: another guard-residual abort (≈1 per 16 legs observed); G1
waits so all legs share one identity.
