**P1 — Verdict at current heads**

| Repository | HEAD | Verdict |
|---|---|---|
| Fork | `19ffdf53` | **FIX-THEN-SHIP** — D3 |
| Router | `3f2c87c` | **SHIP** |
| Stack worktree | `554cad9` | **BLOCKING** — D1, D2 |

These are build-review verdicts, not GPU qualification or adoption approval.

**P2 — New findings**

**D1 — HIGH · VERIFIED: C120 exempts non-content mismatches.**  
`benchmark/bench/parity_replay.py:543–550`

Any identity difference becomes expected divergence when the joint row has `verify_blocks_straddle_len2 > 0`. This also exempts reasoning, finish reason, completion tokens and MTP counters.

Reproduction: 20 valid pairs; identical text; change only one row’s `draft_n_accepted` and set its length-2 straddle counter. **Compare returns 0.** The spec permits content divergence only.

Minimal fix: apply C120 only when every non-content identity field matches. Add mutations for each protected field on a C120-tagged row.

**D2 — HIGH · VERIFIED: code identity is neither complete nor uniform.**  
`benchmark/bench/parity_replay.py:247`, `:401`, `:527–540`

Code is checked pairwise, without requiring every row to match its journal’s code or one uniform code per side.

Reproductions:

- Both 20-row sides contain the same mixture of two fork hashes: **compare returns 0**.
- Both carry `{"src/mlx-vlm": null, "src/mlx-serve": null}`: **compare returns 0**. This dictionary also passes the entry truthiness check; `_git_shas()` can produce it when hashing fails.

Minimal fix: require both non-empty serving hashes at entry, resume and audit; require every row’s code to equal the journal code; then compare journal identities. Add mixed-within-side and unresolved-member tests.

**D3 — HIGH · VERIFIED counter logic: invalid straddle output satisfies G1a’s known positive.**  
`mlx_vlm/mtp_verify_scan.py:179–184`, `:350–375`

`_differs()` combines invalid output and representation differences into one flag. For straddles, either increments only `verify_ab_straddle_mismatch`. Thus shape/dtype errors or non-finite output can satisfy the expected-mismatch requirement while `verify_ab_mismatch` remains zero.

Executing the actual extracted methods with a shape-invalid straddle produced:

```text
verify_ab_straddle_blocks=1
verify_ab_straddle_mismatch=1
verify_ab_mismatch=0
```

Minimal fix: retain validity separately from bit differences; invalid outputs must fail G1a even on straddles. Preserve one batched materialization. Add invalid-straddle tests. The corresponding **self-test** validity checks are correctly fixed.

**P3 — Closure table**

“Inspected” means implementation and regression assertions checked, but the full test could not execute here. Paths below are repository-relative; fork tests are under `mlx_vlm/tests`, stack tests under `benchmark/bench/tests`.

| Closure | Code + test evidence | Result |
|---|---|---|
| B1/B2: coverage, complete journals, mandatory identity, request hashes, legacy exit | `parity_replay.py:382,477`; `test_parity_replay_ac11.py:341,371,403` | **Verified** with in-memory cases; D1/D2 remain |
| B3: closed scan values, unknown refusal, override protection, manifest validation | `provenance.py:890,939,1620,1659`; `test_mtp_verify_scan_provenance.py` | **Verified** pure cases; integration inspected |
| Cleanup validates all models before deletion | `generate.py:318`; provenance test `test_r3_d2_valid_then_unresolved_model_deletes_nothing` | Inspected, fixed |
| B4: authentication including preload | `client.py:41`; `parity_replay.py:49`; AC11 auth tests | **Verified**, three existing tests |
| B5: C106, original error, drift stamps, interrupts, completion tail | `parity_replay.py:198,220,296,373`; AC11 tests `:505,930,1052` | Inspected, fixed |
| Resume: clean aborted allowed; drift/status/hash/runtime/code mismatch refused | `parity_replay.py:135`; AC11 tests `:590–688,868` | **Verified**, seven in-memory checks |
| B6: loaded/resolved MTP drafter guard | `server/generation.py:1544`; `test_mtp_verify_scan.py:1189` | Inspected, fixed |
| B7: self-test validity and finite known positive | `mtp_verify_scan.py:548`; fork tests `:1241,1877` | Inspected, fixed |
| B8: deferred AB counters, exception cleanup, original exception | `mtp_verify_scan.py:350–384`; verifier `:406`; fork tests `:1278` | Inspected, fixed; D3 separate |
| B9/B10: device agreement and real mirror | `mtp_verify_scan.py:251,313`; fork tests `:1395–1484` | **Verified** mirror: 208 cells, 44 mismatches, exact leading positions |
| B11/AC8: genuine acceptance and final drafter/cache state | `test_mtp_verify_scan_generation.py:276–315` | Inspected; genuine proposals and rejection asserted |
| B12: opt-in provenance pin | stack `tests/conftest.py:85`; unpinned-refusal test | **Verified** pure refusal; no autouse scan pin |
| F4/router: `kv_bits` predicate, real registry and command | fork `require_environment`; router validation/build; golden tests | **Verified** all 11 entries; actual commands equal `main` |
| Golden fixture/REQUIRE/CI fallback | Both `_stack_registry()` implementations and fixture tests | Fixtures **verified** against live registry and recorded SHA; resolution branches inspected |
| Default import, bytes, scope and markers | guarded imports; serializers; AC1/AC5/AC9 tests | **Verified** 16 serializer comparisons and four AC5 checks; import hook inspected |
| AB observation, non-pooling, post-load checks, counter persistence | provenance/resolver, predictor gate, three ladders, generate; dedicated tests | **Verified** pure cases and AB-vs-AB rejection; integration inspected |

**P4 — Evidence limits and residuals**

- Executed: **32 existing pure provenance cases**, **19 additional compare checks**, **7 resume checks**, **3 auth tests**, plus mirror, serializer, registry and scope checks above.
- Router read-only pytest subset: **67 passed**, one sandbox-related `psutil` failure; 119 temporary-file-dependent tests deselected.
- Full pytest verification is **not established**: temporary-file creation is prohibited; fork collection additionally aborted in MLX/nanobind. Stack autouse fixtures require temporary directories.
- Residuals: documented `_step` counter omission; trailing blank line in both verbatim fixtures. Neither is a new closure blocker.
- **ASSUMPTION / unverified:** GPU identity, live readiness and genuine AC8 execution; historical failing-first evidence; remote publication state.

No files changed, no pushes, no prior review files read, and no servers, model loads or port-8000 access.
