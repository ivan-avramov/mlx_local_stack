# S29 — tg2 where the agent can test before it ships (PLAN M85 phase 1; C389, C390)

v1.0, 2026-11-23. four-eyes STRICT (it relaxes an anti-cheat guard and changes the tg2 identity).

## Goal (verbatim in every brief)

tg2 measures practical agentic coding (rust, javascript, java, cpp under opencode). In practice an agent builds and runs the
project's tests before it declares done. On the current tg2 it cannot: the carrier's anti-lookup shell deny `*xercism*` blocks
cpp's own test build (`-DEXERCISM_RUN_ALL_TESTS`; 39 / 40 cpp sessions per arm hit it, ≈ half of all cpp shell calls denied), and
in every language the shipped Exercism tests are mostly disabled (rust `#[ignore]`, java `@Disabled`, javascript `xtest`, cpp
behind the macro) while the grader runs all of them — so the agent's standard local test command checks only part of what it is
graded on, and enabling the rest by editing the test files makes the grade `tampered`. Solving it means: in every language the
agent's standard test command runs the same full suite the grader runs, is never denied, and never counts as tampering, while a
solution lookup (Exercism / problem-specifications content fetched from outside) stays denied.

## Scope

1. **Testable workspace (tg2 corpus / prepared tree / prompt, the carrier).** T1–T4 below.
2. **Arm-side items that need the identity change anyway.** K1 (the S29-P16 kill-boundary race), K2 (the re-check ack).
3. **Main-side, independent of the identity:** V1 (S26-P19, the KV vision rubric text).
4. Tests and known positives for all of the above.

## Settled constraints

- (operator, C389) The agent must be able to test before it ships; solution lookup stays denied.
- (AGENTS) Never pool across scaffold changes: this is a new tg2 identity; the current A8 rows stay recorded, never pooled.
- (designer) The grader's commands and its view of the tests are unchanged in what they grade (the full suite); the solution
  files the agent may edit are unchanged; the tamper rule (protected files) still holds for everything that is not the solution.
- (designer) The pinned draw / universe stay the same items; only how each item's workspace and prompt let the agent test changes.

## Required behaviour (intent; mechanisms free unless stated)

**T1 — the full suite runs locally.** For every tg2 language and every item of the universe, running the language's standard test
command in the prepared workspace executes every test case the grader executes (none skipped, ignored or disabled). With the
item's reference solution all of them pass; with a stub / broken solution failures are reported per test.
**T2 — the agent is told the command.** The prompt's per-language helper sentence names the command that runs the full suite
(the same one T1 proves).
**T3 — never denied.** That command (and its ordinary variants: build only, run one test, rebuild) is allowed by the carrier.
**T4 — lookup still denied.** Fetching Exercism / problem-specifications content from outside (web fetch, and shell network
fetches such as curl / wget / git clone of those hosts or repos) stays denied, as do the other lookup denies (code search
sites). A local build flag, file or path that merely contains the word is not a lookup and is allowed.
**K1 — the kill-boundary race is the item's own.** A harness kill whose reconciliation shows exactly one trailing failed request
that started at / after the kill signal and processed zero tokens (worker prompt / completion totals unchanged, nothing in
flight before) reconciles as a recorded kill-boundary shape of the item (its order recorded), never an INTEGRITY fault that
invalidates the leg. Any other unexplained inconsistency keeps today's class.
**K2 — the re-check acknowledgement says who.** The sequencer's re-check acknowledgement is recorded with its actor (operator /
designer, with the ruling it rests on) and logged neutrally; a missing actor refuses the ack.
**V1 — the KV vision rubric** asks for accuracy / coverage / precision against the image and carries no reference-caption clause
(the M76 vision corpus has none); its own test; the frozen stage-3 A3 records keep their old rubric binding.

## Acceptance

1. T1 on the real universe: per language, every item, reference solution → all graded test cases run and pass; a stub → per-test
   failures; the count of executed test cases equals the grader's for the same tree (a known positive per language).
2. T3 / T4 by the carrier's own matcher (or a real opencode session): the full-suite command and its variants allowed for every
   language; a lookup per deny class denied; a local path / flag containing the word allowed.
3. The tamper rule: a run that only builds and tests leaves no protected file changed (no `tampered`).
4. K1: the recorded S29-P16 shape (`tg2-m76-n16-s2.a1` javascript/zebra-puzzle's termination + worker summaries) reconciles as the
   item's own; a failed request that processed tokens, or one before the signal with nothing in flight, keeps today's verdict.
5. K2, V1 by their tests. Every changed module's existing tests pass, nothing that passed on the baseline fails.
6. The positives (M85 phase 2) gain a per-language "the agent ran the full suite" record and a lookup-denied record.

## Non-goals

Changing what is graded, the items, the scoring, the decider's statistics, tg1 / A7 (audited separately in phase 6).

## Open questions

None blocking. Mechanism for T1 (prepare-time enabling of the tests vs a test-command configuration) is the implementer's, under
T1–T3 and the tamper rule.
