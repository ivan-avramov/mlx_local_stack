K1 — OPEN — HIGH — `benchmark/bench/p426_leg.py:330-413,487-547`  
Problem: `BaseException` is covered only inside the started-leg body. Preflight catches only `Exception`; watcher shutdown and teardown also catch only `Exception`; planning, file loading, and imports happen before `run_leg`. Receipt writes are non-atomic.  
Failure scenario: `KeyboardInterrupt` during preflight/watcher shutdown, an M1 planning refusal, or a failure while finalizing the receipt exits without a receipt and may skip remaining cleanup.  
Fix: wrap the complete CLI lifecycle in an outer `BaseException` guard/finally, independently guard every cleanup step, atomically publish the INVALID/NOT_STARTED receipt, then re-raise interrupts.

K2 — OPEN — HIGH — `benchmark/bench/p426_leg.py:277-285,428-435,509-544`  
Problem: the supplied pins are checked against previously read registry text, not conclusively against the file actually served. The actual router config hash is not compared with the frozen pin, and none of the resolved repository/pin values are recorded in the receipt. The pins file itself is caller-selected and unbound to a committed frozen record.  
Failure scenario: an overlay changes after `registry_text` is read but before router startup. The router and worker consistently use the changed file, `router_ok()` confirms it remained unchanged afterward, and the leg can be VALID under an unpinned configuration.  
Fix: bind pins to the frozen campaign record, hash the actual served path immediately before and after startup/exit, compare it with the pin, and record all resolved commits and hashes in every receipt.

K3 — OPEN — HIGH — `benchmark/bench/p426_plan.py:36-79`; `benchmark/bench/p426_leg.py:487-520`  
Problem: row-based Wave-1 axes are now derived correctly, but M1 is absent. `plan_leg()` supports only Math500, cjudge, vision, and reasoning; `run_leg()` always starts a router and expects rows, whereas M1 is an in-process qualify leg with directory outputs and different evidence.  
Failure scenario: `--axis m1` refuses before receipt creation, so M1 smokes/full legs cannot receive the mandatory B10 freshness, pin, artifact, environment, and receipt checks. Running qualify manually bypasses the wrapper.  
Fix: add a typed M1 plan and execution adapter deriving its argv/output directory/artifacts and validating the in-process evidence without starting a router.

K4 — CLOSED — `benchmark/bench/p426_plan.py:48-77,91-101`; `benchmark/vision_gate.py:295-325`  
Every planned row now has checked seeds. Benchmark rows include sample/base/sampler seed, reasoning membership pins task seeds plus sampler seeds, and vision persists and checks both turn seeds.

K5 — OPEN — HIGH — `benchmark/bench/p426_leg.py:289-320`  
Problem: `(prompt_tokens, draft_n, draft_n_accepted)` is not a stable request identity. Multiple items—especially OFF rows with null draft counters—can naturally share the same tuple.  
Failure scenario: a missing completion is replaced by a foreign request with the same prompt-token count and counters; the multisets and aggregate request count still match, producing VALID attribution. The planned reasoning extra is likewise identified only as an arbitrary leftover.  
Fix: persist a unique request identifier in each response row and completed log record, then reconcile exact identifiers and telemetry, including explicitly identifying the calibration request.

K6 — OPEN — MEDIUM — `benchmark/bench/p426_leg.py:534-540`  
Problem: `qualify.power_log_problems()` only requires a `Using AC|Batt` token; it does not require any timestamped event parseable by `battery_intervals()`.  
Failure scenario: malformed output such as an unparseable line containing `Using AC` passes validation, yields zero intervals, and leaves speed valid.  
Fix: require at least one event matching the full timestamp/source grammar and reject every malformed source-event line before evaluating overlap.

K7 — CLOSED — `benchmark/bench/p426_panel.py:119-184`  
Export requires a nonexistent packet directory, and ingestion rejects verdicts whose current packet or attachment hash differs. This closes stale verdict reuse after re-export or packet/image modification.

