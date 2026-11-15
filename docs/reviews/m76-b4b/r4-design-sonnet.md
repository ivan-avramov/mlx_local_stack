I found nothing that would make a tg2 leg fail to run, make the harvested evidence unusable for B4b-2, or silently drop a tg1 guarantee. The v3 defects I traced earlier are fixed in v4, and the new text is consistent with the code I checked:
- The snapshot now lives outside `grading-private`.
- The bookkeeping regex covers `ls-<volume>`, `<step>-n-x` and `plan-<container with uppercase T>`.
- The re-check record is sealed before `publish_run_files`.
- The rehearsal CLI carries the pair, both worktrees and the date, and v8 reads its settle-bound inputs.
- `--evidence p426` is keyed on the config id.
- The stall selector is corpus-driven.

Two small points remain, followed by suggestions on over-engineering.

## F1 — R2 / R3 arm assignment is ambiguous
- **Location:** spec §2 table row "rehearsal `r2` / `r3` (each arm)" and §3 v8 (`--r2 L --r3 L`).
- **Severity:** minor. **Evidence:** confirmed from the spec text and from `p426_freeze.py:249-253` and `:675`.
- **Problem:**
  - The table says each arm runs R2 and R3, which is four rehearsal legs. v8 takes one R2 leg and one R3 leg.
  - tg1's kv convention is R2 on the test arm and R3 on the reference arm. v3 said N16 only.
  - `rehearsal_problems` / `binding_problems` bind one leg per case.
- **Scenario:**
  - An implementer who runs four rehearsal legs wastes GPU time on rehearsals the v8 command never reads. The test-writer then has two possible bindings to test.
  - A pair of N16-only legs would leave X's reconcile path unrehearsed.
- **Change:** state one assignment. I recommend tg1's: R2 on X (it exercises X's serving path through reconciliation), R3 on N16. The table row then reads "r2 on X, r3 on N16".

## F2 — The testing rule needs one clarification
- **Location:** spec "How to read this spec" and acceptance criterion 1.
- **Severity:** minor. **Evidence:** confirmed from the spec text.
- **Problem:** the preamble says "no mocks of the functions this spec names". Criterion 1 says "mocked box" and "a mocked agent". A test-writer cannot tell which seams may be faked.
- **Change:** say that only the router, worker, agent and docker daemon may be faked, and that the spec-named functions (the grade call, builders, readers, harvest classifier, hooks) run for real.

## Over-engineering (simplifications that keep the goal)
- **12 injected positives.**
  - The stall, loop and alloc gates are language-independent: the `ls` / `sleep` / `python3` prompts are the same in every language.
  - The language-specific risk is the grader, which the per-language stub-FAIL / reference-PASS check already covers on real trees.
  - Running the three kinds on one language (3 runs, not 12) would lose no guarantee. M65 step 4 says "one item per language", so this is the operator's call.
- **Positives-record identity comparison.** The §3 order has v8 compare "every identity field" of the positives record to live inputs, and the sequencer re-verify the sha at start and on resume. A sealed record whose sha is pinned in v8, plus an N16 commit check, gives the same protection. The field-by-field comparison adds code and tests without adding protection.
- **R2 / R3 GPU rehearsals.**
  - They re-prove tg1's reconcile-mismatch and probe-kill mechanisms. Only the target-language selector changes for tg2.
  - The pilot pair already exercises the positive reconciliation path on real tg2 items.
  - The negative paths are language-independent. A red test per tg2 selector (R2 gives INVALID `R2_REASON`, R3 gives a scored kill, both on a real Rust item path) would cover the change.
  - Dropping the GPU legs needs `cmd_v8` to accept the existing tg1 rehearsal manifest for the same pair. That is a trade against keeping v8's structure, so it is optional.