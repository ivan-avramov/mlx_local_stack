# Handoff — 2026-09-23: thread-1 review executed (M45 DONE, M46 DONE, M47 pilot DONE); switchyard composition reviewed and deferred; C101/C102 filed

Read this first, then `docs/PLAN.md` and `docs/open-questions.md`. Reports this session: lab-notebook entry
"2026-09-23 (00:30–01:05) — M45"; `docs/specs/switchyard-nvsy-plan.md` §8 (2026-09-23 review).

## Operator rulings 2026-09-23

Reviewed two community threads (30-day `Qwen3.8-27B` run; "Qwen 3.8 with Claude" <!-- allow-shorthand -->).
Ruled: Switchyard escalation mode is NOT the quality gate for sw-dev work (struggle detector + one-way latch);
the frontier-driver + local-executor composition is the better one but is **DEFERRED** (note in the switchyard
doc §8); same-model reduced/medium-effort subagent roles **REJECTED** on memory; Swift-variant screen dropped
(medium tune already delivers the shorter thinking). "Proceed, keep going" on the qwen-thread items → M45, M46,
M47 pilot executed unattended.

## Runtime state

**Daily-driver stack is UP** (router on `main_models.yaml`, `MLX_VLM_CACHE_SESSION_MAX=2`, APC absent; task
model + embeddings on :8092; OWUI :3000). `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` resident (worker
pid changes; idle footprint ~23 GB). **The router logged memory-pressure CRITICAL (90.6% used, 6.5 GB free)
30× during M45 with two sessions live and the full stack resident; swap 1.9 GB.** No OOM. This is the
two-session regime C85 lived in; treat any second long-context session as at-the-edge while OWUI + task
model are resident.

## Done this session (all committed, NOT pushed)

- `e027ef6` switchyard doc §8: escalation-router mechanics (judge window 28×500 chars, `confirmations=2`,
  one-way latch, needs `x-switchyard-session-id`, only at tag `v0.2.0-rc.1`; NVIDIA: ~6 pt below frontier at
  7% route share; 13.3% cheaper than Opus-alone with a strong weak tier), the deferred composition sketch
  (A1 wrapper → A2 skill → A3 gate → A4 read), and the subagent-role rejection.
- `1736279` PLAN M45/M46/M47 + C101.
- `01a23e6` **M46 DONE**: opencode probe runs each item with an isolated `XDG_DATA_HOME`, exports the
  session transcript (PII-scrubbed) to `$STACK_WORKDIR/opencode_transcripts/<model>/<tag>/`, adds
  `transcript_path` + `loop_metrics` to the row. Not yet exercised live — the next opencode run is the check.
  Also `bench/session_cache_probe.py` (M45 instrument).
- `7b61583` **M47 tooling**: `run_bfcl_fc --sample-seed` (seeded random pilot per category — the first-N cap
  violated the pilot rule) and `--temperature` (recorded override of ONLY the deployed temperature).
- `a1bce3d`, `6543009` **M45 DONE** (rows `session_cache.m45.json` legs A+B, `session_cache.m45c2.json`
  leg C): opencode reuse ≈99%/request (12.7K of 183K prompt tokens prefilled over 16 requests, 11.1K on
  turn 1); eviction = one cold prefill of the context (10 s / 53 s / 127 s at 8K/32K/64K), warm turns ~1 s.
  **Two mechanisms → C102**: (a) `mlx-serve` forwards only 4 headers, `X-MLX-VLM-Chat-Id` never reaches
  the worker, every client rides the anonymous hash chain (≥2 matching turn hashes, assistant hash over
  verbatim content); (b) the DeltaNet snapshot boundary sits before the final user turn, so the FIRST
  follow-up after a `[system, big-user]` opener re-prefills the opener once.
- **M47 pilot DONE** (`bfcl_fc.m47_pilot.json`, this commit): t0.3/t0.5/t0.7 = 19/20 each, identical
  paraphrase miss in all arms, 0pp; ~6 s/item, no runaway. Full run sized 120 items/arm ≈ 12–33 min/arm.

## Open for the operator

- **C101** (M47 full OFAT?): recommendation revised to (b) close on the pilot — validity is temperature-
  insensitive at medium in [0.3, 0.7]; run (a) only for the n=120 row on record (~1 h quiet box).
- **C102** (a) forward the chat-id header (trivial, recommend now); (b) snapshot at prompt end (fork change
  on the C85-certified rewind path; needs a go).
- Deferred composition (switchyard doc §8): revisit when wanted; A1–A4 sketch is ready.

## Parked / deferred (unchanged)

S1 NVSY (awaiting go), D12 (lands with the next opencode run — now together with the M46 transcript check),
C77/C78/C87 (deferred).

## Git

Six stack commits this session (see `git log`), nothing pushed; push only on explicit in-turn instruction.
Forks untouched.

## Resume discipline

One resident model; APC absent; retained sessions 2; full active preallocation; deployed sampling and
explicit served-overlay environment. Never alter source/config during a live run; preserve real data and
recorded failures. Commit coherent units; push only on explicit current-turn instruction. Next decision id
C103; discussion ids continue from P30 (this session used P1–P30).
