# Handoff — 2026-10-06 (00:20 UTC): M57 ADOPTED and SHIPPED (fused attention + lazy embeddings, first pick, provisional); everything pushed; stack down

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (the only queue; M57 COMPLETE, M58 queued) and `docs/open-questions.md`
(C115 ruled). M57 record: `docs/campaign-results.md` 2026-10-05, `docs/proposal-flash-attention.md`, `docs/specs/m57-*.md`.

## What M57 established (first pick `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; qualified, two order-balanced sessions)

- `fused_v1` vs `auto`: prefill −14.6 % at 128K, −24.9 % at 256K; peak −3.21 / −6.49 GB; with lazy embeddings the peak is flat at
  37.97 GB from 8K to 256K. Decode, retrieval, MTP acceptance unchanged; coding axis +2 pp / 0 (n=100 per session, within tolerance,
  not proven equivalent); long-context retrieval and chain-4 reasoning 12/12 in every session; lazy embeddings byte-identical on
  200/200 coding outputs; AgentBench 5-item smoke identical across arms; vision gate 20/20 in the adopted state.
- Mechanisms: a 128K prefill is 44 % attention, 34 % MLP, 17 % GatedDeltaNet — fused attention is a 1.5× kernel, not a 2× lever;
  the served peak under `auto` was unfused score scratch (≈ 1.23 score tensors of the largest unfused chunk) plus the whole-prompt
  embeddings; `force_fused` raises at query lengths 6–8 and loses below ≈ 128 queries, hence the shape-aware policy; chunk 1024 buys
  nothing on the linear part; decode at long context is the MTP verifier reading the cache up to three times per round (M58).
- Neither agentic harness reaches long context (opencode ≤ 27.8K, AgentBench OS ≤ 3.8K): the gain lands on long daily-driver sessions
  and on memory headroom. Warm-state drift (AGENTS.md rule): compare latency arms only in matched machine state.

## State of the world (end of session, 2026-10-06 00:20 UTC)

- **Everything is pushed.** Stack `main` = `origin/main` = `d92c741`; fork `mlx-vlm` `main` = `fbe2775e`; fork `mlx-serve`
  `main` = `7be6bfd`; submodule pointers on the remote match. Tree clean except the operator's untracked `ts.md`.
- **Stack is DOWN** (operator instruction stands: do not auto-start `runserver.sh`). Docker (OrbStack) was started by the operator
  for grading and is still up. Power 140 W.
- **M57 is ADOPTED and SHIPPED (C115, PROVISIONAL).** The first pick's registry entry carries `attention_policy: fused_v1` and
  `lazy_prompt_embeddings: true`; the daily driver picks them up at its next start. Every manifest written from now on is
  fingerprint v7 with both controls; pre-M57 first-pick rows do not pool with post-M57 rows (serving-path hash and policy both
  changed) — expected, not a bug. Record: `docs/campaign-results.md` 2026-10-05 (four entries), `docs/proposal-flash-attention.md`,
  `docs/specs/m57-*.md`.

## Leftovers, in priority order

1. **First daily-driver start under M57 is unverified.** The shipped state was verified on a LEAN router (`MLX_VLM_CACHE_SESSION_MAX=1`).
   `runserver.sh` runs `=2` with OWUI and the task model; nothing in M57 depends on session count, but the first real session should
   check the worker command line (`--attention-policy fused_v1 --lazy-prompt-embeddings`), one `Request completed` log line with
   `sdpa_forced` > 0 on a long prompt, and a vision turn through OWUI.
2. **Certification debt on the shipped state:** the judge panel (M38/M40 style) and Math500 were NOT re-run under M57; native16 itself
   (C81) is still provisional on the broader axes. One re-run on the FINAL state (native16 + M57) rather than two.
3. **M58 — joint MTP verification scan** (queued, spec owed): the verifier in `mlx_vlm/models/qwen3_5/speculative_verifier.py` attends
   blocks longer than 2 as separate single-query calls; a joint call is bit-identical at kernel level and saves ≈ 28 % of
   verification attention (estimate +14 % decode at 128K). Gate 1 = byte-identical outputs within one loaded instance.
4. **Harness gaps found, not fixed:** `benchmark/vision_gate.py` writes an unscrubbed absolute `corpus` path into its manifest (the
   adoption manifest was hand-scrubbed; the PII hook caught it); `run_dsh_probe.py` has no M50 check; capacity-ladder rows do not
   carry the `sdpa_*` counters; `generate` rows leave `content_sha256` / `reasoning_sha256` unset (identity checks must use the
   content); pair-publication residuals (`docs/handoff.md` previous entry; Codex review 10 in `$STACK_WORKDIR/m57/`).
5. **Unresolved observation:** branch `auto` ran 1.4–3.6 % slower than the previous shipped code at 64K–256K in both adjacent
   comparisons (under the 5 % flag). Could be machine state or a small default-path overhead (profiler hooks / policy checks); a
   profiled A-vs-shipped pair in matched state would settle it. Moot for the first pick (it ships `fused_v1`), relevant for any
   other model served by the bumped fork under `auto`.
6. **Suggested `AGENTS.md` additions** (operator owns that file; 7 bytes of headroom were freed by the trim): PYTHONPATH runs are
   probes, never graded (the harness hashes `src/*`); a 10-minute idle does not reset a multi-hour campaign — only the
   order-balanced comparison is valid.
7. Candidates not queued: dense prefill path (dequantise-then-dense at chunks ≥ 2048; ≤ −8…14 % TTFT); fused-kernel tuning
   (≲ 20 %); P41 watch-list (open HySparse2-class checkpoint); P42 harder long-context benchmarks. M56 stays PARKED (C110).
8. Workdir: `$STACK_WORKDIR/m57/` holds every script, overlay, Codex review (1–12), microbench JSON, profile and run log of this
   milestone; `qual2/collided/` holds the archived double-launch rows. Agent worktrees under `.claude/worktrees/` can be removed.

## Rules learned this session

- Read the kernel dispatch source and measure before designing around a flag: the "3.1×" was a cold-buffer artifact, and three
  claims in the first design were wrong.
- A memory instrument must show its known positive first (`get_active_memory` still counts a just-released buffer).
- A single back-to-back latency pair is order-biased on this laptop (E15) — matched state or no delta.
- Process-pattern checks bit three times in one campaign (a gate matching an idle app helper, a waiter matching itself, a guard
  counting its own launching shell): match on the executable and exclude your own pid, and never launch by hand while a waiter
  may still be alive — verify zero runner processes first.
- Smoke every runner script end to end on a real router before a multi-hour run (an import-path bug cost a session).
- `scripts/stack_stop.sh` kills ANY process whose command line matches the worker pattern, including a Codex review whose prompt
  was passed as an argument. Pass review prompts on stdin (`codex exec … - < prompt.md`); don't stop the stack while reviewers run.
- The worker's stderr log (`$TMPDIR/mlx-manager-logs/<model>.log`) is recreated at worker start — read the whole file per arm.
- Profiled or fork-branch runs write to the workdir only; nothing from them enters `benchmark/results/`.

Next decision id C116; discussion ids continue from P88.
