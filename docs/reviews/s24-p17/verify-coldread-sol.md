P1 — Round-1 Sol P1: resolved  
Location: `piicheck.py:107-112`; `p426_harvest_excerpt_wave2.py:12-23`  
Severity: major (round-1; resolved)  
Evidence: confirmed—`^leg:<session>/<stem>$` now matches the leg-relative path passed as `e.source`.  
Problem: the former Wave 2 source-path miss is fixed.  
Concrete failure scenario: `leg:s1/<model>.s1.opencode_go.L1.full.a1.jsonl` containing `/home/<name>/` is now suppressed as approved.  
Proposed change: none.

P2 — Round-1 Sol P2: not fully resolved  
Location: `piicheck.py:113-114`  
Severity: major  
Evidence: confirmed—the regexes are component-bounded, but not root-anchored; they match those components anywhere.  
Problem: `/home/` is also suppressed in non-harvest paths such as `docs/opencode_transcripts/README.md` or `docs/example.final_tree/notes.md`. No convention says every exact-named component anywhere is harvested output.  
Concrete failure scenario: either file contains a real `/home/<name>/project/` path; `piicheck.violations` returns no finding, violating “`/home/` enforced everywhere else.”  
Proposed change: full-match the documented published and leg-relative layouts, or pass an explicit validated artifact kind from the harvester instead of inferring these classes from an unanchored component search.

P3 — Round-1 Sol P3: resolved  
Location: `test_s24_p17_pii_model_output_home.py:15-74`  
Severity: minor (round-1; resolved)  
Evidence: confirmed—the suite now covers leg-relative rows, non-row JSONL boundaries, near-name directories, every other protected pattern, and placeholders.  
Problem: the former coverage gaps are closed.  
Concrete failure scenario: broadening suppression to tokens, hostnames, flattened paths, or near-name directories now fails tests.  
Proposed change: none.

P4 — Round-1 GLM F1: resolved  
Location: `piicheck.py:110-112`; `test_s24_p17_pii_model_output_home.py:31-35`  
Severity: minor (round-1; resolved)  
Evidence: confirmed—depth-2 result rows and structured Wave 2 rows are matched separately; deeper watch and receipt JSONL paths remain protected.  
Problem: the former arbitrary-depth JSONL exemption is removed.  
Concrete failure scenario: `benchmark/results/m76/wave2/<attempt>/watch.jsonl` containing `/home/<name>/` now produces a violation.  
Proposed change: none.

P5 — Round-1 GLM F2: not resolved  
Location: `piicheck.py:113-114`; `test_s24_p17_pii_model_output_home.py:36-38`  
Severity: major  
Evidence: confirmed—the near-name cases are fixed, but exact `opencode_transcripts` and `*.final_tree` components remain exempt at arbitrary roots.  
Problem: this is the same remaining protection leak described in P2.  
Concrete failure scenario: `scripts/opencode_transcripts/setup.sh` containing `/home/<name>/` passes.  
Proposed change: root-anchor these artifact layouts or use explicit harvest classification.

P6 — Round-1 GLM F3: resolved  
Location: `piicheck.py:111-112`; `test_s24_p17_pii_model_output_home.py:18-21`  
Severity: minor (round-1; resolved)  
Evidence: confirmed—both published Wave 2 paths and actual `leg:<session>/<stem>` source paths are covered.  
Problem: the former uncertain harvest-path miss is fixed.  
Concrete failure scenario: both forms now suppress the approved model-written `/home/` value.  
Proposed change: none.

P7 — Round-1 GLM F4: resolved  
Location: `test_s24_p17_pii_model_output_home.py:31-35`; `test_pii_check.py:107-113`  
Severity: minor (round-1; resolved)  
Evidence: confirmed—dedicated controls now cover deeper non-row `.jsonl` files.  
Problem: the adjusted legacy `.md` test no longer carries the boundary alone.  
Concrete failure scenario: exempting attempt journals or deeper receipts now fails the new tests.  
Proposed change: none.

P8 — Round-1 GLM F5: resolved  
Location: `test_s24_p17_pii_model_output_home.py:40-64`  
Severity: minor (round-1; resolved)  
Evidence: confirmed—all eight other pattern classes are tested across every model-output path.  
Problem: the former token, hostname, and flattened-form gaps are closed.  
Concrete failure scenario: suppressing `/Users/`, either flattened form, a token, AWS key, or mDNS hostname now fails.  
Proposed change: none.

P9 — Round-1 GLM F6: resolved  
Location: `test_s24_p17_pii_model_output_home.py:72-74`  
Severity: minor (round-1; resolved)  
Evidence: confirmed—the placeholder behavior is tested both inside and outside model-output paths.  
Problem: the former refactoring coverage gap is closed.  
Concrete failure scenario: `/home/<name>/` becoming reportable in either context now fails.  
Proposed change: none.
