D1 — HIGH — `mlx_vlm/server/generation.py:2793-2797,3032-3039`; `mlx_vlm/speculative/common.py:390-404`  
Problem: Published counters are not per-request under continuous batching. They snapshot and diff drafter-global lifetime counters; the helper explicitly says attribution is exact only at batch size 1. Production defaults to unbounded concurrent sequences.  
Failure scenario: Request B joins while A is active. A’s counters include B’s rounds, while B excludes A’s earlier rounds. Overlapping values can be duplicated or misweighted yet pass reconciliation and `accepted <= proposed`, silently corrupting acceptance. P426’s serial chain may avoid this, but the production claim does not.  
Fix: Track speculative rounds/proposed/accepted per UID and attach that row’s totals to its terminal token. Alternatively, enforce and verify `max_num_seqs=1` whenever this telemetry is authoritative, while documenting the limitation.

D2 — MEDIUM — `mlx_vlm/tests/test_p426_draft_counters_log.py:92-124,149-181`  
Problem: The end-to-end tests manually place perfect counters on a fake generator’s terminal token. They prove endpoint plumbing, not the real `ResponseGenerator` snapshot, cached-session, or continuous-batch paths. The fake even labels itself `cached_session` without invoking that path.  
Failure scenario: Final-token extraction becomes absent, stale, or cross-request contaminated while every new test remains green. Back-to-back no-draft requests on an MTP worker, overlap, cancellation, errors, and streaming disconnects are untested.  
Fix: Exercise real worker plumbing through the endpoint and log: cached and continuous paths, overlapping requests, ON followed by no-round/OFF, zero acceptance, and cancellation/error behavior. Also assert the complete MTP-OFF log line and response body remain identical.

No endpoint omission found: pinned opencode uses OpenAI-compatible `/v1/chat/completions`; `/responses` is also covered. Images, audio, embeddings, reranking, and decisions do not run the autoregressive drafter and are correctly out of scope. The production diff does not alter generation arguments, response construction, or numerics, and fork markers are consistent.

VERDICT: DISAGREE D1,D2