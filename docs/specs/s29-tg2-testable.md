# S29 — tg2 where the agent can test before it ships (PLAN M85 phase 1; C389, C390)

v1.1, 2026-11-23. four-eyes STRICT (it relaxes an anti-cheat guard and changes the tg2 identity). v1.1 applies the design review r1 (Sol P1–P7; adopted / adapted, not re-reviewed): K2 and V1 moved to a separate main-side change (`s29-main-small.md`).

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
2. **The arm-side item that needs the identity change anyway:** K1 (the S29-P16 kill-boundary race).
3. Tests and known positives for all of the above. (K2 — the re-check ack actor — and V1 — the KV vision rubric — are main-side
   and identity-independent: a separate small change before the phase 3 panel.)

## Settled constraints

- (operator, C389) The agent must be able to test before it ships; solution lookup stays denied.
- (AGENTS) Never pool across scaffold changes: this is a new tg2 identity; the current A8 rows stay recorded, never pooled.
- (designer) The grader's commands and its view of the tests are unchanged in what they grade (the full suite); the solution
  files the agent may edit are unchanged; the tamper rule (protected files) still holds for everything that is not the solution.
- (designer) The pinned draw / universe stay the same items; only how each item's workspace and prompt let the agent test changes.

## Required behaviour (intent; mechanisms free unless stated)

**T1 — the graded suite runs locally.** For every tg2 language and every item of the universe, running the language's standard
test command in the prepared workspace executes exactly the test cases the grader grades — every graded leaf, none of them
skipped, ignored or disabled; the grader's frozen optional leaves (`OPTIONAL_LEAVES`) stay optional / skipped locally as they are
graded. With the item's reference solution all of them pass.
**T2 — the agent is told the command.** The prompt's per-language helper sentence names the command that runs the full suite
(the same one T1 proves).
**T3 — never denied.** That command (and its ordinary variants: build only, run one test, rebuild) is allowed by the carrier.
**T4 — lookup still denied.** Fetching Exercism / problem-specifications content from outside (web fetch, and shell network
fetches such as curl / wget / git clone of those hosts or repos) stays denied, as do the other lookup denies (code search
sites), for any letter case and inside a compound command (e.g. a permitted build command chained with a fetch). A local build
flag, file or path that merely contains the word is not a lookup and is allowed. The supported threat is a cooperative agent
looking things up, not an adversary obfuscating a fetch.
**K1 — the kill-boundary race is the item's own.** A harness kill whose reconciliation shows exactly one trailing failed request
of the item's own session (the worker's `requests_started` and `requests_failed` each +1, `requests_completed` unchanged, nothing in
flight at the pre-signal sample, the failure recorded at / after the signal) is the item's own accounting: recorded (the
`accounting_fault` class: its tokens / latency descriptive only), never an INTEGRITY fault that invalidates the leg. Failed
requests expose no token counts, so no zero-token proof is required: the client was killed, nothing it received can enter the
item's outcome. Any other unexplained inconsistency keeps today's class.
**I1 — a new identity.** The change produces a new tg2 scaffold / identity value that binds the carrier, the prompt (helper
sentences) and the workspace preparation; rows of the old and new identity never pool (the existing pooling / identity
refusals see them as different).

## Acceptance

1. T1 on the real universe: per language, every item, reference solution → the locally executed test cases equal the grader's
   graded leaves for the same tree (count and names) and all pass; per language one known negative — a solution that compiles but
   is wrong — shows failures locally and in the grader.
2. T3 / T4 by the carrier's own matcher (or a real opencode session): the full-suite command and its variants allowed for every
   language; a lookup per deny class denied; a local path / flag containing the word allowed.
3. The tamper rule: after the stated local build-and-test command (and its variants) in a prepared tree with the reference
   solution, the production tamper check (`tamper_reasons`) returns no reasons.
4. K1: the recorded S29-P16 shape (`tg2-m76-n16-s2.a1` javascript/zebra-puzzle's termination + worker summaries) is the item's own
   accounting, the leg not INVALID; a shape outside K1 (e.g. a failed request with nothing started, or a completed-count change)
   keeps today's class.
5. I1: the old and new identities differ, and a row of each refuses to pool. Every changed module's existing tests pass, nothing
   that passed on the baseline fails.
6. The positives (M85 phase 2) gain a per-language "the agent ran the full suite" record and a lookup-denied record.

## Non-goals

Changing what is graded, the items, the scoring, the decider's statistics, tg1 / A7 (audited separately in phase 6).

## Open questions

None blocking. Mechanism for T1 (prepare-time enabling of the tests vs a test-command configuration) is the implementer's, under
T1–T3 and the tamper rule.
