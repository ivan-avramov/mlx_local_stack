Cold CODE review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). Fork `../mlx-vlm` (read-only), branch
`p426-b1-draft-log`: red `1b52d3a8` (tests only) and green `c37a7d5e` on top of `494aea2c`; review with
`git -C ../mlx-vlm diff 494aea2c c37a7d5e` and `git -C ../mlx-vlm show <sha>:<path>`. Spec: build B1 of
`docs/specs/p426-fable-mtp-recert.md` (this STACK repo, §9) — a PRODUCTION, log / metrics-only change: thread the per-request
drafter counters (`draft_kind / draft_rounds / draft_n / draft_n_accepted`, already accumulated in `GenerationMetrics`) into
`_build_metrics_envelope` at every call site that passes the M58 `verify_counters`, so `/metrics` and the `Request completed` log
line carry them; absent when no drafter ran (MTP-OFF lines byte-identical). The P426 re-certification will parse these log lines
as its per-request acceptance / speed instrument on opencode chains (§6 T2: per item, tokens ÷ summed decode time; acceptance =
summed accepted ÷ summed proposed) with exact reconciliation (every probe request has exactly one record). Gate so far: fork suite
×2 6775 passed / 17 skipped, identical skips; eight audits green.

Review adversarially: (1) can a drafted request's record be missing, duplicated, stale (counters from a previous request, the
cached-session path, retries, cancellation, errors, tool-call continuation, streaming disconnects) or wrong (`draft_n` vs
`draft_n_accepted` semantics, the zero-acceptance case, a drafter-free request on an MTP worker); (2) is any generation path,
response body or numerics changed; (3) every endpoint the opencode client can reach (check what `opencode` sends: chat
completions / responses) and any envelope call site missed (images, audio, embeddings, decisions are out of scope — say if one
should not be); (4) test gaps (do the tests prove the end-to-end path the real worker takes, or only the fake generator's?); (5)
fork-marker / upstream-parity conventions. Findings ids D1 onward (or say none), each: severity, file:line, problem, failure
scenario, fix. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`. OUTPUT RULE: your FINAL message must
contain EVERY finding in full, then the VERDICT line.
