# Session handover — quality-first re-plan, testbed guard rails, LCB convergence investigation (2026-06-24)

Read alongside `AGENTS.md` and the memories `project-nonconvergence-and-quality-first-replan`,
`project-256k-execution-campaign`, `project-suffix-decoding-nonlossless`,
`project-local-256k-eval-program`.

## State — all committed + pushed; both boxes synced + IDLE; routers up
- **Stack** @ `b553f19` (origin/main). **mlx-vlm** @ `ea4c635`. **mlx-serve** @ `5c5de1e`.
- **M2** (local dev, co-resident with this AI session ~22GB) and **M5** (`ssh`, remote, faster, 64GB)
  both at stack `b553f19`, routers healthy + idle, **no model loaded, no python >1GB** (verified).
- M5 keeps UNCOMMITTED local registry entries (never commit): the Opus-distill (`$DISTILL_MODEL_PATH`)
  and `Qwen3.6-27B-UD-MLX-6bit-kv16`. Sync M5 with: `git stash push -- main_models.yaml && git pull &&
  git stash pop` — AND first `rm` any scp'd untracked files under `benchmark/` that collide with newly
  committed ones (recurring scp-vs-pull abort; bit us 3× this session).

## What this session accomplished
1. **Quality-first re-plan (user directive).** The candidate search had been narrowed FIT-first
   (256K@46GB → forced aggressive 4-bit → introduced quant errors). Correct order: establish each
   model's QUALITY ceiling at the highest fidelity the box runs (8→6-bit, **bf16/8-bit KV** — KV-quant
   is a bigger quality lever than weight-quant for code), THEN optimize context/speed down to the ≤5%
   gate. NEVER prune a model on one benchmark; rank across the full suite.
