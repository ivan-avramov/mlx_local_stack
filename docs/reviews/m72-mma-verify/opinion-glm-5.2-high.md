I have completed my analysis. Here are my findings.

---

## Findings

### F1 — `fragment_mapping_ok()` verifies only the column half of the mapping the kernel's reductions depend on (blocker)

- **Location:** `fork.diff` `fragment_mapping_ok()` (≈lines 362–389) vs the pass-1 reductions `simd_shuffle_xor(mt, 1)` / `.., 8)` (≈lines 210–225).
- **Severity:** blocker (the material fails its purpose — the spec's "verify it with a unit test before relying on it" is not met for the part the kernel relies on).
- **Evidence:** confirmed by reading.
- **Problem:** The kernel's online softmax reduces `mt` and `rs` across the 4 lanes it credits with the same row using `simd_shuffle_xor(1)` then `simd_shuffle_xor(8)`. That is only correct if the 4 lanes sharing a row differ in lane bits 0 and 3 (the documented `fm = (q&4) + (l/2)%4` row mapping). The shipped `fragment_mapping_ok()` loads one matrix and reads only `m.thread_elements()[0/1]` per lane, checking the **column** mapping `fn, fn+1`. It never checks that the 4 lanes credited with row `fm` actually hold the same row's elements. A GPU/arch where the row mapping differs but the column mapping matches would pass the self-check while the xor-1/xor-8 reductions silently mix rows.
- **Failure scenario:** On a Metal target whose 8×8 fragment row mapping is not `(q&4)+(l/2)%4`, the kernel reduces scores/sums across *different* query rows. On random sweep data the mixed-row output is close to the true output (rows within a query group are statistically interchangeable), so A1 can still pass; the planted case may or may not catch it depending on whether the row mix changes the dominant token. The probe records `fragment_mapping_ok` as a boolean but does not fail on False.
- **Proposed change:** extend `fragment_mapping_ok()` to load a second matrix whose row `i` is filled with the value `i` (distinct per row) and assert that the 4 lanes credited with row `fm` all read the same value; or load two matrices and perform the actual xor-1/xor-8 reduction, comparing to a scalar row-reduction reference. Add a pytest test that calls it and asserts True; have the probe `sys.exit` when it returns False.

### F2 — `tq_production` slices the TQ4 state to `lengths[-1]`, so for k=1 planted cases the production path reads the bait token and the A1 bound is vacuous (major)

- **Location:** `stack.diff` `tq_production` (≈line 443); planted caches hold T+1 tokens (`MMA_PLANTED_T`, `planted_kv`).
- **Severity:** major (the accuracy instrument is blind for the k=1 TQ4 planted rows — exactly where A2/A3 are meant to bite).
- **Evidence:** confirmed (testwriter reproduced at T=8193: production rel error 1.74, A1 bound 3.48; kernel 2.5e-3).
- **Problem:** The planted caches hold T+1 tokens so the N2 (leak) control stays in range. `tq_production` slices the proxy to `lengths[-1]`, but for k=1 `lengths[-1] = T`, so the singleton reads the bait token at position T. The recorded `prod_rel_err` is ~1.7, making `2 × max(prod_rel_err, 2⁻⁸) ≈ 3.5`, so any kernel output passes A1. The k=1 planted TQ4 sweep rows record a vacuous `pass=True`, a wrong `prod_rel_err`, and the "worst / bound" log line is wrong.
- **Failure scenario:** the operator reads the report's accuracy section and believes the k=1 TQ4 planted case passed A1 against a meaningful production floor; it did not.
- **Proposed change:** build the proxy from a state sliced to exactly `lengths[-1]` per query (or give planted caches `offset == T`), then regenerate the smoke JSON.

### F3 — `m_run == NEG` exact-equality empty test is fragile (minor)

- **Location:** `fork.diff` line ≈241 (`bool empty = m_run == NEG;`).
- **Severity:** minor (no failure under supported conditions — bf16/half inputs and bounded norms cannot make `sf*kfac` reach −1e30 — but the test is a float-equality on a sentinel).
- **Evidence:** traced in source; not reproduced.
- **Problem:** Emptiness is inferred from `m_run == -1e30f` rather than tracked explicitly. Under the supported shapes/codec this is safe, but it is a latent hazard if the sentinel or input ranges ever change.
- **Proposed change:** track an explicit `bool any_visible` per row (set when any `ok[c][e]` is true in the block) and use that for the empty flag.

### F4 — `fragment_mapping_ok()` is shipped but no test asserts its result, and the probe does not fail on False (minor / scope request)

- **Location:** `fork.diff` `fragment_mapping_ok()`; `test_m72_mma_verify.py` has no test for it; `stack.diff` records it in `meta.mma_kernel` but does not gate on it.
- **Severity:** minor (the spec asked for a unit test; the function exists but is unverifiable by the suite).
- **Evidence:** confirmed by grep.
- **Proposed change:** add a pytest test calling `mma.fragment_mapping_ok()` and asserting True; have the probe `sys.exit` when it returns False.
- **Scope request:** the spec says "verify it with a unit test before relying on it" — this should be a required test, not an unasserted helper.

### F5 — `last_kv_inputs` is module-level mutable state, written on every launch, never read by tests (minor)

- **Location:** `fork.diff` `last_kv_inputs = {}` and `_run`.
- **Severity:** minor (dead weight; not thread-safe).
- **Evidence:** confirmed by grep — the A5 test checks identity via `before`/`after` `is` comparisons, not via `last_kv_inputs`.
- **Proposed change:** remove it, or document it as debug-only and guard it behind a flag.

### F6 — `FRAGMENT_TYPES` comment claims TQ4 codebook values are "exact in half" (minor)

- **Location:** `fork.diff` line ≈39–40; docstring; report header.
- **Severity:** minor (literal mismatch without material consequence — codebook entries are fp32 centroids; the cast to half loses ~2⁻¹¹ per element; measured accuracy unaffected).
- **Evidence:** confirmed (testwriter F3).
- **Proposed change:** correct the wording to "rounded to half".

### F7 — Launcher not executable, syntax unchecked, monitor leaves `sleep 60` child alive (minor)

- **Location:** `stack.diff` `m72_run_mma.sh` (mode 0644, `trap "kill $mpid" EXIT`).
- **Severity:** minor.
- **Evidence:** confirmed (implementer + testwriter reports).
- **Proposed change:** `chmod +x`; run `zsh -n`; `trap "kill $mpid; pkill -P $mpid 2>/dev/null" EXIT` (or kill the process group).

### F8 — Report `mtp_off` "TQ4 best / native16 best" takes min per checkpoint then interpolates (minor)

- **Location:** `stack.diff` `m72_mma_report.py` `gmin` (≈line 140).
- **Severity:** minor (matches the spec wording "per checkpoint the faster of …"; the synthetic test verifies the min-then-interp order; but the min can switch arms between checkpoints, producing a kink the report does not flag).
- **Evidence:** confirmed by reading; test `test_mtp_off_projection_best_of` passes.
- **Proposed change:** none required (spec-conformant); optionally annotate the table when the min switches arms across T.

### Beyond the spec

- `meta.mma_kernel` (tile tokens, target blocks, fragment types, mapping-ok) is an extra metadata field beyond the schema in the spec; harmless and useful.
- Extra asserts (ascending lengths, 1 ≤ k ≤ 5, 4-bit codec, bf16 dtype) are beyond the spec's preconditions; harmless.
- Planted cases are limited to T ∈ {8193, 32770} (two values) where the spec says "a case" — sufficient.

### What the tests miss

- No test calls `fragment_mapping_ok()` (F4).
- `test_a5_reads_nothing_beyond_the_last_length[tq4]` uses `mx.random.bits` which does not exist in MLX 0.32.4 — the TQ4 arm of that test never runs (testwriter F1). The property was checked by hand but is not covered by the suite.
- `test_launcher_runs_two_passes_with_mode_mma_and_idles_600` asserts the only `sleep` call is `sleep 600`, but the launcher also runs `sleep 60` in its monitor loop — the assertion is over-strict (testwriter F2).
- No test covers the `len(Tp) < 2` early return in the report (testwriter noted this).
- No test verifies that the kernel's row-reduction (xor-1/xor-8) actually matches a scalar row-reduction reference on this GPU — the one check that would catch F1.
