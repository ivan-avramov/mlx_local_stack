I have enough to compile the verification. Here is my report.

---

# P475 stage 1 build — VERIFY, round 2 of 3

I traced every adopted/adapted row of `dispositions.md` against `candidate-fix.diff` and `repair.interdiff`, and re-walked the declined rows for premise changes. Findings below.

## Adopted / adapted findings

**Sol P1 / TW F4 — instrument byte-identity pre-check — RESOLVED.**
`INSTRUMENT_FILES` (the contract's five), `instrument_shas`, `instrument_problems` are in place (`p475_kv.py` ~L329, L748–765); the pre-check calls them and adds to `pre` (L1153–1154); the receipt records `instrument` shas. Red-first tests cover a differing file (×5), a missing file on either side (×2), and the receipt sha record. The check compares the arm worktree to `cfg.repo` (the orchestrator checkout), which is what the contract literally says ("byte-identical to the orchestrator checkout's"). Production assumes the orchestrator checkout is at the base commit; if it has drifted the check fails closed — acceptable.

**Sol P2 — N16 keeps the scheme line — RESOLVED.**
`ARM_EDITS["N16"] = {"kv_bits": "0"}` (L337); `registry_diff_problems` refuses an N16 commit that drops `kv_quant_scheme`; the test `test_every_kv_arm_registry_passes_the_forks_real_kv_arm_gate` exercises the real `classify_kv_arm` for all five KV arms, and `test_the_old_n16_shape_is_what_the_fork_gate_refuses` confirms the dropped-scheme shape is what the gate rejects. The registry test's N16 branch was amended to `want["kv_bits"] = 0` only.

**Sol P3 — dossiers bound to the run; one usable dossier per slot — RESOLVED.**
`dossier_binding_problems` (L1569–1599) checks leg/model/base/arm-identity/gitlinks and entry==exit; `load_dossiers` (L1610–1654) adds cross-dossier arm-commit and gitlink agreement (against the run's recorded identity when `state.json` has one) and refuses two usable dossiers for one slot; `recorded_identity_problems` (L776–783) refuses an arm re-committed mid-run; `_attempt` records `arm_commits`/`gitlinks` into `state["identity"]` at the first non-NOT_STARTED leg (L1907–1909). Tests cover all seven tamper cases, another base without state, disagreeing commits, the recorded-identity assertion, an arm recommitted mid-run, and a second usable dossier.

**Sol P4 — peak memory and decode rate finite and > 0 — RESOLVED.**
`rung_problems` requires `_num(v) and v > 0` for `peak_memory_gb_cumulative` and `predicted_per_second` (`capacity_ladder.py` L39–43); `_metric_cells_missing` is a defensive matrix-level check (L1741–1745). Tests cover both keys × {None, 0, 0.0, −1.0, nan, inf, "12.5", True} (16 cases), an absent peak, and a leg whose backend omits peak memory → INVALID.

**Sol P5 / TW F3 — driver and router groups verified empty — RESOLVED.**
`Ops.group_alive` is in the protocol; `RealOps.group_alive` reads `ps -axo pid=,pgid=,stat=`, ignores zombies (`not parts[2].startswith("Z")`), and raises on `ps` failure (L2238–2247); `RealOps.signal_group` fires if the leader is alive OR the group is alive (L2232–2235); `_reap_driver` signals while any member lives (also after a normal leader exit), escalates TERM→KILL, and verifies the group empty, failing closed on unreadable state (L1048–1076); `_teardown` checks the router wrapper's group (L1342–1346). Tests cover a lingering driver child, SIGKILL survival, an empty group not signalled, unreadable state, a surviving router group member, the realops zombie/failure paths, and the protocol name.

**Sol P6 — every dossier file through `p426_harvest.Gate` — RESOLVED.**
`_gate` builds `Gate(scrub, secrets)` (L1399–1402); `_publish` calls `gate.check(rel, data, dest)` on the original bytes (L1404–1410); `default_scrub` sets `emails=operator_emails(cfg)` (L1386–1388); `operator_emails` reads `--operator-email` else `git config user.email`, refusing empty (L1360–1374); evidence logs are gated with `dest="evidence"` (L1463–1466), and foreign addresses in evidence go to a local review file, never published (L1495–1497). Tests cover a foreign e-mail in a ladder row, a reserved example allowed, the operator address in an evidence log, and a credential in the original bytes refused even when scrubbed away.

**Sol P7 / GLM F5 — block plan and deciding block persisted — RESOLVED.**
`state["plan"] = {blocks, deciding_block}` is saved before the first measured leg (L2038–2039, L1899–1901); a changed `--blocks` after any leg refuses rc 2 (L2024–2025); `blocks` is removed from `CAP_NAMES` (L1864); `_deciding_step` persists `state["deciding"] = {block, started, complete}` and never re-enters a completed deciding block (L2090–2105, guard `not dec["complete"]`); `matrix` reads the recorded plan (L1753–1754). Tests cover the persisted plan + changed-blocks refusal, no plan before any leg, legs-without-plan refusal, a completed deciding block not re-entered, and the matrix CLI reading the recorded plan.

**Sol P8 — exactly one of canonical / PARTIAL — RESOLVED.**
`matrix` writes one atomically then `unlink`s the other (L1814). Tests cover complete→partial (removes canonical) and partial→complete (removes partial).

**TW F1 — INVALID smoke leg terminal on resume — RESOLVED.**
`_run_smoke` raises `_Stop` on a standing INVALID smoke leg (L2118–2120). Tests cover an INVALID N16 smoke stopping on resume and an INVALID TQ4 smoke stopping on resume.

**TW F2 — `evidence-stage/<leg>` a destination, never overwritten — RESOLVED.**
`_destinations` includes `cfg.evidence_stage(leg)` (L929); harvest writes evidence through a temp dir + `os.rename` (L1483–1493); on replay, byte-identical existing evidence is accepted, differing content refuses (L1470–1476). Tests cover an existing evidence stage being a destination, a replay never overwriting differing evidence, and a replay accepting byte-identical evidence.

**TW F6 — unresolved instability exits nonzero, labelled — RESOLVED.**
`unresolved_flags` (L1729–1739) returns flagged cells no deciding block resolved; the matrix labels `UNRESOLVED` (L1775–1777) and per-row (L1797–1799); `run` exits nonzero when `unresolved` is non-empty (L2064). I reproduced the `unresolved_flags` expression shape in Python across empty/non-empty/resolved deciding sets — it behaves as a single generator `(A and B) for b in deciding` (the comprehension binds `b` for both clauses), and returns the correct results. Tests cover a zero-cap unresolved case (nonzero, labelled) and a resolved case (not labelled).

**GLM F1 — worker-env macOS assumption (D1) — RESOLVED (adapted, no code change to the check).**
`SMOKE_ARMS = ("N16", "TQ4")` (L322); every smoke receipt records `worker_env` (names + kv/tq values via `worker_env_record`, L1083–1087), `telemetry` (via `telemetry_identities`, L1089–1099), and `drafter_keys`. The test `test_the_worker_env_record_keeps_kv_values_for_the_d1_question` confirms a TQ4 smoke with `KV_BITS=4` in the worker env is INVALID (R2 fires) AND records `kv_tq={"KV_BITS":"4"}` for the operator — exactly the D1 evidence the disposition asked for. The R2 check itself is unchanged (declined-as-code part of the disposition).

**GLM F5 — deciding block re-entered on resume — RESOLVED.** Folded into Sol P7; `dec["complete"]` is set and the re-entry guard skips it. The `test_a_completed_deciding_block_is_not_re_entered` test asserts no spurious "deciding block" log and `len(ops.spawned) == 18` on resume.

**P651 — watcher `--capacity-rows` recorded and checked — RESOLVED.**
`watch_rows_problems` (L1037–1042) requires `--capacity-rows` exactly equals the leg's rows path; `run_leg` builds the argv once, stores it as `watcher_argv` in the receipt, runs the check before `start_watch`, and passes the same argv to the watcher (L1213–1216). Tests cover the matching path (no problem, argv recorded on-disk), a wrong/missing `--capacity-rows` (speed-invalid, ×2), and a wrong-rows watcher being replaced in a full run.

## Declined rows — premise unchanged by the repair

- **GLM F3 (telemetry identities, declined as code):** the repair did NOT relax the R21 checks; it added `telemetry_identities` recording on smoke legs (and all legs), so a live mismatch is caught at smoke and returns to the operator as a contract change — exactly the disposition. Premise unchanged; the decline stands.
- **GLM F4 (`busy()` zombie/unrelated):** `RealOps.busy` (L2160–2167) is unchanged — still no create_time/zombie filter. The new `group_alive` ignores zombies, but `busy()` does not, so a zombie in `busy()` still yields INVALID. That is the same fail-safe behaviour the disposition declined; premise unchanged.
- **GLM F6 (worker log read twice):** the log is still read in full before and after load (`_read_optional(ops, log_path)` ×2). Performance-only, unchanged.
- **TW F5 (NOT_STARTED cap run-wide):** `state["used"]["not_started"]` is still run-wide. Unchanged.

## Anything else the diff breaks or leaves failing

**H1 — `default_scrub`'s operator-email fallback can refuse a clean live smoke (minor, hazard).**
- Location: `p475_kv.py` `operator_emails` (L1360–1374), `default_scrub` (L1376–1388).
- Evidence: confirmed. When `--operator-email` is not given, `operator_emails` reads `git config user.email` of the main checkout and refuses (raises `P475Error`) if it is unset. `_scrub_for` calls this lazily on the first harvest, so a smoke leg on a box without `user.email` configured would raise at harvest time and the leg's `_harvest` becomes `"harvest failed: … the operator email set is empty"`, making the smoke exit nonzero even though the leg itself was VALID.
- Failure scenario: a fresh box provisioned by `scripts/bootstrap_machine.sh` without `git config user.email` runs `run --smoke`; both smoke legs are VALID but the run exits 1 at the first harvest, blocking the live acceptance path.
- Proposed change: have `bootstrap_machine.sh --box <label>` set a placeholder `user.email` (it already generates `config.sh`), or print an explicit preflight hint in `run --smoke` when `operator_emails` would be empty. The fix report already flags this dependency; raising it here so the operator sees it before the live smoke.

**H2 — `instrument_problems` compares to `cfg.repo`, not `cfg.base` (minor, scope note).**
- Location: `p475_kv.py` `instrument_problems` (L755–765).
- Evidence: confirmed. The check hashes `cfg.repo/benchmark/<rel>` against `cfg.worktree(arm)/benchmark/<rel>`. The arm worktree is prepared from `cfg.base`, so the check is correct only when the orchestrator checkout (`cfg.repo`) is at `cfg.base`. The contract explicitly says "byte-identical to the orchestrator checkout's", so this matches the contract; it is a production assumption, not a defect. Noting it only so the operator confirms `cfg.repo` HEAD == `cfg.base` before the first leg (a drift fails closed — every leg NOT_STARTED).

No further defects found. The four frozen tests the fix report judges unsupported by v1.2 (old N16 rule, one-leg smoke, two harvest tests whose PII injection now reaches the TQ4 smoke) are correctly characterised — they fail because they encode pre-v1.2 rules, not because the fix is wrong; the d3 test-writer delivery adapting them to v1.2 plus failing-case tests per fix is still in progress per the brief and is outside this round's scope.

## Summary

All twelve adopted/adapted findings (Sol P1–P8, TW F1/F2/F3/F4/F6, GLM F1/F5) plus P651 are **resolved**, each with red-first tests traced in `test_p475_impl_fixes.py` and the touched suites. The four declined rows (GLM F3/F4/F6, TW F5) had their premises **unchanged** by the repair; the declines stand. Two minor hazards (H1 operator-email fallback, H2 `cfg.repo`-vs-`cfg.base` assumption) are operator-side preconditions, not defects in the material, and the fix report already surfaces H1. The material meets its purpose for the round-2 verify.
