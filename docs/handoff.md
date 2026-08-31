# Handoff — 2026-08-30 late night (M11 v4 LIVE, C39 ruled; M6d certified; Nemotron rollback SHIP on fork branch) <!-- allow-shorthand -->

Single box (M5 Max 64 GB). **A RUN IS LIVE: M11 reasoning ladder, v4 orchestrator** —
`$STACK_WORKDIR/m11/m11_orchestrator_v4.py`, pid 36314 (`m11_orchestrator_v4.pid`),
launched 23:19 2026-08-30 to ADOPT the model-1 ladder child (pid 32064, started 19:05 by
v3; v3 SIGTERM'd because its 12 h bound would have killed the child inside the 156K rung —
lab-notebook 2026-08-30 (night)); log `m11_orchestrator.log` (v4 lines prefixed `v4`); 5-min
watch `m11_watch_v4.py` pid 36346 → `m11_watch.log`; per-model logs `m11_<model>.log`
(`rung done` = the only source of NEW rung events; `REASONING_EFFECTIVE_CTX=` = model
finished); per-rung persistence `benchmark/results/<model>/reasoning.partial.jsonl`
(design-keyed; `--resume`); final `reasoning.json` per model. Roster in order:
`Qwen3.8-27B-mlx-uniform-4bit` (shallow 6 rungs 1.0; 96K done 23:01 `acc=1.0
budget_hits=2/3` — strict 1/3; 128K began 23:01, expect 03:20–05:30; 156K then 08:00–10:30
08-31) → `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` → `Ornith-1.0-35B-mlx-uniform-4bit` →
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`. Design of record (PLAN M11, pre-registered):
8K/16K/24K/32K/48K/64K at 5 samples; 96K/128K/156K at 3 samples with the early stop (first
2 deep samples both hit the 81,920 budget → rung scored from those 2); threshold 0.85,
climb on LENIENT accuracy (C39: report both curves, STRICT ranks), `deployed`, request
timeout 9600 s, unload+pgrep-verified between models, **20 h per-model bound** (adopted
child: 12 h from 23:19), fail-loud. Budget: ~15–18 h/model when deep rungs think to budget
(~2 h 10 m per 128K sample, ~2 h 20 m at 156K). Router :8000 serves
`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml` (SESSION_MAX=2, APC absent).
**Session waiters die with the launching session — a resuming session re-arms a PID waiter
on 36314 (failure + timeout arms), confirms `pgrep -f m11_watch_v4`, and MUST use
`/usr/bin/tail`/`/usr/bin/grep --line-buffered` (the shell hook rewrites bare `grep` to a
proxy that buffers to EOF — four monitors were silent through a rung completion tonight)
and fire a known-positive self-test line before trusting it.** Progress truth = router log
request lines (`logs/main_model.log`, `metrics —` lines carry prompt/completion tokens +
ms) plus the per-model `rung done` lines.

**When M11 lands** (or a leg aborts — diagnose first, never re-run over a poisoned tree):
evaluate each model's `reasoning.json` (rung accuracies, `budget_hits`, `early_stop`,
`reasoning_effective_ctx`), write the dated campaign-results entry (reasoning-depth curves
per B-menu model + `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`; mechanism = budget-length thinking at depth), lab-notebook,
PLAN M11 → done, handoff rewrite, commit.

**THEN the box queue (all operator-approved 2026-08-30):**
1. **M14 `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` predictor** — fork branch `nemotron-h-rollback` (`../mlx-vlm`, PUSHED to
   the fork remote; head `d1d57955` = `58cac341` impl + `86f352b6` verifier fixes + black;
   verifier verdict SHIP; GPU-kernel exactness is the one thing CPU tests could not cover).
   Steps: (a) `split_mtp` the downloaded BF16 source (hub
   `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16` <!-- hub repo id, allow-shorthand -->, already in the HF cache,
   MTP shard fetched) into an int4 sidecar dir under `$STACK_WORKDIR/scratch/m6a/` using the
   fork branch (`PYTHONPATH=../mlx-vlm`); (b) Metal load smoke: serve
   `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` with `--draft-kind mtp --draft-model <dir>`
   via the fork branch on PYTHONPATH, verify flags at the worker cmdline, one request must
   complete with non-null draft counters and coherent text; (c) `m1.mtp_probe --draft-model
   <dir>` (it starts its own router — stop :8000 first) against the 1.3× bar; (d) on a
   passing smoke: merge branch → fork main, push fork, bump `src/mlx-vlm` in the stack
   (`chore(stack): bump src/mlx-vlm -> <sha>`), `git submodule update --force` — all
   pre-approved; (e) ≥1.3× → M6b/M6d-style quality OFAT n=164 → CERTIFIED registry flip.
2. **M27 `Ornith-1.0-35B-mlx-uniform-4bit` MTP transplant** — base shards 13–14/14 of hub `Qwen/Qwen3.5-35B-A3B` are in
   the HF cache; `split_mtp` (the `qwen3_5_mtp` splitter stacks MoE experts) → sidecar dir →
   load smoke on `Ornith-1.0-35B-mlx-uniform-4bit` (rollback/verify inherited from qwen3_5)
   → `m1.mtp_probe --draft-model` (1.3× bar; MoE verify makes it effectively higher) → OFAT
   if it clears. M28 (head fine-tune on the tune's own generations) is gated on M27's
   acceptance (< ~0.8 triggers it).
3. Then M21 int8 causal test → M12 d128k cliff check (pre-registered, PLAN M12) → M17/D11.

**Closed 2026-08-30**: M6d CERTIFIED (`Qwen3.8-27B-mlx-uniform-4bit` `draft_kind: mtp`,
n=164 EQUIVALENT, 1.60×, acceptance 0.674, `76dad59`) — B 3rd choice ships a complete
triple; M6c `Ornith-1.0-35B-mlx-uniform-4bit` suffix leg CLOSED (1.20× on real opencode
traffic < 1.3×; suffix counters are structurally unobservable on the fork — speed was the
observable); C38 ruled (B menu of three); C30 bound delivered; M26 closed; ladder tooling
fixed (O36 profile, O41 timeout + escalation, persistence/resume, deep design). Bench
suite GREEN (1243 passed) — the C35 corpus guard now keeps each manifest's recorded draft
state (operator ruling).

## Operator decisions owed

- None blocking. C39 RULED 2026-08-30 23:15 (lenient climb stands for this run, both curves
  reported, strict ranks; v3→v4 swap executed). Follow-up owed before the next ladder:
  persist per-sample rows in `bench/reasoning.py` (score, completion_tokens, budget_hit per
  draw) so strict re-scoring never needs the router log. Standing debt: the
  `caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter` HF card still says PROBE-ONLY
  (outward-facing update owed, do deliberately). C31 deferred. Next O/C number: **C40**.

## Standing state

- **PUSHED through `3c81c8d`** (operator-approved 2026-08-30 night). Fork branch
  `nemotron-h-rollback` pushed. Never push without in-turn approval.
- Working tree: the **FIVE** intentional `main_models.yaml` local-path overrides (NEVER
  commit; clean-checkout + re-apply procedure in lab-notebook 2026-08-30 asserts all five)
  + old untracked m23-era files + untracked M6b/M6d OFAT rows under `benchmark/results/`
  (M6b storage precedent). Live `~/.config/opencode/opencode.json` = BENCH carrier, restored
  to :8000 after the M6c probe (backup `$STACK_WORKDIR/opencode.json.probe-backup`).
- Data: M26 python s2 rows in-repo; javascript s2 + logs `$STACK_WORKDIR/m9/`; M6d
  analysis `$STACK_WORKDIR/m6b/q38_*`; M6c probe `$STACK_WORKDIR/m6c/`; M11
  `$STACK_WORKDIR/m11/`; downloads `$STACK_WORKDIR/m14/`, `$STACK_WORKDIR/m27/` logs.
- Bench-router invariants: draft-OFF overlay + SESSION_MAX=2 + APC absent; C35 tripwire
  live (it refused a mis-enved M6c launch — working as designed). HF cache pruned to 253G
  deliberately (2026-08-28) — the two MTP-source fetches added ~20 GB on purpose.

## THE HEADLINE — M26: the pooled split did NOT resolve; the B pick STANDS

Pre-registered pooled McNemar (discordants over (item, session), s1↔s1/s2↔s2,
python+javascript, Holm family = 2): `Qwen3.8-27B-mlx-uniform-4bit` vs
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` **20:8 p=.036** vs Holm rung .025 — MISS; vs
`Ornith-1.0-35B-mlx-uniform-4bit` **14:5 p=.064** — MISS. No displacement case goes to the
operator. The direction is unchanged (challenger 75/88 pooled vs 63 and 66, ahead in every
pooled cell) but nothing is significant, and item clustering (`connect`/`forth` recur)
makes the exact p-values optimistic in the challenger's favor.

**The bigger finding is methodological (C30): the python 8:0 replicated as 4:4** — the s1
pick python leg (12/22) was an outlier-bad session (s2: 18/22, +6). Six same-model s1→s2
replicate pairs give deltas +6, +5, −1, −1, −1, −2 with up to 9+3 item flips per pair:
**single-session 22-item opencode arms carry ±5–6 items of session noise, not the ±1–2
previously assumed.** Every single-session cell in campaign-results (the M9 five-language
block included) is directional only. `Qwen3.8-27B-mlx-uniform-4bit` is the most
session-stable arm. Full tables: campaign-results 2026-08-29 (night); mechanics:
lab-notebook 2026-08-29 (night).

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
