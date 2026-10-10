# Cold adversarial review: `docs/proposal-reviewbench.md` (Claude, review 1, 2026-10-05)

Scope: design review only. I made no model calls, started no servers, ran no benchmarks, and changed nothing in the repository. For analysis I downloaded upstream ReviewBench at commit `ceb0794a3768da6ef4a56e5311dfb4afd29e5dee` (main on 2026-10-05) to a temporary directory and deleted it afterwards. Tags: **VERIFIED** means checked against code, data or docs, with the source cited. **ASSUMPTION** means inferred and not yet checked. Repository citations are `path:line`. Upstream citations name the file at the commit above.

## Verdict

**REVISE before approval. Not ready to become an implementation spec.** The direction is sound: a separate review axis, private adapted-protocol labelling, failures counted in the denominator, PR-cluster intervals, and generation kept separate from judging. The proposal is also careful about what it does not claim. But six problems carry real weight, and the proposal either gets them wrong or misses them:

1. The opencode path sends no seeds today (R1).
2. The progress gate the proposal plans to reuse would kill every review after about 10 minutes (R5).
3. The M50 tripwire refuses the very config override that isolation needs (R3).
4. The shipped opencode has no isolation at all: bash, webfetch and host-wide shell are all allowed (R2).
5. Upstream's judge silently drops PRs that have no candidate file, and macro-averaging drops PRs where a metric is null (R8, R9).
6. The golden set is about 98 % LLM-produced, about 55 % of it by Claude-family reviewers, and it is judged by a Claude model. That is a lineage-affinity confound for this particular comparison (R12).

Each problem has a concrete fix, listed below. None blocks the axis in principle.

## Findings

### Seeds, sampling and limits

**R1 — Seed propagation does not exist on the opencode path. VERIFIED.**
- `benchmark/run_opencode_probe.py` contains no `seed` anywhere. The row hard-codes `"sample": 0` (`:718`), and the command is `opencode run --dir … --model mlx-local/<m> [--pure] <prompt>` (`:272-278`).
- The opencode carrier `opencode_config/opencode.json` sets no `seed` in any model's `options`. The global `~/.config/opencode/opencode.json` is byte-identical to the shipped file (checked with `cmp`).
- The server falls back to `DEFAULT_SEED` when a request has no seed (`src/mlx-vlm/mlx_vlm/server/generation.py:2619-2627`). It would accept one if sent: `FlexibleBaseModel` has `extra="allow"` (`schemas.py:46-49`), and `request_normalization.py:200` reads `seed`.
- So every turn of every opencode session to date ran on seed 0. M55's spec line "same seeds as the existing M9/M32 rows (`rowschema.sample_seed`)" (`docs/specs/m55-polyglot-gap.md:10`) is not what the probe did. Its own AC2 amendment admits "unseeded sampling" (`:19`).

Consequences:
- (a) C109's "distinct paired seed schedules" cannot currently be implemented for opencode.
- (b) Two unseeded sessions are correlated replays: same seed, near-identical prompts. Their between-session discordance understates true sampling variance.
- (c) A "same-seed reload control" cannot be told apart from an ordinary second session.

Fix: put a per-session seed into an opencode config overlay (`options.seed`), then prove it reaches the router (R4). ASSUMPTION: `@ai-sdk/openai-compatible` passes unknown model options through to the request body. The `top_k`, `min_p` and `thinking_budget` options appear to work through this path, but no request body has ever been captured to show it.

**R2 — Every unit-of-analysis claim about "deployed sampling via `params_for`" is unverified for opencode. VERIFIED gap.**
- opencode sends whatever its resolved config says.
- The probe records `params_for(model, "deployed")` into the manifest (`provenance.gather(..., profile="deployed")`, `run_opencode_probe.py:657-666`). It hashes the shipped file (`:320-331`) but never compares the model options opencode resolves against `params_for`.
- ASSUMPTION, worth checking: opencode may also send its own `max_tokens`. Recent opencode caps output tokens client-side, and which field wins in the request body is unverified.

