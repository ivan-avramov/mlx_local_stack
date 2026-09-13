# Handoff — 2026-09-13 ~15:15 PDT (M41 COMPLETE; box idle; M42 awaits a go)

Rewritten in place. Phase 1 closed (B ladder C57, C ladder C70). Phase 2: **M40 COMPLETE** (both picks certified
predictor-ON; C74 RULED), **M41 COMPLETE** (pick A capacity + depth ladders in the shipped ON state). Nothing is
running. Entries: `docs/campaign-results.md` 2026-09-13 (M41, M40 pick B, M40 pick A).

## Resume checklist

1. **Box state**: expect NOTHING running (`pgrep -fl 'mlx_vlm.server|mlx-serve|run.py|bench.run_'` → empty). The
   M41 runner exited cleanly at 14:59 (worker unloaded, 0 listeners). Daily-driver router: start per AGENTS.md if
   the operator wants the stack up (it is down).
2. `git status`: `main_models.yaml` carries intentional local-path overrides — NEVER stage it from the worktree
   (HEAD-blob technique; `docs/qualify-a-model.md`). NOTE: the worktree copy predates the two `# CERTIFIED M40`
   comment lines at HEAD (comments only; harmless). No untracked result files should remain.
3. Unpushed: `git log --oneline origin/main..main`. Push ONLY on explicit in-turn approval.
4. Next discussion point P354; next C id C75. Nothing open for the operator except the M42 go.

## M41 result (full entry in campaign-results 2026-09-13)

`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ON: `mx.get_peak_memory` 35.0 / 37.3 / **41.1 GB** at 131K / 197K /
262144 (gate ≤46 PASS, 4.9 GB headroom); retrieval 1.0 at every rung to 128K; chain-4 reasoning 1.0 at every rung to
156K, **0/42 runaways**; decode 44.7 → 18.3 tok/s (8K → 156K), 10.7 at 262K; prefill 332 → 132 tok/s (131K → 262K,
~33 min TTFT at the cap). Mechanism: acceptance is task-stable (0.74–0.92) so the ON advantage grows with depth as
OFF decode collapses; prefill, not memory, is the depth-usability limit. Files `benchmark/results/<pick>/
{capacity_retrieval,retrieval,reasoning}.m41on.*` (+ manifests, provenance; data commit 2d09326).

## Next: M42 KV-lever OFAT on pick A (PLAN row; needs a go)

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

- Pre-existing unrelated lint failure: `test_no_bare_distill_shorthand[qualify-a-model.md]` (docs debt, not touched).
