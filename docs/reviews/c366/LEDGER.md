# C366 cold read — ledger (round 1 of 3)

Member: Sol (`gpt-5.6-sol-high`, cursor-agent `--mode ask`, read-only, `checkout` = a scratch clone with the diff applied; user
instructions unconfirmed; no session id reported), exit 0, raw output `cold-read-sol-r1-report.md`. Brief `brief.md`, material
`fix.diff` (as reviewed, tests not yet run: a GPU leg was live).

| id | Sol | disposition | reason |
|----|-----|-------------|--------|
| P1 | major: `CANCEL_PATH` (named functions) is not transitively complete (`in_flight`, `wait_cancel`, `worker_json`, `ProcessGuard` helpers, `GRACEFUL_CLIENT_S` unhashed) | ADOPTED | The digest is now over whole files' ASTs (comments / positions ignored, docstrings kept): token_turn_gate, proc_guard, arm_adapter, opencode_v2_core, host, worker_receipts, tg2_runner, run_tg2_probe, arm_runner, arm_opencode, inject_verify — excluding only the named S26 identity / Gradle-home definitions and inject_verify's alloc tail (`verify_row` cut at its `# alloc` marker; a missing marker refuses). Equal at `c7c6993a` and `9abef6a69` (`97f6e1d5…`). Tests mutate each named dependency (digest drifts) and the exclusions (digest holds). |
| P2 | blocker: v8 trusts the record's self-asserted evidence (the seal is recomputable); `reference_row_sha256` unmatched | ADAPTED | Adopted where v8 can check a fact cheaply: the per-language reference stall rows are constants (`TRANSFER_REFERENCE_STALL_ROWS`, from the sealed 11-17 record) and must match; v8 recomputes the reference arm's LIVE stop-path digest and refuses any transfer unless it equals the constant. Declined: v8 re-opening and re-verifying every row / manifest / artifact — the same trust model as S26's accepted DECLINED evidence, under the gate's "accidental, not adversarial" threat model; a deliberately forged, resealed record is out of scope (recorded residual). |
| P3 | major: the waiver reads `per_process` from an unverified manifest | ADOPTED | `waiver_evidence` verifies the manifest bytes against the probe's recorded `evidence_sha256` before reading the limit; `waived_evidence.manifest_sha256` must equal the entry's `evidence_sha256` in v8. Test: an edited manifest is not waived. |
