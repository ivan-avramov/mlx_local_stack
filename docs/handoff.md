# Handoff — 2026-09-14: C93 OpenWebUI reconciliation complete; stack stopped

Read this first, then `docs/PLAN.md` and `docs/open-questions.md`. Reports: [depth qualification](native16-depth-qualification-2026-09-14.md), [runtime/capacity](stack-certification-2026-09-14.md), [client audit](client-config-audit-2026-09-14.md).

## C93 complete — OpenWebUI deployment alignment

Operator approved P727. Existing configgen now emits `models_config.json` plus hash-bound `model_settings.json`; registry `agent_defaults.openwebui` selects the approved first pick. Shared startup/manual reconciliation sets the seven-main-model allowlist, separate task model, explicit thinking params and default/pinned selection. Candidate/router-only entries cannot leak through unrestricted router discovery. Stale managed registrations fail pending reviewed `--prune`; unrelated custom models/connections and existing access grants are preserved.

63 CPU tests passed, including the actual current API split between saved base and custom models. Live readback verified exactly8 visible entries, all model params, defaults and task routing. The installed payload transformer preserves all eight generated parameter sets; explicit chat overrides still win. No inference or model-server launch. The external stack was stopped during implementation; only OpenWebUI was temporarily started from its cached image for verification and stopped afterward. Settings persist for next startup. See `docs/openwebui-reconciliation-2026-09-14.md` and `openwebui-init/README.md`. Private backups/readback: `$STACK_WORKDIR/qualification/c93-owui`.

The earlier five commits were pushed through e7f58fb. C93 is a subsequent local commit; no push authorization this turn. The operator explicitly reverted all machine-local registry overrides: do not restore them. Model paths now use committed HF IDs; monitoring uses the default destination. The only new registry change is the public OpenWebUI default selector. Historical tested registry snapshots remain immutable. Both fork GitHub heads and installed pins match522671c4/b632280; a later read-only fetch found five newer MLX-VLM upstream commits through1ecf1ecd (v0.7.1), not merged or qualified.

## C89/C90 complete

C89 approved by P648: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, deployed native16/MTP-ON, t0.5/medium. Retrieval25/25 prompts and125/125 codes through128000; chain-4 tracking39/39 through156000. All64 converge with full81920 resolved budget, positive MTP and zero prefix reuse. Exactly66 actual HTTP calls including2 calibrations. Scored request wall2h49m; no new capacity or causal timing comparison. Final independent audit clear. Phase2 is CLOSED at the approved C84/C88/C89 measured scope; retain approved config/order and broader quality caveats.

All owned model/router/driver/readers stopped, including final router36301/worker36302/driver36767/reader36769. Ports8000/8091/8092 had no listeners at final verification. Daily-driver remains DOWN. Verify current PIDs/ports before any new lifecycle action; never launch a completed runner.

C90 complete in f5d71d3: OpenCode attachment/modalities/context/input/output corrected; main/bench files regenerated; four client READMEs updated. Aider/Zed/VSCode/OpenWebUI generated configs already matched.52 tests, generation checks and cold review pass. No installed personal config overwrite or new client end-to-end benchmark.

Private C89 root `$STACK_WORKDIR/qualification/c89-depth-20260914-v2`: raw wire files, frozen inputs, manifests, finalization receipt and public-complete export. Freeze0a2e1f9d8987c91cb72339ca8cee4bc45e5b3a5ae66b8703b20cf790267e12b1; protocol1b255de6c06735a300d29639b03809c363041f1fa3f88af0d66f886583788b5b; runnera05f928643952da670c528d5909efb12c909b72c8c7c966b625b1354ce57913e; exporteredac67fd432890888406ff85dc3d9bf5e384a7e5ea218bd71e7d152028b1abf0. Public final receipt `benchmark/results/c89_export_20260914.provenance.json` binds all7 exported files. All1781 frozen files verified before post-run registry changes. Recorded stackHEADbc66da863c2ac279aee2ce981f8bb0d9caa60d74.

Original root `$STACK_WORKDIR/qualification/c89-depth-20260914` is immutable:1 calibration HTTPcall,3210 prompt/2 reported completion tokens, null final content plus reasoning, length termination. Original validator aborted before scoring; v2 adopted the exact response without replay. Source inspection found C91 terminal-chunk reporting issue; source repair remains proposed, not armed. No universal historical token subtraction. Original default monitoring logs were written before detection and were not deleted.

