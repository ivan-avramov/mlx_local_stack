**FAIL — M54 at `ee6fcaa` still has scoring, timeout-provenance, and monitoring defects.** The requested tests pass, but independent probes reproduce three residuals and two additional failures.

**P1 — Review 6 verification.** “NOT” includes partial fixes. Aliases cover every row review 6 marked NOT.

| Review 6 finding / residual aliases | Status | Current evidence |
|---|---|---|
| **R6:P7 grading**; R5:P8, P47, P37/P23 | **NOT** | A real local checker executing `exit 125` becomes excluded `setup_error`, with `exec_started=False`. Conversely, mocked exec-creation failure returning 1 followed by `Running=true` becomes scored `failed_tests`. [agentbench_adapter.py:1053]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1053) |
| **R6:P8 timeout identity**; R5:P9, P48, P43(b)/P30 | **NOT** | Incompatible configuration still produces **1,324 s** for 102,400 tokens. Its new `observable="params-match (UNVALIDATED)"` value is truthy, so generation proceeds without an explicit override. [derivation:713]($STACK_REPO/benchmark/bench/run_agentbench_os.py:713), [launch gate:946]($STACK_REPO/benchmark/bench/run_agentbench_os.py:946) |
| **R6:P9 watcher**; R5:P12, P52, P38/P25 | **NOT** | Missing-timing arithmetic and unreadable-evidence→WEDGE are fixed; router PID/hash changes invalidate calibration. But one active BUSY observation still enables WEDGE without known-idle calibration, and worker replacement under the same router does not invalidate it. [identity:342]($STACK_REPO/benchmark/bench/agentbench_watch.py:342), [calibration:537]($STACK_REPO/benchmark/bench/agentbench_watch.py:537) |
| **R6:P10 first-call-only semantics** | **CONFIRMED-FIXED** | Correct first answer followed by empty second answer passes in one turn; ignored calls cannot abort it. [agentbench_adapter.py:1369]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1369) |
| **R6:P11 aborted-turn telemetry** | **CONFIRMED-FIXED** | Empty answer preserves **57 total tokens, one turn, one tool call**, consistent with per-turn evidence. [agent_loop.py:197]($STACK_REPO/benchmark/bench/agent_loop.py:197) |
| **R6:P12 incomplete UTF-8** | **CONFIRMED-FIXED** | Real Bash `printf 'ABCD\342'` now returns the upstream decode-error message; complete UTF-8 remains intact. Finalization also covers timeout/EOF paths. [agentbench_adapter.py:792]($STACK_REPO/benchmark/bench/agentbench_adapter.py:792) |
| **Residual infrastructure recovery / comparable coverage** | **NOT** | Resume still skips every existing ID, including infrastructure-error rows. `graded_ids` records coverage but does not enforce comparable arms. [resume:860]($STACK_REPO/benchmark/bench/run_agentbench_os.py:860), [coverage:440]($STACK_REPO/benchmark/bench/run_agentbench_os.py:440) |

The remaining grading assumption is false: Docker’s CLI propagates the executed process’s nonzero status, including 125. Container health also does not establish that a particular exec started. Use separate exec creation/start/completion evidence; quarantine ambiguity instead of inferring execution from status codes or `Running`. [Docker CLI implementation](https://raw.githubusercontent.com/docker/cli/master/cli/command/container/exec.go)

For timeout evidence, require exact compatible serving identity—including implementation—or a complete performance fingerprint. Relabeling incompatible evidence does not make the derived bound adequate; require an explicit override when validation fails.

For monitoring, bind active/idle calibration to the **worker identity and serving configuration**. Also, unreadable row evidence still permits `RUNAWAY-SUSPECT`; CPU activity cannot establish missing item progress when the item evidence itself is unavailable.

**P2 — HIGH, new: model-controlled NUL answers escape the scoring denominator.**

`answer_action({"answer":"\u0000"})` reaches checker argv construction. Python rejects it with `ValueError: embedded null byte`; the catch-all converts that into excluded `setup_error`.

I reproduced both the actual local subprocess argv rejection and the resulting mocked episode classification. This is a malformed model answer, not evidence of infrastructure failure.

Minimal fix: detect unrepresentable model-supplied argv values and retain a scored failure with diagnostics. Handle genuine execution failures separately. [argv construction:510]($STACK_REPO/benchmark/bench/agentbench_adapter.py:510), [catch-all:1781]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1781)

