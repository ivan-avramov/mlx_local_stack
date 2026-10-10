**FAIL — M54 at `aae3bfb` still has scoring and protocol defects.** The requested suite passes, but several fixes address only the original reproductions.

**P7 — Verification of P47–P54 and review 4’s residual NOT rows**

“NOT” includes partial fixes.

| Prior finding | Status | Verified result and reference |
|---|---|---|
| P47 grading classification | **NOT** | Application stderr and deleted dependencies no longer trigger exclusions. However, a running container does not prove the checker executed. [agentbench_adapter.py:991]($STACK_REPO/benchmark/bench/agentbench_adapter.py:991) |
| P48 timeout provenance | **NOT** | Box, budget, KV cap and drift filtering work. Serving-config hash and preallocation remain unchecked. [run_agentbench_os.py:536]($STACK_REPO/benchmark/bench/run_agentbench_os.py:536) |
| P49 upstream argument behavior | **NOT** | First-value extraction and unknown-tool text are fixed. Empty `answer_action({})` now receives recovery opportunities absent upstream. [agentbench_adapter.py:1334]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1334) |
| P50 finish telemetry | **CONFIRMED-FIXED** | Invalid types/values escalate; valid empty EOS and `length` responses remain scored outcomes. [client.py:121]($STACK_REPO/benchmark/bench/client.py:121) |
| P51 sentinel UTF-8 | **NOT** | Complete trailing `€` works. A trailing partial UTF-8 character still corrupts the preceding result. [agentbench_adapter.py:790]($STACK_REPO/benchmark/bench/agentbench_adapter.py:790) |
| P52 watcher failures/calibration | **NOT** | Permission failures no longer crash the reader; all-UNKNOWN calibration fails. Actual inference calibration is still replaced by “ever saw BUSY.” [agentbench_watch.py:461]($STACK_REPO/benchmark/bench/agentbench_watch.py:461) |
| P53 counters/feedback | **CONFIRMED-FIXED** | Grading exception preserved one turn and 57 tokens; malformed, unknown-tool and tool-less feedback were captured. [agentbench_adapter.py:1588]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1588), [exception handling:1680]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1680) |
| P54 correction assessment | **NOT** | Insufficient evidence now yields UNKNOWN. “Correction cost” is still sunk work, without an estimate of fixing or recovery. [agentbench_watch.py:526]($STACK_REPO/benchmark/bench/agentbench_watch.py:526) |
| P37/P23 grading residual | **NOT** | Same remaining classification defect as P47. |
| P38/P25 watcher residual | **NOT** | Discovery works; calibration and evidence propagation remain incomplete. [agentbench_watch.py:471]($STACK_REPO/benchmark/bench/agentbench_watch.py:471) |
| P43(a)/P29 evidence preservation | **CONFIRMED-FIXED** | Requested grading-counter and corrective-feedback reproductions pass; see P53. |
| P43(b)/P30 timeout evidence | **NOT** | Same remaining identity gap as P48. |
| P43(d)/P32 assessments | **NOT** | Lifecycle timing and prediction comparison work; intervention economics remain unsupported. |
| P24 telemetry escalation | **CONFIRMED-FIXED** | Missing/invalid token telemetry and malformed finish reasons escalate. [client.py:130]($STACK_REPO/benchmark/bench/client.py:130) |

**P8 — HIGH: Grading still misclassifies failures in both directions.**

Two reproduced cases:

- A Docker exec creation failure, followed by successful inspect reporting `Running=true`, became scored `failed_tests`, with no infrastructure evidence.
- A checker emitting invalid UTF-8 on stderr became an excluded `setup_error` through `UnicodeDecodeError`. This can be model-controlled: an existing corpus checker sources the model-editable `.bashrc`.

The first is a P47 residual; the second is an additional classification path through [docker_exec:507]($STACK_REPO/benchmark/bench/agentbench_adapter.py:507) and the [catch-all:1673]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1673).

**Minimal fix:** distinguish exec creation/start failures from the process’s exit status using separate execution evidence. Capture checker streams as bytes; decoding diagnostics must not turn model-caused failures into exclusions. Quarantine ambiguous execution failures.

**P9 — HIGH: Incompatible serving configurations still size “observable” timeouts.**

An independently mocked historical manifest with matching checked fields but a different serving-config hash and preallocation still produced **1,324 seconds for 102,400 tokens**, with `observable=True`. Recording the source hash does not validate it.

**Minimal fix:** compare the serving-config fingerprint and relevant performance settings, including preallocation, before admitting rate evidence. Retain those fingerprints in the derivation.

**P10 — MEDIUM, new protocol defect: Empty submissions can recover and pass.**

`answer_action({})`, followed by a correct answer, passed in two turns. Pinned upstream raises `IndexError` during positional extraction; that exception escapes the action handler and terminates the sample through its task-error path. The adapter instead renames the call to an unknown-tool sentinel and continues. [Adapter:1336]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1336), [pinned upstream implementation](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/src/server/tasks/os_interaction/task.py).