Historical C89 checkpoint: after final audit, registry certification comments were updated using a clean HEAD-derived blob, with no parsed deployment changes. At that checkpoint, eight private model-path overrides remained unstaged. Local `monitoring.log_dir` pointed to `$STACK_WORKDIR/logs/mlx-serve` so future traffic cannot append to C89 evidence. Exact tested registry snapshot/hash22b6d91fa9f883484884c46f3d19502cc0c8c6b02e162d8f00933df77eb051b6 is retained; do not compare it blindly to post-run comments/log paths or rerun the exporter against changed live files. Those overrides were subsequently reverted by explicit operator request; do not restore them.

Publication: stack pushed and verified through e7f58fb6181156800b53d185547348e8d7b13176. C89 target/drafter HF updates remain PREPARED, not published (C92; `docs/huggingface-c89-prepared-2026-09-14.json`). C93 is local; new pushes require an explicit instruction.

## C88 COMPLETE: shipped-config vision smoke

- Operator narrowed qualification to `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` exactly as actual `main_models.yaml` declares. No TQ4 comparator, depth ladder or manual extraction grading. Existing20 images: description, then ground truth and the model's own PASS/FAIL.
- **20 PASS,0 FAIL,0 null; all40 turns converged, no runtime errors.** Random88 five-image pilot5/5 was included in20. Runner418.94s; known-positive selftest, pilot, periodic300s assessment and terminal exit0 recorded.36 CPU tests passed before launch; independent launch and final evidence reviews clear. All40 responses carry positive MTP counters.
- Native16/MTP ON, t0.5/medium, all registry sampling/cache settings preserved. Source522671c4/b632280, MLX/Metal0.32.2 verified; localhost listener ownership and worker model/drafter paths checked. Initial/final registry hashes and source/config fingerprints agree. Certification comments added only AFTER the run through a HEAD-derived blob; parsed YAML unchanged.
- Public rows/summary/provenance: `benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/vision_gate.c88-shipped-20260914.*`; response/hash evidence `benchmark/results/m43_c88_vision_20260914.json`. Private root `$STACK_WORKDIR/qualification/c88-vision-20260914`, freeze SHA2565db123772ee528fc4338ea6b62b98b835570d1ac657468f0f26584c979736c1b. Preserve wire files, registry-tested snapshot and manifests. Do not rerun this completed directory.
- Owned router25101, worker25102, driver25198 and tail watcher stopped. Daily-driver stack remains DOWN. Retain approved config/order. C77/C78 comparisons remain deferred. C89 subsequently completed; see the final checkpoint above.
- Stack publication through2f0c7ad completed. Operator then authorized the C88 HF updates and matching Git push. Both cards and new C88 evidence files are PUBLISHED and independently anonymously verified: targetf2b38a25, drafter41ee4495; all23 other file signatures unchanged. Canonical mirrors match readback; receipt `docs/huggingface-c88-update-2026-09-14.json`. Verify origin/main against HEAD on resume. Those local overrides were subsequently reverted by the operator.

## Latest approved work: C83/C76

- Operator approved P606: CPU-only capacity reporting/monitor cleanup, correction of historical M41 draw counts, then refreshed quality planning before GPU work. C83 and C76 are COMPLETE. No model calls, fork changes, registry settings or Hugging Face publication in this cleanup.
- C83 schema2 separates request completion, descriptive48GB target flags and bounded retrieval co-scores; numeric overrun never stops the grid. Malformed/failed requests remain unscored and abort with nonzero exit. Output collisions are refused; historical bulk rescore is retired. Capacity daemon performs known-positive selftest, periodic baseline/mean/max assessments and terminal reporting; monitor failures propagate. 94 relevant CPU tests pass; independent cold review clear. See `docs/specs/c83-capacity-reporting.md`.
- C76: M41 `reasoning.m41on.json` contains39 unique draws (six rungs×5, three×3), all score1.0, zero budget hits/errors. Active42-draw summaries corrected with dated note; all raw artifacts/provenance unchanged. SHA256a8524d48fac46bfb8134f35ddcd8b4777389f40ae94bf42f1aec2441e253827a.
- C88 completed under the narrowed shipped-config scope above; the earlier two-cache210-call proposal was superseded.
- Operator explicitly requested Push after727013d/a0e57c0 and clarified C88 vision scope2026-09-14: retain the same20-image description→ground-truth→model PASS/FAIL smoke. The proposal now removes manual visual grading and the replacement strict-pass metric; convergence remains diagnostic. That earlier turn authorized publishing the cleanup/planning commits and that clarification; the publication completed. Verify GitHub main against HEAD on resume. Local registry overrides were later reverted; that push did not arm a GPU study; subsequent C88 approval is recorded above.

