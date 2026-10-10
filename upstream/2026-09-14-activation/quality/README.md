# C84 fresh actual-stack repair quality regression

Prepared only. No generation, HTTP, GPU, installation or container execution was performed while preparing this instrument. Root owns loading, unloading, supervision and the decision to launch after review.

The comparison has **80 generation requests**: two phases × two models × four axes × five items. `before` uses actual main MLX-VLM `e3bffd9a25510d5ed2d27079ff0eb76f749c544f`; `after` is intended to use the reviewed C85 repair `5b43e5d934a423303b731d6847120a945a1c6a69`. Both use MLX-Serve `f8f1df4952b2baf15f3504159f2869e170795fb2`, the same main `.venv` package set, and the actual main registry. Final seal commands require installed full source SHAs.

- `native16`: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, native16 KV, repaired MTP, deployed temperature0.5.
- `tq4`: Qwen3.8-27B-mlx-uniform-4bit, TQ4 KV, MTP, deployed temperature0.6.
- Each arm uses the five frozen C77 items on Math500, HumanEvalPlus, MBPPPlus and cjudge; one explicit sample-zero seed per item. The first model's15 math/code payloads exactly match C82, verified against its frozen artifact. All four phase/model combinations use canonical `run.py generate`, roundrobin, deployed profile, generous102400/81920 bounds, full262144 cache cap/preallocation and prefill512.
- Historical mean-based reference:3909.2383s (65.15min) generation for80 requests, excluding startup, grading and tails. First model27.72min, second37.44min across both phases. This is a planning reference from historical configurations, not a guarantee; historical Math500 maxima493.7/806.6s.
- This is a fresh before/after **repair** experiment, not the original C77 old/upstream-runtime80 proposal. Historical records select tasks and inform planning; they are not substituted for a fresh baseline or used for causal attribution.

`prepared.json` contains exact prompts/payloads/seeds, corpus identities and hashes, canonical builder/extractor/grader hashes, all69 serving package versions, editable import roots, actual registry hash and historical timing references. Each phase seal adds its actual clean serving source fingerprints and current instrument hashes. The `after` seal requires both20-request `before` arms complete, exactly paired requests/registry/bench code/runtime, unchanged Serve SHA and a changed VLM SHA. Existing prepared revisions were preserved; no phase was sealed by the implementation worker.

Before each request the parent checks the frozen inputs, actual worker/router PID and creation time, ports8000/8091 ownership, worker executable/defaults/cache flags/environment, single worker, source and runtime pins, registry and all four canonical manifests, then ACKs the child. Requests have no retries. Protocol/transport failures escape canonical error-row recovery and abort the arm. A daemon records a known-positive selftest, assessments every300s and RUNNER-EXIT. No numeric memory cutoff. Root handles worker cleanup; the supervisor cleans only its owned child process group. Each arm is exclusive-create and nonresumable.

## Commands for root

Set the following in the root shell; all output remains private. These commands are recipes, not a lifecycle script. Load exactly the intended model through the root-owned lifecycle helper before each arm and preserve its launch evidence.

```sh
C84_QUALITY=$STACK_WORKDIR/upstream/2026-09-14-activation/quality
C84_BENCH_PY=$STACK_REPO/.venv-bench/bin/python
export PYTHONPATH=$STACK_REPO/benchmark
export MLX_SERVE_CONFIG=$STACK_REPO/main_models.yaml
export TMPDIR="$C84_QUALITY/tmp"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export HF_DATASETS_OFFLINE=1
```

The input preparation is already saved. After independent instrument review, while main remains on the before source:

```sh
"$C84_BENCH_PY" -B "$C84_QUALITY/screen.py" seal --phase before \
  --vlm-sha e3bffd9a25510d5ed2d27079ff0eb76f749c544f \
  --serve-sha f8f1df4952b2baf15f3504159f2869e170795fb2
```

Record the printed frozen SHA as `C84_PHASE_PIN`. For each mode (`native16`, then `tq4`), set `C84_MODE`, the root-created launch-evidence path `C84_LAUNCH`, and its SHA `C84_LAUNCH_PIN`. Confirm the phase/mode are correct, then detach:

```sh
nohup "$C84_BENCH_PY" -B "$C84_QUALITY/screen.py" run \
  --phase before --mode "$C84_MODE" --frozen-sha "$C84_PHASE_PIN" \
  --launch-evidence "$C84_LAUNCH" --launch-evidence-sha256 "$C84_LAUNCH_PIN" \
  >"$C84_QUALITY/before-$C84_MODE-supervisor.log" 2>&1 </dev/null &
```

Wait for the owned supervisor and inspect `runs/before/<mode>/summary.json`, `heartbeat.jsonl`, and the root worker logs. **Before changing sources**, independently finalize each completed arm:

```sh
"$C84_BENCH_PY" -B "$C84_QUALITY/screen.py" finalize \
  --phase before --mode "$C84_MODE" --frozen-sha "$C84_PHASE_PIN"
```

Review the finalized evidence and record the printed SHA as `C84_FINAL_PIN`. Then grade offline (this command launches the pinned ARM64 containers, so root executes it when model work is stopped or otherwise explicitly scheduled):

```sh
"$C84_BENCH_PY" -B "$C84_QUALITY/grade_screen.py" \
  --phase before --mode "$C84_MODE" --frozen-sha "$C84_PHASE_PIN" \
  --run-evidence "$C84_QUALITY/finalized-before-$C84_MODE.json" \
  --run-evidence-sha256 "$C84_FINAL_PIN"
```

After both fresh baselines are completed/finalized and root installs the reviewed fix, seal the after phase:

```sh
"$C84_BENCH_PY" -B "$C84_QUALITY/screen.py" seal --phase after \
  --vlm-sha 5b43e5d934a423303b731d6847120a945a1c6a69 \
  --serve-sha f8f1df4952b2baf15f3504159f2869e170795fb2
```

Repeat the per-model run/finalize/grade commands using **after** everywhere and the new after frozen SHA/launch evidence. Never reuse a before launch artifact after restarting or changing sources. All outputs/tags are phase-separated. Review each `grades/<phase>/<mode>/prose-review.md` and compare paired bodies; mechanical integrity and hash equality alone are not prose quality.

## Grading and reporting limits

Math and code use the unchanged canonical grading functions. The ARM64 sandbox helper is SHA-pinned to the reviewed C82 implementation: offline fixed image, no network, read-only samples bind, isolated writable evaluator output, original rows/manifests never mounted, and captured-CID cleanup. Full executable-corpus IDs come from the frozen local corpus, so the host EvalPlus downloader is never called. The adapter requires exact math-grading versions and a symbolic fraction1/2=0.5 known-positive that string fallback cannot pass. Canonical failure handling and official pass/fail/timeout semantics are retained. HumanEval/141's existing prompt/reference discrepancy must remain an official failure if observed again.

Report per-axis matched outcomes, convergence, exclusive solves, tokens and wall/decode metrics; analyze paired before/after rows with their declared source treatment. Five items per axis are a diagnostic, not ±5pp equivalence certification. Do not rank prose by length or hash. No generated code executes on the host. No API judges or automatic promotion/default changes are part of this instrument.
