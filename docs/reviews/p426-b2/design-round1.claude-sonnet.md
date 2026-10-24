I've read the spec and spot-checked the chain runner, hooks and config code. I'm writing up the findings now.

**Findings (B2 spec v1)**

**1. Blocker. §3 / §2 / §4. The DNF-and-continue path has no host in the chain.**
- `run_config.py:31` allows only `abort_restart` and `incident_retry`. `run_tg1_chain.py:91` uses `abort_restart`. That policy archives the load and restarts it from leg 0, or aborts.
- `incident_retry` ties DNF rows to the retry slot.
- §2 refuses both policies in P426 mode, and §3 says to "reuse chain_incident / transport_dnf without the retry".
- A helper following this literally has no policy under which a transport failure leaves the load running. The hook vocabulary is only `accept | rerun_same_slot | block` (`chain_hooks.py:15`), and `pre_spawn_incident` applies only before the spawn.
- Failure scenario: item 7 hits a connection error. Either the chain archives and restarts the load, so the "same loaded instance" is lost and the loaded-instance pilot and reload guarantees break. Or the helper invents a third policy that touches `chain_core` lines 526, 1353, 1774, 1906 and 2000, which older chains rely on. No ruling covers that.
- Change: name a third policy (e.g. `dnf_continue`). Specify the probe relaunch for the remaining items, the cache reset, the persisted progress and DNF records, and the resume behaviour. Pin by test that `abort_restart` and `incident_retry` configs are byte-identical.

**2. Blocker. §3. A DNF is "never graded, never a strict fail", which biases the ON-vs-OFF comparison.**
- AGENTS ranks by `acc_strict@budget` "DNF included".
- If MTP causes a worker error or a dropped stream, that item becomes a DNF. It is excluded from ON's accuracy and moved to a make-up leg outside the pairs.
- Failure scenario: ON crashes on 2 of 43 items. The paired accuracy is unchanged and the ship call is made on a flattering number.
- Change:
  - Report DNFs in the denominator, per the AGENTS rule.
  - Classify `server_error` and worker-side errors that occur only in ON as an attention flag that blocks "ship".
  - Have B8 consume DNF slots explicitly, because the pairs are no longer item-complete.
  - Reconcile this with the §2 exit check "rows == planned items", which a DNF breaks.

**3. Major. §3. The boundary between a DNF and an in-probe strict fail is undefined.**
- A DNF is a "client timeout" with the worker healthy.
- A strict fail includes `client_inactivity` and exec timeout.
- `TRANSPORT_CAUSES` (`arm_opencode.py:69`) contains `timeout`, which collides with that.
- A client timeout while the worker is still generating (BUSY) fails the "nothing in flight" test. The spec says nothing in that case, and it also says "never kill".
- Change: give an explicit cause-to-class table. Say what happens when a request is still in flight (wait to drain, else systemic).

**4. Major. §6. The reconciliation hook has timing and attribution holes.**
- It runs at the `done` barrier against an append log. The server writes "Request completed" after the stream closes, so the client can finish first. That would stop a healthy run on a false mismatch.
- Requests carrying a different `session=` (title, compaction or subagent requests) would be unattributed. Evidence is only 17/17 on one rehearsal item.
- "rounds > 0" is applied to every request. Short or tool-call-only completions, or prefill-only ones, may legitimately have zero rounds. As a systemic stop this kills a good ON leg.
- Change:
  - Add a settle-and-poll rule with a bounded wait.
  - Specify how requests with unknown sessions are handled.
  - Apply "rounds > 0" per item (at least one request, or the sum), not per request.
  - Run the reconciliation on at least the pilot items and on a multi-item sample before the freeze.

