# Handoff — rewritten 2026-08-21 ~09:00 (M15/M16/M17 Stage-2 fold; session continuing)

Single box (M5 Max 64 GB). Stack pushed through `df30685`; ~10 local-only commits after
(results + grades, ledger folds, O34/O35 shipped, M19/M20 rulings, Stage-2 trees `4ce4159`).
Intentional dirt: `main_models.yaml` (six candidate entries, $HOME-local hf_paths) + M19 probe
artifacts in `$STACK_WORKDIR/status/m19_scan/`.

## Live right now

- **M19 DNF-first probes** (task in flight): all 10 `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`
  DNF items at candidate knee **t0.5** under the 8192 cap. Scan verdicts on `HumanEval/2`:
  t0.5 conv @437 tok, t0.4 clamp-hit (6654), t0.3 conv @924 — non-monotonic, knee = t0.5.
  If the DNFs convert → n=15 rung at t0.5 (pass@1 hold) → full 2×50 re-screen (gates, below).
  If they don't budge → prune, t0.6 stands, model wears 10% DNF.

## The 2026-08-20→21 Stage-2 screens (all n=50, graded, committed `4ce4159`)

| model @tune | hep acc/strict (DNF) | mbpp acc/strict (DNF) | paired vs representative |
|---|---|---|---|
| `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` @t0.6 | 95.6/86 (5) | 86.7/78 (5) | hep **+2.3 [+0.0,+6.8]**, mbpp 0.0 — INCONCLUSIVE |
| `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` @t0.6 | 88.4/76 (7) | 79.1/68 (7) | hep −4.9, mbpp −7.0 — INCONCLUSIVE, trailing |
| `Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit` @t0.4 | 92.0/90 (0) | 74.0/74 (0) | hep **+6.2**, mbpp −6.0 — INCONCLUSIVE, 3× speed |

Representative = `Qwen3.8-27B-OptiQ-4.5bpw-mixed` @t0.6 (hep strict 84 / mbpp 80, 2+1 DNFs).
Incumbent `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` @t0.3 fresh-cap: hep 93.75/90 (2), mbpp 81.6/80
(1); head-to-head vs representative INCONCLUSIVE both benches — **B pick stands**.

## Findings to carry (fold complete, in ledger)

1. **Runaways are item-anchored across families**: `HumanEval/32` beat 4 models / 2 families;
   `HumanEval/132`, `/99`, `Mbpp/306` (3 models), `/440` each 2+. A DNF is an (item ×
   thinking-mode) property more than a model property.
2. **Quant-recipe DNF hypothesis (open question, do not act)**: OptiQ quants 4% DNF vs <!-- allow-shorthand -->
   uniform-4bit 10–18% — but `Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit` is <!-- allow-shorthand -->
   uniform-4bit AND 0% (MoE arch, t0.4 — arch/temp confound). Needs a designed test <!-- allow-shorthand -->
   (e.g. an OptiQ conversion of one distilled candidate). <!-- allow-shorthand -->
3. **Distillation ≠ runaway immunity** (Stage-1 zero-DNF was n=15 flattery), but
   `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` hep accuracy leads the family and
   `Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit` is clean + fast.
4. O34/O35 SHIPPED (`daa622e`): $HOME-form manifests; probe-timeout rows = DNFs, not retried.
5. M19/M20 sufficient-gated re-eval RULING (`ec3cb32`): contention on DNF-excluded acc →
   DNF-first at knee (prune if unmoved) → n=15 rung (pass@1 hold) → ONE full 2×50; no
   mixed-tune splicing. Recommendations only on shipped-config data.

## Queue after M19/M20

M20 (`Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` — gate 1 passed by the letter, trailing
both point estimates; own scan + DNF-first) → M3/M4 (opencode) → M5 DNF re-runs → M18 (BFCL)
→ M7 → D10 submodule bump → F1+F2 → M11/M12 → D11 cards (Stage-2 numbers now final) → D6 →
M14 `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` MTP probe.

## Standing traps (delta from last rewrite)

zsh does NOT word-split `set -- $var` — six grades failed rc=2 silently green-looking; always
explicit args. The commit-msg hook rejects bare "distill"; rtk "ok" still lies about <!-- allow-shorthand --> commits —
verify with `git log`. Grading (CPU/docker) may overlap a token-verdict GPU probe, never a
wall-clock-scored run. Probe artifacts go to `$STACK_WORKDIR/status/`, never the results tree.

**Order of resumption: this file → `docs/PLAN.md` → `docs/work-queue.json` →
`$STACK_WORKDIR/status/` (live runs).**
