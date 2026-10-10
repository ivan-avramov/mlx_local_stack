# mlx_local_stack

Select local LLMs for 256K agentic coding on the M5 Max 64GB; prioritize quality over speed/cost. Phase 1 selects; Phase 2 optimizes. Record bottlenecks/mechanisms for hardware-specific findings and transferable methodology.

## Authority and required reading

- This file overrides conflicting project docs. Date corrections when authorized.
- Before campaign work, read `docs/handoff.md`, then `docs/PLAN.md` (sole queue; no JSON mirror) and `docs/open-questions.md`. Rewrite the one handoff each session; add judgement calls immediately to open questions; retain closed items.
- Before benchmarks/analysis, read `docs/metrics.md`, `docs/box-notes.md`, `benchmark/README.md`, and `docs/regrade-vs-rerun-guideline.md`. Regrade; rerun only what regrading cannot recover.
- Before serving/configuration changes, read `docs/serving-path.md` and `docs/box-notes.md`. Current picks/evidence: `README.md`; deployed parameters: `main_models.yaml`. Never restore historical defaults. Index: `docs/README.md`; results: `docs/campaign-results.md`; history: `docs/lab-notebook.md`.

## Development and safety

- Obtain approval before non-trivial implementation; newly discovered bugs need their own proposal. Commit coherent approved work autonomously. Never push without explicit in-turn approval. Derive messages from staged diffs; prefixes: `feat(bench)`, `fix`, `docs`, `data(bench)`, `chore(stack)`.
- Edit parent forks `../mlx-vlm` and `../mlx-serve`, never `src/*`. Commit/publish forks before bumping submodules; push approval still applies. Test via `PYTHONPATH=../mlx-vlm`; synchronize with `git submodule update --force`.
- Features/bugfixes: failing test first, then minimal fix. Lazy-import heavy dependencies; mock tests; unavailable dependencies yield `skipped/acc:null` with explanation. Transport failures must abort.
- Public repo: no PII, credentials, absolute home paths, hostnames, usernames or emails, including history. Use placeholders; machine-local values belong in `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh`.
- Out-of-repo artifacts belong under `$STACK_WORKDIR`. Exceptions: `~/.cache/huggingface`, `~/.cache/livecodebench`, uv/venv caches, `$TMPDIR/mlx-manager-logs`. Verify redirecting process environments before writes; missing redirection is a blocker.
- Never open live container SQLite databases from the host. Use HTTP APIs or query a separate copy including DB/WAL/SHM.
- Use full registry model names in reports, docs, results, chat and commits, including first use per message/body. Keep naming/PII hooks enabled. PII in history requires filter-repo cleanup; force-push still requires approval.

## Runtime

- Single box, driver and worker; one resident model. Unload between models via `POST /v1/models/unload`; stop obsolete benchmark processes by PID.
- Never change serving configuration during live runs. Stop via `scripts/stack_stop.sh`; verify :8000 free before restart, new router ownership afterward, and zero surviving `session_cache_probe`/`opencode run` processes before another probe. Record worker cmdline (`--model`/`--draft-kind`). Verify processes, never infer termination; restart ghost-ready routers after crashes.
- Benchmark routers: lean, no OWUI/docker, `MLX_VLM_CACHE_SESSION_MAX=1`; daily driver: `=2`. Keep `APC_ENABLED` absent; verify router/worker environments. Suffix stays OFF.
- Keep structural `kv_prealloc_tokens=max_kv_cache_size`; never lower active allocation. Honor `cache_session_shrink` only while idle; restore full preallocation before writing. Thread `prefill_step_size` into generation; EpiCacheKVCache is single-sequence.
- Launch long runs detached; use background waiters, no foreground sleep. Use Python subprocess timeouts or `--probe-timeout`, not unavailable macOS `timeout`/`gtimeout`. Preserve exit codes; never mask queue failures with `|| true`, `if !` status capture or pipelines. zsh does not word-split unquoted variables.

## Registry and clients

- Registry holds current B/C top-two picks. Update it with certification/pick changes in the same commit; annotate `generation_defaults` with `CERTIFIED <milestone> <date>` or `PROVISIONAL`. Upload before promotion: public HF download plus `caslca/<full-registry-name>` insurance clone; unpublished placeholders say `NOT-YET-UPLOADED`.
- Ship certified (model, tune, predictor) triples per PLAN M6d; otherwise draft-OFF. Selection uses predictor-OFF; certify ON on every supporting axis, retain both states, ship OFF if OFF wins beyond ±5pp on any axis. Optimize in shipped state; never assume bf16 speculation lossless.
- Sampling/thinking changes update all four: `main_models.yaml` `generation_defaults`, `opencode_config/opencode.json`, `aider_config/aider.model.settings.yml`, `openwebui-init/models_config.json` (then `publish_models.py`). Model/context/capability changes also update registration-only `vscode_config/chatLanguageModels.json` and `zed_config/settings.snippet.jsonc`. Audit drift.
- Full-sampling carriers retain temp, top_p, top_k, min_p, presence_penalty, max_tokens, enable_thinking and thinking_budget. Registration-only clients inherit omitted sampling from registry defaults.
- Generate OWUI JSON/policy with `configgen`; never hand-edit. Use ordered `openwebui.models` C menu; task model active with `meta.hidden: true`; exclude other models. Enable `web_search`/`code_interpreter` capabilities/defaults and native function calling.
- OWUI settings require `init.py` HTTP reconciliation/compose environment; no seed file. Verify live API config, allowlists, defaults, parameters and routing. Native `search_web`/`fetch_url`, no forced RAG; gate: `scripts/websearch/owui_e2e_gate.py`.
- opencode is primary (v2 probe `run_opencode_probe_v2.py`; the 1.18 probe is frozen 2026-10-07, rows retained); aider harness retired, rows retained, runner frozen. Daily: the generated v2 client config removes `opencode.config.compatibility`; probes: the hermetic v2 env (P149). Record skill policy/config hash; never pool across scaffold changes.

