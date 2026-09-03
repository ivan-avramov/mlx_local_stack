# docs/ — index (2026-09-03)

Live, in reading order for a cold start:

| file | role |
|---|---|
| `handoff.md` | THE one handoff, rewritten in place each session — read first |
| `PLAN.md` | the backlog / queue (authoritative for what is live); rows M*, D*, C*, H*, S* |
| `open-questions.md` | operator decision queue (O*/C* items; closed items are never deleted) |
| `campaign-results.md` | living results record: dated entries + the scoreboard + comparability rules |
| `lab-notebook.md` | dated history from 2026-08-14 (earlier history: git log) |
| `model-ledger.md` | every model ever considered, status + dated reasoning |
| `metrics.md` | measurement rules and derivations (convergence vector, MDE, bootstrap, seeds) |
| `serving-path.md` | how a request becomes a generation: registry → router → worker; provenance fingerprint |
| `box-notes.md` | box administration, venvs, grading images, corpus facts |
| `regrade-vs-rerun-guideline.md` | the decision rule for re-grading vs re-running |
| `two-box-archive.md` | archived two-box procedures (live again only if a second box returns) |
| `specs/` | design specs for harness/fork work that is queued or landed (`c47-…`, `m29-…`, `switchyard-nvsy-plan.md`) |

Rules live in `AGENTS.md` (repo root). Deleted 2026-09-03 (git history is the archive, last present at
`b723bde`): `docs/superpowers/{plans,specs}/` (June–August design docs), `docs/sketches/` (June session
notes), `docs/work-queue.json` (JSON queue mirror; `PLAN.md` is the only queue).
