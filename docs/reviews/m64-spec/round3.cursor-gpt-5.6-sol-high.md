Reviewed the requested files at `2760015f`; targeted content is unchanged in the current checkout.

## 1. Prior findings

- P17 — **Partly.** OLS intercept is now confirmatory, but code-length definition and exact refit/shift-bootstrap TOST procedure remain unspecified.
- P18 — **Yes.** Cell TOSTs, intersection-union claim p-values, unavailable=`p=1`, and the fixed 12-claim Holm family are defined.
- P19 — **Yes.** Synchronous audit, same-slot rerun, preparation, token carry-over, and operator blocking are specified.
- P20 — **Yes.** Full slot identity, reload protocol, second-failure row, and token carry-over are explicit.
- P21 — **Yes.** Hashed exact-graded-code snapshots and packet manifests are required.
- Receipt ownership — **Yes.** Assigning receipts to the `mlx-vlm` worker correctly supersedes the plan’s inaccurate router wording.
- Shell-watchdog attribution — **Partly.** §5.4 defines attribution, but §6’s generic “detached child” positive conflicts with the acknowledged pre-tick G2 escape.
- D1/D2 amendments — **Partly.** D1 is properly framed; D2 presents the right choices but subsequent sections already assume choice (b).

Still-partly round-1 findings:

- P4 — **Partly.** REJECT/HOLD is correct, but the adopted dsh release and effective surface necessarily await inventory and D1/D2.
- P5 — **Partly.** Ownership and range correlation are defined, but the end-mark/drain semantics for disconnected in-flight generations are not.
- P8 — **Partly.** Observable descendants get a deadline; claiming an unqualified equal deadline remains too strong given G2.
- P11 — **Yes.** Attempt identity, recovery, cumulative tokens, and `transport_dnf` are specified.

## 2. New v3 problems

- P22 — **Opencode treatment contradiction.** §5.1 says the M64 carrier differs only by `compaction.auto`, but the current carrier denies `websearch`, `question`, `execute`, and `subagent`. D1 covers the latter two and D2 may change `websearch`; `question` is unaddressed despite C165 2a. Existing tests confirm it is absent from the wire tool list.
- P23 — **M64 judge gate remains ambiguous.** §11 requires per-judge exclusion, while `judge_gate.py` implements panel-level anchor metrics, majority aggregation, κ/α, and missing-as-tie. “Thresholds from `judge_gate.py`” does not define the promised new M64 path.
- P24 — **Length-adjusted inference is not reproducible.** Define code length units/files, the ≥50% denominator, OLS refitting in every bootstrap replicate, both TOST p-values, and degenerate/zero-variance handling.
- P25 — **Receipt range closure is incomplete.** The worker must assign sequence numbers at request admission; the end mark must fence admissions and wait for every preceding request—including disconnected generations—to finalize. Otherwise late receipts can fall outside the attempt.
- P26 — **Attempt-state composition is ambiguous.** Distinguish a registered native client cut (`client_inactivity`, scored strict failure) from a transport client timeout (incident/retry), and define precedence when one attempt has both transport failure and auditable web evidence.

The existing opencode-only audit paths, block-level restart, M38 judge path, and absence of worker generation receipts are expected BUILD work, not independent reasons to reject this pre-build specification.

## 3. D1/D2 and BUILD readiness

D1 is correctly framed as C165 (2c): snapshot-dependent, narrowly limited to concurrent model-session tools, with rejection requiring redesign.

D2’s decision framing is correct, and recommendation (b) is defensible. Its integration is not: §6 assumes (b), while §5.1 claims compaction is the only carrier change. Either ruling must be propagated through the treatment, carrier, and contract tests.

The specification is not yet complete enough for a BUILD go conditional only on D1/D2. P22–P26 are specification ambiguities that could produce materially different implementations or estimands.

## 4. Minimum edits to agree

1. Reconcile §5.1 with the ruled effective opencode tool surface, explicitly resolving `question` and D2-dependent `websearch`.
2. Define the M64-specific per-judge gate and complete the length-adjusted bootstrap/coverage contract.
3. Add receipt end-fence/drain semantics.
4. Define client-cut versus transport-timeout classification and transport/P201 precedence.
5. Scope the detached-child positive to an observed/tracked detach and retain immediate pre-tick escape as G2.
6. After the operator rules, record C165 (2c)/(2d) and parameterize §6 accordingly.

AGREE WITH CHANGES: opencode tool-surface/parity reconciliation; M64 judge and length-adjusted inference contract; receipt end-fence semantics; client-cut/transport/P201 state machine; scoped detached-child watchdog test; D1/D2 ruling propagation
