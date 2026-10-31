P1 — Not resolved as claimed  
- Location: row 11; `reviews/cleanup-verify-r1/**` → `docs/reviews/cleanup-2026-10/**`
- Severity: blocker
- Evidence: confirmed. `main-docs-reviews.paths` contains no cleanup archive, and that destination does not exist on local `main`.
- Problem: the verification evidence remains only under `reviews/`. Removing `reviews/` from row 11 prevents immediate loss, but filing is not complete.
- Failure scenario: `reviews/` is later re-added based on the incorrect “filed” assertion, destroying the cleanup certification.
- Proposed change: keep `reviews/` excluded until the complete verification directory is committed and confirmed with `git ls-tree main`.

P2 — Resolved  
The P475/P475a review texts are on local `main`; 18 code/draft/script files are on local `evidence` commit `05161ba0`. Existing duplicate P476 and B2 material was also traced.

P3 — Resolved  
Full enumeration found 702 arrays under deletion targets: 330 on HF, 240 in `npz-upload.list`, and exactly 132 package fixtures under the four documented virtual environments. All paths and sizes matched; evenly spaced SHA-256 samples of 12/330 existing and 12/240 pending arrays matched.

P4 — Resolved  
Full path comparison confirms the revised exceptions:
- Row 2: nine suite files, one rehearsal transcript, six manager logs, five lock copies.
- Row 3: 1,202 scratch files under `tmp/`.
- Row 7: 51 DB/index pairs plus 918 generated `.git` files.
- Row 11: 332 HF-cache files, eight download files, six trivial C147 scratch files.

P5 — New finding  
- Location: deletion gate; rows 1, 4 and 10
- Severity: major
- Evidence: confirmed. Local `main` is four commits ahead of `origin/main`. The origin lacks `docs/reviews/b2/**`, `docs/reviews/parked/**`, `benchmark/results/c249/**`, and the latest P541/P542 build records.
- Problem: the gate requires the evidence push and HF upload but omits the pending `main` push, contrary to the stated GitHub-backup requirement.
- Failure scenario: cleanup completes after only the documented gates; the sole remote still lacks filed reviews and results.
- Proposed change: also require and verify `main == origin/main` before deletion.
