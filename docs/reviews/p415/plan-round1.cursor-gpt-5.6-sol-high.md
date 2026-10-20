# P415 plan — Cursor plan review round 1 of 3 (gpt-5.6-sol-high, `--mode ask`), plan v1

Q1
- Severity: High
- Plan section: §2 Q1–Q2; §3 T2–T3
- Problem: Expectations are derived from `worker_argv` itself rather than independently from the registry. This is self-referential.
- Failure scenario: `_build_command` drops `--kv-quant-scheme turboquant`; `kv_from_argv` then defaults to uniform, the server serves affine, and the affine manifest matches—yielding `COMPLETED` for a TurboQuant registry entry.
- Fix: Establish a three-way check: independently parse each registry block → verify semantic argv fields → verify live runtime/manifest. Cover model path, KV settings, context/preallocation, prefill step, attention/lazy/shrink settings, generation defaults, drafter and verification policy for all seven entries.

Q2
- Severity: High
- Plan section: §2 Q2; §3 T3
- Problem: Runtime attestation covers only drafter, verification policy and KV fields. It does not prove other capacity-critical argv settings were honored.
- Failure scenario: Fable silently ignores `attention_policy: fused_v1`, lazy prompt embeddings, preallocation or prefill step size. It still loads, produces native leaves and 32 tokens, so it reports `COMPLETED` while measuring the wrong configuration.
- Fix: Attest live values or captured generation kwargs for every peak-relevant setting, including model identity, context cap, KV preallocation, prefill step, cache shrink, attention policy, lazy embeddings and memory limits. Add mismatch tests for each.

Q3
- Severity: High
- Plan section: §2 Q3; §3 T4
- Problem: The claimed prompt length comes from the dry-run sizing request. Existing probe machinery does not verify the measured request’s actual templated prompt or pin the peak-reset boundary in tests.
- Failure scenario: The measured path truncates, rerenders or otherwise processes a shorter prompt while the report still records 261,120. Alternatively, reset/capture ordering regresses but all four metrics remain finite and positive.
- Fix: Capture the measured request’s preprocessing IDs, count and digest; require exactly 261,120, the sizing digest, cached tokens zero and the expected backend. Add a mocked-stream sequencing test proving reset occurs before input preparation/prefill, prefill peak is read at first yield, and decode peak follows a second reset.

Q4
- Severity: High
- Plan section: §2 Q6; §3 T5
- Problem: The environmental safeguards are advisory or incomplete. `Monitor` only logs power, while `refused_process` deliberately permits `python -c` and misses some console-script worker forms.
- Failure scenario: Power falls below 140 W/28 V during prefill, or another MLX worker starts after preflight. The run still produces `COMPLETED` with contaminated peak/rates.
- Fix: Run a qualification-specific interference scan before every entry and during monitoring. Treat invalid power, process conflicts, monitor failure or unreadable state as entry failure. Test mid-request power drift plus `python -c`, console-script and late-starting worker interference.

Q5
- Severity: High
- Plan section: §2 Q5–Q6; §3 T7
- Problem: The specified continuation, cleanup and atomic reporting behavior is not backed by a process-lifecycle design. Existing probe legs use blocking `subprocess.run`.
- Failure scenario: Timeout raises instead of returning, SIGTERM leaves a child using the GPU, malformed/missing result JSON aborts the driver, or interruption leaves no terminal status for remaining entries.
- Fix: Use the orchestrator’s supervised process-group launch and extinction checks. Persist atomic state transitions for every entry, including `NOT_RUN` after interruption. Test load failure, transport exception, HTTP error, timeout, malformed result, SIGTERM, child extinction, continuation and final exit status.

Q6
- Severity: Medium
- Plan section: §2 Q1 and Q6
- Problem: Stack HEAD plus cleanliness of `main_models.yaml` does not bind the executable loader. The stack venv may import a dirty or stale editable `mlx-serve` submodule.
- Failure scenario: A local `_build_command` edit generates non-shipping argv while the report records the clean stack HEAD and registry hash. Registry changes during the run are also not explicitly guarded.
- Fix: Before every entry and at exit, guard stack HEAD and registry SHA; require the `mlx-serve` submodule HEAD to match the gitlink and be clean; verify the imported module path. Record Python, MLX/Metal versions and resolved model snapshot revision.

Q7
- Severity: Medium
- Plan section: §2 Q4; §3 T6
- Problem: Codec plus doc path/date is insufficient to establish reference-peak comparability.
- Failure scenario: A 261,449-token peak measured under different attention policy, preallocation, MTP state, MLX version or reset protocol is presented beside the new result as though codec were the only mismatch.
- Fix: Give each reference an immutable source locator/digest and full fingerprint: exact prompt length, code/MLX versions, MTP state, KV layout, attention/lazy/preallocation settings and measurement boundary. Compute deltas only for exact protocol matches; otherwise label them non-comparable.

Q8
- Severity: Medium
- Plan section: §4
- Problem: The 2–2.5-hour estimate has no preregistered boot, request or per-entry deadlines. Inherited long-leg timeouts can make continuing failures expand the run dramatically.
- Failure scenario: Seven entries each consume a six-hour inherited timeout, making the nominal 2.5-hour run approach 42 hours.
- Fix: Specify stage and per-entry hard deadlines, cleanup allowance and total worst-case wall time. Include timeout behavior in T7 and describe 2–2.5 hours as nominal rather than bounded.

VERDICT: DISAGREE Q1 Q2 Q3 Q4 Q5 Q6 Q7 Q8