**P3 — MEDIUM, new: malformed manifest evidence can kill the watcher.**

`read_manifest()` uses strict UTF-8 decoding but catches only `OSError` and `JSONDecodeError`. An invalid UTF-8 manifest raises `UnicodeDecodeError` out of the daemon. Successful JSON decoding also does not establish that the result is a mapping.

Minimal fix: validate decoding and document shape, return an explicit evidence-failure status, and propagate UNKNOWN while keeping the watcher alive. Opening the file successfully is insufficient validation. [reader:122]($STACK_REPO/benchmark/bench/agentbench_watch.py:122), [evidence flags:918]($STACK_REPO/benchmark/bench/agentbench_watch.py:918)

**P4 — Four live-pilot fixes.**

| Claim | Status | Evidence |
|---|---|---|
| Explicit transcript directory nests `<model>/<run_id>` | **CONFIRMED-FIXED** | Independently probed the resulting path. [run_agentbench_os.py:171]($STACK_REPO/benchmark/bench/run_agentbench_os.py:171) |
| Global test workdir guard | **CONFIRMED-FIXED** | Direct probe refused resolution to the real workdir before use. [conftest.py:230]($STACK_REPO/benchmark/bench/tests/conftest.py:230) |
| Watcher exits on completed rows plus dead driver | **CONFIRMED-FIXED** | First-tick completion test passes. [agentbench_watch.py:968]($STACK_REPO/benchmark/bench/agentbench_watch.py:968) |
| Watcher exits promptly on SIGTERM | **CONFIRMED-FIXED** | Real-signal regression test passes; the interval wait uses an interruptible event. [agentbench_watch.py:972]($STACK_REPO/benchmark/bench/agentbench_watch.py:972) |

**P5 — Verification performed.**

Ran:

- Requested suite: **469 passed**, two warnings, **32.76 s**. Initial sandbox attempt failed before collection; retry used the specified workdir temporary directory.
- Adjacent agent-loop suites: **33 passed**.
- Independent real Bash: **20 MiB output + 300 KiB script in 0.242 s**; **1.2 MB valid UTF-8** preserved; full-queue `close()` returned in **0.063 s**, with no surviving reader thread.
- Independent mocked probes for grading, malformed arguments, first-call behavior, telemetry escalation, timeout identity, resume identity, watcher UNKNOWN/calibration, and correction economics.
- Actual discovery against reviewer-owned processes: **100% CPU → busy; 0% → idle**. This verifies OS observation, not MLX inference calibration.
- Programmatic comparison against pinned upstream Git objects: **144 task records, 19 scripts, license, prompt, tools, round limit, and corpus hash matched**. The existing exclusion artifact has rule v2, 144 dispositions, two exclusions, and matching corpus/script hashes. [Pinned configuration](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/configs/tasks/os.yaml), [task implementation](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/src/server/tasks/os_interaction/task.py)
- Build-script syntax, commit-range whitespace, and added-line PII/model-name checks passed.

Read the contract, AGENTS.md, six reviews, requested fix history, scoped implementation/tests, README, build script, and corpus artifacts. Historical test-first commits exist.

No Docker execution, localhost:8000 contact, source edits, or commits. HEAD and the pre-existing untracked exclusions artifact remain unchanged. Actual image identity and Docker lifecycle remain unverified.

**P6 — Pilot and full-arm recommendation.**

**Fix before a scored five-item pilot:**

- R6:P7 grading classification, including the false exit-125 assumption.
- P2 model-controlled argv failures becoming exclusions.

**Safe to carry into a supervised five-item pilot, conditionally:**

- R6:P8 timeout gap: use an independently justified explicit timeout.
- R6:P9 and P3 watcher gaps: independently supervise daemon liveness, record assessments, and do not act on unvalidated WEDGE/RUNAWAY labels.
- Unverified Docker/image behavior: validate identity and cleanup during bring-up.
- Infrastructure recovery/coverage gaps: use fresh outputs and do not treat pilot scores as a ladder comparison.

**Before 144-task arms:** close all remaining defects above; validate known-active/known-idle inference calibration for the actual worker; verify real container cleanup and image identity; and establish infrastructure-error recovery with matched valid task coverage. **I would not authorize comparative arms from this revision.**
