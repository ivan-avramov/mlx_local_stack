I made all three fixes in `dev/p369_phase2/qualify.py`. Ten frozen tests fail: the 7 known ones, plus 3 that the new fix 3 refusal breaks on purpose. Nothing else changed: `registry_states.py`, production code under `mlx_vlm/` and the tests are as they were. Nothing is committed, and I didn't run black/isort.

**P1 — Fix 1 (`sdpa_forced` must be a real count).** In `request_problems`, the old `rec.get("sdpa_forced") or 0` treated a missing or bad counter as 0. Now, whenever the expected manifest is known, the counter must be present and an `int` (not a bool) that is ≥ 0. Anything else adds the problem `sdpa_forced <value> is not an integer >= 0 (attention <policy>)`, so a missing value, `None`, a negative number, NaN or a float all fail. Then the rule is as before: the count must be > 0 if the policy is `fused_v1` and the expected manifest has a native leaf, and exactly 0 otherwise.

**P2 — Fix 2 (no attention verdict without a manifest).** The whole attention check now runs only when `native_attention is not None`. Without a manifest there is no `sdpa_forced` verdict under any policy, `auto` included. Before, the check was skipped only under `fused_v1`.

**P3 — Fix 3 (an MTP-ON KV arm refuses).** In `kv_arm_gate`, after the existing MTP-OFF refusal, `--predictor on` with a non-empty delta now refuses with `--kv-arm --predictor on: an MTP-ON KV arm is uncertified; preflight it with --predictor off`. With an empty delta it carries on as today's `--predictor on`, and the certified-argv binding (C199) still applies. I updated the docstring to match.

**Summary line, verbatim:** `10 failed, 1084 passed, 2 skipped, 2 warnings in 122.06s (0:02:02)`

**P4 — The 10 failures:**
- **The 7 known driver-helper failures:** `test_refuses_a_third_entry_even_when_the_registry_is_an_accepted_state` ×3, `test_refuses_a_third_entry_whose_kv_keys_were_changed` ×3, and `test_refuses_an_unknown_entry_listing_the_registry`.
- **3 new ones:** `test_predictor_on_serves_the_committed_mtp_on_arm_registry_without_an_overlay[fable-AF8]`, `[uniform-AF4]` and `[uniform-TQ8]`. Each is refused with the fix 3 message, which I confirmed by re-running them.
  - These tests still assume the old v3 rule that the arm is "served as is" under `--predictor on`, and they forge a P369 summary to make it work. That is the gap GLM's F1 points out.
  - Under v4.1 these three cases must refuse, so the tests are out of date, not the code. They need rewriting as refusal tests.
  - `[fable-N16]` (empty delta) still passes, as v4.1 requires.
  - This should go to the test-writer along with the 7 known ones.
