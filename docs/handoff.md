# Handoff — 2026-08-29 night (M26 CLOSED; box IDLE; B pick stands)

Single box (M5 Max 64 GB). **No run is live.** The M26 second-session block finished clean
19:22 2026-08-29 (6/6 legs rc=0, 9.7 h); analysis, docs and commits are DONE. The worker
still holds the last M26 model — unload before any new work
(`POST /v1/models/unload` + pgrep-verify `mlx_vlm.server` gone).

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

## Operator decisions owed (none blocking)

- **C30 bound write-up** — now materially informed (six replicate pairs); should use flip
  counts, not net deltas. Natural next doc task.
- **M12 d128k call** — was deferred behind M26; M26 landed unresolved, so the question is
  whether d128k is still worth the wall-clock given the C30 error bar.
- C31 stays deferred. Queue behind: M11 reasoning ladder, M21 int8 causal test, M14
  drafter (`nemotron_h_mtp` dev was in flight), M6c/M6d predictor probes, M17 funnel, D11
  cards. Next O/C number: **C38**.

## Standing state

- **PUSHED through `df3ca80`**; local-only commits after it: `d30035e` (M26 PLAN row),
  `6ec0625` (prior handoff), plus tonight's M26 data + docs commits. Never push without
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
