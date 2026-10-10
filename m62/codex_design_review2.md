Part A assesses whether the **design** addresses each finding, not whether it is implemented. This was a read-only source and data review; I did not run live inference or fault injections.

References: `S` = [revision 2](docs/specs/m62-token-turn-gate.md); `OC` = the pinned `opencode-v2.0.20` source under `$STACK_WORKDIR/m59_research/src/`; `PB` = `$STACK_WORKDIR/polyglot-benchmark`.

| Prior finding | Status | Evidence |
|---|---|---|
| P1 — Complete usage accounting | **PARTIAL** | S:43–46 makes final server usage authoritative and refuses missing usage. However, the proposed message-ID reconciliation has no shared wire identifier; error and held-request accounting remain undefined. See P18. |
| P2 — Request-boundary enforcement | **PARTIAL** | S:39–42 introduces real admission control. That controls the next model request, but does not establish workspace quiescence. See P15. |
| P3 — Silence classification | **NOT RESOLVED** | S:51–56 replaces one unsupported inference with others: no chunks does not prove server wedge; descendant existence does not establish why the client is waiting. See P19. |
| P4 — Subagent accounting | **PARTIAL** | Denial plus counting all traffic is the right direction, but S:57 specifies the wrong permission name for this client. Concurrent leakage also breaks the single-request overshoot argument. See P17. |
| P5 — Misattributed calibration logs | **RESOLVED** | S:124–127 explicitly excludes mismatched sessions and limits replay claims. I reproduced 54 mismatches, including 36 passing rows, leaving 381 identity-matched passes. The frozen manifest remains a deliverable. |
| P6 — Matched budgets and overshoot | **PARTIAL** | S:62–77 correctly freezes campaign constants, uses `≥`, specifies precedence and acknowledges overshoot. Per-request context clamping, overrides and terminal-exit behavior remain ambiguous. See P25. |
| P7 — False strict passes | **NOT RESOLVED** | S:47–50 requires a forced-thinking-closure observation that the current stream does not expose. A mock alone cannot establish it. See P16. |
| P8 — Gameable progress | **PARTIAL** | S:79–85 fixes equal-count churn and unknown-grade resets conceptually. Failure counts lack a stable denominator, especially for panicking Go stubs; solution-hash and protected-file scope are incomplete. See P21. |
| P9 — Subprocess containment | **PARTIAL** | S:89–93 adds PID creation times and explicit container ownership. One-second ancestry sampling still misses short-lived parents and escaped descendants. See P22. |
| P10 — Memory containment | **PARTIAL** | S:94–98 correctly calls this best effort and adds aggregate/container limits. Host Python graders are not covered explicitly; client-resource exclusion still lacks causal justification. See P22. |
| P11 — Durable writes | **RESOLVED** | S:99–101 adopts whole-file replacement, checked writes/fsyncs and fault tests. Signal masking still needs a precise implementation contract, but the write strategy addresses the original finding. |
| P12 — Instance integrity and runners | **RESOLVED** | S:102–106 specifies creation time, per-item checks, exact expected IDs, refusal across identities and archive/restart behavior. These are adequate design requirements. |
| P13 — Acceptance coverage | **PARTIAL** | V1–V3 cover substantially more cases, including Go and real cleanup. Critical tests still substitute mocks for the assumptions being tested; V5 also precedes V4 despite claiming to review it. See P26. |
| P14 — Costs and scaffold identity | **PARTIAL** | S:110–114 separates scaffolds and hashes policy. The new endpoint’s effect on that hash is unspecified, and the nine-hour V4 “worst case” remains unsupported. See P23 and P27. |

**P15 — BLOCKER: holding a model request does not make the workspace quiescent.**

Foreground parallel tools are not the main problem: `OC/packages/core/src/session/runner/step.ts:101–145` starts tool fibers and joins them before completing the step. But `OC/packages/core/src/tool/plugin/shell.ts:198–263` explicitly returns immediately for background jobs; those jobs can continue writing files and later inject completion notifications. Arbitrary shell commands can also launch detached descendants.

Consequently, while request *j+1* is held, a background writer can mutate the snapshot source. Its completion can also alter subsequent conversation state. Denying subagents does not fix this.

**Change:** replace the assertion at S:40 with an enforceable execution-boundary contract. Either constrain shell execution through an owned supervisor that can establish all jobs are stopped/settled before snapshotting, or abandon the quiescence guarantee and specify weaker snapshot semantics. Test a background writer that changes files throughout an admission hold. Merely checking that file hashes happen to match twice is insufficient.

**P16 — BLOCKER: exact forced-thinking closure is not observable in the current stream.**

The serving path does emit final usage when requested:

- `OC/packages/ai/src/protocols/openai-chat.ts:816–835` requests streaming usage.
- `src/mlx-vlm/mlx_vlm/server/openai.py:2730` increments output tokens before separating thinking from visible content.
- `openai.py:2868–2876` emits those tokens in the usage chunk.

Thus **thinking-inclusive completion accounting is supported by source**.

However, `src/mlx-vlm/mlx_vlm/utils.py:2731–2821` forces the thinking closing sequence internally. `server/schemas.py:886–908` exposes neither its token count nor a forced-closure flag. Natural and forced closing tags are indistinguishable in decoded text. Furthermore, `server/openai.py:2834–2838` replaces the generation finish reason with `tool_calls` when tool calls are parsed, potentially concealing a preceding length finish.

**Change:** choose explicitly between:

- The existing conservative rule: `completion_tokens >= resolved_thinking_budget` means budget nonconvergence. Call it a **budget-threshold hit**, not proof of forced thinking closure.
- Exact detection, requiring server telemetry for effective budgets, thinking count, forced closure and the underlying generation finish reason.

The first option is considerably smaller and aligns with `benchmark/bench/convergence.py:105–117`. Define how natural `tool_calls` finishes map to agentic convergence; literal `finish_reason == "stop"` cannot be applied unchanged to every tool-producing request.

**P17 — MAJOR: the specified subagent denial targets the wrong tool.**

S:57 says “task tool permission off.” The pinned client declares:

- `OC/packages/core/src/tool/plugin/subagent.ts:17`: `name = "subagent"`.
- The permission check uses that name at lines 138–143.

A `task` deny does not implement this requirement. Counting leaked requests afterward also does not preserve quiescence or the one-request overshoot bound if parent and child generate concurrently.

**Change:** specify the exact carrier rule: action `subagent`, resource `*`, effect `deny`; test it with the real pinned client. Refuse unexpected child-session traffic before forwarding, and enforce at most one admitted generation at a time.

For the auxiliary paths: the existing carrier disables title generation and automatic compaction; `--title probe` is also supplied (`benchmark/run_opencode_probe_v2.py:352`). `OC/packages/core/src/session/compaction.ts:203–204` disables overflow-triggered compaction too when `auto:false`. Preserve and assert these settings. They substantially simplify the proxy contract.

**P18 — MAJOR: “reconcile by message ID” cannot currently be implemented as specified.**

Opencode creates its assistant message ID locally at `OC/packages/core/src/session/runner/llm.ts:208`. Its outgoing headers carry session affinity, project and client identifiers, but no assistant message ID (`session/model-request.ts:274–286`). The server independently generates `chatcmpl-<uuid>` at `server/openai.py:2673`.

There are also two unhandled cases:

- A held, never-forwarded request can leave an interrupted assistant record with no server usage.
- A recognized context-overflow response has no successful final usage chunk. “Missing usage on a forwarded request → abort” conflicts with retaining current scored `context_overflow` behavior (`benchmark/run_opencode_probe_v2.py:419–421`).

**Change:** define a request ledger with session, ordinal, admitted/forwarded/completed state, terminal outcome and export mapping. With subagents and retries prohibited, ordinal matching plus explicit cardinality checks may suffice; otherwise add an out-of-band correlation mechanism. Specify **zero tolerance for integer completion-token disagreement** after normalization, and explicit handling for rejected and never-forwarded requests.

Count final usage once. Do not deduplicate identical SSE text deltas: repeated text can be legitimate, and ordinary chunks lack unique event identities.

**P19 — MAJOR: the 900/1800-second rules still misclassify causality.**

S:53 treats a silent in-flight request as a server wedge without checking whether the worker is prefilling or otherwise BUSY. This conflicts with `AGENTS.md:48`. A long model-generated prompt can cause a long prefill; excluding that attempt automatically creates selection bias.

The other branch is equally weak:

- A live background server or language-service process does not prove the active tool is hung.
- A model-triggered in-process tool can hang without a descendant.
- A background shell can hang while the agent continues requesting generations, or exits normally. It may never satisfy “no request for 1800 s,” so V3’s promised `exec_timeout` is not guaranteed.
- A proxy-held request needs its own state; it must not be mistaken for an upstream silence.

**Change:** use explicit states—held/grading, upstream prefill, upstream decode, active foreground tool, background job, client idle—and independent worker/tool liveness evidence. Treat 900 seconds as a diagnostic trigger until a wedge is verified. Define a separate background-job lifetime/cleanup policy and retain model-caused timeouts in the denominator.

**P20 — MAJOR: the hold-time timeout contract is unproven; `noretry.js` does not supply one.**

The plugin only sets `retry:false`. It neither extends deadlines nor prevents the first request from timing out.

