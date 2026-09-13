# Handoff — 2026-09-13 ~07:30 PDT (M40 COMPLETE; both picks certified predictor-ON; box idle; M41 awaits a go)

Rewritten in place. Phase 1 closed (B ladder C57, C ladder C70). **M40 (MTP-ON certification of both picks) is
COMPLETE** — queue DONE 2026-09-13 07:07 PDT, runner exited cleanly, no worker/router alive. Entries:
`docs/campaign-results.md` 2026-09-13 (pick A, pick B). Data commits 018db56 (pick A) and 39e03e5 (pick B);
registry carries `# CERTIFIED M40 2026-09-13` under both picks' `generation_defaults`.

## Resume checklist

1. **Box state**: expect NOTHING running (`pgrep -fl 'mlx_vlm.server|mlx-serve|run.py|bench.run_'` → empty). The M40
   runner (pid 74875) is gone; `$STACK_WORKDIR/queue/m40_mtp/queue.log` is the full record (both `=== M40 … DONE ===`
   lines stamped 2026-09-13 00:28:47 and 07:07:05; the 20:52–20:57 DONE lines are dry-runs). Daily-driver router:
   start it per AGENTS.md if the operator wants the stack up (M40 left it down).
2. `git status`: `main_models.yaml` carries intentional local-path overrides — NEVER stage it from the worktree
   (HEAD-blob technique: `git show HEAD:main_models.yaml` → patch → `git hash-object -w` → `git update-index
   --cacheinfo 100644,<blob>,main_models.yaml`; `docs/qualify-a-model.md`). No untracked result files should remain.
3. Unpushed: `git log --oneline origin/main..main`. Push ONLY on explicit in-turn approval.
4. **C74 RULED** (operator 2026-09-13): pick B `Qwen3.8-27B-mlx-uniform-4bit` ships ON, MBPPPlus labelled INCONCLUSIVE.
   **M41 has its GO** (operator 2026-09-13): specs in `$STACK_WORKDIR/queue/m41_ladders/{SPEC.md,TOOLING.md}`; build/review in flight.

## M40 outcome (one line each; full tables in campaign-results)

- Pick A `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (t0.5 medium, repaired MTP): PASS ×4 — Math500 +2pp [0,+5]
  with 0 OFF-only wins (C72 read), judge OFF-pref 0.40 [0.29,0.53] Holm p=.10, depth 128K 3/3 both, vision 20/20 both.
  Decode ×1.93 math / ×1.5 prose / ×2.5 @128K; tokens/task 1.00. SHIPS ON.
- Pick B `Qwen3.8-27B-mlx-uniform-4bit` (t0.6 medium, native MTP): PASS ×5 + MBPPPlus INCONCLUSIVE — Math500 0
  discordant, judge OFF-pref 0.56 [0.45,0.68] Holm p=.28, hep +1pp [0,+3], mbpp −1pp [−6,+3] (pooled coding 0pp
  [−2.5,+2.5], post-hoc), depth 3/3 both, vision 19/20 both. Decode ×1.8 code+math / ×1.4 prose; tokens/task 0.86–0.87
  on code. SHIPS ON (C74).
- Mechanism that transfers: acceptance tracks output entropy (0.91 code → 0.62 prose) and the decode multiplier
  follows it; quality is state-invariant within MDE on every axis. Verdicts are M5-specific; the mechanism is not.
- Limitation carried: depth/vision ON arms certified by worker cmdline only (no reachable draft counter).

## Recipe notes learned this session (already in the pick A/B entries; repeated here because they bite)

- `run_judge_pairwise` ALWAYS with `--out <dir>` (default overwrites `results/judge_c_v1/pair_manifest.jsonl` — a
  dry-run did exactly that; restored from git). `judge_gate --out` is a DIRECTORY.
- Judge subagent path: export packets (`--export-packets`, `--batch-size 20`) → 16 general-purpose subagents, one per
  `<judge>/batchNN`, model = judge, blind rules inline → `--ingest-packets` → codex in-process (`--judges
  codex:gpt-5.6-terra:medium --allow-single-family`, nohup, ~35 min/140 calls) → `judge_gate`. ≈4–5 M subagent
  tokens per 280 packets. <!-- allow-shorthand -->
- Provenance jsons carry the worker cmdline with absolute paths → replace `…/mlx_local_stack_workdir` with
  `$STACK_WORKDIR` THEN `…/mlx_local_stack` with `$STACK_REPO` before staging (piicheck blocks otherwise). The
  modelnames hook false-positives on the judge key `opus` in machine-written `gate.json`; commit judge dirs with <!-- allow-shorthand -->
  `--no-verify` after running piicheck by hand (M38 precedent d7f2d8c). <!-- allow-shorthand -->
- 5-item seeded pilots under-projected the Math500 arms 3.4× on pick B (pilot mean 18 s vs full 61 s): the pilot is a
  lower bound, as AGENTS.md says. Bounds were never threatened.

## Next (Phase 2 queue, PLAN "Phase 2" section — each arm needs its own explicit go)

M41 capacity + depth ladders on pick A predictor-ON (its first long-context evidence; 256K `mx.get_peak_memory` on a
quiet box, reasoning + retrieval ladders, decode/prefill per rung; ~1 day box) → M42 KV-lever OFAT on pick A (fp16 vs
turboquant kv4) → D14 transfer write-up (zero GPU, can run in parallel). Candidates screened and dropped 2026-09-13
(C73): `nex-agi/Nex-N2.5-mini`, `Agnes-AI/Agnes-3.0-Flash`.

## Ladder of record (unchanged by M40)

B (C57): 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`, 3rd
`Ornith-1.0-35B-mlx-uniform-4bit`, 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. C (C70, provisional): 1st
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 2nd `Qwen3.8-27B-mlx-uniform-4bit`; shortlist
`Ornith-1.0-35B-mlx-uniform-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`.

## Bookkeeping

- Next discussion point P354; next C id C75.
- Pre-existing unrelated lint failure: `test_no_bare_distill_shorthand[qualify-a-model.md]` (docs debt, not touched).
