I inspected all 454 rows, their referenced event logs, the relevant probe code, and the locally available opencode 2.0.20 source. No files or processes were changed.

1. **P1 — BLOCKER: `step_finish` is not complete request accounting.**  
   The actual fields are `event.part.tokens.output` and `event.part.tool/state.input`. Output includes thinking: the serving code sends total output usage without a separate reasoning count. However, **all 381 identity-matched passing logs omit the final `step_finish`**; their exports contain the missing usage. This agrees with the explicit exception in [the classifier]($STACK_REPO/benchmark/run_opencode_probe_v2.py:427). Missing final usage reached 850 tokens in the checked corpus; that observed maximum is not a bound.

   **Change:** specify authoritative usage reconciliation on normal exit, keyed by request/message ID, before classifying completion or applying ceilings. Missing usage must never silently become zero. Validate thinking-inclusive accounting with an actual wire capture, not merely a mock containing the expected number.

2. **P2 — BLOCKER: observing a request boundary does not let the probe stop at that boundary.**  
   Opencode runs independently while the probe polls its stdout file ([spawn/orchestration]($STACK_REPO/benchmark/run_opencode_probe_v2.py:342)). In identity-matched logs, **690 finish→next-start intervals are under one second**. The current polling default is five seconds; snapshot grading can take minutes. Consequently, when the gate handles request *j*, request *j+1* may already be generating. Killing then violates G6; waiting introduces additional, unspecified overshoot. Copying the live directory can also attribute later edits to an earlier request.

   **Change:** enforce admission of the next request through a synchronous client hook or equivalent handshake. Define when snapshotting, grading and gate decisions occur relative to that admission. A passive tailer cannot guarantee “never cut a request.”

3. **P3 — BLOCKER: silence does not establish transport failure.**  
   The pinned shell tool explicitly accepts `timeout: 0`, and background commands default to no timeout ([shell schema]($STACK_WORKDIR/m59_research/src/opencode-v2.0.20/packages/core/src/tool/plugin/shell.ts:47), [execution]($STACK_WORKDIR/m59_research/src/opencode-v2.0.20/packages/core/src/tool/plugin/shell.ts:198)). `tool_use` is emitted on completion/failure, not invocation. Thus an infinite model-written command can remain silent legitimately from the client’s perspective. Likewise, the logs do not report in-flight thinking progress.

   `102400 / 8 + 600 = 13400` is arithmetically correct, but the calibration does not establish an 8 tok/s floor or bound prefill/tool time. Automatically excluding these cases contradicts [silent/BUSY handling and DNF accounting]($STACK_REPO/AGENTS.md:48), and C146 originally specified `exec_timeout`.

   **Change:** distinguish verified transport failure, ongoing server generation, model-caused tool timeout and unknown infrastructure failure. Preserve attempts and diagnostics; do not turn model-caused nontermination into an unscored retry opportunity.

4. **P4 — MAJOR: subagent compute escapes both proposed budgets.**  
   Opencode’s JSON event handler filters ordinary events to the parent session ([source]($STACK_WORKDIR/m59_research/src/opencode-v2.0.20/packages/cli/src/run/noninteractive.ts:225)). Subagents execute in child sessions. The probe currently only marks their presence as an incomplete web audit ([audit]($STACK_REPO/benchmark/run_opencode_probe_v2.py:521)); that does not account for their generation.

   **Change:** explicitly deny subagents under tg1, or aggregate authoritative usage and request counts across every descendant session. Test the chosen policy with a real child-session known positive.

5. **P5 — MAJOR: the calibration corpus has misattributed transcripts.**  
   **54/454 rows reference logs with a different `sessionID`: 36 passing and 18 failing rows.** The affected files include both `Qwen3.8-27B-mlx-uniform-4bit` `m59.s1.window558` legs and ten original `m59.s2` stalls.

   Using the rows’ own recorded metrics, passing output tokens are **median 3,860 / nearest-rank p95 19,345 / max 39,142**; requests are **7 / 13 / 26**. The spec’s median 3,833 is reproducible from the currently referenced exports, including replacements. I reproduced 36,947 tokens and 14 requests only as a **write/edit-tool proxy**, not verified no-progress intervals.

   The kindergarten-garden row records **359 consecutive calls, 358 repetitions**. Its eighth identical call occurs at **request 15**, event line 46—not within ten requests from item start ([row]($STACK_REPO/benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/opencode_v2_go.m61.s2.jsonl:16)).

   **Change:** freeze an identity-checked, hashed replay manifest; recover originals or mark them unavailable. State percentile and write-detection methods. Define the loop criterion relative to loop onset, or correct its expected request index.

