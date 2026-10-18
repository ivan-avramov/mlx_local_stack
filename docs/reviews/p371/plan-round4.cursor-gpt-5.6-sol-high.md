R10 — resolved — A14 now maps all four `steps_for` shapes and exact comparison pointers.

R11 — partially — policy values are split, but edits to probe-imported `worker_receipts` or `item_barrier` still rotate generation identity despite being called non-generation protocol.

R13 — partially — after-attempt reruns are durable, but `before_attempt` transport failures have no persisted pre-spawn incident/stop/resume transition.

R23 — partially — durable chain ownership exists, but probe bindings and §5 still include “hooks,” permitting accidental `chain_hooks` closure inclusion.

R24 — resolved — `load_gen`, archival, active inventory, and scoring exclusions cover restart-load.

R25 — partially — `hook_stopped` is absent from the invocation status enum and `scored_ids`; accepted rows preceding a cheat can be rerun or duplicated.

R26 — not — §3.1 excludes `chain_hooks`, while the probe-binding row and §5 include hooks in `probe_code_sha256`.

R27 — resolved — pilot-only, pilot+full, full-only, and smoke layouts each have differential coverage.

R28 — resolved — worker, tool-window, and date-freeze receipts have distinct paths, schemas, and parameters.

R29 — BLOCKER — §3.4/A12/M64 §9 — web evidence is extracted “after every invocation,” but P201 must decide at each `.done` before `.continue`; later items can run unaudited. Extract and audit at the done barrier, with post-invocation fallback only when no done barrier exists.

R30 — BLOCKER — §3.1 `arm_adapter` versus A12 — `web_evidence()` remains an adapter method while extraction is declared chain-only. This creates duplicate ownership or puts evidence code back into probe identity. Remove the method; retain extraction rules as arm-spec data consumed by `bench/web_evidence.py`.

R31 — HIGH — A3 versus M64 §7 — `attempt_header` is mandatory for every receipt/join, while §7 requires it only where the client supports custom headers. A compliant headerless arm cannot run. Declare header capability and permit fence/sequence/order joining when absent.

Build start remains blocked by R13, R23, R25, R26, R29, and R30; P372, D2, and P201 block real M64 runs, not phase-1 fake contracts. The archived A14 harness is feasible with bundled `FakeOps`, timers, and pytest monkeypatching.

VERDICT: AGREE WITH CHANGES R11 R13 R23 R25 R26 R29 R30 R31
