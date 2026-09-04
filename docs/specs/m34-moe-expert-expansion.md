# M34 — layer-scoped expert-budget expansion (MoE routing lever)

Source: Agrillo, "Layer-Scoped Expert-Budget Expansion Discovers Succinct Convergence in Sparse MoE Reasoning" (preprint, 2026-09).
Inference-only, training-free routing change. Targets: `Ornith-1.0-35B-mlx-uniform-4bit` (fork model `qwen3_5_moe`) first,
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (`nemotron_h`) second. Operator GO 2026-09-03.

## Definition (paper §3, made exact)

Per token at a MoE layer with router probabilities `p[e]` over `E` experts, native top-`K`. Parameters: `N >= K`, `T in [0,1]`,
`D in (0,1]`, inclusive layer range `[Ls, Le]` in ABSOLUTE 0-based decoder-layer index.

1. Rank experts by `p` descending; ties by lowest expert id (deterministic: sort on a composite key, never rely on argsort stability).
2. Ranks are 1-based `j = 1..E`. `R = floor(N/2)`; `pref = p` at rank `R`.
3. `T == 0`: keep exactly ranks `1..N`. `T > 0`: keep rank `j` iff `j <= floor(N/4)` or `p_j >= T * pref`; never more than `N`.
   Kept count `c in [floor(N/4), N]`.
4. Decay for extra ranks `j = K+1..N`: `factor(j) = 0.99 - (0.99 - D) * (j - (K+1)) / (N - (K+1))`; when `N == K+1`,
   `factor = (0.99 + D) / 2`. Ranks `<= K`: factor 1. Appendix A check (N=20, K=8, D=0.5): ranks 9/12/15/18/20 → 0.990/0.856/0.723/0.589/0.500.
5. Weights `w_j = p_j * factor(j) * kept_j`, renormalized over kept experts (`w / sum(w)`).
6. `qwen3_5_moe`: `p = softmax(gate)`; native renormalizes the top-K, so rule 5 is the native rule extended.
   `nemotron_h`: selection on the bias-corrected sigmoid scores (after the group step, as native); weights from `orig_scores * factor`,
   then native `norm_topk_prob` renormalization and `* routed_scaling_factor`.
7. Layer outside `[Ls, Le]`, or expansion unset, or `N == K`: the ORIGINAL code path runs (not a re-implementation). Byte-identical.

## Implementation

- Kernel shape: always pass `N` indices to `gather_qmm`/`SwitchGLU`; pruned ranks carry weight 0. Compute waste in gated layers is
  accepted and documented (the lever is tokens per task, cost is measured separately).
- Pure function `expand_route(p, k, n, t, d) -> (inds[..., n], weights[..., n])` in `mlx_vlm/models/moe_expand.py` (shared by both models),
  plus a `MoeExpansion` dataclass `(layers: tuple[int,int], n: int, t: float, d: float)` and a parser for the CLI string `LS-LE:N:T:D`.
- `qwen3_5_moe`: `Qwen3_5MoeSparseMoeBlock(args, layer_idx)`; block attribute `moe_expand: MoeExpansion | None = None`;
  `__call__` branches ONLY when `moe_expand` is set and `layers[0] <= layer_idx <= layers[1]` and `n > k`. The MTP target-verify path
  (`_target_verify_switch_glu`) takes `k = indices.shape[-1]` and needs no change.
- `nemotron_h`: `NemotronHMoE(config, layer_idx)`; same attribute; expansion inside `group_expert_select` (new optional arg).
- `LanguageModel.set_moe_expansion(exp: MoeExpansion | None)` on both models (sets every MoE block; clears with None).
- CLI: `--moe-expand LS-LE:N:T:D` on `mlx_vlm/server/cli.py` and `mlx_vlm/chat.py`; applied to the TARGET model after load. The MTP
  drafter (draft model object) is NEVER expanded. Log one line at startup: `moe_expand=<str> layers=<count>` (goes to the worker
  stdout the stack already captures); the value must be visible in the worker cmdline (`ps -o command=`).
- mlx-serve (`../mlx-serve`): `ModelConfig.moe_expand: str = ""`, parsed from the registry entry, forwarded as `--moe-expand <str>` for
  text and vision types.
- Stack: `registry_kv` records `moe_expand`; `_FINGERPRINT_KV_EXTRA += ("moe_expand",)` (OUTPUT-DETERMINING → `compare` refuses
  across it; `--clean-stale` sees it). Manifest `kv.moe_expand`. Fingerprint version stays 5 (an added key; absent == None on old rows).

## Tests (TDD — failing tests first; tiny synthetic configs only, NEVER load a real checkpoint while the box is serving)

Fork `mlx_vlm/tests/test_moe_expand.py`:
- `expand_route` on hand-built `p`: T=0 keeps exactly N; floor `floor(N/4)` always kept; cap N; tie-break by lowest id; renormalized
  weights sum to 1 over kept; Appendix A factors; N=K+1 fallback 0.745; N==K returns the native top-K weights bit-identically.
- Tiny `qwen3_5_moe` model (e.g. 4 layers, 8 experts, K=2, dim 16): forward with expansion unset vs set with `n == k` vs set on an
  empty range → all byte-identical logits; expansion on layers [2,3] changes only those layers' outputs (hook the per-layer output).
- Experts-per-token instrumentation helper (count of nonzero weights) reads exactly `K` outside the gate, `in [N/4, N]` inside.
- Tiny `nemotron_h` model: identity cases as above; `routed_scaling_factor` and `norm_topk_prob` still applied.
- CLI parser: `27-39:20:0.8:0.5` round-trips; malformed strings raise.
- `set_moe_expansion` on a model with an MTP drafter attached leaves the drafter's blocks unset.
Stack `benchmark/bench/tests/test_provenance_fingerprint.py`: a manifest with `kv.moe_expand` set is NOT compatible with one without.
mlx-serve: cmdline builder forwards `--moe-expand`.

## Verification (verifier agent)
Byte-identity claims re-run independently (same seed, expansion unset vs `n == k` vs out-of-range); tie-break determinism reviewed;
drafter isolation confirmed; full fork suite green; diff reviewed against this spec line by line.

## Commits
Fork: `feat(moe): layer-scoped expert-budget expansion (M34) — qwen3_5_moe + nemotron_h, --moe-expand, tests`. mlx-serve: `feat(config): moe_expand`.
Stack: `feat(bench): moe_expand in the provenance fingerprint (M34)`. No pushes; the submodule bump follows the operator's fork push.

## Experiment (after the build; PLAN M34)
OFAT on `Ornith-1.0-35B-mlx-uniform-4bit`: native vs `27-39:20:0.8:0.5` (the paper's config, 0-based, last 13 of 40 layers).
M21b recipe: hep + mbpp n=50 k=3 at t0.4, `deployed`, predictor OFF; math500 n=100 (the M33 `Ornith-1.0-35B-mlx-uniform-4bit` row is the native arm).
Read: strict EQUIVALENT (TOST ±5pp) AND tokens-per-task ratio CI < 1 → promote to a second OFAT (held-out config probe); ratio CI
containing 1 with no strict gain → CLOSE. Decode tok/s and Σ wall reported alongside (expected: slower per token, memory-bound).
Prior from the paper's own table: mathematics −0.9 %, computer science −1.0 % (no saving on our axes); the upside is the runaway tax.
