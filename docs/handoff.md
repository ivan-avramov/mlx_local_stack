# Handoff — 2026-09-09 17:58 (Go running; resolution successor armed)

## Resume checklist

1. Read this checkpoint first, then PLAN's active execution order, README's ranking/evidence tables, and open questions C57–C59. This checkpoint supersedes previous B ordering and old Math500 accuracy scores.
2. Verify `queue/go_medium.pid` and `queue/resolution.pid` against command lines and logs, not PID existence alone. Check per-item row advancement. Never edit either running script, carrier or overlay. Kill a waiting successor BEFORE stopping its predecessor.
3. Keep the approved queue working. Check independent Rosetta regrade (`queue/resolution/regrade.pid`, serial evaluation logs and diff files). A repeated infrastructure fault is not a model failure. No regeneration until saved-answer recovery is exhausted.
4. On EVERY completed test/regrade, update README's B/C ranking AND evidence tables, report learnings, trends, non-convergence and proposed movers. Quality first; inconclusive does not mean discard. Promotions require approval.
5. Preserve SEVEN local `main_models.yaml` path overrides. Stage registry changes from the HEAD blob plus intended edits, never `git add main_models.yaml`. No push without explicit in-turn approval. Next discussion point P145; next C id C60.

## Approved decisions and landed work

