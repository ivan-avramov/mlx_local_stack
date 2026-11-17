P1 — V1  
Location: `benchmark/bench/p426_wave2.py:1087-1162`  
Severity: major (resolved)  
Evidence: confirmed, source trace  
Status: Resolved. Every sealed file is validated against the current gate, axis, sessions, arms, and selected attempts before recovery, SHA comparison, or acknowledgement. File+record and file-only states stop rc 1 on changed selection; record-only stops rc 1; neither computes once. Outside acknowledgements remain rc 5 until acknowledged, and a prior acknowledgement cannot bypass a later selection mismatch.  
Proposed change: None.

P2 — V2  
Location: `benchmark/bench/corpus_tg2.py:239-246,273-280`  
Severity: minor (resolved)  
Evidence: confirmed, source trace  
Status: Resolved. `spec_text()` now calls `verify_source()`, checking both checkout SHA and item-input hash before reading prompt material. An unchanged exercise under another checkout SHA raises `TransportAbort`.  
Proposed change: None.

P3 — GLM F1  
Location: `benchmark/m62/inject_verify.py:34-48,103-117`; `benchmark/bench/arm_opencode.py:365-373`  
Severity: major  
Evidence: confirmed, source trace  
Status: Not resolved; unchanged by the round-2 diff and still awaiting the operator’s disposition.  
Problem: tg1 verification now accepts a row containing hash-verified `datefreeze`, whereas the baseline required exactly the three original evidence keys. This exceeds the request’s permitted tg1 changes.  
Concrete failure scenario: A real tg1 row carrying `datefreeze_path` and its digest now passes `check_files`; the baseline returned `FAIL:evidence_sha256_keys`.  
Proposed change: Either restrict extended evidence handling to tg2, preserving tg1’s exact three-key contract, or explicitly approve the tg1 widening as a scope request.
