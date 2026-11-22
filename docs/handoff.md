# Handoff — 2026-11-22 (session 28 → 29: all code gated and pushed (`main` @ `14eca7b44`); the A8 tg2 decider is LIVE at X s1 a3)

THE one handoff. Read this, then `docs/PLAN.md` rows M76, M83, then `docs/open-questions.md` top entries (newest first: C382 … C374,
S28-P32 … S28-P1). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance:
guardrails prevent wrong data or wasted time, not ceremony; GPU time is the binding resource; run-time calls are the designer's
(C353); all work on this box (C350); **intent over mechanism (S28-P5)**. Run-time autonomy (C374) was session 28's only — ask again. Label points
`S29-P<n>`.

Decisions: session 28 ruled C374–C382 (next **C383**).

## Goal

Certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TQ4 KV + `tq4_attention: m72_exact` + MTP ON as the shipped default (−13 GB at
256K). Stage 1 ✔, stage 2 ✔, stage 3a ✔. Remaining: stage 3b A8 (tg2) decider — RUNNING — then B8-A8, signals, the A8 panel and the ship
recommendation (an UNDECIDED A8 reads by C379 (2), pre-registered).

## FIRST

1. **A run is LIVE — do not upgrade Homebrew** (C360 fingerprint), no pytest in the arms' trees (S27-P8), no gate (it locks out legs).
   Sequencer pid in `$STACK_WORKDIR/m76/p426/wave2.tg2/sequencer.pid` (session 28: 30445, chain 30512, watcher 30610), log
   `wave2.tg2/sequencer.stdout`. Leg `tg2-m76-x-s1.a3` started 2026-11-21 23:50Z (≈ 5–6 h); then s2 (X → N16) and reload (X → N16),
   ≈ 15–19 h in all. The exec-latency logger runs (pid in `m76/p426/exec-latency/pid`; rows carry `t_epoch` / `t_utc`).
2. **Ask the operator for run-time autonomy again** (C374 was session 28 only): reruns of a leg INVALID before any item, holds,
   continue / pause calls under C353.
3. Check processes by pid / port / pid file only — never a pattern your own command carries (S28-P28). Power 140 W / 28 V;
   `env -u CLAUDE_CODE_CHILD_NOTES_DIR` for legs / gates. If a leg dies before any item on the vmmap census again, check
   `vmmap -w <small pid>` (< 30 s) and look for a root filesystem scan; a further rerun uses `--rerun-attempt N` (C381).
4. Pushed: `main` = `14eca7b44` (gate PASS `d9ec9ec8b`, receipt `…-18038ff7e402`). Local `evidence` = `b909ceb72` (pilot pair + s1 N16
   + X s1 a1 / a2 evidence), NOT pushed: one data-only push of all A8 evidence after the decider (C382 — the designer's timing).

## Next, in order

1. After the decider: harvest; publish `run/exec_latency.json` (sealed, from
   `$STACK_WORKDIR/m76/p426/exec-latency/exec_latency.jsonl`, rows now carry `t_epoch` / `t_utc`); commit its evidence (as `b909ceb72`).
2. B8 (`bench.p426_verify --lever kv all --pair n16,x`) → B8-A8 → signals (A8 verdict by `axis_verdict`; the pre-registered UNDECIDED
   reading C379 (2)) → the A8 panel (two families, both orders, a judge context never holds both orders) → the ship recommendation.
3. S26-P19 KV vision rubric fix before the next KV panel; C357 PII hook; Y10 conftest LIFO (S28-P18, with the next gated change); the
   vmmap-census bound as a measured precondition (S28-P24 follow-up).

## State (session 28)

- S27 bundle accepted (C378), gated twice (the second with its own gate code, S28-P17); B4b-2 built four-eyes strict (r1–r3 + fix
  rounds 1–4; the last two real-record findings T1 / T2 only visible on the new-identity pilot).
- New-identity A8 chain: positives PASS `486ebbfa` (interrupt in flight), rehearsal `20261121a`, v8 `ba4d6b27`, pilot pair VALID,
  sizing `docs/reviews/m76-s3b-sizing/SIZING-s28.md` (decider 8.5 / 11.9 / 12.0 h per arm). Old-identity records moved to
  `benchmark/results/m76/wave2.tg2-old-identity/`.

## Worktrees and scratch (each: resolution)

- `$STACK_WORKDIR/worktrees/m76-g2-{n16,x}`: the NEW tg2 arms (@ `72e5626a5` / `026ef4557`) — keep until the A8 readout. Old arms are
  branches `archive/m76-g2-{n16,x}-old-identity`.
- `$STACK_WORKDIR/worktrees/evidence-s28`: the local `evidence` branch worktree (commit `b909ceb72`) — remove after the evidence push.
- `$STACK_WORKDIR/fe-s27/`, `fe-b4b2/`: four-eyes build copies — records harvested to `docs/reviews/s27-robustness/` and
  `docs/reviews/m76-b4b2/four-eyes/`; remove.
- `m76-w2-{n16,x}`, `m76-q-{n16,x}`, `m76-f45-*`: keep until the stage 4 decision.
- Scratch keep until the A8 readout: `m76/p426/{wave2.tg2,wave2.tg2-old-identity,tg2-s28,rehearsal.tg2}/`, `m76/p426/exec-latency/`.
- Branch `archive/main-pre-s27-rebuild`: the pre-rebuild main (C378) — delete after the push.

## Rules learned (session 28)

- A pass rule widened after seeing data goes to the operator even when the designer check was pre-registered (S28-P4 → C375).
- Intent over mechanism (S28-P5): specs = goal + must-never invariants + scenarios; tests assert outcomes; exact only where data
  validity depends on it (S28-P6).
- Four-eyes copies need the submodules and `.venv-bench` (else hundreds of tests mask); `claude -p` JSON `result` holds only the
  last message — have helpers write their report to a file.
- The gate is the suite check; no separate candidate full run (S28-P8).
- Four-eyes copies: link the polyglot corpus into the redirected `STACK_WORKDIR` and put OrbStack's docker on the helpers' PATH; compare the copy's skip count with the gate's before gating (S28-P11).
- Results-first sequencing: nothing that can block a leg runs while legs remain; quality first when they conflict (C381).
- Real-record acceptance on the CURRENT records before a gate: synthetic worlds cannot show record facts (S28-P30, T1 / T2).
- When verifying a reviewer's claim by grep, search every write form (`ctx[...] =` and `ctx.update(...)`) before adopting (X5).

## Rules learned (sessions 18–27, condensed; full text in git history of this file)

- A guard checks what the harness owns; noise is measured, enforced only when it can change the outcome; a harness fault reruns
  the item, never the leg; rerun only before the outcome (C370, C372). No pytest while a sequencer / positives run is live
  (S27-P8). Unset `CLAUDE_CODE_CHILD_NOTES_DIR` for gates and legs. A borrowed proof is bound to the code it relies on. Test every
  language's own tooling path on the real box before a long leg. Inject positives measure compliance. A judge context never holds
  both orders. Check arms with the gate's inventory digest. Four-eyes implementers run named tests only. After a reboot start
  OrbStack before any gate.

## Archives (local, no push)

- `$STACK_WORKDIR/archive/tg2-universe-ff76573b/`, `archive/s26-dot-gradle-20261117/`, `m72/superseded-instrument-v{1,2}/`,
  `archive/p475-base-*`, `archive/session18-worktrees/`; branches `archive/*`.
