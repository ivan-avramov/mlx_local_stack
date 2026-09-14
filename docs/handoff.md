# Handoff — 2026-09-13 (M43 upstream integration RUNNING; M40 + M41 COMPLETE)

Rewritten in place. Phase 1 closed (B ladder C57, C ladder C70). Phase 2: **M40 COMPLETE** (both picks certified
predictor-ON; C74 RULED), **M41 COMPLETE** (pick A capacity + depth ladders in the shipped ON state). M43 compatibility smokes and bounded controls have completed; the first new-runtime capacity ladder is running under the reviewed supervisor. Inspect the live-state files below before launching anything. Entries: `docs/campaign-results.md` 2026-09-13 (M41, M40 pick B, M40 pick A).

## Active integration — C75 (operator approved P359–P363)

- Specification: `docs/specs/upstream-2026-09-13.md`; M43 in PLAN precedes M42.
- Original stack submodules/serving environment unchanged. MLX-VLM integration branch `sync/upstream-2026-09-13` lives at
  `$STACK_WORKDIR/upstream/2026-09-13/mlx-vlm`; upstream target `45d6e125`. Integration commit `c5a6f97b` is unit/audit validated; both models pass old/new five-case smokes. Summary: `docs/upstream-integration-2026-09-13.md`.
- MLX-Serve upstream was already incorporated; standing-rule documentation commit `f8f1df4` is local and validated (75 tests).
- Environments: `venv` (unit) and `runtime-venv` (serving pins except MLX/Metal 0.32.2), both under the integration directory. Both full suites pass: 5357 tests, 10 skips, 149 subtests. Eight source audits pass; cold code/cache reviews complete.
- Live validation state: `$STACK_WORKDIR/upstream/2026-09-13/{active-router,active-capacity}.json`; inspect PIDs before any launch. All four primary smoke arms and one old-runtime repeat have finished. JSON reasoning differs while final answers match; both old-source/new-MLX controls reproduce original traces. Source numerical paths changed; C77 diagnostic proposal is pending. Daemon/summary under `smokes/<runtime>/<model>/`. Runner does not resume/overwrite. Raw old/new smoke data and worker/source/version evidence remain separate.
- Isolated stack-validation clone checks out integration commits for truthful driver provenance; original stack submodules and serving environment remain unchanged.
- Active capacity: tag `m43on-20260913`, first pick, fresh NEW router/worker. Supervisor and child passed 65 fake tests plus independent cold review. Logs, SELFTEST/assessments and terminal result: `capacity/<tag>/<model>/`; actual driver PID/environment captured there. Do not edit live runner/source/config. Next: second-pick capacity, then approved M42 fp16 capacity-first.
- Power constraint: battery power was observed during the first capacity ladder; the operator was asked to connect AC for remaining runs. Check `pmset -g batt` before the next arm. Power was not sampled at launch, so do not make source-only timing claims; local observation/log excerpts are in `evidence/power-observation.json`.
- Interim first-pick rung reports: 131072 → 35.005776684 GB, prefill 520.05 s; 196608 → 37.320530766 GB, prefill 1066.47 s. The 262144 request is running. These remain provisional until final token-count and manifest checks.
- M42 preflight follow-up: `M42_FP16_PREFLIGHT_DRAFT.md` under the integration directory proposes handling the router's omitted zero-bit flag and checking inherited `KV_BITS`. Apply/test/review only after the live runner exits; do not edit it in place during a run. The arm is unquantized native 16-bit KV (BF16 expected), not a forced IEEE fp16 conversion.
- C77 proposes 40 paired items /80 generations across math, code and prose, about 65 minutes historical generation-only plus overhead/tails. Exact frozen selection/spec: `docs/specs/m43-quality-diagnostic.md`. No diagnostic generation or external judge wave is armed.
- No push authorized. No production environment/submodule activation until validation.
- Discussion numbering continues at P410; C75 RULED; C76 OPEN (M41 draw-count correction); C77 OPEN (quality diagnostic); next C id C78.

## Resume checklist

1. **Box state**: M43 owns isolated validation processes as recorded above; inspect PIDs and ports before acting. M41 exited cleanly at 14:59. The daily-driver stack remains down; its startup is not part of C75.
2. `git status`: `main_models.yaml` carries intentional local-path overrides — NEVER stage it from the worktree
   (HEAD-blob technique; `docs/qualify-a-model.md`). The two committed M40 comment blocks have been restored locally. M43 documentation and evidence may be pending a coherent checkpoint commit.
3. Unpushed: `git log --oneline origin/main..main`. Push ONLY on explicit in-turn approval.
4. C75 approves the integration and bounded resumption above. The previous checkpoint decisions below are retained as context; P354/P355/D14/P356 now have a go within C75 scope.

## Queued operator request — P373

M44 in PLAN: full audit of all operator-published Hugging Face models against local artifacts, including insurance clones, MTP companions and vision assets; refresh model cards with matching latest test evidence, recommended parameters, MTP configuration and tested vision capabilities. Queued after current integration/resumption; not armed.

## Previous checkpoint proposals (2026-09-13 15:30; C75 disposition above)

