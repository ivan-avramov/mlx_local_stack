# Box operational notes (single-box era, M5 Max 64 GB)

Operational facts that exist nowhere else, moved from AGENTS.md on 2026-08-23 (token-budget
cleanup). Since 2026-08-17 the M5 Max is the SOLE box (driver + worker). The retired two-box
procedures are archived in `docs/two-box-archive.md`.

## Toolchains & grading infrastructure

- **The `aider-benchmark` docker image is the ONLY place all five language toolchains exist, at pinned versions** — go 1.21.5, node 20.20.2, cargo 1.97.1, javac 21.0.11, python 3.11.15, pytest 9.0.2, aarch64-native. The host has only node and python. **It is a GRADING SANDBOX — keep it even though aider is retired**; multi-language opencode grading depends on it.
- **LiveCodeBench grading recipe:** `uv venv --python 3.11` + `uv pip install 'datasets<3' json_repair requests numpy` (pyext NOT needed), then `PYTHONPATH=$HOME/.cache/livecodebench/LiveCodeBench .venv-lcbgrade/bin/python benchmark/run.py grade --models <M> --benches livecodebench`.
- **BFCL does NOT run through `run.py generate`** (`unknown benchmark 'bfcl'` — absent from `benchmarks.SPECS`). It runs via `bench/bfcl_adapter.py` driving `bfcl-eval`, plus `bfcl_shim/` and `bfcl_diag.py`. Mistaking this is what produced the laundered fake smoke.
- **EvalPlus docker mechanics** (`grade_evalplus`): the official evaluator runs IN DOCKER (`ganler/evalplus`, `--platform linux/amd64`) because evalplus's `reliability_guard` calls `resource.setrlimit` in a way macOS rejects — it crashes natively but runs clean in the Linux container (which also isolates the executed code). evalplus asserts ALL dataset problems are present, so a small-N subset is PADDED to the full set with failing dummies, and pass@1 is read for ONLY the generated subset from the per-problem `*_eval_results.json` (`eval[task_id][0].base_status/plus_status`; headline acc = the stricter `plus`). The `-v` host mount MUST be absolute (a relative path becomes a docker named volume → empty `/work`). LiveCodeBench uses `lcb_runner` directly (no docker).
- **Venvs:** `.venv-bench` = mlx+pytest+json_repair, NO `mlx_audio` (epicache/unit tests run here; `test_server.py` won't collect). `.venv` / `../mlx-vlm/.venv` = full deps. bfcl-eval (2026.3.23) is in `.venv-bench` on this box. **`mlx_optiq` is 0.4.21 and its import name is `optiq`. These uv venvs have no `pip`, so `pip show` prints nothing — that is not evidence of absence.** <!-- allow-shorthand -->

## macOS / box administration

- **Do NOT put this repo, or the aider/polyglot clones, under `~/Documents`, `~/Desktop` or `~/Downloads`.** TCC denies protected folders to publickey ssh sessions; it cost 21 java cases mid-run. Root cause: `/etc/pam.d/sshd`'s `pam_opendirectory.so` runs only for password auth and OpenSSH skips the PAM auth stack for publickey, so no OpenDirectory session exists and TCC denies. Fixes: keep the repo out of protected folders (survives OS updates), or grant Full Disk Access to `/usr/libexec/sshd-keygen-wrapper`.
- **The box is Jamf-managed.** If it goes unreachable, confirm Remote Login is still on (`systemsetup -getremotelogin`) — a compliance policy can switch it off — and find it with `dns-sd -B _ssh._tcp local` rather than a subnet scan.
- **`~/mlx_bench_snapshots/pre-deployed-evalplus-2026-08-14/` is the ONLY copy of the retired-box rows.** They are not re-measurable at any price. **Never run `--clean-stale` against an un-archived tree.**

## Conversions & heavy jobs

- **`mlx_optiq` conversions cannot co-reside with the AI session** — measured on the retired driver: 24 min elapsed for 1:49 of CPU (~6%), swap 2 GB → 8 GB, and the expensive KL phase had not started. Schedule conversions in a quiet window; a partial `~/optiq_out` baseline is scratch, not resumable. <!-- allow-shorthand -->
- **`opencode` costs ~18,050 prompt tokens for a four-word request** — budget prefill accordingly for agentic runs.

## Corpus provenance facts

- **The corpus SPLITS at a deployed-code sha.** Bumping `src/mlx-vlm` 8b7100b8 → 0c1c8b17 changed a matched item from 2,475 to 3,526 completion tokens with identical prompt and sampling, deterministically 3/3, while the model implementation and sampler were byte-unchanged. Rows either side are NOT poolable (the sha is in the fingerprint). Attribution unresolved; a bisect over the 30 commits would settle it (repro: one item, ~35 s).
- **The polyglot corpus has NO difficulty or category metadata** (`.meta/config.json` holds only authors), and the 110-item matched set is 5 languages × a *different* random 22 each — 57 distinct exercise names, only 3 common to all five. **Within-language cross-model comparison is valid; CROSS-LANGUAGE IS NOT** — "multi-language ranking" means five per-language rankings, never one blended number. cpp is excluded on purpose: it measures the C++ toolchain, and one case produced a 165k-token prompt.
- **Two contamination controls for the agentic harness:** `.meta/` holds the reference solution, so exclude it from any scratch copy; and **the models DO rewrite the test file** — observed — so a modified test invalidates the grade and is scored as a FAILURE.
- **`session_pass` (an opencode session outcome) is NOT comparable to aider's `final`**, which allows a second test-informed attempt. Score the session outcome, never intermediates.
- **IFEval's vendored verifiers INVENT the criterion when a kwarg is absent** — e.g. a "use keyword X" instruction with no keyword supplied gets a verifier-chosen one. Ruled LEAVE IT (deterministic, documented, 0.2% of items) — but anyone quoting an IFEval number should know ~0.2% of items are graded against a criterion the verifier made up.
- **The per-model DERIVED MAX PROMPT is a real limit written down nowhere else.** `max_tokens` 102400 with the 0.8 clamp puts it near **159,744 tokens for `Ornith-1.0-35B-mlx-uniform-4bit`**, and LOWER for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (larger thinking budget). Above it the model silently gets less room to think. Record it per model and preflight against it before any depth axis.

## Third-party quant families (identification hazards)

- **`oQ*` / `omlx` repos are a DIFFERENT quantiser family from our `mlx_optiq`** — do NOT read `oQ4e` as one of our own builds. <!-- allow-shorthand --> The family now appears under the `mlx-community` org, which lends credibility it has not earned. Related: **every public `mlx-optiq` build is named `-4bit` and none is 4 bpw** (measured ~5.14); ours are 3.966 / 4.0 / 4.501. Never register one as a "4-bit arm".
- **The `mlx_optiq` mixed-precision recipe does NOT support the `qwen3_5_moe` FUSED-expert layout.** `Static mixed recipe failed: 30720 params not in model` (256 experts × 40 layers × 3 proj — the quantiser allocates bits per UNFUSED expert, mlx_lm loads them FUSED) → a broken 8.376 bpw / 34 GB artifact, not a valid 4-bit. Expect it on any MoE self-conversion. <!-- allow-shorthand -->

## Retired-harness facts still worth knowing

- **The aider `weak_model_name` "bug" is NOT a bug — do not re-fix it.** aider builds the weak model as its own `Model` and merges `extra_params` into litellm kwargs, so :8092 is reached BY DESIGN; "fixing" it would move commit-message generation onto the 19–29 GB agent model. **The real hazard is benchmark-only:** the lean bench-router recipe starts :8000 only, so a weak call gets ECONNREFUSED and then aider's 24 h `RETRY_TIMEOUT`. Same shape as opencode's `small_model` pointing at :8092.
- **A bench harness that mounts a CLIENT config silently excludes `role: candidate` models**, and a candidate then runs at the harness's default sampling. That is why `benchmark/aider_bench.model.settings.yml` and `benchmark/opencode_bench.json` exist as BENCH carriers. Expect this with every new candidate.