## M44 completion and README cleanup

- C86/M44 COMPLETE: all13 public repositories (9 target/mirror models,4 MTP drafters) audited; authenticated enumeration found no private repos. Final full-byte audit read161,764,394,797 bytes/206distinctfiles:139 model/support files match (61LFS SHA256,78GitblobSHA1),46safetensorsheaders and18indexchecks pass. Original README/license/.gitattributes differences are separately recorded.
- Refreshed the stale local `Qwen3.8-27B-static-mixed-4bit` cache from548e7898 to the already-published vision artifactbe1aa462, preserving oldsnapshot/ref backup. Restored three missing local support files. No published weight/config/tokenizer/vision artifact was changed.
- All13 updated cards and dated evidence files are PUBLISHED on Hugging Face, fresh anonymously read back, and independently verified. All152 pre-existing non-README signatures remain unchanged. Full revisions/receipts: `docs/huggingface-audit-2026-09-14.json`; [human report](huggingface-audit-2026-09-14.md).
- Exact publishable mirrors live at `docs/model-cards/<full-model-name>/README.md` with their `evaluation/` files. Four former flat names are navigation redirects; never upload those stubs. Publisher tests29pass; artifact-tool7pass; card/content/binding/publication cold reviews clear.
- Cards correct old predictor/rank/memory/vision claims while preserving measured limitations. First-pick quantization accounting corrected to~4.98/152eight-bit modules from the old4.67/150 claim; only its registry COMMENT changed. Parsed deployed settings are unchanged.
- README reduced from178 to70lines (~4052 to~700words), with detailed per-language/session results and certification provenance preserved in `docs/model-recommendation-evidence.md`.
- Private audit root: `$STACK_WORKDIR/hf-audit/2026-09-14`. Preserve `remote`, baseline`local`, final`local-final`, cachebackup, reviewedcards, publicationplan/journals/readbacks. `publication/final-completed.json` is the final receipt; original `completed.json` records the initial13 commits, with small README-only follow-ups recorded separately. Publication is COMPLETE; do not rerun the publisher or overwrite its journal. No GPU models were loaded for M44.
- C87 remains OPEN: historical `Qwen3.8-27B-static-mixed-4bit` t0.4 recipe versus current registryt1.0. Saved15attempts included13returned/converged,12correct,2transporterrors; one t0.6 timeout is not nonconvergence proof. No registry tune change or promotion. Reconcile only if this historical candidate is prioritized.

## Current state and publication

