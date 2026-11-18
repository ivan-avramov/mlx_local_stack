Cold read, round 1 of 3. Read-only. A blind pairwise judge panel (benchmark/bench/p426_panel.py, KV lever: two arms of ONE model
that differ only in KV-cache mode) refuses to export packets whose text matches a leak check (`_kv_leaks`: registry names, KV/arm
identifiers, a model-family token regex, serving-template tags), so judges cannot learn which arm wrote an answer. The real stage-3
A2 member (chat questions judged free-form) refused: 9 of 40 answers name model families as their TOPIC (LLM-deployment questions:
"Qwen2.5", "NVIDIA"). The fix: an item whose ONLY leak kind over (prompt, both answers) is `family-token` is excluded and recorded in <!-- allow-shorthand -->
FROZEN `excluded` under KV_FAMILY_TOPIC_RULE; any other leak kind still refuses at packet writing.
Files here: fix.diff, test_s26_p17_panel_family_token.py. Repo context: p426_panel.py `kv_export`, `_kv_leaks`, `_kv_write_packets`,
`kv_freeze`, `kv_panel_members`, `kv_panel_completeness`; judge_pairwise.py `_FAMILY_RE`, `FAMILY_TOKENS`.
Question: can this exclusion let an identity leak through to a judge, bias the panel in a way that matters for its purpose (a paired
blind preference between two KV modes of one model), or break ingestion / completeness downstream? Is the exclusion decision made on
the same text the packet would show? Numbered findings with severity (blocker / major / minor), file:line, a concrete scenario;
"no findings" if none. Do not modify any file.
