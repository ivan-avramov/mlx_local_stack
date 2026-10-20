# P369 phase-2 — Cursor gpt-5.6-sol-high micro-round 6 (smoke-7 import fix; fork `p369-mtp`, 2026-10-19)

Prompt: `round6-micro.prompt-head.md` + diff; `--mode ask`, stream-json — the `result` text verbatim:

E11 — Medium — `mlx_vlm/tests/test_p369_phase2_worker.py:876`  
Problem: The guard checks only whether loads fall within the importing block’s line span, not whether the import dominates the load; it also skips `fn.body`.  
Failure scenario: A load preceding its import in the same block—or a function-level import placed after a load—passes the test but raises the same `UnboundLocalError`.  
Fix: Check source order and control-flow dominance for every import binding, including function-body imports.

The current fix itself is correct; other worker imports are safe. Only the two shown files changed, and the production diff from `4e6d0e03` is empty.

VERDICT: NOT CLEARED E11