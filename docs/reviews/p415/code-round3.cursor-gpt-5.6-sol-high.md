# P415 — code review round 3 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p369-v13` `ef956511`

Production check passed: `git diff 7207179b ef956511 -- mlx_vlm ':!mlx_vlm/tests'` is empty.

D5 — OPEN — `dev/p369_phase2/qualify.py:700-721,902-908,953-961`  
The console script is re-attested after jobs and at exit, but the exit attestation can raise instead of becoming an `end_problems` entry. If the script is deleted, truncated, or otherwise unreadable after the last job check, the final report retains `COMPLETED` entries despite the command failing. Convert attestation exceptions into exit problems and invalidate every completed entry before persisting the report.

D10 — CLOSED by the stated design — `dev/p369_phase2/qualify.py:69-118,736-750`  
The gate now requires an artifact beneath the campaign root, a sibling manifest with the same head, and a real fork commit containing reviewed v13. Combined with the existing production, phase, status, pick, and reviewed-head checks, this excludes stale, wrong, or unrelated summaries. Re-deriving the verdict is unnecessary under the stated single-operator, non-forgery threat model.

D11 — CLOSED — `dev/p369_phase2/qualify.py:510-532,812-833,890-894,985-993,1088-1121`  
Each reference blob must have existed at its named source path. The mandatory fingerprint now includes loaded snapshot revisions, digests of the complete worker-verified file-hash maps, and the reviewed fork commit.

D12 — OPEN — `dev/p369_phase2/qualify.py:456-464,916-920`; `dev/p369_phase2/orchestrate.py:1294-1339`  
The shorter stale threshold fixes the reproduced blocked-tick case, but monitor exceptions remain unrecorded and the liveness check is racy. A tick can be alive during the check, fail immediately afterward, and the final synchronous tick can succeed; the entry then remains `COMPLETED` despite a failed monitor tick. Store sticky tick start/completion/error state, stop and join the thread, and invalidate completed entries if any tick failed or remained incomplete.

D13 — CLOSED — `dev/p369_phase2/qualify.py:751-767`  
Lock release is now in an outer unconditional `finally`, covering report-writing and monitor-cleanup failures.

E1 — CLOSED — `dev/p369_phase2/qualify.py:890-894,1104-1111`  
The fingerprint consumes the real `{flag: revision}` snapshot schema, and the lifecycle test exercises that shape.

E2 — CLOSED — `dev/p369_phase2/qualify.py:788-793,973`  
The qualification installs the 600-second boot limit for `run_job` and restores the original orchestrator value during normal cleanup.

F1 — Medium — `dev/p369_phase2/qualify.py:916,1031-1034`  
Problem: `_pmset_log()` ignores the subprocess return code and stderr; empty or unparseable output is indistinguishable from “no battery intervals.”  
Failure scenario: `pmset -g log` fails during finalization after a short battery outage that both endpoint checks missed. `battery_intervals("")` returns empty and the entry is marked `COMPLETED`.  
Fix: require a successful command and parseable power-source history; treat command or format failure as `INVALID`. Add lifecycle tests for nonzero and unparseable output.

VERDICT: NOT CLEARED D5,D12,F1