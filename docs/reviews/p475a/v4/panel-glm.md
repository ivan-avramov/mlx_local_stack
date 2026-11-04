Based on my review of the candidate diff, the spec, the matrix, and the frozen tests, here are my findings.

## Findings

### F1 — `--kv-arm --predictor on` with a non-empty KV delta cannot pass the C199 argv-binding gate in practice; the frozen test masks it with a crafted summary

**Location:** `dev/p369_phase2/qualify.py` `kv_arm_gate` (lines ~1077-1082) + `drive` argv-binding loop (lines ~1241-1249) + `entry_problems` C199 gate (lines ~296-333).

**Severity:** major (hypothesis — traced in source, not reproduced end-to-end against a real P369 run).

**Evidence:** The spec's `--predictor on` rule (spec lines 26-28): *"`--predictor on` ONLY when the arm commit's registry already serves the entry MTP-ON … then no overlay is built and the committed arm registry is served as is (C233); any other `on` case refuses."* The only refusing condition the spec names is the entry being MTP-OFF. `kv_arm_gate` enforces exactly that. But once accepted, `arm_for` returns `"served_on"` (qualify.py:84), which is in `MTP_ON_ARMS`, so `entry_problems` applies the full C199 gate: it requires a P369 full-run PASS summary whose `manifest.json` carries `picks[name].argv_on`, and `drive` then binds the served argv to that certified one via `argv_binding_problems` (qualify.py:1248). For an arm with a non-empty KV delta (e.g. AF8), the served argv carries `--kv-bits 8 --kv-quant-scheme uniform`, but the certified `argv_on` from any real P369 run was taken against the *committed* registry (N16 for Fable, TQ4 for Uniform) and carries different KV flags — so `argv_binding_problems` refuses. The candidate does not bypass or relax the C199 gate under `--kv-arm`.   <!-- allow-shorthand: verbatim reviewer output -->

**Problem:** The spec says the committed arm registry is "served as is" under `--predictor on`, but for every arm with a non-empty KV delta the C199 argv binding refuses before serving. So `--kv-arm --predictor on` is dead for all 8 non-committed P475 cells; only the two committed picks (empty delta) can pass, and for those `--kv-arm` adds nothing over today's `--predictor on`.

**Failure scenario:** `qualify --kv-arm --predictor on --entry Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` against the AF8 arm commit's worktree (kv_bits=8, scheme=uniform, MTP-ON). `kv_arm_gate` accepts (entry not in `off`). `arm_for` → `served_on`. `entry_problems` reads the only available P369 summary (certified the committed N16 registry); `certified[name]`'s `argv_on` has no `--kv-bits`/`--kv-quant-scheme` (or `--kv-bits 0`). `argv_binding_problems` reports `the served configuration differs from the one its P369 run certified (--kv-bits)`. The run refuses — the opposite of "served as is."

**Frozen-test gap:** `test_predictor_on_serves_the_committed_mtp_on_arm_registry_without_an_overlay` (driver tests:278-292) crafts `rig.summary(pick, argv_on=mlx_serve_argv(...arm_text(arm, pick)...))` — i.e. it forges a P369 summary whose `argv_on` is the *arm's* argv, not the committed registry's. No real P369 run produces that summary for a KV arm. The test asserts the path works by construction, hiding that it cannot work against a real P369 manifest.

**Proposed change:** Decide which the spec means and make the code match it. If "served as is" means the C199 gate is waived under `--kv-arm --predictor on` (my reading of spec line 27), then under `--kv-arm` skip the `MTP_ON_ARMS`/C199 branch in `entry_problems` and the `argv_binding_problems` loop in `drive`, and add a frozen test that runs `--kv-arm --predictor on` with a *committed-registry* P369 summary (mismatching argv) and asserts completion. If instead the C199 gate is intended to stay, add a refusal test that shows `--kv-arm --predictor on` with a non-empty delta refuses on the argv binding, and correct the spec's "served as is" wording.

---

### F2 — `request_problems` computes `expected_manifest` twice per call (minor)

**Location:** `dev/p369_phase2/qualify.py` lines ~631-639 (candidate).

**Severity:** minor (confirmed — traced in source).

**Evidence:** The candidate adds `native_attention = any(e["kind"] == "native" for e in kvmanifest.expected_manifest(template, expected_kv(expected)))` immediately after `problems += kvmanifest.manifest_problems(observed, template, expected_kv(expected))`. `manifest_problems` internally calls `expected_manifest` (kvmanifest.py:191 → `expected = {e["path"]: e for e in expected_manifest(template, kv)}`). So `expected_manifest` runs twice and `expected_kv` is built twice per request.

**Problem:** No correctness impact — both calls use the same inputs and the function is pure. It is wasted work on the hot path (every measured request), and `expected_kv` allocates a dict each time.

