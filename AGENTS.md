# mlx_local_stack

Local stack: mlx_vlm task model (port 8092), mlx-serve main models (port 8000), and OpenWebUI on docker compose (port 3000).

## Slash commands

- `/mlx start` — runs `./runserver.sh` (syncs submodules, backs up OWUI data, launches both model servers, brings up compose, tails logs; Ctrl+C tears down via the trap).

## Entry points

- `runserver.sh` (full bring-up; reads `.env` for `HF_TOKEN`), `main_models.yaml` (mlx-serve registry), `openwebui_config.json` (seeded each start), `do_backup.py`.

## Client/agent integrations (configs we ship)

Five clients, all pointed at the mlx-serve router (`localhost:8000`, OpenAI-compatible), all exposing the two winners (`Ornith-1.0-35B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`):

| config | client | class |
|---|---|---|
| `opencode_config/opencode.json` | opencode CLI (primary agentic driver) | full-sampling |
| `aider_config/` (`aider.model.settings.yml` + `.model.metadata.json` + `.conf.yml`) | aider (also the bench harness via `benchmark/run_aider_docker.sh`) | full-sampling |
| `openwebui-init/models_config.json` | OpenWebUI (:3000) — SOURCE OF TRUTH, pushed to OWUI by `publish_models.py`/`init.py` (NOT the DB-export `openwebui_config.json`) | full-sampling |
| `vscode_config/chatLanguageModels.json` | VS Code — Copilot Chat BYOK + Roo Code | registration-only |
| `zed_config/settings.snippet.jsonc` | Zed editor assistant | registration-only |

