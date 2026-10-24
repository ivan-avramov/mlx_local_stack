I've completed my review. Here are my findings.

---

## Findings

### F1 — minor — `bundle.py` carrier overlay leaves the manifest's `commit` field dishonest about provenance

**Location:** `mlx_local_stack/benchmark/bench/tests/p371_baseline/bundle.py:27-29` (`LIVE_INPUTS`), `:78-83` (overlay), `:88` (`manifest = {"commit": full, …}`), `:3-5` (docstring).

**Problem (judging the change the operator flagged):** The overlay is *sound for the differential's purpose* — it holds the four configgen carriers constant so the old-side and new-side reads agree on `carrier_source_sha256` / `opencode_bench_config_sha256` / `carrier_sha256`, which `compare.TABLE` does not list as allowed value-changes. Without it, `regen_p371_goldens.sh` alone could not move the goldens (the implementer's claim matches the code: the old side reads the bundle's carriers, the new side reads the current tree's). The differential still isolates the baseline-core vs new-core code change. **But** the overlay is grafted onto `make_bundle` as a permanent step, not the one-time regen S3b names ("refreshed by its own procedure — P371: `P371_REGEN_GOLDEN=1`"), and the manifest it writes still records `"commit": <0c9bd32a>` while four files in that bundle are no longer from `0c9bd32a` — they are the current tree's carriers. `verify_manifest` only checks files against the manifest's file map, never against the git commit, so the gap is undetected. The docstring still says "Root runtime inputs … are tracked and therefore included" with no mention of the overlay.

**Failure scenario:** A future maintainer (or a provenance audit, or a regen run after the *next* carrier change) checks the bundle against `0c9bd32a`, finds four files whose bytes do not match that commit, and either (a) treats it as tampering and archives the goldens, or (b) reverts the overlay thinking it is a hack — after which `regen_p371_goldens.sh` produces goldens whose carrier-derived fields drift from the new side on every future carrier regeneration, failing the differential with "unlisted difference" on `carrier_source_sha256`.

**Proposed change:** Record the overlay in the manifest — e.g. an `"overlaid_files": {<rel>: <current-tree sha256>}` map alongside `"commit"` — and add one sentence to the docstring stating that the four `LIVE_INPUTS` carriers are overlaid from the current tree (P476 S3b) so the goldens track the shipped carrier. This preserves the differential's soundness while making the provenance honest and the regen reproducible for a reviewer who was not told.

---

### F2 — minor — the OWUI policy diff reorders a *non-pruned* entry, violating AC2's "removal of pruned entries only (no other line changes)"

**Location:** `mlx_local_stack/openwebui-init/model_settings.json` `excluded_model_ids` (diff at `candidate2.stack.diff:2065-2078`); emitter at `configgen/emitters/owui.py:86-90`.

**Problem:** AC2 requires every generated-file diff to be "the removal of pruned entries only (no other line changes)." The OWUI policy diff is not pure removal: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (a *published* entry, not pruned) moves from position 3 to position 1, and `Qwen3.8-27B-static-mixed-4bit` (pruned) moves up within the list. This is the mechanical consequence of S2b's emitter — after the prune, step 1 (`[m.name for m in source.models if m.role != "task" and m.name not in main]`) yields only `Qwen3.6`, and the six retired ids are appended at the end — so the non-pruned `Qwen3.6` shifts to the front. No frozen test catches this: `TestRegistryDiffIsDeletionsOnly` checks only the *registry* diff; `TestCarrierIds` checks id membership, not diff shape; `test_registry_published_set.py` checks retired ids are only in `excluded_model_ids`, not that the diff is removal-only. <!-- allow-shorthand: verbatim reviewer output -->

**Failure scenario:** A reviewer auditing the carrier diffs against AC2's "removal only" wording sees `+ "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"` and `- "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"` lines in the OWUI policy and must determine by hand that it is a benign reorder, not a semantic change — exactly the audit-friction AC2's wording exists to eliminate. It does not fail in use (`reconcile_models.py` consumes `excluded_model_ids` as a set), but the spec's constraint is violated and untested.

**Proposed change:** Either (a) acknowledge in AC2 that the OWUI policy's `excluded_model_ids` list reorders as a consequence of S2b (retired ids are appended after the surviving main-not-in-menu ids), so reviewers know to expect it; or (b) have the emitter preserve the pre-prune order of the surviving `excluded_model_ids` entries and splice the retired ids into their old positions, so the diff is genuinely removal-only. (a) is the cheaper fix and matches the spec's intent.

---

### What the tests miss (summary, no separate findings)

- `_carrier_model_ids` (frozen `test_p476_frozen.py:210-244`) walks only dict keys/values and prefix-tagged tokens; it does **not** scan bare string elements of JSON arrays. The six tombstoned ids sit in `excluded_model_ids` as array elements, so `TestCarrierIds::test_every_carrier_id_is_in_registry_or_task_model` does not see them — coverage of "no pruned id leaks into a carrier" falls entirely on the special-cased `test_no_carrier_names_a_pruned_entry`. A future carrier that places a pruned id in a bare array (not under `excluded_model_ids`) would not be caught by the membership test. Not a defect in this candidate (no such carrier exists), but a gap the frozen suite leaves.
- No test asserts the OWUI policy diff is removal-only for non-pruned entries (F2 above).
- No test asserts the P371 bundle's files match its manifest's `commit` field (F1 above).

### What the candidate does beyond the specification

- `bundle.py` `LIVE_INPUTS` overlay (F1) — beyond S3b's stated regen procedure; judged sound but provenance-dishonest.
- Fork fixture `retired_model_ids` block (`stack_registry_golden.yaml:47-53`) — beyond the S4 list, but required for verbatim correctness (the test-writer's D4; I agree, not a defect).
- `test_deployed_profile.py::test_gemma_fixture_is_the_verbatim_baseline_block` and the `gemma_31b_qat_registry.yaml` fixture — beyond S3's literal text but faithful to its intent (the round-1 sol finding is resolved: the fixture now includes the trailing draft comments and is checked against `c4faf574`).

### What would fail in use

Nothing I found. The serving stack resolves no pruned name from the registry at runtime (production-code references are comment-only: `graft_vision_tower.py:83`, `cycles.py:20`, `bfcl_adapter.py:47`, `aider_adapter.py:11`); the historical one-off tools (`mem_decompose.py`, `run_bfcl_h2h.sh`, `w0_gemma_*.sh`, `bfcl_shim/sitecustomize.py`) are P478 out-of-scope. Clients name only the five. OWUI tombstones keep unmanaged saved registrations flagged stale. The fork's `classify`/`overlay_on` round-trip the pruned live registry; `load_references` passes on the real pruned table; the served-arm code path stays tested via the synthetic entry. The P371 overlay couples the goldens to the current carrier, so a *future* carrier change (not P476) will break the P371 differential until regen — but that fragility is pre-existing (the comparator never listed carrier-derived fields) and is not introduced by this candidate.
