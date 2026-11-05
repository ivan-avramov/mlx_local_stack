Resolution ledger

| Finding | Status | Why |
|---|---|---|
| Sol P1 / TW F4 | Resolved | All five instrument files are byte-compared before startup and hashes are receipted. |
| Sol P2 | Resolved | N16 changes only `kv_bits`; the scheme remains. |
| Sol P3 | Not fully resolved | Receipt/run identity and duplicate slots are checked, but off-plan blocks remain accepted; P3 below. |
| Sol P4 | Resolved | Peak memory and decode rate must be finite and positive; matrix rechecks metric completeness. |
| Sol P5 / TW F3 | Not fully resolved | Normal driver/router groups are checked, but startup identity-capture failures can lose group ownership; P2 below. |
| Sol P6 | Resolved | Every dossier/evidence file passes through the P426 gate. |
| Sol P7 / GLM F5 | Not fully resolved | Plan and deciding identity are persisted, but matrix regeneration ignores the recorded deciding identity; P3 below. |
| Sol P8 | Resolved | Regeneration leaves exactly one canonical or partial matrix. |
| TW F1 | Resolved | Standing INVALID smoke legs stop initial and resumed smoke runs. |
| TW F2 | Resolved | Evidence stage is a protected destination and is never overwritten. |
| TW F6 | Not fully resolved | `run` exits nonzero, but standalone `matrix` returns zero; P4 below. |
| GLM F1 | Resolved | N16 and TQ4 smoke legs record worker environment, telemetry and drafter-key shape; D1 is settled. |
| P651 | Resolved | Watcher argv is receipted and the capacity-rows path is checked. |

Declined GLM F4, GLM F6 and TW F5 retain their original premises. GLM F3 is settled by D2 and the smoke receipts.

P1
- Location: `benchmark/bench/p475_kv.py:1129-1170`, `benchmark/bench/p475_kv.py:1242-1280`
- Severity: major
- Evidence: confirmed, source-traced
- Problem: A VALID dossier can omit `watch.jsonl` or the capacity manifest. Harvest silently skips missing sources, while dossier loading requires only the receipt and one ladder.
- Concrete failure scenario: After a crash, replay finds a VALID receipt and ladder but the watcher journal or capacity manifest has disappeared. It publishes a usable dossier and matrix without the required power/speed or runtime-provenance artifact.
- Proposed change: Require the exact VALID-leg inventory during harvest and loading, including watcher journal and capacity manifest, with every expected file represented in `SCRUB_MANIFEST.json`.

P2
- Location: `benchmark/bench/p475_kv.py:881-884`, `benchmark/bench/p475_kv.py:1923-1934`, `benchmark/bench/chain_ops.py:390-442`, `benchmark/bench/chain_ops.py:738-754`
- Severity: major
- Evidence: confirmed, source-traced
- Problem: Spawned process-group ownership can be lost before `run_leg` receives an identity. `RealOps.spawn` leaks a started driver if create-time capture raises. Failed router startup can clear `handle.router`; its refusal cleanup checks only the leader, not surviving group members.
- Concrete failure scenario: A router wrapper or driver leader exits while a child remains, or identity capture raises after `Popen`. Teardown cannot identify, signal or prove the group empty, leaving a process alive.
- Proposed change: Capture PGIDs immediately at spawn. In P475-specific startup wrappers, clean and verify groups on every exception before discarding ownership; similarly kill/reap the driver group if create-time capture fails.

P3
- Location: `benchmark/bench/p475_kv.py:1323-1384`, `benchmark/bench/p475_kv.py:1463-1479`
- Severity: major
- Evidence: confirmed, source-traced
- Problem: Matrix loading does not bind block numbers to `state.plan` and `state.deciding`. Every usable block greater than `blocks` is treated as a deciding block.
- Concrete failure scenario: A matching stale `b4` dossier exists for a two-block run whose recorded deciding block is `b3`. Matrix regeneration displays and uses `b4` to resolve instability despite it not belonging to the run plan.
- Proposed change: Accept ordinary blocks only from the recorded plan and deciding data only from the recorded deciding-block identity; refuse all other block dossiers.

P4
- Location: `benchmark/bench/p475_kv.py:1477-1532`, `benchmark/bench/p475_kv.py:2101-2103`
- Severity: minor
- Evidence: confirmed, source-traced
- Problem: Standalone `matrix` returns zero whenever required legs are complete, even when instability remains `UNRESOLVED`.
- Concrete failure scenario: After `--max-deciding 0`, `run` correctly exits 1, but `python -m bench.p475_kv matrix` regenerates the same unresolved table and exits 0.
- Proposed change: Make `matrix` return nonzero when `unresolved` is nonempty, without changing canonical-versus-partial naming.
