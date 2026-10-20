Cold PLAN review — ROUND 1 OF 3 (C186: at most 3 rounds, then the operator decides open findings; prioritise what must change
before implementation). P400: a production fix in the fork `mlx-vlm` for an MTP exactness defect (TurboQuant KV × width-2
verify block). Workspace: the `mlx-vlm` fork checkout at `24551869`; the relevant code is in this repository's object store at
`p369-mtp` HEAD `3a92943d` — read with `git show 3a92943d:<path>` (read-only; modify nothing). Key files:
`mlx_vlm/models/qwen3_5/speculative_verifier.py` (`Qwen3_5BatchInvariantForward._attention`), `mlx_vlm/turboquant.py`
(`TurboQuantKVCache.quantized_attention`, `decode_attention`, `prefill_attention`), `mlx_vlm/models/qwen4_exp/language.py`
(subclass), `mlx_vlm/speculative/mtp.py` (the round loop, `_mtp_next_block_size`), `mlx_vlm/tests/test_mtp_exactness.py`
(`_quantized_pair`, the E1a tests), `mlx_vlm/tests/test_p369_phase2_observe.py` (the quantized E1c tests).

The proposal (inline below) states the measured defect, the confirmed root cause, fix options A / B / C (recommends A), the
tests, the sequencing around a GPU run in progress, and the acceptance criteria.

Review adversarially: (1) is the root-cause claim sound and complete — could another path still serve a length-2 (or any)
block non-exactly on TurboQuant KV after A (e.g. the left-padded path, the verify-policy path, DFlash / other drafters,
batched B > 1 verification, `qwen4_exp`)? (2) Is A correct and the best option vs B / C (performance, blast radius, upstream
divergence, other model families)? (3) Do the proposed tests catch the defect class (including the gap that hid it: no
TurboQuant KV in the exactness fixtures) and would they be red today for the right reason? (4) Is the re-certification scope
right (what must rerun for each pick on the new production pin; can the
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` full-run evidence carry over)? (5) Anything missing.

Findings ids T1 onward, each: severity (BLOCKER / HIGH / MEDIUM / LOW), the problem, a concrete failure scenario, the change to
the plan. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
