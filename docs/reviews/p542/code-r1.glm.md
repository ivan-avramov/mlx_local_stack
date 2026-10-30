I read `BRIEF.md`, `spec.md`, `qualify.py.txt`, `registry_states.py.txt`, and `change.diff` (incl. the three test files). Findings below. (I cannot see `orchestrate.PRODUCTION`'s length, so F1's severity is conditioned on that — stated explicitly.)

---

## F1 — MTP-ON gate's production check is inverted when the run uses the default production; a valid P369 PASS summary is refused
- **Location**: `qualify.py` `_production_matches` (lines 149–155) and `entry_problems` `passed` (lines 223–225); called from `drive` with `production = orchestrate.PRODUCTION` (lines 956–962).
- **Severity**: major (hypothesis — confirmed if `orchestrate.PRODUCTION` is a short sha, which the material strongly implies: the removed constant was `"7207179b"`, 8 hex, and `test_c3_a_summary_on_the_old_production_constant_refuses` treats `7207179b` as the old production pin of the same shape).
- **Evidence**: hypothesis, traced in source.
- **Problem**: spec v1.1 requires *the summary's* `binding.production` / `manifest.production` to be a prefix (≥7 hex) of *this run's* resolved production sha. `_production_matches(value, production)` implements this as `str(production).startswith(value)` — i.e. `run_production.startswith(summary_production)`. For that to hold, `summary_production` must be ≤ `len(run_production)`. When the run uses the default (`--production-ref` unset), `production = orchestrate.PRODUCTION` (a short pin, e.g. 8 hex). A real P369 campaign summary records a full 40-hex production sha. A 40-hex string can never be a prefix of an 8-hex string, so `_production_matches` returns False and every MTP-ON arm (`served_on`, `mtp_on_restored`) is refused on the default run — the exact case spec rule 3 + the `test_c3_a_summary_on_the_default_production_passes` test claim should pass. The direction is also asymmetric with `resolve_production_ref`, which expands a short ref to a full sha for a non-default `--production-ref` (lines 957–961) but leaves the default short.
- **Failure scenario**: Operator runs the default qualification (`--entry Qwen3.6-27B-Opus-Distill-OptiQ-4bit --p369-summary <real campaign summary.json>`). The summary's `binding.production` is the campaign's full 40-hex sha; `production` is `orchestrate.PRODUCTION` (8 hex). Gate fails → `refused: [...Qwen3.6... MTP-ON only after its P369 full-run PASS (C199)]` despite a valid PASS. Every served-on/restored arm is unmeasurable on the default production. <!-- allow-shorthand: verbatim member output (a truncated argv) -->
- **Proposed change**: resolve the default production to a full sha the same way a non-default ref is resolved (so `production` is always ≥40 hex), *or* make the match bidirectional: `str(production).startswith(value) or value.startswith(str(production))` with the ≥7-hex floor on both. Resolve the default once at the same site `resolve_production_ref` is called.

---

