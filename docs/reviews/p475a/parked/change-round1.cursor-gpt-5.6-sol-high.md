- Location: `dev/p369_phase2/registry_states.py:318`, `dev/p369_phase2/qualify.py:14-18`  
  Severity: major  
  Problem: `--kv-arm` is accepted for Qwen3.6, despite “other entries” being a non-goal.   <!-- allow-shorthand: verbatim reviewer output -->
  Failure scenario: `qualify --kv-arm --predictor off --entry Qwen3.6-27B-Opus-Distill-OptiQ-4bit` proceeds with an unreviewed KV arm.  
  Proposed change: restrict KV-arm entries to the two P475 picks in both classifier and CLI validation; add a refusal test.

- Location: `dev/p369_phase2/registry_states.py:285-324`, `dev/p369_phase2/qualify.py:194`  
  Severity: major  
  Problem: fractional TurboQuant widths are accepted, then truncated by `int(values["kv_bits"])`.  
  Failure scenario: `kv_bits: 4.5` is classified valid and served as TQ4.5, but its live manifest is checked against TQ4, failing after the real-weight run.  
  Proposed change: preserve the numeric KV width in `expected_config`; add fractional-width integration coverage.

- Location: `dev/p369_phase2/registry_states.py:242-244,303`  
  Severity: minor  
  Problem: the documented `None` refusal boundary throws on valid YAML with malformed structure or non-finite widths.  
  Failure scenario: `models: [null]` raises `AttributeError`; `kv_bits: .inf` raises `OverflowError`.  
  Proposed change: validate document/model shapes, reject non-finite widths, and return `None`; add adversarial tests.

- Location: `mlx_vlm/tests/test_p475a_qualify_kv_arm.py:253-328`  
  Severity: minor  
  Problem: driver coverage exercises only Fable/AF8 with mocked argv and manifests. The other nine combinations, actual worker served-state check, and real 64-layer topology are untested.   <!-- allow-shorthand: verbatim reviewer output -->
  Failure scenario: a pick-specific argv or topology regression remains green and is discovered only during an expensive real-weight preflight.  
  Proposed change: parameterize the driven path across all ten arms and assert argv, worker KV state, manifest, and attention counters.
