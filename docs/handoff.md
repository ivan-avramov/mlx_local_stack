# Handoff — 2026-09-07 14:30 (SESSION CHECKPOINT — QUEUE RUNNER 2 self-driving: S2b (hep leg LANDED `9414861`; mbpp/opencode legs in flight) → S2c → S3 M34 → S4 M35 → after_queue MTP control; rulings owed C50 + C51)

Single box (M5 Max 64 GB). **The box is BUSY and self-driving** (operator directive 2026-09-06: never idle; follow the queue). Router UP on
`$STACK_WORKDIR/queue/bench_overlay_q2.yaml` (pid 82020, on `queue/bench_overlay_q2.yaml` since 14:09), SESSION_MAX=2,
APC absent. Serving path = `src/mlx-vlm` 420c01e1 / `src/mlx-serve` 0ccc6842 (bumped `a08f933`); every row since carries it; older rows do not `compare`
across (C47). Working tree: NINE intentional `main_models.yaml` local-path overrides (7 + the two mixed-checkpoint effort clones) — NEVER commit;
committed registry edits go via the HEAD blob (`git show HEAD:main_models.yaml` → edit → `git hash-object -w` → `git update-index --cacheinfo`; then mirror
the edit into the worktree — READ the worktree file BEFORE opening it for write). origin/main = `4acefd2` (operator pushed 2026-09-07 14:10); UNPUSHED since: `9414861` (S2b hep leg). Push only on in-turn approval.

## Live processes (verify by pid, never infer)
- `queue/queue_chain2.py` pid in `queue/queue.pid` (7556), log `queue/queue.log`, launched 12:55. The orphaned S2b hep driver exited 14:08; router moved to
  `bench_overlay_q2.yaml` (pid 82020) 14:09; hep leg graded + paired + LANDED (`9414861`). Now: S2b resume (mbpp k=3 medium [pilot started 14:10] + fresh xhigh `m24x`, opencode python leg on
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-MED`) → S2c (hep n=164 on `Qwen3.8-27B-mlx-uniform-4bit-LOW` and `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-LOW`, paired vs xhigh `m32b` + medium `m24`) → S3 M34 (`Ornith-1.0-35B-mlx-uniform-4bit` `m34nat` vs `m34exp`
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
   Untracked rows now: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-MED/mbppplus.m24.*` (in flight — do NOT commit until the `S2b_mxmed_mbpp_med_full` SUMMARY line); then `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/mbppplus.m24x.*` and `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-MED/opencode.jsonl`. Extend the campaign-results 2026-09-07 S2b entry (currently hep-only) when they land.
3. Read the M35 smoke log (`queue/S4_dsh_smoke.log`) against the 8-point checklist in PLAN M35 before trusting the dsh leg.
4. When `=== AFTER-QUEUE DONE ===`: if the control shows acceptance ~0.67 the mixed sidecar's zero is real (head incompatible → ships draft-OFF, record);
   if the control ALSO shows zero acceptance, MTP is broken on the bumped serving path → C-item, urgent (the B 1st/2nd/3rd triples ship mtp).
   Restart the router on `queue/bench_overlay_q2.yaml` before any new arm.

## Landed 2026-09-07 14:30 — S2b hep leg (campaign-results 2026-09-07 S2b entry, PLAN M24 row)
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-MED` hep n=164 strict 95.1, 0 loops, 1.35 h: vs own xhigh (`m32b` 93.9) +1.2pp CI [−1.8, +4.9] EQUIVALENT, tokens 0.42×;
vs `Qwen3.8-27B-mlx-uniform-4bit-MED` (93.9) +1.2pp CI [−1.2, +3.7] EQUIVALENT, tokens 0.79× CI [0.65, 0.94], wall 1.35 h vs 1.27 h. **At medium-vs-medium the
mixed checkpoint's hep wall edge is GONE** (slower decode at 4.98 bits eats the token saving) → C50's usability case now rests on the agentic legs; S2b's
opencode leg (mixed at medium vs the base-medium 19/22) is the deciding cell. Extra paired JSON: `queue/paired_S2b_mxmed_vs_u4med_hep.json` (run `paired_ofat.py` from `benchmark/` with `PYTHONPATH=.`).

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
1. C50 + C51 rulings → registry/carrier changes in ONE commit each (a pick or tune change touches all five carriers; medium adoption also needs the
   predictor re-probe at medium once the instrument is validated).
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
