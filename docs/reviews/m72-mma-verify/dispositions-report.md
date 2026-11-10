# M72 matrix-unit verify kernel — four-eyes light: finding ledger (designer's dispositions)

Spec `docs/specs/m72-mma-verify.md` (v1.1 at dispatch, v1.2 after the fix round). Raw outputs: `opinion-gpt-5.6-sol-high.md`,
`opinion-glm-5.2-high.md` (panel, cold, briefed context, cursor-agent `--mode ask`, user instructions unconfirmed),
`testwriter-2-report.md`, `implementer-1-report.md`.

| # | finding | raised by | origin | disposition | reason |
|---|---|---|---|---|---|
| 1 | k = 1 production reference reads the T + 1 bait token; A1 vacuous on planted k = 1 TQ4 rows (prod rel 1.71) | test-writer F1, Sol P3, GLM F2, designer | original | adopted (fix 1) | instrument blind exactly where A2 must bite |
| 2 | A1 floor 2⁻⁸ above production's ≈ 2.5e-3 error: effective bar ≈ 3.1×, not the operator's 2× | side agent → designer | original (designer's spec error) | adopted (spec v1.2, floor 2⁻¹²) | restores the ruled criterion; stricter, so not result-seeking |
| 3 | stale `mma-2.json` in a reused out dir averaged with a new pass 1 | Sol P4 | original | adapted (launcher exit 10 on existing outputs; report refuses mismatched provenance) | plausible rerun path; smallest guard |
| 4 | fixed arm order confounds drift with arm | Sol P6 | original | adapted (pass 2 reversed, `meta.arm_order`) | AGENTS.md: order-balance arms |
| 5 | probe continues when the fragment-mapping self-check fails | Sol P8, GLM F4 | original | adopted (exit 6) + test | cheap gate |
| 5b | extend the self-check to transposed / half / bfloat loads | Sol P8 | scope request | declined | the A1 sweep exercises those operand types end to end |
| 6 | report says "A3 holds" for any non-empty all-failing control list | Sol P9 | original | adopted (exactly six controls) | instrument weakness |
| 7 | launcher mode 644; black / isort; blank line | all | original | adopted | |
| 8 | "exact in half" wording | test-writer F3, Sol P12, GLM F6 | original | adopted | literal error |
| 9 | `last_kv_inputs` written, never read | GLM F5 | original | adopted (removed) | remove an unneeded mechanism |
| 10 | sentinel −1e30 vs logits below it | Sol P1 (major), GLM F3 | original | declined — residual | needs logits ≤ −1e30, outside supported inputs |
| 11 | TQ4 queries in half overflow for components ≥ 2¹⁶ | Sol P2 (major) | original | declined for the prototype — residual, carried to 1.3 | real scaled, rotated queries are orders of magnitude below; production must decide |
| 12 | TQ4 `eff_GBps` uses full-cap bytes | Sol P5 (major) | original | declined — false | `tq.state` slices to `offset` = T (traced) |
| 13 | mapping self-check verifies only columns | GLM F1 (blocker) | original | declined — false | it loads `arange(64)`: each value encodes row·8 + column, so rows are verified |
| 14 | monitor's `sleep 60` child survives ≤ 60 s | GLM F7 | original | declined | no consequence |
| 15 | MTP OFF best-of: min per checkpoint, then interpolate | GLM F8 | original | no change | spec-conformant |
| 16 | `mx.random.bits` absent in MLX 0.32.4; exact `sleep` list over-strict | test-writer, Sol P7 / P11, GLM | test defects | test amendments (test-writer) | frozen tests invalid as written |

## Verify (one per member; fresh sessions — cursor-agent cannot be continued)

Sol (`opinion-verify-gpt-5.6-sol-high.md`): 1–9, 12–13, 15–16 resolved; 10, 11, 14 re-raised as not resolved (no new evidence →
dispositions stand, shown to the operator). New: (17) the probe's TQ4 production reference assumes consecutive lengths for k > 1
(major, Sol) — declined: every length list the probe builds is consecutive (sweep, planted, N1–N3, checkpoints); gapped lengths are
tested only in the fork tests against their own reference; residual. (18) A6 not established (full suite unrun) — resolved by the
clean-clone gates on the temporary-branch commits. (19) the staged repair diff lacks the 100755 mode — material artifact only; the
committed launcher is 100755. GLM (`opinion-verify-glm-5.2-high.md`): every finding resolved or declined with reason; NOTHING OF
SUBSTANCE. Frozen test file reformatted by black in the gate commit (AST identical).
