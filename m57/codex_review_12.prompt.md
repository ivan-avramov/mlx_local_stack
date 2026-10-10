Cold adversarial CODE review, CONFIRMING PASS. Read-only: modify nothing, no model loads, no servers, no GPU. If your sandbox
cannot run pytest, review by reading and say so once.

Three fix commits on worktree branch `worktree-agent-a0c55413033380924` of this repo (files under
.claude/worktrees/agent-a0c55413033380924/): `git show 1c5c9fd` (your C3: `registry_draft` uses the exact worker identification),
`git show e1dc58c` (your C4: the opencode probe does only one discovery call before the M50 check, with cwd = the existing
STACK_WORKDIR), `git show e3cf4a7` (your C2, C5, C1, C6: `provenance.ExitGuard` shared by run_capacity / run_retrieval /
run_reasoning; capacity quarantines journal AND scorecard on a refused run; reasoning `--resume` requires a compatible provenance
sidecar and records `router_history`). They answer your previous findings C1-C6 on the commits 1449e38, d33eba5, c710aaf.
Rules: AGENTS.md "Measurement discipline" (M50, C106, C35).

Implementer's stated deviations: capacity writes the scorecard before `guard.verify()` so the drift stamp lands on it, then sets
both artifacts aside, and appends a `served_config_drift` event row to a `.jsonl` journal; the resume sidecar manifest is
best-effort (if it cannot be built the sidecar has no manifest and a later resume refuses); the sidecar is written without
`os.replace`; opencode discovery uses `<STACK_WORKDIR>/scratch/m50-discovery-xdg-data` as its data home; if
OPENCODE_PROBE_SCRATCH points outside STACK_WORKDIR the discovery ancestry differs from the item directories; a non-`--resume`
reasoning run still appends to an existing journal and overwrites its sidecar (pre-existing behaviour).

QUESTIONS
(a) Are C1-C6 really fixed?
(b) New defects: does the opencode discovery data-home path create a directory BEFORE the M50 check (that would re-introduce the
    original bug)? Does `ExitGuard` ever swallow or replace an exception, double-quarantine, or quarantine artifacts of a run that
    succeeded? Can the appended drift event row break a reader of the capacity journal? Can the C35 change refuse a healthy
    `generate` run on a normal box (worker for another model loaded; no worker yet; router up but model on-demand and not
    loaded)? Does the resume sidecar refuse a legitimate resume after a router RESTART on the same overlay (new pid, same config
    sha256 — that must be allowed and recorded in router_history)?
(c) Anything that blocks a healthy run or records false provenance.

DELIVER (markdown, ids D1, D2, ... most severe first, file:line): what is wrong, concrete scenario, consequence, fix; classify
BLOCKING / RESIDUAL. One line each for C1-C6. Verdict: SHIP / SHIP-WITH-RESIDUALS / FIX-THEN-SHIP. Under 600 words. No praise.
