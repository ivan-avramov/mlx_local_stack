I have completed my analysis. Let me write up the findings.

## Round-2 verification — P426 B2 (the whole candidate)

### Round-1 findings: resolved / not

**1. `p426_dnf.load` swallowed by a comment; `attempt` the per-stem counter — RESOLVED.**
`chain_core.py:2611-2612` now writes `load=load["idx"]` (restored from the comment) and `attempt=self.p426_attempt_no(att)`. `p426_attempt_no` (2645-2649) parses `\.a([1-9][0-9]*)$` from `Path(self.out_root).name`, falling back to `att["attempt"]` only for a bare chain. `test_b2_fix3.test_1…` asserts `attempt==2, load==0` for `…off-pilot.a2`. Confirmed in source.

**2. A resumed pair dossier trusted by its stored verdict — RESOLVED.**
`p426_wave2.ensure_dossier` (570-596) always recomputes `problems/differences/verdict` from the current receipts; when `path.exists()` it calls `verify_dossier` (599-629), which re-checks self-hash, pair, `arms.<arm>.{attempt,receipt_sha256,harvest_sha256}`, `differences`, `verdict` and stops (rc 1) on the first mismatch. The stored verdict is never read. `test_b2_fix3.test_2_*` covers each field.

**3. `KV_*`/`TQ_*` prefix exemption leaks `KV_API_KEY` — RESOLVED.**
`p426_secrets.py:21-24` replaces `NON_SECRET_PREFIXES` with the exact `STACK_DEFINED_KV_TQ_NAMES` allowlist; `is_credential_key` (47-50) returns `not (upper in NON_SECRET_KEYS or upper in STACK_DEFINED_KV_TQ_NAMES)`. `KV_API_KEY`/`TQ_TOKEN`/`TQ_KEY_BITS` are now credentials; `KV_KEY_BITS`/`TQ_KV_QUANT_MODE` are not. `test_b2_fix3.test_3_*` and the amended `test_b2_s5_receipt` pin it. The safe direction is taken (an undefined `KV_`/`TQ` name is a credential).

**4. DNF requests never engagement-checked; ON items with only ≤1-token requests pass — RESOLVED.**
`p426_reconcile.engagement_problems` (135-156) gains `item=False`; with `item=True` an ON item with no `generated_tokens≥2` request is `unengaged`. `p426_hooks.after_attempt` passes `item=True` for normal items (line 200) and `p426_hooks` DNF path (274-277) calls engagement on DNF completed requests. `p426_freeze.leg_items_problems` (139-159) re-validates DNF item records (`item=not dnf`) and adds a leg-level `unengaged` when an ON leg has no judged request anywhere. Tests `test_4_*` cover both paths.

**5. In-flight DNF cases without in-flight evidence — RESOLVED.**
`_reconcile` (246-249) adds `check("inflight_evidence", inflight_possible, …)` for the `inflight_failed` case. `reconcile_item` (294-297) derives `inflight_possible` from `term["in_flight_at_kill"]` (int ≥1); `reconcile_dnf` (309-310) from `in_flight is True or message_id is not None`. A boundary abort/kill with a trailing failed line and no structured in-flight marker is now systemic. `test_5_*` covers DNF and kill boundary/in-flight/unaccounted variants.

**6. Pilot gate bypassable via `amend`/an existing amendment — RESOLVED.**
`p426_freeze.write_amendment` (649-667) runs `pilot_gate_problems + pilot_dossier_problems` itself and records `pilot_dossier_sha256`. `p426_wave2.ensure_amendment` (632-642) runs `write_amendment` (gate inside) on first write and `verify_amendment` (644-669) on an existing file: self-hash, kind, `v8_base_sha256`, and that `pilot_dossier_sha256` equals the selected pilots' PASS dossier. `test_6_*` covers failing gate, missing/wrong dossier, and re-verification of a tampered amendment.

**7. R1–R3 roots not bound to the rehearsal manifest — RESOLVED.**
`p426_freeze.binding_problems` (213-237) requires each R1-off/R1-on/R2/R3 `chain.json` to record `frozen_record={path,sha256}` equal to this manifest and the expected `inject` (R1: none); `rehearsal_problems` (242-249) calls it. `chain_core` persists `frozen_record`/`inject` in `chain.json` (1100-1102) via `p426_frozen_record_ref` (portabilized by `portable_doc` at write). The manifest's own commits are deliberately not compared with the v8 arms. `test_7_*` covers wrong manifest/path/missing ref, wrong leg name, wrong injection, and the no-commit-compare ruling.

