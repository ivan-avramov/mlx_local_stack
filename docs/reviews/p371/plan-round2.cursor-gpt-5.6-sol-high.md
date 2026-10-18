R1 — resolved — corpus, label, and entry are immutable per configuration.

R2 — resolved — request classes come from the finalized transcript before receipt joining.

R3 — resolved — `AttemptContext` precedes environment generation; start fencing immediately precedes spawn.

R4 — resolved — missing, corrupt, or unwritable tool-start receipts fail closed.

R5 — resolved — exact cleanup schema and values are specified.

R6 — partially — immutable files are required, but tg1 pilot/full still lack distinct invocation/file semantics; full can overwrite, duplicate pilot rows, or be skipped.

R7 — resolved — sole loader, consumer migration, and enforcement scan are specified.

R8 — resolved — artifact path/SHA freezing, lifecycle verification, and refusal cases are covered.

R9 — partially — isolation is required, but the archived baseline lacks a runnable injected chain harness and necessary root runtime inputs.

R10 — partially — JSON pointers and normalization are bounded, but the promised file-layout mapping table is absent, allowing pilot/full drift to be normalized away.

R11 — partially — policy layers are separated, but the enumerated `GenerationPolicy` drops existing generation-identity inputs, notably P311 toolchain identity.

R12 — resolved — typed multi-file preparation, grading, change detection, and final-tree contracts are defined.

R13 — partially — hooks exist, but item-core ownership cannot implement chain-level cache reset, warm-up, blocking, and durable P201 reruns without another control-flow seam.

R14 — resolved — tg2 tiers consume and verify the frozen seed-6501 artifact.

R15 — resolved — lifecycle includes the import closure, canonical `ChainConfig`, arm operations, gate, and launcher.

R16 — resolved — semantic/control-flow fixes require another cold review.

R17 — resolved — cross-configuration, cross-product, both-order process isolation is explicitly tested.

R18 — BLOCKER — P371 §4 A8/A14; `run_tg1_chain.py:steps_for/build_cmd`: pilot and full are separate launches sharing one logical leg and output today; immutable files make full duplicate pilot rows or mark the leg complete prematurely. Fix: specify phase-qualified invocation IDs, files, manifests, expected-item sets, and pilot→full interruption tests.

R19 — HIGH — P371 §4 A8/A9; `chain.json.progress`: `{leg_key, attempt, file, sha256, worker}` cannot distinguish validated partial transport prefixes, completed legs, and quarantined attempts. Fix: add phase/status, expected and accepted slots, worker segment, and explicit per-load resume cursors.

R20 — BLOCKER — P371 §4 A14: `git archive … benchmark scripts` plus fake client/worker cannot drive the legacy chain’s injected `ChainOps`/timers in a subprocess, and excludes root runtime inputs. Fix: define a complete archived runtime bundle and a baseline-side subprocess harness with controlled chain operations and no current-tree imports.

R21 — HIGH — P371 §4 A3 vs M64 §7: receipts omit per-receipt worker identity and no immutable receipt artifact/hash is specified. A worker replacement between marks can yield unauditable token attribution. Fix: include and verify worker identity on every receipt and persist the raw fenced receipt set by SHA.

R22 — BLOCKER — P371 §3.2/§5 vs P311 §3–4: “only `GenerationPolicy`” is hashed, but its field list omits current gate/hygiene/plugin and runtime toolchain inputs. Lock, interpreter, grader-image, or control drift can retain the same generation identity. Fix: explicitly preserve the complete current scaffold-policy recipe inside `GenerationPolicy`.

R23 — BLOCKER — P371 §3.3 vs M64 §9/P311: P201 hooks run inside the probe closure, while the ruled lifecycle is chain-level and scoring-only changes must not move generation identity. Crash-resume also loses cheat tokens/dispositions. Fix: make item attempts return durable evidence to `chain_core`; let chain-owned hooks audit, reset/warm, rerun/block, and persist attempt state outside the generation closure.

Build start — blocked on R18–R23 amendments; P372, D2, and P201 implementation block real non-smoke M64 runs, not fake-core construction.

VERDICT: DISAGREE R18 R19 R20 R21 R22 R23
