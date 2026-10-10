**FAIL — M54 at `4c7dcb5` is not ready for the live pilot.** The tests pass, but independent probes still reproduce scoring, monitoring, cleanup and provenance defects.

**P35 — Verification of P21–P32.** “NOT” includes partial fixes.

| Claim | Status | Evidence at reviewed HEAD |
|---|---|---|
| P21 Resume identity | **NOT** | Sampling/hash changes are rejected, but existing rows without a manifest remain accepted. Changing implementation fingerprints also passes. [run_agentbench_os.py:298]($STACK_REPO/benchmark/bench/run_agentbench_os.py:298), [:331]($STACK_REPO/benchmark/bench/run_agentbench_os.py:331). |
| P22 Deadlock/shutdown | **NOT** | Concurrent I/O fixes the reproduced deadlock; `close()` is bounded. However, reader threads remain blocked on full queues after cleanup. [agentbench_adapter.py:611]($STACK_REPO/benchmark/bench/agentbench_adapter.py:611), [:825]($STACK_REPO/benchmark/bench/agentbench_adapter.py:825). |
| P23 Grading classification | **NOT** | Bare checker exit 127 now remains scored. Docker exit 1 with “container … is not running” still becomes `failed_tests`; application stderr can falsely trigger exclusion. [agentbench_adapter.py:887]($STACK_REPO/benchmark/bench/agentbench_adapter.py:887). |
| P24 Telemetry escalation | **NOT** | Missing fields escalate, but invalid token-count types produce excluded rows. Valid empty/reasoning-only completions now incorrectly abort the run. [client.py:89]($STACK_REPO/benchmark/bench/client.py:89). |
| P25 Watcher | **NOT** | Dead-driver and explicit UNKNOWN branches work. Actual macOS worker discovery fails; failed CPU reads become idle. [agentbench_watch.py:170]($STACK_REPO/benchmark/bench/agentbench_watch.py:170), [:198]($STACK_REPO/benchmark/bench/agentbench_watch.py:198). |
| P26 Cleanup | **NOT** | Removal verification correctly requires successful `docker ps`; prepare’s final removals are verified. Startup discovery still silently accepts command failure, and prepare lacks an initial sweep. [agentbench_adapter.py:387]($STACK_REPO/benchmark/bench/agentbench_adapter.py:387), [run_agentbench_os.py:579]($STACK_REPO/benchmark/bench/run_agentbench_os.py:579). |
| P27 Malformed arguments | **CONFIRMED-FIXED** | Malformed submit JSON receives corrective feedback and consumes another turn; it no longer becomes a submission. [agent_loop.py:165]($STACK_REPO/benchmark/bench/agent_loop.py:165), [agentbench_adapter.py:1174]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1174). |
| P28 UTF-8 compaction | **CONFIRMED-FIXED** | Incremental decoding preserves valid multibyte output. Independent 1.2 MB euro-sign probe passed. [agentbench_adapter.py:698]($STACK_REPO/benchmark/bench/agentbench_adapter.py:698). |
| P29 Transcripts | **NOT** | Default run directories and grading-error turn preservation are improved. Shell-death/timeout and parse-error feedback remain absent from saved turns. [agentbench_adapter.py:1235]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1235). |
| P30 Timeout sizing | **NOT** | Maximum-generation sizing, per-turn minimum and unvalidated override labeling are fixed. Historical rates still lack serving-identity filtering. [run_agentbench_os.py:512]($STACK_REPO/benchmark/bench/run_agentbench_os.py:512), [generate.py:98]($STACK_REPO/benchmark/bench/generate.py:98). |
| P31 Named output paths | **CONFIRMED-FIXED** | Derived exclusions and watcher `--out` are checked before writing. Additional confinement gaps remain below. [run_agentbench_os.py:557]($STACK_REPO/benchmark/bench/run_agentbench_os.py:557), [agentbench_watch.py:584]($STACK_REPO/benchmark/bench/agentbench_watch.py:584). |
| P32 Timing/assessments | **NOT** | Full lifecycle timing now exists. “CORRECT-vs-FINISH” merely prints elapsed/remaining estimates; it neither compares against a prior prediction nor evaluates correction cost. EOS classification also mispairs turns. [agentbench_watch.py:301]($STACK_REPO/benchmark/bench/agentbench_watch.py:301), [:376]($STACK_REPO/benchmark/bench/agentbench_watch.py:376). |

**P36 — HIGH: Valid model failures are newly misclassified as transport failures.**

A response containing reasoning, valid usage and `finish_reason="length"` raises `TransportFailure` without a row. Immediate EOS with valid zero-completion usage does likewise. These are model outcomes the benchmark must retain. The serving implementation explicitly permits empty content while returning reasoning and usage: [openai.py:2981]($STACK_REPO/src/mlx-vlm/mlx_vlm/server/openai.py:2981).

Conversely, `completion_tokens="bad"` passes client validation, then becomes an excluded `setup_error` row.

**Minimal fix:** validate envelope structure and nonnegative integer telemetry; accept structurally valid empty completions and let the episode/convergence logic classify them. Escalate malformed telemetry before entering the loop.

**P37 — HIGH: Grading still confuses execution failure with checker failure.**

Independent end-to-end probes produced:

- Exit 1, daemon reports stopped container → scored `failed_tests`.
- Exit 127, application says “application is not running” → excluded `setup_error`.

The suite explicitly asserts the first incorrect behavior in [test_agentbench_adapter.py:242]($STACK_REPO/benchmark/bench/tests/test_agentbench_adapter.py:242). Passing tests therefore do not resolve the contract violation.

**Minimal fix:** distinguish checker execution/exit status from Docker execution failure through separate execution-status evidence. Broad stderr substrings are insufficient. Require matched, valid task coverage before comparing arm scores; recording `graded_ids` alone does not enforce it.

