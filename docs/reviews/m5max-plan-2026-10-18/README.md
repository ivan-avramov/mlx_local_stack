# m5max (64 GB) plan review — 2026-10-18

What the 64 GB box should do next after pulling the 2026-10-15 → 18 work from the chain box. Written by the session
lead, reviewed once by codex `gpt-6.1-sol` (review-panel, converge, 1 round; `round1.codex-gpt-6.1-sol.md`), then
closed by the operator's direction the same night: "I will dispatch the actual GPU work on the 128G box. I just wanted
to close up this session." The adopted plan is the ledger below applied to `plan_v1.md`; no v2 was dispatched (changes
not re-reviewed).

Questions to the operator during the review: none. Gate: review-panel. File-load warnings: `~/.config/review-panel/panel.toml`
loaded (members `codex`, `opus`); `opus` not dispatched (same vendor as the driver; the operator asked for codex only). <!-- allow-shorthand: review-panel member names / risk wording / judge model, not registry models -->
Roster: `codex` — runtime codex 0.163.0, model `gpt-6.1-sol`, tier top (declared), vendor OpenAI (declared, observed
`provider: openai`), sealed brief in an empty directory with `~/.codex/AGENTS.md` present (user instructions loaded),
level L3 against the driver. Session id, timestamps and tokens are in the member file.

## Ledger (driver adjudication)

| id | member finding (severity proposed) | disposition | reasoning / adaptation |
|---|---|---|---|
| P1 | R2 makes an upstream fork merge a prerequisite for the reranker build (major) | adapted (major) | Agreed: the upstream sync (61 commits incl. `#2527`) is its own reviewed item with its own re-qualification cost, not a reranker prerequisite. Kept: the reranker still waits for P369's fork push/merge (P372: one fork branch in flight — a settled constraint). Base = the fork head after P369 merges. |
| P2 | R7 excludes whole items from this box on access/phase grounds (major) | adapted (minor) | Correct in principle: only the GPU phases are box-bound; P369 development could run here once `p369-mtp` is pushed (R6a). Moot for now: the operator closed this session and dispatches the work on the chain box. Recorded as the reason R6a matters. |
| P3 | R3-before-R4 orders only this box; unpushed local merges are invisible to the other box (major) | adopted (major) | Rule added to the handoff: a change to a shared runner/scoring file is pushed (on a go) before the other box starts a phase that consumes it; shared-file ownership is named per phase. |
| P4 | the full suite runs before the fetch/rebase, so it describes the wrong candidate (major) | adopted (major) | Rule corrected: fetch, rebase, resolve, THEN the full suite on the frozen candidate; targeted tests only for a change made after that run. |
| P5 | D2 (SearXNG + MCP) deferred without an owner or a completion gate (major) | adapted (major) | Adapter unit completion ≠ integration acceptance; the adapters' contract artifacts list D2-dependent clauses OWED (P374) and the arm is not "built" until the docker-backed checks pass with D2 up. D2 owner: whichever box has docker when the adapters are done (OrbStack can be started here). |
| P6 | R6b reopens the settled C181 ruling without an established delay (minor) | adopted (minor) | R6b withdrawn; C181 stands. |

## Resulting plan (v1 + ledger; not re-reviewed)

Operator decisions: R6a (push `p369-mtp` as a WIP fork branch), R6c (delete merged `m64-build` / `tg2-step2`), R1
(mlx-serve submodule bump to `e6a7a5a`, v0.3.0 — recommended, a serving change, needs a go), pushes. Work for this
box when it reopens: R3 (P383 build), R4 (Pi / dsh adapters, unit completion; D2 integration gated per P5), R5 (per-box
two-judge config and packet tooling), each: worktree → fetch + rebase → full suite on the frozen candidate → codex
review → merge → push on a go, shared files published before the other box depends on them. R2 done (fork docs commit
`f8a91f67`, unpushed); the upstream fork sync is a separate item after P369.
