# M76 spec — verify, round 2 of 3 (strict) — ledger

Material: v1.1 (`e9386d67`), the v1 → v1.1 diff, the round-1 dispositions; brief `brief-r2-verify.md`; context `checkout` (same
read-only copy, v1.1 and C324 staged). Sol and GLM: fresh `cursor-agent --mode ask` sessions (Cursor cannot resume; models
`gpt-5.6-sol-high`, `glm-5.2-high`; user instructions unconfirmed). Sonnet: the round-1 session resumed
(`eff3681e-b658-46f0-8c98-5d6bc9abee76`, `claude-sonnet-5-5`). All exit 0, valid. Raw: `verify-r2-{sol,glm,sonnet}.md`.
This is a check of the diff, not independent discovery.

Round-1 status: GLM all 20 resolved; Sol 15 resolved, 5 not (1, 8, 9, 10, 13); Sonnet resolved / partly (3, 8, 10 open).
The open ones are covered by the new findings below.

| # | raised by | finding | disposition (v1.2) |
|---|---|---|---|
| V1 | Sol P3, Sonnet N4 | B0's "no drafter" condition has no plumbing: `require_environment` / `require_policy_stamps` get no drafter state; an absent scan reads `per_query` | **adopt** (verified `server/generation.py:204-245`, `:1569-1586`): pass the configured `draft_kind`; ON = today's rule, OFF = scan absent + no stamp; re-assert after drafter load; red tests incl. mode + drafter + no scan refused |
| V2 | Sol P4, GLM F1, Sonnet N3 | α contradictory: interval 2.5 / 97.5 % vs the exact bound's 0.05; A5's 7.2 pp is the α 0.05 value (8.8 pp at 0.025) | **adopt**: separate `interval_alpha` / `exact_alpha`, M76 passes one-sided 0.025 to both; A5 figure corrected |
| V3 | Sol P5, GLM S1 | the simulation gates power, not error; no data model, no fixed planning discordance | **adopt**: pre-registered data model (beta per item from stored rows, session random effect), fixed p_d per axis, ≥ 20,000 reps with MC intervals; a look is kept only if its false-PASS upper MC bound at 10 pp ≤ 0.025; asserted by red tests for every final look too |
| V4 | Sol P6 | B7 has no API for paired sessions; changing `paired_delta` globally breaks consumers | **adopt**: new `paired_session_delta` keyed by (item, session); `paired_delta` unchanged |
| V5 | Sol P7, Sonnet N6 | the stage-2 FAIL branch offers an unbuildable / off-candidate XO vs N16-OFF; ABORT ≠ FAIL | **adopt** Sonnet's framing: FAIL → operator (run stage 3 + a separate X ON-vs-OFF certification amendment, or halt); ABORT → diagnose and repeat stage 2 |
| V6 | Sol P8, Sonnet N1 | stage-4 tier 2 adds X only, so V − N16 has no N16 on the added items | **adopt**: added items run on N16, X and V; budgeted |
| V7 | Sol P9, GLM F2, Sonnet N2 | a 5-item whole-output tg1 sentinel misses drift on other axes and fails on timestamps (P611) | **adopt**: identity equality (commits, venvs, grader images, opencode, prompt date, fingerprint) + one item per axis family (exact for single-turn, P640's identical-context criterion for agentic); failure → X reruns with V order-balanced; worst case budgeted |
| V8 | Sol P10, Sonnet N3 | A5 pooling lets a retrieval regression cancel against chain-4; ≥ 0.85 per rung not estimable at 6–7 prompts | **adapt**: per-task gates pooled over rungs (each arm ≥ 0.85, per-task point ≥ −5 pp); per rung descriptive; A5 size 40–80 set by the simulation (PASS ≥ 0.8 at no loss) |
| V9 | GLM F3, Sonnet N7 | the session-disagreement flag is undefined | **adopt**: pairwise, opposite signs AND each session's 95 % interval excludes the other's point; flag blocks the ship recommendation |
| V10 | GLM S2 | byte-identity goldens must be red-first | **adopt** |
| V11 | GLM S3, Sonnet N7 | the look gate's planning discordance is ambiguous | **adopt**: fixed per axis (tg1 0.10, Math500 0.06, A5 0.05, tg2 0.182) |
| V12 | Sonnet N5 | CPU estimate not rescoped | **adopt**: ≈ 7 build-days, ≈ 4–5 calendar days; B0–B2 first so stages 0–2 use the GPU while B3–B7 are built |

Driver note: the worst case rises to ≈ 165 GPU h (≈ 215 h with allowance) because of the stage-4 three-arm coverage and the
sentinel-failure rerun; the expected path is ≈ 80–83 h. v1.2 is not re-reviewed (round 3 of 3 is the operator's call).
