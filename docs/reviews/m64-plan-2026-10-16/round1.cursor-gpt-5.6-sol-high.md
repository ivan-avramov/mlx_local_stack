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