**Failure scenario:** None functional. A run with many requests does double the manifest derivation.

**Proposed change:** Have `manifest_problems` return (or accept a precomputed) `expected_manifest` list, or compute `expected = kvmanifest.expected_manifest(template, expected_kv(expected))` once and pass it into a variant of `manifest_problems` that takes the precomputed list. Not a blocker.

---

### F3 — Frozen tests miss: `--kv-arm` without `--predictor` (refusal), and the `--predictor on` + missing-summary refusal under `--kv-arm`

**Location:** frozen tests `test_p475a_qualify_driver.py`.

**Severity:** minor (the behaviour is correct; the tests don't pin it).

**Evidence:** `kv_arm_gate` refuses when `predictor not in ("off", "on")` (qualify.py:~1063), which covers `--kv-arm` with no `--predictor` (default `None`). No frozen test exercises `--kv-arm` alone (without `--predictor`). Separately, no frozen test exercises `--kv-arm --predictor on` against a missing/invalid P369 summary to assert the C199 refusal (the only `--predictor on` refusal tested is the MTP-OFF case, driver tests:300-312).

**Problem:** A future change that drops the `predictor not in ("off","on")` guard, or that relaxes the C199 gate under `--kv-arm`, would pass the frozen suite.

**Proposed change:** Add `refused(rig, rig.run("--kv-arm", "--entry", kv.UNIFORM))` to `test_refuses_without_an_entry_and_with_two_entries`, and add a test that runs `--kv-arm --predictor on` with an MTP-ON arm but no `--p369-summary` and asserts refusal.

---

### What I did NOT find

- **A registry `--kv-arm` accepts that it must refuse:** I traced `classify_kv_arm` against every refusal category the spec names (third entry, non-KV key, second entry, `quantized_kv_start != 0`, partial MTP, foreign MTP value, fractional/non-finite/mistyped width or scheme, malformed structure, duplicate entry/name, top-level change, added `kv_group_size`/split-width/`kv_quant_mode` key). All return `None`. The `_kv_arm_row` integer-width guard (`type(bits) is not int`) correctly rejects floats, `.inf`, `.nan`, strings, lists, dicts, bools, and `null`. The settings comparison (via `_states`) catches every non-KV-key difference because `KV_ARM_KEYS` is exactly `("kv_bits","kv_quant_scheme")` and the restored entry substitutes the fixture's values for those two keys only — so any other difference survives into the `_states` comparison and refuses.
- **A registry it refuses but must accept:** All 10 arm×pick cells are accepted (the `_kv_arm_row` table matches the matrix's five rows; N16 keeps the fixture's scheme via the `_same` branch). The 16-base-state test (frozen:248-258) confirms acceptance on every base, including bases where a non-tested entry is MTP-ON.
- **A wrong attention verdict for any of the 10 cells:** The candidate's rule `(fused and native_attention) != (forced > 0)` with `native_attention=None → pass` matches the spec exactly: Fable N16/TQ8/TQ4 (native leaf) require forced calls; Fable AF8/AF4 and Uniform (all arms, `auto`) require zero; a missing manifest yields only the manifest problem. The `native_attention` is derived from the *expected* manifest (`expected_manifest`), as the spec requires.   <!-- allow-shorthand: verbatim reviewer output -->
- **A change without `--kv-arm` beyond the two allowed:** The only no-flag-affecting edits are (a) `_exact_width` replacing `int(values["kv_bits"])` (the "exact widths" change — spec line 59) and (b) the `request_problems` attention rule (spec line 28-30). The `classify` refactor into `_states` is behaviour-preserving (same checks, same return). `kv_arm_gate`/`kv_arm_reference`/`classify_kv_arm` are only reached when `args.kv_arm` is set. The `--kv-arm` parser flag is additive. I confirmed `kv_arm` is `None` without the flag, so `snapshot["kv_arm"]`, `report["kv_arm"]`, and `kv_arm_reference` are all no-ops without it.
- **A crash where `None`/refusal is required:** `classify_kv_arm` wraps `parse` in `try/except ValueError` and validates `isinstance(doc, dict)` / `isinstance(doc.get("models"), list)` / `all(isinstance(m, dict))` before touching anything, so malformed YAML, `models: [null]`, scalar models, non-mapping items all return `None`. `_exact_width` calls `int(value)` for its side effect, which raises on non-convertible values — but `expected_config` wraps that in `(TypeError, ValueError, AttributeError)` → `ValueError` (qualify.py:393), and such values are refused at the `classify_kv_arm` gate before `expected_config` is ever called under `--kv-arm`.

The one substantive item is **F1**: the `--kv-arm --predictor on` path's interaction with the C199 argv-binding gate. Everything else is minor or a test gap.
