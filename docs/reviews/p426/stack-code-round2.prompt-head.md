Cold CODE review — ROUND 2 OF 3 (at most 3 rounds, then the operator decides open findings). STACK repo (this workspace) at
`e732d2d3`: the P426 Wave-1 builds (round 1: `docs/reviews/p426/stack-code-round1.prompt-head.md`; its findings K1–K11 are in
the scratch copy quoted at the end of this prompt). Fix commits: `b3fc620b` (K1–K6 red), `7bf5b2cb` (K1–K6 green), `e732d2d3`
(K7–K11 red + green; red `HEAD~1`). Files: `benchmark/bench/p426_leg.py`, `benchmark/bench/p426_plan.py` (new),
`benchmark/vision_gate.py`, `benchmark/bench/p426_panel.py`, `benchmark/bench/judge_pairwise.py`, tests `benchmark/bench/tests/test_p426_*.py`.
Claimed: K1 every path receipted (BaseException captured, interrupts re-raised after the receipt; watcher stop and teardown
guarded); K2 `pin_problems` (stack HEAD, clean tracked tree, both submodules, both registry text shas; `fork_dev` derived from the
frozen tree); K3 `p426_plan.plan_leg` derives argv / cwd / outputs (any file of the stem refuses) / membership / seeds / expected
requests from the verified `ids.json` and the CLI takes only --axis --arm --block|--smoke; K4 `seed_problems` per row (vision
rows record both turn seeds); K5 `request_match_problems` one-to-one by (prompt tokens, draft_n, draft_n_accepted) with exactly
the planned extra requests; K6 `qualify.power_log_problems`; K7 fresh packet dirs + verdicts sealed to packet / attachment sha;
K8 per-verdict provenance, client-version preflight; K9 leak scan (model names stripped by judge_pairwise); K10 `select` per axis
+ `make_pairs`; K11 `admit` (complete judge × order lattice). Gate: 234 P426 / judge / vision tests; stack suite running.