- **full-sampling** (opencode, aider, openwebui): carry the complete per-model sampling — `temperature`, `top_p`, `top_k`, `min_p`, `presence_penalty`, `max_tokens`, `enable_thinking`, `thinking_budget`. Only through these does the tuned op-temp AND `presence_penalty: 0.0` (which lets suffix decoding engage — a nonzero one trips the fallback) actually reach the model. (OWUI's `_family_defaults.py` VENDOR_RECOMMENDED is only a cross-check reference — e.g. qwen3 presence_penalty 1.5 — NOT what we deploy; `models_config.json` overrides with our tuned values.)
- **registration-only** (vscode, zed): declare model + context + capabilities only — their config formats can't carry sampling. mlx-serve holds NO per-model sampling defaults (verified), so these run at the mlx_vlm worker's DEFAULT sampling, NOT the tuned config.

**NOTE-TO-SELF — a per-model config change must hit EVERY carrier, then audit for drift:**
- **Sampling / thinking** (temp, top_p, top_k, min_p, penalties, budget): update ALL THREE carriers — `opencode_config/opencode.json`, `aider_config/aider.model.settings.yml`, AND `openwebui-init/models_config.json` (then `publish_models.py` pushes OWUI); keep them consistent. (Audited 2026-07-08: all three identical + latest — Ornith t0.4 / distill t0.3, top_p 0.95, top_k 20, min_p 0.0, presence_penalty 0.0, max_tokens 102400, thinking_budget 81920.)
- **New model / context / capabilities**: update all five configs (each lists models) + `main_models.yaml`.
- **KNOWN GAP (vscode + zed only):** their formats carry no sampling, so the tuned op-temps + `presence_penalty 0.0` don't reach them (worker defaults → suffix may silently fall back). Proper fix: registry-side default sampling in mlx-serve (per-model `temperature`/`top_p`/… in `main_models.yaml`, applied when a request omits them) — NOT YET BUILT.

## Logs

`logs/{mlx_vlm,task_model,main_model,compose}.log`.

## Mission & priorities

- Goal: evidence-based pick of a local LLM for 256K-context agentic coding on a 64GB Mac, plus methodology/techniques transferable to future H200/B200 work. Phase 1 = Selection (capacity → retrieval → reasoning → coding → tool-calling at baseline). Phase 2 = Optimization (quality-neutral perf levers on the winner).
- Bias QUALITY over speed/cost. When in doubt, do the more rigorous thing.
- Hard gates: memory ≤46GB MLX-peak @256K (≤56GB browser-closed), metric = `mx.get_peak_memory` (prefill spike), NOT RSS. Every lossy lever ≤5% quality drop, measured OFAT. Effective-context threshold = accuracy ≥0.85; keep retrieval-depth and reasoning-depth curves SEPARATE. Report prefill-TTFT and decode-tok/s separately (the router metric conflates them).
- For every result, LOG THE BOTTLENECK/MECHANISM (compute vs bandwidth, which memory pool). Verdicts are HW-specific; mechanisms transfer.
- Current phase: coding is the open differentiator (BFCL/LCB/SWE). Front-runners gemma-OptiQ-4bit (fast MoE) vs Qwen3.6-27B(-distill) (dense). Live work = EpiCache ≤5% gate and a fair coding H2H.

## Operating rules

- ONE resident model per machine, always. RAM-constrained. Unload between models: `POST /v1/models/unload {"model":...}` + `pkill -f bench.run_*`. Never two big models on one box.
- M2 Max = local 64GB dev laptop (repo `$STACK_REPO`); co-resident with the AI session (~22GB), so capacity is UNRELIABLE >192K (system-memory backstop crashes the worker). Run high-context/capacity on M5.
- M5 Max = remote 64GB target box, faster. `ssh $REMOTE_HOST` (user `$REMOTE_USER`, repo `$REMOTE_REPO`). Non-interactive ssh has a bare PATH — prepend every remote cmd with `export PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH`. M5 has no `.env`, but an `HF_TOKEN` is exported in `~/.zshrc` — non-interactive ssh does NOT source `.zshrc`, so cached models load fine token-less BUT downloading a new/ungated model unauthenticated hits HF rate limits; load it first with `export HF_TOKEN="$(zsh -ic 'print -rn -- $HF_TOKEN' 2>/dev/null)"` (export it, don't pass via argv; never print/commit the value). M5 keeps an UNCOMMITTED local registry entry for the distill — never commit local hf_paths; preserve `main_models.yaml` when syncing: M5 has `pull.rebase=true`, so a plain `git pull` ABORTS on the dirty local registry — back it up, then `git fetch origin main && git merge --ff-only origin/main` (a FF leaves the dirty registry untouched since campaign commits don't modify it), and `git submodule update --force` only if the submodule pointers actually changed.
- Router (re)start recipe (per box): `cd <repo> && set -a; . ./.env 2>/dev/null; set +a; MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start >logs/main_model.log 2>&1 </dev/null &` → :8000. Run the lean router (no OWUI/docker) for benchmarking.
- After a crash the router may report a model "ready" with no live subprocess → 500s. Restart the router to clear.
- Monitoring: foreground `sleep` is blocked. Launch long runs detached on the box (`nohup … </dev/null &`), poll from a LOCAL background poller (run_in_background) checking the result file + `pgrep` liveness. Bench runners print per-rung only at the end — watch `logs/main_model.log` completion lines for live progress.

## Measurement discipline (READ before any A/B)

- THINKING IS ENABLED FOR ALL TESTS. It is the daily-driver reality. NEVER disable thinking to "make a benchmark work." Hitting the `thinking_budget` (or truncating mid-`<think>` against a `max_tokens` cap) is a FAIL signal to INVESTIGATE, never a solution and never "fixed" by lowering the budget. Convergence rule: `converged = (finish_reason=="stop" AND completion_tokens < thinking_budget)`. `finish=="stop"` alone is a FALSE PASS (budget-hits force an EOS).
- THINKING-BUDGET IS EXTERNAL TRUNCATION, NOT A MODEL KNOB. mlx_vlm's `ThinkingBudgetCriteria` force-injects `</think>` at the cap; the model never sees the budget and CANNOT "expand to fill" it. So a budget-hit means exactly one thing — the model did not self-terminate = NON-CONVERGENCE. Bumping the budget does NOT fix non-convergence (it only moves the clip point); set it as GENEROUS FIXED HEADROOM (high enough that a converging trace is never clipped — e.g. Qwen 81920), never as a tuning knob. PROVEN: gemma-MoE OptiQ-4bit LCB 16384→32768 left convergence equal/worse (11/15→8/15) and pass@1 flat (~80%), just revealing longer-but-still-truncated traces. Corollary: NEVER compare runs that differ ONLY in budget — the model ignores it, so any convergence/pass@1 delta is single-sample temp-0.7 noise, not a budget effect.
- THE KNOB FOR NON-CONVERGENCE IS TEMPERATURE, not budget (established: gemma degenerate-loops at temp 1.0, converges at 0.7 — see Known pitfalls). When a model persistently hits a GENEROUS budget, run the **TEMPERATURE-LADDER RECIPE** below. It is the STANDING, REPEATABLE per-model process — apply it identically to every new candidate that won't converge, so results are comparable.
  - GOAL: find the HIGHEST temperature that reliably converges WITHOUT a pass@1 regression. Quality (pass@1) is the HARD CONSTRAINT (goal #1); convergence / reasoning-efficiency is the secondary objective (goal #2), optimized STRICTLY within it — NEVER trade pass@1 for convergence. We hunt a KNEE (a dramatic drop in median reasoning tokens / jump in convergence, e.g. ~8k→4k), NOT subtle differences.
  - PROCEDURE: OFAT — hold everything (same items, fixed GENEROUS budget headroom via the `coding` profile) and vary ONLY temperature via the provenance-tracked `--temp` override (`bench/model_params.py`, `run.py`; each rung auto-clean-stales + is archived per-temp). Coarse grid 0.7→0.5→0.3; add ONE intermediate rung only if a big jump appears between two rungs. Per rung record {median reasoning tokens, convergence rate, pass@1} on the SAME items. N=15 single-sample resolves a DRAMATIC knee but NOT subtle (~±13pp) differences — do not over-read small deltas (0.5 vs 0.6 is noise).
  - DECISION: pick the HIGHEST temp that clears the convergence bar AND holds pass@1 vs the baseline temp. No knee → record the highest reliable temp as-is.
  - WATCH-POINTS: (1) reliability is often NON-MONOTONIC — too-low temp re-introduces GREEDY repetition loops (`finish=length` near `max_tokens`), so it's a sweet spot, not "lower is always better"; check BOTH ends. (2) The result is MODEL/QUANT-SPECIFIC — re-run the ladder per candidate; never globalize one model's temp.
- APPLES-TO-APPLES IS MANDATORY. Any comparison (especially speed/latency/memory) must be SAME BOX, SAME SESSION, SAME CONFIG. Cross-box (M2 vs M5) and cross-session/stale baselines are INVALID — re-measure the baseline alongside the test. (A "2.4× EpiCache win" was M2-ON vs a stale M5-OFF baseline; the real same-box number was ~1×.) Record box + config + EpiCache-on/off + params with every result so it is auditable.
- WHEN RESULTS CONTRADICT PUBLISHED/KNOWN RANKINGS, SUSPECT OUR HARNESS FIRST, not the model. (A coding H2H "inverted" published rankings — the cause was a harness token cap + wrong eval mode, not the models.) Inspect raw model outputs; near-zero or surprising accuracy means template/mode/parse mismatch, not capability.
- Match each model's intended eval MODE. Tool-calling: native function-calling (FC) mode, not prompt-mode text — prompt-mode disadvantages models with native tool_calls and is not what public leaderboards use. Verify token caps are generous enough for a thinking model to finish reasoning AND answer (bfcl hard-caps generation at min(4096) — raise it).
- Production params verbatim, never greedy/neutral defaults: use `bench/model_params.py:params_for(model)` (≡ `opencode_config/opencode.json`). Vary ONLY the param under test. temp 0.7 means single-sample runs carry variance — use for RELATIVE comparison, not absolute leaderboard parity.
- ALWAYS use a model's FULL registry name — in reports, results, docs, AND commits. NEVER a shorthand ("qat-6bit", "the OptiQ", "the MoE", "8bit"). The candidate field is full of near-collisions across arch / bit-width / packager — e.g. `gemma-4-26B-A4B-it-QAT-MLX-4bit` (MoE, 4-bit, lmstudio) vs `gemma-4-31B-it-qat-6bit` (dense, 6-bit, mlx-community); multiple `OptiQ-4bit` / `6bit` variants exist across `gemma-4` and `Qwen3.6`. A shorthand is ambiguous (a "QAT < OptiQ" reading already got conflated this way). Disambiguate arch (dense vs MoE) and bit-width explicitly when comparing.
- Capacity metric = `mx.get_peak_memory` (prefill spike). Rejected: system-used minus baseline (contamination-prone) and psutil RSS (under-counts Metal). Keep the box quiet during a capacity run.
- Instrument by axis: recall/reasoning → exact-match; code correctness → execution-gated; subjective quality → blind mixed-family judge panel over execution-PASSING outputs only (not a correctness oracle). Always start a real benchmark with a tiny smoke (`--limit 5`) to confirm the integration before the full run.
- Two-phase harness (`benchmark/`): `generate` (slow, resumable, writes per-item jsonl) → `grade` (fast, mechanical, no model), over HTTP against :8000. `--order roundrobin` keeps partial runs balanced.
- EvalPlus coding grading (`grade_evalplus`) runs the OFFICIAL evaluator IN DOCKER (`ganler/evalplus`, `--platform linux/amd64` under OrbStack/Rosetta on these arm64 Macs). Required because evalplus's `reliability_guard` calls `resource.setrlimit` in a way macOS rejects ("current limit exceeds maximum") — it crashes natively but runs clean in the Linux container (which also isolates the executed code). evalplus asserts ALL dataset problems are present, so a small-N subset is PADDED to the full set with failing dummies, the evaluator runs, and pass@1 is read for ONLY the generated subset from the per-problem `*_eval_results.json` (`eval[task_id][0].base_status/plus_status`; headline acc = the stricter `plus`). The `-v` host mount MUST be absolute (a relative path becomes a docker named volume → empty `/work`). LiveCodeBench uses `lcb_runner` directly (no docker); EvalPlus is the docker case.
- Results & rankings for every candidate live in `docs/campaign-results.md` (living doc): per-arch sampling configs + rationale, the pass@1/convergence scoreboard, and methodology/validation notes. This is the campaign's running record — UPDATE it as each model/tier completes (append rows; never prune a model on partial results).
- The DURABLE WORK QUEUE lives in `docs/campaign-queue.md`: the live per-box worklist (running / queued / blocked-on-prep) plus a reboot-recovery procedure. Nohup'd drivers + monitors do NOT survive a reboot (per-item results jsonls DO and resume) — so KEEP THIS FILE CURRENT as work moves, and after any reboot relaunch the `[RUNNING]` drivers from it.

## Implementation & code workflow

- **No PII in the repo — it is PUBLIC.** Never commit absolute home paths, host aliases or hostnames, usernames, tokens, or emails (in docs, scripts, configs, results, or any file content — and not just the working tree: history too). Machine-local values live ONLY in `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh` (one per box; committed template `config.example.sh`); scripts source it. Committed files use placeholders (`$STACK_REPO`, `$REMOTE_HOST`, `$REMOTE_USER`, `$REMOTE_REPO`, `$REMOTE_HOME`, `$DISTILL_MODEL_PATH`) and relative paths (`../mlx-vlm`). Sanity-check the staged diff for `/Users/`, `/home/`, ssh aliases, and usernames before every commit; if PII reaches history, scrub with `git filter-repo --replace-text` (preserves commits, rewrites content) + force-push.
- Edit the PARENT forks, not the `src/*` submodules: `../mlx-vlm`, `../mlx-serve`. Deployed code runs from the stack's `src/mlx-*` submodule. Flow: edit fork → commit → push the fork's `origin` main → bump submodule in the stack → boxes `git submodule update --force`. Test the fork directly via `PYTHONPATH=../mlx-vlm …` (its `.venv` imports the parent fork). For quick validation you may scp a changed file into a box's submodule (uncommitted, temporary), then commit properly.
- Propose before fixing/committing/pushing. Diagnose freely, but present fix proposals for approval before editing/committing/pushing; an approved plan does not cover newly found bugs. Commit/push only when asked. Write commit messages from `git diff --staged`, not stale in-session reads.
- TDD for features/bugfixes: failing test first, watch it fail, minimal code to pass.
- Venvs: `.venv-bench` = mlx+pytest+json_repair, NO `mlx_audio` (epicache/unit tests run here; `test_server.py` won't collect). `.venv` / `../mlx-vlm/.venv` = full deps. bfcl-eval installed in `.venv-bench` on both boxes.
- Bench tooling must lazy-import heavy deps, graceful-degrade (write `skipped/acc:null` + note, never crash the batch), and be mocked in tests.
- Commit prefixes (observed): `chore(stack): bump src/mlx-vlm -> <sha> (<summary>)`, `feat(bench)`/`fix`/`docs`.

## Known pitfalls (don't re-learn these)

- Suffix/MTP/draft speculative decoding is INHERENTLY non-lossless on bf16 (kernel numerics flip greedy argmaxes) — proven not a logic bug; MTP is a net slowdown. Campaign runs suffix-OFF; don't re-chase as "bugs."
- `prefill_step_size` must be threaded into generation, else runtime defaults to 2048 → 4× QK² scratch → 256K OOM. EpiCacheKVCache does NOT support the batched `/v1/completions` path (single-sequence only).
- Quant sensitivity is real, not architectural: gemma recall is QUANT-sensitive (OptiQ-4bit recalls where QAT-4bit doesn't). Converted/MTP-packaged quants need loader tolerance (mtp-key strip + vision-tower tolerance).
- M5 Neural Accelerators: dispatch never selects them — dead end until a new mlx release. Don't pre-dismiss small expected gains otherwise; let the harness quantify (skip only true mechanism category-errors).
