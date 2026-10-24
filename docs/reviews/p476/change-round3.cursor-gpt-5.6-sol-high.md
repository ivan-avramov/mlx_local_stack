- Location: `benchmark/bench/tests/test_p371_baseline.py:91-99,580-596`  
  Severity: major  
  Problem: Two tests overwrite tracked carrier files; this is not acceptable. `finally` cannot handle SIGKILL and can overwrite concurrent legitimate edits with stale bytes.  
  Failure scenario: An interrupted or parallel test leaves/observes mutated carrier bytes, corrupting campaign identities or an eventual commit.  
  Proposed change: Run against a temporary repository/worktree or inject temporary carrier paths; never modify tracked carriers.

- Location: `benchmark/bench/tests/fixtures/m59_policy.json:2`; `benchmark/bench/tests/fixtures/answer_key/README.md:16-18`  
  Severity: minor  
  Problem: The refreshed fixture retains provenance commit `22288fc`, whose carrier SHA is `d1a21f…`, while the fixture now pins post-P476 SHA `757121…`. Tests ignore `baseline_commit`, so this inconsistency passes.  
  Failure scenario: Reproducing the frozen identity from its declared commit yields different hashes.  
  Proposed change: Record the P476 carrier commit, or separate the identity-code commit from the carrier-source commit and verify both.