First, for EACH of K1–K11 state CLOSED or OPEN with the reason. Then anything new (L1 onward): severity, file:line, problem,
failure scenario, fix. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`. OUTPUT RULE: your FINAL message
must contain EVERY finding in full, then the VERDICT line.

----- ROUND 1 FINDINGS (verbatim) -----
I found a fail-closed surface in the leg wrapper that merits tracing through `ChainOps`: several non-`ChainAbort` exceptions can currently escape after startup without producing the required receipt. I’m checking whether arm/registry and process-pin guarantees are enforced transitively before assigning findings.K1 — HIGH — `benchmark/bench/p426_leg.py:271-338`  
Problem: only `ChainAbort` and driver timeouts are converted into receipts. Other exceptions, interrupts, or failures in `stop_watch()` escape before `_write()`; a watcher-stop exception also skips teardown.  
Failure scenario: malformed rows, `pmset` timeout, `OSError`, `KeyboardInterrupt`, or watcher failure leaves no receipt and may leave the router running.  
Fix: catch `BaseException`, independently guard watcher shutdown and teardown, atomically write an INVALID receipt in an outer `finally`, then re-raise interrupts.

K2 — HIGH — `benchmark/bench/p426_leg.py:271-286,400-433`  
Problem: the wrapper never verifies the frozen stack commit, either submodule SHA, driver-code SHA, expected registry hashes, or that `fork_dev` belongs to the frozen checkout.  
Failure scenario: an unreviewed stack/fork or different `mlx-serve` revision with equivalent registry text can produce a VALID receipt.  
Fix: pin and verify stack HEAD, both submodules, driver files, OFF/ON registry hashes, and path relationships before startup; record all values in the receipt.

K3 — HIGH — `benchmark/bench/p426_leg.py:145-176,271-286`  
Problem: freshness and membership are based entirely on caller-supplied `destinations` and `planned`. The wrapper neither requires `rows_path` and its sidecars among destinations nor derives membership from committed `ids.json`.  
Failure scenario: a spec omits an existing rows file, runs a resumable/no-op driver, and supplies those stale IDs as `planned`; or it selects valid IDs from the wrong block. The leg can be VALID.  
Fix: derive destinations and membership from a typed axis/block specification and the pinned `ids.json`; validate driver argv against that derivation and refuse every existing output/manifest/summary/journal.

K4 — HIGH — `benchmark/bench/p426_leg.py:311-316`  
Problem: exit validation checks item membership and draft engagement but not `sample`, `seed_base`, task seed, or `sampler_seed`.  
Failure scenario: ON and OFF use different request-seed bases—or A4 omits `--request-seed-base`—while retaining identical task IDs; both legs pass although the paired comparison is invalid.  
Fix: add per-axis seed adapters that validate every row against `rowschema.sample_seed` and the committed A4 request-seed map.

K5 — HIGH — `benchmark/bench/p426_leg.py:209-235`  
Problem: log reconciliation compares only aggregate counts. It does not establish a one-to-one relationship between persisted rows and request records or detect substitution by unrelated/duplicated records.  
Failure scenario: a missing measured completion is balanced by a foreign or duplicate cached-session request; counts still equal `expected_requests`, so attribution passes.  
Fix: persist a stable request/session identifier in rows and logs and compare exact multisets, including backend and draft telemetry.

K6 — MEDIUM — `benchmark/bench/p426_leg.py:423-429`  
Problem: `pmset -g log` is considered readable whenever its return code is zero. The existing `qualify.power_log_problems()` check is not called.  
Failure scenario: empty or malformed output returns no battery intervals; a brief on-battery interval between watcher ticks is missed and speed remains valid.  
Fix: require parseable power-source history; treat timeout, nonzero status, empty history, or malformed timestamps as a speed-invalid condition recorded in the receipt.

K7 — HIGH — `benchmark/bench/p426_panel.py:80-85`; `benchmark/bench/judge_pairwise.py:622-684`  
Problem: packet export overwrites packets/manifests in an existing directory, while the Cursor runner blindly skips existing verdict files. Verdicts are not bound to packet content.  
Failure scenario: re-exporting changed pairs into the same directory reuses `pNNNN.verdict.json` from an older packet and attributes that decision to a different item/order.  
Fix: require a fresh output directory or validate existing verdicts against packet, rubric, attachment, judge, and prompt hashes.

K8 — HIGH — `benchmark/bench/p426_panel.py:78-103`; `benchmark/bench/judge_pairwise.py:670-677,731-739`  
Problem: C207’s per-verdict provenance is absent. Packet SHA, attachment SHA, model ID, and client version are not carried on verdict rows; Cursor version return status is unchecked, and one directory-level provenance file is written only after all calls.  
Failure scenario: an interrupted run resumes under a different client/model and relabels earlier verdicts; a failed version command yields accepted empty provenance; a wrong image cannot be detected.  
Fix: preflight the client/version successfully, hash packets and attachments, and write immutable provenance with every verdict before accepting it.

K9 — HIGH — `benchmark/bench/judge_pairwise.py:92-113,660-668`; `benchmark/bench/p426_panel.py:67-72`  
Problem: blinding covers exact model names, selected family tokens, and template tags only. Task prompts are unsanitized, and tune/arm labels, predictor names, registry keys, session roots, and paths are not rejected.  
Failure scenario: an A7 diff or summary containing `p426-on`, an MTP drafter name, or an arm-specific path tells the judge which response is ON.  
Fix: sanitize every textual packet component using an experiment-specific forbidden-token set, case-insensitive full identities, and path detection; scan the final packet and fail closed on any leak.

K10 — HIGH — `benchmark/bench/p426_panel.py:62-64`; `benchmark/bench/judge_pairwise.py:212-224`  
Problem: the sole pair builder always selects shared-converged `id` rows. It has no axis adapters enforcing A1 both-correct, A2 all 40, A4 strict draws keyed by seed, A3 eligibility, or A7 both-pass per session.  
Failure scenario: nonconverged A2 items are silently excluded, incorrect A1 outputs can be included if raw rows are supplied, and raw A4 rows cannot be paired by their `seed` key.  
Fix: implement explicit per-axis selectors with exact eligibility and identity rules, then test expected packet counts.

K11 — HIGH — `benchmark/bench/p426_panel.py:106-124,144-169`  
Problem: `item_scores()` computes a score from whatever verdicts remain, without enforcing the complete two-judges × two-orders lattice or uniqueness. `length_adjusted()` then accepts these partial scores without consulting `missing`.  
Failure scenario: failures concentrated among OFF-favouring verdicts leave only ON-favouring judgments, biasing both the adjusted estimate and bootstrap interval; duplicate rows can overweight an item.  
Fix: require exactly one valid verdict for each expected judge/order, exclude incomplete items while counting them, reject duplicates, and bootstrap only the admitted item clusters.

VERDICT: DISAGREE K1 K2 K3 K4 K5 K6 K7 K8 K9 K10 K11