- C57 RULED: provisional B order is 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (t0.5, medium, OFF); 2nd `Qwen3.8-27B-mlx-uniform-4bit` (t0.6, medium, certified MTP); 3rd `Ornith-1.0-35B-mlx-uniform-4bit` (t0.4, native, certified MTP); 4th `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (deployed t0.3, certified MTP). C retains its first two picks. README labels the other C entries as unranked evaluation shortlist.
- Commit `f9bb70c`: requested README tables/Best for, AGENTS upkeep rule, approved order/defaults, C51 medium adoption, redundant base medium bench clone retired. Configgen outputs all verified in `queue/c57_release/`. Client files updated. TWO live bench carriers remain intentionally old in the worktree until the Go boundary: `benchmark/aider_bench.model.settings.yml` and `benchmark/opencode_bench.json`. Their desired versions are committed and copied at the boundary by the successor, with pre-change hash guards. Do not “fix drift” while Go is active. No OWUI listener was present; its source JSON already matches generated output (reasoning_effort is registry-defaulted, no emitter).
- Commit `9945e87`: C58 Math500 parser fix. Four saved false-negative regression pairs failed first; 93 combined grader/configgen tests pass. Seven arms regraded from saved answers. README/campaign-results contain corrected scores and paired intervals. Broader historical math grading coverage audit still owed.
- No expanded routing or repaired predictor promoted. No push this turn.

## Live Go and successor

- Go runner PID 59406, `queue/queue_go_medium.py`, log `queue/go_medium.log`; router originally 59432, worker originally 59502, current driver 60078 — reverify. At 17:56, base medium Go 10/22 rows, 8 pass, 2 stalled, mean 323.5s, last five-minute advance +2. Partial results are NOT final. Then same22 cases on the mixed checkpoint at medium. Fresh immutable q7 overlay, predictor OFF. User opencode config temporarily installed and restored by runner finally.
- Successor PID 92141, `queue/resolution/run.py`, PID file `queue/resolution.pid`, log `queue/resolution.log`, errors `queue/resolution_launcher.log`. SELFTEST and predecessor liveness logged 17:57. Waits for Go PID exit AND Go DONE marker AND both22-row outputs; verifies no remaining driver before router transition. Snapshotted helpers, not modifications to running scripts. Five-minute log assessments; no automatic agent wakeup and no macOS scheduler.
- Executable order: activate deferred carriers → current-path base medium known-positive MTP control → mixed original medium OFF/ON → norm-corrected mixed medium OFF/ON → verify independent Rosetta audit completed → conditional M36 quality arms → full serving-environment expansion tests → M34r four-cell predictor interaction → M34r transfer resolution. See PLAN for counts. Any transport, provenance, test or grading fault stops dependent work for diagnosis. One resident model enforced.
- M36: if corrected speed screen ≥1.3x and all six converge, HumanEvalPlus and MBPPPlus n=50 k=3 OFF/ON (600 responses), five seeded pilots per arm, fresh baseline. Speed is a screening criterion only, quality certification still owed.
- M34r: `Ornith-1.0-35B-mlx-uniform-4bit` MBPPPlus n=100 k=1, native/expanded × MTP ON/OFF (400); `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` MBPPPlus + Math500 n=100 k=1 native/expanded (400). Expansion configs unchanged: `27-39:20:0.8:0.5` / `36-51:15:0.8:0.5`. Seed5909 across each corpus; pilot seed5910. Pilots are five items; means/max and right tails size expectations. Overlays regenerated at execution from approved registry plus local paths, all unrelated predictors stripped; driver env and manifest draft/registry/expansion verified.

## New findings and evidence

- Corrected M33 ordinary/strict: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 99/99, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 99/97, `Ornith-1.0-35B-mlx-uniform-4bit` 99/93 (n100 each). First-minus-second strict +2pp CI[-2,+6]; first-minus-third +6pp CI[+1,+12]. Descriptive pairwise95% intervals, before family multiplicity adjustment; nominal MDE12.5pp. Old89/88/86 counts and old accuracy intervals are superseded.
- Initial M34 Math500 corrected strict native93 vs expanded96; +3pp CI[-1,+8]; token ratio .835 CI[.669,1.028]. Native/expanded ordinary99/100. M34c five-item math pilot corrects1/5→5/5 BOTH arms. No generation rerun needed for parser fault.
- C59 MTP packaging cause: mixed sidecar's22 matrix/quant tensors already match the known-positive base; seven stripped-key BF16 norm vectors missed HF offset conversion. +1 with BF16 rounding makes ALL29 tensor payloads identical. Corrected candidate at `queue/mtp_recovery/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-normfix/`; original untouched. `artifact_audit.json`, `repack.py` and independently reproduced candidate SHA verify determinism. No live repair result yet. This artifact is not uploaded or production-certified.
- Expansion review:47 CPU-compatible tests pass; seven GPU-only tests and four missing-serving-dependency CLI tests remain for the correctly provisioned idle GPU check. No newly demonstrated routing defect. Do not call all58 passing or eleven routing failures.
- Independent serial MBPPPlus audit PID65835 (reverify), `queue/resolution/regrade_rosetta.py`: original M34a eval/score files archived in `resolution/rosetta_archive`; docker `--parallel 1`, same evaluator/image, bounded7200s each. Captures Rosetta errors, restores original eval if fault persists; per-item differences and serial scores on completion. Does not change generated answers. At17:58 native arm was329/578 padded entries; inspect live docker log if silent. This CPU work overlaps Go; do not treat concurrent latency as a quiet-box capacity measurement.

## Still owed after current queue

- Review/land finished M34a/M34b/M34c and dsh result artifacts; dsh eight-point checklist remains separate. Standard opencode remains preferred.
- Larger language coverage for the new B first choice; medium C axes, temperature ladder, M17/judge work remain PLAN items. Do not substitute this checklist for PLAN.
- Upload/certify repaired sidecar only after validation and operator approval. No approval to push.

## Pasteable continuation

Resume mlx_local_stack: read docs/handoff.md FIRST, then PLAN active execution order, README, C57–C59. Verify Go and resolution successor plus independent Rosetta audit and per-item progress. C57 order/C51 medium now approved and committed; two live bench carriers deliberately lag until Go boundary. Preserve seven local registry paths. Math500 scores were corrected by regrading; old accuracy intervals are invalid. MTP norm packaging candidate awaits queued controls/quality. Keep authorized queue working; report learnings/trends/B-C movers and update README on each completion. Never auto-promote or push.
