# Handoff — 2026-09-08 21:36 (M34a full confirmation running)


## CURRENT — supersedes all historical process/sizing notes below
- Operator: "proceed with next steps. keep running things from the queue on the machine". C56 resolved by sizing M34a at 100 fresh cases per dataset: MBPPPlus k=3, HumanEvalPlus k=1. Prioritize distinct items on the expensive axis. Pilot-mean generation estimate 14.1 h total; planning allowance 20–24 h with substantial tail uncertainty.
- ACTIVE `$STACK_WORKDIR/queue/queue_m34a_full.py`, PID in `queue/m34a_full.pid` (96373), started 21:35:50. Logs: `queue/m34a_full.log`, errors `queue/m34a_full_launcher.log`. Native MBPPPlus driver 96403, watchdog 96404, router 96395, worker 96503. Verify identities before acting.
- Executable sequence: MBPPPlus native 300 responses → expanded 300 → paired analysis → HumanEvalPlus native 100 → expanded 100 → paired analysis → `M34a FULL DONE`. Model `Ornith-1.0-35B-mlx-uniform-4bit`, tunes `m34afnat`/`m34afexp`, same deployed t0.4 and budgets, draft-OFF; expansion `27-39:20:0.8:0.5`. Grade each arm before advancing; abort on generation/grade errors.
- IDs: `queue/m34a_full_ids.json`, seeded random sample 3402, exclude both original 50-item experiment and five pilot items on each dataset. Dry-run verified four stages, matched IDs, 300/300/100/100 counts, and grade/compare ordering.
- Fresh served overlays `queue/bench_overlay_q4.yaml` and `queue/bench_overlay_q4_exp.yaml` derive from current HEAD + local checkpoint paths + draft-OFF; semantic pair differs only in target `moe_expand`. No registry worktree edits. Router SESSION_MAX=2, APC absent; verify first manifest and worker flags. Never modify these overlays or runner while active.
- Each arm has the existing 300-second `bench_watch.py` assessment daemon, with correct sample totals. This is log-based monitoring, NOT autonomous agent wake-up. macOS scheduler/notifications remain disabled and unregistered at operator request. Do not reinstall them.
- M34b predictor interaction and M34c bounded transfer pilot remain authorized AFTER M34a, but are not executable stages in this runner. Prepare their continuation before these four arms finish. Do not describe them as already launched.
- Owed while box runs: land initial M34 results and M34a pilot rows; M35 eight-point instrument audit + final data/results closeout; C51 medium predictor certification/carriers (probe passed 1.644x). Preserve seven local registry path overrides; never push without in-turn approval.

## Historical pilot completion — 21:17
- `Ornith-1.0-35B-mlx-uniform-4bit` completed all four M34a pilots and grading. HumanEvalPlus expanded advanced 8→15/15 since the prior assessment: 13 converged, two `degenerate_repetition`, zero errors; mean/max 180.1/1085.3 seconds, token median/max 3382/82070. Ordinary/strict accuracy 1.0/0.8667 at budget 81920. Native: 1.0/0.8, convergence 12/15, mean/max 260.0/1052.0 seconds. Each pilot has five cases with three samples; these scores do not establish a quality difference.
- MBPPPlus native/expanded both have 15 responses, all converged, zero errors, ordinary/strict accuracy 0.6/0.6; mean/max seconds 11.1/22.1 and 10.9/19.9 respectively.
- `queue/followups.log` records generation and grading rc=0, then `M34a PILOTS DONE` at 21:16:35. Host process identities verify runner, driver and watchdog exited; router 93157 and idle worker 93265 remain as designed. No recovery required or performed. No serving parameters changed.
- Generation ETA is zero. Full-arm sample counts and runtime budget require C56 decision; no executable continuation remains. Mean-based paired cost for 100 cases × 3 samples per arm: MBPPPlus approximately 1.83 hours, HumanEvalPlus 36.67 hours, before startup/grading and additional tail allowance. These are sizing lower bounds, not approved runs. M34b/M34c remain backlog entries.

