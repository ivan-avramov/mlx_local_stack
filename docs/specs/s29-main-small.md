# S29 — two main-side fixes before the next KV panel (PLAN M85; split from `s29-tg2-testable.md` by its design review, Sol P6)

v1.0, 2026-11-23. four-eyes light (main-side, no identity change).

## Goal (verbatim in every brief)

Two records currently say something that is not true. (1) The Wave 2 sequencer logs every re-check acknowledgement as
"acknowledged by the operator", whoever passed `--recheck-ack` (S29-P13: it was the designer's, under C383), and the sealed
`sequence.json` records no actor at all. (2) The KV panel's `vision` rubric tells judges to compare "against the human reference
captions given in the prompt", but the M76 vision corpus has no captions and the packets carry none (S26-P19). Solving it means:
the acknowledgement record and log say who acknowledged and on what ruling; the vision rubric asks only for what the packets
support; neither change alters any frozen record.

## Required behaviour

K2. A re-check acknowledgement is recorded in `sequence.json` with its actor (`operator` / `designer`) and the ruling it rests on;
    the log line names them and never asserts an actor it was not given; an acknowledgement without an actor refuses (nothing
    resumes). An already recorded acknowledgement without an actor (the S29-P13 one) stays as recorded and is accepted on resume.
V1. The KV `vision` rubric asks for accuracy / coverage / precision against the image and names no reference captions. Frozen panel
    records keep the rubric text and sha they were frozen with; a new export binds the new text (its own `rubric_sha256`).

## Acceptance

Tests for each: K2 the success path, the missing-actor refusal, the legacy record accepted; V1 the new text has no reference
clause, the frozen stage-3 A3 records still verify against their own rubric sha. Existing tests that pin the old wording change,
listed; nothing that passed on the baseline fails.

## Non-goals

Re-judging A3; any tg2 identity change.