Fix: at entry, parse the per-model `options` from `opencode debug config` and refuse unless they equal `params_for(model, "deployed")` minus fields the carrier deliberately omits (`reasoning_effort`, which the worker applies per `main_models.yaml:542`). Then capture one request body (R4).

**R3 — The M50 tripwire refuses the isolation config the proposal needs. VERIFIED.**
- `provenance.opencode_router_base` raises on `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR` and `OPENCODE_CONFIG_CONTENT` (`benchmark/bench/provenance.py:1368-1372`).
- The only remaining ways to apply a review-only permission policy or `steps` cap are all bad:
  - edit the shipped daily-driver config, which changes the scaffold hash for every future opencode row and alters the daily driver;
  - drop an `opencode.json` into each corpus checkout, which the model can see, which contradicts upstream's "your agent never learns it is part of a benchmark" (`AGENT_CONTRACT.md`), and which leaves recorded provenance pointing at the wrong file;
  - amend the tripwire.

Recommend amending it: accept exactly one repo-tracked overlay passed through `OPENCODE_CONFIG`, record its sha as scaffold identity, keep refusing the other two variables, and verify the merged result with `opencode debug config`. This is a stack change to `benchmark/bench/provenance.py`, not a fork change. It needs its own approval.

**R4 — No known-positive exists for what opencode actually sends. VERIFIED absence; the mechanism itself is an ASSUMPTION.**
- I found no captured request body and no worker log of received sampling fields (the worker log does not print them).
- Fix, no GPU needed: an integration test runs the pinned `opencode` binary against a local mock OpenAI-compatible server. The mock records request bodies and replays a scripted stream. Assert that `seed`, `temperature`, `top_p`, `top_k`, `min_p`, `presence_penalty`, `max_tokens`, `enable_thinking` and `thinking_budget` all arrive with the expected values.
- The same mock drives the leakage controls (R6) and a slow-stream test of opencode's client-side request timeout. ASSUMPTION: opencode has a default provider request timeout. Its semantics are undocumented on the providers page I fetched.

**R5 — Reusing the progress gate would kill every review at about 600 s. VERIFIED.**
- `bench/progress_gate.py:96-118` counts progress only as "failures decreased, or the file changed".
- With the defaults `tick_s=300` and `stall_ticks=2` (`:37-39`), a session that writes no solution file is declared `stalled` after two flat ticks.
- A reviewer that must not modify the checkout never shows progress. The kill rate would then depend on model speed and verbosity, which is an instrument artefact that can rank models.

Fix: replace the gate for this axis with:
- opencode `steps` (a native cap; ASSUMPTION per opencode agent docs);
- the deployed per-turn budgets;
- a derived wall backstop;
- a liveness monitor that kills only silent/IDLE wedges, per `AGENTS.md:48`.

The outcomes `steps_cap`, `deadline`, `no_output` and `invalid_output` are model-caused failures and score zero coverage.

### Leakage and information parity

**R6 — Shipped opencode has no tool isolation. VERIFIED.**
- `opencode_config/opencode.json` has no `permission` block. The only top-level keys are `provider`, `small_model`, `model` and `plugin`.
- opencode's documented default is "most permissions default to allow", with `external_directory` and `doom_loop` set to `ask` (opencode permissions docs, current web version; ASSUMPTION that pinned 1.18.30 matches).
- So `bash`, `webfetch` and edits are allowed. Bash is not confined to the project; only file tools fall under the external-directory check (`run_opencode_probe.py:137-143` explains why out-of-project file paths auto-reject in `run` mode).
- Concretely, a reviewer could `curl` the public golden JSON (`raw.githubusercontent.com/review-bench/ReviewBench/.../golden/*.json`), webfetch the PR page (human comments and later commits), `git fetch` a remote left configured (R7), or read anything in `~`. It would also execute untrusted repository code on the operator's daily machine: `npm install` postinstall hooks, test runners and build scripts from 187 repositories.

