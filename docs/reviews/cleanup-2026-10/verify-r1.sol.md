P1
- Location: Row 11 — `reviews/cleanup-verify-r1/sol/**`.
- Severity: blocker.
- Evidence: confirmed. Thirteen listed audit inputs are absent from local/origin `evidence`; `BRIEF.md`, `citations.txt`, `rulings.md`, `worktrees.txt`, and `fork-branches.txt` are additionally missing from `workdir-files.list`.
- Problem: deleting `reviews/` would destroy the cleanup’s verification bundle and review results.
- Failure scenario: after cleanup, the deletion approval cannot be reproduced or audited.
- Proposed change: keep this review directory until all three rounds and the final disposition are committed.

P2
- Location: Row 10 — `parked/session7/{p475-change-round3.glm.md,p475-change-round3.sol.md,p475a-change-round2.glm.md,p475a-change-round2.sol.md,p475a-test-writer-after-fix1.md}`.
- Severity: blocker.
- Evidence: confirmed. `parked/` is excluded from evidence, and these five substantive reviews have neither matching blobs nor their distinctive contents on `main`; only earlier P475/P475a rounds and P476 artifacts are filed.
- Problem: “reviews filed” is false for later P475/P475a verification evidence.
- Failure scenario: deletion removes the findings that explain why those candidates were rejected or superseded.
- Proposed change: file scrubbed copies under `docs/reviews/p475*/parked/` before deletion.

P3
- Location: Rows 4 and 6 — `p542/fork/mlx-vlm/.venv/**` and `p369/fork-{1cce312f,a4cd07e0,fd67082a}/.venv/**`.
- Severity: minor.
- Evidence: confirmed. There are 132 arrays absent from HF and `npz-upload.list`: 33 under P542 and 99 under the three P369 forks. All are NumPy/SciPy package fixtures under `site-packages`, not experiment outputs.
- Problem: the literal claim that every deleted array is published is false.
- Failure scenario: exact virtual environments require package reinstallation rather than dataset restoration.
- Proposed change: explicitly exempt `.venv/**/site-packages` arrays from the publication rule.

P4
- Location: Rows 2, 3, 7, and 11.
- Severity: minor.
- Evidence: confirmed:
  - Row 2 additionally omits 6 temporary manager logs and 5 UV locks.
  - Row 3 omits 1,202 files, all under `tmp/`.
  - Row 7 omits 51 database/index pairs plus 918 generated scratch `.git` files—not the stated 56.
  - Row 11 additionally omits 332 HF cache metadata files and 8 download logs.
- Problem: the “on evidence except…” descriptions are incomplete.
- Failure scenario: an operator expecting exact scratch restoration discovers these transient files were never archived.
- Proposed change: enumerate these transient/generated exceptions in the table.The cross-check completed successfully. It produced no additional findings beyond P1–P4 above; no follow-up action is needed.
