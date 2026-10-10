Revision 3 is materially better, but it is not implementation-ready. The remaining blockers concern observable states, passive overshoot, terminal accounting, and cleanup guarantees. They can be addressed while retaining every operator ruling.

This was read-only. I inspected source and stored rows/events; I did not run inference, graders, or fault injections. The worker at port 8091 was unavailable, so `/metrics` authentication was verified from code, not a live response.

References below: **S** = [revision 3]($STACK_REPO/docs/specs/m62-token-turn-gate.md); **OC** = `$STACK_WORKDIR/m59_research/src/opencode-v2.0.20/packages`; **PB** = `$STACK_WORKDIR/polyglot-benchmark`.

**Part A — prior findings**

“RESOLVED” assesses the specification, not an implementation.

| Finding | Status | Evidence |
|---|---|---|
| P1 — Complete usage accounting | PARTIAL | S:35–39 adds final-export reconciliation. Terminal/error/interrupted-message accounting still needs explicit states; P32 below. |
| P2 — Request-boundary enforcement | PARTIAL | S:28–32 explicitly permits interrupting the next request, resolving the obsolete no-interruption requirement. The one-request overshoot claim remains false; P31. |
| P3 — Silence classification | NOT RESOLVED | S:98–101 still infers causality from event silence and descendant existence. Its event states do not correspond to HTTP states; P28. |
| P4 — Subagent accounting | RESOLVED | S:95–97, 144–145 requires the correct `subagent` denial and a real-client test. |
| P5 — Misattributed calibration logs | PARTIAL | S:147–150 excludes 54 mismatches, which I reproduced. The 381 passes include seven excluded `go/counter` observations; the replay manifest is absent. P38. |
| P6 — Matched budgets/overshoot | PARTIAL | Constants, carrier checks, `≥`, and precedence are explicit at S:53–69. Context reconstruction, overshoot and terminal handling remain defective; P29/P31/P32. |
| P7 — False strict passes | PARTIAL | S:40–45 adds the appropriate conservative threshold rule, but computes its input context incorrectly; P29. |
| P8 — Gameable progress | PARTIAL | S:66–85 fixes equal-count churn and introduces a fixed denominator. Snapshot identity and final tamper enforcement remain incomplete; P33/P34. |
| P9 — Process containment | NOT RESOLVED | S:102–107 retains one-second ancestry sampling, which cannot establish complete ownership; P35. |
| P10 — Memory containment | PARTIAL | S:110–113 adds aggregate limits, Docker limits and scored client exhaustion. Host Python graders remain outside the stated memory policy; P36. |
| P11 — Durable writes/interruption safety | PARTIAL | S:114–115 resolves the write strategy. Acquisition and repeated-interrupt cleanup races remain unspecified; P35. |
| P12 — Instance integrity/runners | RESOLVED | S:116–118 and 172–173 specify creation time, per-item checks, append refusal, exact IDs and fresh-instance leg restart. |
| P13 — Acceptance coverage | PARTIAL | S:138–160 improves coverage substantially, but omits critical parser, scheduling and terminal-state oracles; P38. |
| P14 — Cost/scaffold compatibility | PARTIAL | S:122–127 correctly separates legacy behavior and hashes policy. S:164 still relies on an unsupported overshoot bound; P31. |
| P15 — Workspace quiescence | PARTIAL | Background-parameter rejection and copy checks help, but neither prevents detached writers nor attributes a snapshot to request j; P33/P35. |
| P16 — Forced-closure observability | RESOLVED | S:43–45 explicitly chooses a conservative completion-token threshold rather than claiming exact forced-closure detection. |
| P17 — Wrong subagent permission | RESOLVED | `subagent` is correct: OC `core/src/tool/plugin/subagent.ts:17,138–143`. Title/compaction assertions are included. |
| P18 — Reconciliation identifiers/states | PARTIAL | The proxy/server-ID problem is N/A. Live events and exports share client message IDs, but interrupted/context-overflow reconciliation remains incomplete; P32. |
| P19 — Silence causality | NOT RESOLVED | The longer timeout does not repair the state or causal inference; P28. |
| P20 — Proxy hold-time timeout | N/A | No admission hold or proxy remains. A real-client long-response test is still useful for the retained long-request contract. |
| P21 — Fixed test universe/hash scope | PARTIAL | S:72–85 supplies the right denominator concept. Grading paths, trusted artifacts and protection scope need completion; P33/P34. |
| P22 — Cleanup/resource coverage | PARTIAL | Scored client-resource exhaustion is fixed. Escaped descendants and host-grader memory remain unresolved; P35/P36. |
| P23 — Proxy/M50 carrier identity | N/A | Proxy-specific. The new plugin still requires a narrowly scoped provenance allowlist extension; P37. |
| P24 — Proxy transparency equivalence | N/A | Proxy-specific. |
| P25 — Gate transitions | PARTIAL | S:64–68 resolves evaluation order and reset-after-j. Terminal evaluation, parallel-tool ordering and complete flags remain unspecified; P30/P32. |
| P26 — Falsifiable acceptance package | PARTIAL | Real-client plugin tests, lowered thresholds and split V5 reviews are improvements. Remaining omissions are in P38. |
| P27 — Cost claims | PARTIAL | V4 is correctly descriptive and no longer has a worst-case promise. The passive generation bound is still incorrect; P31. |

