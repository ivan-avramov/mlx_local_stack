# Handoff — 2026-11-20 (session 28: the S27 robustness bundle built (four-eyes strict, 3 review rounds, 3 fix rounds); regate of `s27-bundle` @ `72e5626a5` running; then Accept)

THE one handoff. Read this, then `docs/PLAN.md` rows M76, M83, then `docs/open-questions.md` top entries (newest first: C375,
S28-P7, S28-P5, S28-P4, C374 … C364). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance:
guardrails prevent wrong data or wasted time, not ceremony; GPU time is the binding resource; run-time calls are the designer's
(C353); all work on this box (C350); **intent over mechanism (S28-P5)**. Session 28 holds run-time autonomy for the post-gate tg2
chain (C374) — session 28 only; ask again. Label points `S28-P<n>` (used: P1–P11).

Decisions: session 28 ruled C374–C377 (next **C378**).

## Goal

Certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TQ4 KV + `tq4_attention: m72_exact` + MTP ON as the shipped default (−13 GB at
256K). Stage 1 ✔, stage 2 ✔, stage 3a ✔. Remaining: stage 3b A8 (tg2) decider — blocked on the S27 bundle + gate — then the ship
recommendation.

## FIRST

1. No GPU run is live. The four-eyes build lives in `$STACK_WORKDIR/fe-s27/` (status log `out/status`): clones `impl/`, `tw/`
   (test-writer, candidate 2 applied), `twb/` + `base/` (baseline), `panel/verify{,2}/`; briefs `briefs/`, frozen tests
   `frozen/v{1,2}` (+ `FROZEN` times), patches `out/candidate-{1,2}.patch`, `out/fix-1.patch`. Helper sessions: implementer fix
   `3a24a19a…` (Claude Opus), test-writer `9d1f8601…` (Claude Sonnet, deliveries 1–3).
2. Pushed: `origin/main` = `9abef6a6`, `origin/evidence` = `1c42f0ef`. Local `main` ~40 commits ahead (docs + C366 code + C365 test
   fixes); they push after the bundle's gate, on the operator's word.
3. Power 140 W / 28 V; launch gates / legs with `env -u CLAUDE_CODE_CHILD_NOTES_DIR`; no BUSY pattern in your own argv.
   Homebrew: the session-28 upgrade changed no formula (cursor cask failed, stale Caskroom record — harmless).

## Next, in order

1. **S27 bundle — regate running** on local branch `s27-bundle` @ `72e5626a5` (worktree `$STACK_WORKDIR/worktrees/s27-bundle`;
   log `$STACK_WORKDIR/gate-logs/stack-72e5626a.log`). First gate (`f55c4dc1b`) FAILED 2 / 16027 on spec-changed pins (S28-P11),
   fixed. Ledgers r1–r3 (`docs/reviews/s27-robustness/change-ledger-r{1,2,3}.md`), C376 / C377 fix rounds; frozen tests v5
   (299), both helpers "merge". Residual to state at Accept: Z2b (a session that empties, pid reused as a new leader which spawns
   and exits, all before the chain scan → its children claimed; needs pid reuse in seconds) plus Y7, Y8, C1 alias, C5 pause.
2. **On gate PASS → Accept to the operator** (final diff, findings with dispositions, widened cases C375 / S28-P7), then
   fast-forward `main` to the gated commit (no second gate: same sha); push on the operator's word; remove the worktree and
   branch, harvest `fe-s27/` remains (briefs / reports are already in `docs/reviews/s27-robustness/four-eyes/`) and remove it.
3. **B4b-2** (A8 consumers, spec v1.4) — after or with the bundle; reads `accounting_fault`, `cleanup_status`, rerun attempts,
   harness DNFs.
4. **tg2 chain from the gate (C374 autonomy):** rebuild arms on the gated sha (`p475_kv._ensure_venvs`; inventory digest;
   opencv reinstall if digests differ, S26-P10); restart the S27-P5 exec-latency logger; positives (with the interrupt positive) →
   rehearsal → v8 → pilot pair → sizing → the decider (C367's Go stands; ≈ 6–9.5 h per arm).
5. Then: B8-A8 → signals → A8 panel → ship recommendation. KV vision rubric fix (S26-P19) before the next KV panel. C357 PII hook.

## State (session 28)

- §10.2 designer check: the D1 26th step never published a step_finish (export-recovered `unpublished`) → spec v1.4 second shape,
  approved C375.
- Baseline full suite in the clone layout: 3 h 39 min, 6 env-only failures (tmp under home, canonical remote, frozen heads).
- Frozen tests v1 (blind, 08:39:36Z, 103 fail / 89 pass on baseline) → v2 (amended to the interface under S28-P5, 13:17:58Z);
  candidate 1 revealed 11:57:15Z; v2 on candidate 1: 208 / 209 (X4).
- Fix round 1: 18 findings fixed + X5 corrected (not a defect; designer's grep missed `ctx.update`); X19 root cause = a test
  re-wrapping `ProcessGuard.__init__` via monkeypatch (late undo leaked the hermetic wrapper).

## Worktrees and scratch (each: resolution)

- `$STACK_WORKDIR/fe-s27/` — the bundle build; harvest briefs / reports / ledgers into `docs/reviews/s27-robustness/` at Accept,
  then remove. Branch `s27-bundle` (to create) — fast-forwarded into `main` at Accept, then deleted.
- `m76-g2-{n16,x}`: tg2 arms on the OLD identity — remove after the new arms exist.
- `m76-w2-{n16,x}`, `m76-q-{n16,x}`, `m76-f45-*`: keep until the stage 4 decision.
- Scratch to remove: `review/{s25-p10,c365,c366,b4b2-design,s27-robust}/`, `gate/scratch/stack-67908a4b33eb-*`. Keep until the A8
  readout: `m65/inject/positives-2026111{7,9}T*`, `m76/p426/{tg2,tg2-s27,rehearsal.tg2,wave2.tg2}/` (the failed decider leg is
  the bundle's real-path input, §10.2), `m76/p426/exec-latency/`. Keep: `m76/panel-*`, `archive/s26-dot-gradle-20261117/`,
  `m76/p426/tg2/attempt1-FAIL/`.

## Rules learned (session 28)

- A pass rule widened after seeing data goes to the operator even when the designer check was pre-registered (S28-P4 → C375).
- Intent over mechanism (S28-P5): specs = goal + must-never invariants + scenarios; tests assert outcomes; exact only where data
  validity depends on it (S28-P6).
- Four-eyes copies need the submodules and `.venv-bench` (else hundreds of tests mask); `claude -p` JSON `result` holds only the
  last message — have helpers write their report to a file.
- The gate is the suite check; no separate candidate full run (S28-P8).
- Four-eyes copies: link the polyglot corpus into the redirected `STACK_WORKDIR` and put OrbStack's docker on the helpers' PATH; compare the copy's skip count with the gate's before gating (S28-P11).
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
