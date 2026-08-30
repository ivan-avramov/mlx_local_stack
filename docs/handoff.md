# Handoff — 2026-08-29 night (M26 CLOSED; box IDLE; B pick stands)

Single box (M5 Max 64 GB). **A RUN IS LIVE: M6d OFAT EXTENSION, mtp-ON arm to n=164**
for the B 3rd choice `Qwen3.8-27B-mlx-uniform-4bit` — launched 02:50 2026-08-30. WHY:
the n=63 OFAT came back **INCONCLUSIVE** — delta 0.0pp, discordants 2:2
(`HumanEval/47`,`/95` OFF-pass vs `/116`,`/122` ON-pass), CI ±6.3pp vs the ±5pp TOST
gate, measured p_d=0.063 (4× M6b's), n_for=200 — so per O25 precedent NO certification
at n=63; both arms extend to the full 164-item humanevalplus corpus (nested resume,
same seed-39 protocol; balanced-split CI at n=164 ≈ ±4pp resolves the gate).
n=63 interim: ON 93.7/93.7 strict conv 100%, acceptance 0.678 (63/63 engaged); OFF
93.7/92.1 conv 98% (one budget-hit, `HumanEval/39` 83402 tok); speed ON +17.7 tok/s
decode, wall −106 s/item; analysis `$STACK_WORKDIR/m6b/q38_ofat*.json`.
Resuming session checks FIRST: driver pid `$STACK_WORKDIR/m6b/q38_ext_on.pid`, log
`q38_ext_on.log`, watch `q38_watch_ext_on.log`, rows
`benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/humanevalplus.mtpon.jsonl` (→164).
Router :8000 serves `$STACK_WORKDIR/m6b/overlay_q38_mtp_on.yaml` (worker verified
`--draft-kind mtp`; SESSION_MAX=2, APC absent). NEXT: when ON ext exits → router onto
`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml` (verify draft-free at worker) → OFF
extension `--limit humanevalplus=164 --tune mtpoff` → regrade both arms (`run.py grade
--tune mtpon|mtpoff`) → rebuild per-item accuracy (script pattern in lab-notebook
2026-08-30 entry, restrict to generated ids, drop `__pad__` rows) → TOST ±5pp; pass →
CERTIFIED `draft_kind: mtp` registry flip. Then `Ornith-1.0-35B-mlx-uniform-4bit`
suffix-acceptance probe (M6c) and `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`
extraction + probe (M14; fork drafter landed at `ab5708a`). M26 closed clean earlier
tonight (below).

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
- **PUSHED through `00b0bba`** (operator-approved 2026-08-29 night — includes all M26
  data + docs). Local-only: `253999c` (C30 bound + C38 open), `5dc6699` (B 3rd-choice
  promotion, registry + carriers), and the C38-ruling docs commit. Never push without
  in-turn approval.
- Working tree keeps the four intentional `main_models.yaml` local-path overrides (NEVER
  commit; stash-protect during rebases) + old untracked m23-era files.
- Data layout: python s2 rows committed in-repo
  (`benchmark/results/<model>/opencode.s2.jsonl`, M25 precedent); javascript s2 rows + all
  s2 manifests + every C37/M26 log stay in `$STACK_WORKDIR/m9/`.
- Bench-router invariants unchanged: draft-OFF overlay (2026-08-29) + SESSION_MAX=2 + APC
  absent; C35 tripwire live. Live `~/.config/opencode/opencode.json` is still the BENCH
  carrier (backup `$STACK_WORKDIR/opencode.json.probe-backup`) — restore only when
  opencode work fully closes.
- HF cache pruned to 253G deliberately (2026-08-28) — don't "fix" it.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
