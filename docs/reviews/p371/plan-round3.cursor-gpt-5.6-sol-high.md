R6 — resolved — immutable invocation files, quarantine, and resume tests eliminate append/SHA drift.

R9 — resolved — full archived runtime, bundle-only imports, and root inputs close baseline leakage.

R10 — partially — the layout table assumes pilot+full; pilot-only, reload, and later full-only legs have different phase/manifest cardinality.

R11 — partially — policy values are split, but evidence modules and hooks remain in `probe_code_sha256`; evidence-code changes still break P311 pairing.

R13 — partially — chain hooks exist, but mid-invocation `rerun_same_slot` lacks durable stop, retry-index, and scored-attempt semantics.

R18 — resolved — pilot/full are phase-qualified, disjoint invocations with separate expected sets.

R19 — resolved — progress distinguishes validated, partial-incident, and quarantined invocations with explicit cursors and slot sets.

R20 — resolved — archived `tg_fixture`, `fake_probe`, `FakeOps`, and `Timers` can support the specified isolated subprocess driver.

R21 — resolved — every receipt carries worker identity; the fenced set is persisted and hashed.

R22 — resolved — `GenerationPolicy` explicitly preserves the complete gate, hygiene, plugin, and toolchain recipe.

R23 — partially — hooks are chain-owned in prose, but probe entries and §5 explicitly include hooks in the generation closure; durable cheat-attempt selection is also unspecified.

R24 — BLOCKER — P371 A8/A9 `restart_load`/`scored_ids`. Failure: an archived tg1 load’s validated pilot remains scored—or its moved file fails SHA recheck—so restart can skip pilot rows or abort. Fix: generation-scope progress records and exclude archived loads from active inventory/scoring.

R25 — BLOCKER — P371 §3.3/A8 versus M64 §9. Failure: P201 stops a multi-item probe after one row, but `--expect-items` still requires the whole invocation and progress has no intentional-hook-stop state; the cheat row also enters `scored_ids`, suppressing its rerun. Fix: use one-slot barrier invocations or define hook-stopped prefixes; persist disposition/rerun index and score only the latest non-cheat attempt.

R26 — BLOCKER — P371 §3.1/§5 versus P311. Failure: `chain_hooks` is simultaneously outside and inside the probe closure; evidence-only code drift moves generation identity despite the stated policy. Fix: remove chain hooks from probe imports and clarify that imported receipt/barrier code changes move identity, while EvidencePolicy value changes do not.

R27 — HIGH — P371 A14 layout table versus `steps_for`. Failure: pilot mode and reload have pilot only, later legs full only, yet A14 always expects pilot+full and a full manifest. Fix: specify mappings and tests for all four phase shapes.

R28 — BLOCKER — P371 A3/A4 and item flow. Failure: worker receipts, tool-window receipts, and P364 date-freeze receipts lack distinct pinned paths/env fields, allowing schema collision or evidence loss. Fix: define separate `.receipts.json`, `.toolwindows.jsonl`, and `.datefreeze.jsonl` artifacts and adapter parameters.

Build start remains blocked on R24, R25, R26, and R28.

VERDICT: AGREE WITH CHANGES R24 R25 R26 R27 R28
