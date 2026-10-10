**FAIL — M54 at `0c4d469` is not ready for a scored pilot or comparative arms.** The claimed reproductions are fixed, but grading, timeout provenance, and monitoring gaps remain. The new checker wrapper also breaks seven vendored initialization scripts.

**P4 — Scope and review-7 verification**

References below use **`0c4d469` line numbers**. During review, external edits appeared in `agentbench_adapter.py` and its tests. I made no edits; I verified the affected findings against the requested Git object loaded into memory. The exclusions artifact was already untracked.

“NOT” includes partial fixes. `R7:` distinguishes previous-review identifiers.

| Review-7 finding / residual | Status | Verification |
|---|---|---|
| R7:P1 grading; R6:P7 and earlier aliases | **NOT** | Real Bash exits 125/126/127/137 are correctly recognized as checker exits. Missing-marker, non-timeout exec failure is excluded. But a **pre-execution timeout** followed by `Running=true` still becomes scored `failed_tests`, `exec_started=True`. [Classifier:1108]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1108) |
| R7:P1 timeout identity; R6:P8 | **NOT** | The new gate correctly rejects `False`, integer `1`, and `"params-match (UNVALIDATED)"`; it admits only literal `True` without override. However, incompatible serving implementations still receive an “exact” match. [Gate:955]($STACK_REPO/benchmark/bench/run_agentbench_os.py:955), [identity:583]($STACK_REPO/benchmark/bench/run_agentbench_os.py:583) |
| R7:P1 watcher; R6:P9 | **NOT** | Missing timing yields UNKNOWN; unavailable rows block RUNAWAY. One active BUSY sample still enables WEDGE without known-idle calibration, and worker replacement under the same router preserves calibration. [Calibration:354]($STACK_REPO/benchmark/bench/agentbench_watch.py:354), [BUSY observation:569]($STACK_REPO/benchmark/bench/agentbench_watch.py:569) |
| R7:P1 infrastructure recovery / comparable coverage | **NOT** | Mocked resume with one infrastructure-error row reported **one done, zero todo**. `graded_ids` records coverage but does not enforce comparability. [Resume:860]($STACK_REPO/benchmark/bench/run_agentbench_os.py:860), [coverage:440]($STACK_REPO/benchmark/bench/run_agentbench_os.py:440) |
| R7:P2 NUL answer | **CONFIRMED-FIXED** | Actual subprocess argv rejection becomes `failed_tests`, `setup_error=False`, retaining one turn and 57 tokens. Oversized argv remains a separate failure below. [Answer handling:1780]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1780) |
| R7:P3 invalid UTF-8 / top-level manifest shape | **CONFIRMED-FIXED** | Invalid UTF-8, malformed JSON, lists and scalars return unavailable evidence without escaping the reader. Nested corruption remains below. [Reader:122]($STACK_REPO/benchmark/bench/agentbench_watch.py:122) |
| R7:P1 first-call-only semantics | **CONFIRMED-FIXED** | Correct first answer followed by empty second answer solves in one turn. [Adapter:1426]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1426) |
| R7:P1 aborted-turn telemetry | **CONFIRMED-FIXED** | Empty first answer remains a scored failure with one turn and 57 aggregate tokens. [Abort handling:197]($STACK_REPO/benchmark/bench/agent_loop.py:197) |
| R7:P1 incomplete UTF-8 | **CONFIRMED-FIXED** | Real Bash `printf 'ABCD\342'` returns the upstream decode-error message. [Decoder finalization:851]($STACK_REPO/benchmark/bench/agentbench_adapter.py:851) |
| R7:P4 four pilot fixes | **CONFIRMED-FIXED** | Transcript nesting, test-workdir guard, completed/dead-driver exit and interruptible SIGTERM wait remain implemented; their regression tests pass. [Nesting:176]($STACK_REPO/benchmark/bench/run_agentbench_os.py:176), [guard:231]($STACK_REPO/benchmark/bench/tests/conftest.py:231), [watcher exits:1005]($STACK_REPO/benchmark/bench/agentbench_watch.py:1005) |

The older shell deadlock/close/compaction, malformed-argument, telemetry-escalation and resume-identity fixes also passed independent probes.

**P5 — HIGH, new regression: the wrapper rejects comment-only initialization scripts.**

At [agentbench_adapter.py:555]($STACK_REPO/benchmark/bench/agentbench_adapter.py:555), wrapping comment-only code inside `( … )` creates an empty Bash subshell body. Bash rejects it with exit 2 before printing the marker.

Syntax probes against **every vendored Bash script** found seven affected tasks: `std-007-{18,55,59,62,67,74,75}`. Running the actual `std-007-18` initialization through the pinned adapter produced `server_error`, `setup_error=True`, with **zero model calls**. Regenerating exclusions could also misclassify these harness failures as corpus defects.

**Minimal fix:** insert a leading `:` inside the subshell; test the exact wrapper against the whole corpus. The external uncommitted edit exposed this issue and contains that proposed fix; the reviewed commit does not.

**P6 — HIGH, residual: timeout still substitutes container health for execution evidence.**

