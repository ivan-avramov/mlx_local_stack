- Location: `dev/p369_phase2/qualify.py:382-413`; `mlx_vlm/tests/test_p475a_qualify_kv_arm.py:522-533`  
  Severity: major  
  Problem: The arm-specific attention change is global, violating the requirement that behavior without `--kv-arm` remain byte-for-byte unchanged.  
  Failure scenario: A normal no-flag Fable qualification missing its manifest and reporting `sdpa_forced == 0` previously reported both failures; it now reports only the missing manifest. The new test explicitly pins this changed behavior.   <!-- allow-shorthand: verbatim reviewer output -->
  Proposed change: Pass `kv_arm` into `request_problems` and use manifest-derived attention only for arm runs; preserve the original no-flag assertion.

- Location: `docs/specs/p475a-qualify-kv-arm.md:43`; `review/implementer_report_fix.md:24-29`  
  Severity: major  
  Problem: Acceptance criterion 3 remains unmet: the full suite ran once rather than twice with compared skip lists, and none of the eight audits ran.  
  Failure scenario: Skip-list nondeterminism or an audit failure is discovered only when preparing the real ten-arm campaign, despite the change being treated as finished.  
  Proposed change: Complete the second full-suite run, compare skip lists, and run all eight required audits before acceptance.
