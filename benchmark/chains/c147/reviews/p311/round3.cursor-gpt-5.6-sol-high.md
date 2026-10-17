P21-level blockers are emerging: the proposed “all imports” AST closure cannot exclude function-local standard-v2 scoring imports, and the prompt-date treatment contradicts C170’s explicit ruling. I’m completing the independent path/closure checks before giving the numbered verdict.
P21 — blocker — `docs/specs/p311-identity-split.md:33-42`  
Failure: the proposed AST walk follows every module- and function-level import, yet `run_opencode_probe_v2.py` remains a closure root and will function-locally import `answer_key` and `web_scan` for standard-v2. Therefore the closure cannot both follow every import and exclude those scoring modules; test 1(a) is unsatisfiable.  
Fix: give tg1 a separate entry/shared-generation module whose static closure contains no standard-v2 scoring paths.

P22 — high — `docs/specs/p311-identity-split.md:37-43`; `benchmark/bench/provenance.py:18-19`  
Failure: a full static closure remains substantially over-inclusive. `provenance.py` imports `generate`, which transitively loads modules tg1 never executes. Changes there would still orphan tg1 rows. The proposed runtime test proves only that loaded modules are included, not that included modules are reachable.  
Fix: extract or lazy-import tg1 provenance dependencies, then test both directions: all runtime-loaded local modules are covered, and each covered Python module is reachable on a tg1 path.

P23 — high — `docs/specs/p311-identity-split.md:37-49`; `benchmark/bench/structured_grade.py:266-417`  
Failure: Python and Go graders influence `TokenTurnGate` during generation, but identity covers only their wrapper code. It omits the `.venv-bench` interpreter/dependencies and mutable `aider-benchmark` Docker image. Either can change grade boundaries, stopping, and final pass status under the same identity.  
Fix: include verified Python/toolchain lock identity and the local Docker image digest in `scaffold_policy_sha256`/the composite; refuse missing or changed identities.

P24 — high — `docs/specs/p311-identity-split.md:43`; `benchmark/chains/c147/run_tg1_chain.py:216-221`  
Failure: chain lifecycle hashes are merely rewritten into `chain.json`, not frozen and checked. Editing `run_tg1_chain.py`, `chain_ops.py`, or the A4 gate mid-chain can change scheduling or validation, while the final record shows only the new hash. P14 therefore remains partially open.  
Fix: freeze lifecycle hashes at chain creation and verify them before every launch, barrier, validation, resume, and exit.

P25 — blocker — `docs/specs/p311-identity-split.md:45-49`; `benchmark/chains/c147/run_tg1_chain.py:200-205`  
Failure: the composite includes the resolved model artifact but is pinned once from the first manifest. A two-pick chain necessarily has different model artifacts, so the second model either aborts or the model artifact is not actually enforced.  
Fix: freeze a mapping keyed by model/predictor arm, or keep model identity outside the shared composite and compare it separately everywhere.

P26 — high — `docs/specs/p311-identity-split.md:47-49`; `benchmark/bench/provenance.py:110-126,340-400`  
Failure: `provenance.config_fingerprint` is not a complete effective-worker fingerprint. It intentionally omits `draft_model`, `draft_block_size`, `suffix_min_match`, and related predictor controls. These are output-determining for MTP/suffix runs; “resolved model artifact” singular does not cover the drafter. P16 remains open.  
Fix: define a fail-closed fingerprint from verified worker argv plus served registry, covering target and draft artifacts and every active output-determining flag.

P27 — blocker — `docs/specs/p311-identity-split.md:50-53`; `docs/open-questions.md:22,38`; `benchmark/bench/tg1_runner.py:1168-1217`  
Failure: C170 explicitly requires P17 in the composite. The date is prompt content, so recording it as a covariate permits pairing different interventions. Sentinels can detect general drift but cannot make differing prompts matched. Current tg1 also records the date after generation, not at spawn, so a midnight-crossing item can record the wrong prompt date. C168 requires a frozen prompt date.  
Fix: capture immediately before spawn and include it in row-level pairing identity; segment/refuse date-mismatched pairs or freeze the date for the epoch.

P28 — high — `docs/specs/p311-identity-split.md:26-32`; `benchmark/web_audit.py:150-204`; `benchmark/bench/answer_key.py:211-216,344-405`  
Failure: moving `_web_audit` is generation-safe—tg1 does not consume its result—but the specified integration is incomplete. `web_audit.audit_rows`, `answer_key.audit_states/report_rows`, and existing report counters read audit fields directly from rows. Merely changing `needs_web_audit` would make P201 see no evidence or reports silently lose contact counts.  
Fix: define one fail-closed row-plus-score-sidecar join used by all audit, scoring, and reporting entry points. Test transcript → `tg1_score` → P201 audit → strict exclusion end to end. `validate_leg` need not require scoring at runtime.

P29 — high — `docs/specs/p311-identity-split.md:18-20,28-31`; `benchmark/bench/opencode_common.py:44-49`; `benchmark/bench/answer_key.py:53-73`  
Failure: the corpus input is not pinned as claimed. `polyglot_sha` records only Git HEAD, while `contact()` reads live `.meta/example*`, `exemplar*`, and `proof*` files; dirty edits change contact labels without changing the transcript, scoring hash, or recorded corpus SHA. A stale sidecar would remain apparently valid.  
Fix: derive contact inputs from the recorded Git tree, or record and verify a content digest of all reference files in each score record.

P30 — medium — `docs/specs/p311-identity-split.md:61-71`  
Failure: tests omit grader/toolchain drift, chain-code drift, multi-model composite cardinality, spawn-time midnight drift, dirty corpus references, scoring-sidecar version replacement, and the complete P201 pipeline.  
Fix: add those mutation and end-to-end cases, including fail-closed missing/stale/duplicate score records.

Round-2 disposition: P10–P13 and P19 are moot under forward-only P311-lite; P18 remains covered only if today’s separate model/language/seed checks are preserved. P14–P17 and P20 still apply through P21–P30 above. The underlying post-hoc-scoring direction is sound, and tg1 currently makes no rerun decision; only `_carrier_selection`’s deny construction and `_web_audit` reach `answer_key` on tg1.

VERDICT: AGREE WITH CHANGES P21,P22,P23,P24,P25,P26,P27,P28,P29,P30No follow-up needed; the completed checks corroborate the findings and verdict.
