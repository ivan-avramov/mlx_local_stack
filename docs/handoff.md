# Handoff — 2026-11-20 (session 27 → 28: the A8 decider stopped on harness defects; the S27 robustness bundle is designed, ready to build)

THE one handoff. Read this, then `docs/PLAN.md` rows M76, M83, then `docs/open-questions.md` top entries (newest first: C373 … C364,
S27-P11 … S27-P1). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: guardrails prevent wrong data or
wasted time, not ceremony; GPU time is the binding resource; run-time operational calls are the designer's (C353); all work on this box
(C350). Session 27's "run the tg2 chain on your recs" (C364) was SESSION 27 ONLY — ask again. Label points `S28-P<n>`.

Decisions: session 27 ruled C364–C373 (next **C374**). Session 27 ids used: S27-P1 … P17.

## Goal

Certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TQ4 KV + `tq4_attention: m72_exact` + MTP ON as the shipped default (−13 GB at
256K). Stage 1 memory ✔, stage 2 exactness ✔, stage 3a ✔ (A1, A5, A7 PASS; panel no flag). Remaining: stage 3b A8 (tg2) decider, then the
ship recommendation to the operator.

## FIRST

1. **No run is live.** The A8 decider stopped after N16 s1 (S27-P11, INVALID, harvest refused). No waiters or loggers are running (the
   S27-P5 launch-latency logger was stopped; restart it, `m76/p426/exec-latency/exec_latency.py`, before the next live run). The
   operator upgrades Homebrew at each fresh session (memory) — fine now; HOLD upgrades once a Wave 2 / tg2 run is live (C360 fingerprint).
2. Pushed (C371): `origin/main` = `9abef6a6`, `origin/evidence` = `1c42f0ef`. Local `main` is ~30 commits ahead (docs + C366 code +
   the C365 test fixes): they push after the S27 bundle's gate, on the operator's word.
3. Check power 140 W / 28 V; launch gates / legs with `env -u CLAUDE_CODE_CHILD_NOTES_DIR` (S27-P3); no BUSY pattern in any of your own
   argv while a leg may start (S27-P7: check processes by port / pid file; a self-matching `pgrep` loop never ends).

## Next, in order

1. **S27 harness robustness bundle** — design FINAL, `docs/specs/s27-harness-robustness.md` v1.3 (C370 principles, C372 retry split,
   C373 interrupt positive; review rounds 1–3, ledgers `docs/reviews/s27-robustness/`). Build four-eyes STRICT: a fresh blind test-writer
   (not the implementer's model) writes the §10 red tests first; implementer `claude -p` in a worktree; change review Sol + GLM + Sonnet
   (rounds ≤ 3), verify; then the full stack gate (it rotates the tg1 + tg2 identities; stage-4 reuse loss accepted, C371). Includes:
   ownership-based cleanup (`foreign_new`, receipt schema 2), order-tolerant reconciliation (`kill_boundary_late_record`,
   `PASS_NO_INFLIGHT`), pre-outcome rerun / post-outcome `accounting_fault` / in-probe final-grade regrade, the abort route + PAUSED, the
   C365 cancel, D3 harvest links, the C368 lock-file view, measure / ALERT / item-boundary hold, §12 push binding (C371 B), §4.5
   interrupt positive. Designer check before the build freeze: the `java/sgf-parsing` events (§10.2).
2. **B4b-2** (A8 consumers) — design FINAL, `docs/specs/m76-b4b2-a8-consumers.md` v1.4 (C368, C369; reviews `docs/reviews/m76-b4b2/`).
   Build after (or with) the bundle; it reads the bundle's new row fields (`accounting_fault`, `cleanup_status`, rerun attempts, harness
   DNFs). Its javascript lock-file regrade (§3.7) applies only to rows graded on the OLD identity; on the new identity the view omits the
   lock (C368 forward fix), so new rows need no regrade.
