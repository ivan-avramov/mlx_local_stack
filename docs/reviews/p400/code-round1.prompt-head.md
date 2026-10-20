Cold CODE review — ROUND 1 OF 3 (C186: at most 3 rounds, then the operator decides open findings; prioritise what must be
fixed before the re-certification GPU runs). P400 (operator-approved plan v4, C188) + the P401 hardening + P403, fork
`mlx-vlm` branch `p400-tq-width2` (local only, HEAD `d4150165`, off `3a92943d`). Workspace: the `mlx-vlm` checkout at
`24551869`; read with `git show d4150165:<path>` (read-only). Diff `3a92943d..d4150165` inline below (red tests first, then fixes).

Context: P400 — the `qwen3_5` verifier's length-2 shortcut (one batched masked SDPA) is not exact on TurboQuant KV under TF32
(this box's default numerics), so `Qwen3.8-27B-mlx-uniform-4bit`'s MTP was not lossless; fix A routes every length > 1 block
through the per-query loop. P401 — an unprimed warm prefill sliced suffix-local RoPE positions at the absolute cache offset
(short / empty arrays); `LanguageModel.__call__` now refuses that (equal-length block-local positions untouched; EpiCache
excluded → P402). P403 — the suite forces TF32 off; a conftest override + a test rerun every quantized exactness test under
TF32 on. Harness: TurboQuant leaf detection for both classes + a leaf census. Batched (B > 1) MTP is refused and falls back
to plain decoding (existing tests), so the left-padded multi-row TurboQuant verify path is unreachable under MTP (plan T1).

Review adversarially: (1) is the production change exactly the approved one (fix A + the P401 guard) and correct — any
remaining path that serves a > 1-query block on TurboQuant through a non-singleton call; any legitimate caller the P401 guard
now breaks (mRoPE 3-D, APC, canonical prefill, chunked prefill, speculative verify, Qwen4, batched offsets); (2) do the tests
prove the claims (red for the right reason, both numerics modes, codec / width assertions, the subprocess production-numerics
rerun really runs with TF32 on); (3) the harness changes (census, positives, codec metadata) — new defects; (4) the M58
scope-guard tests were rewritten to the new contract — is that faithful.

Findings ids C1 onward, each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line, the problem, a concrete failure scenario,
the fix. End with exactly one line: `VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
