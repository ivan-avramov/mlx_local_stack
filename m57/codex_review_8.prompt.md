Cold adversarial CODE review, FINAL CONFIRMING PASS for the stack part. Read-only: modify nothing, no model loads, no servers, no GPU.
If your sandbox cannot run pytest, review by reading and say so once.

SPEC: docs/specs/m57-attention-policy.md in this repo (Stack section, Amendment 1 S1-S5, Amendment 2 T1-T4).

REVIEW ONLY these two commits on worktree branch `worktree-agent-a6011ca833d3e6e68` (files under
.claude/worktrees/agent-a6011ca833d3e6e68/): `git show 7e6cb82` (serving-state precheck in run_capacity / run_retrieval /
run_reasoning: before the first request, again after the model is loaded, and no longer swallowed at end of run) and
`git show 46af4bd` (the worker is identified as the process listening on the registry's `mlx_port`; unreadable argv refuses).

FACTS: full suite at 46af4bd: 2674 passed, 1 known unrelated failure. A LIVE check with real psutil/lsof passed all three cases:
no stack -> `fused_v1` / source registry; router+worker from the M57 branches -> `fused_v1` / source worker; shipped router that
drops the registry field (worker serves `auto`) -> ServingStateError raised.
Known and accepted, do not re-report: the pre-existing `draft_kind` C35 tripwire is still swallowed by `generate`; these three
drivers have no M50 router check (both reported to the operator); a registry without `mlx_port` identifies no worker.

QUESTIONS
(a) 7e6cb82: can a refusal leave a partial result/journal/manifest behind, or delete something that existed before the run? Does the
    after-load re-check run before ANY measured request in each driver (calibration aside)? Can the new checks abort a legitimate
    run (worker serving a DIFFERENT model than requested while the router is about to swap; a remote base URL; `--no-preload`)?
    Is `ServedConfigError` still swallowed anywhere on these three paths?
(b) 46af4bd: is the port-owner logic correct on macOS (IPv4/IPv6 listeners counted twice? a listener that is the router's child
    vs an unrelated process squatting the port? `lsof` absent or returning nonzero with no listeners — is "no listeners"
    distinguished from "lookup failed"?). Does treating a failed `manager_port` lookup as "router up" refuse runs in an environment
    without `lsof`/psutil permissions where the old code worked (e.g. CI, the test suite itself)? Any place that still uses the
    removed all-process scan?
(c) Anything that records false provenance or blocks a healthy run.

DELIVER (markdown, ids Z1, Z2, ... most severe first, file:line): what is wrong, concrete scenario, consequence, fix. Verdict for the
stack: SHIP / FIX-THEN-SHIP / REWORK. Under 600 words. No praise.