The proposal's "audit before choosing" is correct but understated: today the boundary does not exist.

**R7 — Upstream's local runner is not leak-free, so "reproduce the information boundary" means building it ourselves. VERIFIED (`scripts/try-agent.sh`, `docs/RUNNER.md`).**
- `try-agent.sh` fetches `base` and `head` with `--filter=blob:none`, a partial clone with a live promisor remote.
- It leaves remotes `origin` (the mirror) and `upstream` (the real GitHub repo) configured.
- When the mirror lacks a commit it falls back to `pull/$pr/head`, the PR's current head, which includes post-review fix commits now present in `FETCH_HEAD` and the object store.
- `RUNNER.md` admits "the script uses full clones, which is more forgiving". The official minimiser is not published.

The trusted preparer must:
- fetch exactly `base` and `head` by sha, with full blobs and no filter;
- never fetch `pull/*`;
- remove every remote and delete `FETCH_HEAD`, reflogs, stray refs and packs;
- run `gc --prune=now`;
- verify that every object reachable from all refs is an ancestor of `head` or `base`, and that `git config` has no URLs.

Upstream does provide a `.git` at head with history reachable from base and head (`AGENT_CONTRACT.md`, "What you receive"). Parity means including that minimised history, not stripping `.git`.

**R8 — Instruction files can contaminate the scaffold. The global file is a pre-existing gap; ASSUMPTION about whether it loads, high confidence from opencode rules docs.**
- opencode loads `AGENTS.md`/`CLAUDE.md` by walking up from the cwd. If no `~/.config/opencode/AGENTS.md` exists, it also loads `~/.claude/CLAUDE.md`, unless `OPENCODE_DISABLE_CLAUDE_CODE` or `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` is set.
- VERIFIED: no `~/.config/opencode/AGENTS.md` exists on the box. A `~/.claude/CLAUDE.md` exists. The probe env sets only `OPENCODE_DISABLE_EXTERNAL_SKILLS` (`run_opencode_probe.py:302-314`).
- If the docs apply to 1.18.30, the operator's private global instructions are in the system prompt of every opencode probe row, M55 included. Exported transcripts do not contain the system prompt, so I could not confirm this from rows.
- That is a newly discovered pre-existing issue and needs its own proposal. For ReviewBench: set `OPENCODE_DISABLE_CLAUDE_CODE=1`, and record each checkout's own `AGENTS.md`/`CLAUDE.md`/`.opencode/` presence. Repository-local files are identical across arms and are legitimate project context, but record them. Also check that no ancestor of the scratch root carries rules files.
- Minor: `small_model` points at the task model on :8092 (not running on the lean router), which the M50 destination check does not cover.

### Upstream scoring as implemented (all VERIFIED in `scripts/eval/*.ts` at `ceb0794`)

**R9 — Missing candidate files silently leave the denominator.**
- `buildEvalInputSummary` evaluates only the intersection of candidate PRs and golden PRs (`input-validation.ts`, `evaluation_keys = overlapKeys`).
- Strict mode flags candidates without gold, never gold without candidates.
- So a PR the reviewer failed on disappears unless we write a file for it. The proposal's "retain all intended PRs" therefore cannot rely on upstream aggregation.

**R10 — Macro-averaging drops nulls. Empty reviews leave the precision average.**
- `scorer.ts`: `augmented_precision = null` when `candidate_count == 0`, and `grounded_recall = null` when `golden_tp_count == 0`. `averageMetric` filters nulls before taking the mean.
- An empty review contributes 0 to macro grounded recall (correct, if a file is written) but is invisible to macro augmented precision. A model that abstains on hard PRs pays no precision cost.
- Micro precision is not gameable this way, but it is finding-weighted.
- Four of the 219 PRs have zero golden TPs and are always null for recall.