2. **Testbed guard rails — built, TDD'd, committed, deployed both boxes** (suite 190 pass):
   - `benchmark/preflight.sh <model>` — fresh router + codebase-freshness + convergence **canary**
     before every run (prevents stale router/model/codebase). Run from repo root.
   - `bench/convergence.py` — `converged = finish=="stop" AND tokens < thinking_budget`; grade flags
     any looped/truncated run **INVALID** (a loop can't be silently scored). Wired into generate+grade.
   - `bench/quant_info.py` + `run_quant_info.py --scan` — full quant numbers incl param-weighted
     **effective bits-per-weight** (nominal labels mislead: gemma-OptiQ-"4bit" = 6.92 eff bpw).
   - `grade_lcb` reports **per-difficulty pass@1** (Easy/Med/Hard).
   - `bench/provenance.py` — stamps every results file with box/SHAs/eff-bits/KV/sampling/profile.
   - `--auto-restart-on-loop` + `generate.probe_with_recovery` — on a loop, restart router + retry once,
     classify **recovered** (stale router) vs **loop_persisted** (genuine quant/model loop).
   - `model_params.params_for(model, profile="official")` — official per-family sampling
     (gemma temp 1.0/rep 1.0; Qwen-coding temp 0.6/min_p 0/presence 0); production set unchanged.
     `run.py --sampling-profile official` + `--auto-restart-on-loop`.
   - **bf16-KV registry variants** (`*-kv16`, kv_bits 0): Qwen-8bit, gemma-31b-6bit, gemma-MoE-8bit
     committed; Qwen-UD-6bit-kv16 is M5-local. (4-bit-KV entries kept for the Stage-3 KV ladder.)
   - **Prompt-only LCB cache** (`perf(bench)` b553f19): generation was holding the full LCB dataset
     (880 problems + private test cases, **~10GB RAM co-resident with the model**); now `_load_lcb`
     caches a prompt-only view (~2.8MB, per-release, atomic write). Cache on both boxes. Test cases
     still load at grade time (off-box). THIS resolved the ">8GB sibling" memory pressure.
   - EpiCache batched-gen B=1 fix shipped earlier (ea4c635).

## Investigation findings (the decisive ones)
- **Non-convergence had TWO causes, now disentangled:** (a) **stale-router state** amplified loops
  (gemma 60%→17% after a restart) — FIXED by preflight-restart-before-run; (b) a **residual inherent
  over-thinking on hard problems**, which differs by model:
  - **gemma (MoE + dense-31B) = degenerate VERBATIM repetition loop** (max-repeat 34–78, ~44% unique
    lines) — a genuine **defect**, prompt-INDEPENDENT (official LCB prompt didn't fix it) and
    budget-independent; auto-restart classifies these `loop_persisted`. gemma-31B-dense codes well
    (LCB ~90% pass@1 incl Hard on the items it converged) but **~25% loop rate**; gemma-MoE-8bit
    loops **~92%** of hard items → arch-limited (4B active).
  - **Qwen3.6-27B = GENUINE long reasoning** (max-repeat 2, ~99% unique lines), NOT a loop. It just
    needs a big budget — the official 3.6 rec is **81,920 tokens for hard programming problems**.
    The worst-case AtCoder outlier `abc358_e` pushes even 80K; easy/LeetCode (`3496`) converge fast
    (~9K). So Qwen "works" but is SLOW on hard problems (~15 tps dense → up to ~90 min/item at 80K).
  - **Pattern:** LCB **AtCoder/Codeforces (stdin) problems** trigger the over-thinking across all
    candidates; **LeetCode functional** problems converge cleanly.
- **3.6-specific published facts** (NOT 3.5 — that distinction matters): official LCB thinking-mode
  **removes the "return only the program" restriction** (our prompt keeps "no explanation after it" →
  diverges — adopt the official template, TODO below); code is more quant-sensitive than reasoning
  (Q8 52% ≳ Q4 51%); more output tokens ↔ lower accuracy; 3.6 SWE-bench used temp=1.0 + an agent
  scaffold (not 0.6). Qwen3.6-27B is a published flagship coder (SWE-Verified 77.2) and is expected
  to out-quality gemma-4-31b while being slower.

## Candidate quant ladder (cached, eff_bits via quant_info; all on M5)
- **Qwen3.6-27B:** OptiQ-4bit 5.06bpw/20GB · UD-4bit 4.80/26GB · UD-6bit 6.42/30.5GB · MLX-8bit 8.0/34.7GB
- **gemma-4-31B-dense:** 4bit 4.0/18.4 · UD-4bit 5.26/23.3 · 6bit 6.0/26.1 · qat-6bit 7.36/31.3
- **gemma-4-26B-A4B (MoE):** QAT/vanilla-4bit 4.64/15.6 · OptiQ-4bit 6.92/18.8 · 8bit 8.0/28
- **Opus-distill:** TeichAI BF16 55.6GB (convert to 8/6-bit), M5-local.

## NEXT STEPS (priority)
1. **Adopt the official LCB prompt in `benchmarks.build_messages`** (system msg + `### Question/Format/
   Answer` + explicit stdin framing for AtCoder; drop "no explanation after it"). 3.6-validated +
   standard-compliant. TDD. (My A/B showed it doesn't *shorten* Qwen's reasoning, but it's how 3.6 was
   officially evaluated — use it for fair, comparable numbers.)
2. **Run the STACK-RANKING campaign** (no model pruned). Per model: **3-run param hill-climb** (Run#1
   official params → Run#2 step the key knob colder/stricter → Run#3 continue if better else reverse)
   to find each model's best config, then run the suite at best. **Suite per model:** LiveCodeBench
   (per-difficulty), Aider polyglot, SWE-Verified-40, BFCL, IFEval, reasoning probes (agg/latent/
   vartrack), judge panel. **Include the Qwen quant ladder** (OptiQ-4bit / UD-6bit / MLX-8bit) — don't
   overfit UD; test prediction "more-aggressive quant → more thinking" directly on 3.6.
3. **Feasibility caveat for Qwen on LCB:** at 80K budget, ~90 min/item → LCB is slow for Qwen. Use a
   feasible N (small per-difficulty sample) and **lean on the agentic axes (SWE-40, Aider)** where
   thinking is bounded per turn and where Qwen3.6's published coding strength actually lives.
4. **Early-pruning schedule** (don't waste time): Stage-0 preflight canary gate → Stage-1 small-N
   per-difficulty screen at best params → Stage-2 full release_v5 / agentic on survivors → Stage-3
   quant+KV ladder. Grade convergence-gated; loops flagged INVALID, investigated not scored.

## Orchestration / operating notes
- **One model per box; preflight before every run; unload between.** Run from repo root.
- **Box assignment:** M5 (idle, fast, 64GB) for the HEAVY dense models (Qwen-8bit 34.7GB, distill,
  gemma-31B). M2 throttles 34GB models to ~9 tps → **timeouts** (the probe cap is 3600s) → use M2 only
  for the LIGHT/fast MoE or grading. The distill is M5-only.
- Launch detached on the box (`nohup … </dev/null &`) + a LOCAL background poller (results jsonl +
  `pgrep`); generate prints per-chunk only. Cross-box speed comparisons are INVALID — accuracy is
  box-independent (fine to compare), speed/latency must be same-box/session.
- Network to M5 dropped a few times this session (DNS for the host alias) — pollers must tolerate ssh
  failures and continue.
- Ad-hoc investigation tools committed: `benchmark/lcb_prompt_ab.py` (our-vs-official prompt A/B),
  `benchmark/lcb_budget_test.py` (thinking-budget convergence test); both cache-backed.