The native provider uses `RequestExecutor` and `FetchHttpClient` (`OC/packages/ai/src/route/executor.ts:227–252`; `packages/util/src/effect/app-node-platform.ts:11`). The explicit Bun timeout disabling in `packages/core/src/aisdk.ts:159–160` belongs to the AISDK path, not this native provider. The CLI separately disables Bun’s default five-minute timeout for its event connection (`packages/cli/src/run/run.ts:86–89`).

This establishes a **timeout risk**, not proof that this particular binary will fail at exactly five minutes. Python grading already permits 300 seconds before overhead (`benchmark/bench/opencode_common.py:357–365`).

**Change:** require a real-client delayed-response test exceeding the maximum supported hold, including startup and grading overhead. Verify one upstream attempt, no retry, correct export and no premature disconnect. Specify proxy upstream/downstream timeouts explicitly. Adding `settings.timeout:false` cannot simply be assumed effective: the native provider strips core timeout settings (`OC/packages/core/src/provider.ts:136–141`).

**P21 — MAJOR: the new-minimum rule needs a fixed test universe and complete snapshot identity.**

The Go stub baseline is a concrete counterexample. `PB/go/exercises/practice/book-store/book_store.go:4` panics. Its test suite iterates subtests (`book_store_test.go:7–15`). A panic terminates execution before the remaining cases run. Counting reported failed tests therefore gives a small baseline; a better implementation that runs all tests but fails several can appear worse. Counting both failed parents and failed subtests introduces another ambiguity.

Python summaries likewise need rules for collection errors, skips, setup failures and incomplete runs. “All tests failing” requires a known denominator.

The hash/protection scope also matters. The existing helper hashes one selected solution file (`benchmark/bench/opencode_common.py:193–221`). Go’s `cases_test.go` supplies test data but appears under `files.editor`, not `files.test`, in the corpus metadata. Checking only the selected test file misses it.

**Change:** freeze trusted test identities and compute failures as required tests not successfully completed; define parent/subtest counting and incomplete-run treatment. Use structured grader output. Hash every executable solution/configuration input and protect all test fixtures, including auxiliary case files. Missing dependencies or grader infrastructure failure must not masquerade as model test failures.

**P22 — MAJOR: H1/H2 still cannot establish their cleanup and coverage guarantees.**

A one-second tracker can miss a child that forks, changes directory and loses its parent between polls. Two subsequent scans cannot prove absence of a process that was never associated with the item. Opencode’s detached spawning is explicit at `OC/packages/core/src/shell.ts:299–305`.

Separately, the host Python snapshot grader is launched by the probe, not opencode (`benchmark/bench/opencode_common.py:357–365`). H2 covers tracked model-spawned processes and Docker graders, leaving this C138 failure path unspecified.

The client’s 16 GB threshold is also not evidence of an infrastructure cause: model-generated output can drive client memory consumption.

**Change:** establish execution ownership at process creation or narrow the cleanup claim to best effort. Explicitly include host graders and their descendants in resource tracking. Define client-resource outcomes without automatically giving model-induced exhaustion an unscored retry. Freeze Docker memory/swap limits and resource units. Add a rapid orphan/chdir test and a host-grader allocation test.

For H3, specify which threads block signals and how child signal masks are restored; naming `pthread_sigmask` alone does not define safe multithreaded acquisition.

**P23 — MAJOR: the M50 amendment must cover carrier identity, not just permission to use a proxy.**

**Yes, opencode can target a local proxy:** `OC/packages/ai/src/providers/openai-compatible.ts:27–33` accepts the configured baseURL directly. The existing hermetic probe cannot simply substitute one:

- It verifies the carrier destination as the router at `benchmark/run_opencode_probe_v2.py:893–895`.
- It hashes and checks exact carrier bytes at lines 239–245 and 264–268.
- The scaffold policy includes that carrier hash at lines 579–608.

A per-item proxy with ephemeral ports changes carrier hashes across items/runs. Without an explicit identity design, comparisons or resumes either refuse valid runs or weaken provenance incorrectly.

The discovery call is `api GET /api/config --standalone` (`benchmark/bench/provenance.py:1947–1955`), not an inference request. It should not consume item budgets or enter admission grading.

**Change:** specify the full router→proxy→carrier binding and discovery lifecycle. Separate exact runtime carrier evidence from campaign policy identity, with a narrowly defined endpoint normalization. A single run-owned listener with per-item ledger resets would remove considerable per-item port/configuration complexity.

**P24 — MAJOR: the transparency test promises the wrong equivalence.**

Byte-preserving **entity-body forwarding** is achievable. Identical direct/proxied runs from the same seed are not a sufficient or generally valid wire oracle:

- The destination/Host changes.
- Opencode sends session affinity and a session-derived `prompt_cache_key` (`OC/packages/core/src/session/model-request.ts:274–288`).
- Responses contain generated IDs/timestamps.
- Transport libraries may change header serialization and HTTP chunk boundaries.

Cache identity is consequential: the server keys sessions from those identifiers and maintains an LRU (`src/mlx-vlm/mlx_vlm/server/session_manager.py:198–292, 395–433`).

Holding also changes scheduling. Grading consumes host resources and introduces model idle time; background completion ordering can change prompts. “Hold time is wall time only” is not a demonstrated neutrality guarantee.

**Change:** test captured request bodies byte-for-byte across the proxy, preserve semantic/session headers, and enumerate allowed transport-header changes. Test response SSE bytes against fixed fixtures with arbitrary fragmentation. Separately measure controlled direct/proxy behavioral equivalence with matched cache state. Record admission wait, grading, upstream TTFT/decode and total item wall time separately.

**P25 — MAJOR: constants are plausible, but the gate’s state transitions are incomplete.**

I reproduced the stated calibration:

- 454 rows; 417 passes.
- 381 identity-matched passes; 54 mismatched logs.
- Passing output-token median/p95/max: **3,860 / 19,345 / 39,142**.
- Passing request median/p95/max: **7 / 13 / 26**.
- Passing maximum identical-call run: **2**.
- The kindergarten-garden eighth identical call occurs at **request 15, event line 46**.

Thus T=81,920, N=40 and K=8 pass the proposed retrospective screen. They do not demonstrate safety for longer, previously censored attempts.

Missing definitions include:

- Whether progress is applied before testing T/N.
- Whether the request that caused improvement is included in the reset.
- What happens when the final response crosses an item ceiling and no next admission occurs.
- Tool-call ordering/signatures under parallel execution.
- Whether all tax flags survive the primary-reason precedence.
- How dynamic context clamping interacts with “resolved budget must equal B.”

The last issue is real: `server/generation.py:520–536` clamps thinking budget according to remaining context. The recorded maximum context, 108,462, does not exercise the 159,744-token headroom boundary for a 262,144 context and 102,400 output allowance.

**Change:** add an explicit transition table covering initialization, successful completion, tool settlement, grading, next admission and normal exit. Keep campaign B separate from per-request resolved budgets; define context exhaustion as a scored outcome rather than an ad hoc override/refusal. Apply total-ceiling policy on terminal exit too.

**P26 — MAJOR: V1–V5 are not yet a falsifiable acceptance package.**

V1 mocks both endpoints around the disputed assumptions. They can demonstrate the implementation matches an invented protocol while missing real background behavior, native-client timeouts and absent server telemetry.

V2 is appropriately described as a false-positive screen, but its frozen manifest is not present in the inspected M62 artifacts despite S:152 saying rows are “listed” there.

V3’s background-shell expectation contradicts its proposed timer, and its >8 GB allocation is unnecessary for validating threshold wiring. V5 says review against V1–V4, while S:153–155 schedules V5 before V4.

**Change:** pre-register executable oracles for:

- Real pinned-client background writer, concurrent tools, subagent denial and long admission hold.
- Real serving-path small-budget closure and length-with-tool-output cases.
- Exact request/export reconciliation on normal exit, gate stop and context overflow.
- Go panic baseline, partial improvement and auxiliary-test tampering.
- Rapid orphan escape, host-grader memory and resource-monitor failure.

Use lowered watchdog thresholds for live wiring tests. Freeze replay input hashes before implementation. Either move V5 after V4 or split it into pre-live and final evidence reviews. Descriptive V4 need not require a pass-rate improvement.

**P27 — MINOR: the revised cost arithmetic is better, but nine hours is not a V4 worst case.**

At the stated 19.5 tok/s:

- No-progress generation bound: **2.626 h**.
- Total-ceiling generation bound: **6.126 h per item**.
- Three items reaching that ceiling: **18.379 h**, before prefill, tools, grading and reloads.

A new-minimum improvement can reset the no-progress counter, so V4 is not confined to one no-progress window per item. Moreover, 19.5 tok/s is an observation, not an established lower bound. The runner formula at S:106 references §6 for a per-item worst case that is not defined there.

**Change:** remove the nine-hour worst-case claim and report conditional generation arithmetic separately from pilot estimates and administrative deadlines. Keep the conservative replay, but cut unnecessary complexity: exact integer reconciliation needs no tolerance policy; a run-owned proxy needs no per-item listener lifecycle; a threshold wiring test needs no actual 8 GB allocation.

**Verdict: redesign.** Retain request admission and campaign-constant token/turn budgets, but resolve execution quiescence, observable convergence and outcome classification before implementation.