## Benchmark validity

- Use deployed parameters via `params_for(model, profile="deployed")`; explicitly pass `--sampling-profile deployed`. Match box/session/config, remeasure baselines, vary only the tested parameter; record provenance.
- Thinking always ON; generous fixed budget, never tuned. Investigate hits with the per-model temperature ladder, never budget reductions or presence penalties. Preflight available generation headroom; convergence requires `finish_reason=="stop"` AND tokens below the resolved budget. Use `convergence.resolved_thinking_budget`; keep its 0.8 clamp aligned with the fork.
- Every driver exports served `MLX_SERVE_CONFIG`; verify PID environment and first manifest's `runtime.draft_kind`/`registry.sha256` before item two.
- M50: before any read/write/request, refuse unless the sole local router-port owner is mlx-serve with its config (resolved against its cwd/HOME) matching driver `paths.registry_path()`; missing files/owners or remote hosts refuse. No bypass. Record `router.pid`, `router.config`, `config_sha256`, resume `router_history`; opencode probes verify their own provider baseURL. Reverify PID/hash at exit; drift stamps `served_config_drift`, exits nonzero. Archive/regenerate false-provenance or drifted rows; never grade/pool them. Exception (C114): opencode's own data-home write in the probe's one pre-check discovery call. v2 probes (M59/M61) may set `OPENCODE_CONFIG_DIR` to the bench-owned dir holding exactly one generated v2 carrier (optionally with the recorded `agents.build.system` overlay from `benchmark/opencode_prompts/`) and `noretry.js` by sha (tg1: plus `toolbounds.js` by sha), and `OPENCODE_CONFIG_CONTENT` to exactly the per-item seed overlay; `OPENCODE_CONFIG` stays refused.
- Never pool differing caps, predictor states or fingerprints; check existing caps before resume/`--clean-stale`. Explicit paired seeds via `rowschema.sample_seed`; pilot-twice certifies only one loaded instance. Agentic chains require k=2 independent loaded instances, distinct paired schedules plus same-seed reload control; pair accuracy per session, never pool.
- Start with `--limit 5` smoke. Before n≥40 enters queue, run five seeded-random corpus items, not first items. Estimate from mean/max as lower bounds plus heavy-tail allowance. Generate→grade over HTTP, `--order roundrobin`.
- Derive client timeouts from max generation/floor decode rate plus headroom; retries=0. HTTP/transport errors abort nonzero, never grade. Silent/BUSY: don't kill; silent/IDLE: verify wedge, kill by PID.
- Every run needs a daemon (`benchmark/m1/bench_watch.py` or equivalent) logging every five minutes: item progress, mean-based ETA versus prediction, errors/convergence/token distribution, and whether correction beats finishing.
- Before kernel experiments, read the Neural Accelerator correction in `docs/lab-notebook.md` (2026-08-31): active by default; fp16/fp32 ratios cannot detect them. Quant sensitivity is model/quant-specific; converted/MTP-packaged quants need loader tolerance.
- Capacity: quiet box, `mx.get_peak_memory` prefill spike, never RSS/short-generation peaks. Roughly 48GB at 256K is guidance, not rejection threshold; weigh pressure/stability/quality/latency.
- Latency/rates: verify `pmset -g ac` = 140 W / 28 V and battery > 20% before/during capture; monitors log both each tick. Match machine state, order-balance arms, idle ≥ 10 minutes between arms, log start state; never cite one back-to-back pair.
- Validate instruments against known positives; inspect raw outputs/harness modes before accepting surprising rankings. Report elapsed time from `ps -o etime`, never run prefixes.

## Analysis and reporting

- `acc_strict@budget` IS THE RANKING KEY at a MATCHED budget, DNF included; report `(acc, acc_strict@budget, conv%, nonconv_kinds)`. `pass@1|converged` is DEMOTED to a DIAGNOSTIC and must NEVER rank; no composites or `successes_per_hour`.
- Report capability/exclusive solves, edit competence, latency and runaway tax separately. Tax: budget-hit, turn-cap, exec-timeout flags plus deduplicated union per session; pooled rates descriptive only, no interval; wall-clock from clean-box chains.
- Deltas require intervals and axis MDE; use two-stage cluster bootstrap, not pooled Wilson; Holm across families, TOST ±5pp for equivalence. Lossy levers: ≤5% quality drop OFAT. Effective context: accuracy ≥0.85; separate retrieval/reasoning curves and prefill-TTFT/decode-tok/s.
- Recall/reasoning: exact-match; code: execution; subjective quality: blind mixed-family panel over execution-PASSING outputs. Execution accuracy is not code quality.
- Each completion/regrade updates README ranking/evidence tables (≤4 entries/ladder, “Best for”, uncertainty, per-language/session evidence, coverage/provisional/pending labels). Report status, mechanisms, trends and B/C implications with explicit recommendation. Inconclusiveness alone never drops candidates or excuses avoiding a choice; prioritize quality, label trend-based choices provisional. Changes to picks/order require operator approval; evidence updates do not.

## Entry points

- `/mlx start` → `./runserver.sh`: backup, model servers, compose, logs; Ctrl+C/TERM tears down. `do_backup.py` handles backups.
- Lean start: `set -a; . ./.env; set +a`, then `MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG=<overlay> nohup uv run mlx-serve start >logs/main_model.log 2>&1 </dev/null &`; verify ownership/environment as above.
- Router :8000; task :8092; OWUI :3000. Logs: `logs/{mlx_vlm,task_model,main_model,compose}.log`.
