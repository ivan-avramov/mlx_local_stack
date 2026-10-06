# Proposal: ReviewBench as a code-review selection axis

Recorded: 2026-10-05. Status: proposed; document creation authorized, implementation and model calls not authorized. No milestone assigned or execution queued. `PLAN.md` remains the sole queue.

## Recommendation and purpose

Qualify ReviewBench as an additional B-ladder axis: identifying and explaining actionable problems in unfamiliar code changes. Start with a bounded pilot; adopt the standing axis only after the corpus, scaffold and scoring instrument pass review.

Code review complements code generation, test-driven repair and shell-tool interaction. A model can solve an exercise or navigate a shell while missing a regression in an existing implementation. Conversely, a capable reviewer may not reliably produce a correct repair. Keep these capabilities separate.

The initial comparison should use `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` and `Qwen3.8-27B-mlx-uniform-4bit`. Additional candidates need a later scope decision. ReviewBench would contribute evidence for the B ladder; it would not replace execution-graded coding, the C panel, or the retrieval/reasoning depth ladders. No result automatically changes picks or order.

## Upstream evidence inspected

The public repository and methodology were inspected on 2026-10-05. These are upstream descriptions, not measurements of this stack:

- Full corpus: 219 PRs from 187 repositories across 19 languages. The 25-PR showcase is a subset of that corpus, not a held-out test set. TypeScript and Python account for about half the full corpus; 35.6% of PRs change more than 1,000 lines. GitHub-wide representativeness does not establish representativeness for our workloads. [Repository](https://github.com/review-bench/ReviewBench)
- Golden findings combine human review comments, inferred author follow-up fixes, deterministic tools and LLM reviewers. Findings are deduplicated and labels human-audited. The published methodology reports TP/FP agreement of 96.6%, exact severity agreement of 62.9%, and exact category agreement of 79.7%. Agreement does not measure exhaustive issue coverage or guarantee candidate-finding judgment accuracy. [Methodology, sections 4–5](https://github.com/review-bench/ReviewBench/blob/main/docs/METHODOLOGY.md)
- GitHub reports that offline changes predicted the direction of subsequent Copilot production experiments. This supports relevance to their review system; transfer to local models and opencode is unmeasured. [Launch article](https://github.blog/ai-and-ml/github-copilot/reviewbench-an-open-benchmark-for-ai-code-review/)
- A private evaluation can generate normalized findings independently and invoke the published judging pipeline afterward. Official leaderboard results require their onboarding/final-run process and judge. Locally computed results must be described as private evaluations with their exact configuration. [Judging guide](https://github.com/review-bench/ReviewBench/blob/main/docs/JUDGING.md)

No reviewer, judge, container, dependency installation or corpus checkout was run in this proposal session. The website's dynamic leaderboard was not verified. A source/code audit remains necessary before relying on the published runner's behavior.

## What the result would mean

The measured unit is `(model, deployed tune, predictor state, serving fingerprint, opencode scaffold, review protocol)`. Hold the scaffold and task access constant across models. A score does not isolate intrinsic model capability from repository exploration, tool fluency or output formatting.

This is PR-review evidence. Record actual prompt/context sizes and context-required labels before claiming broader repository reasoning. A large repository or a 1,000-line diff does not establish 256K reasoning. Keep any future long-context extension as a separately specified axis; do not pad this corpus and call it an upstream ReviewBench result.

A new benchmark release is not a contamination guarantee. Audit PR/snapshot dates and candidate cutoffs where available. Public golden findings, historical review comments and later fixes are potential leakage paths. Do not describe this as the contamination-resistant coding decider parked under M56.

## Proposed review protocol

Use a private local runner around the existing opencode scaffold and the HTTP router. Reuse existing provenance and monitoring components. Preserve upstream PR identity, base/head snapshots, diff semantics and normalized finding schema. Do not require leaderboard submission or expose the router externally.

Each PR receives a fresh isolated agent session with the frozen repository at head, the base commit, the diff, title and body. The task asks for atomic findings with repository-relative file, head-line range, and an explanation of the problem and its consequence. Permit inspection of related files; prohibit modifying the checkout, fixing the issue, accessing golden findings, fetching historical review comments or looking up later fixes. Apply the same instruction and output contract to every model.

Isolation must be enforced, not merely requested in the prompt. Before choosing a native sandbox or container, audit what the existing opencode tool policy actually permits. Restrict agent access to the task checkout and necessary runtime/configuration paths; deny benchmark/golden directories, unrelated host files and external repository/web access. The local router remains reachable. Separate trusted corpus preparation and output collection from agent tools. Do not allow repository-local instructions/plugins to load unrecorded tools or reveal benchmark data. Record the chosen policy.

Upstream supplies minimised repositories and forbids access to the original repository during official runs. Reproduce that information boundary locally, including exclusion of future commits and review evidence; do not substitute a full current upstream checkout. [Agent contract](https://github.com/review-bench/ReviewBench/blob/main/AGENT_CONTRACT.md)

Selection uses predictor OFF with deployed sampling via `params_for(model, profile="deployed")`, thinking ON and generous fixed budgets. Do not retune temperature or thinking to this corpus. Record all sampling fields, resolved headroom and per-turn termination. If the axis backs a pick, qualify its shipped predictor state separately under the existing certification policy.

Pin opencode, source revisions, skill policy (`OPENCODE_DISABLE_EXTERNAL_SKILLS=true`), effective client configuration and the review prompt. Verify that seed propagation actually reaches model requests; a seeded item schedule is not proof of seeded generation. If the scaffold cannot propagate seeds, record that limitation and resolve the protocol before the full campaign.

Use M50/C106 entry/exit checks, the served registry hash and actual provider baseURL. Keep one resident model, lean benchmark routing, session retention 1, APC absent and suffix OFF. Fresh instances and paired schedules follow C109: two independent loaded instances per model, distinct schedules, and a same-seed reload control. Pair results within each session; do not pool sessions or historical fingerprints.

The official default is 15 minutes per PR, with retries and all-or-nothing run completion. Those defaults are unsuitable to import silently: local decoding and generous thinking can exceed the wall cap. Derive HTTP timeouts from generation limits and measured decode floors, specify a common turn/episode budget, and retain transport retries=0. Freeze limits before comparing models. If our limits or scaffold differ, label the result as a private adapted protocol. [Agent contract](https://github.com/review-bench/ReviewBench/blob/main/AGENT_CONTRACT.md)

## Scoring and proposed policy exception

Keep upstream finding-level metrics with their actual definitions:

| Metric | Meaning | Proposed use |
|---|---|---|
| Grounded recall | Known golden TPs covered by the reviewer / all golden TPs | Main coverage endpoint, reported per session |
| Grounded precision | Matched candidates inheriting TP / all matched candidates; unmatched candidates excluded | Diagnostic; cannot establish noise suppression |
| Augmented precision | Matched TPs plus unmatched judge-approved TPs / all candidate findings | Essential companion for usefulness/noise |
| Augmented recall | Coverage plus novel approved TPs / golden TPs plus novel approved TPs | Diagnostic only; denominator depends on the agent |

Source: [methodology, sections 6–7](https://github.com/review-bench/ReviewBench/blob/main/docs/METHODOLOGY.md). Semantic matching is file-constrained and LLM-based; inspect missed cross-file anchors and spurious matches in the audit. Preserve raw correspondences and classifier verdicts.

This proposal requires an explicit exception to the standing execution-graded coding/ranking rules: code-review findings are judged observations, not executable solutions, so do not relabel recall as `acc_strict`. Proposed comparison: strict grounded coverage under matched budgets, accompanied by augmented precision and false positives per PR. Retain all intended PRs in coverage denominators; model-caused no-submit, malformed-output, turn-cap or budget failures receive zero strict coverage. Retain partial findings for a separately labelled diagnostic; do not count a failed review as a successful precise review.

Transport, preparation and judge failures abort rather than becoming model-quality failures. Do not publish an incomplete intended corpus as a complete score. Distinguish a valid empty review from missing output: empty reviews have zero coverage where golden TPs exist and undefined precision, not perfect precision. Freeze handling of PRs with no golden TPs and macro/micro averaging before implementation.

Report macro and micro coverage/precision, unmatched counts, false positives per PR, and model/format failures. Predeclare overall coverage plus correctness/security/reliability and medium/high-severity slices; retain all-severity upstream results so filtering cannot hide low-severity behavior. Exact severity/category labels are imperfect, so slices are supporting evidence, not an automatic decider.

No F-score or capability/speed composite governs selection. A recall improvement with more false positives is a tradeoff, not an unqualified win. The operator must approve any precision non-inferiority margin or minimum precision rule before it becomes an adoption/ranking gate. An inconclusive comparison can support a labelled provisional recommendation; it cannot establish equivalence.

Use paired PR-cluster intervals, retaining finding dependence within a PR; account for repeated draws inside PRs if applicable. Report each independent session separately, uncertainty and endpoint-specific power/MDE. Do not reuse binary-task MDE values for fractional PR recall or treat thousands of findings as independent tasks. Apply Holm across the predeclared endpoint family. Two sessions do not estimate shared session variance reliably.

## Judge qualification and evidence retention

Start with the published rubric and exact official judge configuration after verifying its current identity (the inspected docs name Claude Sonnet 5). Freeze matcher/classifier prompts, model revision, tool access and settings. External judging runs after generation; do not load a second local heavyweight model beside the reviewer. Provider access, cost and permission for paid calls remain operator decisions.

Before full scoring, validate the instrument against known positives and negatives: exact and paraphrased matches, same-location different issues, wrong-file anchors, duplicate findings, plausible claims blocked by an existing guard, and valid findings absent from gold. Use model-blind manual checks of matches and unmatched verdicts across both arms. Include a second model family on disputed/material cases. This is calibration/adjudication, not permission to replace the official scoring configuration without disclosure.

Pre-register the calibration sample, numerical tolerances and adjudication procedure in the implementation spec. Do not claim a calibrated instrument merely because a five-item smoke passes. Systematic match/classifier errors block ranking until resolved; preserve original and revised verdicts.

Persist reviewer transcripts, per-turn request/response metadata, raw/normalized findings, failures, matches, judge outputs, prompt fingerprints, dataset hashes, model/config revisions and checkpoint completeness. Separate generation from judging so revised judgments can regrade saved findings without reviewer inference. Verify whether the upstream CLI supports the needed intermediate persistence/resume; do not assume its final metrics JSON is sufficient.

## Stages and adoption gates

1. **Design audit, no model calls.** Pin upstream revision; inspect manifests, snapshots, gold TP/FP coverage, dates, rubric, matcher, scoring code, empty/missing handling and judging persistence. Specify sandbox, seed propagation, limits, policy exceptions and acceptance tests. Present concrete implementation surfaces and obtain approval.
2. **Build after approval.** Minimal corpus adapter, opencode driver, finding validator, judging bridge and reporting. Failing tests first; mock router, opencode and judge. Required controls cover leakage denial, wrong snapshots, malformed/empty output, duplicates, denominator preservation, timeout/failure accounting, transport abort, provenance drift, resume compatibility and cleanup. No fork or deployment change is expected; any discovered need gets a separate proposal.
3. **Five seeded-random PR smoke after run approval.** Repeat on the loaded instance, record output/score variability, then the reload control. Validate the complete generation-to-judgment path. Estimate runtime from mean and max, plus heavy-tail allowance; measure judge tokens/cost. Log power, progress, errors and convergence every five minutes.
4. **25-PR feasibility/calibration pilot.** Both models under the frozen protocol. Inspect task exploration, context, output validity, judged noise and material disagreements. This set qualifies feasibility and the instrument; it does not decide the B ranking. Do not optimize prompts against public gold or select the best of repeated pilot runs.
5. **Full 219-PR comparison only after a review checkpoint.** Approve the measured resource envelope and any unresolved exceptions first. Two models × two independent instances × 219 PRs = 876 reviewer episodes, excluding smoke, repeatability controls and calibration. No hour/cost estimate is credible until the pilot. Freeze the final protocol before the full run; retain every attempted episode.
6. **Operator adoption decision.** Adopt the standing axis only if leakage boundaries, provenance, strict denominator accounting and judge calibration hold, and findings provide interpretable evidence relevant to coding use. Similar model scores do not make the axis useless. Update the evidence tables on completion, label adaptation and uncertainty, and recommend a choice without automatic promotion.

All scratch checkouts, client homes, caches outside the approved exceptions, logs and scoring artifacts belong under verified `$STACK_WORKDIR` redirection. A docker requirement conflicts with the lean no-docker benchmark rule and needs a scoped ruling before use. Latency claims require matched power/thermal state and order-balanced arms under the standing cooldown policy. Report reviewer wall time, tokens, judge cost and failure/runaway tax separately from coverage.

## Decisions to resolve before implementation

- **D1 Protocol:** recommended opencode with related-file inspection and enforced isolation; finalize native sandbox versus a justified container exception. Audit information parity with upstream snapshots.
- **D2 Ranking exception:** approve LLM-judged strict coverage as a new review endpoint, with augmented precision/noise alongside; choose any precision gate/margin before results.
- **D3 Instrument:** select judge provider/access and spending cap; pre-register calibration tolerances, adjudication and empty/no-gold aggregation conventions.
- **D4 Limits and reproducibility:** approve the common turn/episode budget, derived timeouts, seed-propagation treatment and exact cross-instance schedule.
- **D5 Execution:** authorize build separately from paid judge/model calls and the full 876-episode comparison. Decide scheduling against the live queue; do not infer priority from this proposal.

If taken forward, record operator rulings in `open-questions.md`, add the approved milestone to `PLAN.md`, and write a terse implementation spec with numbered acceptance criteria. Saving this proposal grants none of those later approvals.

## Sources

- [GitHub launch article](https://github.blog/ai-and-ml/github-copilot/reviewbench-an-open-benchmark-for-ai-code-review/)
- [ReviewBench website](https://review-bench.ai/)
- [ReviewBench repository](https://github.com/review-bench/ReviewBench/tree/main)
- [Methodology](https://github.com/review-bench/ReviewBench/blob/main/docs/METHODOLOGY.md)
- [Agent contract](https://github.com/review-bench/ReviewBench/blob/main/AGENT_CONTRACT.md)
- [Judging guide](https://github.com/review-bench/ReviewBench/blob/main/docs/JUDGING.md)
- Local context: `metrics.md`, `box-notes.md`, `regrade-vs-rerun-guideline.md`, `specs/m54-agentbench-os.md`, `specs/m55-polyglot-gap.md`, root `README.md` and `AGENTS.md`.
