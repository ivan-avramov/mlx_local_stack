**FAIL — M54 at `0390b17` still has scoring and protocol defects.** The requested suite passes, and several important regressions are fixed, but passing tests do not establish AC3–AC5 compliance.

**P46 — Verification of the previous findings**

“NOT” includes partial fixes. References are to the current checkout.

| Claim | Status | Evidence |
|---|---|---|
| P36 valid empty completions / token-count types | **CONFIRMED-FIXED** | EOS and reasoning-only `length` responses remain scored outcomes; invalid integer telemetry escalates. [client.py:111]($STACK_REPO/benchmark/bench/client.py:111). |
| P37 / P23 grading classification | **NOT** | Original examples are repaired, but application-controlled stderr and a model-damaged health-check dependency still cause exclusions. [agentbench_adapter.py:958]($STACK_REPO/benchmark/bench/agentbench_adapter.py:958). See P47. |
| P38 / P25 watcher | **NOT** | MacOS discovery, ancestry filtering and failed-`ps` UNKNOWN behavior work. Calibration can nevertheless succeed without any CPU observation; unreadable rows can crash the daemon. [agentbench_watch.py:77]($STACK_REPO/benchmark/bench/agentbench_watch.py:77), [calibration:751]($STACK_REPO/benchmark/bench/agentbench_watch.py:751). |
| P39 / P21 resume identity | **CONFIRMED-FIXED** | Missing/unreadable manifests, changed sampling/configuration hashes and changed harness/fork identities are rejected. Segments retain identity snapshots. [run_agentbench_os.py:298]($STACK_REPO/benchmark/bench/run_agentbench_os.py:298), [resume check:336]($STACK_REPO/benchmark/bench/run_agentbench_os.py:336), [segments:931]($STACK_REPO/benchmark/bench/run_agentbench_os.py:931). |
| P40 / P26 startup cleanup | **CONFIRMED-FIXED** | Failed discovery raises; both prepare and generate perform the sweep. Verified removal requires a successful absence check. [agentbench_adapter.py:404]($STACK_REPO/benchmark/bench/agentbench_adapter.py:404), [prepare:679]($STACK_REPO/benchmark/bench/run_agentbench_os.py:679), [generate:920]($STACK_REPO/benchmark/bench/run_agentbench_os.py:920). |
| P41 / P22 deadlock, bounded close, queue-thread leak | **CONFIRMED-FIXED** | Concurrent I/O and cancellation-aware queue operations passed real-Bash probes. No surviving reader threads in the completed cleanup checks. [agentbench_adapter.py:635]($STACK_REPO/benchmark/bench/agentbench_adapter.py:635), [close:878]($STACK_REPO/benchmark/bench/agentbench_adapter.py:878). |
| P42 confinement | **CONFIRMED-FIXED** | Default self-test files use the workdir; resumed transcript destinations are checked after resolution. [agentbench_watch.py:603]($STACK_REPO/benchmark/bench/agentbench_watch.py:603), [run_agentbench_os.py:896]($STACK_REPO/benchmark/bench/run_agentbench_os.py:896). |
| P43(a) / P29 evidence preservation | **NOT** | Shell-death, timeout and JSON-parse feedback are now saved. Unexpected grading exceptions still reset row counters; other actual feedback remains missing. [agentbench_adapter.py:1595]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1595). See P53. |
| P43(b) / P30 timeout evidence | **NOT** | Model/predictor filtering and source filenames exist, but box, KV/context, serving configuration and drift status remain unchecked. [run_agentbench_os.py:522]($STACK_REPO/benchmark/bench/run_agentbench_os.py:522). |
| P43(c) EOS pairing | **CONFIRMED-FIXED** | Finish reasons and token counts are paired by turn; the reported false-positive example now counts zero. [agentbench_watch.py:359]($STACK_REPO/benchmark/bench/agentbench_watch.py:359). |
| P43(d) / P32 assessments | **NOT** | Lifecycle timing and prediction ratios exist. The recommendation does not assess correction cost and can recommend FINISH with no evidence. [agentbench_watch.py:446]($STACK_REPO/benchmark/bench/agentbench_watch.py:446). |
| P24 telemetry escalation | **NOT** | Original missing/token-count cases escalate; malformed `finish_reason` types still become scored outcomes. [client.py:111]($STACK_REPO/benchmark/bench/client.py:111). See P50. |
| P27 malformed submit JSON | **CONFIRMED-FIXED** | Malformed JSON consumes a corrective turn, then a valid submission can succeed. [agent_loop.py:170]($STACK_REPO/benchmark/bench/agent_loop.py:170). |
| P28 UTF-8 compaction | **CONFIRMED-FIXED** | The 1.2 MB euro-sign reproduction passes. A separate sentinel-boundary bug remains: P51. [agentbench_adapter.py:731]($STACK_REPO/benchmark/bench/agentbench_adapter.py:731). |
| P31 named output paths | **CONFIRMED-FIXED** | Prepare-artifact and watcher-output confinement remain enforced. [run_agentbench_os.py:655]($STACK_REPO/benchmark/bench/run_agentbench_os.py:655), [agentbench_watch.py:762]($STACK_REPO/benchmark/bench/agentbench_watch.py:762). |

