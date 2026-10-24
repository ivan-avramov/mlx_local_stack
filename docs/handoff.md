# Handoff — 2026-10-24 (session 7 END): MTP blessing first (C234); P476 at its last check; B2 strict design review round 1 running

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C234, C233, C232, P479, C231, C230, P477
addendum, C229 … C218, P478, P476, P475, P474), then `docs/specs/p426-b2-tg1-wave2.md` (B2 spec v1 + Goal), `docs/specs/p476-registry-prune.md`
(v3.1), `docs/specs/p426-fable-mtp-recert.md` (plan v4). Model names: FULL registry names only, always (chat included).

## Goal and path (C218, C232, C234)

Certify the top two picks per category (both categories share `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` and `Qwen3.8-27B-mlx-uniform-4bit`)
in their shipped config. MTP blessing FIRST for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: P476 Accept → B2 (four-eyes STRICT) → v8 freeze
(`bench.p426_freeze`, C226) → Wave 2 (pilot OFF/ON → s1 OFF/ON → s2 ON/OFF → reload ON/OFF; ≈ 12.5 h GPU) → B8 / B6 → operator ship call.
The KV-format work (P475 / P475a) is PARKED (C234); `Qwen3.8-27B-mlx-uniform-4bit` keeps KV-first.

## State of the world

- Box `m5max-128`, AC 140 W. GPU IDLE (nothing since the 2026-10-23 P456 rehearsal). OrbStack running (docker grader), no compose services.
- Stack `main` = `6d7fc7cd` + this handoff commit, NOT pushed (≈ 60 commits since `3982b7db`; archive refs `archive/c152-alloc-tool-scope-wip`,
  `archive/p297-uncertain-gone` pushed). Fork `main` `0f30522c`, mlx-serve `86921f02` (unchanged). No worktrees; local branches: stack `main` +
  `evidence`, fork `main`.
- Helper outputs of this session are harvested by a detached script into `$STACK_WORKDIR/parked/session7/` (`DONE` appears when every in-flight
  helper exited): P476 test-writer round 3 + change review round 4, P475 change review round 3, P475a test-writer + change review round 2,
  B2 design review round 1 (sol / glm / sonnet), all frozen tests with `SHA256`, and each test-writer's Cursor chat id (`*.test-writer.chat_id`, for
  `cursor-agent --resume`).

## Work items

1. **P476 (registry prune; four-eyes light; fix round 3 done):** candidate = `$STACK_WORKDIR/parked/p476/candidate4.{stack,fork}.diff` against stack
   `c4faf574` / fork `0f30522c`. Verified so far: full stack suite 7317 passed / 0 failed (round 3), fork suite ×2 identical skips + 8 audits green
   (on the unchanged fork diff), production diff empty. Pending: read `parked/session7/p476-test-writer-round3.md` + `p476-change-round4.*`; if clean,
   **ask the operator to Accept**; then apply both diffs, substitute `P476-STACK-COMMIT` (fork fixture header + `test_mtp_verify_scan.FIXTURE_SOURCE` +
   `m59_policy.json` / answer-key README) with the stack commit, commit stack (S1–S3) → fork commit (S4) → ASK for the fork push → submodule bump +
   K3 + stack suite. Frozen tests: `parked/session7/p476-frozen/`. Records: `docs/reviews/p476/`.
2. **B2 (tg1 legs; four-eyes STRICT, ≤ 3 design rounds):** spec `docs/specs/p426-b2-tg1-wave2.md` v1 (all decisions C219–C228, C232). Round 1 of 3
   dispatched to `gpt-5.6-sol-high`, `glm-5.2-high` (cursor-agent, checkout) and Claude Sonnet (`claude -p`); brief `parked/session7/b2-design-round1.prompt.md`.
   Next: judge round 1 (adopt for the problem, never the mechanism), revise, round 2 if criteria changed; then Go with the cast; build (implementer
   Sonnet, test-writer `glm-5.2-high` via `cursor-agent create-chat` / `--resume`, change review sol + glm).
3. **P475 (KV matrix harness) — PARKED:** candidate after fix round 2 `$STACK_WORKDIR/parked/p475/candidate-after-fix2.stack.diff` (vs `abc15aa8`),
   test-writer PASS (full stack suite 7685 passed). Frozen test `parked/p475/frozen_test_p475_frozen.py`. On resume: one fix round = C233 (MTP-ON
   arms, MTP engagement proof, code-like carrier, native16 OFF reference) + its change-review round-3 findings + **replace the short pick keys
   (the two short `PICKS` keys) with full registry names** (the naming hook refuses them). <!-- allow-shorthand: names the defect --> Spec v3 `docs/specs/p475-kv-matrix.md`.
4. **P475a (fork `qualify --kv-arm`) — PARKED:** candidate `parked/p475a/candidate-after-fix1.fork.diff` on top of `parked/p475a/base-p476-fork.diff`
   (the P476 fork change); spec v3 adds `--predictor on` for arm commits already MTP-ON (C233). Resume after P476's fork commit.
5. **Later:** B8 / B6 (during Wave 2), P477 fused quantized-KV kernel (Phase 2, NAX tensor path for multi-query; ANE not a fit), P478 historical
   tools, R6 / `Qwen3.8-27B-mlx-uniform-4bit` KV + MTP.

## Rules learned (session 7)

- Rank options by quality of outcome; "smallest change" only as a tie-breaker (memory `quality-over-smallest-change`).
- Arms are stack commits served as shipped (C218); a pick's configuration is tuned and certified in its shipped state (AGENTS.md, P480).
- Never two full stack suites at once (shared `$STACK_WORKDIR` test dirs); helpers in scratch copies need `.venv-bench` / `.venv` symlinks.
- Tests never write tracked files (C231). Frozen tests that assume names are re-pointed by the test-writer, never weakened.
- Helper outputs that matter go to `$STACK_WORKDIR/parked/` or the repo before a session ends — the scratchpad is session-local.
- Ask only at four-eyes Go / Accept, pushes and scope changes (C228); keep turns short.

Next decision id C235; discussion ids continue from P480.