K8 — OPEN — HIGH — `benchmark/bench/p426_panel.py:50-61,140-184,208-241`  
Problem: provenance is written but not validated. Judge configuration does not require a model ID; the Claude configuration used by tests therefore seals `model: null`. `seal_verdicts()` accepts an arbitrary client-version string and skips any document already containing `packet_sha`; ingestion validates neither prompt SHA nor required judge/client/model/version fields against the manifest/config.  
Failure scenario: a verdict with matching packet/image hashes but missing or false model, client version, judge, or prompt SHA is ingested and can be admitted.  
Fix: validate the judge schema, preflight each client, require nonempty provenance, and compare every provenance field and prompt SHA with the manifest/config during ingestion.

K9 — OPEN — HIGH — `benchmark/bench/p426_panel.py:68-71,107-132`  
Problem: the final scan is fail-closed but its forbidden set is incomplete. It misses identities such as `draft_model`, `mtp_verify_scan` because underscores defeat `\bmtp\b`, `predictor=on`, generic arm labels, registry keys, and paths outside `/Users`, `/private`, and `/home`.  
Failure scenario: an A7 diff containing `draft_model=/tmp/...` or `predictor=on` passes the scan and reveals the arm.  
Fix: derive forbidden identities from both registries and campaign metadata, include all tune/arm/predictor keys and values, and apply comprehensive absolute/session-path detection.

K10 — OPEN — HIGH — `benchmark/bench/p426_panel.py:63-101`  
Problem: selectors remain incomplete and bypassable. The legacy `pairs()` still performs generic shared-converged pairing; tg1 receives no both-pass/per-session filter; reasoning treats `score == 1` as strict without checking convergence/budget status; expected axis cardinality is not enforced.  
Failure scenario: A4 correct-but-budget-hit draws or A7 failed items enter the panel, while missing A2 rows silently reduce the promised 40 items.  
Fix: provide mandatory axis-specific adapters using committed membership, strict-status fields, and session identity; remove/private the generic bypass and assert expected packet counts.

K11 — OPEN — HIGH — `benchmark/bench/p426_panel.py:166-204,244-262`  
Problem: `admit()` only examines items having at least one valid-choice row. Items with all verdicts missing, unbound, or unparseable disappear rather than being counted incomplete. It also does not validate pair identity, and `item_scores()` remains callable directly on unadmitted rows.  
Failure scenario: all four verdicts for an OFF-favouring item fail; the item vanishes from both the estimate and incomplete-item count, biasing the result.  
Fix: admit against the expected manifest item/lattice set, count zero-verdict items, validate pair keys, and make estimation accept only admitted clusters.

L1 — MEDIUM — `benchmark/bench/p426_leg.py:322-326,510-521`  
Problem: the receipt path is neither included in freshness checks nor opened exclusively; `_write()` overwrites it.  
Failure scenario: accidentally rerunning a completed leg hits existing benchmark outputs and replaces its VALID receipt with NOT_STARTED, destroying the original evidence.  
Fix: require fresh receipt/log/watch paths or use immutable run IDs, exclusive creation, and atomic publication.

L2 — MEDIUM — `benchmark/bench/p426_panel.py:282-299`  
Problem: the required two-stage cluster bootstrap is only a one-stage item-cluster bootstrap; within-item judge/order verdicts are never resampled.  
Failure scenario: substantial judge/order disagreement is treated as fixed, producing intervals that can be too narrow and misleading Holm/significance decisions.  
Fix: retain verdict-level observations and resample items first, then verdicts within each sampled item, before refitting each replicate.

L3 — HIGH — `benchmark/bench/run_judge_pairwise.py:95-112,156-183,205-212`; `benchmark/bench/p426_panel.py:1-305`  
Problem: none of the P426 protections is wired into an executable workflow. The existing documented CLI still calls generic `build_tune_pairs`, `export_packets`, and `ingest_packets`; `p426_panel` is referenced only by tests.  
Failure scenario: following the existing packet-export/ingest command bypasses fresh-directory enforcement, P426 selectors, sealed provenance ingestion, and lattice admission while appearing to run the intended panel.  
Fix: add one P426 CLI/orchestrator that composes selection → pairing → export → sealed judging → validated ingest → admission → estimation, and refuse the generic path for P426 labels.

VERDICT: DISAGREE K1 K2 K3 K5 K6 K8 K9 K10 K11 L1 L2 L3