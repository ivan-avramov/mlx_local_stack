# M72 P2′ stage 1 — design review (strict): finding ledger, designer's dispositions

Spec `docs/specs/m72-p2-stage1-scratch.md` v1 → v1.1 (findings applied once, not re-reviewed). Raw: `opinion-design-*.md`
(cursor-agent `--mode ask`, briefed, user instructions unconfirmed). Preflight (designer, 2026-11-10, P1's generic path vs the
fp32 reference, heads 0 / 6 / 12 / 18, max rel error): T = 8192 — TQ4 production 3.48e-3, P1 bf16 scratch 7.03e-3 (2.02×),
P1 fp16 scratch 4.02e-3 (1.16×); T = 32768 — 3.58e-3, 5.42e-3, 3.81e-3. Memory spike (designer, `benchmark/results/m72/memory/`):
one lazy 16-layer graph holds 6.42 scratches; per-layer evaluation 1.08.

| # | finding | by | disposition | reason |
|---|---|---|---|---|
| 1 | ms vs s in the projection | Sol P1 | adopted | confirmed |
| 2 | interpolation / append source unspecified; tautological native check | Sol P2, GLM F5 | adopted | exact `interp`, append fields, unit test on synthetic data |
| 3 | growing scratch sizes defeat buffer-cache reuse; A4 ignores cache memory | Sol P3 | adopted | cap-sized outputs; growing-T scenario; OS ledger includes cache |
| 4 | A4 window not evaluated / not a chained graph | Sol P4 | adopted | moved to the separate spike (operator), chained graph, per-layer eval mandatory |
| 5 | bit-identical P1 may fail A1 by construction | Sol P5 | adopted | preflight confirmed (bf16 2.02×); fp16 scratch (1.16×) |
| 6 | reference helpers lack explicit T; checkpoint dequant identity unrecorded | Sol P6 | adopted | explicit-T helpers; fidelity on the sweep |
| 7 | N1 strength; heads miss KV head 2 | Sol P7, GLM F7 | adopted | planted distinct constants; heads 0/6/12/18; shift in the SDPA grouping |
| 8 | full-path bit identity exceeds the operator's requirement | Sol P8 | adapted | dequant fidelity kept (cheap, strong); accuracy is the gate; full-path identity a diagnostic |
| 9 | criterion naming; `--max-t` scope | Sol P9, GLM F8 | adopted | |
| 10 | `rot_fused()` passes `qp`, not `qr` (blocker) | GLM F1 | declined — false | the material's line 212 passes `qr` |
| 11 | A4 must exclude SDPA's own transients | GLM F2 | adopted | SDPA-only baseline scenario |
| 12 | codebook dtype at the multiply | GLM F3 | adopted | fp32 at the multiply |
| 13 | causal alignment for L < T unstated | GLM F4 | adopted | stated + tested |
| 14 | fp32 reference cost at 262,144 | GLM F6 | adopted | per head, freed before timings |
| 15 | in-place check unspecified | GLM F9 | adopted | identity + sentinel-past-T test |
| 16 | RHT assumption | GLM F10 | adopted (assumption) | |
| 17 | provenance refusal fields | GLM F11 | adopted | arm orders + kernel meta |
| 18 | dequant share is a diagnostic | GLM F12 | adopted | |

## Verify (strict; fresh sessions) and fix round

Sol (`opinion-verify-gpt-5.6-sol-high.md`): design findings 1–18 resolved except: (7) N1 uses random per-head-scaled data, not
fixed constants — declined (N1 fails at rel 5.2–5.5, seed fixed; no material consequence); (17) report accepted a single pass —
adopted (fix 2); new (19, blocker) full-cap acceptance not yet run — process, resolved by running the two-pass measurement and A4
before Accept; (20, major) A1 over several heads compared independent maxima — adopted (fix 1); (21) integration of tests / skip
entry / amended parser test — resolved at the merge commit; (22) the designer's memory spike ignored `dep` for p2s — fixed by the
designer (`78ae2819`). GLM (`opinion-verify-glm-5.2-high.md`): no blocker or major; M1 causal-alignment diagnostic on the full path —
adopted (fix 3); M2 = Sol 20. Test-writer minors: hard-coded 262,144 — adopted (fix 4); bare `KeyError` on an unsupported dtype —
adopted (fix 5). One fresh fix-round implementer; failing-case tests for 1, 2, 3, 5 fail on candidate 1 and pass on candidate 2.
Accepted by the operator 2026-11-10 ("accepted - sounds like a good plan"); merged fork `608e33ac`, stack `ed0348c2`.
Post-accept finding (real activations, `benchmark/results/m72/realact/`): S20-P18.