**New findings**

1. **P28 — BLOCKER: the silence state machine does not describe this client.**

   A successful continuing step does settle its local tool fibers before publishing its end: OC `core/src/session/runner/step.ts:138–145,199–250`. Thus successful request j’s `step_finish` precedes the next step’s start, with its foreground tools settled. My scan found no second start while the preceding start remained unfinished in the 400 identity-matched row traces.

   However:

   - `step_start` is generated by response activity, not HTTP dispatch: OC `ai/src/protocols/openai-chat.ts:1099–1113,1164`; `core/src/session/runner/publish-llm-event.ts:400–427`. A request awaiting first output can look “idle.”
   - `step_finish` waits for tools. A hung tool looks like an “in-flight request,” so it reaches the roughly 3.86-hour `TransportAbort` branch rather than the 900-second `exec_timeout` branch.
   - A permission decline can produce `Step.Failed` and interruption, without `step_finish`: `step.ts:199–217,239–250,264–270`. An ordinary configured denial is a different, recoverable tool-error path.
   - An unrelated surviving descendant does not prove that the client is waiting on that process.

   **Change:** define states as observations—awaiting first output, streaming/unfinished step, tools unsettled, terminal—not as inferred HTTP states. Cross-check worker activity and tool status before classifying silence. Treat R_max as a diagnostic/administrative deadline, not proof of transport failure; specify retention of model-caused nontermination in the scored denominator.

   The worker does expose **`summary.in_flight`**, not a top-level field: `src/mlx-vlm/mlx_vlm/server/generation.py:718–727`. `/metrics` requires authentication only when `MLX_VLM_SERVER_API_KEY` is set: `server/app.py:72–85,1211–1217`. Require this read-only capability during preflight; do not discover its absence after killing an item.