**8. Missing self-hash passes the harvest; `leg.json` not checked — RESOLVED.**
`p426_harvest._is_immutable`/`_immutable_problem` (209-219) cover `leg.json`, `receipt.json`, `items/*`, `p426_dnf` sidecars; a missing `sha256` fails like a wrong one. The `_check_references` loop (659-663) applies it to every immutable leg file. DNF sidecar equality is enforced (651-653). `test_8_*` covers each immutable record and the sidecar mismatch.

**9. Run-file publication failure exits 0 — RESOLVED.**
`p426_wave2.publish_run_files_or_stop` (737-743) wraps `publish_run_files` and raises `Stop(4, …)` on failure; `run()` calls it at `--through` and at completion (729, 731). `run_files_done` (init 303) prevents the `main` `finally` from re-running/re-logging. `test_9_*` asserts rc 4, no DONE line, and single publication.

**10. A manifest run id resolving to no directory passes — RESOLVED.**
`p426_harvest._manifest_runs` (470-473) appends a problem when `not run_dirs and not ev_dirs` or when `len>1`. `test_10_*` covers both. The harvest raises `HarvestError` on problems.

**11. `ready_sha256` is the file hash, not the self-hash — RESOLVED.**
`p426_hooks._item_record` (line 200) sets `ready_sha256=(ready or {}).get("sha256")`; the removed `ready_file_sha256` has no remaining references. `p426_harvest._check_references` (643-645) requires the item's `ready_sha256` to equal the ready record's `sha256`. `test_11` and the amended `test_b2_fix_chain`/`test_b2_s4_reconcile` pin the self-hash.

**12. Secrets parsing — shell comments, JSON `Bearer`, non-UTF-8 — RESOLVED.**
`p426_secrets.parse_assignments` (56-78) uses `shlex.split(value, comments=True)`, first token; an unparseable credential-keyed line raises `SecretsError` naming the key only. The bearer regex (137) matches `Authorization["']?\s*[:=]\s*["']?Bearer …` (HTTP, JSON, quoted). `p426_harvest.Gate.check` (408-417) decodes non-UTF-8 via `surrogateescape`, records `lossy`, and re-scans scrubbed bytes; `harvest_wave2` (882-883) stamps `e.lossy="surrogateescape"`. `test_12_*` cover all three.

### Anything else the diff breaks or leaves failing

**F-A — ON DNF item with no judgeable request is not flagged `unengaged` per-item (minor, hypothesis).**
Location: `benchmark/bench/p426_hooks.py:274` (DNF path calls `engagement_problems(report.requests, self.arm)` with `item=False`) and `benchmark/bench/p426_freeze.py:156` (`engagement_problems(requests, arm, item=not dnf)` → `item=False` for DNF).
Evidence: traced in source; no test covers an ON DNF item whose completed requests are all `≤1` token.
Problem: spec §16.8 says "an ON item or leg with no judgeable request is `unengaged`." A DNF item is an item, but the per-item `unengaged` check (`item=True`) is applied only to non-DNF items. An ON DNF item that aborted with only `≤1`-token completed requests records `verdict="reconciled"`, `engagement.ok=True`, and is re-validated clean by `leg_items_problems`; the leg-level `unengaged` fires only when the *whole* leg has no judged request, so a DNF-with-only-short-requests in an otherwise-engaged leg passes silently.
Scenario: an ON leg where one normal item engages (judged) and one DNF item aborts after only single-token completed requests; the DNF item is reported as reconciled+engaged despite proving no engagement.
Counter-argument: §4.4 says `≤1`-token requests are "counted and listed, not judged" (not violations), and a DNF that aborts early may legitimately have only short requests; the leg-level check is the natural granularity for "the leg proved no engagement." This is narrow (a DNF with all completed requests `≤1` token is unusual) and fails safe at the leg level. Proposed change (if the operator reads the spec literally): call `engagement_problems(report.requests, self.arm, item=True)` in the DNF hook path and `item=True` for DNF in `leg_items_problems`, or state in the spec that the per-item `unengaged` rule applies only to completed items.

NOTHING OF SUBSTANCE.
