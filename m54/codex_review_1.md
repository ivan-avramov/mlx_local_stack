**FAIL — M54 at `d09660f` is not ready for model comparisons.** Resume can mix incompatible evidence, infrastructure failures can affect accuracy, and command timeouts do not bound the whole command operation.

All line numbers below refer to **`d09660f`**, excluding uncommitted changes observed during review.

**P6 — Acceptance criteria**

| AC | Status | Evidence |
|---|---|---|
| AC1 corpus | **CONFIRMED** | 144 unique tasks; expected group counts; JSONL hash matches manifest. Loader preserves fields: `agentbench_adapter.py:140–147`. Pin/license/hash: `agentbench_os_v1.manifest.json:3–29`. All task configurations loaded successfully. |
| AC2 exclusions | **NOT** | Artifact validation trusts `complete` without checking task coverage or script identity: `agentbench_adapter.py:196–211`. State-check tasks receive one reference run, diverging from literal AC2: `:700–705`. |
| AC3 protocol | **NOT** | Schemas, prompt, eight-turn default and output wrapper match; however, the command timeout starts after blocking stdin writes: `agentbench_adapter.py:498–511`. Exit status 137 is incorrectly treated as timeout: `:517–518`. |
| AC4 driver | **NOT** | Entry guard correctly precedes requests: `run_agentbench_os.py:342–346`. Resume identity checks are insufficient (`:145–160`); exceptional exits bypass C106 (`:440–461`); pilot selection can be restricted to the corpus prefix (`:386–394`). |
| AC5 evaluation | **NOT** | Normal match/check chaining matches upstream: `agentbench_adapter.py:581–617`. Missing usage can count as converged (`:857–868`), and infrastructure evaluation failures become scored failures (`:614–615`). |
| AC6 tests | **CONFIRMED** | Docker/model/router seams are mocked; failing-test-first commits precede implementation fixes. Directly invoked 100 fixture-free pinned tests successfully. Full pytest execution was blocked before collection by sandbox temporary-file restrictions. |
| AC7 degrade | **CONFIRMED** | With the required router guard satisfied, missing corpus/Docker/images produce a separate skipped marker and exit 0: `run_agentbench_os.py:229–247,348–351`. |
| AC8 hygiene | **NOT** | Naming/PII diff validators passed; README and build-directory discipline exist. However, unrestricted `--out` and corpus-sibling writes permit artifacts outside approved roots: `run_agentbench_os.py:305–308,524–528`. |
| AC9 cleanup | **NOT** | Normal/exception cleanup and SIGTERM handlers exist, but removal errors and nonzero statuses are discarded: `agentbench_adapter.py:358–362`. Subsequent containers can start while previous ones survive. |

**Findings, ranked by severity**

**P7 — HIGH: Resume can relabel incompatible or invalidated rows as a valid run.**  
`run_agentbench_os.py:145–160,373–395,421–435,457–474`.

Resume checks only the registry **path**, accepting a changed hash, different model, changed corpus/exclusions, and even an existing `served_config_drift` marker. I reproduced acceptance of a drift-marked manifest with a different router PID and hash. With remaining tasks, `_write_manifest` replaces the old manifest; existing rows are then included in the new summary. Exceptions also bypass the exit guard because it is outside `finally`.

**Minimal fix:** require matching model/config/scaffold/corpus/exclusion fingerprints before accepting rows; reject drift-marked runs; preserve segment provenance; execute C106 verification on exceptional exits without masking the original exception.

**P8 — HIGH: PersistentShell’s timeout excludes the blocking write.**  
`agentbench_adapter.py:498–511,533–539`.

A command followed by sufficiently large script text can fill stdin while the shell is busy. The timeout clock has not started yet. A real Bash probe using a 50 ms timeout returned successfully after approximately **467 ms**. An indefinitely blocked reader can prevent reaching timeout enforcement entirely.

**Minimal fix:** establish the deadline before writing; use deadline-aware nonblocking writes, handling partial writes, followed by reads using the same deadline.

**P9 — HIGH: Infrastructure failures produce model-dependent accuracy changes.**  
`agentbench_adapter.py:383–387,475–477,611–615,921–933,987`.

Two reproduced cases:

- A mocked Docker evaluation failure with “Cannot connect to the Docker daemon” became `failed_tests`, `setup_error=False`, with no recorded error.
- Shell startup failure is ignored. A subsequent Bash action fails, but a direct correct answer can pass despite the same unusable environment.

**Minimal fix:** validate the startup handshake before calling the model. Distinguish Docker transport/execution failure from a checker’s legitimate nonzero result; preserve infrastructure diagnostics and apply the specified setup-error policy consistently.

**P10 — HIGH: Exclusion artifacts do not establish complete, current preparation.**  
`agentbench_adapter.py:176–211,242–244`; `run_agentbench_os.py:354–365`.

A document with matching hashes and `complete=True`, but **no golds or exclusions**, passes validation. Referenced script contents and `--scripts-root` are absent from the fingerprint, so changing a checker/reference script leaves the artifact accepted.

The D2 split is implemented as described in README: two `"1"`/`"2"` probes for gold-slot tasks, one exit-status probe for state-check tasks. That distinction is reasonable, but literal AC2 was not amended accordingly. Manual exclusions also precede the match exemption (`agentbench_adapter.py:680–685`).

**Minimal fix:** record and validate an exhaustive per-task disposition, hash referenced scripts and preparation policy, and reconcile AC2 with the approved split and manual-exclusion exceptions.