6. **P6 — MAJOR: the budget is neither universally matched nor a hard ceiling as written.**  
   `resolved_thinking_budget(params_for(...))` returns `None`: the helper also requires context limit, max tokens and prompt tokens ([implementation]($STACK_REPO/benchmark/bench/convergence.py:42)). Moreover, registry budgets are not identical across all models: `gemma-4-31B-it-qat-6bit` has 16,384 thinking tokens and `gemma-4-26B-A4B-it-OptiQ-4bit` has 32,768 ([registry]($STACK_REPO/main_models.yaml:72)). The two current Qwen picks do match at 81,920, before context clamping.

   Even with perfect boundary control, strict `>` permits **41 no-progress requests and 151 total requests**. Whole-request overshoot permits approximately **266,240 no-progress tokens or 430,080 total tokens**. Different request sizes therefore receive different realized allowances.

   **Change:** freeze campaign-level budgets, verify comparable arms match, and separate them from per-request resolved budgets. Explicitly choose exact caps versus soft thresholds with bounded whole-request overshoot; register comparison operators and precedence. Equal output-token allowances also should not be described as equal compute.

7. **P7 — MAJOR: full-budget requests can become false “strict” passes.**  
   The current classifier examines process exit, errors and gate termination; it does not classify server thinking-budget hits or length finishes ([classifier]($STACK_REPO/benchmark/run_opencode_probe_v2.py:414)). The report’s strict score accepts any passing, completed row without `nonconv_kind` ([report]($STACK_REPO/benchmark/results/m61_rr/rr_report.py:24)).

   M62 makes this newly consequential: a request can exhaust its thinking allowance, be forcibly closed by the server, edit successfully and exit before either item threshold fires.

   **Change:** record per-request usage, resolved budget and termination information; propagate budget-hit/max-token flags into session convergence and strict scoring. Add a known positive that passes tests after forced thinking-budget closure.

8. **P8 — MAJOR: “progress” rewards churn and grading failure.**  
   [The snapshot helper]($STACK_REPO/benchmark/bench/opencode_common.py:193) maps grades to 0/1, returns `None` on grader exceptions, and calls the raw grader without `_grade_result`’s tamper check. [The policy]($STACK_REPO/benchmark/bench/progress_gate.py:99) treats a changed file with no observed failure increase as progress. Therefore comment edits, alternating wrong solutions, and changed-but-ungradeable files reset counters.

   The ceilings prevent unlimited *counted* requests; they do not make this meaningful progress. Churning models can consume the total ceiling while equally unsuccessful non-editing models stop earlier.

   **Change:** at minimum, unknown grades must not establish progress, repeated solution hashes must not repeatedly reset it, and protected-test integrity must be checked. Either obtain actual failure counts or explicitly describe this as an edit-activity heuristic and test its intended treatment of churn.

9. **P9 — MAJOR: H1 does not contain the actual subprocess topology.**  
   Opencode already spawns shells with `detached: true` on macOS ([source]($STACK_WORKDIR/m59_research/src/opencode-v2.0.20/packages/core/src/shell.ts:299)). Such shells are outside the proposed opencode process group. A detached child that changes cwd and has no scratch path in argv escapes the fallback sweep.

   Additionally, non-Python grading uses `docker run --rm` ([grader]($STACK_REPO/benchmark/bench/opencode_common.py:399)); killing the host Docker CLI/group is not a container-lifecycle policy.

   **Change:** track descendants and their groups while ancestry exists, retaining PID creation times; explicitly own and stop grader containers by ID. Repeatedly verify cleanup before deleting scratch. Specify how inaccessible processes, detached descendants and repeated termination signals are handled.