## Agent supervision — macOS scheduler removed by operator request
- CURRENT (2026-09-08): operator requested Claude-style native self-supervision without macOS scripts. Disabled `enabled` and `notifications`, unloaded `local.mlx-stack.codex-review`, and removed its LaunchAgents symlink after verifying no review was active. Files/reports remain for reference. NO recurring background agent review is now active. Native same-chat scheduling creation is not exposed in this session; do not claim restart-persistent supervision until configured and tested. Pilots were already complete; no benchmark was interrupted. Historical installation evidence follows.
- Notification change (2026-09-08): operator reported hung AppleScript apps. Host process and application inventories found no running `osascript`, applet or Automator process; scheduler had completed 14 runs with exit 0. Set local `queue/codex_supervision/config.json` `notifications:false`; recurring Codex reviews remain enabled. Do not re-enable notifications without operator approval.
- Operator approved P96: actual Codex reviews every five minutes, routine repair/resumption of approved work, and persistence across restarts. Read `docs/campaign-supervision.md` for authority and boundaries. No new experiment parameters, promotions or pushes are authorized by this approval.
- `scripts/campaign_review.py` is run by the macOS user LaunchAgent `local.mlx-stack.codex-review`: RunAtLoad + StartInterval=300. Registration in the user's LaunchAgents directory points to `$STACK_WORKDIR/queue/codex_supervision/local.mlx-stack.codex-review.plist`. Runs independently of the desktop app; requires an awake, logged-in machine and working Codex authentication/network.
- Persistent reviewer thread: `01a08412-ba19-7772-a3a0-2c23833c8b7f`. Local `config.json`, `state.json`, `latest.md`, `latest.json`, `scheduler.log` and `runs/<id>/{events.jsonl,stderr.log,assessment.json}` live in `queue/codex_supervision/`. Read the latest assessment before intervening. Pause via `enabled:false`, then wait for the active review to finish before concurrent repairs.
- Verified actual agent repair of an isolated broken worker (`selftest/agent_ack.json`); eight supervisor tests pass including killed-scheduler/orphan exclusion and expiry. Actual launchd review completed 19:55:59; unloaded/reloaded the idle job and the SAME reviewer session completed another review 19:59:52. Ordinary timer fired 20:04:52 and completed review 20:05:45. Cadence measured: 300 seconds after previous review completion, roughly six minutes between assessments. Physical reboot was not performed during the benchmark. Notification command SELFTEST returned 0; visual delivery was not independently verified.
- Latest verified benchmark state (19:59): `Ornith-1.0-35B-mlx-uniform-4bit` M34a MBPPPlus native/expanded pilots both complete and graded; HumanEvalPlus native 10/15, expanded follows. Current native driver 90219, router 90211, worker 90319, watchdog 90220; runner 89640. Long response under observation, zero errors, one degenerate repetition among ten completed rows. No intervention warranted; verify fresh counts from the next assessment.
- Next C-item ID: C57. No live runner or serving overlay was changed by supervision setup.
- Latest automatic assessment (20:05): count still 10/15; request age approximately 610 seconds vs observed maximum 1052 seconds and timeout 7800 seconds. Reviewer checked logs/process identity/provenance and found no recovery justified. Read `latest.md` for newer evidence.

Next-session prompt: Read this handoff first, then `docs/campaign-supervision.md` and the latest local reviewer assessment. Verify the login job and reviewer heartbeat before taking action; pause and wait before competing repairs. Continue authorized PLAN work and owed result/certification closeout. Preserve running work and all seven registry path overrides. Never push without approval in that turn.

