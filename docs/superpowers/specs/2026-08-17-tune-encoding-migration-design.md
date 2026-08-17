# Tune encoding + migration (D3)

Status: SPEC (architect, 2026-08-17). Encoding ratified by operator ruling 6 (2026-08-17).
Implementation: Sonnet worker to this spec; architect reviews the diff before commit.

## Why

A recommendation is a **(model, tune) pair** per goal. Today the corpus encodes "tune" three
incompatible ways, none of them queryable:

1. **Pseudo-model directories**: `Ornith-1.0-35B-mlx-uniform-4bit-kv4/`,
   `Ornith-1.0-35B-mlx-uniform-4bit-suffix/`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3/`,
   `Qwen3.6-27B-MLX-8bit-kv16/`, `Qwen3.6-27B-UD-MLX-6bit-kv16/`, `gemma-4-31b-it-6bit-kv16/`
   — the tune is fused into the model name, which under the ratified taxonomy is a category
   error (KV bits are TUNE, not model identity), and it poisons every name-keyed tool
   (modelnames hook, registry lookups, `params_for`).
2. **Ad-hoc file suffixes**: `humanevalplus.suffixon.jsonl` (+ `.manifest.json`,
   `.score.json`, `.suffixon_samples_eval_results.json`) — this one is the KEEPER, generalized.
3. **Manifest-only**: OFAT temperature rungs distinguishable only by reading
   `sampling.temperature` out of archived manifests.

## The encoding (ruled)

- **Result directories stay PURE registry model names.** No new `-kv4`-style dirs, ever.
- **`tune` is a short canonical label**, stamped in the manifest as a top-level `tune` field
  and encoded in filenames as `<bench>.<tune>.<ext>` for every non-default tune.
- **Absent label = the `deployed` tune** (registry `generation_defaults` + registry KV block,
  suffix per registry). `<bench>.jsonl` with no tune infix means deployed — the entire
  existing base-name corpus keeps its meaning without a rewrite.
- Label grammar: lowercase `[a-z0-9._-]+`, no dots at the ends; compose multi-axis tunes with
  `+` (e.g. `kv4+t0.3`). Canonical single-axis labels: `kv<bits>` (KV quant), `t<temp>`
  (temperature override), `suffixon`/`suffixoff` (draft state when it differs from registry),
  `cap<k>` (kv-cache cap override). The label NAMES the delta from deployed; the manifest
  fingerprint still carries the full resolved config (v4), so the label is a key, never the
  provenance.

## Implementation (worker scope)

1. `bench/generate.py result_path(model, bench)` grows a `tune: str | None = None` keyword;
   `None` -> today's path (byte-compatible), else `<bench>.<tune>.jsonl`. Same for the
   manifest/score/eval-artifact derivation sites (grep for `.with_suffix` on result paths —
   the `.suffixon_samples_eval_results.json` naming from the OFAT is the pattern for
   secondary artifacts).
2. `run.py generate` and `grade` grow `--tune <label>`; the label is validated against the
   grammar, threaded to `result_path`, and stamped as `manifest["tune"]` by
   `provenance.gather`/`write` (new optional `tune=` kwarg; absent -> field omitted, meaning
   deployed). NOT part of the fingerprint (the resolved config already is).
3. **Migration script** `benchmark/bench/migrate_tunes.py` (idempotent, dry-run by default,
   `--apply` to execute; prints every rename as `old -> new`):
   - For each pseudo-model dir above: move every `<bench>.*` file into the PURE model dir as
     `<bench>.<label>.*` with the label from the dir suffix (`-kv4` -> `kv4`, `-suffix` ->
     `suffixon`, `-kv3` -> `kv3`, `-kv16` -> `kv16`); rewrite the manifest's `model` field to
     the pure name and add `tune: <label>`; delete the emptied dir.
   - Collision rule: if the target filename exists, REFUSE that file loudly and continue
     (never overwrite; the operator resolves collisions by hand).
   - `.suffixon.*` files: already in the target encoding; add `tune: "suffixon"` to their
     manifests only.
4. Tests (mocked filesystem via tmp_path/`tmp_results`): round-trip `result_path` with and
   without tune; `--tune` label validation rejects `Bad_Label`/empty/uppercase; migration
   dry-run renames exactly the expected set and touches nothing; collision refusal; manifests
   rewritten with `tune` + pure `model`.
5. **Out of scope** (follow-up items, do not attempt): tune-aware `compare` (same model,
   two tunes head-to-head), scoresheet regeneration, registry changes, any edit to
   `main_models.yaml`, anything under `docs/` except nothing — docs are architect-owned.

6. **Isolation invariant (test it explicitly):** loading rows for `(model, bench)` WITHOUT a
   tune must never pick up `<bench>.<tune>.jsonl` files — audit `grade._rows` /
   `generate` resume / `bench_watch` / scoresheet globs for any `bench*`-style glob that a
   tune infix would leak into. A `.kv4` row silently pooled into the deployed baseline is the
   exact defect class this migration exists to end.

## Acceptance

- Full suite green; new tests fail before the implementation, pass after.
- `migrate_tunes.py --apply` on the real tree leaves `git status` showing only renames +
  manifest edits under `benchmark/results/`, zero content changes to row data (verify: jsonl
  md5s unchanged across the rename).
- The modelnames hook's known-dirs list shrinks by the six pseudo-model dirs on the next run.
