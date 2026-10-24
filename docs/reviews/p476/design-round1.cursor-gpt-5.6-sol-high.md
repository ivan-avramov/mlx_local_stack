1. Location: S4/Q2 and Acceptance 5; `dev/p369_phase2/qualify.py:583-590,946`
   Severity: blocker
   Problem: Removing the four names from `ENTRIES` while retaining their reference rows makes `load_references()` reject the real historical table.
   Failure scenario: Every qualification run aborts on the first pruned reference before testing any remaining model. The suite can miss this because driver tests mock the loader.
   Proposed change: Allow explicitly historical reference names separately from runnable `ENTRIES`, filter references to requested entries, and test loading the real `p415_reference_peaks.json`.

2. Location: Goal lines 9–12 and S3’s generated-output test
   Severity: major
   Problem: “No configgen output names an entry absent from the registry” is not a valid blanket invariant. Generated clients intentionally include the top-level task model, while OpenWebUI intentionally exposes only its four-entry menu, not all five published models. A literal test fails valid output; a six-name blacklist can pass with another stale model.
   Failure scenario: An implementation checks only that the six removed strings disappeared, leaving an unrelated stale model in a carrier while satisfying acceptance.
   Proposed change: Define target-specific expected sets derived from registry roles, `openwebui.models`, and `task_model`, then compare each carrier’s semantic model IDs exactly.

3. Location: S2 and Acceptance 2/5; `openwebui-init/reconcile_models.py:169-190`
   Severity: major
   Problem: Pruning removes the six IDs from `excluded_model_ids`, but the specification has no live OpenWebUI migration or verification. Reconciliation detects absent saved models automatically only when they carry `mlx_local_stack_managed`; older unmanaged registrations lose their tombstones.
   Failure scenario: An old saved registration for a pruned model remains selectable after deployment and routes to a registry that now returns model-not-found, while configgen checks and all suites pass.
   Proposed change: Before deleting the registry entries, reconcile the existing generated policy with `--prune` and a backup, then require live API verification that no pruned ID remains.
