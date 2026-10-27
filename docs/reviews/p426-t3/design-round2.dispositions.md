# P426 T3 — design review round 2 of 3 (the [o1] changes of v2) — dispositions

Spec v2 `708a222d` → v2.1 (changes marked [r2], not re-reviewed). Round 2 of AGENTS.md's three: the operator reset the rounds, and
the side agent's note showed that the v2 changes were unreviewed. Panel 2026-10-27 18:03–18:07Z, context `checkout` (read-only copy +
the S′ fork + the v1 → v2 diff):

| Member | Runtime | Model | Session | Status |
|---|---|---|---|---|
| sol | cursor-agent `--mode ask` (user instructions unconfirmed) | `gpt-5.6-sol-high` | `7e88b5c8-b03f-4422-b2dd-77e0e95d094a` | returned |
| glm | cursor-agent `--mode ask` (user instructions unconfirmed) | `glm-5.2-high` | `ee148dde-8d88-4247-91ce-7b728a57c6be` | returned |

Claude Sonnet sat out: it is the planned T3 implementer.

| # | Finding (raised by) | Disposition | Why |
|---|---|---|---|
| 1 | `production_ref = mlx_vlm` is refused by the fork's `resolve_production_ref` (strict ancestor) (sol P1, blocker) | **adopted**: `production_ref` = `b26fa7c9` | Confirmed: `orchestrate.py:1231–1251`. Every S′ M1 leg would have refused. `b26fa7c9..c688e722` changes `handoff.md` only. Introduced by v2 [o1]. |
| 2 | `qualify` writes `overlay-<entry>.yaml` even for a committed ON registry, against C218's "no overlay files" (sol P2, blocker, settled constraint) | **adapted**: the leg asserts the copy is byte-identical to the ON worktree's registry; **operator ask P504** | Confirmed: `qualify.py:984–985`. Changing the fork is out of T3's scope. P471 / P472 accepted the same "same bytes from another path" for M1. |
| 3 | "Tree clean" counts untracked outputs, so every leg is dirty at exit (sol P3) | **adopted**: tracked changes only, as K2 does today | Otherwise every correct leg is invalidated. Introduced by v2. |
| 4 | The restore-diff check is path-level only (sol P4) | **adopted**: patch-level | C218 requires exactly the restore. |
| 5 | The local-gate change is described, not directed, and a fixed 8-audit tuple cannot be "per sha" (glm F1, F2) | **adopted**: a directed code change; `.upstream-sync-ref` first; audits derived from the fork's `dev/ci.py` | Confirmed: `local_gate.py:34–35, 228–229`. |
| 6 | The naming exemption is stated as a property, but the code matches only `wave1/` (glm F3) | **adopted**: a directed change with the regex | Confirmed: `modelnames.py:270–278`. The first S′ evidence commit would be refused. |
| 7 | Requiring `--build` hides one existing test's guard (glm F4) | **adopted**: that test gains `--build s` | Keeps its coverage. |
| 8 | Per-arm head selection is unstated; a missing `stack_head` compares `None == None` (glm F5) | **adopted** | A wrong worktree head would pass silently. |
| SR | List the stack files T3 changes (glm S1) | **adopted** | Cheap clarity. |
