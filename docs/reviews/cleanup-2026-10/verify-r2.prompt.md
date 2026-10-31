# Verify — round 2 of 3 (follow-up to BRIEF.md, same request, constraints and contract) — the deletion table

Since round 1: `evidence-local.paths` is refreshed (a new local `evidence` commit `05161ba0` adds `parked/**` code: P475 / P475a / P476 candidate diffs, frozen-test drafts, session-7 scripts, with the home path → `$HOME`, its dash-flattened form → `-$HOME-` and the fixture mDNS hostname → `box.example`); `main-docs-reviews.paths` lists `docs/reviews/**` on `main` (new: `docs/reviews/parked/**`, the review texts with no earlier filed copy — 30 files filed, 23 skipped as byte-duplicates of filed files).

## Round-1 findings and their dispositions
1. P1 — deleting `reviews/` destroys this verification: adopted. `reviews/cleanup-verify-r1/**` is filed under `docs/reviews/cleanup-2026-10/` before any deletion; `reviews/` is removed from row 11 until then.
2. P2 — later P475 / P475a review rounds only in `parked/`: adopted and fixed (see above); row 10 now: "filed (texts on `main`, code on `evidence`) → delete".
3. P3 — 132 arrays under `p542/fork/mlx-vlm/.venv/**` and `p369/fork-*/.venv/**`: adopted as an explicit exemption: package test fixtures inside virtual environments, regenerable from the lock files.
4. P4 — incomplete exception lists: adopted; the table now says, per row: row 2 also loses 6 temporary manager logs and 5 `uv` lock copies; row 3 loses 1,202 files under `tmp/` (scratch); row 7 loses 51 opencode DB / snapshot-index pairs (PII-bearing, never publishable) and 918 generated scratch `.git` files; row 11 loses 332 HF-cache metadata files and 8 download logs.

## Contract
For each round-1 finding, state resolved or not, and why. Then report anything else the table still gets wrong, as BRIEF.md asks; where it says to reply exactly NOTHING OF SUBSTANCE, end with that line instead.
