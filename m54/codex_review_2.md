**FAIL — M54 at `95680a7` is not ready for a live pilot.** Remaining defects can mix incompatible rows, alter scoring denominators, misclassify infrastructure failures, and hang cleanup.

“NOT” below includes partial fixes. References are to the reviewed commit.

| Claim | Status | Evidence |
|---|---|---|
| P7 resume identity | **NOT** | [run_agentbench_os.py:212]($STACK_REPO/benchmark/bench/run_agentbench_os.py:212): config hash, effective sampling, predictor/context and scaffold identity remain unchecked. Missing manifests/identity keys are accepted. Drift-marker rejection and exceptional-exit stamping were added. |
| P8 blocking write outside deadline | **CONFIRMED-FIXED** | [agentbench_adapter.py:634]($STACK_REPO/benchmark/bench/agentbench_adapter.py:634): deadline now covers writing. A different write/read deadlock remains—P22 below. |
| P9 infrastructure scored as model failure | **NOT** | [agentbench_adapter.py:773]($STACK_REPO/benchmark/bench/agentbench_adapter.py:773): handshake validation is fixed, but grading’s infrastructure classifier fails in both directions. |
| P10 exclusions completeness/scripts | **CONFIRMED-FIXED** | [agentbench_adapter.py:238]($STACK_REPO/benchmark/bench/agentbench_adapter.py:238): script hash and per-ID disposition coverage checked; match exemption restored. AC2 now documents rule v2. |
| P11 strict score/convergence evidence | **NOT** | [run_agentbench_os.py:297]($STACK_REPO/benchmark/bench/run_agentbench_os.py:297), [agentbench_adapter.py:1138]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1138): strict score exists and missing completion usage no longer certifies convergence, but missing prompt usage still can. Missing telemetry also penalizes strict accuracy. |
| P12 unbounded output memory | **CONFIRMED-FIXED** | [agentbench_adapter.py:570]($STACK_REPO/benchmark/bench/agentbench_adapter.py:570), `:704`: queue and retained buffer are bounded per shell. Their interaction introduces P22/P28. |
| P13 complete final JSON without newline | **CONFIRMED-FIXED** | [run_agentbench_os.py:117]($STACK_REPO/benchmark/bench/run_agentbench_os.py:117): valid JSON is preserved and newline repaired. |
| P14 inherited timeout ceiling | **NOT** | [run_agentbench_os.py:407]($STACK_REPO/benchmark/bench/run_agentbench_os.py:407): ceiling removed and derivation recorded, but sizing still uses thinking budget rather than maximum generation and inadequately filtered rate evidence. |
| P15 exit 137/invalid UTF-8 | **CONFIRMED-FIXED** | [agentbench_adapter.py:672]($STACK_REPO/benchmark/bench/agentbench_adapter.py:672), `:714`: exit 137 is independent of timeout; invalid UTF-8 gets upstream’s message. Compaction introduces a separate valid-UTF-8 regression. |
| P16 verified cleanup | **NOT** | [agentbench_adapter.py:434]($STACK_REPO/benchmark/bench/agentbench_adapter.py:434): verification ignores `docker ps` failure status. Prepare/startup cleanup remains unchecked. |
| P17 pilot/limit bias | **NOT** | [run_agentbench_os.py:557]($STACK_REPO/benchmark/bench/run_agentbench_os.py:557): biased flag combination refused, but `:568–570` still discards sampled execution order. |
| P18 malformed HTTP-200 responses | **NOT** | [client.py:74]($STACK_REPO/benchmark/bench/client.py:74): missing choices/message rejected, but an empty message with no finish reason or usage still becomes a scored failure. |
| P19 path confinement | **NOT** | [run_agentbench_os.py:755]($STACK_REPO/benchmark/bench/run_agentbench_os.py:755): rows/transcript directory checked; prepare’s corpus-sibling artifact and watcher output remain unchecked. |

The substantive remaining and new findings, ranked by severity:

**P21 — HIGH: Resume still mixes serving identities.**  
[run_agentbench_os.py:184]($STACK_REPO/benchmark/bench/run_agentbench_os.py:184), `:212–237`, `:605–639`.

I reproduced acceptance of the same registry path with a different hash and router PID. An empty runtime identity also passes. Changing temperature, predictor state or context cap while retaining the path can therefore append incompatible evidence and replace the manifest describing earlier rows. Segment entries preserve only timestamp, PID and row count.

**Minimal fix:** require a complete immutable identity—including served-file hash, effective parameters, context/predictor and scaffold—and reject existing rows without matching provenance. Preserve each segment’s full provenance.

**P22 — HIGH: Bounded reader queue plus blocking writer creates a new deadlock; cleanup can hang indefinitely.**  
[agentbench_adapter.py:586]($STACK_REPO/benchmark/bench/agentbench_adapter.py:586), `:600–647`, `:738–750`.

