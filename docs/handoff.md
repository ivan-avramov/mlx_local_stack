# Handoff — 2026-09-14: C84 stack certification in progress

Read this first, then `docs/PLAN.md` and `docs/open-questions.md`. C84/C85 remain active under `docs/specs/c84-stack-certification.md`. Fork publication is explicitly authorized; stack publication is not.

## Current source and runtime

- Stack commit `3a3d187`; GitHub-published and GitHub-fetched gitlinks: MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`, MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`. VLM includes upstream `434afb1a` plus ownership, logical-trim and eager-retirement repairs. Startup preserves committed gitlinks.
- Actual stack serving environment uses MLX/Metal0.32.2. All69 package versions remain pinned for the paired study. Imports resolve to this checkout's `src` submodules.
- `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships native16 (`kv_bits: 0`) and `cache_session_shrink: true`. Only idle padding is compacted; active cap/preallocation262144, weights, MTP and tune are unchanged. `Qwen3.8-27B-mlx-uniform-4bit` retains TQ4 and its unchanged registry entry.
- Eight intentional worktree registry path overrides remain. NEVER stage the worktree `main_models.yaml`; use the HEAD-blob technique in `docs/qualify-a-model.md`.
- At this checkpoint final second-model smoke is running; both final actual-stack unit suites and configgen checks passed. Verify PIDs/ports and private run state before GPU use; subsequent quality work may already be running.

## Verified C85 repair evidence

The original native16 tool continuation OOM was real. Fresh-tool controls reproduced it. Ownership cleanup alone, retirement setting alone, and logical trimming alone did not resolve it. Preserve those failed runs.

Native logical trimming had hidden full allocations behind short views. After that repair, retirement still created lazy copies holding the original backing. All three cache formats now evaluate and synchronize compact buffers before publishing replacement fields. Regression tests check immediate active-memory release without caller evaluation, exception safety, valid external aliases, exact prefixes and restoration of the full floor. Independent27 bounded MLX checks pass; final parent suite5372passed,10skipped,149subtests. Serve106passed.

**Actual-stack live retest at522671c4 passed:** all five native16 smoke cases/six requests, including the previously failing tool continuation and vision; all three growing-conversation requests pass with cache reuse on the third turn. MTP remains engaged. Final second-model smoke and paired quality/capacity measurements are still pending. Actual-stack full suite also passed5372tests,10skips,149subtests. This clears the observed continuation failure, not broader statistical quality equivalence.

## Paired study and preserved evidence

Private root: `$STACK_WORKDIR/upstream/2026-09-14-activation`.

- Original `quality` BEFORE protocol/data are immutable:40requests,20permodel, five each Math500/HumanEvalPlus/MBPPPlus/prose. All converge. Native16 official scores5/5,4/5,5/5; TQ4 scores5/5 on each mechanical axis. Shared historical HumanEval/141 prompt/reference mismatch remains an official failure. No prose quality score fabricated.
- BEFORE freeze `5716db4fc30e0ac458fa78b1aa8b6b006a0087f4bcf40e502f75a59c4daf3c11`; finalized native16 `3c4957515f67a5c569d358e32333d28872caeebf302d874ae55b4a059fa4a656`, TQ4 `4db8d0a71caff2265bd8265fc1a52a53a85aff4770b6ca2327a0c66b8d0679bf`. Archived exact registry and historical metadata code preserve old provenance.
- `quality-v2` supplies only40 AFTER requests; independent31 CPU checks clear. Prepared SHA `c58ff1f4cb2d12b3735e1bad4337736a99780f28f9d6ee40e4dfd8e83ef05e89`. Seal final522671c4/b632280 after final preflight; consult its README. Exact wire inputs and69 packages remain matched. Treatment includes the complete repair/upstream/retirement-policy bundle; do not attribute all differences to an isolated change. Original unused5b after freeze cannot launch this adapter.
- BEFORE largest-context control:261449prompttokens,47.138620204GB peak,1099.88s prefill,11.954545tok/s decode,170completiontokens, correct retrieval, zero cache reuse, positive MTP. Exact content/reasoning match C82. `capacity_probe_after.py` repeats the same calibration plus largest request into new `capacity-after`; use a fresh worker.
- Short smoke/quality memory is diagnostic only. Capacity evidence requires the long-context probe. Rough48GB is a guideline, not automatic rejection.

## Finish this authorized work

1. Verify final actual-stack unit/config/provenance checks and second-model five-case smoke.
2. Seal QA-v2 against final clean gitlinks. Run20 AFTER requests per model with fresh workers, actual overlay environment, explicit seeds, daemon300s monitoring, no retries. Finalize each before changing state. Grade code only in the reviewed offline ARM64 container; inspect paired prose directly.
3. Run fresh native16 calibration + exact largest-context control; compare quality, per-axis speed, full-context memory, correctness and convergence against preserved BEFORE evidence.
4. Independently review complete results; update README evidence, campaign results, PLAN, C84/C85 and this handoff. Commit coherent units with PII-redacted exports; no stack push.
5. Next queued project: M44 full HuggingFace artifact parity and model-card refresh. Other open items: C83 capacity-policy reporting, C76 M41 draw-count discrepancy, broader native16 quality/depth coverage. C77/C78 original pre-merge proposals need reshaping and remain unarmed. D14 transfer write-up is complete; incorporate final measured mechanisms.

## Resume safeguards

One resident model; APC absent; session count2; full active preallocation; deployed sampling and explicit served-overlay environment. Root owns lifecycle via private `runtime_control.py`. Verify worker flags and source SHAs. Never change config/source during a live arm. Current discussion sequence follows P539; next decision id C86.

## Historical campaign context

The following sections preserve completed earlier evidence and decisions. Statements about old activation/source state are historical and superseded by the current checkpoint above.

## Latest operator correction — C79

Memory is a **rough target around 48 GB MLX prefill peak at 256K**, not a strict 46 GB or 48 GB cutoff. Do not reject or stop evaluating a configuration solely for a small overrun. C79 supersedes C75's automatic memory-based M42 stop. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` with unquantized native16 KV completed normally at 47.1386 GB and remains a candidate. The earlier “OFAT ends; KV4 stays because memory failed” conclusion is withdrawn. The subsequently approved C80 pilot is now complete (below); this policy correction itself did not approve a deployment change.

