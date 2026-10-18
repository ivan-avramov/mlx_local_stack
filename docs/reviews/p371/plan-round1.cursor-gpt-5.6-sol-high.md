Closure check: A5, A6, A10, and A12 are adequately specified. The remaining gaps follow.

R1 — blocker — P371 §3.1 lines 50–54; §3.2 lines 63–74.  
Failure: `m64-oc` claims one `corpus_id`/entry/`tg1c` label can run tg1 or tg2, while its closure must exclude `tg2_*`. M64-on-tg2 either violates the closure, uses an untracked dynamic import, or retains a misleading identity.  
Fix: bind corpus and tier immutably per config and thin entry, e.g. separate `m64-oc-tg1` and provisionally named `m64-oc-tg2`; finalize the tg2 label in the C175 M64 amendment.

R2 — high — P371 §4 A2/A3 lines 100–103; `docs/open-questions.md:22`.  
Failure: A3 classifies requests from live client events, but P370 says opencode 2.0.20 emits no compaction-request event. A legitimate compaction receipt remains unclassified and aborts before A2 can score `compaction_failed`.  
Fix: let the adapter classify compaction from the finalized export’s independently pinned boundaries, then join receipts. Test successful, tool-less, and failed compactions end-to-end.

R3 — high — P371 §3.3 lines 82–88; §4 A3; §6 P372.  
Failure: `build_env` precedes `receipts.start(attempt)`, with no attempt context passed to the adapter. Pi/opencode therefore cannot place `X-Bench-Attempt` in generated provider configuration. Fake receipt tests will not detect a later fork API mismatch.  
Fix: create `AttemptContext` before config/environment generation, pass its correlation header to the adapter, and place the start fence immediately before spawn. Pre-register an HTTP protocol fixture and fork integration acceptance test.

R4 — high — P371 §4 A4 line 103; `benchmark/bench/arm_watchdog.py:52-85`.  
Failure: if `toolwindows.js` cannot append, emits malformed data, or misses one start hook, a hung tool again has no open window. A one-time real-client positive does not make every attempt fail-closed.  
Fix: make receipt-write failure fail the tool invocation; bind records to attempt/session/callID and sequence; continuously validate them and abort on malformed or unmatched starts. Add disabled/corrupt-plugin tests.

R5 — high — P371 §4 A7 line 105; `benchmark/bench/tg1_runner.py:1004`; `benchmark/bench/proc_guard.py:730-735`.  
Failure: the specified predicate accepts a partial receipt such as `completed:false` or nonempty `unknown` while survivors/containers are empty and `uncertain:false`. Recovery could start with unverified processes.  
Fix: validate the exact cleanup schema: `completed:true`, empty survivors, containers, unknown and unattributed orphans, and `uncertain:false`; reject missing or extra malformed fields.

R6 — blocker — P371 §4 A8–A9 lines 106–107.  
Failure: one appendable segment can contain a validated leg followed by a partially written leg. Its recorded SHA then changes. Resume either rejects the earlier validated leg or ignores the tail, reruns those slots, and makes `load_slots` reject duplicates.  
Fix: use one immutable file per leg/attempt, close/fsync/hash it only after validation, and quarantine unvalidated active files. Test interruption during the second leg after at least one row, including a second resume.

R7 — medium — P371 §3.1 `chain_rows`; §4 A9; §8.  
Failure: “every report entry point” is not enumerated or enforced. One existing base-file reader can still omit recovery rows or double-count DNF rows while acceptance remains green.  
Fix: make the inventory the sole exported chain-row loader; enumerate and migrate all consumers; add a repository test rejecting direct chain JSONL reads and unregistered segment files.

R8 — high — P371 §4 A13; §6 P374; §8 criterion 6.  
Failure: acceptance proves artifact generation but not the non-smoke chain refusal. A mutable artifact can gain `OWED`, fail, or be replaced after entry without detection.  
Fix: require artifact path and SHA in `ChainConfig`, freeze them in `chain.json`, and verify at entry, resume, barriers and exit. Test `OWED`, failed, missing and hash-drift refusal plus the smoke exception.

