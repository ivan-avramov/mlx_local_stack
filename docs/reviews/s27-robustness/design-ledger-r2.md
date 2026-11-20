# S27 robustness design review — ledger (round 2 of 3, verify)

Sol / GLM fresh sessions, Sonnet resumed (`88a8a519`); all exit 0, read-only, checkout at `3c1e6e40` (v1.1). Raw:
`design-verify-{sol,glm,sonnet}-r2.md`. r1 status: Sol R1–R7, R9–R16 resolved, R8 not (V1–V3); GLM F1–F7, S1 resolved + §12 notes;
Sonnet 9 resolved, P1 / P3 / P4 partly (V2, V4, V6). A check of the diff, not independent discovery.

| V | finding (raised by) | disposition | change in v1.2 |
|---|---|---|---|
| V1 | `accounting_fault` has no disposition / durable annotation path (Sol P1) | ADOPTED | §5.3 disposition + sealed `items/<slot>.accounting.json` sidecar; `chain_rows` exposes the flag. |
| V2 | the accounting vs integrity boundary is undefined across `_reconcile`'s checks (Sonnet F2) | ADOPTED | §5.9 closed table; unlisted → integrity. |
| V3 | the second-fault DNF has no schema; caps vs `MAX_RERUNS` (Sol P2, Sonnet F6) | ADOPTED | §5.7: `harness_fault_dnf` / `grade_fault` DNF records; P426 has no cheat rerun, so the rerun index is 0 / 1 for P426. |
| V4 | grader faults and uncertain cleanup arrive through the abort path, which treats them as systemic; who runs the second scan; a hold with no live probe (Sol P3, Sonnet F4) | ADOPTED | §5.8: typed abort stamps routed before the DNF-cause check; a chain-side scan (session id, hermetic roots, container prefix, 60 s); PAUSED needs no live probe and blocks launches. |
| V5 | "grader error" includes candidate-caused timeouts / mem_kills; a grade-only fault should regrade, not regenerate (Sonnet F3) | ADOPTED | §5.1: closed infrastructure list → regrade the retained snapshot (≤ 2), then `grade_fault` DNF; timeout / mem_kill / OOM / tamper stay outcomes. |
| V6 | the late-record reference should be the ingested offset, not the file size (Sonnet F1) | ADOPTED | §4.1–4.2 `ingested_offset_at_count` (file size supplementary). |
| V7 | `PASS_NO_INFLIGHT` must reach every verdict consumer (Sonnet F5) | ADOPTED | §4.3 lists them + a freeze test. |
| V8 | denied start-order / liveness reads still route a foreign daemon to uncertain (Sonnet F7) | ADOPTED | §3.2 every denied read; ownership tests first. |
| V9 | a kept accounting-fault item continues without a settle check (Sonnet F8) | ADOPTED | §5.3 settle before `.continue`; a failed settle → integrity / HOLD. |
| V10 | §12: literal paths, fail closed on a missing base, the receipt-document read, scope, the hazard (GLM N1 / N2, Sonnet F9) | ADOPTED | §12 rewritten: `PROTECTED_PUSH_PATHS`, one helper, any git error refuses, `full` non-evidence only, hazard stated. |
