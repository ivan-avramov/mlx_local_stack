**Verdict: FIX-THEN-SHIP.** Pytest was not run because its temporary-file fixtures require writes prohibited by this sandbox; review used source inspection and isolated, in-memory checks.

- **D1 — BLOCKING:** [run_reasoning.py:204]($STACK_REPO/.claude/worktrees/agent-a0c55413033380924/benchmark/bench/run_reasoning.py:204). A non-`--resume` run overwrites the sidecar but appends to the existing journal. Scenario: A produced several rungs; B changes KV/draft configuration, overwrites the sidecar, then fails before replacing every rung. A later B resume accepts remaining A rows because their design keys omit those controls. Previously successful rows can also be quarantined with B. **Fix:** refuse existing journals on non-resume, or create a separate journal/sidecar pair.

- **D2 — BLOCKING:** [run_opencode_probe.py:594]($STACK_REPO/.claude/worktrees/agent-a0c55413033380924/benchmark/run_opencode_probe.py:594). `_opencode_env()` itself creates nothing, but discovery launches opencode with the new data-home path **before** M50. The implementation and tests explicitly acknowledge opencode’s data-home writes; the tests stub discovery, so their zero-write assertions exclude the offending operation. A refused invocation can therefore create directories. **Fix:** use genuinely read-only discovery, or obtain an explicit operator exception to M50; the implementation comment cannot grant that exception.

- **D3 — BLOCKING:** [run_capacity.py:145]($STACK_REPO/.claude/worktrees/agent-a0c55413033380924/benchmark/bench/run_capacity.py:145). Capacity verifies before `gather()`, which subsequently reads sampling and registry provenance. If the overlay changes during gathering, the manifest can describe new settings while `router_exit` retains the earlier hash; `_verified` prevents another exit check. **Fix:** gather first, then verify immediately before publishing the manifest.

- **D4 — RESIDUAL:** [provenance.py:1278]($STACK_REPO/.claude/worktrees/agent-a0c55413033380924/benchmark/bench/provenance.py:1278). Stamping and renaming share one `try`. Malformed JSON or a failed drift-event append skips quarantine entirely, leaving the artifact at its canonical path. Reproduced in memory with malformed JSON. **Fix:** attempt quarantine independently even when stamping fails.

- **D5 — RESIDUAL:** [provenance.py:1293]($STACK_REPO/.claude/worktrees/agent-a0c55413033380924/benchmark/bench/provenance.py:1293). Warning prints are unprotected. With closed stdout, `BrokenPipeError` from logging replaces the original refusal; reproduced in memory. **Fix:** make cleanup diagnostics non-throwing, including the verification warning.

C1–C6 disposition:

- **C1:** Partial — compatible resumes work, but D1 defeats journal attribution.
- **C2:** Partial — both capacity artifacts normally quarantine; D4 remains.
- **C3:** Fixed — exact worker matching; another model, no worker, and unloaded on-demand models retain registry fallback when observation succeeds.
- **C4:** Partial — one discovery call and reordered preflights, but D2 remains.
- **C5:** Partial — ordinary exceptions propagate and trigger verification; D3–D5 qualify that guarantee.
- **C6:** Fixed — all three ladder entry checks precede their operational work.

Same-overlay router restarts are accepted and previous PIDs enter `router_history` ([run_reasoning.py:115]($STACK_REPO/.claude/worktrees/agent-a0c55413033380924/benchmark/bench/run_reasoning.py:115)). Missing/torn sidecars fail closed, sacrificing resumability. No normal-success or double-quarantine path was found. No current capacity-journal reader was found that the appended event breaks; normally it exists only in the renamed refused artifact.