- Final installed gitlinks: MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`, MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`. Includes upstream MLX-VLM434afb1a / MLX-Servea6f80eb. Both forks were pushed to GitHub FIRST; submodules were fetched through their GitHub origins and committed here. The operator authorized publishing stack main on2026-09-14 (P603); publication through6bdeac6 completed. New commits require a fresh explicit push instruction.
- Main serving environment: MLX/Metal0.32.2, imports resolve to this stack's `src` submodules. All69 package versions were held fixed across the paired study. Startup retains committed gitlinks; no `--remote` update.
- C89 is complete and its owned processes are stopped. The daily-driver stack remains down. Verify current PIDs/ports before any lifecycle action; do not launch historical runners or duplicate an active phase.
- `main_models.yaml` has no machine-local overrides after the operator-requested restore. C84 comments were added through a HEAD-derived blob after all measurements; parsed registry values are unchanged. See `docs/qualify-a-model.md` for the technique.
- `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: native16 KV (`kv_bits: 0`), idle `cache_session_shrink: true`, repaired MTP ON, t0.5/medium. `Qwen3.8-27B-mlx-uniform-4bit`: unchanged TQ4, MTP ON, t0.6/medium. Both cap/preallocation262144 and prefill512 remain unchanged. B/C order remains operator-approved and unchanged.

## Verified results and interpretation

- Actual-stack full suites: VLM5372 passed,10 skipped,149 passing subtests; Serve106 passed; comparison/provenance119 passed; configgen check passed. Source/cache/instrument/result reviews are complete.
- Both final five-case smokes pass, six requests each. Native16 fresh tool pair also passes with zero prefix reuse. Three-turn native16 session returns READY/ORANGE/ORANGE; third turn reuses1839 tokens with49 new tokens. Positive MTP in final-answer serving probes. Tool handoff has its own bounded validation rather than normal-stop convergence.
- C85 mechanism: native logical trimming hid full storage behind short views; lazy compact copies and device-command references then retained old backing. Logical trimming and evaluated/synchronized retirement fix the observed failure. Earlier ownership cleanup remains a valid separate fix, but did not alone resolve the live OOM. Preserve six failed attempts and three passing controls in `benchmark/results/m43_c85_failure_history_20260914.json`.
- All80 quality requests complete and converge:40 exact BEFORE/AFTER pairs across Math500/HumanEvalPlus/MBPPPlus/prose, five items per axis/model. All40 AFTER answers, reasoning hashes and token counts match BEFORE. Native16 official scores5/5,4/5,5/5; second model5/5 on each. The shared native16 HumanEval/141 ASCII/Unicode prompt-reference failure remains official. Ten prose pair reviews tie; shared factual/methodological weaknesses are documented. One nonblinded reviewer, no external judge wave.
- Native16 request time668.6→680.8s; per-axis +1.2–2.5%. Second model821.4→822.9s; per-axis below1%. Report these small observed increases. Per-axis paired intervals are in the report and public analysis; they resample tasks, not repeated machine sessions.
- Matched largest native16 probe:261449 prompt/170 completion tokens, exact answer/reasoning equality, zero cache reuse, all five retrieval codes correct, main-request MTP67rounds/134draft/104accepted. Peak47.138620→47.155397GB (+0.017GB); prefill1099.88→1165.33s (+5.95%); decode11.9545→11.5061tok/s (−3.75%). One observation per state; causal attribution and repeatability unresolved. Two-token calibration intentionally ends by length without MTP. Final supervisor completed1185.9s/rc0.
- Capacity remains near the rough48GB guideline. It is NOT a strict46/48GB cutoff; numeric `fits`/memory-conditioned effective-context fields are not selection decisions or depth certification. The historical capacity daemon recorded real self-test/periodic/terminal events but lacked a baseline-rate estimate and retained generic smoke wording. C83 now supplies a canonical capacity daemon; preserve the old wrapper as immutable evidence, not a reusable runner.
- Certify this bounded runtime integration and retain native16/default order with the observed timing costs. C89 separately passes bounded retrieval/chain-4 depth; C88 passes the shipped vision smoke. Broader native16 quality equivalence is not established. C84 starts from the initially merged e3bffd9a/f8f1df4 stack; it does not measure the original pre-merge integration effect or close C77.

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

1. **M44 COMPLETE.** Cards/evidence published and local parity verified. Remaining historical recipe discrepancy is C87, above; it did not authorize new GPU work or a sampling change.
2. **C83 COMPLETE:** schema2 reporting and capacity-specific daemon; preserve old raw flags and wrapper evidence.
3. **C76 COMPLETE:** active M41 summaries corrected to39 draws; no raw data changes or M40 pooling.
4. **C88 COMPLETE:** shipped-config20-image smoke20/20PASS. The previous native16/TQ4 depth/vision comparison is superseded.
5. **C89 COMPLETE:** retrieval25/25 through128000; chain-4 tracking39/39 through156000; all64 converge; final audit clear. No more calls authorized by this completed protocol.
6. **C77 OPEN, deferred:** original pre-merge quality diagnostic refreshed for final sources, TQ4 fixed in both runtime bundles. C84 does not substitute for C77. **C78 deferred:** old timing proposal must not launch unchanged; prioritize quality before repeatability/mechanism work.
7. Daily-driver startup and new pushes remain operator decisions. M44 publication is complete; C87 historical tuning remains deferred.

M40/M41, M42/C80/C82, P355/P356, D14, C84, M44, C83, C76 and C88 are complete at their documented scopes. C89 is complete at its approved scope; do not arm historical runners or infer approval for another GPU study from completed cleanup work.

## Resume discipline

One resident model; APC absent; retained sessions2; full active preallocation; deployed sampling and explicit served-overlay environment. Verify flags on the actual worker. Never alter source/config during a live run; preserve real data and recorded failures. Commit coherent units; push only on explicit current-turn instruction. Discussion sequence continues after P730; C83/C76/C88/C89/C90 complete. C87 and C91 remain open/deferred; C77/C78 deferred. C92 publication approval pending; C93 complete; next decision id C94. C91 repair proposal: `docs/specs/c91-terminal-token-accounting.md`. Daily-driver startup, push and C89 card publication remain operator decisions.

Recipe reminders: pairwise judge requires `--out`; judge-gate output is a directory. Benchmark ladder CLIs require `--sampling-profile deployed`. Use real known-positive daemon monitors and derived request timeouts without retries. Read the current report before making quality, memory or publication claims from older handoff text.
