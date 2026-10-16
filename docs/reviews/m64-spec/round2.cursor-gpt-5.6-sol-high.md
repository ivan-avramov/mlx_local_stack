Reviewed the requested tree: HEAD is `fd0274b8`, but the scoped files are unchanged from `3c65fc8f`.

## Round-1 findings

P1 — **Yes.** Grading remains runner-owned, with capture/grade boundaries and opencode gate-parity tests required.

P2 — **Yes.** §9 requires arm-neutral evidence confinement, identity-based eligibility, deny equivalents, and Pi/dsh rerun tests.

P3 — **Yes.** dsh contract failure now rejects the snapshot and holds the build; it cannot be silently dropped.

P4 — **Partly.** Inventory/HOLD rules are present, but the adopted dsh release and effective tool surface remain deferred, with D1/D2 unresolved.

P5 — **Partly.** Attempt marks, headers, receipts, and failure tests make correlation implementable, but §7 still says receipt ownership needs operator confirmation.

P6 — **Yes.** The complete bridge algorithm, thresholds, artifacts, and epoch-registration gate are restored.

P7 — **Yes.** Coverage floors, missing-as-unscored, two-judge means, order handling, and a new M64 path are specified.

P8 — **Partly.** A 600-second adapter watchdog and positives are required, but process-to-tool attribution remains too abstract given best-effort `ProcessGuard`.

P9 — **Yes.** Unconfigurable client cuts are treatment, disclosed, with all-item primary and exclusion sensitivity.

P10 — **Yes.** Every request must have effective controls reconciled through receipts before row acceptance.

P11 — **Partly.** Item-level incidents, token carry-over, and synthetic DNF are defined, but the second-failure key and post-reload protocol are ambiguous.

P12 — **Yes.** Balance is per pick×session×language; schedules, reload seeds, resets, and warm-ups are specified.

P13 — **Yes.** Accuracy IU-TOST components, token sign/hypothesis/bootstrap, and incomplete-receipt consequences are stated.

P14 — **Yes.** Generation-only pairing, report-time scoring derivation, and scoring-only-change acceptance are restored.

P15 — **Yes.** Work order and dated provenance/lockfile requirements now match E2.

P16 — **Yes.** Power simulation precedes implementation and can force estimation-screen status.

## New v2 problems

P17 — **Blocker:** subjective inference is not implementable. The spec does not define whether the confirmatory estimator is the raw two-judge mean or the length-adjusted regression result, nor its TOST p-value for Holm. Existing `judge_gate.py` uses M38 majority aggregation and CI heuristics, not this design.

P18 — **Blocker:** accuracy lacks a defined cell-level paired test, and claims unavailable through incomplete receipts or subjective under-coverage have no specified Holm value. Preserve the 12-claim family by defining these as `p=1`, not dropping them.

P19 — **Blocker:** P201 lifecycle is unspecified. The spec must say when auditing occurs, when a cheat rerun occupies its original schedule slot, how reset/warm-up works, and that all cheat-attempt tokens count.

P20 — **Should-fix:** §8.3’s “same (arm,item)” second-failure key is too broad. It must be the full epoch/pick/session/language/item/arm slot. A reload must repeat reset, warm-up, identity checks, and receipt boundaries before attempt 2.

P21 — **Should-fix:** the subjective panel lacks a required immutable final-code artifact. `transcript()` alone does not guarantee the exact graded code supplied to judges; require hashed final-code snapshots and packet manifests.

## D1/D2 and BUILD readiness

D1 is technically well motivated, but only correctly framed if acceptance explicitly amends C165 2a and applies only to fan-out tools actually present. Rejecting D1 would require redesigning accounting and the gate, not merely toggling configuration.

D2 is not yet correctly framed. “Unavailable/off” and §6’s “tools absent” conflate three different treatments: removing the tool, leaving it visible but unusable without credentials, or supplying credentials. C165 explicitly preserves dsh’s native web tool. The ruling must choose one and state that `web_fetch` plus shell networking remain enabled.

The specification is therefore **not yet ready for a BUILD go conditional only on D1/D2**. P17–P21 and the unresolved §7 owner must also be closed.

## Minimum edits to agree

- Define exact accuracy and subjective estimators, bootstrap/TOST p-values, and `p=1` handling for unavailable claims.
- Define synchronous P201 audit/rerun placement and cumulative token accounting.
- Tighten transport-slot identity and post-reload reset/warm-up steps.
- Require hashed final-code judge artifacts and an M64-specific reliability-gate contract.
- Resolve receipt ownership and make the shell-watchdog attribution mechanism explicit.
- Rewrite D1/D2 as explicit C165 amendments with precise effective tool surfaces.

AGREE WITH CHANGES: P17, P18, P19, P20, P21, receipt ownership, shell-watchdog attribution, and precise D1/D2 amendments
