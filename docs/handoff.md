# Handoff — 2026-09-13: local upstream merge landed; C80 cache pilot complete

Read this first, then `docs/PLAN.md` and `docs/open-questions.md`. **C80 is COMPLETE: 30 generations graded; all model/router/driver processes stopped and port8000 has no listener.** The daily-driver stack remains down. State: `$STACK_WORKDIR/upstream/2026-09-13/quality-pilot-c80/active.json`; verify actual PIDs/ports on resume. C81 now sets the first pick's actual registry default to native16 (`kv_bits: 0`, provisional). No new GPU work, runtime activation or push is armed.

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
- KV4 means4-bit TurboQuant (`kv_quant_scheme: turboquant`, `kv_bits: 4`) for both current picks; no3-bit arm ran. M42 changed only cache precision, preserving mixed-quantized weights and MTP ON. Native BF16 cache is expected, not directly instrumented; the whole model is not BF16.
- Long-prompt probes use bounded 256-token generation/thinking fields, with one calibration per ladder. Their retrieval co-signal is not a quality/depth certification. All source/config/prompt/manifest checks passed. Results: `docs/campaign-results.md`.
- KV4 instrument v1:65 fake tests, archived `instrument-v1`; byte-identical runner `capacity_runner_kv4_v1.py`, SHA `6d0182bb009bfdd595a39adb6acf0baa55af8ed4eb4a6f195ec678255b6df0fe`. M42 v2:133 fake tests plus independent review, archived `instrument-v2`; runner SHA `3bddbdbcadc2fac7472c94c9f6c3bdde41717d274496ab916e1f7a10714f17d7`. Child SHA unchanged: `ce86013b328ad4e89df7943a3dc18de87312a6b84601c3f1dbeaa97af85f3d0c`.
- Power correction: AC/battery both had powermode0; power source alone did not establish a performance confound. Charging concerned endurance. Historical M41 timing remains unpaired for other methodological reasons.

## Remaining work and decisions

- M42/C80 pilot COMPLETE: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 15 pairs /30 generations, five frozen tasks each Math500/HumanEvalPlus/MBPPPlus, TQ4 versus native16. Both states score 5/5,4/5,5/5 respectively; all30 converge, positive MTP, no paired outcome change. Official shared HumanEval/141 plus failure retained; recorded accented-filename counterexample exposes a prompt/reference mismatch, not a cache-specific regression. Five pairs per axis do not establish equivalence. Private instruments under `quality-pilot-c80`; public analysis `benchmark/results/m42_quality_pilot_2026-09-13.json`; spec `docs/specs/m42-quality-pilot.md`.
- C80 short-task wall233.2s TQ4 versus235.5s native16, tokens9716 versus10350. Native16/TQ4 mean per-request decode ratio1.090 [1.062,1.121], wall1.010 [0.875,1.128]; seed80,10000 paired bootstrap replicates, mixed-benchmark descriptive overview. More tokens offset faster decoding. Keep separate from the long-context roughly2.04× decode observation. C81 now approves native16 as the provisional recommendation AND registry default. Broader matched quality coverage remains pending; C82 proposes a uniform8 comparison, not armed.
- C77 OPEN:40 paired items/80 fresh generations across math/code/prose on both picks, old/new shipped MTP ON, roughly65.15 minutes historical generation-only plus loading/grading/tails. Frozen selection/spec: `docs/specs/m43-quality-diagnostic.md`. Not armed; no external judges.
- C78 OPEN: two matched nominal131K timing requests plus two calibrations for the first pick, old/new sources both on MLX/Metal0.32.2, roughly15 minutes prefill before overhead. `docs/specs/m43-timing-control.md`. Not armed; hypotheses are not measured causes.
- C76 OPEN: M41 raw reasoning artifact has39 draws and zero budget hits; older summaries say42. D14/audit use verified39 and flag the discrepancy. Do not pool separate M40 draws.
- D14 reviewed evidence report complete, updated for C79/C80: `docs/transfer-findings.md`. P356 cosmetic cleanup complete; local registry certification comments restored without staging local paths.
- M44 QUEUED: full HF-published-model artifact parity audit and card refresh, including MTP companions, recommended parameters and tested vision abilities. Only PLAN is the queue; no audit/upload armed.
- C81 RULED: actual `main_models.yaml` default is native16 (`kv_bits: 0`) for the first pick; weights/MTP/tune unchanged. M40 all-axis certification used TQ4. Zero maps to quantization disabled with current KV_BITS environment absent; verify actual worker settings on next startup.
- C82 OPEN: 15 fresh native16/uniform8 task pairs plus both three-rung capacity ladders, 38 generations total; `docs/specs/m42-uniform8-comparison.md`. No implementation or launch yet.
- Next C id C83. Discussion numbering continues at P474.

## Resume safeguards

1. Read current PIDs/ports and `quality-pilot-c80/active.json` plus `active-router.json` under the integration directory. Both quality and capacity experiments are complete; do not resume either automatically.
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

C80 validation:85 fake tests passed, independent cross-reviews clear; known-answer native ARM64 grading control recognized13 positive and2 syntax-negative fixtures. Frozen plan SHA `18de6de537cc14c4052dd902e2fc55022511cf24ec4f881309e5c859e6fe5e0f`; instrument hashes/checks in private `quality-pilot-c80/prelaunch-checks.json`. Root-pinned completion evidence and canonical input hashes passed before grading. All official grading and independent score/interval checks complete. Full raw request/response evidence remains private; redacted rows/manifests/scores/full coding evaluator outputs/provenance are exported to `benchmark/results`. C81 subsequently approved the native16 registry default; C82 test expansion remains proposed.
