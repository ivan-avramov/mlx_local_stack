# P369 phase-2 — Cursor gpt-5.6-sol-high review, OPERATOR-AUTHORIZED round 4 (P398 judgement, narrowed claim, proposal B, round-3 fixes; fork `p369-mtp` `0d06bb0c`, 2026-10-19)

Prompt: `round4-p398.prompt-head.md` + the smoke-3 evidence + plan v9 §2.2 + the round-3 output + `git diff fa89d19b..0d06bb0c`; `--mode ask`, stream-json — the `result` text verbatim:

P1 — Production isolation is verified: `4e6d0e03..0d06bb0c` is empty under `mlx_vlm` excluding tests. I’m checking one key unresolved issue before accepting the artefact claim: whether the new forced-position counter is tied to actual emitted positions or merely to criteria invocations, especially around cut blocks and length termination.P2 — Q1 — DISAGREE, with qualification

The row mismatch itself is an instrument artefact: ON could not have sampled `</think>` from a row assigning it zero probability. `_mtp_plain_emission` cuts the verified block before forced emission, and the forced branch emits without sampling (`mlx_vlm/speculative/mtp.py:811-884`). Removing that stale row is correct.

However, the evidence does not prove ON forced at the same positions plain decoding would. A real hidden failure is possible:

- ON forces at position 130.
- OFF1 would not force there, but the recorder replaces its sampled output with ON’s `</think>` (`dev/p369_phase2/observe.py:287-292`).
- Consequently tokens, cache states, probes, and OFF1/OFF2 C1 all remain identical.
- The old ON stale row creates the observed mismatch; P398 then removes and excludes it.
- ON and plain forced-pop schedules nevertheless differ—a real MTP neutrality failure.

Thus the stale-row diagnosis is sound, but concluding full neutrality from it is premature until forced schedules are compared.

P3 — Q2 — DISAGREE

“Every sampled emitted position is bit-identical” is accurate. Excluding forced positions from row comparison is also correct because no sampler chooses those tokens.

But “forced positions are covered by E6” is too strong. E6 proves only that ON’s row-less positions equal ON’s recorded forced emissions (`dev/p369_phase2/compare.py:86-105`). It does not prove plain decoding would force at those same positions.

State hashes and probes cannot close this gap because OFF replay is already driven down ON’s token history. E2 token identity likewise cannot reveal a coincident or externally forced schedule difference.

P4 — Q3 — AGREE on the residual and proposal’s core; DISAGREE that B is sufficient as written

The residual is real. An OFF criteria override can make both OFF runs deterministically disagree with ON, causing `c1_acceptance()` to report C1 failure (`dev/p369_phase2/worker.py:819-825`) and `pick_outcome()` to choose ABORT before FAIL (`dev/p369_phase2/orchestrate.py:483-490`).

Required design:

1. Record `(position, token)` forced-pop lists for ON, OFF1, and OFF2.
2. OFF1 versus OFF2 list mismatch means C1 instability → ABORT.
3. ON versus stable OFF1/​OFF2 list mismatch means MTP non-neutrality → FAIL.
4. Ensure ON/output disagreement caused by that established schedule mismatch cannot be reclassified as C1 ABORT.

The cleanest implementation is to make OFF pops observational: record and consume the real pop, but return `None` so it cannot override the already ON-forced replay token. This preserves identical replay history while exposing the plain forced schedule directly.

P5 — Q4

- E6 — RESOLVED. Forced pops carry intended positions; every emitted pop must be row-less and token-equal, with only one pop at exactly `len(tokens)` allowed under a length finish (`dev/p369_phase2/compare.py:86-105`). The real criteria-call counter supports those positions (`dev/p369_phase2/observe.py:331-345`).
- E7 — RESOLVED. All-invalid cells retain every attempt and reduce to ABORT, FAIL, or INCOMPLETE with the required precedence (`dev/p369_phase2/orchestrate.py:1923-1940`).
- E1 — RESOLVED for the reported defect. `cross` is now required to be a non-empty dictionary (`dev/p369_phase2/orchestrate.py:559-562`).
- Production isolation — VERIFIED. `git diff --exit-code 4e6d0e03 0d06bb0c -- mlx_vlm ':(exclude)mlx_vlm/tests'` returned 0.

E8 — BLOCKER — `dev/p369_phase2/observe.py:287-292,341-345,367-373`; `dev/p369_phase2/worker.py:1094-1158`

Problem: Only ON forced pops are recorded; OFF’s actual forced schedule is neither observed nor controlled separately from C1.

Failure scenario: ON forces `</think>` at position 130 while plain would not. The OFF recorder nevertheless emits ON’s token, leaving outputs, states, probes, and C1 identical. P398 excludes position 130 and reports all sampled rows equal, hiding the schedule non-neutrality.

Fix: Record ON/OFF1/OFF2 forced traces, require stable OFF traces for C1, classify ON-versus-OFF trace differences as FAIL, and prevent that established difference from becoming ABORT. Prefer observational suppression of OFF overrides.

E9 — LOW — `dev/p369_phase2/orchestrate.py:575-608`

Problem: E2 validates that every pair key exists in `cross`, but silently ignores extra cross-load keys.

Failure scenario: A request-routing or result-assembly error adds an unexpected cross-load result; E2 can still PASS while that trajectory is never compared.

Fix: Require `set(cross) == set(pair)` and route a mismatch through `MalformedEvidence`.

VERDICT: NOT CLEARED E8
---

Lead (2026-10-19): E8 and E9 fixed test-first per the reviewer's design (observational OFF pops) — fork red `14bc404a`, fix `f0b41d44`; not re-reviewed (operator decides).
