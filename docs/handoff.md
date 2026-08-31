# Handoff — 2026-08-30 (M6d CERTIFIED; M26 closed; box idle between queue items)

Single box (M5 Max 64 GB). **A RUN IS LIVE: M11 reasoning ladder (v3 orchestrator = P52 option a design)** —
relaunched ~17:20 2026-08-30 by `$STACK_WORKDIR/m11/m11_orchestrator_v3.py` (pid in
`m11_orchestrator_v3.pid`; log `m11_orchestrator.log`; 5-min watch `m11_watch.log` (v2,
counts `rung done` lines); per-model logs `m11_<model>.log`; per-rung persistence
`benchmark/results/<model>/reasoning.partial.jsonl` (design-keyed, `--resume`); final
`reasoning.json`). Roster: `Qwen3.8-27B-mlx-uniform-4bit` → `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
→ `Ornith-1.0-35B-mlx-uniform-4bit` → `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`; grid
8K…64K at 5 samples + 96K/128K/156K at 3 samples with the pre-registered early stop (first 2
deep samples both budget-hit → rung scored from 2), threshold 0.85, climb-to-cliff,
`deployed`, request timeout 9600 s, 12 h per-model bound, fail-loud. **Sizing finding**: the first 96K
sample thought to budget (82,033 tok, 2 h 05 m) — a budget-hitting rung costs ~10 h/model
at 5 samples; **P52 RULED (operator 2026-08-30): option (a)** — the design above; shallow rungs
resumed under their base key. Router :8000 serves the
draft-OFF overlay (SESSION_MAX=2, APC absent). Waiters die with the session — poll PID/log.

**Fork work in flight (M14)**: branch `nemotron-h-rollback` in `../mlx-vlm` — `58cac341`
(Sonnet: `RecurrentStateRollbackMixin` + minimal `# Fork:` hunks + 10 tests) then
`86f352b6` (fixes for the verifier subagent's F1–F7: the BLOCKING F1 was a missing `norm_f`
in `speculative_logits_from_hidden` — silent output corruption; now an overridable
`speculative_final_norm` hook; mixin moved to `mlx_vlm/models/recurrent_rollback.py` to
close an import cycle). Verifier re-check of `86f352b6` pending. Branch PUSHED to the fork remote (operator-approved 2026-08-30; verifier SHIP at
`d1d57955`); merge to fork main + submodule bump approved CONDITIONAL on the Metal smoke
passing when the box frees up. Inputs downloaded:
the `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` drafter source shard (hub `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16` <!-- hub repo id, allow-shorthand -->) and the
`Ornith-1.0-35B-mlx-uniform-4bit` base MTP shards (hub `Qwen/Qwen3.5-35B-A3B` 13–14/14, M27) — both splits (MLX) wait
for the quiet window.

**Closed today (2026-08-30)**: M6d CERTIFIED (`Qwen3.8-27B-mlx-uniform-4bit` mtp, n=164
EQUIVALENT, 1.60×, `76dad59`); M6c `Ornith-1.0-35B-mlx-uniform-4bit` suffix leg CLOSED
(1.20× on real opencode traffic < 1.3×); M14 BLOCKED on a real fork gap (`nemotron_h`
lacks `rollback_speculative_cache`; PLAN row). Registry carries FIVE local overrides
(NEVER commit). HF card debt: challenger's drafter card still says PROBE-ONLY.

**⚠ Bench suite is RED by one test — operator ruling owed (see decisions):**
`test_provenance_fingerprint.py::test_a_v3_current_does_NOT_condemn_the_REAL_corpus_on_disk`
now fails on the honest M6d ON-arm manifest (`humanevalplus.mtpon.manifest.json`,
`runtime.draft_kind: mtp`, genuinely served). The test's 08-26 premise ("no real manifest
sets draft_kind") is stale, not the fingerprint: an ON-arm manifest SHOULD refuse a
draft-off current. Proposed fix: the test keeps each manifest's own recorded draft_kind
when building `current` (it tests v2→v3 non-destructiveness, not draft-state refusal).
NOT touched pending ruling (C35 precedent: never adjust a red guard on session judgement).

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

## Operator decisions owed

- **C38 RULED 2026-08-29: B MENU, not displacement** — 1st
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, 2nd `Ornith-1.0-35B-mlx-uniform-4bit`, 3rd
  `Qwen3.8-27B-mlx-uniform-4bit` (NEW). Executed: registry role candidate→main + comments,
  all five carriers via `configgen generate` (commit `5dc6699`), overrides re-applied.
  **OWUI publish PENDING the next compose bring-up** (was down at ruling time) — init.py
  seeds from `openwebui-init/models_config.json` automatically.
- **M12 d128k RULED 2026-08-29 (operator took the session rec): per-model CLIFF CHECK
  only** — pre-registered design in the PLAN M12 row (n=25 seeded, 3 B-menu models,
  >10pp-vs-own-d64k test, no pairwise; ~6–8 h).
- **Queue order RULED (operator took the session rec)**: M6c/M6d block (IN FLIGHT) →
  M11 reasoning ladder (roster now includes the B 3rd choice) → M21 int8 causal test →
  M12 d128k cliff check → M17 funnel + D11 cards interleaved as no-box-time work. M14
  `nemotron_h_mtp` probe rides the M6c block (fork code landed; sidecar extraction owed).
  C31 stays deferred. Next O/C number: **C39**.

## Standing state

- **C30 BOUND DELIVERED 2026-08-29** (in the C30 entry): per-item cross-session
  discordance q = 0.114 / 0.227 / 0.432 (challenger / runner-up / pick); 1-sd session
  noise on a 22-item agentic arm = 1.1 / 1.6 / 2.2 items; quote q per-model beside every
  MDE; ≥2 sessions/arm for pick-affecting axes; single-session arms claim direction only.
- **PUSHED through `9fa573a`** (operator-approved 2026-08-30). Local-only since:
  `76dad59` (M6d cert), `1b66e9b`, `1fcc68d` (M6c close), `a37159e` (M14 blocker),
  `a17a134` (run_reasoning O36/O41 fixes), + this handoff. Never push without in-turn
  approval.
- Working tree keeps the FIVE intentional `main_models.yaml` local-path overrides (NEVER
  commit; stash-protect during rebases) + old untracked m23-era files + the untracked
  M6b/M6d OFAT row files under `benchmark/results/` (M6b storage precedent).
- Data layout: python s2 rows committed in-repo
  (`benchmark/results/<model>/opencode.s2.jsonl`, M25 precedent); javascript s2 rows + all
  s2 manifests + every C37/M26 log stay in `$STACK_WORKDIR/m9/`.
- Bench-router invariants unchanged: draft-OFF overlay (2026-08-29) + SESSION_MAX=2 + APC
  absent; C35 tripwire live. Live `~/.config/opencode/opencode.json` is still the BENCH
  carrier (backup `$STACK_WORKDIR/opencode.json.probe-backup`) — restore only when
  opencode work fully closes.
- HF cache pruned to 253G deliberately (2026-08-28) — don't "fix" it.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
