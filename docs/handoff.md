# Handoff — 2026-10-27 (session 9 CHECKPOINT ~19:40Z): T3 (S′ serving build) implementing; B2 s1–s5 built, fix pass next; GPU rehearsal on provisional S′

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C239, C238, P504, P501, P500, P503, P499, C236 …),
then `docs/specs/p426-t3-serving-build.md` (v2.1) and `docs/specs/p426-b2-tg1-wave2.md` (v3.2 incl. §16; [o4] / [d2] changes, round 2
of 3 done) and `docs/reviews/p426-t3/`, `docs/reviews/p426-b2/`. Model names: FULL registry names only, always (chat included).
Skills in use: four-eyes 0.7.0, review-panel (updated 2026-10-27); review rounds were reset by the operator (AGENTS.md: 3 per artifact).

## Goal and path (C218, C232, C234, C235, C236)

MTP blessing for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` first, on the NEW serving build S′ (C236: fork `c688e722`, mlx-serve
v0.3.0 `e6a7a5a`, mlx 0.32.4): T3 accepted → S′ cut, two committed arm worktrees → **Wave-1 rerun on S′** (≈ 18–23 h GPU, label `s2`)
while B2 finishes → B2 rehearsal R1–R3 → v8 base → pilots → amendment → Wave 2 → B8 / B6 → ship call. P475 / P475a PARKED.

## Running now (all under `$STACK_WORKDIR`)

- **GPU (P499):** OFF tg1 `chain s1` rehearsal on the PROVISIONAL S′ (`t3/stack-prov`, branch `t3-provisional` `fa8f7b13`, own
  `.venv`), out-root `t3/tg1-rehearsal-20261027` (+ `.chain.out`), launched 15:46Z. Pick 1 Python 22 / 22 rc 0; Go leg slow (mean
  ≈ 980 s / item, one `client_inactivity`). Plan: stop it at an item boundary when T3 needs the GPU for its smoke (kill chain PID from
  `t3/rehearsal.pid`, `scripts/stack_stop.sh`, verify). Never graded / pooled; walls labelled concurrent CPU load. TODO: compare its Go
  walls with P486's (old build).
- **T3 implementer** (fresh Claude Sonnet 5.5, `claude -p`) in `t3/impl/mlx_local_stack` (B0 `1a4187e6` = GitHub-main merge + new
  gitlinks + spec), report → `t3/runs/impl-1.json`. **T3 frozen tests** `t3/frozen1/` (10 files, 19:33:33Z; test-writer Claude Opus 5.5
  session `1396ee76…`). Next: candidate diff → test-writer second delivery (`--resume`) → strict verify (fresh sol + glm) → fix → smoke
  (acceptance 6: OFF + ON from scratch committed worktrees) → Accept (operator).
- **B2 test-writer review of s4** (Claude Opus 5.5 session `44568a2b…`, delivery 2b) → `b2/runs/tw2-2b.json`.

## B2 state

- Spec v3.2 (main `6fe4c1f6`): design opinion after the reset [o4], §16 testable interfaces (from five blind test deliveries), C238
  (credential comparison dropped: keys only, per process), round-2 delta review [d2] (closed env allowed list, versioned arm-keyed
  dossiers, record classes, single harvest commit point, typed sources, portable records). Round 3 in reserve.
- **Frozen tests `b2/frozen4/`** (21 files, 19:06:51Z, `POST_REVEAL_TAGS.json`: amendments after the s1–s3 reveal, for C238 / [d2] /
  §16.7 and three test-writer defects). Earlier freezes `frozen2`, `frozen3` kept as records; glm's v6 `frozen/` superseded (P487).
- Slices (arm B = Claude Sonnet 5.5; arm-A sous-agent PAUSED for this session by the operator — session-only, nothing in AGENTS.md):
  s1–s3 reference `0274f35b`, s4 `489f6611`, s5 `5d4cac8e` (all in `b2/arm-sonnet/mlx_local_stack`, scratch commits). Frozen s1–s5 on
  s5: 116 passed / 76 failed (mostly §16 rules the slices predate). Test-writer review of s1–s3 (`docs/reviews/p426-b2/test-writer2-
  delivery2a-s1-s3.md`): fix-then-merge; R2 `--frozen-record` never read, R3 DNF limit per language, R4 router liveness not identity, R5
  injected ops read the real registry. s5 self-reported: a silent skip of s5 checks when test doubles lack seams (hazard), snapshot
  re-hash before every invocation (~20 GB each).
- **Next (C239): ONE fix pass on s1–s5** (fresh Sonnet; adopted findings + frozen4 read-only; test-writer re-runs and adds failing-case
  tests), then s6 watch, s7 locks, s8 freeze + sequencer, s9 harvest on the fixed base; then full suite, test-writer final delivery,
  strict verify, the four-eyes fix round, Accept.
- Evaluation copies `b2/eval-s3`, `eval-s4`, `eval-s5` (frozen4 installed); scoring packets `b2/judge-s3/`.

## Other open items

- **C237** (from the m5max box, renumbered from its colliding C182; lands with the T3 merge): KRAFTON/Raon-1-mini-preview — that box
  recommends not funnelling. Operator, not urgent.
- **P503**: two load-sensitive stack tests (P22 deadlock test, M64 selftest `check_terminal_shapes`) — root-cause after B2.
- **P498** (lead rec, not ruled): serving pins move only through a certification.
- **P478**: retire historical one-off tools as a class (after B2).
- sous-agent: issue NetApp/sous-agent#11 has the full feedback (latest comment 6451488159: s4 run, latency vs behaviour).
- Stack `main` ≈ 70 local commits unpushed; GitHub `main` is merged only in T3's B0 (lands at T3 Accept). Push needs the operator.

## Copies to resolve

`$STACK_WORKDIR/t3/{stack-prov (P499), impl, tw, dop, dop2, venv-fork, frozen1}`; `$STACK_WORKDIR/b2/{tw, tw2, arm-sonnet, arm-sous,
arm-sous-s2, arm-sous-s2b, arm-sous-s3, arm-sous-s4, eval, eval-s3, eval-s4, eval-s5, dop, dop2, frozen*, judge-s3}` — scratch; harvest
accepted candidates at Accept, then delete. No git worktrees of the main checkout.

## Rules learned (session 9)

- Never launch a helper from a command line that also carries brief text: write the brief in one call, launch in another (P454).
- Never run a suite in a copy a helper is editing.
- Check the fork's and the stack's GitHub state before any merge; the forks sync weekly.
- A spec change after a freeze invalidates tests: only the test-writer amends them; tag post-reveal amendments.

Next decision id C240; discussion ids continue from P506.
