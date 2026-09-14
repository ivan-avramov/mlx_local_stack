# Handoff — 2026-09-14: C84 runtime certification complete

Read this first, then `docs/PLAN.md` and `docs/open-questions.md`. Current report: [stack certification](stack-certification-2026-09-14.md). C84 bounded runtime checks are complete; C85's native16 tool-continuation OOM is resolved. Broader quality remains qualified below.

## Current state and publication

- Final installed gitlinks: MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`, MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`. Includes upstream MLX-VLM434afb1a / MLX-Servea6f80eb. Both forks were pushed to GitHub FIRST; submodules were fetched through their GitHub origins and committed here. Stack push was not requested and has not been performed.
- Main serving environment: MLX/Metal0.32.2, imports resolve to this stack's `src` submodules. All69 package versions were held fixed across the paired study. Startup retains committed gitlinks; no `--remote` update.
- All owned model/router/benchmark/grading processes are stopped. The daily-driver stack remains down. Verify PIDs/ports before launching anything; do not arm work from a historical runner file.
- `main_models.yaml` retains eight intentional local path overrides. NEVER stage its worktree copy. C84 comments were added through a HEAD-derived blob after all measurements; parsed registry values are unchanged. See `docs/qualify-a-model.md` for the technique.
- `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: native16 KV (`kv_bits: 0`), idle `cache_session_shrink: true`, repaired MTP ON, t0.5/medium. `Qwen3.8-27B-mlx-uniform-4bit`: unchanged TQ4, MTP ON, t0.6/medium. Both cap/preallocation262144 and prefill512 remain unchanged. B/C order remains operator-approved and unchanged.

## Verified results and interpretation

- Actual-stack full suites: VLM5372 passed,10 skipped,149 passing subtests; Serve106 passed; comparison/provenance119 passed; configgen check passed. Source/cache/instrument/result reviews are complete.
- Both final five-case smokes pass, six requests each. Native16 fresh tool pair also passes with zero prefix reuse. Three-turn native16 session returns READY/ORANGE/ORANGE; third turn reuses1839 tokens with49 new tokens. Positive MTP in final-answer serving probes. Tool handoff has its own bounded validation rather than normal-stop convergence.
- C85 mechanism: native logical trimming hid full storage behind short views; lazy compact copies and device-command references then retained old backing. Logical trimming and evaluated/synchronized retirement fix the observed failure. Earlier ownership cleanup remains a valid separate fix, but did not alone resolve the live OOM. Preserve six failed attempts and three passing controls in `benchmark/results/m43_c85_failure_history_20260914.json`.
- All80 quality requests complete and converge:40 exact BEFORE/AFTER pairs across Math500/HumanEvalPlus/MBPPPlus/prose, five items per axis/model. All40 AFTER answers, reasoning hashes and token counts match BEFORE. Native16 official scores5/5,4/5,5/5; second model5/5 on each. The shared native16 HumanEval/141 ASCII/Unicode prompt-reference failure remains official. Ten prose pair reviews tie; shared factual/methodological weaknesses are documented. One nonblinded reviewer, no external judge wave.
- Native16 request time668.6→680.8s; per-axis +1.2–2.5%. Second model821.4→822.9s; per-axis below1%. Report these small observed increases. Per-axis paired intervals are in the report and public analysis; they resample tasks, not repeated machine sessions.
- Matched largest native16 probe:261449 prompt/170 completion tokens, exact answer/reasoning equality, zero cache reuse, all five retrieval codes correct, main-request MTP67rounds/134draft/104accepted. Peak47.138620→47.155397GB (+0.017GB); prefill1099.88→1165.33s (+5.95%); decode11.9545→11.5061tok/s (−3.75%). One observation per state; causal attribution and repeatability unresolved. Two-token calibration intentionally ends by length without MTP. Final supervisor completed1185.9s/rc0.
- Capacity remains near the rough48GB guideline. It is NOT a strict46/48GB cutoff; numeric `fits`/memory-conditioned effective-context fields are not selection decisions or depth certification. The capacity daemon recorded real self-test/periodic/terminal events but lacked a baseline-rate estimate and retained generic smoke wording; fix this before reusing the wrapper.
- Certify this bounded runtime integration and retain native16/default order with the observed timing costs. Native16 broader depth/vision quality remains provisional. C84 starts from the initially merged e3bffd9a/f8f1df4 stack; it does not measure the original pre-merge integration effect or close C77.

## Evidence and reproducibility

Public results: `benchmark/results/m43_c84_quality_20260914.json`, `m43_c84_capacity_20260914.json`, `m43_c84_prose_review_20260914.json`, `m43_c85_failure_history_20260914.json`, per-model canonical rows/manifests/official grades, and `c84_export_20260914.provenance.json`. Only local paths were redacted; answers remain intact. Original/private and public byte hashes are distinguished.

Private root: `$STACK_WORKDIR/upstream/2026-09-14-activation`.

- Immutable BEFORE protocol/data: `quality`; completed AFTER amendment: `quality-v2`. Original unused5b after freeze is historical and must not launch.
- BEFORE freeze5716db4fc30e0ac458fa78b1aa8b6b006a0087f4bcf40e502f75a59c4daf3c11; AFTER freeze1a4e1d9be211e1e07a46a4b39cb17ead1e8a37d5ac59ef1cb18635c688944f53.
- AFTER finalization hashes: native16d5240ea70997488ee3b38acac95cb6a9432ee2e7d44da91cecbbbce90acfae44; TQ4f03efba6b8103627501bf070a2dfe71340b1b38365e74468983df2b040b54341.
- Analysis0958bad46e8492eed4eda0d26ae57b9588009cc9fe3132648fd4222815942d55; AFTER capacity summary71c7af139c284d1efe77962de5f4d8775ad3dc7ea32d250a435568108a872f53.
- Exact tested registry snapshots: `quality/registry-before.yaml` and `registry-after-tested.yaml`. Final certification comments changed current file bytes only. Do not compare historical exact-registry hashes blindly to the current file or rewrite historical manifests.
- Successful final serving evidence: `smoke-native16-eager`, `smoke-second-final`, `fresh-eager-tool`, `session-after`. `smoke-native16-final` is an earlier FAILURE, despite its name.
- Capacity data: `capacity` and `capacity-after`. Models were stopped through `runtime_control.py` after completion. All quality-screen code samples were graded using the pinned offline ARM64 container; never execute samples on the host.

## Queue and operator decisions

`docs/PLAN.md` is the only queue.

1. **M44 NEXT:** full HuggingFace published-model parity audit and model-card refresh, including historical models, insurance clones, MTP sidecars, vision assets, exact recommended settings and matching latest test provenance. Requested and queued; audit/upload work has not begun. Reconcile artifact-changing remediation before execution.
2. **C83 OPEN:** canonical capacity memory-policy/reporting cleanup; include generic capacity-monitor wording and baseline-rate estimation before reuse. Preserve historical raw flags.
3. **C76 OPEN:** M41 historical39-versus42 reasoning draw discrepancy; D14 uses verified39 and flags the older42 summaries. Do not pool unrelated M40 draws.
4. **C77/C78 OPEN, unarmed:** original pre-merge-versus-integrated quality/timing proposals need reshaping for the current native16 state. C84 does not substitute for C77; C78 can be reshaped to examine timing repeatability/mechanism if prioritized.
5. Broader native16 depth/vision quality remains provisional; no automatic ranking change. Whether to bring up the daily-driver stack and whether to push stack commits remain operator decisions. Fork pushes in C84 followed explicit GitHub-first authorization.

M40/M41, M42/C80/C82, P355/P356 and D14 are complete at their documented scope. M44 is the next queued campaign work, not another automatic GPU benchmark.

## Resume discipline

One resident model; APC absent; retained sessions2; full active preallocation; deployed sampling and explicit served-overlay environment. Verify flags on the actual worker. Never alter source/config during a live run; preserve real data and recorded failures. Commit coherent units; push only on explicit current-turn instruction. Discussion sequence continues after P580; next decision id C86.

Recipe reminders: pairwise judge requires `--out`; judge-gate output is a directory. Benchmark ladder CLIs require `--sampling-profile deployed`. Use real known-positive daemon monitors and derived request timeouts without retries. Read the current report before making quality, memory or publication claims from older handoff text.
