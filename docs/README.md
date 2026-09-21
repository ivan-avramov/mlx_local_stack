# docs/ — index (2026-09-15)

Live, in reading order for a cold start:

| file | role |
|---|---|
| `handoff.md` | THE one handoff, rewritten in place each session — read first |
| `qualify-a-model.md` | agent-facing playbook for qualifying a NEW model on this stack, stage by stage, commands + thresholds |
| `campaign-supervision.md` | recurring Codex review authority, recovery boundaries and local scheduler operation |
| `PLAN.md` | the backlog / queue (authoritative for what is live); rows M*, D*, C*, H*, S* |
| `open-questions.md` | operator decision queue (O*/C* items; closed items are never deleted) |
| `model-recommendation-evidence.md` | detailed per-language/session evidence and historical comparison tables; current picks remain in the root README |
| `campaign-results.md` | living results record: dated entries + the scoreboard + comparability rules |
| `upstream-integration-2026-09-13.md` | M43 merge/refactor disposition and historical runtime validation; current certification is linked below |
| `transfer-findings.md` | reviewed D14 report: measured local findings, transferable methods and destination-backend remeasurement |
| `memory-guideline-audit-2026-09-13.md` | C79 rough48GB policy correction, session decision audit, and KV/weight precision explanation |
| `lab-notebook.md` | dated history from 2026-08-14 (earlier history: git log) |
| `model-ledger.md` | every model ever considered, status + dated reasoning |
| `metrics.md` | measurement rules and derivations (convergence vector, MDE, bootstrap, seeds) |
| `vision-smoke-m39.md` | M39 spec of record: mechanically graded visual-QA smoke for the seeing contenders (corpus, grading, chain) |
| `judge-panel-c.md` | M38 spec of record: blind mixed-family pairwise judge panel for role C (corpus, anchors, gate, ranking, domain prompts) |
| `serving-path.md` | how a request becomes a generation: registry → router → worker; provenance fingerprint |
| `box-notes.md` | box administration, venvs, grading images, corpus facts |
| `regrade-vs-rerun-guideline.md` | the decision rule for re-grading vs re-running |
| `two-box-archive.md` | archived two-box procedures (live again only if a second box returns) |
| `specs/` | design specs for harness/fork work that is queued or landed (`c47-…`, `m29-…`, `switchyard-nvsy-plan.md`) |
| `model-cards/` | canonical `<full-model-name>/README.md` cards with `evaluation/` evidence, verified publication mirrors plus explicitly pending C89 updates (see `huggingface-c89-prepared-2026-09-14.json`); legacy flat files redirect |

Rules live in `AGENTS.md` (repo root). Deleted 2026-09-03 (git history is the archive, last present at
`b723bde`): `docs/superpowers/{plans,specs}/` (June–August design docs), `docs/sketches/` (June session
notes), `docs/work-queue.json` (JSON queue mirror; `PLAN.md` is the only queue).

- [Stack certification,2026-09-14](stack-certification-2026-09-14.md): final GitHub pins, C85 repair, quality/speed/memory evidence and scope limits.

- [Hugging Face audit,2026-09-14](huggingface-audit-2026-09-14.md):13 repositories, byte parity, local alignment, publication revisions and the historical recipe discrepancy.

- [Shipped native16 depth qualification](native16-depth-qualification-2026-09-14.md): C89 retrieval25/25 and chain-4 tracking39/39, timings and bounded scope.
- [Shipped client configuration audit](client-config-audit-2026-09-14.md): C90 OpenCode corrections and all five carrier checks.

- [OpenWebUI reconciliation repair](openwebui-reconciliation-2026-09-14.md): C93 fixes discovery leakage and deployment verification beyond generated-file checks.

- [DDGS web-search host diagnosis](websearch-ddgs-qualification-2026-09-15.md): provider cadence/burst limits, targeted SearXNG comparison, aggregate evidence and C96 follow-up. Measurements stand; its DDGS-as-default conclusion is SUPERSEDED by the 2026-09-16 qualification below.

- [SearXNG engine qualification](websearch-searxng-qualification-2026-09-16.md): C96 resolution. Picks the shipped keyless engine and pool (`duckduckgo web`, `startpage`, `google`), per-engine liveness and failure mechanisms, pooled burst evidence, security hardening and the retrieval-squeeze changes.
- [Web-search end-to-end gate](websearch-e2e-gate-2026-09-20.md): C97 closure. 10/10 PASS through Open WebUI on the shipped NATIVE tool path (`search_web`/`fetch_url`); corrects the 09-16 report (forced-RAG/`top_k` reasoning does not apply; seed-file `top_k`/loader rows never went live → C98). Public aggregate `websearch-e2e-gate-2026-09-20.json`.
- [Local-index web search](websearch-local-index.md): DEFERRED design. Tier-by-tier feasibility (DevDocs yes at ~0.57 GB, general web no), integration options and the acceptance criterion to pre-register if it is picked up.
