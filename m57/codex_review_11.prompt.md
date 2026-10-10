Cold adversarial CODE review of three commits. Read-only: modify nothing, no model loads, no servers, no GPU. If your sandbox cannot
run pytest, review by reading and say so once.

Commits on worktree branch `worktree-agent-a0c55413033380924` of this repo (files under
.claude/worktrees/agent-a0c55413033380924/): `git show 1449e38` (gap 1), `git show d33eba5` (gap 2), `git show c710aaf` (gap 3).
Rules being enforced: AGENTS.md, "Measurement discipline" — the M50 paragraph (every driver/probe REFUSES before its first
read/write/request unless the process owning the router port is an mlx-serve router whose MLX_SERVE_CONFIG is the driver's
registry path; router block in every manifest; C106 exit re-verification: a changed file hash or router pid refuses completion,
stamps `served_config_drift`, nonzero exit) and the C35 `draft_kind` tripwire.

Gap 1: benchmark/run_opencode_probe.py created its scratch directory before the M50 refusal (a test had been failing on main).
       Fix: the router destination check runs in a transient system-temp directory; the workdir scratch root is created after it.
Gap 2: `provenance.registry_draft` raised a plain RuntimeError on a registry/worker `draft_kind` disagreement and `generate.py`
       swallowed it. Fix: it raises `ServingStateError` (a `ServedConfigError` subclass); `run_dsh_probe.py` now re-raises it.
Gap 3: `run_capacity.py`, `run_retrieval.py`, `run_reasoning.py` had no M50 check. Fix: entry check first, `router=` passed to
       `provenance.gather`, exit re-verification before publication (retrieval/reasoning quarantine the result as
       `.refused-<utc>` on drift; capacity writes no manifest and stamps the drift).

QUESTIONS
(a) Gap 1: is anything still read, written or requested before the M50 check in that entry point? Is the transient temp directory
    always removed (exceptions, refusal path)? Could running opencode's `debug config` in a temp directory resolve a DIFFERENT
    provider baseURL than the real project directory would (config discovery walks up from cwd), making the check verify the wrong
    destination? Compare with how the check ran before commit 3948528.
(b) Gap 2: does turning the C35 RuntimeError into a ServedConfigError subclass now abort any caller that deliberately treated C35
    as best-effort (grep every `except` around `gather`, `current_manifest_lite`, `registry_draft`, including tools and
    scripts outside bench/)? Can it refuse a legitimate run — e.g. a bench router on a draft-stripped overlay while the driver's
    MLX_SERVE_CONFIG points at that same overlay (must pass), or a worker still loaded with a previous model?
(c) Gap 3: in each of the three drivers, is the entry check really before ANY read/write/request, and is the exit re-verification
    before any canonical result or manifest is published? With `--resume` in run_reasoning, does the check interact correctly with
    a manifest/journal from an earlier router (router_history)? Does a drift in run_capacity leave its journal rows in a state a
    grader could consume as valid? Any double-reporting or masking of the original exception?
(d) Tests: do the new tests exercise the real entry points, and do they pin the ORDER (check before first write/request)?
(e) Anything that blocks a healthy run or records false provenance.

DELIVER (markdown, ids C1, C2, ... most severe first, file:line): what is wrong, concrete scenario, consequence, fix; classify
BLOCKING / RESIDUAL. Verdict per gap: SHIP / SHIP-WITH-RESIDUALS / FIX-THEN-SHIP. Under 700 words. No praise.
