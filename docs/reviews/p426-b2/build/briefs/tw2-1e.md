# Delivery 1e (same session, still blind): amend the frozen tests the later seams invalidated, then the set is frozen again

The designer judges the frozen tests you listed in your §4 items 1 and 2 invalid: they were written before §16.5 and now contradict it (the designer's later change, not your error). You amend them; the designer freezes the whole set again afterwards. §16.6 (`.b2-spec-v3.2-16d.diff`; the copy's spec is updated) names the sequencer handle, the inputs the sequencer classifies a leg from, the `OVERRUN_PAUSED` / dossier / occurrences paths and formats, the harvest refusal and the census identity — your remaining §3 gaps.

Do:
1. Amend the frozen files where they contradict §16.5 / §16.6, keeping every behaviour the specification supports: the s4 A4 tests to `a4_window_problems(lines, a4_receipt, a4_gate)` with the anon check; the frozen `p426_world` (in `b2_frozen_support.py`) with the §16.5 seams (`expected_worker_argv`, `busy_procs`, `descendants`) and a `create_time` that answers the owned worker's start, so the s7 chain tests exercise the real checkpoints. Keep test names; list every amended test.
2. Align the `add_` files and fixtures with §16.6 where you had chosen otherwise (handle fields, the classification inputs, paths, `HarvestError`, `ops.harvest(leg_root, emails=…)`), and add a rehearsal-leg test that receives a key over `--hmac-fd`.
3. Run every file (frozen and `add_`) and the support checks on the baseline; every support check must pass.

Report as before, with a separate list of the frozen tests you amended and why.