**R11 — Other implementation facts the spec must pin:**
- The loader merges multiple files for the same PR ("combines findings from multiple valid files", `docs/JUDGING_INPUT.md`). Pointing the judge at a directory holding two sessions silently pools them. Use one judge run per (model, session, judge).
- `--limit` takes the first N keys in sorted order, not a random draw.
- A missing unmatched classification defaults to `fp`/`unclassified` (`normalizeUnmatchedClassifications`). Assert that zero `unclassified` labels appear.
- The matcher sees only file, lines and message, and never compares across files. The classifier has read/grep/find/ls tools over a mirror checkout.
- The matcher runs at `thinkingLevel: "low"` and the classifier at `"medium"`, with no temperature or seed control. Verdicts are stochastic.
- A judge error excludes the PR. Strict mode then exits 1 and keeps a checkpoint keyed on judge, prompts and inputs. That aligns with "judge failures abort".
- The CLI cannot accept revised intermediate verdicts. Adjudication needs our own scorer over `results.details.json`.
- Upstream final scores are the mean of three runs (`METHODOLOGY.md` §7.7). The proposal's k=2 is a deviation to label.
- Upstream retries failed PRs (`RB_ATTEMPT`) and fails the whole run if one never succeeds. Our policy of retries=0 and failure=0 is stricter, which is another labelled deviation.

### What the golden set actually is

**R12 — The gold is overwhelmingly LLM-produced, and Claude-family. VERIFIED by counting `golden/*.json` at `ceb0794`.**
- 4,632 golden findings, of which 2,623 are TP.
- TP producers:

| Producer | TPs | Share |
|---|---:|---:|
| `llm_review:claude-sonnet-4.6` | 1,206 | 46.0 % |
| `ccr:gpt-5.5` | 957 | 36.5 % |
| `ccr:claude-opus-4.7` | 228 | 8.7 % |
| `llm_review:gemini-2.5-pro` | 149 | 5.7 % |
| `human_review` | 39 | 1.5 % (17 PRs) |
| `llm_review:gpt-4o` | 36 | 1.4 % |
| `deterministic_tool:semgrep` | 8 | 0.3 % |

- There are zero inferred-author-action findings. 152 of the 191 human comments are labelled FP.
- The proposal's description ("combine human review comments, inferred author follow-up fixes, deterministic tools and LLM reviewers") follows the methodology prose ("human comments and inferred author actions form the backbone", `docs/EXTRACTION.md`), but the data contradicts it.
- Labels come from a Claude Sonnet classifier and were human-audited. That makes the findings LLM-sourced, Sonnet-labelled and human-audited, not human-grounded.
- Grounded recall therefore measures agreement with mostly Claude- and GPT-family reviewers, matched by a Claude judge.
- For this comparison specifically, ASSUMPTION: if `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` was distilled from a Claude-family teacher (the name suggests it; the repo does not document the teacher), it may share phrasing and issue selection with 54.7 % of the gold and with the judge. That biases both matching and novel-TP classification against `Qwen3.8-27B-mlx-uniform-4bit`, and it confounds exactly the delta we want.

Mitigations:
- run a second-family judge as well (D3);
- blind agent ids;
- report recall per gold producer as a pre-declared diagnostic: Claude-sourced, GPT-sourced and other gold separately. A delta that exists only on Claude-sourced gold is affinity, not capability.

**R13 — Slices are low power. VERIFIED.**
- Severity is 59 % low (1,551 TPs), 34 % medium (891) and 7 % high (181, in 63 PRs).
- Security has 98 TPs across 40 PRs. PRs with at least one TP: correctness 174, reliability 128, high+medium 190, broader-project-context 94.
- Overall recall is dominated by low-severity findings. Make high+medium (190 PRs) the one pre-declared secondary endpoint. Security, high-only and category slices are descriptive only and stay out of the Holm family.