Real local Bash reproduction:

- `head -c 20971520 /dev/zero`: completed in **0.034 s**.
- Identical command followed by a **300 KiB comment**: timed out after **1.007 s**.

The writer waits for the complete script to enter stdin before `run()` drains the output queue. Bash blocks emitting output; the queue fills; the writer cannot finish. Subsequently, `close()` blocked at its unbounded stdin write, requiring interruption of my test process. In production this prevents reaching container removal.

**Minimal fix:** service reads and partial writes concurrently against one deadline. Make shutdown bounded even when descendants retain pipe descriptors; stop/join reader and writer threads.

**P23 — HIGH: Grading still changes the denominator according to infrastructure symptoms and model actions.**  
[agentbench_adapter.py:769]($STACK_REPO/benchmark/bench/agentbench_adapter.py:769), `:805–810`, `:1282–1285`; [run_agentbench_os.py:284]($STACK_REPO/benchmark/bench/run_agentbench_os.py:284).

End-to-end mocked reproductions:

- Checker exit **127** becomes `setup_error=True` and disappears from accuracy.
- Docker exit **1**, stderr “Error response from daemon: container abc is not running”, becomes ordinary `failed_tests`.

A model damaging a checker dependency—or making checking hang—can consequently have its failure excluded. Conversely, a daemon/container failure can count against the model. Even correctly classified transient infrastructure errors leave independently computed model accuracies using different task sets.

**Minimal fix:** distinguish Docker execution failure from the checker’s exit status using explicit execution-status evidence. Preserve model-caused checker failures in the denominator. Require matched valid task coverage before comparing arms; recover genuine infrastructure failures before ranking.

**P24 — HIGH: Server telemetry defects remain score-affecting.**  
[client.py:78]($STACK_REPO/benchmark/bench/client.py:78); [agentbench_adapter.py:1138]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1138).

`{"choices":[{"message":{}}]}` produced an eight-turn, scored `no_submit` row in my mocked end-to-end test.

Separately:

- Missing completion usage forces `acc_strict` failure despite potentially correct model behavior.
- Missing prompt usage falls back to the declared budget and can incorrectly certify convergence near the context limit.

**Minimal fix:** validate required envelope and telemetry fields at the client boundary; abort/quarantine uninterpretable responses rather than assigning model scores. Resolve convergence only with adequate prompt/budget evidence.

**P25 — HIGH: The watcher cannot distinguish “healthy” from “not looking,” or busy from idle.**  
[agentbench_watch.py:54]($STACK_REPO/benchmark/bench/agentbench_watch.py:54), `:95–132`, `:249–258`, `:283–295`.

Confirmed behaviors:

- Missing rows file plus dead driver → **`STALL: none` indefinitely**.
- Missing router log plus stale rows → **`WEDGE (idle)`**.
- An old completion marker anywhere in a recently modified log tail counts as current activity.
- The self-test passes an in-memory list directly to formatting; it tests neither file reading nor live observation.
- Driver death is checked only after the stall threshold.

Non-streaming generation can remain busy without recent completion-log entries. The watcher therefore supplies no reliable evidence for its wedge/runaway distinction.

**Minimal fix:** represent missing/unreadable/stale evidence explicitly; check driver death independently; time first-item silence from run start. Use attributable worker/in-flight activity for busy/idle classification, with **UNKNOWN** when unobservable. Exercise actual reader/classifier paths with known-positive and known-negative fixtures.

**P26 — HIGH: Cleanup verification can falsely succeed, and prepare bypasses it.**  
[agentbench_adapter.py:421]($STACK_REPO/benchmark/bench/agentbench_adapter.py:421), `:386–399`, `:846–898`.

I reproduced `remove_container(..., verify=True) == True` when removal returned zero but verification returned **exit 1 with empty stdout**. Prepare removes containers without verification and proceeds to subsequent tasks; startup sweeps also discard failures.

**Minimal fix:** require successful verification command status and proven absence. Apply the same fail-closed cleanup gate to prepare, startup and exceptional exits.

**P27 — HIGH: Malformed submit arguments can receive credit instead of corrective feedback.**  
[agentbench_adapter.py:956]($STACK_REPO/benchmark/bench/agentbench_adapter.py:956), `:1012–1027`; [agent_loop.py:147]($STACK_REPO/benchmark/bench/agent_loop.py:147).

I reproduced malformed JSON in `finish_action` becoming `answer_action({"answer": null})`, then a **passing one-turn episode** for a state-check task. The pinned upstream implementation instead sends a parsing-error tool response and continues. This changes which malformed model outputs receive credit. [Upstream task implementation](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/src/server/tasks/os_interaction/task.py).

**Minimal fix:** retain parse failures and reproduce upstream corrective behavior before submit normalization; do not silently substitute `{}`.

