# Handoff — 2026-10-06 (03:00 UTC): harness gaps fixed (C116), dsh frozen (C117), M58 spec v3.1 + STEP 1 PASSED (build held, C118), ReviewBench DEFERRED (C122); stack down, nothing pushed

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (M58 row) and `docs/open-questions.md`
(C116–C122). Previous handoff (M57 adoption narrative, mechanisms, leftovers): `git show d92c741:docs/handoff.md`.

## Done this session (all committed on `main`, NOT pushed: `64bea61`, `80bc755`, `4d2f3fd`, `2cbd5fe` + this)

- **Harness gaps (handoff item 4) — `64bea61`.** Central placeholder scrub of every manifest `runtime` string (`$STACK_WORKDIR`, `$HOME`,
  boundary-aware; `provenance.portable_path` / `expand_portable`); C116: ladders run a provenance PREFLIGHT gather at entry and never
  publish a result whose end-of-run gather failed (`.pending-<pid>`, rc 3); capacity rows carry `sdpa`; generate rows carry
  `content_sha256` / `reasoning_sha256`; Codex review 10 B2/B3 closed. Two cold reviews folded (Claude, Codex `gpt-6-astra`).
  Test suite: identical failure set to baseline (13 `test_agentbench_adapter` tests need the repo-relative corpus cwd; pre-existing).
- **dsh runner FROZEN (C117)** like aider; rows retained; M50 tests parked in `$STACK_WORKDIR/harness-gaps/`.
- **M58 spec v3.1** `docs/specs/m58-joint-verification-scan.md` after two cold reviews (`$STACK_WORKDIR/m58/*review*`). Key finding
  (Claude review, measured): joint ≠ per-query bitwise across MLX key-length thresholds → rule 7 straddle fallback using the fork's
  plan mirror; the shipped `length == 2` branch is already inexact there (C120, folded in).
- **M58 STEP 1 PASSED** (`$STACK_WORKDIR/m58/verify_microbench.run1.json`; lab notebook 2026-10-06): mirror exact 208/208; `qL ≤ 5`
  identical; −19…−21 % per-layer scan time at 64K–256K; not faster at 8K; `"causal"` string beats the bool mask. **BUILD HELD — operator
  decision C118.**
- **ReviewBench DEFERRED (C122)**; reasons annotated at the top of `docs/proposal-reviewbench.md`. Cold review kept in
  `$STACK_WORKDIR/reviewbench/`.

## Open items, in priority order

1. **First daily-driver start under M57 is still unverified** (worker cmdline `--attention-policy fused_v1 --lazy-prompt-embeddings`; one
   `Request completed` line with `sdpa_forced > 0` on a long prompt; one vision turn through OWUI). Operator starts `runserver.sh`.
2. **C121 — opencode sessions are UNSEEDED** (found by the ReviewBench review, verified): proposal owed BEFORE any new opencode rows —
   per-session seed in provider options, a captured request body proving it reaches the router, lab-notebook retraction of the
   "distinct paired seeds" wording (no rerun; ranks were stable). Same proposal: `OPENCODE_DISABLE_CLAUDE_CODE` never set (R8).
3. **C118 — M58 build go/no-go.** If go: Sonnet implementer from spec v3.1 (AC1–AC12), two cold reviews, live smoke, then gate 1.
4. **M57 certification debt** (judge panel + Math500 on the FINAL state) — after M58 if M58 is built, else now.
5. **C119** — `generate` records transport errors as rows (pre-existing; needs its own proposal).
6. Unresolved: branch `auto` 1.4–3.6 % slower than previous shipped code (handoff d92c741 item 5).

## Rules learned this session

- "Bit-identical" is a property of the kernel plan at each key length, not of the math: sweep every dispatch threshold and make the
  fallback predicate the same one the kernel uses.
- Cold reviewers that MEASURE (a 5-second GPU check) beat reviewers that read; ask for known-positive checks in the brief.
- A best-effort provenance path hides mixed pairs; preflight at entry is what makes strictness affordable.
- `codex exec -s read-only -C <repo> - < prompt.md` with a workdir `TMPDIR`; the review text lands in the stderr log, not stdout.
- The naming hook rejects external judge/gold model names too; mark such lines `allow-shorthand` with a reason.

Next decision id C123; discussion ids continue from P106.