**R14 — Corpus-size facts the proposal under-weights. VERIFIED from `corpus/manifest.json`.**
- Diff size: median 562 changed lines, p90 4,566, max 56,447. 19 PRs exceed 5k lines and 10 exceed 10k.
- Files changed: median 9, max 797. Repository size: median 6.4 MB, max 1.49 GB.
- The manifest carries no PR or commit dates, so the date audit needs commit dates from the mirror.
- The largest PRs will hit opencode's `limit.input` of 159,744 (`opencode.json`) and trigger compaction. Compaction behaviour depends on the model, so compaction events must be counted per episode. A model-independent overflow class, PRs whose diff alone exceeds the window, should be pre-declared and handled identically for both arms, never excluded after the fact.

**R15 — Contamination timing. Partly VERIFIED.**
- The ReviewBench repository was created 2026-09-04 (GitHub API).
- The `Qwen3.8-27B` base was released 2026-08-14 (`docs/PLAN.md` M56 row).
- Our `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` artifact was uploaded 2026-09-03 (`main_models.yaml:494`), so its distillation predates the repository.
- The golden JSON therefore cannot be in either model's training data. The PR code, any later fixes and the 191 human comments can be. ASSUMPTION: most PRs predate the cutoff, so contamination exposure is "seen the merged code", not "seen the gold".
- The proposal is right not to call this contamination-resistant.

### Statistics, power and sessions

**R16 — Power: a prior, not a void.**
- "No estimate is credible until the pilot" is too strong for a go/no-go on a build.
- ASSUMPTION: if the SD of the per-PR paired difference in grounded recall is 0.15–0.25, then n=219 gives a paired MDE of about 2.8·SD/√219 ≈ 3–5 pp per session, and n=25 gives ≈ 8–14 pp.
- Two variants of the same base checkpoint may well differ by less than that.
- Pre-register a stop rule: after the pilot, compute the projected n=219 MDE from the observed SD. If it exceeds 6 pp, or the projected box time exceeds the operator's envelope, do not run the full comparison.

**R17 — Runtime prior, ASSUMPTION.**
- M55 measured a mean of 226–379 s per item (max 636 s) on small exercises with context ≤ 27.8K (handoff).
- ReviewBench episodes read more files at larger contexts with thinking ON. A plausible prior is 10–25 min per PR.
- That puts 876 episodes at roughly 150–365 box-hours (about 6–15 days) before pilot and calibration, on the operator's daily machine.
- That cost belongs in D5 now.

**R18 — Session design.**
- C109 (k=2 sessions, accuracy paired per session, never pooled) applies.
- With R1 unfixed, the reload control is uninformative. Within-instance opencode runs are already nondeterministic (M55 AC2: 4/5 pass-identical, wall time up to 1.8× apart).
- Recommend:
  - per-session seeds, identical across models within a session;
  - a seeded-random PR order per session, identical across models;
  - model order counterbalanced (session 1: A then B; session 2: B then A);
  - the reload control replaced by a 5-PR same-instance repeat in the smoke, which measures within-instance repeatability.
- A ranking claim requires both sessions to agree in sign. Two sessions do not estimate session variance, and the proposal says so correctly.

**R19 — The pilot overlaps the full corpus.** The 25 test PRs are part of the 219. If any protocol element changes after the pilot, report the full result on all 219 and on the 194 PRs outside the pilot as a sensitivity check.

### Rules compatibility

**R20 — The proposal names only one of the rule exceptions it needs.**
- (a) `AGENTS.md:57`, ranking by `acc_strict@budget`, which the proposal names.
- (b) `AGENTS.md:60`: subjective quality uses a blind mixed-family panel over passing outputs. ReviewBench is a single-judge, single-family LLM pipeline.
- (c) `AGENTS.md:46`: explicit paired seeds through `rowschema.sample_seed`. This is unmet (R1).

All three must be ruled explicitly in `open-questions.md`, since AGENTS.md is owned by the operator.