## CURRENT LIVE CHECKPOINT — supersedes historical process/queue notes below
- C51 medium predictor check for `Qwen3.8-27B-mlx-uniform-4bit` completed 19:11:10. All six responses converged; median decode OFF 25.825 vs ON 42.452 tok/s, ratio 1.644x (passes 1.3x), acceptance 7387/8712. Evidence: `queue/c51_medium/{run.log,progress.jsonl,result.json}`. Production certification/carrier update remains owed. Gate is a speed screen, not new quality evidence.
- Fresh `queue/bench_overlay_q3.yaml` derives from HEAD with four local checkpoint paths and draft-OFF; the three local drafter paths are stripped from this OFF overlay. `queue/c51_medium/overlay.yaml` changes only the target effort to medium. Registry-of-record worktree untouched.
- Automatic successor `$STACK_WORKDIR/queue/queue_followups.py`, PID in `queue/followups.pid` (89640), log `queue/followups.log`, launcher errors `queue/followups_launcher.log`: passed its C51 wait and runs M34a held-out pilots on `Ornith-1.0-35B-mlx-uniform-4bit`. MBPPPlus first, then HumanEvalPlus; native and expanded each, 5 seeded random cases x 3 samples. IDs in `queue/m34a_heldout_pilots.json`, seed 3401; all original 50-case sets excluded. Distinct `overlay_q3_*` file preserves old overlays. No production certification changes are automated; review C51 separately while pilots run.
- Recovery 19:15:45: successor had failed before model launch because its overlay insertion assumed four-space YAML indentation. Reproduced failure, inherited indentation from the matched key, verified valid YAML with exactly one semantic change (`moe_expand` on the target). Relaunched detached with `start_new_session=True`. Native MBPPPlus pilot started 19:15:48; worker 89758 loaded, driver 89658, watchdog 89659 (15 samples, 300 s). Router 89649: q3, SESSION_MAX=2, APC absent; worker draft-OFF and first manifest hash verified. Activity Monitor process name is `python3`. Do not edit the running successor.
- Full M34a sizing awaits these pilots. M34b/M34c remain authorized backlog entries, not executable stages. Pilot runner ends with `M34a PILOTS DONE`, leaving its router up; prepare the next continuation before then.
- Earlier queue and after_queue finished normally. Known-positive MTP control: 1.525x, acceptance 68.6%. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` re-probe: 0.613x, 0/47980 accepted; keep draft-OFF. Both earlier probes used the historical effort setting; do not label the mixed result a medium-effort measurement.
- M34 initial six arms complete; M35 execution complete (19/22, three stalls). Their final data/results landing and M35 instrument audit remain owed. No live serving files or runners may be edited. Older log-only daemons do not wake a conversation; C55 above now supplies independent recurring agent reviews.


Single box (M5 Max 64 GB). **The box is BUSY and self-driving** (operator directive 2026-09-06: never idle; follow the queue). Router UP on
`$STACK_WORKDIR/queue/bench_overlay_q2.yaml` (pid 82020, on `queue/bench_overlay_q2.yaml` since 14:09), SESSION_MAX=2,
APC absent. Serving path = `src/mlx-vlm` 420c01e1 / `src/mlx-serve` 0ccc6842 (bumped `a08f933`); every row since carries it; older rows do not `compare`
across (C47). Working tree: NINE intentional `main_models.yaml` local-path overrides (7 + the two mixed-checkpoint effort clones) — NEVER commit;
committed registry edits go via the HEAD blob (`git show HEAD:main_models.yaml` → edit → `git hash-object -w` → `git update-index --cacheinfo`; then mirror
the edit into the worktree — READ the worktree file BEFORE opening it for write). origin/main = `4acefd2` (operator pushed 2026-09-07 14:10); UNPUSHED since: `9414861` … `25257b6` + this handoff (12 commits). Push only on in-turn approval. **Worktree overrides are now SEVEN** (the `-MED` and both `-LOW` bench clones of the two `Qwen3.8-27B` checkpoints were retired from the registry; `Qwen3.8-27B-mlx-uniform-4bit-MED` remains until the base moves to medium). <!-- allow-shorthand -->

## Resumed 2026-09-07 — C52 resolved (supersedes C52 blockers below)
- Operator approved C52(a); hook fix committed `76272a1`, 55 tests pass after failing regression cases.
- The two completed S2c result directories are landed with this checkpoint (164 rows each; SUMMARY/SCORE and paired evidence verified). No S3 rows landed.
- Runner 7556, waiter 7578 and router 82020 verified alive; detached monitor pid in `queue/codex_resume_monitor.pid`, log `queue/codex_resume_monitor.log`; event-filter and pid-loop SELFTEST passed.
- S3 watchdog total is 50 but counts sample rows: this arm expects 150 (50 x 3). Its zero-remaining ETA is invalid; preserve the running runner. C53 approved and fixed in the inactive next-runner copy; see below.
- Before any new arm, use regenerated q3 from current HEAD as required by checklist item 2; older q2 restart advice below is superseded.

## C53 implemented 2026-09-07 (operator P18)
- Inactive `$STACK_WORKDIR/queue/queue_chain3.py` changes only watchdog `--total` to `limit * samples`; NOT launched. Refresh queue stages and overlay from current HEAD before using this copy.
- Regression: `$STACK_WORKDIR/queue/test_queue_watch_total.py`; run with the bench interpreter. Extracts only `run_generate` via AST, mocks subprocesses and file writes. 50x3 and 5x3 failed first; all three cases (including 164x1) now pass.
- Live runner SHA256 `1328513360513df09b95bd0e819552f16c063b0e96cc7979a0a93b79526df7cd`; corrected copy SHA256 `494b721826ea7cbae3e8c6ed11b18a672fd786312dc3df4b754ffcbb2ed61213`. Live runner and waiter verified alive after the fix.

## Queue update 2026-09-08 — M34 follow-ups authorized
- Operator superseded M34's original close rule. Initial OFAT is complete; native production routing remains unchanged.
- PLAN M34a (held-out coding, MBPPPlus first) and M34b (production MTP interaction with matched OFF controls) are authorized, after current M35, after-queue controls and owed C51 certification. Sample counts/runtime require pilot sizing before launch.
- PLAN M34c is an approved bounded expert-expansion pilot for `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (operator P70, 2026-09-08), queued after M34a/M34b. Five seeded random cases each on MBPPPlus and Math500, both native and expanded routing, predictor OFF; review before any full campaign. Map its actual MoE layers before selecting the expansion range.
- These are PLAN queue entries, not appended executable stages. Current runner/waiter are unchanged; after_queue still leaves the router DOWN. A successor must use fresh q3 overlays.

