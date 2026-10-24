- Location: `review/` package premise  
  Severity: major  
  Problem: The promised frozen tests, implementer report, and test-writer report are absent; only two diffs and two prior reviews exist.  
  Failure scenario: Final sign-off cannot verify the claimed test runs, skip lists, or frozen-test coverage.  
  Proposed change: Include the frozen tests and both reports in `review/`.

- Location: `mlx-vlm/dev/p369_phase2/registry_states.py:3-8`; `mlx-vlm/mlx_vlm/tests/test_mtp_verify_scan.py:1732-1734`  
  Severity: minor  
  Problem: Provenance still describes the fixture as stack `59d7802f`, parsed-identically/comment-only, although P476 materially removes six entries and adds tombstones.  
  Failure scenario: A maintainer reconstructs or audits the fixture from the wrong registry epoch.  
  Proposed change: Update both descriptions to the substituted P476 stack commit and accurately describe the structural changes.

- Location: `mlx_local_stack/configgen/source.py:97-108`; `configgen/emitters/owui.py:87-90`  
  Severity: minor  
  Problem: `retired_model_ids` does not require unique, non-empty IDs; duplicate tombstones are emitted repeatedly because the comprehension deduplicates only against pre-existing exclusions. Tests cover live-ID collisions but not duplicate or empty values.  
  Failure scenario: A malformed registry silently generates duplicate/meaningless OWUI exclusions instead of failing `configgen check`.  
  Proposed change: Reject empty or duplicate retired IDs in `load_source` and add disconfirming tests.

- Location: `mlx_local_stack/benchmark/bench/tests/p371_baseline/bundle.py:3-43,91-108`  
  Scope request: The candidate permanently changes the pre-P371 bundle by overlaying two post-P476 carriers and adds committed carrier copies. S3b specifies refreshing carrier-derived pins/goldens but does not authorize this standing mixed-epoch bundle mechanism. Amend S3b to explicitly approve and document it, or rederive the affected carrier fields and remove the overlay.
