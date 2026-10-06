# M60 — certification of the final shipped state on Math500 and the judge panel — spec of record

Status: APPROVED by the operator 2026-10-06 (C127, "approved with your recs": design P116–P125, including the
pilot as phase A of the run, no shipped-state predictor-OFF arm, and lifting the PROVISIONAL labels on PASS).
NOT YET RUN. This file is agent-facing: rules, not rationale. Runner: `$STACK_WORKDIR/m60/run_m60.py`
(self-contained; `--dry-run`, `--analyze-only`); judge pass: `$STACK_WORKDIR/m60/JUDGE.md`.

## Scope

- Model: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, exactly as `main_models.yaml` declares it: native16 KV
  (`kv_bits: 0`), `attention_policy: fused_v1`, `lazy_prompt_embeddings: true`, `mtp_verify_scan: joint_v1`,
  `draft_kind: mtp`, t0.5, medium, thinking ON, budget 81920, max_tokens 102400. No overlay.
- One arm, tune `m60ship`: Math500 on the 100 ids of `$STACK_WORKDIR/queue/resolution/ids.json[math500]`
  (the M37/M40 set) and `cjudge` v1 (40). k=1, seed base 0 — the seeds of the reference rows.
- References, reused and never regenerated: `math500.m40on` (primary), `math500.m37med` (descriptive only),
  `cjudge.m40on`, the 30 anchor pairs `benchmark/results/judge_c_v1/pairs.jsonl`.
- The references ran on TQ4 KV, fork `420c01e1`, fingerprint v5. The arm therefore compares across native16
  (C81), `fused_v1` + lazy embeddings (C115), `joint_v1` (C126) and all serving-code changes since, together.
  A failure is not attributable to one of them without the escalation below.
- Serving shas are whatever is shipped at run time; the runner records stack HEAD, submodule shas, registry
  sha256 and fingerprint version. If an upstream fork merge lands before the run, the comparison includes it
  and the result entry says so.
- Not in scope: a shipped-state predictor-OFF arm (C127 sub-ruling), a `per_query` arm (M58 is identity-gated),
  coding, depth, vision, any second loaded instance.

## Regrade vs rerun

| item | action |
|---|---|
| 100 Math500 + 40 cjudge generations in the shipped state | RERUN (serving-path change) |
| `math500.m40on`, `math500.m37med` scores | regrade in memory with the grader of the run, same pass as the new arm; committed score files are not rewritten; if `n`, `acc`, `acc_strict` or `conv_rate` moves, STOP and report |
| reference rows, anchors, item ids, seeds | reuse |
| judge reliability gate | recompute with the panel of the run (judge calls only) |
| coding, depth, vision, `per_query` | not rerun |

## Router and verifications (all before item two)

- Run only after the operator says the stack is down. Never while another runner or waiter is alive
  (`run.lock`). Launch detached; the exit code is also written to `run_m60.rc`.
- Preflight refuses unless: `:8000` is free; no `mlx_vlm.server`, `mlx-serve start`, `runserver.sh`,
  `session_cache_probe`, `opencode run`, or benchmark driver process exists; no compose service is up; adapter
  140 W / 28 V and battery > 20 %; the registry entry carries the shipped state above; reference rows,
  manifests, committed scores, resolution ids and anchors are present; no `m60ship*` row file exists.
- Lean router: `MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=main_models.yaml uv run mlx-serve start`,
  cwd = repo, `APC_ENABLED` absent, `.env` sourced when present. No OpenWebUI, no docker.
- Verify: exactly one `:8000` listener, it is mlx-serve, its environment carries both variables and no
  `APC_ENABLED`, its cwd is the repo. Load the model through the router, then verify exactly one worker whose
  cmdline has `--attention-policy fused_v1`, `--lazy-prompt-embeddings`, `--mtp-verify-scan joint_v1`,
  `--draft-kind mtp`, `--max-kv-size 262144`, `--kv-prealloc-tokens 262144`, no nonzero `--kv-bits`, no
  `--mtp-verify-ab`; worker environment: session max 1, no `APC_ENABLED`. Record the worker cmdline.
