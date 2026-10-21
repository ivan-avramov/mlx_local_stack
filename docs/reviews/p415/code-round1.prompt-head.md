Cold CODE review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). Fork `mlx-vlm` branch `p369-v13`,
range `3ae8770e..3b84a211` (`3f0743ed` red tests, `3b84a211` green), the P415 R7 256K qualification tool; workspace `../mlx-vlm` at
`24551869`, read with `git show 3b84a211:<path>` (read-only). Production code is UNCHANGED (`git diff 7207179b 3b84a211 --
mlx_vlm ':!mlx_vlm/tests'` must be empty — verify). Spec: plan v5 (`docs/specs/p415-r7-qualification.md`, STACK repo, inline
below; §2.5 = the operator's rulings C198 / C199 and wins over §2.1–§2.4). The stack's argv builder (`src/mlx-serve/src/mlx_serve/
process_manager.py` `_build_command`, mlx-serve `config.ModelConfig` defaults) is inline. The GPU-side hooks (worker mode
`qualify`) are exercised only by the coming GPU smoke; CPU tests cover the pure parts and the driver lifecycle.

Review adversarially against plan v5: (1) can an entry be COMPLETED for the wrong reason — the expectation derived from the
observed, a hook that observes the wrong call (the prefill / decode boundary before the first decode step or draft, the chunk
sequence, the prompt step, the prepared ids, the resolved arguments, the shrink as the retire boundary, lazy embeddings, KV leaf
capacity, memory limits), a check that passes vacuously; (2) does every error path fail closed and is the lifecycle sound
(lock, preflight, before / after checks, supervised job, atomic states, NOT_RUN); (3) will the GPU hooks work against the real
fork code at `7207179b` (signatures, positional vs keyword arguments, the MTP-ON path); (4) tests that pass for the wrong
reason. Findings ids D1 onward, each: severity, file:line, problem, failure scenario, fix. End with exactly one line:
`VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`. OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the
VERDICT line.
