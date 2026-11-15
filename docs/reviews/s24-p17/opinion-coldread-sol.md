P1  
Location: `piicheck.py:102-110`; `p426_harvest_excerpt_wave2.py:12-23`; `test_s24_p17_pii_model_output_home.py:16-19`  
Severity: major  
Evidence: confirmed—Wave 2 passes `e.source`, a leg-relative path. `tg1-m76-x-s1.a1/s1/model.s1.opencode_go.L1.full.a1.jsonl` matches none of the exemption globs; only its published `benchmark/results/...` path matches.  
Problem: Wave 2 result rows are missed, so approved fictional `/home/<name>/` content can still stop a leg. The test incorrectly exercises the published destination path.  
Concrete failure scenario: that row contains `{"content":"cd /home/<name>/project"}`; `piicheck.violations(..., path=e.source)` reports it and P426 adds a PII problem.  
Proposed change: classify model-output entries explicitly in P426 and pass that classification to `violations`, or add a narrowly validated Wave 2 result-row source-path matcher. Test the actual leg-relative path.

P2  
Location: `piicheck.py:102-106`; `test_pii_check.py:107-113`  
Severity: major  
Evidence: confirmed—Python `fnmatchcase` does let `*` cross `/`, exactly as the comment says. Consequently, `benchmark/results/*.jsonl` matches every nested JSONL, including paths such as `benchmark/results/receipts/harvest.jsonl` and `benchmark/results/run/tool-log.jsonl`. `*opencode_transcripts/*` also matches `docs/not_opencode_transcripts/receipt.txt` because `opencode_transcripts` is not component-bounded.  
Problem: non-model-output JSONL, tool logs, receipts, and unrelated near-name directories lose `/home/` protection.  
Concrete failure scenario: a harvest receipt under `benchmark/results/**` records `/home/<name>/work`; the checker returns no violation and the real leak can be committed.  
Proposed change: replace generic globs with exact path-component and artifact-type classification. Require an exact `opencode_transcripts` component and distinguish result rows from other result JSONL using P426’s artifact metadata or validated filename/layout rules.

P3  
Location: `test_pii_check.py:107-113`; `test_s24_p17_pii_model_output_home.py:21-46`  
Severity: minor  
Evidence: confirmed—the adjusted existing test remains meaningful only as proof that a non-agentbench `.md` under `benchmark/results/` is checked. It no longer substantiates the claimed narrow JSONL boundary. The new negative list uses `ids.json`, not a non-output `.jsonl`. Tests check `/Users`, flattened paths, and one HF token, but not `sk-`, `ghp_`, AWS keys, or mDNS hostnames within every exempt path class.  
Problem: the suite misses both major boundary errors and incompletely locks down the “all other patterns remain enforced” requirement.  
Concrete failure scenario: broadening suppression to cover hostnames or an API-key pattern inside result rows would not fail these tests.  
Proposed change: add cases for a leg-relative Wave 2 row, non-output result JSONL, near-name transcript directories, commit-diff and harvest call paths, and every non-`/home/` pattern across all three model-output classes.