**P38 — HIGH: The watcher’s live observation path is unvalidated and broken on this Mac.**

Against a reviewer-owned child process, actual `pgrep -af` returned only its PID; `find_worker_pids()` discarded it. `pgrep -fl` returned the required command line and parsed successfully.

Separately, a failed `ps` call returned `0.0`, producing **WEDGE (idle)**. The self-test injects busy/idle booleans and therefore misses both failures: [agentbench_watch.py:449]($STACK_REPO/benchmark/bench/agentbench_watch.py:449).

**Minimal fix:** use macOS-compatible discovery, associate the worker with the verified router, and propagate observation failures as UNKNOWN. Calibrate CPU observations against known active/idle inference before treating low CPU as proof of a wedge.

**P39 — HIGH: Resume still permits provenance laundering.**

Missing-manifest acceptance remains reachable with existing rows; the existing test actually exercises that acceptance: [test_run_agentbench_os.py:528]($STACK_REPO/benchmark/bench/tests/test_run_agentbench_os.py:528). Changing stack/serving implementation fingerprints also leaves `_identity_snapshot()` unchanged.

**Minimal fix:** require a readable, complete manifest whenever rows exist; include the relevant harness/serving implementation identity. Preserve that identity in each segment.

**P40 — HIGH: Startup cleanup remains fail-open.**

A mocked failed discovery command returned `[]`, indistinguishable from proven absence. After an interrupted run, a transient discovery failure can allow another task container to start while an earlier one survives.

**Minimal fix:** require successful discovery before both generate and prepare; abort when absence/removal cannot be established.

**P41 — MEDIUM: Bounded shutdown still leaks bounded queues indefinitely.**

After a background writer filled the default queue, `close()` returned in **0.307 s**. After killing all reviewer-owned processes, its reader thread remained alive with **256 queued chunks**. A timed join does not cancel a thread blocked in `Queue.put()`.

**Minimal fix:** introduce cancellation-aware queue operations, close pipe handles, and terminate/join all reader/writer threads. Test thread termination after container/process removal, not merely `close()` latency.

**P42 — MEDIUM: Two write paths still escape confinement.**

The watcher calls `tempfile.mkdtemp()` without an approved directory: [agentbench_watch.py:479]($STACK_REPO/benchmark/bench/agentbench_watch.py:479). Default invocation therefore uses the system temporary location unless the operator redirects it.

Resume also trusts the manifest’s saved transcript directory without checking the resolved target; my probe returned `/outside/old-run`: [run_agentbench_os.py:179]($STACK_REPO/benchmark/bench/run_agentbench_os.py:179).

**Minimal fix:** explicitly place self-test files under `$STACK_WORKDIR` and validate the final transcript directory after resume resolution.

**P43 — MEDIUM: Evidence preservation, timeout provenance and monitoring assessments remain incomplete.**

- A shell-death episode retained `tool_result=None` and `error=None`. Save corrective/abort feedback before raising; preserve completed turns through unexpected grading exceptions.
- An incompatible historical 100 tok/s row yielded an “observable” **1,324 s** timeout for 102,400 tokens. Filter rate evidence by serving identity and retain source references.
- `["tool_calls","stop"]` with token counts `[1,100]` falsely counted as degenerate EOS. Pair finish reasons with token counts by turn.
- Compare observed duration against a recorded prediction and provide an actual correction recommendation; elapsed-plus-ETA arithmetic does not satisfy the standing assessment rule.

**P44 — What I ran and read.**

- Requested suite: **331 passed**, two deprecation warnings, **16.53 s**. The initial sandbox attempt failed; the successful run used temporary files under the specified workdir.
- Adjacent agent-loop/driver tests: **21 passed**. Driver tests used their own ephemeral loopback HTTP fixture servers.
- Independent local Bash probes: 20 MiB output plus 300 KiB script completed in **0.137 s**; 1.2 MB UTF-8 output completed correctly; bounded close and persistent reader-thread leak reproduced.
- Independent mocked probes covered grading, malformed arguments, telemetry escalation, resume identity, cleanup, UNKNOWN/busy/idle classification, timeout evidence and transcript failures.
- Verified **144 task records, 19 scripts, license, prompt, tool schemas and corpus hash** against pinned upstream Git objects; consulted the supplied [configuration](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/configs/tasks/os.yaml) and [task implementation](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/src/server/tasks/os_interaction/task.py).
- Read both prior reviews, the requested commit history, contract, binding rules, implementation/tests, README and image-build script. Build-script syntax passed.

No Docker execution, port-8000 contact, repository edits or commits. The pre-existing untracked exclusions artifact remained unmodified; live image identity and actual Docker behavior were not verified.

**P45 — Pilot and full-arm gates.**

**Fix before the five-item pilot:** P36–P38 and P40—the telemetry/scoring, live monitoring and startup-cleanup defects.

**Safe to carry into a tightly controlled pilot after those fixes:**

- Resume gaps: fresh output only; no resume.
- Timeout filtering: independently justified explicit timeout covering maximum generation.
- Confinement gaps: explicit approved `TMPDIR` and fresh approved transcript directory.
- Transcript/ETA gaps: inspect all five episodes manually and measure total elapsed time independently.
- Thread leak: bounded five-task process; terminate the driver afterward and verify cleanup.

**Before corpus-wide arms:** fix all residuals, including resume identity, thread termination, transcript completeness, rate-evidence filtering, path confinement and monitoring assessments. Establish recovery of infrastructure-error tasks and matched coverage for the pre-registered paired analysis. **AC1 is verified; AC3–AC5, AC8 and AC9 retain substantive gaps.**