3. After the gate: rebuild the tg2 arms on the gated sha (`p475_kv._ensure_venvs`; check the gate inventory digest within the pair; the
   opencv `cv2` race recurs — reinstall `opencv-python-headless==4.13.0.92` in X's `.venv-bench` when digests differ, S26-P10); then the
   tg2 chain: positives (with the interrupt positive) → rehearsal → v8 → pilot pair → the decider (C367's Go stands; sizing
   `docs/reviews/m76-s3b-sizing/SIZING.md`: decider ≈ 6–9.5 h per arm). Ask the operator for run-time autonomy again.
4. Then: B8-A8 → signals → the A8 panel → the ship recommendation (stage 3b). The KV vision rubric fix (S26-P19) before any next KV panel.
5. Small owed: the PII hook learning the username pattern from the machine config (C357).

## State (session 27)

- Gate PASS on `9abef6a6` (15331 passed, 3 h 42 min — the endpoint agent ThreatLocker roughly doubles process-launch cost, S27-P5).
- tg2 positives: the 11-17 and 11-19 records committed (`benchmark/results/m76/tg2/positives-*`, evidence `1c42f0ef`); a PASS record
  `3333fa6c` under C366 (transfer rule) — valid only for the OLD identity's arms.
- tg2 pilot pair VALID / VALID, pilot gate PASS, amendment, v8 `7e75cd66` (`benchmark/results/m76/wave2.tg2/`, `7756726e`): all bound to
  the old arms `m76-g2-*` @ `9abef6a6` / `e027dbb7` — superseded once the bundle rotates the identity (the chain restarts from the gate).
- The failed decider leg `tg2-m76-n16-s1.a1` (scratch, `$STACK_WORKDIR/m76/p426/wave2.tg2/`) is NOT harvested (D3); keep it as the
  bundle's real-path test input (§10.2), then archive.
- Stage 3a readout unchanged (`benchmark/results/m76/`: `B8.json`, `SIGNALS-partial.md` per C363, `SIGNALS.md`); README's PROVISIONAL M76
  row still to be updated with the panel.

## Worktrees and scratch (each: resolution)

- `m76-g2-{n16,x}`: tg2 arms on the OLD identity — remove after the new arms exist (their positives / pilot / v8 are superseded).
- `m76-w2-{n16,x}`, `m76-q-{n16,x}`, `m76-f45-*`: stage 3a / stage 1–4 arms — keep until the stage 4 decision (Wave 2 X reuse is lost,
  C371; stage 4 reruns its X legs if it runs).
- Scratch: `$STACK_WORKDIR/review/{s25-p10,c365,c366,b4b2-design,s27-robust}/` (review clones; harvested to `docs/reviews/`) — remove;
  `gate/scratch/stack-67908a4b33eb-*` (2026-11-14, unfinished gate run) — remove; `m65/inject/positives-2026111{7,9}T*`,
  `m76/p426/{tg2,tg2-s27,rehearsal.tg2,wave2.tg2}/` — keep until the A8 readout; `m76/p426/exec-latency/` — keep (S27-P5 data).
- Scratch (keep): `m76/panel-claude-order2-first-pass/`, `panel-claude-order2-second-pass-A2/` (S26-P18), `m76/panel-strays/`,
  `archive/s26-dot-gradle-20261117/`, `m76/p426/tg2/attempt1-FAIL/`.

## Rules learned (session 27)

- A guard checks what the harness owns and does; environmental noise is measured and recorded, enforced only when it can change the
  measured outcome; a harness fault reruns that one item, never the leg (C370, AGENTS.md). Before a post-outcome retry ask whether the
  trigger correlates with the outcome (C372: rerun only before the outcome; flag after it).
- No pytest from the moment a sequencer or positives run launches until it exits, pre-leg idle included (S27-P8); main stays code-free
  while legs run — park uncommitted code as a patch / worktree.
- The Claude Code session exports `CLAUDE_CODE_CHILD_NOTES_DIR` (a home path): unset it for gates and legs.
- A pre-registered pass rule changed after seeing data goes to the operator, and a borrowed proof must be bound to the code it relies on
  (C366 digest) and committed (not scratch).
- An agentic run can turn a cache into symlinks (npx), a package manager into a "tampered" verdict (npm lock): test every language's own
  tooling path on the real box before a long leg.

## Rules learned (sessions 18–26, condensed; full text in git history of this file)

- Inject positives that ask the model to misbehave measure compliance; check whether it ran the command before calling a decline. An agentic
  leg can mutate the host (the JVM ignores `$HOME`). A judge context never holds both orders. A panel is frozen once, against the final B8.
  Check arms with the gate's inventory digest. Each harvest re-imports `bench` from `main`'s working tree. `brew uninstall` autoremoves.
- Four-eyes implementers run named tests only; the full suite runs once as the gate. A test timeout is a margin over a measured duration.
  Waiters match emitted names. `bench.*` modules run from `benchmark/`. GPU stages and pytest helpers never overlap. After a reboot start
  OrbStack before any gate.

## Archives (local, no push)

- `$STACK_WORKDIR/archive/tg2-universe-ff76573b/`, `archive/s26-dot-gradle-20261117/`, `m72/superseded-instrument-v{1,2}/`, `archive/p475-base-*`,
  `archive/session18-worktrees/`; branches `archive/*`.