**Minimal fix:** reproduce the upstream terminal behavior for empty positional arguments. Any intentional recovery policy needs an explicit protocol amendment.

**P11 — MEDIUM: Sentinel output still depends on read-chunk boundaries.**

Deterministic stream probes returned:

| Bytes after completed sentinel | Preceding output |
|---|---|
| Complete `€` | `ABCD` |
| First byte of `€` | Decode-error message |
| Invalid byte `ff` | Decode-error message |

The trailing bytes were correctly carried forward, but also decoded while deciding the preceding command’s result.

**Minimal fix:** separate sentinel/trailing bytes before decoding command output. Finalize the command decoder independently; carry subsequent bytes untouched.

**P12 — MEDIUM: Watcher calibration and UNKNOWN handling remain incomplete.**

A single arbitrary BUSY observation enabled a subsequent **WEDGE** classification without known-active/known-idle inference calibration. Separately, unreadable rows plus a recent manifest produced an evidence warning alongside **`STALL: none`**: evidence flags do not control the classifier.

An additional probe with five rows lacking timing and a supplied prediction raised `TypeError` in correction-cost arithmetic.

**Minimal fix:** persist explicit active/idle calibration tied to the worker/configuration; propagate unreadable or unusable evidence as UNKNOWN; validate timing before arithmetic.

**P13 — MEDIUM: The correction recommendation uses the wrong cost comparison.**

The decision compares:

- remaining rows × observed mean;
- completed rows × observed mean.

Consequently, after the midpoint it cannot recommend correction, regardless of how cheap the fix is or how unusable further rows would be. Two ticks over unchanged rows also satisfy “persistence.”

**Minimal fix:** estimate correction, recovery and remaining valid work separately. Report UNKNOWN when those estimates are unavailable; separate detected problems from intervention recommendations.

**P14 — MEDIUM, new: Resume ignores hardware identity.**

Changing only the manifest’s `box` was accepted by `_check_resume_identity`. Changed implementation SHA, sampling and config hash were correctly refused. [Identity snapshot:323]($STACK_REPO/benchmark/bench/run_agentbench_os.py:323).

**Minimal fix:** include required hardware identity in resume snapshots and segment records. Otherwise moved results can mix hardware-dependent measurements.

**P15 — Verification performed**

- Requested pytest command: **404 passed**, two warnings, **21.41 s**. Initial sandbox attempt failed before collection; the retry used the specified workdir temporary directory.
- Adjacent agent-loop suites: **29 passed**.
- Independent real Bash probes: **20 MiB output + 300 KiB script completed in 0.138 s**; 1.2 MB UTF-8 round-tripped; full-queue shutdown returned in **0.108 s**, with no surviving reader thread.
- Independent mocked probes: grading, malformed arguments, telemetry escalation, resume identity, timeout provenance, transcript counters, UNKNOWN classification, calibration failure and correction recommendations.
- Actual watcher discovery against reviewer-owned processes: **98.5% CPU → busy; 0.1% → idle**. This does not validate MLX inference thresholds.
- Compared **144 tasks, 19 scripts, license, corpus hash, prompt, tool schemas and round limit** against pinned upstream Git objects. Also consulted the supplied [upstream configuration](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/configs/tasks/os.yaml).
- Read the contract, four reviews, fix history, scoped implementation/tests, build script and corpus artifacts. Build-script syntax and added-line PII/model-name checks passed.

**AC1 is verified. AC3–AC5 retain blockers.** AC2, AC7 and AC9 have passing mocked coverage; actual Docker/image behavior remains unverified. Historical test-first commits exist. The existing exclusions artifact has rule v2, 144 dispositions, two exclusions and matching corpus/script hashes; live image identity was not checked.

No Docker execution, localhost:8000 contact, repository edits or commits. HEAD and the pre-existing untracked exclusions artifact remained unchanged.

**P16 — Pilot and full-arm gates**

**Fix before a five-item scoring pilot:**

- Grading classification and checker decoding: P8.
- Empty-argument protocol behavior: P10.
- Sentinel/UTF-8 separation: P11.

**Safe to carry into a supervised five-item pilot after those fixes:**

- Timeout filtering, with an independently justified explicit timeout.
- Resume hardware gap, using a fresh output without resume.
- Watcher calibration gaps, with known-active/known-idle validation during bring-up and no reliance on unvalidated WEDGE labels.
- Assessment gaps, with independently supervised watcher liveness and recorded operator assessments.

**Before corpus-wide arms:** close all remaining findings, validate actual container cleanup/image identity, and establish infrastructure-error recovery plus matched valid task coverage. Current resume skips every existing ID—including setup errors—and `graded_ids` merely records coverage; it does not enforce comparable arms. [Resume:808]($STACK_REPO/benchmark/bench/run_agentbench_os.py:808), [summary:422]($STACK_REPO/benchmark/bench/run_agentbench_os.py:422).