## M35 decision 2026-09-08 (operator agrees with P80)
- Planned dsh executions complete: `Qwen3.8-27B-mlx-uniform-4bit` 19/22, three stalls, 2.15 h; opencode reference sessions 20/22 and 18/22 in 1.69 h and 1.59 h.
- Keep opencode primary; no further dsh expansion queued. Retain the adapter as an alternative.
- Outstanding closeout: full eight-point smoke audit and final results/data commit. Do not describe the instrument as fully validated before that audit.

## Live processes (verify by pid, never infer)
- `queue/queue_chain2.py` pid in `queue/queue.pid` (7556), log `queue/queue.log`, launched 12:55. The orphaned S2b hep driver exited 14:08; router moved to
  `bench_overlay_q2.yaml` (pid 82020) 14:09; **S2b DONE 19:41 and landed** (`9414861`, `ccf45e0`, `bbda2c1`); **S2c DONE 21:52, docs/registry landed `25257b6`, ROWS UNTRACKED (C52)**. NOW IN S3 M34 (started 21:52; hep native pilot 14/15 converged, 1 degenerate loop, sized 4.6 h for n=50 k=3 lower bound). S2c was: (hep n=164 on `Qwen3.8-27B-mlx-uniform-4bit-LOW` and `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-LOW`, paired vs xhigh `m32b` + medium `m24`) → S3 M34 (`Ornith-1.0-35B-mlx-uniform-4bit` `m34nat` vs `m34exp`
  moe_expand 27-39:20:0.8:0.5 on hep/mbpp n=50 k=3 + math500 n=100; overlays `queue/overlay_*.yaml`) → S4 M35 (dsh smoke → pilot → 22 python on
  `Qwen3.8-27B-mlx-uniform-4bit`, tune `m35`) → `=== QUEUE DONE ===`. Stages continue past a failure; router restored to the draft-OFF overlay between stages.
- `queue/after_queue.py` pid in `queue/after_queue.pid` (7578): when the runner exits, stops the router and runs the KNOWN-POSITIVE MTP control
  (`Qwen3.8-27B-mlx-uniform-4bit` + certified drafter, expect ≥1.3×/acceptance ~0.67) then re-probes the mixed sidecar; leaves the router DOWN (`queue/after_queue.log`).
- Paired reads across axes `compare` refuses (draft, effort, moe_expand): `queue/paired_ofat.py` (validated vs M27 + M21b). bench opencode carrier is
  swapped into `~/.config/opencode/opencode.json` only during agentic legs and restored after (guarded).

