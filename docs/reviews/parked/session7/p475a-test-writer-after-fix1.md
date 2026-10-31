`registry_states` is imported at line 832 (inside `drive`). `KV_ARM_ENTRIES` is accessed at 844. Good.

I have enough to write the report. Let me compile the final report.

---

## Report: P475a candidate2 delivery review

### 1. Diff application

`git -C mlx-vlm apply ../candidate2.fork.diff` → **EXIT=0**, no rejections. Touched files:
- `dev/p369_phase2/qualify.py` (modified)
- `dev/p369_phase2/registry_states.py` (modified)
- `mlx_vlm/tests/test_p475a_qualify_kv_arm.py` (new file)
- `mlx_vlm/tests/test_p475a_frozen.py` was already in place (untracked, not touched by the diff).

Production diff (`git -C mlx-vlm diff HEAD -- mlx_vlm ':!mlx_vlm/tests'`) = **0 bytes** (empty). ✓ (spec AC3)

### 2. Frozen tests — `test_p475a_frozen.py`

**Baseline (dev changes stashed):** `29 failed, 9 passed, 2 warnings in 1.66s`
**Candidate (diff applied):** `38 passed, 2 warnings in 2.53s`

(a)/(b) split: **All 38 frozen tests pass on the candidate; there are no failures to classify.** The 9 baseline passes were the "preserves an invariant" tests that already held on the baseline (e.g., `test_native_and_turboquant_arms_require_forced_calls`, `test_native_and_turboquant_arms_pass_with_forced_calls`, the no-flag unchanged tests). The 29 baseline failures were the red-first tests the spec fixes; all turned green on the candidate. No frozen test fails on the candidate, so no (a) "violates the spec" / (b) "only an assumed name differs" split applies.

### 3. Qualify / MTP / full suite / live check

- `./run_fork_tests.sh mlx_vlm/tests/test_p475a_qualify_kv_arm.py mlx_vlm/tests/test_p415_qualify.py mlx_vlm/tests/test_p426_qualify_predictor.py mlx_vlm/tests/test_mtp_verify_scan.py` → `419 passed, 1 skipped, 2 warnings in 9.38s`
- `./run_fork_tests.sh` (full fork suite) → `7004 passed, 17 skipped, 2 warnings, 526 subtests passed in 198.31s (0:03:18)` — **0 failed**
- `./fork_live_check.sh` → `268 passed, 2 warnings in 6.16s`

### 4. Review against `mlx_local_stack/docs/specs/p475a-qualify-kv-arm.md` (v2)

**Correctness — all spec criteria met:**

- **AC0 (attention rule):** `qualify.py:383-411` implements `native_attention` correctly. Under `fused_v1`, `sdpa_forced > 0` is required iff the expected manifest has a native-KV leaf; affine arms require `sdpa_forced == 0`. Without a manifest/template, only "no leaf manifest / template" is reported (sdpa check skipped for fused_v1; still checked for non-fused). Reduces to today's rule without `--kv-arm`. ✓
- **AC1 (`classify_kv_arm`):** `registry_states.py:307-329`. Entry restricted to `KV_ARM_ENTRIES` (the two P475 picks, `registry_states.py:271-274`); `_kv_arm_valid` (`registry_states.py:286-292`) requires `type(bits) is int` and `bits in (0,4,8)`, scheme in `("uniform","turboquant")` (or absent for bits=0) — refuses floats, bools, `.inf`/`.nan`, out-of-set widths, bogus schemes. `_models_ok` (`registry_states.py:295-301`) refuses malformed documents (non-mapping, non-list `models`, non-dict entries, non-string names, null entries). `parse` ValueError → None. Empty delta == `classify`. Second entry differing / non-KV key / `quantized_kv_start != 0` / unknown entry → None. ✓
- **AC2 (`--kv-arm`):** `qualify.py:839-847` refuses unless exactly one `--entry` and `--predictor off` (refuses `on` and `None`); refuses entries outside `KV_ARM_ENTRIES`. `qualify.py:932-942` replaces every `classify` use with `classify_kv_arm` under the flag (gate + `mtp_off` check at `qualify.py:1010` both use the arm's off set; `classify` is not called). `report["kv_arm"] = {entry, delta}` recorded (`qualify.py:941`). `reference_comparison(..., kv_arm=...)` adds `label: "non-comparable: KV arm"`, `comparable: false` (`qualify.py:579-589`), never a refusal. No-flag path byte-for-byte unchanged (else-branch at `qualify.py:943-947`). `expected_config` no longer truncates `kv_bits` (`qualify.py:195`: `values["kv_bits"] or None`), so 4.5 stays 4.5 and the flag reads `--kv-bits 4.5`. ✓
- **AC3:** production diff empty (verified above). Full suite 0 failed. Eight audits and the ×2 identical-skip-list criterion were NOT run (out of scope for this brief; the implementer also did not run them).

**Deviations:** None material. The `--predictor off` requirement is enforced as `predictor != "off"` (refuses `None` too), which is stricter than the spec's parenthetical "(refuses `on`)" but consistent with "requires `--predictor off`". Frozen tests only exercise `on`; the new file also pins `None`.

**Dead code:** None. The "dead guard" removal (the implementer's finding 4) was relative to candidate1, not the baseline HEAD — the baseline `request_problems` already had no `quantized_kv_start` guard; the candidate only adds the `native_attention` logic. No leftover kvmanifest-based guard.

**Unhandled errors:** `classify_kv_arm` catches `ValueError` from `parse` (the only exception `parse` raises). The `next(m for m in doc["models"] ...)` at `registry_states.py:327` is guarded: it is reached only when `_classify_docs` returned non-None (so `doc["models"]` contains the entry). No IndexError/StopIteration/KeyError paths found.

**Security:** No new file I/O, network, subprocess, or env access. `--kv-arm` is a dev-only flag on a dev tool. `KV_ARM_ENTRIES` is a fixed tuple. No injection surface. The `_serve_argv` test helper hand-spells mlx-serve's argv from source; it omits `--moe-expand`, `--mtp-verify-ab`, `--draft-block-size`, `--suffix-min-match`, `--draft-cooldown`, and gates `--memory-limit-frac` differently from the real `_build_command` — but none of those branches are active for the 10 P475 cells (predictor off, no `moe_expand`, all draft sub-flags withdrawn/commented, `memory_limit_frac`=0.85>0), so (b)'s fidelity is sound for the tested cells. The implementer flagged this as source-read, not machine-verified; I confirmed against `mlx_serve/process_manager.py:115-190` that the active branches match for these cells.

**Formatting:** black/isort not installed in the fork venv (implementer noted). The file already has 64 pre-existing >88-char lines, so the candidate's added long lines are consistent with the file's existing style and not a regression.

### Verdict

**Merge.**

The candidate applies cleanly, passes all 38 frozen tests (baseline was 29 failed / 9 passed), passes the targeted qualify/MTP group (419 passed, 1 skipped), the full fork suite (7004 passed, 17 skipped, 0 failed, 526 subtests), and `fork_live_check.sh` (268 passed). Production diff is empty. The implementation matches spec v2 on all criteria (AC0–AC3) with no material deviations, no dead code, no unhandled error paths, and no security concerns. The only unverified items (eight audits, ×2 skip-list, machine-compared argv helper) are explicitly outside this brief and do not block merge.