**P47 — HIGH, residual: grading still mistakes model-caused failures for infrastructure failures.**

Two independent mocked episodes became excluded `setup_error` rows:

- A failing application printed `OCI runtime is not the requested text`, while Docker was healthy. The prefix shortcut skipped the health probe.
- A model-damaged environment made the checker fail and made `bash -c true` fail. That does not prove a Docker infrastructure failure.

The existing tests explicitly endorse the prefix shortcut at [test_agentbench_adapter.py:244]($STACK_REPO/benchmark/bench/tests/test_agentbench_adapter.py:244).

**Minimal fix:** distinguish Docker exec creation/start failure from the checker’s execution and exit status using separate execution-status evidence. Treat model-damaged dependencies as scored failures. Quarantine genuinely ambiguous cases and require recovery plus matched task coverage before comparing arms.

**P48 — HIGH, residual: incompatible or invalidated measurements still size timeouts.**

I supplied a historical manifest with the correct model/predictor but a different box, different KV/context settings, a different configuration hash and `served_config_drift`. Its 100 tok/s row still produced **1,324 seconds for 102,400 tokens**, labelled `observable=True`.

Only model and `draft_kind` are checked at [run_agentbench_os.py:544]($STACK_REPO/benchmark/bench/run_agentbench_os.py:544).

**Minimal fix:** reject drift-marked evidence and require compatible hardware and serving identity, including context/preallocation/KV settings. Retain the contributing fingerprints alongside source filenames.

**P49 — MEDIUM, new: “upstream-faithful” argument extraction changes which answers pass.**

For `answer_action({"thought":"wrong","answer":"42"})`, the adapter selects `"42"` and passes. Pinned upstream takes the **first dictionary value**, `"wrong"`, and fails. Expected-key preference at [agentbench_adapter.py:1190]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1190) contradicts that behavior.

Unknown-tool feedback also differs: the adapter sends its generic available-tools message rather than upstream’s prescribed corrective text. [agent_loop.py:193]($STACK_REPO/benchmark/bench/agent_loop.py:193). Both differences are verifiable in the [pinned upstream implementation](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/src/server/tasks/os_interaction/task.py).

**Minimal fix:** reproduce positional extraction exactly and provide the upstream unknown-tool response through an M54-specific option.

**P50 — MEDIUM, new: malformed finish telemetry remains score-affecting.**

A response with valid usage but `finish_reason=17` passed the client boundary and produced a scored `no_submit`, with `bad_finish_reason`. This is malformed server telemetry, not a model failure.

**Minimal fix:** validate finish-reason type and supported values at [client.py:111]($STACK_REPO/benchmark/bench/client.py:111), alongside the existing token-count checks; escalate invalid responses.

**P51 — MEDIUM, new: non-ASCII output after a sentinel truncates the preceding result.**

A deterministic stream containing `ABCD`, the completed sentinel, then `€` returned **`AB`**, while correctly carrying `€` forward. The code subtracts a **byte count** from a decoded **character count** at [agentbench_adapter.py:764]($STACK_REPO/benchmark/bench/agentbench_adapter.py:764).

