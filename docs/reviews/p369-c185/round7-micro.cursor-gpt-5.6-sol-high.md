# P369 phase-2 — Cursor gpt-5.6-sol-high micro-round 7 (smoke-7 import fix; fork `p369-mtp`, 2026-10-19)

Prompt: `inline confirm (E11)` + diff; `--mode ask`, stream-json — the `result` text verbatim:

E11 — RESOLVED. The guard checks all four import statements and reports `bad=[]`. No loop can reach an imported-name use before its import: notably, the loops at `worker.py:1064` and `:1226` execute imports at `:1218`/`:1252` before uses at `:1221`/`:1259`.

Production code is unchanged from `4e6d0e03`; `ccac74c4..b397d610` changes only the test file.

E12 — Medium — `mlx_vlm/tests/test_p369_phase2_worker.py:885`  
Problem: The negative test reimplements fragments of the predicate instead of exercising the guard at `:843`. It also differs by collecting every `ast.Name`, not just loads.  
Failure scenario: The real guard could regress to its previous span-only check while this negative test continues passing. A later before-import use would then escape detection.  
Fix: Extract one AST-checking helper and invoke it for both `worker.run_job` and the synthetic negative cases, asserting exact violations.

VERDICT: NOT CLEARED E12
---

Lead (2026-10-19): E12 fixed (test-only, fork `3a92943d`: one shared `import_violations` helper, exact-violation negatives); the Cursor loop stopped here — the reviewed-head decision goes to the operator.