**P11 — HIGH: The required strict score is absent, and missing telemetry can certify convergence.**  
`run_agentbench_os.py:184–219`; `agentbench_adapter.py:843–871,968–989`.

A passing, non-converged row yields `acc=1.0`; no separate `acc_strict@budget` exposes the failure. This is acceptable for raw capability accuracy, but insufficient for the pre-registered ranking metric. Separately, `completion_tokens=None` with `finish_reason="tool_calls"` is classified as converged. Prompt counts, resolved budgets and the computed per-turn convergence vector are not retained in the row.

**Minimal fix:** retain raw accuracy, add strict accuracy and convergence reporting, reject/mark unknown incomplete telemetry, and persist enough per-turn data to audit or regrade convergence.

**P12 — HIGH: Output clipping does not bound host memory.**  
`agentbench_adapter.py:465,479–486,508–546,813`.

The reader queue and accumulated byte buffer are unbounded. The 800/780 clipping happens only after command completion. A command such as `yes`, or a continuing background writer between turns, can accumulate enormous output in the host process despite the container’s memory limit.

**Minimal fix:** continuously drain output while retaining only the necessary display prefix and bounded sentinel-search state; bound inter-turn buffering as well.

**P13 — MEDIUM: A complete final row without a newline is silently lost on resume.**  
`run_agentbench_os.py:65–89,93–118,373–395`.

I reproduced a file containing completed rows A and B, with no final newline. `read_rows` includes B in `done_ids`; the next append truncates B. B is then neither rerun nor retained.

**Minimal fix:** normalize the tail before computing completed IDs. Preserve valid final JSON by adding a newline; truncate only an invalid final fragment.

**P14 — MEDIUM: Removing the episode cap did not remove the inherited client cap.**  
`run_agentbench_os.py:251–274,401–413`; `budget_timeout.py:82–107`.

For an 81,920-token budget at 5 tok/s, the helper returns **7,200 seconds**, although budget-only decoding requires **16,384 seconds**. Its `budget_observable=False` result is discarded. Multiplying this capped timeout by eight does not solve premature per-turn abandonment.

**Minimal fix:** derive from maximum generation plus headroom; refuse an inadequate bound rather than silently accepting it, and retain the derivation and observability fields in provenance.

**P15 — MEDIUM: Sentinel handling changes recoverable command behavior.**  
`agentbench_adapter.py:517–519,808–812`.

The real Bash command `(exit 137)` returned promptly with a valid sentinel but was marked timed out, causing episode termination. A command’s exit status is not evidence that this harness’s deadline fired. Invalid UTF-8 is also replaced character-by-character, whereas upstream emits its decode-error message.

**Minimal fix:** determine timeout from deadline expiry, preserve exit status independently, and reproduce upstream decoding behavior. Upstream command/output handling is in the pinned [task implementation](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/src/server/tasks/os_interaction/task.py).

**P16 — MEDIUM: Cleanup attempts are treated as cleanup success.**  
`agentbench_adapter.py:330–362,997–1000`; `run_agentbench_os.py:315–330`.

If `docker rm -f` fails or times out, the failure disappears and execution can proceed to another container. SIGTERM similarly exits after an unchecked removal attempt.

**Minimal fix:** check removal status and verify absence; stop subsequent work when removal cannot be established, preserving both cleanup and original errors.

**P17 — MEDIUM: Combining pilot and limit selects from the easy prefix.**  
`run_agentbench_os.py:386–394`.

`--limit 5 --pilot-seed 42 --pilot-n 5` selects exactly the first five eligible tasks. The later set-based filtering also discards shuffled execution order.

**Minimal fix:** draw from the full eligible corpus before limiting, or reject the combination; preserve the sampled order.

**P18 — MEDIUM: Malformed successful HTTP responses can become graded failures.**  
`client.py:57–70`; `agent_loop.py:125–134`.

A mocked HTTP-200 error envelope became an empty completion rather than an exception. Repeated responses exhaust the turn cap and become a scored failure. Ordinary raised HTTP/connection exceptions do escalate correctly.

**Minimal fix:** validate the response envelope, choices and required telemetry at the client boundary; escalate invalid server responses.

**P19 — MEDIUM: Output paths are not confined to approved roots.**  
`run_agentbench_os.py:242–245,305–308,524–528`.

For example, `--out /tmp/m54.jsonl` permits rows, manifests and summaries outside the repo and `$STACK_WORKDIR`.

**Minimal fix:** validate resolved output and preparation-artifact paths against the permitted roots before creating directories or files.

**P20 — Verification performed**

- **Executed:** 100 fixture-free tests loaded directly from `d09660f`; file-free reproductions above; real local Bash probes for split UTF-8, stdin reads, shell death, exit status, background output and blocked writes; corpus count/hash/configuration checks; naming/PII diff validators; build-script syntax check.
- **Read/compared:** specified commit history and feature/fix stats; pinned implementation/tests; upstream [tool schemas and round limit](https://raw.githubusercontent.com/THUDM/AgentBench/d1e4a10db08c87075c78972e48ecc182be03e2d5/configs/tasks/os.yaml), system prompt, match stripping, chained checker arguments, reference substitution, clipping and re-prompt behavior.
- **Not verified dynamically:** full pytest suite, actual Docker lifecycle, images, or model serving. Pytest failed before collection because temporary files were forbidden. No files were modified, no Docker command was executed, and no model server was contacted.