## Resume checklist (new session)
1. `kill -0 $(cat $STACK_WORKDIR/queue/queue.pid)`; `tail -20 $STACK_WORKDIR/queue/queue.log`; re-arm a Monitor on `queue/queue.log`
   (`tail -F | /usr/bin/grep --line-buffered -E 'FATAL|WARN|ALARM|===|C35|PILOT SIZING|SUMMARY|PAIRED|SCORE|ROWS|EFFORT READBACK|DSH SMOKE|M35 READ|M24 READ|END |SKIP|TIMEOUT|Traceback'`)
   with a pid-liveness loop + SELFTEST line. Also confirm `after_queue.py` is alive. Monitors do not survive a session.
2. Land each finished stage from `queue.log` + `queue/paired_*.json`: campaign-results dated entry, PLAN row, rows commit (`data(bench)+docs`).
   Untracked rows now: `Qwen3.8-27B-mlx-uniform-4bit-LOW/humanevalplus.m24.*` and `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-LOW/humanevalplus.m24.*` (S2c, COMPLETE and graded; blocked on **C52** — commit them as `data(bench)` the moment the hook ruling lands), and `Ornith-1.0-35B-mlx-uniform-4bit/humanevalplus.m34nat.*` (S3, in flight — do NOT commit until the S3 hep SUMMARY/PAIRED lines).
   **Every overlay in `queue/` (q, q2, overlay_*) predates `85db045` — they are fingerprint inputs and stay valid for the RUNNING arms only. Before any NEW arm, regenerate a `bench_overlay_q3.yaml` from HEAD (`git show HEAD:main_models.yaml` + the local-path overrides + draft-OFF edits, same recipe as q2) and restart the router on it.**
3. Read the M35 smoke log (`queue/S4_dsh_smoke.log`) against the 8-point checklist in PLAN M35 before trusting the dsh leg.
4. When `=== AFTER-QUEUE DONE ===`: if the control shows acceptance ~0.67 the mixed sidecar's zero is real (head incompatible → ships draft-OFF, record);
   if the control ALSO shows zero acceptance, MTP is broken on the bumped serving path → C-item, urgent (the B 1st/2nd/3rd triples ship mtp).
   Restart the router on `queue/bench_overlay_q2.yaml` before any new arm.

