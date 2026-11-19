P1 — Medium — `benchmark/bench/piicheck.py:115`  
The exemption suppresses every `/home/<username>/` match, not only fictional model-written paths. A packet containing a genuine Linux path such as `/home/alice/private/...` would pass. Anchoring limits eligible files but cannot establish that their content is fictional; macOS hosts do not prove imported prompts/output lack real Linux PII. `/Users/`, flattened paths, tokens, and hostnames remain enforced. <!-- allow-pii-pattern -->

P2 — Low — `benchmark/bench/modelnames.py:48`, `benchmark/bench/modelnames.py:294`  
The whole `FROZEN.json` is exempt, including arbitrary added metadata—not only generated `inputs.*.prompt` values. For example, an authored `"note": "the OptiQ arm regressed"` passes, and `kv_check_frozen` permits unknown top-level keys. SHA binding preserves whatever content was frozen; it does not prove the content was generated. `manifest.jsonl` was already exempt through the general results-JSONL rule.
