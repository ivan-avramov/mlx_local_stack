`--kv-arm` is in place in `registry_states.py` and `qualify.py`, and the existing p369 phase-2 and qualify tests pass (698 passed, 2 skipped). Black did not run: it isn't installed in `.venv`, and running it through `uvx` or another venv needed approval I didn't have. No tests were written and nothing was committed. Production code under `mlx_vlm/` is untouched.

## Files changed
- **`dev/p369_phase2/registry_states.py`**: the body of `classify` moved into a helper `_states(doc, ref)`, with identical behaviour. New `KV_ARM_KEYS`, `KV_ARM_ENTRIES` (the two picks), `KV_ARM_ROWS` (N16 / AF8 / TQ8 / AF4 / TQ4), `_kv_arm_row` and `classify_kv_arm(text, fixture, entry)`. `classify_kv_arm` checks the YAML structure, requires the entry's KV keys to form one arm row, puts the fixture's KV values back into that entry, and then runs the 16-state comparison. It returns `(off, delta)` or `None` and never raises.
- **`dev/p369_phase2/qualify.py`**:
  - New `--kv-arm` flag.
  - `kv_arm_gate`: exactly one `--entry`, one of the two picks, `--predictor off` or `on`, and `classify_kv_arm` must not be `None`. `--predictor on` refuses if the entry is MTP-OFF.
  - `report["kv_arm"] = {entry, delta}`, added only under the flag.
  - `kv_arm_reference` adds `label: "non-comparable: KV arm"` and `comparable: false` to the reference block.
  - `_exact_width`: `expected_config` keeps the exact `kv_bits` with no `int()` truncation. It still calls `int()` first, so `null` or a non-number still raises the same `ValueError` as before.
  - The attention rule in `request_problems` (below).
- **`kvmanifest.py`**: unchanged, because `expected_kv` already uses `float()`.

## Commands and results
- `PYTHONPATH=.. ../.venv/bin/python -c "import mlx_vlm; print(mlx_vlm.__file__)"` printed `$STACK_WORKDIR/worktrees/p475a-impl/mlx_vlm/__init__.py`, so imports resolve to this copy.
- I ran `PYTHONPATH=.. ../.venv/bin/python -m pytest -q -p no:cacheprovider` on `tests/test_p369_phase2_registry_states.py`, `test_p369_phase2_kvmanifest.py`, `test_p369_phase2_orchestrate.py`, `test_p415_qualify.py`, `test_p426_qualify_predictor.py`, `test_p452_qualify_in_wrapper.py`, `test_p542_impl.py`, `test_p542_qualify_any.py` and `test_mtp_verify_scan.py`. The final run gave `698 passed, 2 skipped, 2 warnings in 57.65s`.
- An ad-hoc probe script, run against the real fixture and then deleted, gave the expected result in every case:
  - All 10 arm × pick combinations were accepted with the right delta.
  - An empty delta gave the same result as `classify`.
  - Arms built on an MTP-OFF base state were accepted.
  - These all returned `None`: a second entry changed, `4.5`, `.inf`, `8.0`, `true`, `6`, N16 with `uniform`, `quantized_kv_start: 5`, a change to a non-KV key, the third entry, an unknown entry, `models: [null]`, `models: 3` and a partial MTP block.
- **Black:** I instead made my additions match black style by hand (comments moved onto their own lines, one long line split). The pinned black still needs to be run before committing.

## Where v4 met P542's existing behaviour
1. **There is no 16-state gate for `--predictor off` at `fd67082a`.** The goal says `qualify` refuses registries outside the 16 states, but P542 only calls `classify` to decide a restore (`--predictor on` for an MTP-OFF entry). So, as P542 stands, a KV-arm registry with `--predictor off` is already served without the flag. `--kv-arm` therefore adds a stricter gate plus the report fields, not a relaxation.
2. **"Replace every `classify` use."** The only use is the `classify()` closure in `drive`. Under `--kv-arm` it returns `classify_kv_arm`'s `off` set. The `mtp_off` check that v3 assumed was gone in P542, which derives MTP-OFF from the committed block (`serves_mtp`) instead.
3. **`--kv-arm --predictor on` probably refuses every arm except the committed format.** P542's rule is kept: an MTP-ON run needs a P369 PASS summary, and its argv must equal the certified `argv_on`. An arm that changes `--kv-bits` or `--kv-quant-scheme` will therefore fail that argv check unless its certified argv matches. I kept P542's behaviour as v4 requires. P475's preflight uses `--predictor off`, so it isn't affected.
4. **The attention rule also applies without the flag.** With `fused_v1`, forced SDPA calls are required if and only if the expected manifest has a `native` leaf; with no manifest the rule isn't checked. For the committed registries the result matches today's. One reported difference: a `fused_v1` record with no manifest now gets only the manifest problem, not an extra `sdpa_forced` one (v4 asks for this).
5. **The `kv_bits` width is kept exactly without the flag as well.** For a float value the fingerprint changes (`4.0` gives `turboquant4.0` where it used to give `turboquant4`). Integer registries are unaffected.

## Ambiguities and how I read them
- **N16 row:** `kv_bits: 0` with `kv_quant_scheme` exactly as in the fixture (`turboquant` for both picks). Removing the scheme or setting it to `uniform` with `kv_bits: 0` refuses.
- **`--kv-arm` without `--predictor`** refuses, since the spec names only `off` and `on`.
- **Malformed registries:** the gate runs before `registry_states.settings()`. That's because `settings()` raises `AttributeError` on `models: [null]` (an existing no-flag crash, which I left alone), and the gate turns that case into a refusal instead.
- **`quantized_kv_start`** is enforced only by the settings comparison, since it isn't in `KV_ARM_KEYS`. There is no second check.
- **`delta`** holds tuples in memory; `report.json` stores them as JSON lists.