10. **P10 — MAJOR: H2 is a watchdog, not an 8 GB memory cap.**  
    A one-second poll cannot prevent an allocation burst between polls. Multiple children below 8 GB can exhaust the shared box, and snapshot graders run concurrently with model tools. Host psutil does not measure individual processes inside the grading VM.

    “Opencode above 16 GB means client bug” is also unsupported: retained model-generated output can drive client memory. A killed snapshot grader cannot satisfy “the model sees its command fail”—that grader is outside the model’s tool session.

    **Change:** specify aggregate execution-memory limits and separate host/container coverage; describe polling as best effort. Define tool-kill, grader-kill and client-memory outcomes separately. Test multi-process allocation, rapid bursts, monitor failure and grader OOM using lowered test thresholds.

11. **P11 — MINOR: H3 improves durability but does not promise transactional row writes.**  
    `os.write` returns the bytes actually written; the caller must handle short writes. `O_APPEND` plus `fsync` does not make arbitrary-length rows crash-atomic. The existing [loader]($STACK_REPO/benchmark/bench/opencode_common.py:484) correctly refuses torn tails. See [Python’s `os.write` contract](https://docs.python.org/3/library/os.html#os.write).

    **Change:** either document fail-closed append semantics and check every write/fsync result, or use whole-file replacement for these small leg files. Fault-test interruption before/after write, fsync and rename. H4 also needs deferred interrupts during resource acquisition and cleanup; merely registering an initially empty child handle does not close the spawn race.

12. **P12 — MAJOR: H5 needs continuous instance validation and runner changes.**  
    [Current worker identity]($STACK_REPO/benchmark/run_opencode_probe_v2.py:648) contains PID and model path, not load time. A resume-only comparison misses reloads during an uninterrupted leg. The actual [chain runner]($STACK_WORKDIR/m59/run_m59.py:206) skips files by row count and imposes a six-hour leg timeout.

    **Change:** define the authoritative load identity and check it before/after each item and at exit. Missing identity must refuse; drift must invalidate affected evidence. Apply exact expected-ID validation and archive-on-new-instance behavior in the runner, not only the probe. Update its timeout and termination behavior for tg1.

13. **P13 — MAJOR: V1–V5 do not validate the hardest guarantees.**  
    V2 can provide a useful conservative check on the **381 identity-matched passing traces**: even charging every request as no progress, their totals remain below T/N and their identical-call runs remain below K. But it cannot reconstruct snapshot grades, missing streams or live scheduling races. Calibration and validation also use the same successful traces.

    **Change:** add deterministic integration cases for split JSON/UTF-8 lines, missing final usage, duplicate events, immediate next-request admission, slow grading, unknown grades, alternating edits, retries, context overflow, subagents, and termination during acquisition/cleanup. The current [_events parser]($STACK_REPO/benchmark/run_opencode_probe_v2.py:382) silently drops malformed lines and must not be reused as a live tailer. Add real macOS cleanup and Go/container smoke coverage; a Python-only smoke cannot establish H1/H2.

14. **P14 — MAJOR: cost bounds and scaffold compatibility remain underspecified.**  
    At the spec’s own 20 tok/s assumption, `T + max_tokens` costs **3.70 hours**, not 1–3; three such items cost **11.09 hours before tools, grading or reloads**, exceeding V4’s claimed ten-hour worst case. The total ceiling plus overshoot permits **5.97 generation-hours per item**. Unbounded tool execution means there is no demonstrated overall worst case.

    The new scaffold ID is correct, but merely recording `gate_policy` is insufficient: [policy hashing]($STACK_REPO/benchmark/run_opencode_probe_v2.py:574) and [comparison]($STACK_REPO/benchmark/bench/compare.py:319) must enforce its effective settings. Running a future candidate under the old ID while applying new memory/tool behavior would not recreate M61.

    **Change:** replace worst-case claims with explicit conditional bounds and pilot-derived estimates. Include gate, resource and timeout policies in resume/comparison identity. Define an exact legacy execution mode or remove the proposed legacy-scaffold fallback.

**Verdict: redesign.** Keep the token/turn direction, but resolve request admission, complete usage accounting and silence classification before implementation. The current passive-log design cannot deliver its central guarantees.