A mocked Docker timeout **before the checker starts**, followed by successful `inspect`, produced:

```text
outcome=failed_tests, setup_error=False, exec_started=True
```

The completion marker cannot distinguish “never started” from “started and hung” when neither reaches completion. [agentbench_adapter.py:1108]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1108)

**Minimal fix:** record execution-start evidence separately and preserve it on timeout. Quarantine unknown execution state instead of asserting that the checker ran.

**P7 — HIGH, additional answer-classification gap: oversized answers escape the denominator.**

A real local subprocess probe with a 2 MiB submitted answer raised `OSError(E2BIG)`. The pinned episode became excluded `server_error`, `setup_error=True`. The new handler catches `ValueError`/`TypeError`, while this model-controlled argv failure reaches the infrastructure catch-all. [Handler:1780]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1780), [catch-all:1856]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1856)

**Minimal fix:** classify answer-induced `E2BIG` as a scored invalid-answer failure. Keep genuine process-launch infrastructure errors separate.

**P8 — HIGH, residual: “exact” timeout identity omits serving implementation.**

A historical manifest with the same YAML hash and checked parameters but an incompatible serving implementation returned `(True, "exact")`. Its rate yielded **1,324 seconds for 102,400 tokens**, with `observable=True`, which passes the repaired gate. [run_agentbench_os.py:567]($STACK_REPO/benchmark/bench/run_agentbench_os.py:567)

**Minimal fix:** include serving implementation identity in the required performance fingerprint. A configuration-file hash alone does not establish performance compatibility.

**P9 — MEDIUM, additional monitoring failures and remaining calibration gap.**

Full mocked watcher probes reproduced:

- `{"router":[1]}` → uncaught `AttributeError`.
- A string `segments[-1].started_at` → uncaught `TypeError`.
- A JSON-list row → uncaught `AttributeError` during assessment.

Top-level mapping validation does not validate consumed fields. [Manifest validation:140]($STACK_REPO/benchmark/bench/agentbench_watch.py:140), [router extraction:958]($STACK_REPO/benchmark/bench/agentbench_watch.py:958), [timing arithmetic:548]($STACK_REPO/benchmark/bench/agentbench_watch.py:548)

**Minimal fix:** validate nested manifest fields, numeric timestamps and row mappings; propagate invalid evidence as UNKNOWN while keeping the daemon alive. Separately, require known-active **and** known-idle calibration tied to worker identity and serving configuration.

**P10 — What I ran versus read**

**Ran:**

- Requested suite: **480 passed**, two warnings, **39.48 s**. The initial sandbox attempt failed before collection; the authorized retry used the specified temporary directory.
- Adjacent agent-loop suites: **33 passed**.
- Real local Bash: exit-125 checker; **20 MiB output + 300 KiB script in 0.145 s**; 3.6 MB valid UTF-8 through compaction; full-queue `close()` in **0.190 s**, reader terminated; incomplete UTF-8 rejection.
- Independent mocked driver/runner probes for grading, NUL/oversized answers, malformed arguments, first-call semantics, telemetry escalation, resume identity/recovery, timeout gating and watcher UNKNOWN/calibration.
- Actual watcher discovery against reviewer-owned processes: **97.1% CPU → busy; 0.1% → idle**. This validates OS observation, not MLX inference calibration.
- Pinned upstream comparison: **144 task records, 19 scripts, license, prompt, tool schemas and round limit matched**; corpus hash matched. Exclusions artifact: rule v2, 144 dispositions, two exclusions, matching corpus/script hashes.
- Build-script syntax, commit-range whitespace, and added-line PII/model-name checks passed.

**Read:** contract, binding rules, prior-review findings, fix history, scoped implementation/tests, README, build script and corpus artifacts. Historical test-first commits exist. Upstream comparisons used the pinned [configuration](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/configs/tasks/os.yaml) and [task implementation](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/src/server/tasks/os_interaction/task.py).

**Contract:** AC1 verified; AC2–AC5 retain substantive gaps. AC6/AC7/AC8 checks passed within the stated scope. AC9 has passing mocked coverage; actual Docker cleanup and image identity remain unverified.

No Docker execution, port-8000 contact, source edits or commits were performed by me.

**P11 — Pilot and full-arm recommendation**

**Fix before a scored five-item pilot:**

- P5 comment-only initialization regression.
- P6 ambiguous timeout grading.
- P7 oversized-answer exclusion.

**Safe to carry into a supervised five-item pilot after those fixes:**

- P8 timeout provenance gap, using an independently justified explicit timeout.
- P9 watcher gaps, with independent daemon supervision and recorded assessments; do not trust unvalidated WEDGE/RUNAWAY labels.
- Infrastructure recovery/coverage gap, using fresh outputs and making no ladder comparison.
- Unverified image/container behavior, explicitly validated during pilot bring-up.

**Before full 144-task-corpus arms:** close all remaining findings; establish infrastructure-error recovery and matched valid coverage; validate actual worker active/idle calibration, image identity and container cleanup. **I would not authorize comparative arms from `0c4d469`.**