**5. Major. §4 / §9. Arm identity only covers the registry diff and the predictor flags.**
- The worker tripwire checks only the predictor flags.
- Nothing asserts that the two arms' router and worker argv and environment are otherwise identical. That covers `MLX_VLM_CACHE_SESSION_MAX=1`, `APC_ENABLED` absent, the venv or interpreter, the submodule checkouts being clean at the gitlink, and the cwd.
- `--campaign-core` and the commit shas differ per arm. §9 doesn't say these are excluded from the lifecycle hash and pool checks.
- Failure scenario: the ON worktree resolves a different installed mlx-vlm and nothing detects it.
- Change: add a leg-time diff of the worker argv/env/cwd, and a check that each submodule is clean, resolved to the same path and sha. Allow only the three predictor flags to differ. Record the result in the receipt.

**6. Major. §9. Timeouts could differ between arms.**
- "Each leg's timeout is derived from the pilot legs' walls". If each arm derives it from its own pilot, the arms get different timeouts. That makes the arms differ in more than the MTP state, and it changes which items DNF.
- The pilot itself has no source for its timeout.
- Change: derive one common value (e.g. the max over both pilots with the tail allowance). Freeze it into the record before the s1 legs. Record a bootstrap timeout for the pilots. Keep client timeouts and per-request limits identical in both arms.

**7. Major. §9 / P468. Data boundary: what lands on public `main`.**
- The harvest puts these on `main`: per-item code diffs, server-log slices, stdout, `RUNLOG.md` and receipts. AGENTS bans absolute home paths, hostnames and usernames.
- "Scrubbed" is stated for P437 generally, but the main-versus-evidence split is not tied to the scrub gate.
- "Pushed separately with approval" is stated for `evidence` only. Pushing `main` also needs in-turn approval.
- Change: run the scrub with its manifest on every file before it lands on `main`, and fail the harvest on any hit. State that no push occurs without approval. Say that log slices contain no prompt text.

**8. Major. §9. INVALID, `NOT_STARTED` and aborted legs are not required to be harvested.**
- Resume skips "only VALID + harvested", but the harvest rule is silent for invalid legs. Partial data, including a systemic-stop leg, is a citable byte and the evidence for why a leg stopped.
- Change: harvest every leg state, labelled. Say that nothing is removed from a worktree or out-root until harvested.

**9. Major. §8. The leg only "tries" the gate lock.**
- A pre-check that tries `RUNNING` and then releases protects nothing during the leg. The sequencer's `SEQUENCER.lock` covers sequenced runs only, and a manual rerun is unprotected.
- A child that inherits the lock file descriptor (router, worker) keeps the lock after its holder dies.
- Change: the process that runs the leg holds the lock for the whole leg. Open lock files close-on-exec.

**10. Minor. §7. There is no rule for the watcher dying.**
- AGENTS requires a daemon for every run. §7 does not say that `bench_watch` dying mid-leg makes the leg speed-invalid or systemic.
- It reads `chain.json`, which the chain writes, so it is not independent for progress.
- Change: define watcher death as speed-invalid, and have it log a heartbeat.

**11. Minor. §1 / §5. The pilot-versus-chain relationship is unclear.**
- The existing runner's `chain` runs "the cell minus the pilot's validated slots", and a pilot and the chain after it share one lifecycle hash. The P426 pilot is a separate invocation and load.
- §1 doesn't say whether leg 3 re-runs the pilot's 5 items, or how they are counted.
- Change: state that `chain s1` runs the full 43 items. State that the pilot rows are excluded from pairs and that reload reuses those same 5 items.

**12. Minor. §10 / §4. The "old config byte-identical" test is under-specified.**
- Requiring `--models` and demoting `--predictor` to an assertion changes the M63 CLI and its reproducibility. The spec says it is ruled by C221.
- Change: test the frozen M59/M61/M62/M64/inject paths explicitly. Say that `--p426` gates the new item order, so old-chain schedules do not change.

**Scope requests (no severity)**
- Add a pair-verifier input contract, so that B8 and B6 consume what B2 persists. Today it is only "persists the per-item slice".
- A "model accepted by the pre-launch census" receipt that captures `ps` at launch. Today it is verification only.

**Possible simplification:** §10's dry leg per arm and the pilot gate overlap. Fold the "smoke-scale dry leg per arm" into the pilot gate, since both exercise the full topology.
