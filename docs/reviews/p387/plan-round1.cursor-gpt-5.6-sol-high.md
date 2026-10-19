# P387 build note v1 — Cursor gpt-5.6-sol-high PLAN review round 1 (2026-10-19)

Prompt: `the scratchpad p387-plan-r1.md` (build note v1 + plan v7 §5 + the five interim lines verbatim); workspace `../mlx-vlm` at `24551869`, branch read at `c10205ae`. Output verbatim:

K1 — HIGH  
Problem: The accepted MTP-ON state is incompatible with the existing live-overlay test. `overlay_registry()` requires C177-commented lines, so an exact fixture registry contains nothing to restore.  
Scenario: Opt-in acceptance approves the verbatim fixture, then `test_overlay_on_the_live_stack_registry` calls `overlay_registry()` and fails with “expected 2/3 C177 lines.” Current acceptance only exercises the live interim, so this is missed.  
Fix: Classify the live state first. Overlay only the interim; for MTP-ON, assert it already equals the fixture. Add a require-mode suite run against both accepted states.

K2 — MEDIUM  
Problem: Prefix matching contradicts the claimed exact C177 interim. Parsed-minus-five equality cannot validate discarded comment text.  
Scenario: Changing a marker to `# P369 INTERIM (C177 altered reason)` still passes after uncommenting because the restored YAML equals the fixture. That registry is neither verbatim fixture nor the supplied verbatim interim.  
Fix: Construct the expected interim using the five complete replacement lines and compare bytes directly. Add cases mutating marker suffixes and trailing text on commented `draft_model` lines.

K3 — MEDIUM  
Problem: The proposed determinism test does not independently exercise sibling-checkout isolation because `MLX_STACK_REGISTRY` shadows the synthesized sibling. Removing the sibling-drift test leaves this channel unguarded.  
Scenario: A future regression reads the sibling only when the environment variable is absent. All planned runs can pass in a worktree without that sibling, while ordinary tests fail on an operator checkout.  
Fix: Add separate poison tests: env set with sibling absent, and env unset with `SIBLING_REGISTRY` pointing to the interim. Both must return fixture sampling.

K4 — LOW  
Problem: The claim that every listed red test fails today for its stated reason is inaccurate. Existing require mode already rejects partial interim, unmarked lines, extra edits, absent paths, and missing live registries. Those negative tests are guards, not red tests.  
Scenario: The negative matrix passes against the old blanket byte-equality implementation, providing no before/after proof of the new classifier. If it fails only because a new helper is undefined, that is not the stated behavioral failure.  
Fix: Record the true baseline: full-interim acceptance and fixture refresh are red; invalid-state cases are characterization guards. Add a red-commit run listing the exact failing test IDs.

Subject to those changes, the fixture refresh is safe given the measured facts: no other repository code reads this fixture, existing consumers depend only on unchanged sampling/KV/scheme values, and routing `deployed_sampling()` through `certified_registry()` removes the remaining ordinary-test registry dependency. Full byte comparison also correctly rejects partial, reordered, duplicated, wrong-block, CRLF, and trailing-newline variants.

VERDICT: AGREE WITH CHANGES K1,K2,K3,K4