**R21 — The docker conflict is narrower than stated. VERIFIED.**
- M54 ran a docker sandbox per task, and M55 graded in docker, both under the lean-router rule (`docs/PLAN.md` M54/M55 rows; `docs/specs/m54-agentbench-os.md` AC9).
- "Lean, no OWUI/docker" (`AGENTS.md:26`) governs the router stack, not task sandboxes.
- The real container hazard is different. ASSUMPTION: opencode inside a container reaching a router bound to host loopback needs a host-gateway route. It must not lead to rebinding the router, which would be a serving change and external exposure, nor to an M50 check that cannot see the container's destination.

**R22 — Output contract.**
- Upstream lets the agent write anywhere in a disposable checkout and reads a file outside it.
- The proposal's "prohibit modifying the checkout" is stricter than upstream, and with native opencode it conflicts with writing a findings file.
- Simplest parity-preserving contract: deny all edits, and have the reviewer return findings as the final assistant message, a JSON block. This is the same pattern as upstream's Codex example (`examples/codex-cli/agent.mjs`, `--output-last-message`). The runner extracts it from `opencode export`.
- One identical same-session format-repair turn (`--continue` with the validator error) for every arm is defensible, comparable to upstream's retry. Report first-shot validity separately as edit/format competence (`AGENTS.md` reporting rule).

**R23 — The proposal is correct on the following. VERIFIED against upstream:**
- corpus counts: 219 / 187 / 19 named languages plus "unknown", TypeScript+Python 49.8 %, 35.6 % over 1,000 lines;
- the 96.6 / 62.9 / 79.7 agreement figures, which are classifier-vs-human agreement on corpus labels and not matcher accuracy;
- the metric definitions;
- the file-constrained LLM matcher;
- the 15-minute, retry and all-or-nothing defaults;
- that local results are private and not leaderboard-eligible.

**Correction:** the official judge configuration cannot be reproduced exactly from public material. The local CLI uses one user-chosen model for both matching and classification. The portal shows "how each judge voted" (`docs/RUNNER.md`), and the README says the "judge models" are public, which implies a multi-judge official setup that is not specified. Describe our setup as "upstream prompts at `ceb0794`, judge X". Do not call it "the official judge".

## Recommended resolutions

**D1 Protocol: native host opencode, read-only tools, enforced by an overlay and proven by an adversarial mock.**
- Allowed tools: `read`, `grep`, `glob`, `list`.
- Denied: `bash`, `edit`, `write`, `patch`, `webfetch`, `websearch`, `external_directory`, and subagent/task tools.
- `steps` cap fixed before any comparison.
- Env: `OPENCODE_DISABLE_EXTERNAL_SKILLS=true` and `OPENCODE_DISABLE_CLAUDE_CODE=1`.
- The trusted preparer builds a minimised checkout per R7, with the neutral diff and PR metadata files excluded through `.git/info/exclude`. Title and body go in the prompt, which never says "benchmark".
- Label the result "private adapted protocol: read-only tools, no code execution".

Rationale: it is the only option that closes R6 with no new container networking (R21) and keeps M50 intact. The cost is less information than upstream, since there is no shell, `git log` or test execution, so record it as the main deviation. Revisit a container shell variant only if the pilot shows systematic need, and then as a separately specified arm.

**D2 Ranking exception: approve a review endpoint named `recall_strict@<budget>`.**
- Per-session paired macro grounded recall over the 215 PRs that have at least one golden TP.
- Every model-caused failure (no output, invalid after the repair turn, `steps_cap`, `deadline`) counts as 0.
- Zero-gold PRs are run and counted for false positives, and excluded from recall by definition.
- Guard: micro augmented precision is non-inferior at −5 pp (the TOST convention), with false positives per PR reported.
- Ranking statement: allowed only if the guard holds and both sessions agree in sign.
- Holm family: {recall, precision guard, high+medium recall}. Everything else is descriptive.
- No F-score.

