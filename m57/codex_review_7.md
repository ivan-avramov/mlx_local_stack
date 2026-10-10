**Y1 — Medium: T3 still permits false provenance.** Stack, [benchmark/bench/provenance.py:97]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/provenance.py:97).

`psutil.process_iter(..., ad_value=None)` converts per-process `AccessDenied` into `cmdline=None`. `_worker_cmdlines()` silently skips that process; `_resolve_control()` then treats the missing worker as permission to use registry values.

Concrete scenario: the serving worker’s argv is unreadable, it serves `auto`, and the registry declares `fused_v1`. The manifest records `fused_v1/source=registry`; neither observation failure nor disagreement raises. This leaves T3 incomplete. An in-memory check using the installed psutil implementation reproduced `AccessDenied → cmdline=None → []`.

**Fix:** establish expected worker identity independently through router ownership/worker PID information, and refuse when that live worker’s argv cannot be observed. Continue ignoring unrelated inaccessible processes and exited zombies. Test this per-process failure, not only an iterator that raises.

**Y2 — Probe state: no production regression identified.** Fork, [mlx_vlm/attention_policy.py:252]($HOME/ws/mlx-vlm/mlx_vlm/attention_policy.py:252) and [server/generation.py:1395]($HOME/ws/mlx-vlm/mlx_vlm/server/generation.py:1395).

The forward runs before request KV preallocation and session-cache population, using a fresh disposable cache. Recorder policies are restored in `finally`; real policy counters remain untouched. It does leave one-token `_position_ids` and zero `_rope_deltas`, so it is not literally state-free. The supported request paths supply fresh positional metadata, and speculative generation resets these fields. I found no resulting request contamination.

The startup thread has no active chunk profiler; the probe does not enter or suspend a generation iterator. A model lacking the required text forward/cache interface fails through `AttentionPolicyError` before READY.

Suspension is **per policy instance, per thread**. Both production scopes surround synchronous recursive calls without yields; pausing the outer generation iterator cannot strand their depth.

**Y3 — Serialization and driver compatibility: no additional defect identified.** Fork, [server/openai.py:637]($HOME/ws/mlx-vlm/mlx_vlm/server/openai.py:637); stack, [generate.py:318]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/generate.py:318).

Under `auto`, the helper’s unset counters are omitted; completions retain absent terminal timings. The widened union preserves existing `GenerationTimings` instances and permits the new streaming instance. No changed response bytes were identified in the touched shapes.

No-router and remote-URL refusals already occur at `generate.run` entry. Missing registry models still resolve to `unknown`; the new exception handling does not independently reject that case. Unrelated unreadable/zombie processes are skipped. Row migration, grading and comparison accept additional dictionary keys, so `row["sdpa"]` does not introduce an unknown-field rejection.

| Item | Assessment |
|---|---|
| G1 | **PASS** — named terminal shapes use the helper; tool-call stream without usage is tested. |
| G2 | **PASS** — instance-specific thread-local depth; nesting, exceptions and two threads covered. |
| G3 | **PASS** — derived limits equal `auto`; explicit override remains. |
| G4 | **PASS** — actual query dtype recorded; probe failures normalized; lifespan assertion specific. |
| T1 | **PASS** — detected disagreement/ambiguity propagates before requests and stamping. |
| T2 | **PASS** — unresolved controls are incompatible even with themselves. |
| T3 | **PARTIAL** — exact argv parsing works; inaccessible-worker observation remains conflated with absence (Y1). |
| T4 | **PASS** — raw timings retain counters; generated rows preserve them only when supplied. |

**Verdicts:** `mlx-vlm`: **SHIP**. Stack: **FIX-THEN-SHIP**.

Reviewed the specified commits, excluding uncommitted follow-ups. Validation was source review plus the isolated psutil check; supplied suite/live-gate results were not independently rerun.