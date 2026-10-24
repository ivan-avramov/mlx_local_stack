- Location: `benchmark/bench/tests/p371_baseline/bundle.py:17-29,78-88`; `benchmark/bench/tests/test_p371_baseline.py:72-76`  
  Severity: major  
  Problem: The immutable `0c9bd32a` baseline bundle now silently replaces four archived carriers with arbitrary current-tree bytes while still recording only the baseline commit. The new test merely confirms this self-reference.  
  Failure scenario: A later surviving-model sampling, capability, or limit change is supplied to both differential sides; regenerated goldens pass and conceal the carrier regression. Dirty working-tree bytes can likewise be blessed as baseline. Three overlaid carriers are not even used by the tg1 scenarios.  
  Proposed change: Overlay only a pinned post-P476 tg1 fixture, assert its hash and exact six-record removal diff, and record the override in the manifest; alternatively preserve the archived carrier and explicitly rederive the permitted identity-field transitions.

- Location: `benchmark/bench/tests/test_registry_published_set.py:30-69`  
  Severity: major  
  Problem: The “every model id” test only recognizes IDs beginning with Qwen, gemma, Ornith, or NVIDIA. Unknown-family IDs are ignored rather than rejected.   <!-- allow-shorthand: verbatim reviewer output -->
  Failure scenario: A generated client accidentally exposes `DeepSeek-*` or `Mistral-*`; configgen drift checks and this test pass, but the client sends an unserved model and receives a routing failure.  
  Proposed change: Extract IDs from each carrier’s structural model-bearing fields instead of guessing IDs with a family regex.

- Location: `openwebui-init/model_settings.json:14-21`; `configgen/emitters/owui.py:87-90`  
  Severity: minor  
  Problem: Tombstone generation reorders the unchanged `excluded_model_ids` set, contradicting AC2’s removal-only generated-file diff requirement. Set-based tests miss the byte drift.  
  Failure scenario: The certification’s byte-diff audit rejects the generated policy despite identical runtime semantics.  
  Proposed change: Preserve the prior ordering or explicitly amend AC2 to permit this reorder.

- Location: `benchmark/bench/tests/fixtures/m59_policy.json:22`  
  Severity: minor  
  Problem: `_p476_refresh` adds a new fixture-schema field although S3b permits only carrier-derived pins to move. Existing consumers ignore it by selecting named keys.  
  Failure scenario: A strict or full-object fixture consumer rejects the unexpected field.  
  Proposed change: Move the old→new note into `test_m61_web_audit.py` comments and leave the JSON schema unchanged.
