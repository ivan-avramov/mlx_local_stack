I reviewed the candidate diffs, the spec, both frozen tests, the implementer's and test-writer's reports, and the live registries/carriers. I agree with the three known findings (F1 blocker, F2 minor, F3 test-side) and do not re-report them. Below are the disconfirming cases I found that are not already on the table.

---

**Finding 1 — minor — stale "seven" docstrings in `qualify.py` contradict the pruned `ENTRIES`.**

Location: `mlx-vlm/dev/p369_phase2/qualify.py:64` (`default_entries`) and `:79` (`entry_problems`).

Problem: S4 requires "the seven-entry set / `len == 7` assertions become the three-entry set." The candidate updated every assertion (`len == 3`, the `_the_three_entries_…` renames) but left the two docstrings stating "the full qualification is all seven" and "Every name is one of the seven." With `ENTRIES` now holding three, both docstrings are wrong.

Failure scenario: A future maintainer reads `default_entries`'s docstring, believes the default run is seven entries, and adds the four pruned served entries back to `ENTRIES` (or passes `--entry` for them) thinking R7's scope is seven — re-widening R7, which S4 forbids ("no entry is added — R7's scope is not widened"). The green `len == 3` assertion would then catch it, but the docstring steers the edit toward the bug.

Proposed change: rewrite both docstrings to "the three MTP entries" (and drop the "all seven" / "one of the seven" phrasing) in the same commit that pruned `ENTRIES`.

---

**Finding 2 — minor — the gemma fixture is not verified against the baseline block, and it silently drops the baseline's trailing draft comments.** <!-- allow-shorthand: verbatim reviewer output -->

Location: `mlx_local_stack/benchmark/bench/tests/fixtures/gemma_31b_qat_registry.yaml` (new) and `benchmark/bench/tests/test_deployed_profile.py:96`.

Problem: S3 says a test whose literals are entry-specific "reads a fixture registry holding that entry's baseline block." The fixture is a hand-copy of the baseline gemma block. No test asserts the fixture equals the baseline block: the frozen `TestRemainingEntriesMatchBaseline` checks only the five *published* entries against baseline; `test_deployed_gemma_is_the_daily_driver_not_the_coding_profile` pins only five sampled values (`temperature`, `top_k`, `repetition_penalty`, `thinking_budget`, `max_tokens`). The non-sampled fields the deployed-profile machinery also reads — `hf_path`, `max_kv_cache_size`, `kv_prealloc_tokens`, `kv_quant_scheme`, `kv_bits`, `prefill_step_size`, `quantized_kv_start` — are unchecked. The fixture also omits the four inert trailing lines of the baseline block (`# draft_kind: suffix`, `# draft_block_size: 16`, `# suffix_min_match: 2`, `# draft_cooldown: 2`), so it is parsed-equivalent, not a verbatim baseline block. <!-- allow-shorthand: verbatim reviewer output -->

Failure scenario: a copy error in the fixture's `max_kv_cache_size` (e.g. `262144` for `196608`) or `hf_path` is undetected; `test_deployed_profile_is_the_registry_block` is tautological for gemma (both sides read the same fixture), and no other test cross-checks the fixture against `c4faf574`. The deployed-profile test would pass while pinning a gemma block that never shipped. <!-- allow-shorthand: verbatim reviewer output -->

Proposed change: add one assertion that parses `git show c4faf574:main_models.yaml`, extracts the gemma block, and asserts the fixture's parsed gemma entry equals it (field-for-field, including `max_kv_cache_size`/`hf_path`/`kv_bits`); or assert the fixture's gemma block equals the baseline block textually. <!-- allow-shorthand: verbatim reviewer output -->

---

**On the rest of the question:**

- *What does the candidate do beyond the specification?* Nothing. Every stack file touched is a carrier named in S2, the registry (S1), or the two S3 test files; every fork file touched is named in S4. No production file outside the spec's list changed; the fork production diff is empty.

- *What would fail in use?* Nothing beyond the known F1 test failures. The serving stack reads the pruned registry and serves the five; clients/carriers name only the five (frozen `test_no_carrier_names_a_pruned_entry` green); `configgen check` rc 0; the fork's `classify`/`overlay_on` round-trip the pruned live registry against the regenerated fixture (frozen `test_live_sibling_classifies_as_all_four_off` and `test_fixture_equals_pruned_sibling_with_four_mtp_on` green); `load_references` on the real pruned reference table passes. The 14 pinned-hash tests are test-side failures marking a new Wave-2 epoch (carrier bytes moved); the harnesses themselves would run and compute new hashes — they do not fail in use, they just cannot pool with historical rows, which S2 anticipates.

- *Scope request (labelled as such, no severity):* the spec's S2 acknowledges `probe_code_sha256` moving but does not acknowledge the carrier-derived `opencode_bench_config_sha256` / campaign `scaffold_policy_sha256` (c147/m61) or the p371 goldens moving, so AC4 ("0 failed") is unachievable without touching the read-only test directory. Either regenerate those goldens or list those four files under AC4's "removed/retargeted, listed" allowance. This is the F1 remediation the test-writer already named; I raise it only as a scope request because the implementer is forbidden to edit the test directory.
