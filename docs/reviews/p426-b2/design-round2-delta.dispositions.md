# P426 B2 — design review round 2 of 3 (delta: [o4], §16, C238) — dispositions

Spec v3.2 `ba8d7317` → `[d2]` changes (applied once, NOT re-reviewed). Round 2 of AGENTS.md's three after the operator's reset (C238).
Panel 2026-10-27 ~18:45Z, context `checkout` (read-only copy at `ba8d7317` + the v3.1 → v3.2 diff):

| Member | Runtime | Model | Session | Status |
|---|---|---|---|---|
| sol | cursor-agent `--mode ask` (user instructions unconfirmed) | `gpt-5.6-sol-high` | `57f7b2a7-1608-498d-9a94-d57feb3ba1e9` | returned |
| glm | cursor-agent `--mode ask` (user instructions unconfirmed) | `glm-5.2-high` | `f24dd5bb-cce6-4683-8041-ada12c409c3b` | returned |

Claude Sonnet sat out: it implemented slices s1–s4.

| # | Finding (raised by) | Disposition | Why |
|---|---|---|---|
| 1 | The allowed environment differences are generated from R1's observation, which is circular (sol P1, blocker; glm F7) | **adopted**: a closed list in §6.5; R1 only confirms a subset | Otherwise an unintended arm difference seen in R1 would be permitted forever. Introduced by [o4]. |
| 2 | Credential-key presence is recorded globally, not per process (sol P2) | **adopted**: per process | C238 meant presence per process. |
| 3 | The dossier path is not versioned, so a rerun cannot publish (sol P3, blocker) | **adopted**: `<pair>__off-a<n>__on-a<m>.json`; `sequence.json` selects | Introduced by [o4]'s attempts. |
| 4 | "All records immutable" contradicts mutable state and journals (sol P4) | **adopted**: three record classes | Literal contradiction; resume needs mutable state. |
| 5 | Staged publication has no single commit point (sol P5) | **adopted**: evidence first; the `main` rename carrying `HARVEST.json` is the commit point; retry deletes only its own attempt | Otherwise a crash leaves an unrecoverable half-published destination. |
| 6 | Sources outside the leg root cannot be named; the frozen records are not harvested (sol P6) | **adopted**: typed sources; `publish_run_files` | Introduced by [o4]'s extra roots. |
| 7 | Scrubbing changes self-hashed records (sol P7) | **adopted**: portable paths at creation; a scrub change to a `main` record fails the harvest | Otherwise B8 rejects its own evidence. |
| 8 | The dossier's arrays are unordered by arm; s2 runs ON → OFF (sol P8) | **adopted**: keyed by arm | Otherwise the sign of ON − OFF flips. |
| 9 | The dossier has no publication interface (glm F1) | **adopted**: `publish_dossier` (with #6) | Same gap as #3 and #6. |
| 10 | `p426_dnf` fields `pick` / `load_gen` / `invocation` / `attempt` are undefined, and their writer is unassigned (glm F2) | **adopted**: defined; the chain derives `attempt` from its out-root `<leg>.a<n>` | Otherwise B8's binding of DNFs to attempts breaks. |
| 11 | The hook signatures have no default (glm F3) | **adopted**: `context=None`, as built in s3 | Legacy hooks must keep working. |
| 12 | A DNF table cell says "the row's session" (glm F4) | **adopted** | Contradicted §4.3's own introduction. |
| 13 | `proc_argv` is missing from the seam list (glm F5) | **adopted**: the seam list is the union | Clarity. |
| 14 | The `D` clarification names a per-request fork function (glm F6) | **adopted**: restated in aggregate terms | `ΔD` is an aggregate. |
| 15 | `invalidate`'s vocabulary membership is ambiguous (glm F8) | **adopted**: hook vocabulary only, no slot disposition | Follows the `pre_spawn_incident` precedent. |
| SR | `ops.harvest` returns the `HARVEST.json` sha (glm S1); the occurrences file is unordered (glm S2) | **adopted** | The dossier needs the sha; the input order must not matter. |