- Every driver: `MLX_SERVE_CONFIG=main_models.yaml` in its environment (verified on the driver pid),
  `--sampling-profile deployed`, `--order roundrobin`, `--seed 0 --seed-base 0 --samples 1`, timeout DERIVED
  (no `--probe-timeout`), no restart-on-loop, retries 0.
- First manifest of every tune, checked while item one runs; on mismatch the driver is killed and the rows are
  false-provenance: `runtime.draft_kind == mtp`, `attention_policy == fused_v1`, `lazy_prompt_embeddings`,
  `mtp_verify_scan == joint_v1`, `kv.kv_bits == 0`, cap and prealloc 262144, deployed sampling values,
  `registry.sha256` == sha256 of the served file, fingerprint version == the harness's (≥ 8), `router.pid` ==
  the verified router, `router.config_sha256` == the registry sha.
- Every generated row must carry `draft.draft_kind == mtp` with `draft_n > 0`.
- `benchmark/m1/bench_watch.py` runs beside every driver (300 s). The runner logs adapter/battery state on the
  same cadence; a deviation is logged and makes the decode/wall figures non-citable (quality verdicts stand).

## Phase order (one loaded instance)

1. Math500 pilot: the 5 recorded pilot ids, tune `m60ship`. These rows ARE part of the arm.
2. The same 5 ids again, tune `m60ship-p2`. Diagnostic rows: kept, never graded, never pooled.
3. Pilot-twice: content sha, reasoning identity (`reasoning_sha256`, else head/tail/length), completion
   tokens, finish reason and sampler seed must be identical 5/5, and the worker pid unchanged. Else STOP.
4. cjudge pilot: `--limit cjudge=5 --seed 0`, tune `m60ship` (part of the arm).
5. Cost go/no-go: pilot mean wall × n. More than 4 h projected for either bench → STOP and report.
6. Math500 remaining 95 (same tune; the driver resumes), then cjudge remaining 35.
7. Router pid and worker pid unchanged since step 1, else STOP (rows span two loaded instances).
8. Unload, `scripts/stack_stop.sh`, verify `:8000` free and no serving process. The stack stays stopped.
9. ROW GUARD, then grade, reference regrade check, paired read, `summary.json` / `summary.md` (CPU only;
   repeatable with `--analyze-only`).
10. Judge pass per `JUDGE.md` (no GPU).

No resume across loaded instances: if any `m60ship*` rows exist, the runner refuses to generate. Archive them
first (never `--clean-stale`).

## Tripwires — abort, nothing graded

- Any driver exit ≠ 0 (transport error, M50/C106 refusal, timeout bound).
- ROW GUARD: any `m60ship` row with `error` whose `error_kind` is not `probe_timeout`. (`generate` still writes
  such rows — C119 is not built; a probe-timeout DNF is a legitimate row and a strict failure.)
- First-manifest mismatch, driver-environment mismatch, router/worker verification failure.
- Pilot-twice mismatch; worker or router change during the arm; a torn row file.
- A reference score that moves under today's grader.
- Cost no-go.

## Criteria (pre-registered)

Math500, ranking key `acc_strict@81920`, n=100, paired by item, `bench.stats.paired_delta` (two-stage cluster
bootstrap, 10000 iterations, seed 0), delta = `m60ship` − `m40on`:

- PASS: CI lower bound > −5 pp. Evaluated first (a significant loss inside the margin is PASS, as in
  `compare_predictor`). If the CI upper bound is also < 0, report it as "PASS — significant loss within
  the margin", never as a plain PASS.
- FAIL: CI upper bound < 0, or point ≤ −5 pp.
- Otherwise INCONCLUSIVE: the axis stays PROVISIONAL.
- `compare_predictor` refuses this pair (several manifest keys differ); it is not weakened. The runner prints
  the manifest differences it compares across and is the M60 instrument.
- Red flag: ≥ 3 non-converged items (references: 0). Stop and report with `nonconv_kinds`; the temperature
  ladder is the tool, never the budget.
