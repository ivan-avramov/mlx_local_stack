P1
- Location: `benchmark/bench/p475_kv.py:414-480,687-701`; `docs/specs/p475-stage1-contract.md:15-18,47-51`
- Severity: blocker
- Evidence: confirmed
- Problem: Arm worktrees are pinned to the dispatch base and may differ only in `main_models.yaml`, but the driver and watcher execute from those worktrees. The fixed base `bc3ad13e` lacks the candidate’s `--p475-strict`, capacity watcher, KV parser, and carrier code.
- Failure scenario: An operator honors the contract’s base, runs `prepare`, then a leg. The arm’s `run_capacity` rejects `--p475-strict` and its watcher rejects the P475 options; no record matrix can complete.
- Proposed change: Define the accepted harness commit as the arm parent, while separately pinning the serving registry and gitlinks to the dispatch baseline. Add a precheck that hashes the driver, watcher, ladder code, and carrier in every arm.

P2
- Location: `benchmark/bench/p475_kv.py:45-48`; `src/mlx-vlm/dev/p369_phase2/registry_states.py:264-296`
- Severity: blocker
- Evidence: confirmed
- Problem: N16 removes `kv_quant_scheme`, but the real `--kv-arm` gate accepts N16 only when that key remains exactly as in the fixture.
- Failure scenario: `preflight --arm N16` is refused on every attempt. The reference arm never runs, so ratios, instability analysis, and the complete matrix are impossible.
- Proposed change: Amend N16 to change only `kv_bits: 0`, retaining `kv_quant_scheme: turboquant`; alternatively change and repin the fork gate. Add a test using the real `classify_kv_arm`, not the fake qualify result.

P3
- Location: `benchmark/bench/p475_kv.py:1097-1164,1214-1226`
- Severity: major
- Evidence: confirmed
- Problem: Dossier loading ignores the receipt’s model, base, arm identity, gitlinks, and campaign fingerprint. `block_values` also silently overwrites duplicate usable dossiers for the same arm/block.
- Failure scenario: Old dossiers remain while `state.json` is removed or a new `--base` is supplied. `matrix` can return a canonical table using measurements from another stack revision without running new legs.
- Proposed change: Validate every receipt against `cfg.model`, `cfg.base`, directory leg identity, arm commits, gitlinks, and instrument/config hashes; reject duplicate usable cells and mixed campaign fingerprints.

P4
- Location: `benchmark/bench/capacity_ladder.py:112-153`; `benchmark/bench/p475_kv.py:1148-1164,1214-1272`
- Severity: major
- Evidence: confirmed
- Problem: A rung can be valid with missing or invalid cumulative peak memory and decode rate. Matrix completeness checks only rung contexts, while `_metric` converts absent values to `None`.
- Failure scenario: The backend omits `peak_memory` or `predicted_per_second`; the driver exits successfully, legs are VALID, and a canonical matrix is generated with `—` for required tradeoff metrics.
- Proposed change: Require finite positive `peak_memory_gb_cumulative` and `predicted_per_second` in `rung_problems`, with a defensive matrix-level completeness check.

P5
- Location: `benchmark/bench/p475_kv.py:704-718,929-964,1614-1617`; `benchmark/bench/chain_ops.py:936-969`
- Severity: major
- Evidence: confirmed
- Problem: Driver and router process groups are not verified gone. `_reap_driver` stops as soon as the leader dies, and teardown checks only named leader identities, the port, and heuristic busy-process matches.
- Failure scenario: A driver exits zero while a child in its session survives. The child does not match a busy marker or own port 8000, so the receipt can be VALID despite a surviving process.
- Proposed change: Extend `Ops` with process-group identity/liveness, signal groups while any member survives, and verify both driver and router groups empty after SIGKILL.

P6
- Location: `benchmark/bench/p475_kv.py:968-998,1010-1065`; `benchmark/bench/p426_harvest.py:83-98`; `benchmark/bench/piicheck.py:22-27`
- Severity: major
- Evidence: confirmed
- Problem: Harvest does not detect email addresses. `piicheck` intentionally excludes emails, `p426_secrets.scan` checks credentials only, and P475 never uses `p426_harvest.Gate`. The implementer’s PII test forces a synthetic `_publish` failure instead of testing real detection.
- Failure scenario: A real address appears in a ladder field, manifest, receipt, or log. It survives scrubbing and can enter the committed dossier.
- Proposed change: Run every dossier file through `p426_harvest.Gate.check(..., dest="main")`, configure operator addresses/domains, and refuse non-reserved addresses in evidence intended for publication.

P7
- Location: `benchmark/bench/p475_kv.py:1318-1328,1454-1506`
- Severity: major
- Evidence: confirmed
- Problem: `blocks` is treated as a monotonic resume cap, while the deciding block is recomputed as `blocks + 1` instead of persisted.
- Failure scenario: An unstable two-block run completes deciding block 3. Resuming with `--blocks 3` reclassifies block 3 as ordinary, removes its deciding column, and may designate block 4 instead.
- Proposed change: Persist the measurement-block count and deciding-block identity. Refuse changing `--blocks` after any leg exists, or separate it from monotonic retry caps.

P8
- Location: `benchmark/bench/p475_kv.py:1214-1272`; `.p475-review/frozen-tests/test_matrix.py:115-125`
- Severity: major
- Evidence: confirmed
- Problem: Generating a partial matrix does not remove or quarantine an existing canonical matrix. The frozen test explicitly deletes the canonical file before testing the partial path, masking this.
- Failure scenario: A complete matrix exists, then a dossier is removed, corrupted, or refused. Regeneration returns nonzero and writes `.PARTIAL.md`, but the stale canonical file remains available for citation.
- Proposed change: Ensure exactly one current matrix artifact exists; atomically retire the alternate canonical/partial path and test complete-to-partial transitions.
