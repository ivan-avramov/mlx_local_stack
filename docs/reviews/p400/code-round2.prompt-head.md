Cold CODE review — ROUND 2 OF 3 (C186; prioritise what must be fixed before the re-certification GPU runs). Fork `mlx-vlm`
branch `p400-tq-width2` HEAD `78c9f99d`; your round 1 CLEARED `d4150165`. Workspace `../mlx-vlm` at `24551869`; read with
`git show 78c9f99d:<path>` (read-only). Diff `d4150165..78c9f99d` inline below. Production code is UNCHANGED since round 1
(`git diff d4150165 78c9f99d -- mlx_vlm ':!mlx_vlm/tests'` must be empty — verify); this round is tests, the dev harness and a
dev measurement tool.

What changed and why: (a) the P369 harness production pin moves to `da27f0ef` (P400 fix A + P401); (b) the P400 §5.3 ABBA
performance probe `dev/p400_perf_probe.py` (pre-registered statistic / bounds, tested pure parts); (c) GPU smoke 9 showed the
live `Qwen3.8-27B-mlx-uniform-4bit` KV cache is AFFINE `PreallocQuantizedKVCache`, not TurboQuant — a separate production
defect (P405: the server ignores `--kv-quant-scheme turboquant`; NOT fixed here) — so the P400 exactness tests now cover the
affine codec too (red on the pre-fix base structurally; the tiny fixture's affine L = 2 call is numerically exact, the live
divergence was shown on real weights), the harness gained an affine KV smoke positive (`quantized_scale`), and the smoke gate
derives the required KV positive from the E1c leaf census instead of the registry label; (d) a TurboQuant leaf-detection and
codec-metadata fix for both TurboQuant classes, plus the census.

Review adversarially: (1) does anything here weaken a claim (a positive that cannot fail, a gate that passes without the
evidence, a census that can be absent or wrong, the probe's statistic / bounds / leg binding); (2) correctness of the new
tests and whether they prove what their docstrings say; (3) anything that must change before the
`Qwen3.8-27B-mlx-uniform-4bit` re-certification on the new pin.

Findings ids C2 onward, each: severity, file:line, problem, failure scenario, fix. End with exactly one line:
`VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`. OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the
VERDICT line.