**P28 — MEDIUM: Memory compaction corrupts valid UTF-8.**  
[agentbench_adapter.py:704]($STACK_REPO/benchmark/bench/agentbench_adapter.py:704).

Compacting **1.2 MB of valid `€` characters** produced the decode-error message. Fixed byte cuts split multibyte characters; the adapter then discards the useful output that upstream would decode and truncate normally.

**Minimal fix:** validate/decode incrementally across original chunks while retaining a bounded display prefix and separate sentinel-search state.

**P29 — MEDIUM: Transcripts are neither run-isolated nor complete on important failure paths.**  
[run_agentbench_os.py:156]($STACK_REPO/benchmark/bench/run_agentbench_os.py:156), `:173–176`; [agentbench_adapter.py:1065]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1065), `:1282–1285`.

Different runs of the same model share `<model>/<task>.json`; a later run overwrites evidence referenced by earlier rows. Timeout/shell-death paths omit tool results. A grading infrastructure error resets an already-executed episode to zero turns/tokens and an empty transcript—I reproduced this with checker exit 127.

**Minimal fix:** use immutable run-specific transcript paths; preserve completed turns and error/tool results on all post-model failure paths.

**P30 — MEDIUM: Uncapped timeout is improved, but “observable” overstates its evidence.**  
[run_agentbench_os.py:368]($STACK_REPO/benchmark/bench/run_agentbench_os.py:368), `:413–421`; [agentbench_adapter.py:1310]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1310).

The old example now correctly derives **24,576 s** for 81,920 thinking tokens at 5 tok/s. However, calculation ignores `max_tokens`, uses episode-average decode rates rather than the recorded slow per-turn rates, and reads historical rows across serving configurations. An arbitrarily short explicit override is labelled observable.

**Minimal fix:** derive from maximum generation plus prefill/load headroom, using compatible per-turn slow-rate evidence. Record explicit overrides as unvalidated unless independently checked.

**P31 — MEDIUM: Remaining write paths violate confinement.**  
[run_agentbench_os.py:459]($STACK_REPO/benchmark/bench/run_agentbench_os.py:459), `:764`; [agentbench_watch.py:262]($STACK_REPO/benchmark/bench/agentbench_watch.py:262).

`--prepare --corpus /outside/tasks.jsonl` writes a sibling artifact outside approved roots. Watcher `--out` is unrestricted.

**Minimal fix:** validate every resolved write target before creating it, including derived artifacts.

**P32 — MEDIUM: ETA uses the mean, but not total task duration.**  
[agentbench_adapter.py:1300]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1300); [agentbench_watch.py:136]($STACK_REPO/benchmark/bench/agentbench_watch.py:136).

Successful rows report loop time, excluding container setup, grading and cleanup. Failed-setup rows use a different timing scope. Mean-based ETA therefore underestimates campaign cost. The watcher also omits the required comparison with predicted rate, `nonconv_kinds`, degenerate-EOS distribution and correction-versus-finishing assessment.

**Minimal fix:** record consistent end-to-end task duration separately from loop duration and implement the missing assessments.

**P33 — Verification and acceptance status**

- **Ran:** 162 fixture-free tests from the three requested files; another 23 agent-loop tests—all passed. These were direct invocations, not a full pytest run.
- **Ran:** mocked reproductions described above; real local Bash I/O reproduction; build-script syntax check.
- **Verified programmatically:** 144 unique tasks, manifest hash, all task configurations, corpus fields and vendored scripts against the local clone at the pinned upstream SHA; prompt and tool-schema equality. Also consulted the supplied upstream [configuration](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/configs/tasks/os.yaml).
- **Blocked:** the exact pytest command failed before collection because no writable temporary directory was available.
- **Read:** specified fix history, implementation, tests, contract, binding rules and build script. No Docker or model-server calls; no edits or commits. An untracked exclusions artifact appeared during review and was excluded from this commit-scoped assessment.

**AC1 passes. AC2’s revised preparation identity is substantially repaired. AC3–AC5 and AC9 retain blockers. AC7’s degrade path is present. AC6 is only partially verified; AC8 retains confinement gaps.**

**P34 — What can safely wait until after a five-item pilot**

Only with explicit operating constraints:

- **P21:** use a fresh output and never resume.
- **P29:** use a unique transcript directory per run; treat failure transcripts as incomplete.
- **P30:** supply an independently justified timeout covering maximum generation and headroom.
- **P31:** keep every input-derived artifact and output under approved roots.
- **P32:** measure total pilot elapsed time independently; do not use current ETA for scheduling.
- **P17’s remaining ordering issue:** the subset is random; restoring randomized execution order can wait.

I would **not** carry P22–P28 into the live pilot. Fix the execution, scoring, monitoring and cleanup blockers first, then run the full requested suite.
