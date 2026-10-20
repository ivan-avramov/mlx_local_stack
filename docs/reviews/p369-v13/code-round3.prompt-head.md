Cold CODE review — ROUND 3 OF 3 (the LAST round: open findings after it go to the operator as a table). Fork `mlx-vlm` branch
`p369-v13` HEAD `a2808acf`, on top of the reviewed P405 head `64afc7dd`. Workspace `../mlx-vlm` at `24551869`; read with
`git show a2808acf:<path>` (read-only). Production code is UNCHANGED (`git diff 64afc7dd a2808acf -- mlx_vlm ':!mlx_vlm/tests'`
must be empty — verify). Your round 2 (inline below) returned `NOT CLEARED M1 M2 M3 M5 M7 N1 N2 N3 N4` on `5f407d5d..d36d33c5`
(M4 M6 M8 M9 M10 closed). This round reviews `d36d33c5..a2808acf`: `d4256803` (red tests) and `a2808acf` (green). Plan v13
(`docs/specs/p369-phase2-run-plan.md`, STACK repo) is inline below, as are the operator rulings C184 / C193 / C194.

Disposition of round 2:
- M1: test-only — the new test drives `Campaign.prepare()` itself; a spy stops at the classifier and asserts the CR bytes reached
  it and are refused. Mutation-checked: `prepare()` reverted to `read_text()` turns it red at that assertion.
- M2: `telemetry` is imported at module top with the existing script fallback (telemetry is stdlib-only at import); each
  invocation needs a `drafter.`-prefixed non-empty block and a non-empty list of unique `int` (not bool) expert ids in
  `[0, PICKS[pick].drafter.experts[0])`. Tests: direct-script mode in a `python -I` subprocess with only `dev/p369_phase2` on the
  path (red: ModuleNotFoundError), nine malformed shapes (red: all passed the gate).
- M3: `check_loaded_drafter(model, drafter, shape)` binds the loaded drafter to the served target — exactly `reset()`'s
  `bind(model)` at each request start — then reads its identity; `run_job` uses it. A bound method is identified by owner, name
  and `__func__` (a builtin by itself). Tests: a freshly constructed, unbound served-shape MoE drafter passes the gate with the
  shape JSON round-tripped, and fails against another target (red: helper absent); a same-named method of another function is
  not the head (red: behavioural).
- M5: only the outermost successful helper records (nested `exact_quantized_moe_hc_expand` → `exact_quantized_selected_linear`
  was double-counted; red: behavioural). The fused-branch test now calls `glu.eval()` — `SwitchGLU`'s exact fused path is
  inference-only (`not self.training`), which the round-1 test never reached — at width 512, asserts the spy saw the fused helper
  return non-None, and asserts the exact `Counter`. It is GREEN on the red tree: the round-1 per-bank family fix holds on the
  fused branch.
- M7: test-only strengthening (green on the red tree): the prompt-end snapshot exists, has a probe and is neutral; `1 +
  sum(n_emit over cuts) == emitted tokens`.
- N1: NOT CHANGED — operator ruling C194 (verbatim below) keeps an explicit operator `--wall-limit-s` ("an explicit operator
  `--wall-limit-s` remains possible and must be finite and positive"); only the default cap was withdrawn, and no default cap is
  applied (`campaign_deadline(None)` is unbounded). Removing the option would contradict the ruling. Re-raise only if the code
  applies a cap the operator did not explicitly pass.
- N2: the test helper applies the sabotage inside `monkeypatch.context()`, undone before the telemetry restores its own
  wrappers. Test: an explicit `MonkeyPatch` + `undo()` after a sabotaged turn must leave the real `__call__`s (red: behavioural).
- N3: each routed invocation frame records its owner (the container argument before `x`) and the bank module names; the
  verdict requires exactly `{owner}.gate_proj / up_proj / down_proj`. Test: swapping the two layers' gate banks fails on
  ownership (with P413 fixed first, the old verdict PASSES the swap: red for the right reason).
- N4: test-only (green on the red tree): no dense `Linear` / `Embedding` / `SwitchLinear` in either served fixture; every
  quantized leaf affine 4 / 64 with bf16 scales and biases.

Declared new defects, found while fixing round 2 (dev only; neither reached a GPU minute — no v13 smoke has run):
- P412: the job reaches the worker as JSON, so the certified `experts` arrives as `[256, 8]` against the identity's tuple
  `(256, 8)` — `Ornith-1.0-35B-mlx-uniform-4bit` would refuse at every boot. Fixed (compared after the round trip); red test.
- P413: a BOUND drafter holds the target's embedding / head as attributes, so `KernelTelemetry`'s name map renamed those target
  modules `drafter._input_embed` / `drafter._lm_head_fn` ("unknown module" in the target manifest). The M3 fix binds at boot, so
  without this every v13 MTP-ON verdict would fail. Fixed (target names take precedence); red test.
- On `a2808acf`: fork suite ×2 identical (6669 passed / 17 skipped, same skip set), 8 audits `--upstream-ref 952d4f6b`
  (deletions `--strict`) all OK.

Review adversarially: (1) does each fix close its round-2 finding completely and fail closed; (2) did a fix introduce a new defect
or weaken an earlier guarantee — in particular, can binding at boot (M3) change served behaviour or mask a later bad bind, and can
the ownership check (N3) false-fail a correct served path (verifier `_switch_glu` vs `SwitchGLU.__call__`, the drafter's own
`SwitchGLU`); (3) do the red / green claims hold. Only findings that must be fixed before a GPU smoke of this harness.

Report each round-2 finding as CLOSED or OPEN (with why), then new findings R1 onward, each: severity, file:line, problem, failure
scenario, fix. End with exactly one line: `VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`. OUTPUT RULE: your FINAL message
must contain EVERY finding in full, then the VERDICT line.