Session audit and precision explanation: `docs/memory-guideline-audit-2026-09-13.md`. Only M42's native16 rejection was found to depend on the strict cutoff; all three capacity ladders completed every rung. Historical raw46GB flags are preserved and are not current eligibility decisions. Archived runners retain numeric 46 GB stop behavior: review before reuse; do not merely substitute a hard 48 GB cutoff.

## Source integration and environment

- C75 approved P359–P363: upstream integration, bounded compatibility/capacity validation, D14, P355 and P356. Expanded quality/judge work, activation, daily-driver startup and push remain separately scoped. Specification: `docs/specs/upstream-2026-09-13.md`, amended by C79.
- Parent MLX-VLM local main: tested merge `c5a6f97b` through upstream `45d6e125` (0.7.0), plus documentation-only `e3bffd9a`. Parent MLX-Serve main: `f8f1df4`, standing-rule documentation; upstream was already incorporated. Both parent trees are clean. Quality-first fork-maintenance rule is in both AGENTS files.
- Frozen experiment worktrees: `$STACK_WORKDIR/upstream/2026-09-13/{mlx-vlm,mlx-serve}` at `c5a6f97b`/`f8f1df4`. Do not mutate these validated sources casually.
- Original stack submodules remain `420c01e1`/`0ccc684`; original serving environment remains unchanged. Experimental `runtime-venv` uses MLX/Metal0.32.2 with original serving pins; `control-venv` uses old sources with MLX/Metal0.32.2. `venv` is the separate unit environment. All are under the experiment directory.
- Isolated `stack-validation` clone supplies truthful benchmark source/submodule provenance. Raw outputs remain there; redacted exports are in the original `benchmark/results`. No push was made.
- Both full MLX-VLM suites:5357 passed,10 skipped,149 passing subtests; MLX-Serve75 passed. Eight audits and supplementary lead reviews complete; independent source/cache reviews clear. Integration report: `docs/upstream-integration-2026-09-13.md`.

## Completed runtime measurements