## F2 — `test_c3_a_summary_on_the_default_production_passes` does not test what it claims
- **Location**: `test_p542_qualify_any.py` `test_c3_a_summary_on_the_default_production_passes` (diff lines 1326–1332); helper `_Rig.summary` (diff lines 1086–1101).
- **Severity**: major (confirmed).
- **Evidence**: confirmed, traced in source.
- **Problem**: The test asserts the default production passes, but `_Rig.summary(name)` sets the summary's `production` to `orchestrate.PRODUCTION` — *equal* to the run's production. `_production_matches` then reduces to `"X".startswith("X")`, which passes for any length. The test never exercises the realistic shape (a summary carrying a longer/full-sha production that must be a prefix of the run's). It therefore passes regardless of whether F1 is a defect, and masks it. The test's docstring ("the default attested production is `orchestrate.PRODUCTION` — not qualify's old `7207179b`") is the only thing it actually verifies.
- **Failure scenario**: F1 ships; this test stays green; the refusal of real campaigns is discovered only at operator time.
- **Proposed change**: have the summary write a production that is a strict prefix (e.g. first 12 hex) of a full-sha run production, and add a case where the summary's production is a full 40-hex sha and the run's is the short default — which, if F1 stands, must be asserted to refuse (or, after F1's fix, to pass).

---

## F3 — `arm_for` does not verify `name` is in the supplied `registry_state` for a restore
- **Location**: `qualify.py` `arm_for` (lines 76–88).
- **Severity**: minor.
- **Evidence**: confirmed, traced; not currently exploitable.
- **Problem**: For `--predictor on` on an OFF entry, `arm_for` checks `name in registry_states.ENTRY_OFF` and `registry_state is not None`, then returns `mtp_on_restored` without checking `name in registry_state`. The spec v1.1 defines restorable as "the name is in `registry_states.ENTRY_OFF` *and* the registry classifies". The classify invariant (`serves_mtp` False ∧ classify ≠ None ⟹ name ∈ OFF set) currently makes the omission unexploitable, but the function accepts a `registry_state` that does not contain `name` and still returns the restore arm — a latent gap if a caller ever passes a cached/foreign classify result.
- **Proposed change**: add `if name not in registry_state: raise ValueError(f"{name}: the registry serves it MTP-ON, nothing to restore")` before returning `mtp_on_restored`.

---

## F4 — `mtp_off` line-removal regex is indent-anchored to the entry's first line; a block whose MTP keys sit at a different column is refused (not silently mis-measured), but the refusal message is misleading
- **Location**: `qualify.py` `mtp_off_registry` (lines 99–113).
- **Severity**: minor.
- **Evidence**: confirmed, traced; safe due to the `new != want` guard.
- **Problem**: `indent` is derived from the block's first line (`  - name: …`): `len(first) - len(first.lstrip()) + 2`. The removal regex `^${indent}(draft_kind|draft_model|mtp_verify_scan)\s*:` only matches MTP-key lines at exactly that column. If an entry's MTP keys live at a different indent (e.g. inside a nested mapping, or a registry with unusual list indentation), the regex misses them; the `new != want` equality check then raises `f"{name}: the MTP keys could not be removed textually"` — a refusal, so no silent mis-measure. But the message blames "could not be removed textually" when the real cause is an indent mismatch, and the spec's A1 assumption ("removing exactly the three MTP key lines … yields a registry that mlx-serve serves as that entry MTP-OFF") is silently narrower than "any registry entry."
- **Failure scenario**: A new candidate model committed with MTP keys under a nested mapping fails `--predictor off` with a confusing message rather than a clear "the entry's MTP keys are not at the expected column."
- **Proposed change**: either remove keys by parsed-key rather than by indent-anchored line match, or include the expected indent in the refusal message; document the indent assumption in A1.

---

## Scope request S1 — pin `orchestrate.PRODUCTION`'s shape
- **Location**: spec v1.1 "prefix (≥ 7 hex) of this run's resolved production sha"; `drive` lines 956–962.
- Not a defect in the material, but F1 cannot be graded without knowing whether `orchestrate.PRODUCTION` is a short pin or a full sha. Request the operator confirm its length; if short, F1 is a blocker for default-production MTP-ON runs.

---

Nothing else of substance: the `mtp_on_restored` overlay path re-runs `overlay_registry` with the same fixture/classify used by the gate (lines 1126–1132); the `mtp_off` arm is correctly excluded from `MTP_ON_ARMS` so no gate is skipped; a new candidate served MTP-ON is refused via `name not in orchestrate.PICKS` (lines 200–204, test `test_c3_mtp_on_needs_the_entry_in_picks_even_with_a_summary`); the classifier is invoked only for restores (lines 191, 997–999, tests `test_c4_*`); `rates`/`arm` are written whenever a record exists (lines 1196–1197); the removed `ENTRIES` table and `7207179b` constant are gone (test `test_c1_the_fixed_entries_table_is_removed`); `load_references` no longer refuses names outside a fixed table (diff lines 252–253, test `test_c5_load_references_takes_any_entry_name`).
