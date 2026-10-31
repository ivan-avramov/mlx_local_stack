# P579 / P580 — cold review (opinion, round 1 of 1; C263)

Member: `sol`, cursor-agent, `gpt-5.6-sol-high`, context `briefed` (the commit diff `2612a856`, the inventory code, its receipt consumer, spec 6.4–6.5), user instructions unconfirmed (cursor-agent); exit 0. No verify round (C263: one cold review).

| # | Finding (sol) | Severity / evidence | Disposition |
|---|---|---|---|
| P1 | A non-editable local install's in-site-packages `direct_url.json` names its worktree; not canonicalized | major / confirmed (trace) | **Declined**: fails closed (a false systemic stop, never a hidden difference); none of the three real venvs has one — their inventories compare equal across the arms. Residual. |
| P2 | The actual-digest cache ignores the RECORD algorithm | major / confirmed | **Adopted**: digests cached per (path, algorithm), each claimant compared with its own; red-first test. |
| P3 | Substring replacement canonicalizes sibling paths that start with the worktree root (`<WT>-cache`); literal `<WT>` collides | major / confirmed | **Adopted**: the root is replaced only at a path boundary (followed by `/`, a quote, whitespace, NUL or the end), by a NUL-delimited token; red-first test. |
| P4 | Outside-site-packages files read whole into memory | minor / confirmed | **Adapted**: canonicalized only up to 1 MiB (console scripts); larger files stream-verified and keep their RECORD digest. |

After the fixes: the real arms' three venvs inventory equal (`.venv`, `.venv-bench`, the fork venv); B2 test files 1511 passed, 2 skipped.