- Both picks pass five old/new compatibility cases (six requests including tool continuation): arithmetic, executable Python, exact JSON, native tools and vision; final convergence and MTP counters positive. JSON reasoning changes while final answers remain correct. Both old-source/new-MLX controls reproduce original responses; unique numerical cause is not isolated. Third-turn session probe reuses1839 tokens correctly. These are screens, not statistical quality recertification.
- M43 tag `m43on-20260913`: both KV4 ladders complete. Actual prompts130783/196115/261449. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` peaks35.0058/37.3205/41.1029GB; largest-rung prefill1573.81s/decode6.28tok/s. `Qwen3.8-27B-mlx-uniform-4bit` peaks31.7408/34.0559/37.7970GB; largest-rung prefill1598.33s/decode6.15tok/s. P355 closed for the new-runtime shipped state.
- M42 tag `m42native16-20260913`: native16 KV peaks42.5220/44.8367/47.1386GB at the same actual prompts; prefill368.24/737.54/1114.00s, decode17.62/15.96/12.78tok/s. Complete, no errors. C79 keeps it eligible; C80 paired quality pilot is complete below. C81 subsequently approved native16 as the actual registry default; the stack is stopped.
- The historical KV4 arms used4-bit TurboQuant (`kv_quant_scheme: turboquant`, `kv_bits: 4`); C81 changed the first pick to native16 while the second retains TQ4; no3-bit arm ran. M42 changed only cache precision, preserving mixed-quantized weights and MTP ON. Native BF16 cache is expected, not directly instrumented; the whole model is not BF16.
- Long-prompt probes use bounded 256-token generation/thinking fields, with one calibration per ladder. Their retrieval co-signal is not a quality/depth certification. All source/config/prompt/manifest checks passed. Results: `docs/campaign-results.md`.
- KV4 instrument v1:65 fake tests, archived `instrument-v1`; byte-identical runner `capacity_runner_kv4_v1.py`, SHA `6d0182bb009bfdd595a39adb6acf0baa55af8ed4eb4a6f195ec678255b6df0fe`. M42 v2:133 fake tests plus independent review, archived `instrument-v2`; runner SHA `3bddbdbcadc2fac7472c94c9f6c3bdde41717d274496ab916e1f7a10714f17d7`. Child SHA unchanged: `ce86013b328ad4e89df7943a3dc18de87312a6b84601c3f1dbeaa97af85f3d0c`.
- Power correction: AC/battery both had powermode0; power source alone did not establish a performance confound. Charging concerned endurance. Historical M41 timing remains unpaired for other methodological reasons.

## Remaining work and decisions

- M42/C80 pilot COMPLETE: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 15 pairs /30 generations, five frozen tasks each Math500/HumanEvalPlus/MBPPPlus, TQ4 versus native16. Both states score 5/5,4/5,5/5 respectively; all30 converge, positive MTP, no paired outcome change. Official shared HumanEval/141 plus failure retained; recorded accented-filename counterexample exposes a prompt/reference mismatch, not a cache-specific regression. Five pairs per axis do not establish equivalence. Private instruments under `quality-pilot-c80`; public analysis `benchmark/results/m42_quality_pilot_2026-09-13.json`; spec `docs/specs/m42-quality-pilot.md`.
- C80 short-task wall233.2s TQ4 versus235.5s native16, tokens9716 versus10350. Native16/TQ4 mean per-request decode ratio1.090 [1.062,1.121], wall1.010 [0.875,1.128]; seed80,10000 paired bootstrap replicates, mixed-benchmark descriptive overview. More tokens offset faster decoding. Keep separate from the long-context roughly2.04× decode observation. C81 now approves native16 as the provisional recommendation AND registry default. Broader matched quality coverage remains pending; C82 completed the uniform8 comparison below and supports retaining native16.
- C77 OPEN:40 paired items/80 fresh generations across math/code/prose on both picks, old/new shipped MTP ON, roughly65.15 minutes historical generation-only plus loading/grading/tails. Frozen selection/spec: `docs/specs/m43-quality-diagnostic.md`. Not armed; no external judges. Refresh the first-pick cache scope after C81 before arming; its original TQ4 specification and historical cost estimate are not a current launch plan.
- C78 OPEN: two matched nominal131K timing requests plus two calibrations for the first pick, old/new sources both on MLX/Metal0.32.2, roughly15 minutes prefill before overhead. `docs/specs/m43-timing-control.md`. Not armed; hypotheses are not measured causes. Refresh the original first-pick TQ4 scope after C81 before arming.
- C76 OPEN: M41 raw reasoning artifact has39 draws and zero budget hits; older summaries say42. D14/audit use verified39 and flag the discrepancy. Do not pool separate M40 draws.
- D14 reviewed evidence report complete, updated through C82: `docs/transfer-findings.md`. P356 cosmetic cleanup complete; local registry certification comments restored without staging local paths.
- M44 QUEUED: full HF-published-model artifact parity audit and card refresh, including MTP companions, recommended parameters and tested vision abilities. Only PLAN is the queue; no audit/upload armed.
- C81 RULED: actual `main_models.yaml` default is native16 (`kv_bits: 0`) for the first pick; weights/MTP/tune unchanged. M40 all-axis certification used TQ4. Zero maps to quantization disabled with current KV_BITS environment absent; verify actual worker settings on next startup.
- C82 RULED: 15 fresh native16/uniform8 task pairs plus both three-rung capacity ladders, 38 generations total; `docs/specs/m42-uniform8-comparison.md`. All38 requests complete and independently audited. Native16 has lower measured peak and faster long-context prefill/decode at all three rungs; retain its actual default, provisional across broader quality axes.
- C83 OPEN: canonical capacity-policy/reporting cleanup; C82 raw retrieval_effective_ctx is memory-threshold-conditioned and is not an actual retrieval failure. Next C id C84. Discussion numbering continues at P518.

## Resume safeguards

1. Read current PIDs/ports and `quality-pilot-c82/active.json` plus `active-router.json` under the integration directory. Both quality and capacity experiments are complete; do not resume either automatically.
2. Preserve intentional `main_models.yaml` local-path overrides; NEVER stage its worktree copy. Use the HEAD-blob technique in `docs/qualify-a-model.md` when needed.
3. Inspect `git status` and `git log --oneline origin/main..main`; commit coherent units, but push only on explicit current-turn approval. No production submodule/environment activation yet.
4. One resident model, APC absent, retained sessions2, full-cap preallocation and explicit served overlay/deployed profile remain mandatory for approved future runs. Preserve raw data/provenance; policy changes do not justify relabelling historical measurements.

## Recipe notes that bite (kept from this session)

- `run_judge_pairwise` ALWAYS with `--out <dir>`; `judge_gate --out` is a DIRECTORY.
- Provenance jsons: the M41 runner redacts `$STACK_WORKDIR`/`$STACK_REPO`; older runners do not — sanitize before
  staging. Judge dirs commit with `--no-verify` after a by-hand piicheck (judge key `opus` false-positive, M38 <!-- allow-shorthand -->
  precedent d7f2d8c).
- The ladder CLIs REQUIRE `--sampling-profile` since ddb1e23 (`run_capacity_seq.sh` and the docs were updated).
- 5-item seeded pilots under-projected Math500 3.4× on pick B; the pilot is a lower bound.
- The reasoning ladder's `seed` selects the vartrack INSTANCE (5 items per rung), not the sampler — verified the
  instances differ; identical completion-token counts across draws are the fixed answer format, not copies.

C80 validation:85 fake tests passed, independent cross-reviews clear; known-answer native ARM64 grading control recognized13 positive and2 syntax-negative fixtures. Frozen plan SHA `18de6de537cc14c4052dd902e2fc55022511cf24ec4f881309e5c859e6fe5e0f`; instrument hashes/checks in private `quality-pilot-c80/prelaunch-checks.json`. Root-pinned completion evidence and canonical input hashes passed before grading. All official grading and independent score/interval checks complete. Full raw request/response evidence remains private; redacted rows/manifests/scores/full coding evaluator outputs/provenance are exported to `benchmark/results`. C81 subsequently approved the native16 registry default; C82 comparison is complete.

C82 preflight:102 generation +56 grading +27 capacity fake tests pass, independent reviews clear. Known-answer ARM64 grader control recognized13 positives and2 negatives. Frozen plan SHA `240ebeb38bea29867cb0a7a43427f387df434b0ce349959d7a2d405d7e84eaa8`; final instrument hashes in private `quality-pilot-c82/prelaunch-checks.json`. Constructor/tiny-tensor CPU check confirms16native/16uniform8 attention caches,48recurrent unchanged, group64 and full preallocation; no live-model dtype observation claimed. Old C80 evidence and first pre-review C82 freeze are preserved.

C82 final capacity audit: all four logical request payloads match across states, all six measured responses report zero prompt-cache reuse, and all three pairs have identical content/reasoning, completion counts209/234/170 and MTP counters. Native16 peaks42.521969452/44.836723538/47.138642770GB, prefill324.84/658.91/1063.47s, decode19.9858/16.2615/12.9479tok/s. Uniform8 peaks43.595711276/45.910465358/48.212384590GB, prefill441.39/941.52/1609.23s, decode11.1101/7.7286/5.6726tok/s. The observed native16 decode ratios are1.80/2.10/2.28, without repeatability intervals. Smaller calculated uniform8 KV backing did not reduce total measured peak; the responsible allocation was not isolated. Quality data: f136bba; uniform8 capacity:76870d9; final native16/comparison data accompany this handoff. All raw scorecard threshold-conditioned fields are annotated; C83 remains unarmed.