- **P354 — M42 KV-lever OFAT: go, reshape, or skip.** M41 prior: 4.9 GB headroom at 262144 under turboquant kv4; fp16 KV
  on the 16 full-attention layers ≈ +12 GB → EXPECTED to fail the 46 GB gate at the cap. Recommendation: run the fp16
  PEAK LADDER FIRST (131K/197K/262K, one prefill each, <1 h) under the pre-registered rule "gate FAIL at 262144 ⇒ OFAT
  ends, kv4 stays"; spend the paired quality arms (hep/mbpp/Math500 item sets, decode/prefill @256K) only if fp16 fits.
  Skipping M42 entirely on this prior is defensible; the PLAN row carries the proposed shape.
- **P355 — coverage gap: `Qwen3.8-27B-mlx-uniform-4bit` (B/C 2nd) has NO capacity row.** Proposal: one capacity ladder
  in its shipped ON state (131K/197K/262K, ~1 h, same M41 runner with the M40 `on_Qwen3.8-27B-mlx-uniform-4bit.yaml`
  overlay, tag `m41on`). Its M11 depth rows exist (OFF, effort None — not the deployed medium tune).
- **D14 transfer write-up** (PLAN row; zero GPU; can run while the box is busy): needs a go. Inputs are complete:
  M40/M41 entries give the mechanism-vs-verdict split for the predictor and long-context axes.
- **Push**: unpushed commits on `main` (`git log --oneline origin/main..main`) — push only on explicit in-turn approval.
- **Daily-driver stack**: down since M40 started (2026-09-12 20:58). Bring up per AGENTS.md on request.
- **P356 — docs debt**: pre-existing lint failure `test_no_bare_distill_shorthand[qualify-a-model.md]`; the worktree
  `main_models.yaml` lacks the two committed `# CERTIFIED M40` comment lines (comments only). Both cosmetic.

## M41 result (full entry in campaign-results 2026-09-13)

`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ON: `mx.get_peak_memory` 35.0 / 37.3 / **41.1 GB** at 131K / 197K /
262144 (gate ≤46 PASS, 4.9 GB headroom); retrieval 1.0 at every rung to 128K; chain-4 reasoning 1.0 at every rung to
156K, **0/42 runaways**; decode 44.7 → 18.3 tok/s (8K → 156K), 10.7 at 262K; prefill 332 → 132 tok/s (131K → 262K,
~33 min TTFT at the cap). Mechanism: acceptance is task-stable (0.74–0.92) so the ON advantage grows with depth as
OFF decode collapses; prefill, not memory, is the depth-usability limit. Files `benchmark/results/<pick>/
{capacity_retrieval,retrieval,reasoning}.m41on.*` (+ manifests, provenance; data commit 2d09326).

## Next: M42 KV-lever OFAT on pick A (capacity-first approved C75)

Prior from M41: fp16 KV on the 16 full-attention layers ≈ +12 GB at 262144 → EXPECTED to fail the 46 GB gate at the
cap. Recommended shape: (1) fp16 peak ladder first (131K/197K/262K, one prefill each — minutes) with a pre-registered
rule "gate FAIL at 262144 ⇒ OFAT ends, kv4 stays"; (2) only if it fits, paired quality on the existing hep/mbpp/
Math500 item sets + decode/prefill at 256K. Tooling is ready: `bench.run_capacity --sampling-profile deployed
--out-tag <tag> --request-timeout 7200` with an overlay that sets `kv_bits: 0` for the pick (copy the M41 overlay,
edit, log its sha). Runner pattern: `$STACK_WORKDIR/queue/m41_ladders/run.py` (reviewed; reuse `_launch_and_wait`,
`assert_manifest`, `_redact_paths`).

## Recipe notes that bite (kept from this session)

- `run_judge_pairwise` ALWAYS with `--out <dir>`; `judge_gate --out` is a DIRECTORY.
- Provenance jsons: the M41 runner redacts `$STACK_WORKDIR`/`$STACK_REPO`; older runners do not — sanitize before
  staging. Judge dirs commit with `--no-verify` after a by-hand piicheck (judge key `opus` false-positive, M38 <!-- allow-shorthand -->
  precedent d7f2d8c).
- The ladder CLIs REQUIRE `--sampling-profile` since ddb1e23 (`run_capacity_seq.sh` and the docs were updated).
- 5-item seeded pilots under-projected Math500 3.4× on pick B; the pilot is a lower bound.
- The reasoning ladder's `seed` selects the vartrack INSTANCE (5 items per rung), not the sampler — verified the
  instances differ; identical completion-token counts across draws are the fixed answer format, not copies.

## Ladder of record (unchanged)

B (C57): 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`, 3rd
`Ornith-1.0-35B-mlx-uniform-4bit`, 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. C (C70, provisional): 1st
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`; shortlist
`Ornith-1.0-35B-mlx-uniform-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`. Dropped 2026-09-13 (C73):
`nex-agi/Nex-N2.5-mini`, `Agnes-AI/Agnes-3.0-Flash`.

## Bookkeeping

- P356 cosmetic shorthand lint was corrected in `a45dc26`; local registry comments restored without staging local paths.
- C76 remains OPEN: raw M41 reasoning rows contain 39 draws; older summaries say 42. D14 uses the verified 39 and flags the discrepancy.