**D3 Instrument: two judges from different families on the decisive data.**
- Primary: the upstream-named Claude Sonnet 5 at the `ceb0794` prompts.
- Secondary: one OpenAI-family judge through the same pipeline.
- Agent ids blinded.
- A direction claim needs agreement between the judges. Calibration and adjudication stay separate from that.

Calibration, pre-registered:
- judge repeatability: re-judge the 25-PR pilot findings once and report verdict flip rates;
- blinded manual audit of 60 match decisions and 60 unmatched verdicts, stratified by arm, with pre-specified tolerances (match precision ≥ 0.90, unmatched agreement ≥ 0.85, between-arm judge-error difference ≤ 5 pp);
- recall per gold producer (R12).

Our own Python scorer over `results.details.json` enforces the R9/R10 conventions and applies adjudicated overrides, and is parity-tested against upstream `results.json`. The operator sets the spending cap after the 5-PR smoke measures judge tokens.

**D4 Limits and reproducibility.**
- Deployed per-turn budgets unchanged (102400 / 81920; the resolved-budget clamp only binds above a 159,744-token prompt).
- `steps` cap, liveness monitor, and a derived wall backstop with outcome `deadline`.
- Transport errors abort.
- Seeds: a per-session overlay `options.seed`, proven by the R4 capture. If propagation fails, record "unseeded", drop the reload control, and treat sessions as reload replicates.
- Schedule per R18.

**D5 Execution.**
- Now: authorize the design audit and the CPU-only build, with mocks and no paid calls.
- Separately: the smoke plus 25-PR pilot (about 50–100 episodes), with a judge spend cap.
- Full run: only through the R16 stop rule and a box-time envelope. Schedule the box stages after M58 and the M57 certification-debt rerun (handoff leftovers 2–3).

## Minimal implementation plan (proposal only; no file is changed by this review)

### Proposed file changes

1. `docs/specs/m5X-reviewbench.md` (new; milestone id assigned on approval). Terse spec with the ACs below and the R7 preparer rules.
2. `docs/open-questions.md`. One new entry, C116, holding D1–D5 and the three exceptions from R20, plus a separate entry for the R8 instruction-file finding.
3. `docs/PLAN.md`. One queue row after the ruling.
4. `benchmark/bench/provenance.py`. The R3 overlay acceptance, plus an `opencode_resolved_options(cwd, env, model)` helper that compares resolved options to `params_for`.
5. `benchmark/reviewbench/opencode_review.json` (new, repo-tracked). The review agent definition (permission deny-list, `steps`). The per-session seed is rendered into a generated copy under `$STACK_WORKDIR`, whose sha goes in the manifest.
6. `benchmark/bench/reviewbench_corpus.py` (new). Pinned upstream sha, manifest and golden loaders, and the minimised-checkout builder with leak verification.
7. `benchmark/run_reviewbench.py` (new driver). M50/C106 entry and exit checks, manifest, resumable rows, `--pilot-seed` and `--pilot-n`, `--session`, per-episode outcome labels, transcript export through the existing probe helpers, and one candidate directory per (model, session).
8. `benchmark/bench/reviewbench_findings.py` (new). Final-message JSON extraction, schema validation, the single repair turn, and candidate-file writer (an empty file for a valid empty review, a failure record plus an empty file for model failures).
9. `benchmark/bench/reviewbench_score.py` (new). Python port of upstream `scorer.ts`, our denominator conventions, adjudication overrides, per-producer recall, and `stats.cluster_bootstrap` / `paired_delta` / `holm`.
10. `benchmark/bench/reviewbench_watch.py` (new, or an extension of `bench_watch`). A five-minute log of progress, ETA against prediction, outcomes and power.
11. `benchmark/bench/tests/test_reviewbench_*.py` (new). Failing tests first.
12. `benchmark/README.md`. One section.

No fork change. No change to the shipped `opencode_config/opencode.json`.

### Acceptance criteria (numbered, for the cold verifier)