A background process can produce this ordering.

**Minimal fix:** separate command-output bytes from sentinel/trailing bytes before decoding; never trim decoded text using trailer byte length.

**P52 — MEDIUM, residual: watcher failure paths still overstate observation.**

Probes showed:

- An unreadable rows file raises `PermissionError`, escaping the daemon loop.
- Calibration with samples `[None, None]` exits **0**.
- No real MLX active/idle calibration is enforced before low CPU becomes `WEDGE`.

Discovery itself worked against reviewer-owned processes: **94.8% CPU → busy**, **0.3% → idle**. That validates the OS observation path, not its inference threshold.

**Minimal fix:** preserve read failures as UNKNOWN while keeping the watcher alive; fail calibration without valid observations; require recorded active/idle inference calibration before interpreting low CPU as a wedge.

**P53 — MEDIUM, residual: preserved transcripts and row telemetry still disagree.**

An unexpected grading exception after a 57-token submission produced:

- Saved transcript: one turn, 57 tokens.
- Row: **zero turns, zero tokens**.

Unknown-tool and tool-less corrective responses also remained `tool_result=None` despite being sent to the model. [agentbench_adapter.py:1238]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1238), [exception handling:1595]($STACK_REPO/benchmark/bench/agentbench_adapter.py:1595).

**Minimal fix:** retain actual loop counters on grading exceptions and capture feedback where the loop actually appends it, rather than reconstructing selected responses in the adapter.

**P54 — MEDIUM, residual: correction recommendations do not implement the standing cost question.**

The watcher recommended **FINISH with no rows and no prediction**. It also recommended CORRECT identically with 143 tasks remaining and one task remaining, without any correction-cost input.

**Minimal fix:** report UNKNOWN when evidence is insufficient; distinguish a detected problem from a justified intervention, and compare estimated correction/recovery cost against remaining work.

**P55 — What I ran and read**

- Requested suite: **377 passed**, two warnings, **21.24 s**.
- Adjacent agent-loop/client-driver tests: **25 passed**, **6.15 s**. Driver tests used their own ephemeral loopback HTTP fixtures.
- Real Bash: 20 MiB output plus 300 KiB script completed in **0.149 s**; 1.2 MB UTF-8 round-tripped; bounded shutdown, full-queue cancellation and reader termination checked.
- Independent mocked probes: grading, malformed arguments, telemetry escalation, resume identity, cleanup discovery, timeout provenance, transcripts, UNKNOWN/busy/idle states, calibration failure and assessment recommendations.
- Programmatically compared **144 task records, 19 scripts, corpus hash, prompt, tool schemas and round limit** against pinned upstream Git objects. All matched. Consulted the supplied [upstream configuration](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/configs/tasks/os.yaml).
- Read all three reviews, specified commit history, contract, implementation/tests, README and image-build script. Build-script syntax passed.

**AC1 is verified. AC3–AC5 retain substantive gaps.** Cleanup and confinement fixes passed the relevant mocked/local checks; actual Docker behavior, image identity and MLX calibration remain unverified.

No Docker execution, localhost:8000 contact, repository edits or commits. The pre-existing untracked exclusions artifact remains present.

**P56 — Pilot and full-arm recommendation**

**Fix before the five-item live pilot:** grading classification (P47), protocol differences (P49), malformed finish telemetry (P50), and sentinel UTF-8 handling (P51).

**Safe to carry into a tightly controlled five-item pilot after those fixes:**

- Timeout filtering, **only with an independently justified explicit timeout**.
- Missing transcript/counter details, with manual inspection of all five episodes.
- Incomplete correction-cost recommendations, with explicit operator assessments recorded alongside the daemon.
- Uncalibrated inference CPU thresholds, **only until known-active and known-idle calibration is completed during pilot bring-up**; do not act on WEDGE labels beforehand.
- Watcher read/calibration failure handling, only with independently supervised watcher liveness and readable inputs.

**Before 144-task arms:** close every residual above; establish infrastructure-error recovery and enforce matched valid task coverage for paired analysis. Merely recording `graded_ids` does not enforce that requirement.