- Report the discordant items in both directions, the `m37med` delta (descriptive), convergence, tokens/task,
  decode tok/s, wall, MTP acceptance, `verify_*` and `sdpa_*` counters. State the MDE (±12.5 pp at n=100) and
  that PASS needs roughly ≤ 1–2 net losses.

cjudge, pair `m40on` vs `m60ship`:

- All 40 converge; shared converged items with `m40on` ≥ 38. Else stop and report.
- The six-metric reliability gate of `docs/judge-panel-c.md` must PASS with the panel of the run, computed on
  the anchors before any item packet is issued. Gate FAIL → no verdict.
- FAIL: `m40on` preferred with p < .05. Otherwise "no detectable drift at n=40 (MDE ±20 pp)" — an underpowered
  PASS, always labelled so.
- Token-length ratio `m60ship`/`m40on` outside [0.8, 1.25] → report the length-adjusted margin beside the raw one.

## Judge pass

- `run_judge_pairwise --models <model> --pair-tunes m40on m60ship --anchors benchmark/results/judge_c_v1/pairs.jsonl
  --out benchmark/results/judge_m60/<model>`. Always the explicit `--out`: the default writes into
  `judge_c_v1/` on every invocation, including `--dry-run`.
- 40 items × 2 orders × 3 judges = 240 item verdicts + 30 anchors × 2 × 3 = 180 anchor verdicts.
- Panel: Codex `gpt-5.6-terra` medium in-process; `opus` and `sonnet` as blind Claude Code subagent packets. <!-- allow-shorthand -->
  The tool's judge labels are fixed strings: record the exact model each label ran on in
  `judge_m60/<model>/panel.json` before the first call. The Claude judges are not the versions gated in
  M38/M40, so the gate result of the run is the only admissible one.
- Blindness of the Claude judges: a subagent inherits the user and project instruction files (which name the
  models and picks) unless told otherwise. Run them through a judge agent definition with `omitClaudeMd: true`
  (or headless `claude --bare -p` from an empty directory outside the repo). Before the anchors, one canary
  packet asks the judge to list any project or user instructions it can see; anything listed → STOP and fix.
  Record the mechanism in `panel.json`. (M38/M40 judges ran without this; one more reason the verdicts never pool.)
- Anchors first for the Claude judges; the anchors-only gate is computed in a scratch directory (the gate tool
  writes a ranking file whenever it passes). Item packets only after it passes.
- Never pooled with M38 or M40 verdicts. `judge_c_v1/` and `judge_m40/` must be untouched (`git status`).

## Decision rule

- Math500 PASS and cjudge PASS → same commit: `generation_defaults` gains `CERTIFIED M60 <date>` (Math500 and
  judge panel in the shipped state, with the numbers); the "broader quality provisional" wording on the C81,
  M57 and M58 registry comments is updated and their PROVISIONAL labels are lifted (C127); README ranking and
  evidence tables, `docs/model-recommendation-evidence.md`, `docs/campaign-results.md`, PLAN row, handoff.
- Any FAIL or red flag → no registry change; open a decision item with the escalation plan.
- INCONCLUSIVE → labels stay PROVISIONAL; report the interval.
- No pick or order change in any case.

## Escalation (pre-registered; needs a new operator go)

OFAT on the failing axis only, same items and seeds, lean router, one-key overlays:
1. `kv_bits: 4`, everything else shipped (isolates native16).
2. `attention_policy: auto` with `lazy_prompt_embeddings` off (isolates M57).

## Cost bound

≈ 3.3 h box (lower bound from `m40on`: Math500 1.20 h, cjudge 1.07 h; pilots and load ≈ 0.3 h; one runaway
allowance). Driver wall bounds 12 h / 8 h are kill bounds, not estimates. Judge pass ≈ 4 M subagent tokens
+ 140 Codex calls, no GPU.

## Runner exit codes

0 complete (read `summary.json` for the verdict) · 2 preflight refusal, nothing started · 3 tripwire, nothing
graded, stack stopped · 4 internal error. Before a real run: `run_m60.py --dry-run` must exit 0 with only the
expected would-refuse lines, and `test_run_m60.py` must pass.
