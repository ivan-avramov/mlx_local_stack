# Handoff — 2026-10-05 (01:15 UTC): M57 build review-complete (fork + router SHIP on branches, stack merged locally); qualification design awaits sign-off; push NOT approved

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/proposal-flash-attention.md` (the whole M57
record: proposal → reviews → design P25–P44 → reviews 2/3 → reconciliation → evidence E1–E15 with P65–P75), `docs/PLAN.md` (M57 row),
`docs/specs/m57-attention-policy.md` (build spec, AC1–AC12) and `docs/specs/m57-prefill-profiler.md`.

## State of the world

- **Git (stack):** pushed through `bd2823d`; everything after is LOCAL ONLY (handoff, M57 docs, specs, probe rows, AGENTS.md rule).
  Push needs the operator's word.
- **Fork `../mlx-vlm`:** branch `m57-prefill-profile` @ `21d62fe6` (4 commits on `main` `1bd249d3`; env-gated prefill component
  profiler; 71 CPU tests; three cold-review rounds by a Claude reviewer and Codex `gpt-6-astra`; live gate passed). NOT pushed, NOT
  merged, submodule NOT bumped. The fork's working tree is left on that branch. `../mlx-serve` untouched.
- **Stack is DOWN by operator instruction: do NOT auto-start `runserver.sh`.** :8000 free, no router/worker. 140 W, battery 100 %.
- **Picks unchanged.** `main_models.yaml` untouched.
- Workdir `$STACK_WORKDIR/m57/`: microbench scripts + JSON, `probe/` (128K overlay probe, MTP round profile), `profile/` (component
  profiles, three runs), `overlays/step{512,1024}.yaml`, Codex prompts/reviews 1–4, `transcript_accounting.{py,json}`.
- `ts.md` at the repo root is the operator's untracked video transcript — not committed.

## What the evidence says (first pick `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, native16, MTP ON; all PROBES, one session per arm)

- Fused attention is NOT a 2× lever. At 128K, fused chunks give −16 % (warm vs warm) to −22 % (cool vs cool) TTFT. A 128K prefill is
  44 % attention, 34 % MLP, 17 % GatedDeltaNet; below 32K the weight projections (quantized matmuls) are nearly everything.
- Memory is the stronger benefit: the served peak tracks ≈ 1.23 score tensors of the LARGEST UNFUSED chunk (confirmed by a 1.71 GB
  rise when the tail grew from 512 to 734 queries). Predicted with a tail-fusing policy: −3.9 GB at 128K, −7.9 GB at 256K.
- Fused is 2.6–14× closer to an fp32 reference than the unfused bf16 path served today.
- `force_fused` raises at query lengths 6–8 and is slower below ≈ 128 queries → policy `fused_v1` in the build spec.
- Chunk size 1024 does not speed up MLP / GatedDeltaNet per token; without a tail policy it RAISES the peak.
- Decode at long context is the MTP verification forward (91 % of a round at 128K). A joint verification scan is bit-identical to
  the per-query pattern at kernel level; estimate +14 % tok/s at 128K. MLX's vector kernel is already at memory bandwidth.
- Neither agentic harness reaches long context (opencode max 27.8K, AgentBench OS max 3.8K): the time benefit lands on long
  daily-driver sessions and capacity.
- Warm-state drift (new AGENTS.md rule): ≈ 20 % slower prefill work when a run follows a five-minute GPU load; compare latency arms
  only in matched state with a ≥ 10 min cooldown.

## In flight / pending

1. **M57 build (C112).** Spec `docs/specs/m57-attention-policy.md` (+ Amendments 1, 2). Nothing merged, nothing pushed.
   - Fork `../mlx-vlm` branch `m57-attention-policy` @ `fbe2775e` (on top of the profiler branch): policy `fused_v1`, counters in
     HTTP timings, startup self-test, lazy embeddings behind `--lazy-prompt-embeddings`. Cold reviews: SHIP (3 rounds). Full fork
     suite 5309 passed. Live gate PASSED (self-test 12 forced calls; cold 20819-token prompt `sdpa_forced=656 / sdpa_auto=16`; all
     requests 200). GPU parity gate AC12 PASSED 24/24 cells (`$STACK_WORKDIR/m57/ac12_parity.run1.json`).
   - Router `../mlx-serve` branch `m57-attention-policy` @ `7be6bfd`: registry fields `attention_policy`,
     `lazy_prompt_embeddings`. Cold reviews: SHIP. 152 tests.
   - Stack: MERGED into local `main` as `601979e` (fingerprint v7 with `attention_policy` + `lazy_prompt_embeddings`, strict
     serving-state refusals, worker identified as the `mlx_port` listener descended from the router, prechecks in
     `run_capacity` / `run_retrieval` / `run_reasoning`, staged result + manifest publication with `result_sha256`). Six review
     rounds; the last commit (`396319a`, pair publication) was read and suite-checked by the session, not cold-reviewed. Full
     suite on merged `main`: 2705 passed, 1 known failure (twice); `test_work_queue::test_PAUSE_logs_…` failed once in four
     full runs and passes alone — an order-dependent flake, not investigated. Live resolver check passed (registry fallback /
     worker / mismatch refusal). The agent worktree `.claude/worktrees/agent-a6011ca833d3e6e68` can be removed.
   - Qualification design APPROVED (C113). Next:
     `docs/specs/m57-qualification.md` → pilots → arms (matched machine state).
2. **M58 queued** (joint MTP verification scan) — spec owed after M57.
3. **Push: NOT approved** (operator undecided). Recommendation on record: push the stack docs commits when convenient; do NOT
   merge fork branches into fork `main` or bump submodules until M57 qualifies — one serving-path hash change, not two.
4. **Found, NOT fixed (operator go needed):**
   - `test_m50_entrypoints::test_run_opencode_probe_refuses_before_the_manifest` fails on `main` — since `3948528` the opencode
     probe creates its scratch directory BEFORE the M50 refusal.
   - The C35 `draft_kind` tripwire raises a plain `RuntimeError` that `generate.py` swallows ("never block a run on provenance"):
     a predictor-state mismatch does not stop a `generate` run.
   - `run_capacity`, `run_retrieval`, `run_reasoning` never call the M50 router check (`assert_served_config`); only `generate`,
     AgentBench, the session-cache probe, the stack smoke and the parity replay do.
5. Not queued: dense prefill path (dequantise-then-dense at chunks ≥ 2048). Carried: P41 / P42 into `docs/open-questions.md`?
   M56 stays PARKED (C110).

## Rules learned this session

- Read the kernel dispatch source and measure before designing around a flag: the "3.1×" was a cold-buffer artifact, and three
  claims in the first design were wrong.
- A memory instrument must show its known positive first (`get_active_memory` still counts a just-released buffer).
- A single back-to-back latency pair is order-biased on this laptop (E15) — matched state or no delta.
- `scripts/stack_stop.sh` kills ANY process whose command line matches the worker pattern, including a Codex review whose prompt
  was passed as an argument. Pass review prompts on stdin (`codex exec … - < prompt.md`); don't stop the stack while reviewers run.
- The worker's stderr log (`$TMPDIR/mlx-manager-logs/<model>.log`) is recreated at worker start — read the whole file per arm.
- Profiled or fork-branch runs write to the workdir only; nothing from them enters `benchmark/results/`.

Next decision id C114; discussion ids continue from P82.
