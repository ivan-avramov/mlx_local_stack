Cold CODE review ROUND 2 — the P369 phase-2 GPU worker-conformance harness (fork `mlx-vlm`, branch `p369-mtp`), the fix
round for your round-1 findings H1–H14.

Workspace: the `mlx-vlm` fork checkout at the base `24551869`; the branch commits are in this repository's object store —
read any file with `git show <HEAD>:<path>` (read-only; modify nothing). Production is pinned at `4e6d0e03`; the harness is
`4e6d0e03..<HEAD>` and touches ONLY `dev/p369_phase2/` and `mlx_vlm/tests/test_p369_phase2_*.py` (production diff empty —
verify). Round 1 reviewed `c10205ae`; this round's diff is `c10205ae..<HEAD>` (inline below), each fix red test first
(`test(dev): … red` commits name the failing ids; where a helper was absent the red is stated as such).

Lead decisions in this round (verify the code matches them; challenge them if wrong):
- H1: `ArraysCache.metadata_revision` is deliberately NOT hashed (a derived-metadata invalidation counter bumped by every
  speculative commit / abort, i.e. by every ON block and every probe; hashing it makes ON and OFF differ by construction);
  the effective `left_padding` / `lengths`, TurboQuant codec mode / kind / bits / `_snapshot_kv_codec` coordinates are hashed;
  an open transaction refuses.
- H2: expected families come from the production eligibility predicates (`quantized_verifier._can_optimized_affine_linear`,
  `supports_quantization`, the `exact_speculative_verify_weight` guard replicated with its source named) for a B = 1 verify
  block; fallbacks pass only where the predicates expect them (e.g. dense GDN `in_proj_a` / `_b` decline the dense kernel by
  shape: K ≥ 16·outputs); on-path coverage = `model.layers.*` + the head.
- H3: the worker env is an allowlist (mlx-serve spawns the worker with the router's inherited env; the deployed tuple is in
  the argv, incl. `--generation-defaults`).
- H6: the C84 bundles store prompt COUNTS only, so the link to the original runs stays count-based (disclosed); the digest
  binds every E2 / E7 request to this run's reconstruction.
- H7: production never calls `_append_session_assistant_hash`, so a session's `turn_hashes` are the last request's message
  hashes; continuity is checked at token level against `PromptCacheState.token_ids` (the new prompt must reproduce the
  cached sequence, which must hold generated tokens, and reuse must reach its end − 1); the echo carries `reasoning_content`
  (both picks' templates re-render it by default).
- C184 (operator ruling, after round 1): NO default campaign wall limit (`--wall-limit-s` is an explicit operator option);
  the per-request watchdogs (deadline = max tokens / floor decode rate + headroom) are the only automatic stops; each pick's
  step results reach `summary.json` as each step finishes.

Review adversarially: (1) for EACH of H1–H14, is it RESOLVED, PARTIALLY RESOLVED or NOT RESOLVED — cite the code; (2) any
NEW defect the fixes introduced (patch / restore symmetry, the supervisor's kill / timeout paths and child processes, the
nested telemetry wrapper's frames, the censoring relaunch indices, the binding fields, the lock reclaim race, determinism
and orphan processes in the new tests, the heartbeat files vs the clean-tree check); (3) anything that could still let a
run PASS without establishing the claim, or report a harness failure as an MTP finding.

Findings ids H15 onward (re-cite H1–H14 by id when not resolved), each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line,
the problem, a concrete failure scenario, the fix. End with exactly one line: `VERDICT: CLEARED` or
`VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
