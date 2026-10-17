P10 — blocker — `docs/specs/p311-identity-split.md:34-38`; `benchmark/run_opencode_probe_v2.py:688-735`  
Failure: `rerun_decision` is stored on the result row, after the gated attempt. A crash after launch but before row commit leaves no frozen decision. Negative decisions (“done/no rerun”) are not specified, so scoring drift can still add an attempt. Audit record keys also do not identify which appended resolution won.  
Fix: atomically append a decision journal before launch/advance for every disposition (`done`, `rerun`, `blocked`), including exact selected-record hashes, resolved labels, policy/scoring hashes, deny plan and decision ID. Attempts reference that ID; later scoring cannot alter it without an explicit superseding operator decision.

P11 — blocker — `docs/specs/p311-identity-split.md:68-73`  
Failure: historical commits lack `deny_rules.py` and `rerun_policy.py`, so the v2 generation list cannot be hashed at their `git.stack_head`. Even a “present files only” rule produces a different hash from post-P311 because `tg1_runner.py` and shared probe files necessarily change to implement P311. Consequently historical and new composites cannot match, defeating P6’s old-to-new pairing.  
Fix: define a reviewed equivalence migration, not a literal historical v2 hash: verify each historical tree with its versioned legacy recipe, then map it to a canonical generation-equivalence version with explicit normalization of identity-only changes.

P12 — high — `docs/specs/p311-identity-split.md:70-71`; `benchmark/bench/tg1_runner.py:319-337`  
Failure: “the old list” is undefined and changed over time—for example, earlier P223/M63 recipes omit later `web_audit_cursor.py`. Matching that digest proves only the listed files matched, not that “the tree matched the commit”; reachable but unhashed modules could have been dirty.  
Fix: register the exact ordered legacy recipe per recipe/version or commit range, golden-test real P223/M63/c144 manifests, and narrow the proof claim to those files.

P13 — blocker — `docs/specs/p311-identity-split.md:10-11,27-30,94`; `benchmark/run_opencode_probe_v2.py:603-610`  
Failure: standard-v2’s digest hashes both `run_opencode_probe_v2.py` and `answer_key.py`. Moving rerun logic and modifying `_rerun_resume` necessarily changes that digest, contradicting “standard v2 identity unchanged” and test 9’s unchanged golden value.  
Fix: either keep both files byte-identical by implementing only tg1-specific modules, or explicitly permit/version the standard-v2 identity change. The current requirements cannot all hold.

P14 — high — `docs/specs/p311-identity-split.md:15-21`; `benchmark/chains/c147/run_tg1_chain.py:26`; `benchmark/bench/provenance.py:18-19`; `benchmark/bench/generate.py:18`  
Failure: the claimed exact partition is neither import-closed nor tg1-exact. It omits chain-driving `run_tg1_chain.py`/`chain_ops.py` and transitively loaded `generate.py`, `client.py`, `benchmarks.py`, `depth.py`, and `traces.py`. Conversely, `m62/replay.py` and the proposed rerun modules are not executed by tg1. Changes can therefore either evade identity or orphan rows without changing tg1 behavior.  
Fix: define and test the project-local import/call closure, lazy-import unused provenance dependencies, and separately hash chain lifecycle code. Document any intentionally pinned, non-runtime artifacts.

P15 — high — `docs/specs/p311-identity-split.md:17,27-31`; `benchmark/run_opencode_probe_v2.py:519-583,688-735`; `benchmark/bench/answer_key.py:246-328`  
Failure: hashing all of `run_opencode_probe_v2.py` keeps tg1 coupled to scoring-only `_web_audit` and standard-only `_rerun_resume`. Also, moving `rerun_plan` without moving `deny_patterns_for`, which it calls, leaves generation policy dependent on scoring code.  
Fix: extract tg1 generation helpers and scoring audit collection into separate modules; move all deny-plan construction, including `deny_patterns_for`, into generation policy.

P16 — high — `docs/specs/p311-identity-split.md:45-51`; `benchmark/bench/chain_ops.py:493-505,718-724`; `benchmark/bench/provenance.py:272-399`  
Failure: the composite includes only `draft_kind`, not the effective worker configuration. Two runs can share it while differing in model artifact, KV scheme/cap, prefill behavior, MTP draft model/scan/block settings, session retention, APC or other serving controls. The chain currently pins the registry precisely because these affect generation.  
Fix: include a canonical effective worker/config fingerprint—preferably based on `provenance.config_fingerprint` plus resolved model artifact—rather than only `draft_kind` or raw registry bytes.

P17 — high — `docs/specs/p311-identity-split.md:45-51`; `benchmark/run_opencode_probe_v2.py:194-197`; `benchmark/bench/tg1_runner.py:1217`  
Failure: `prompt_date` changes opencode’s system prompt, but is absent from the composite. A chain crossing midnight can assign one manifest identity to rows with different prompts.  
Fix: include spawn-time `prompt_date` in each row’s pairing identity, and either segment/refuse a leg at date drift or define a row-level composite.

P18 — medium — `docs/specs/p311-identity-split.md:49-56`; `benchmark/bench/tg1_runner.py:1071-1097`  
Failure: “resume compares generation identity fields only” does not explicitly preserve separately compared model, language and seed schedule. A literal implementation using only the composite could reuse existing item rows under a new seed base or language.  
Fix: enumerate the resume contract: composite plus model, language, seed base/schedule, worker/router continuity and required gate receipts; only scoring/support hashes may drift.

P19 — medium — `docs/specs/p311-identity-split.md:39-40`; `docs/specs/m64-scaffold-arms.md:79-89,260-272`  
Failure: P8 is deferred, not resolved. M64 still specifies synchronous chain-owned audit/rerun without P311’s decision-journal schema or freeze/recovery semantics. Implementing either document alone yields different ownership and crash behavior.  
Fix: amend M64 §4/§9 now and make its lifecycle reference the same durable decision record and recovery rules.

P20 — medium — `docs/specs/p311-identity-split.md:79-94`  
Failure: tests omit decision crash windows and negative decisions, real pre-P311 migration with missing files and old-to-new equality, static import closure, effective worker controls, midnight prompt-date drift, and M64 decision parity. The listed suite can pass while P10–P19 remain.  
Fix: add those cases as acceptance tests, using committed historical manifests/commits rather than only temporary current-tree vectors.

Round-1 closure: P7 is resolved; P4 is mostly resolved but underspecified by P18. P1, P2, P3, P5, P6, P8 and P9 remain open through the findings above.

VERDICT: AGREE WITH CHANGES P10,P11,P12,P13,P14,P15,P16,P17,P18,P19,P20
