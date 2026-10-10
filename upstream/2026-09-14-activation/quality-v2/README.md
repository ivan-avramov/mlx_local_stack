# C84 amended AFTER protocol

**PREPARED AND UNSEALED.** Independent review cleared31 CPU checks. Root reports the actual published522671c4 VLM bundle passed all five smoke cases (six requests), including the previous tool-continuation OOM and vision. Root is completing three-turn reuse validation and final actual-stack tests before sealing; no seal or model launch has been performed by this adapter.

This directory implements only the40 remaining AFTER requests. The completed40 BEFORE requests, original scripts, frozen plan, raw responses, canonical rows/manifests, grading results and exact registry snapshot remain unchanged under the sibling `quality` directory. The unused earlier5b43e5d9 after freeze is historical and cannot launch this adapter.

The treatment is a **combined deployed stack bundle**: VLM lifetime, logical-trim and eager physical-release repairs plus the new upstream commits, the Serve per-model retirement option, and `cache_session_shrink: true` on Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed only. Qwen3.8-27B-mlx-uniform-4bit keeps its entire registry entry unchanged. Do not attribute measured differences to an isolated repair, upstream kernel change or retirement policy. Root's separate fix-only live smoke supplies distinct evidence for that narrower question.

Expected installed source bundle:

- BEFORE VLM `e3bffd9a25510d5ed2d27079ff0eb76f749c544f`, Serve `f8f1df4952b2baf15f3504159f2869e170795fb2`.
- AFTER VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`, Serve `b632280709f771972bffbaf3231e996e8a89f4e8`.
- Same69 serving package versions and editable source paths, deployed sampling, corpus items, explicit seeds, exact raw request JSON, cap/preallocation262144, prefill512, sessions2, APC absent and per-request timeout21080s with zero retries.

`prepared.json` was built against the actual amended main registry. Preparation protects220 baseline/source inputs. It verifies the entire parsed registry against the archived exact baseline, permitting only the native16 boolean field; numeric type drift also fails. Current benchmark code must match the original freeze except the reviewed hashes for `provenance.py`, `compare.py` and `compare_predictor.py`. These add truthful retirement metadata and hardware refusal guards; all builders, generator, client, grader, extractor and statistics remain pinned. The AFTER manifests must include retirement metadata (true for native16, null for the unchanged TQ4 entry). Actual native16 worker CLI must emit `--cache-session-shrink on`; TQ4 must omit it. Global cache/retirement environment overrides are rejected.

Historical BEFORE validation uses `quality/registry-before.yaml` and SHA-verified `quality/historical-code/{provenance,compare,compare_predictor}.py`. It does not compare old provenance bytes or registry SHA to the current changed files, and never rewrites an old manifest. The paired ratio estimator AST is verified unchanged against its archived definition. The ordinary comparison guards remain intact; this dedicated analysis declares the complete source/retirement treatment explicitly.

## Root commands

No model/HTTP/GPU/container job was run during preparation. Root owns lifecycle, one-model occupancy and approval to launch after independent review. Set:

```sh
C84_AFTER=$STACK_WORKDIR/upstream/2026-09-14-activation/quality-v2
C84_PY=$STACK_REPO/.venv-bench/bin/python
export PYTHONPATH=$STACK_REPO/benchmark
export MLX_SERVE_CONFIG=$STACK_REPO/main_models.yaml
export TMPDIR="$C84_AFTER/tmp"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE=1
export HF_DATASETS_OFFLINE=1
```

The real-input preparation already exists; do not overwrite it. Once the reviewed final bundle passes root's live checks, seal:

```sh
"$C84_PY" -B "$C84_AFTER/screen.py" seal --phase after \
  --vlm-sha 522671c4bebc5ff492d465a1d0e6a14251f18260 \
  --serve-sha b632280709f771972bffbaf3231e996e8a89f4e8
```

Record the printed SHA as `C84_AFTER_PIN`. Load the intended model with the root lifecycle helper and preserve its fresh launch-evidence path/SHA as `C84_LAUNCH`/`C84_LAUNCH_PIN`. For each `C84_MODE` (`native16`, then `tq4`):

```sh
nohup "$C84_PY" -B "$C84_AFTER/screen.py" run --phase after \
  --mode "$C84_MODE" --frozen-sha "$C84_AFTER_PIN" \
  --launch-evidence "$C84_LAUNCH" --launch-evidence-sha256 "$C84_LAUNCH_PIN" \
  >"$C84_AFTER/after-$C84_MODE-supervisor.log" 2>&1 </dev/null &
```

Every request is gated by parent ACK after source/runtime/registry/worker/listener and all four manifest checks. Inspect the owned process and `runs/after/<mode>/heartbeat.jsonl`; the daemon selftests, assesses every300s, and records RUNNER-EXIT. No numeric memory cutoff or resume/overwrite is allowed. After an arm completes, finalize before changing its source/configuration:

```sh
"$C84_PY" -B "$C84_AFTER/screen.py" finalize --phase after \
  --mode "$C84_MODE" --frozen-sha "$C84_AFTER_PIN"
```

Review that evidence and capture its SHA as `C84_FINAL_PIN`. Run mechanical grading offline when root schedules container work:

```sh
"$C84_PY" -B "$C84_AFTER/grade_screen.py" --phase after \
  --mode "$C84_MODE" --frozen-sha "$C84_AFTER_PIN" \
  --run-evidence "$C84_AFTER/finalized-after-$C84_MODE.json" \
  --run-evidence-sha256 "$C84_FINAL_PIN"
```

The unchanged reviewed ARM64 sandbox helper preserves read-only samples, isolated output, owned-CID cleanup and the pinned offline image. Full corpus IDs come from frozen files, avoiding the host EvalPlus downloader. Canonical math/code scoring and symbolic known-positive checks are preserved. Prose receives mechanical integrity records and a review document, with no fabricated quality score.

After both AFTER arms are finalized and graded, the separate analyzer audits both old BEFORE arms and new AFTER arms:

```sh
"$C84_PY" -B "$C84_AFTER/analyze.py" \
  --before-sha 5716db4fc30e0ac458fa78b1aa8b6b006a0087f4bcf40e502f75a59c4daf3c11 \
  --after-sha "$C84_AFTER_PIN"
```

Outputs: `analysis/comparison.json` and `analysis/paired-prose-review.md`; add `--check` for deterministic read-only verification. Record human/source prose judgements separately. The analyzer requires all80 requests/four graded arms and never emits a prefix verdict. Per-model/per-axis quality and convergence deltas are after−before; wall/token/mean-per-request-decode ratios are after/before, seed84 and10000 paired bootstrap replicates. No cross-model pooling or composite quality ranking. Five pairs per axis and zero discordance do not establish ±5pp equivalence. Short-task memory telemetry is not capacity evidence; root's matched long-context probes remain separate.
