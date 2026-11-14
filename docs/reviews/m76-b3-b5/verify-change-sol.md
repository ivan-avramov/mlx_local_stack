Disposition audit

P1 Resolved — A5 uses axis-specific tunes/stems; populated-directory coverage exercises A4 followed by A5.

P2 Not resolved in this snapshot, as stipulated — `benchmark/results/m76/ids.json` remains a required designer-generated artifact before execution.

P3 Resolved — signals call B7’s `axis_verdict`; every `size_warning` becomes blocking.

P4 Resolved — A7 derives planned sessions from B7, supports `s3`, and refuses incomplete planned evidence.

P5 Resolved as framed — KV export, freeze, judge, seal, B8 binding, and two-family enforcement exist. P16–P17 identify remaining workflow defects.

P6 Resolved — any rejected planned key now rejects its Wave-1 or A7 pair.

P7 Resolved in code — exact prompt counts and row-specific resolved budgets are frozen and verified; operational use awaits P2.

P8 Not fully resolved — Wave-1 compares complete normalized provenance, but A7 does not. Detailed below.

P9 Resolved for B3 — stage-4 V workflow remains deferred, and V sequences refuse during preflight.

P10 Resolved/adapted — V and missing X M1 bindings refuse before launch.

P11 Resolved — decode uses P426’s T2 estimator.

P12 Resolved — the specified Python functions expose `lever=`.

P13 Resolved — verify and panel expose top-level `--lever`.

P14 Not resolved in the frozen test snapshot — product behavior preserves `s`/`s2`, but the test-writer’s golden amendment remains external/pending.

P15 Resolved — A5 panels only chain-4 both-correct pairs under the reasoning rubric and explicitly exclude retrieval.

Remaining findings

P8  
Location: `benchmark/bench/p426_verify.py:1899-1976`, contrasted with `:1633-1669`  
Severity: major  
Evidence: confirmed — traced in source  
Problem: A7 validates harvest hashes, schedules, receipts, seeds, and dossiers, but never loads or compares the arms’ generation provenance manifests through `kv_provenance_problems`.  
Concrete failure scenario: one A7 arm runs with a different sampling profile, runtime control, serving-path hash, or fingerprint version. Its independently hashed harvest remains valid, so the session pair can be accepted despite violating the full-provenance contract.  
Proposed change: load each arm’s published per-invocation provenance manifests, normalize and compare them using the explicit KV/commit whitelist, and reject the session pair on any other difference.

P16  
Location: `benchmark/bench/p426_panel.py:1352-1396`, `:1655-1718`, `:1460-1521`  
Severity: major  
Evidence: confirmed — Wave-1 prompts and A3 attachments are arbitrary caller-provided mappings; only presence and identity-leak checks are performed. Tests successfully freeze synthetic prompts.  
Problem: packet hashes prove only that an arbitrary packet stayed unchanged, not that its task prompt or attachment belongs to the B8 item being judged.  
Concrete failure scenario: a stale or mis-keyed A2 prompt is supplied for a valid item ID. The correct arm outputs are judged against the wrong task, yet the resulting panel remains frozen and B8-bound.  
Proposed change: derive packet inputs from B8-covered benchmark artifacts, or require a source artifact with per-item prompt/attachment hashes and validate and freeze that mapping.

P17  
Location: `benchmark/bench/p426_panel.py:1731-1763`; `benchmark/bench/p426_signals.py:1460-1493`, `:1628-1633`  
Severity: major  
Evidence: confirmed — absent member directories are silently skipped; missing, unsealed, or failed verdicts only reduce `judged`; signals add no incomplete-panel status or blocking flag.  
Problem: supplying an empty or partial panel root produces an apparently present panel family rather than a pending/incomplete panel.  
Concrete failure scenario: `--panel` points to a directory containing only A2, or only unsealed verdicts. Signals emit no completeness failure and may show no adverse panel flag.  
Proposed change: require every B8-expected member and frozen judge×order verdict slot for a completed panel, or emit an explicit blocking `panel_incomplete` state; expose partial ingestion only as an explicit mode.

P18  
Location: `benchmark/bench/p426_panel.py:1604-1611`  
Severity: minor  
Evidence: confirmed — rejected-pair exclusions include `rec["keys"]` but omit `rec["keys_rejected"]`.  
Problem: exclusion accounting drops precisely the missing or seed-mismatched keys that caused rejection.  
Concrete failure scenario: one key has a seed mismatch; the block is rejected, but its panel exclusion count is one short.  
Proposed change: include and deduplicate both accepted and rejected key lists when recording a rejected pair’s exclusions.