## S2c CLOSED 2026-09-07 21:52 (campaign-results S2c entry, `25257b6`)
The effort curve's knee is at MEDIUM: on `Qwen3.8-27B-mlx-uniform-4bit` the lowest setting LOSES to medium (hep n=164 strict −2.4pp CI [−4.9, −0.6], 0:4 — the first significant effort delta) for 0.83× tokens;
on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` equivalent (−1.8pp CI [−4.9, +1.2], 2:5) for 0.87×. Closed as an operating point (C31 stands as measured). Both effort-suffixed bench clones retired. M24 axis COMPLETE.

## RULED + SHIPPED 2026-09-07 20:00 — C50 + C51 (operator P10/P11): `85db045` registry + all carriers, `f689608` docs
B menu: 1st `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, 2nd `Ornith-1.0-35B-mlx-uniform-4bit`, **3rd `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @ t0.5 + `reasoning_effort: medium`, DRAFT-OFF, role main**,
4th `Qwen3.8-27B-mlx-uniform-4bit` (certified xhigh + mtp triple ships UNTIL its predictor is re-probed at medium; C51 ruled medium). `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-MED` is
retired (rows stay). **OWED, in order:** (1) after `=== AFTER-QUEUE DONE ===` validates the probe instrument, re-probe the `Qwen3.8-27B-mlx-uniform-4bit` MTP predictor at
medium (~30 min; acceptance was 0.674 at xhigh; bar ≥1.3×) → second complete commit: base `reasoning_effort: medium` + `# CERTIFIED` note, retire
`Qwen3.8-27B-mlx-uniform-4bit-MED`, all carriers; if the re-probe FAILS the bar, C-item (medium draft-OFF vs xhigh + mtp is the operator's call). (2) go leg at medium on both
checkpoints (not a gate). (3) `configgen` has NO `reasoning_effort` emitter — carriers rely on the registry default (FU-2); an emitter is a small feature if the operator wants the field explicit in `opencode.json`.

## Landed 2026-09-07 — S2b (campaign-results 2026-09-07 S2b entry, PLAN M24 row)
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-MED` hep n=164 strict 95.1, 0 loops, 1.35 h: vs own xhigh (`m32b` 93.9) +1.2pp CI [−1.8, +4.9] EQUIVALENT, tokens 0.42×;
vs `Qwen3.8-27B-mlx-uniform-4bit-MED` (93.9) +1.2pp CI [−1.2, +3.7] EQUIVALENT, tokens 0.79× CI [0.65, 0.94], wall 1.35 h vs 1.27 h. **At medium-vs-medium the
mixed checkpoint's hep wall edge is GONE** (slower decode at 4.98 bits eats the token saving) → C50's usability case now rests on the agentic legs; S2b's
opencode leg decided it: **22/22, 0 stall-kills** (vs base-medium 19/22 with 3, discordant 3:0 on its stall items, p=.25); mbpp k=3 medium 80.0 vs own xhigh 81.3 / base-medium 80.7 (both inconclusive), tokens 0.32× / 0.98×;
pooled n=214 EQUIVALENT on both cells (+0.6pp / +0.8pp). Extra paired JSON: `queue/paired_S2b_mxmed_vs_u4med_{hep,mbpp}.json` (run `paired_ofat.py` from `benchmark/` with `PYTHONPATH=.`; pooled read = `load_arm` + `stats.paired_delta(strata=bench)`).
**Hook fix `c03f610`:** `bench.modelnames` now exempts `*_samples_eval_results.json` (EvalPlus grader output embeds model code; a variable named after an effort fragment blocked a data commit). The commit-msg hook treats the bare effort words as shorthands too — write around them.

## Closed this session (campaign-results 2026-09-06 ×2, 2026-09-07 ×2; lab-notebook 2026-09-06/07)
- **M33** math500 n=100: three-way tie (`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 89 / `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 88 / `Ornith-1.0-35B-mlx-uniform-4bit` 86 strict), July basis superseded → **C48 RULED: C 1st `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, 2nd `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (provisional)**.
- **M32 + M32b** `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5: python 21/22, go 20/22, hep n=164 EQUIVALENT to the B 3rd choice at 0.26× tokens, 0 loops; MTP sidecar probe 0.65× with ZERO
  acceptance (instrument control queued) → **C50 OPEN** (B-menu slot; rec: 3rd choice, base to 4th).
- **M24** `Qwen3.8-27B-mlx-uniform-4bit` medium (registry-entry route `Qwen3.8-27B-mlx-uniform-4bit-MED`, operator P23): EQUIVALENT to xhigh (pooled n=214 strict +1.1pp CI [−1.7, +4.0]) at
  0.13× tokens, 0 loops, opencode 19/22 (3 stalls, on the bound) → rule fired → **C51 OPEN** (adopt medium as the 3rd choice's operating point;
  rec: yes after a predictor re-probe at medium). **Rule C50 and C51 TOGETHER after S2b** (if the base moves to medium its runaway tax vanishes,
  which narrows the usability case for promoting the mixed checkpoint above it; S2b gives the medium-vs-medium cell).
- Registry: medium- and low-effort entries for both checkpoints (role candidate, bench carriers only). No pick changed. <!-- allow-shorthand -->
- Submodules bumped to the M34 forks (`a08f933`); `queue/paired_ofat.py` built; the model-name hook now treats the bare effort word as a shorthand (registry-name
  component) — mark such prose `allow-shorthand`.

## THE QUEUE AFTER THE RUNNER (operator)
1. ~~C50 + C51 rulings~~ DONE `85db045`; remaining: the base's predictor re-probe at medium → second commit (see RULED section).
2. `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` temperature ladder (C 1st, t1.0 never laddered) — proposal + pilot.
3. M17 / D11 / M18 read; C axes at medium (math500/ifeval) if C51 adopts medium.

## Standing rules that bit this session
- A chain's "another driver is live" pgrep must match PYTHON drivers only — a Monitor shell whose command line quotes the chain's name is not a driver.
- An exit handler that restores/removes a third-party config must act ONLY if this run installed it (`_installed` guard).
- `~/.config/opencode/opencode.json` is the file opencode reads; brew upgrades re-initialise that directory. Bench legs swap the carrier in and restore.
- A bench overlay is a FINGERPRINT INPUT (the `deployed` profile reads `MLX_SERVE_CONFIG`): regenerate overlays from HEAD after every registry edit.
- `open(f,'w').write(edit(open(f).read()))` TRUNCATES BEFORE READING — read first, write second.
- Validate an instrument against a known positive before trusting a zero (the MTP sidecar's 0/48k acceptance).
- A running python runner cannot be edited: hand over by stopping the runner WITHOUT killing its in-flight driver, then a successor that waits on the
  driver's pid and resumes via the arm() skip/resume logic (done 13:15 for the low-effort legs).
- Killing a waiter that watches a runner pid BEFORE stopping the runner — otherwise it fires its post-queue actions mid-arm.

## M21b CLOSED 2026-09-03 (campaign-results entry; PLAN row DONE)
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 vs `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` @t0.6-r2, k=3 on
hep (`c4216b9`) and mbpp (`e7810e8`): strict EQUIVALENT pooled n=100 (+0.7pp CI [−2.7, +4.3]); tokens-per-task ratio
0.66 / 0.64 per bench, pooled **0.650 CI [0.455, 0.880]**; P28 met on both benches (mbpp on all three conditions).
Operator ruled CARRY: uploaded `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (public, 15 files, sha-verified,
card with the paired results), registry entry @t0.5 `# CERTIFIED M21b 2026-09-03`, candidate role, draft-OFF (triple
rule applies only on promotion; the artifact carries an MTP head sidecar, untested). Bench carriers regenerated
(`configgen`), check clean. Mechanism: the recipe trims the verbose/bimodal tail, not the chronic failures.

## Landed 2026-09-02 evening → 2026-09-03
- **C47 SHIPPED (`19e6fbb`)**: fingerprint v5 = serving-path tree hash beside the commit sha; `compare` refuses only on a
  serving-path change; older manifests derive it. Spec `docs/specs/c47-serving-path-fingerprint.md`. Live: `57177a21`
  ≡ `7330d3a6` ≡ `f5fff9b5`; `ab5708a` differs.
- **Docs reorganized (`6ae5772`)**: `docs/superpowers/`, `docs/sketches/`, `docs/work-queue.json` DELETED (git history
  is the archive, last present at `b723bde`); `docs/specs/` for design docs; `docs/README.md` index; PLAN.md is the ONLY queue.
- Community thread + JetBrains review (P43–P48) → **M31** ifeval arm for `Qwen3.8-27B-mlx-uniform-4bit` queued.
- Pre-session untracked rows committed (`5b8f4de`, `3ea3d9c`); C46 filed.

## M34 BUILT 2026-09-03 (forks pushed; submodule bumps landed 2026-09-06 `a08f933`)
Layer-scoped expert-budget expansion (spec `docs/specs/m34-moe-expert-expansion.md`). Fork `../mlx-vlm` main: `b95130c9` (feature)
+ `420c01e1` (verifier fixes) — 2 ahead of origin. `../mlx-serve` main: `0ccc684` — 1 ahead. Stack: `674499c`, `0e1a29b`, `3493c34`
(PARAMS drift-guard fix). NOT YET: fork pushes → `chore(stack): bump src/mlx-vlm` + `src/mlx-serve`; registry `moe_expand:` field on an
M34 overlay entry; the OFAT (after M33). Verifier scripts kept at `$TMPDIR/m34verify/` (re-run `v3_identity.py` after any routing edit).

## Artifacts
`$STACK_WORKDIR/m33/` (chain, waiter, `m33.log`; empty until the waiter fires).
`$STACK_WORKDIR/m31/` (chain, `m31.log`, driver + `watch_*` logs, grade + compare logs).
`$STACK_WORKDIR/c46/` (chain, `c46.log`, per-run driver + `watch_*` logs, `mem_arms.log`, pilot/full pids, grade + compare logs).
`$STACK_WORKDIR/m21/` (chains, logs, `k3_analysis.py --bench`, analyses, card draft, overlay);
`$STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed` (18 GB, the served local copy of the
uploaded repo — KEEP, it is the registry override target). HF cache: the `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source <!-- allow-shorthand -->
(52 GB) was DELETED 2026-09-03 18:20 (operator); re-download only if a new conversion is ever planned.

- Old-vs-new `compare` on C46 rows REFUSES by design: the old rows sit at serving path `17e0e5a7` (fork `0c1c8b17`), HEAD is `920efc38`; the verdict is new-vs-new plus the DNF follow-up. Item sets are identical (seed-0 draw), so the follow-up is paired.

**Order of resumption: this file → `docs/PLAN.md` (C46 row in open-questions, M31) → `docs/open-questions.md`.**