- **AC1 Corpus pin.** Upstream sha `ceb0794…` and the hashes of `corpus/manifest.json` and `golden/` are in every manifest. The loader yields 219 PRs and 2,623 golden TPs.
- **AC2 Minimised checkout.** For every PR, the object set reachable from all refs is contained in ancestors(head) ∪ ancestors(base). No remotes, no `FETCH_HEAD`, no reflog. `git config --get-regexp url` is empty, `HEAD == head`, and the tree is clean. Tests cover a fixture repo with a planted post-head commit, a `pull/*` ref and a promisor remote. Each must be detected and refused.
- **AC3 Leakage denial (mock adversary).** Against a scripted mock server, pinned opencode with the overlay denies every attempt: bash, webfetch of a GitHub URL, a read outside the checkout, a write or edit, and a task/subagent call. No out-of-project file and no network host other than the router is reached. The resolved permission set from `opencode debug config` equals the expected policy, or the run refuses.
- **AC4 Request capture.** Against the mock, captured bodies carry the session `seed` and every deployed sampling field equal to `params_for(model, "deployed")`, with the carrier-omitted `reasoning_effort` absent. A slow-stream test shows no client-side cut before the derived backstop.
- **AC5 Provenance.** M50 at entry. C106 at exit with drift stamped and nonzero exit. The overlay sha, opencode version, env policy (`OPENCODE_DISABLE_EXTERNAL_SKILLS`, `OPENCODE_DISABLE_CLAUDE_CODE`), registry sha, `runtime.draft_kind` (`off` for selection) and attention policy are in the manifest and verified before PR two.
- **AC6 Bounds.** The progress gate is not used. Outcomes are one of {completed, steps_cap, deadline, no_output, invalid_output}. A silent/IDLE wedge is killed by PID only after verification. Transport/HTTP errors abort nonzero with no row.
- **AC7 Denominators.** Every intended PR yields a candidate file and an outcome row. The scorer refuses if any intended PR is missing. Model failures score recall 0. Zero-gold PRs are excluded from recall and kept for false positives. Zero `unclassified` labels are present.
- **AC8 Scorer parity.** On fixtures and on one real `results.details.json`, the Python port reproduces upstream `results.json` macro/micro values exactly, before our conventions are applied.
- **AC9 Sessions.** One judge run per (model, session, judge). Sessions are never pooled. Per-session seeds and PR order are identical across models, with model order counterbalanced.
- **AC10 Blinding and dual judge.** Candidate `agent`/`producer` ids are arm hashes. Both judges run on the decisive data. Per-producer recall is reported.
- **AC11 Calibration.** Repeat-judge flip rates and the blinded 60+60 audit are reported against the pre-registered tolerances. A failed tolerance blocks ranking.
- **AC12 Reporting.** For each session: `recall_strict@budget` with a cluster-bootstrap CI and MDE, the precision guard, false positives per PR, the outcome mix, compaction counts, exclusive golden-TP coverage sets, and tokens and wall per PR on a clean box. No composite.
- **AC13 Hygiene.** Every scratch item, transcript and judge artifact is under `$STACK_WORKDIR` (`.noindex` scratch). PII scrub covers the transcripts. Tests are mocked, with no network, model or paid calls. Hooks pass.
- **AC14 Smoke gates.** A 5-PR seeded-random smoke, then a same-instance repeat of the same 5 with discordance recorded. Runtime is projected from mean and max with a heavy-tail allowance. The R16 stop rule is evaluated after the pilot and before any full-run request.

## Assumptions to discharge in the design audit

- opencode's pass-through of `seed` and of the max-token field (R1, R2, R4).
- The pinned 1.18.30 default permissions, `steps`, and rule-file loading (R6, R8, R5).
- The opencode client request timeout (R4).
- The teacher lineage of `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (R12).
- The SD of per-PR recall differences and the per-PR runtime (R16, R17).
- The official judge composition (R23).
- PR dates relative to cutoffs (R15).