R9 — blocker — P371 §4 A14 lines 112–114.  
Failure: copying only three legacy files does not freeze the old path; they still import current `token_turn_gate`, `chain_ops`, opencode core and plugins. A shared-dependency regression can affect both sides identically and pass.  
Fix: execute the baseline from an isolated `0c9bd32a` checkout/archive, or vendor its complete import/data closure with no production imports beyond explicit fakes.

R10 — high — P371 §4 A14; §7 phases 2–3.  
Failure: “identity values” is an unbounded allow-list, while `compaction` should not appear for tg1 at all. Conversely, nondeterministic paths, UUIDs and timing fields are not addressed. Phase 2 also demands chain differential paths before `chain_core` exists in phase 3.  
Fix: list exact JSON pointers and value predicates, normalize injected clocks/UUIDs/paths, independently verify identity recipes, and forbid tg1 compaction fields. Split item differential tests into phase 2 and chain tests into phase 3.

R11 — high — P371 §3.2 lines 63–67; P311 §4.  
Failure: hashing every `RunConfig` field makes evidence location, transport policy and snapshot-completeness policy part of generation identity. Changing an output directory or recovery rule would invalidate pairing; an absolute `evidence_root` could also encode machine-local paths.  
Fix: separate hashed generation policy from runner evidence policy and chain lifecycle policy. Store only a logical relative evidence namespace; keep transport/resume/snapshot gates in frozen `ChainConfig`.

R12 — high — P371 §3.1 `Corpus`/`Host` lines 35–39, 56–59; `benchmark/bench/tg2_grade.py:716-737`.  
Failure: `initial` is undefined by `Corpus.prepare`, so tg2’s multi-file editable set cannot implement `changed`. The grade contract also lacks normalized phase outcomes, resources and artifacts needed by the shared `GradeWorker`. Corpus-specific `_polyglot_*` and `_seed_row_fields` remain in the Host seam.  
Fix: define typed `PreparedItem` and `GradeOutcome` contracts, including editable-tree baseline, tamper result, infrastructure/model outcome, reports and final-tree artifact. Move corpus paths into `Corpus` and generic seed derivation into the core now.

R13 — high — P371 §2 non-goals; §3.3; M64 spec §5.5 lines 160–176 and §9 lines 260–270.  
Failure: D2 needs a health/canary check before every attempt, while P201 needs immediate same-slot cheat reruns with fresh receipts, cache reset and accumulated tokens. The proposed core has neither an attempt lifecycle hook nor a retry-disposition seam, forcing another control-flow refactor.  
Fix: add no-op `before_attempt`/`after_attempt` hooks and a configurable attempt-disposition interface now; leave D2 and P201 implementations for their owned steps.

R14 — medium — P371 §4 A1; `docs/specs/m65-tg2-corpus.md:97-103`.  
Failure: `tg2_tier` is not explicitly bound to the frozen seed-6501 permutation artifact and sidecar SHA. It could generate a different prefix while still producing internally stable hashes.  
Fix: freeze the draw artifact SHA and tier in `ChainConfig`/`schedule.json`, consume its prefixes rather than redraw them, and verify membership and SHA at every leg.

R15 — high — P371 §5 lines 120–121; current `benchmark/bench/arm_specs.py` and `arm_ops.py`.  
Failure: the lifecycle set omits arm specs/operations and serialized `ChainConfig`. Changing reset, warm-up, search restart, labels or pinned runtime fields between legs may evade drift detection.  
Fix: define a canonical lifecycle closure per chain entry covering `ChainConfig`, arm specs/ops, core, schedules, row inventory, gate and launcher; test each file’s drift.

R16 — medium — P371 §6 P375 lines 137–139.  
Failure: a round-four semantic fix can introduce a new reachable defect yet skip independent review merely because the original finding was “improbable.” P365 is not a general safety argument for this core.  
Fix: require another cold review after semantic/control-flow fixes; permit lead-only closure solely for mechanical changes with a proving regression test and unchanged behavior.

R17 — medium — P371 §8 criterion 5.  
Failure: testing a fake adapter and fake corpus separately does not detect cross-product incompatibility or mutable configuration leakage between sequential tg1, m64 and tg2 runs.  
Fix: run the non-opencode adapter × four-language corpus combination and execute all configs in both orders in one process, asserting rows, identities, closures and disabled features remain isolated.

VERDICT: DISAGREE R1 R2 R3 R4 R5 R6 R8 R9 R10 R11 R12 R13 R15
