Build review of `08a7be3d..ff071979` (P311-lite)

L1 — High — `benchmark/bench/arm_identity.py:17-25,56`  
Failure: the deployed first pick’s worker argv includes `--cache-session-shrink on` from `main_models.yaml:497`, but the flag is unclassified, so every real P311 run for that pick refuses before writing a manifest.  
Fix: classify the flag—likely inert under the existing text-invariance ruling—and test complete recorded argv for both picks, predictor OFF and MTP. Keep unknown flags fail-closed.

L2 — Medium — `benchmark/bench/arm_identity.py:130-157`  
Failure: `arm_identity_sha256` omits APC state required by §4. Chain tripwires protect this runner, but the identity itself can remain unchanged across APC states on other entry paths.  
Fix: read APC from the exactly verified router/worker environment, include it in the fingerprint, and refuse if unreadable.

L3 — Medium — `benchmark/bench/chain_ops.py:742-743`  
Failure: lifecycle freezes `drive_chain.sh`, while the current launcher is `benchmark/chains/c147/launchers/launch_tg1.sh`. The actual launcher can change without lifecycle drift detection.  
Fix: freeze the active launcher, or record and freeze every supported launcher actually used.

L4 — High — `benchmark/chains/c147/run_tg1_chain.py:231-248`  
Failure: an unreadable, malformed, or schema-incomplete existing `chain.json` is treated as a new chain. Lifecycle, arms, and pins are silently re-frozen and the record overwritten.  
Fix: if `chain.json` exists, require a complete valid lifecycle/pins/arms schema; otherwise refuse and require a new out-root.

L5 — High — `benchmark/results/p223_tg1/tg1_report.py:112-114`; `benchmark/results/m63_mtp/m63_report.py:87-100`; `benchmark/results/c144_base/c144base_report.py:115-131`  
Failure: reports still pair by item ID and never call `tg1_pairing`. Rows from different prompt dates or generation epochs can therefore enter paired deltas.  
Fix: gate current rows through full `(generation identity, both arm identities, prompt_date)` grouping and report mismatches separately. Preserve the byte-identical legacy branch.

L6 — Medium — `benchmark/bench/tests/test_p311_closure.py:115-129`  
Failure: test 3(c) is not call-graph reachability. A function-local import on a never-executed tg1 branch passes whenever its bound name appears syntactically, causing irrelevant code to invalidate generation identity.  
Fix: implement entry-rooted reachability with the specified allow-list, supplemented by runtime-path coverage.

L7 — Medium — `benchmark/bench/row_scores.py:39-47`  
Failure: any single scoring key, even `"web_fetches": []`, classifies a tg1 row as legacy and bypasses the sidecar join. Partial rows can silently become “no contact.”  
Fix: use an explicit legacy discriminator or require the complete legacy scoring schema; sidecar-merged rows must not become authoritative legacy rows.

L8 — Low, non-blocking — `benchmark/results/p223_tg1/tg1_report.py:97-99`; `benchmark/results/c144_base/c144base_report.py:100-102`  
Unscored rows contribute zero to displayed fetch/contact counts. Strict scoring is provisional, but those columns are misleading. Render them as unknown/unscored.

L9 — Operational, non-blocking — `benchmark/bench/chain_ops.py:20-23`; `benchmark/chains/c147/run_tg1_chain.py:813-823`  
Adopt the lead call. Resolve policy from the configured probe’s `--print-identity`, forwarding the same `--universe`; treat supplied `--policy-sha` solely as an assertion; freeze the result in `chain.json`; reverify it on resume; remove the box-specific constants and P351’s unrelated `--policy-sha`/`--universe` coupling.

The `provenance.write(result_path=...)` deviation is sound. Wide scoring closure is conservative and sound. Git-tree contact inputs, standard-v2 rerun paths, legacy byte identity, fake composite layout, and universe forwarding otherwise look correct.

VERDICT: CLEARED AFTER FIXES L1 L2 L3 L4 L5 L6 L7