2. **P29 — MAJOR: the resolved-budget formula uses the wrong prompt length.**

   Opencode’s `tokens.input` means **non-cached input for this request**, not a reliable additive context increment. Its provider subtracts cache reads/writes from `prompt_tokens`: OC `ai/src/protocols/openai-chat.ts:892–918`; `core/src/session/usage.ts:11–18`.

   The recoverable prompt length is:

   ```text
   prompt_j = tokens.input_j + tokens.cache.read_j + tokens.cache.write_j
   ```

   This is a measured discrepancy. For `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `opencode_v2_go.m59.s1.jsonl:1`, request 2’s event reports input **1,112**, cache read **3,329**: prompt **4,441**, whereas the proposed sum gives **4,442**. Across the identity-matched traces, 2,928 of 3,328 completed-request readings differ. The 482-request alphametics trace reaches a discrepancy of 481 tokens.

   `convergence.py:65–68` otherwise mirrors the clamp for accepted requests. Two qualifications remain: the server uses `get_configured_context_limit()`, whereas health’s effective limit also considers native context; and the server can reject insufficient headroom before generation (`server/generation.py:477–536`; `server/app.py:140–146`).

   **Change:** reconstruct each prompt independently from its token breakdown; validate those fields. Assert that the selected health/configuration limit matches the clamp’s actual limit. Handle context rejection separately from missing successful-request usage. Test cache hits, cache misses and clamped requests.

3. **P30 — MAJOR: “calls in order” selects two different K detectors.**

   S:65 references `_tool_calls`, which traverses export order. Live `tool_use` events are emitted on completion/error, so concurrent tools can appear in a different order.

   I found differing orders in **439 of 570 multi-tool requests** across identity-matched row traces. For example, `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/opencode_v2_go.m59.s2.stall48k.jsonl:1`, assistant `msg_11a63999e001HHIXOfQV3kQ06P`, has the two tool IDs reversed between its export and event log. Source: OC `cli/src/run/noninteractive.ts:421,468`; `benchmark/bench/opencode_common.py:271–283`.

   **Change:** explicitly choose completion-event order for the passive detector, or obtain invocation ordering through an identified observable. Use that same order in replay and reported loop metrics. Specify whether tool-free requests preserve the current run. Add a parallel-call permutation test.

   The specific kindergarten-garden claim is correct: the eighth identical call occurs at **request 15, event line 46**, in `Qwen3.8-27B-mlx-uniform-4bit/opencode_v2_go.m61.s2.jsonl:16`.

4. **P31 — BLOCKER: passive overshoot is not bounded by one request.**

   S:69 and S:164 are unsupported for two independent reasons:

   - Request j can itself cross a token threshold by almost one whole request; request j+1 is additional work.
   - While the probe copies and grades, j+1 can finish and further requests can run. Recording decision lag does not bound this backlog.

   Even under an idealized assumption of exactly one additional request, the conservative token arithmetic is approximately `T + 2 × max_tokens`, not `T + max_tokens`. At 19.5 tok/s that is **4.08 generation-hours**; the analogous total-ceiling calculation is **7.59 hours**. These still exclude tools/prefill and are not bounds on the actual asynchronous implementation.

   **Change:** retain passive operation, but remove the one-request and derived wall-time guarantees. Record the first threshold-crossing request, latest completed request at action time, decision backlog, and actual known/unknown post-threshold usage. Keep event ingestion and watchdogs responsive during grading. Once a stop is established, later progress or process exit must not erase it.

   K and total ceilings do not depend on grading: check them before launching an unnecessary grade while preserving the specified reason precedence.

5. **P32 — MAJOR: terminal exit and reconciliation need a complete transition contract.**

   S:33 says no decision is made at process exit. That permits an otherwise passing item to cross the total ceiling—or complete its eighth repeated call—on its final request and escape those checks. It also leaves a race between pending decisions and process termination.

   The final-event exception is real: all **381 identity-matched passing traces omit final `step_finish`**. Export reconciliation is therefore essential, not exceptional.

   Specify these separately:

   - Normal final request: reconcile and charge once.
   - Gate/resource kill: reconcile every completed request, including those completed during decision lag; identify unfinished messages explicitly.
   - Context overflow: retain the recognized scored outcome without demanding nonexistent successful usage.
   - Permission interruption, malformed stream, retry and unexpected client exit: explicit classification.
   - Multiple nonconvergence conditions: preserve all applicable flags, with a separately specified primary reason.

   **Change:** apply terminal accounting and applicable thresholds after draining events and reconciling export. Match by message ID—the inspected native export has `messages[].id`, matching `part.messageID`; do not silently fall back to ordinal on an ID discrepancy. Validate nonnegative integers, excluding booleans. Native export normalization currently drops IDs (`run_opencode_probe_v2.py:455–476`), so reconciliation must precede that normalization.

6. **P33 — MAJOR: hashing “all files” includes the harness’s own changing logs and does not establish a request-j snapshot.**

   The current probe writes `.opencode_probe_events.jsonl` and `.opencode_probe_stderr.txt` inside the exercise tree (`run_opencode_probe_v2.py:340–359`). S:46–47,85 excludes only `.git/`. Consequently, event traffic itself changes the tree hash, triggers grading, and can defeat copy consistency checks. Python caches and grader products introduce additional irrelevant changes.

   Before/after source hashes also do not verify that the copied files equal either source manifest. A later request can edit files before snapshot capture, so the resulting grade cannot be attributed to request j.

   **Change:** move harness artifacts outside the exercise tree; define the exact execution-input manifest and generated-artifact exclusions. Compare the copied manifest with both source manifests and specify symlink/non-regular-file handling. Describe accepted snapshots as consistency-checked observations, not atomic request-boundary states. Record which event boundary and completed-request count surrounded capture; define how later edits affect progress credit.

7. **P34 — MAJOR: the test-universe approach is suitable, but its trusted grading boundary is incomplete.**

   Static corpus inspection supports the basic approach: all 44 Python/Go items represented in these rows have one solution file and one existing `files.example` reference. Excluding `go/counter` leaves 43 eligible items. Go book-store’s panic-prone stub and subtests demonstrate why reference-derived leaves are preferable to counting reported failures.

   The implementation contract still needs:

   - An explicit example→solution mapping and removal of reference copies before model spawn. The model’s TMPDIR path is exposed in its prompt (`run_opencode_probe_v2.py:105–109`); “a run-temp dir the model never sees” is not an isolation mechanism.
   - Python grading against the same official test target, with a fixed pytest root/configuration; tuple IDs rather than ambiguous string concatenation.
   - Go IDs including package and full subtest name; leaves determined from the reference tree. Panic/build failure must preserve only genuinely reported passing leaves.
   - Docker bind paths expressed as `/work` inside the container; structured stdout/report collection and infrastructure-error classification independent of the existing 600-character tail.
   - A rule for new grader-affecting files. Protecting only existing files does not catch a new `conftest.py`, pytest configuration, or Go `TestMain` that suppresses official execution.

   Protecting Go `cases_test.go`, `interface.go`, `common.go` and `go.mod` is reasonable for this corpus; helper solution files and model-authored diagnostic tests need an explicit allowed policy.

   **Change:** specify trusted grader inputs and reject additions that alter official test discovery/execution. Resolve S:83–84’s ambiguity: `_grade_result` currently forces `passed=False` for tampering of one selected test (`opencode_common.py:456–471`). Define exactly how the expanded set affects `passed`, `test_modified` and strict eligibility. Merely setting a new flag is insufficient.

8. **P35 — MAJOR: H1 cannot prove zero surviving descendants, and interruption safety regressed out of the contract.**

   Opencode explicitly detaches shells on macOS: OC `core/src/shell.ts:299–306`. A child can fork, detach, change cwd and lose its parent between one-second scans. It then matches neither ancestry, recorded group/session nor scratch cwd. Two clean scans cannot establish that it never existed.

   Rejecting the shell’s `background` parameter does not prevent a foreground shell command from launching such descendants. Creation-time checks prevent killing a reused PID; they do not solve discovery.

   **Change:** either establish ownership at process creation through an explicitly specified mechanism, or label H1 best effort and limit its guarantee to tracked processes. Preserve diagnostics and refuse progression when cleanup is uncertain. Add the rapid fork/detach/chdir case, not just a long-lived detached shell.

   Also restore an acquisition/cleanup contract: register ownership before resources become live, defer repeated termination through cleanup, and handle normal exit, timeout, exception and interrupted acquisition consistently. Named Docker cleanup must cover every grader invocation, including startup races and final/reference grades.

9. **P36 — MAJOR: H2 still leaves the host Python grader able to recreate C138.**

   H1 tracks grader descendants, but H2 applies its 8/16 GB thresholds only to “model-spawned” processes and opencode. The probe-spawned Python grader executes the same model-written code and currently runs directly on the host (`opencode_common.py:357–363`). Tracking a process does not impose a memory policy.

   **Change:** explicitly include Python graders and descendants in per-process and aggregate watchdog accounting; define their killed-grade outcome and diagnostic flag. Include simultaneous tool/grader pressure in the aggregate. Specify bytes/GiB, Docker swap behavior and whether aggregate excess is enforced until usage drops below threshold. Test host-grader allocation, several individually small children, monitor death and container OOM using lowered thresholds.

   The best-effort wording and scored `client_resource` outcome are appropriate.

10. **P37 — MAJOR: provenance records policy, but does not yet prevent another overwritten-evidence incident.**

    Scaffold separation and the existing comparison guard are sound (`bench/compare.py:319–325`). However, regular transcript destinations still derive from output stem and item; the probe overwrites them (`run_opencode_probe_v2.py:1122–1127`). Archiving an incomplete rows file alone does not preserve its evidence.

    New implementation modules also need inclusion in code identity: `_identity` currently hashes a fixed list containing `progress_gate.py`, not the proposed gate/structured-grader modules (`run_opencode_probe_v2.py:591–600`).

    **Change:** make tg1 event/export destinations immutable per run/session/item, store their hashes, and archive the complete evidence bundle. Extend code identity and freeze the universe/protected-manifest/grader identity. Extend `opencode_v2_env_check`’s exact directory allowlist only for tg1; it presently accepts exactly the carrier and `noretry.js` (`provenance.py:1889–1910`).

    H3 whole-file replacement and H4 worker identity are otherwise adequate design choices. Keep worker identity as a within-leg consistency check, not a requirement that distinct independent sessions share a PID.

11. **P38 — MAJOR: V1–V5 need executable oracles for the disputed assumptions.**

    The current package should add:

    - Fragmented UTF-8/JSON, duplicates, malformed complete lines and terminal event draining. The existing parser silently discards malformed lines (`run_opencode_probe_v2.py:382–391`).
    - Slow grading while several additional requests complete; process exit during grading; final-request threshold crossings.
    - First-output delay, unfinished tools after generation, permission denial versus decline, and context overflow.
    - Correct cached-token reconstruction and exact-boundary clamping.
    - Rapid orphan escape, host-grader exhaustion, cleanup interruption and cancellation observed through `summary.in_flight`.
    - Reference-universe preflight across all 43 eligible items, with universe and protected-input hashes frozen before model runs.

    For V2, distinguish **381 historical identity-matched passes** from **374 valid passing observations** after C145. Keep the seven excluded cases only as labelled parser fixtures. `benchmark/m62/replay_manifest.json` does not yet exist; freeze it before implementation. I reproduced the passing maxima of 39,142 output tokens and 26 requests, but this is a retrospective screen, not validation of uncensored long attempts.

    The requested plugin mechanism is source-supported: `plugins/*.js` discovery exists; the hook sees tool name **`shell`**, while **`opencode.tool.shell` is the plugin ID**. Sources: OC `core/src/plugin/source-directory.ts:7–24`; `core/src/tool.ts:103–110`; `core/src/tool/plugin/shell.ts:22,103,188–198`. Promise-hook rejection takes a defect path (`plugin/src/promise/adapter.ts:504–505`), which the runner converts into failed-tool feedback (`runner/step.ts:208–216,303–310`). Keep the real-client oracle proving rejection, model-visible bound text, continuation, and exact rejection counting. Code Mode `execute` is already denied by the inherited web carrier (`configgen/emitters/opencode.py:99–103`); assert that remains true.

    V4’s descriptive role and the V5a/V5b split are appropriate. They do not compensate for missing deterministic safety/accounting tests.

12. **P39 — MINOR: several simplifications remove ambiguity without weakening the intended guarantees.**

    **Change:** remove ordinal fallback when message IDs exist; remove the unsupported one-request overshoot promise and derived cost bound; skip grading when K or a total ceiling already mandates stopping; use one explicitly ordered call stream for both replay and live K; keep reference solutions only during preflight.

    Preserve the ruled constants, single pass, conservative budget-hit rule, legacy isolation, atomic replacement and descriptive V4. No proxy or two-stage cap is needed to make these corrections.

**Verdict: redesign.** Revise the observable-state, terminal-accounting and containment contracts before implementation; retain the ruled passive architecture and constants.