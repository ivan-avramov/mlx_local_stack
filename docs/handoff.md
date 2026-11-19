# Handoff — 2026-11-19 (session 27 in progress: S25-P10 fixed (S27-P1); stack gate of `c34976a03` running; tg2 arms `m76-g2-*` built)

THE one handoff. Read this, then `docs/PLAN.md` rows M76, M83, then `docs/open-questions.md` top entries (newest first: C363, S26-P19 …
S26-P1, C362 … C359). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: guardrails prevent wrong data or
wasted time, not ceremony; GPU time is the binding resource; run-time operational calls are the designer's (C353); all work on this box (C350).
C359's "proceed on recs, stop only for major blockers" was SESSION 26 ONLY — ask again. Label points `S27-P<n>`.

Decisions: session 26 ruled C359–C363; session 27 C364–C366 (next **C367**). Session 27 ids used: S27-P1 … P8; next S27-P9.

## Goal

Certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TQ4 KV + `tq4_attention: m72_exact` + MTP ON as the shipped default (−13 GB at
256K). Stage 1 memory ✔, stage 2 exactness ✔, stage 3a ✔ (A1, A5, A7 PASS; panel no flag). Remaining: stage 3b A8 (tg2) decider, then the
ship recommendation to the operator.

## FIRST

**HOMEBREW: when a Wave 2 / tg2 run is live (see 0 below), do NOT `brew upgrade` until it ends** — C360's fingerprint stops the run on
any Cellar change. Session 27 state of this line: **tg2 DECIDER LIVE** (C367; `$STACK_WORKDIR/m76/p426/wave2.tg2/`, launched 2026-11-19 22:48Z, ≈ 13–20 h).

0. Session 27 (live): the A8 tg2 DECIDER is running (C367) — sequencer `$STACK_WORKDIR/m76/p426/wave2.tg2/` (`launch_decider.sh`,
   pid file `sequencer.pid`; legs s1 N16 → X, s2 X → N16, reload X → N16), on v8 7e75cd66 / amendment (pilot pair VALID, gate PASS,
   `7756726e`); sizing `docs/reviews/m76-s3b-sizing/SIZING.md` (decider 5.9 / 8.1 / 9.5 h per arm). No pytest, no code on `main`,
   no `brew upgrade`, no BUSY pattern in any argv until it exits. After: harvest commits (data), the stage-3b evidence batch to
   `evidence` (`wave2.tg2/scratch/evidence` + the pilot), B8 / signals for A8 (needs B4b-2), the ship recommendation.
1. Not pushed: `main` is ~46 commits ahead of `origin/main` (`3fc079ca`); the local `evidence` branch has `8b45058f` (Wave 2 evidence) on
   top of the remote. Pushing waits for the operator's word; the pre-push gate needs a stack-gate PASS receipt for the pushed `main`.
2. Box idle (no legs, no helpers). Check power 140 W / 28 V and `pgrep -fl "claude -p"` before anything. docker lives in `~/.orbstack/bin`.

## State

- Stage 3a readout (committed, `benchmark/results/m76/`): `B8.json` (Wave 1 10 / 10 + A7 5 / 5 pairs), `SIGNALS-partial.md` (C363: the
  panel readout; one Cursor verdict of 1152 failed, A2 39 / 40), `SIGNALS.md` (default sheet, panel not ingested). A1 +2.0 pp, loss bound
  0.0; A5 0 / 72 discordant, loss bound 9.2 pp; A7 +1.6 pp [−3.9, +7.8], loss bound 3.9 pp; panel all Holm p ≥ 0.65; directional: tg1 code
  quality leans N16 in all three sessions (0.40 / 0.43 / 0.49, none significant). README has a PROVISIONAL M76 row (update it with the panel).
- S26 agent-env change on `main` (`5c5b00eab`, C363): host-env fingerprint guard (sequencer + tg2 positives), positives decline rule,
  inject_verify alloc fix (S26-P14), bench-owned tg2 Gradle home (`$STACK_WORKDIR/tg2-gradle-home/`, prefilled + checked on this box, 45
  / 45 offline), bootstrap 5b toolchains (installed: rust 1.100, openjdk@21 linked, cmake 4.5). Report `docs/reviews/s26-agent-env/REPORT.md`.
- Also merged this session: S26-P8 (KV rehearsal harvest + watcher PYTHONPATH), S26-P15 / P15b (B8 rerun selection: a rerun only of a
  not-clean attempt with a recorded reason), S26-P16 / b / c (hook data exemptions), S26-P17 / P17b (C362: KV panel leak = arm / box identity).

## Next, in order

1. Stack gate: FAIL on `c34976a03` (S27-P3). After the reboot / race fix, gate again (the gate sha must be the arms' base).
2. DONE (session 27): tg2 arms `m76-g2-n16` (`c34976a03`) / `m76-g2-x` (`1b7833b6` = + cherry-pick `d4c44a9d`), venvs by
   `p475_kv._ensure_venvs`; X's `.venv-bench` got the wrong `cv2` again (S26-P10), fixed by reinstalling `opencv-python-headless==4.13.0.92`;
   pair inventory digests equal (`.venv` 8f21180f, `.venv-bench` b7e5d411, fork venv 370cbc5f; = the `m76-w2-*` arms). Both clean.
3. tg2 positives (`p426_wave2 positives --corpus tg2 --lever kv`, out `<out-base>/run/positives.json`, record the frozen prompt date) under the
   new rule; rehearsal (`p426_freeze rehearsal --corpus tg2` → `p426_wave2 rehearsal --corpus tg2`, out-base under
   `$STACK_WORKDIR/m76/p426/rehearsal.tg2/`, `--main-root` a scratch clone, P576), v8 (`--corpus tg2 --positives …`), the pilot pair
   (`p426_wave2 run --corpus tg2 --through tg2-m76-x-pilot`), the sizing report vs both budgets (S24-P9) → the stage-3b Go to the operator.
4. Beside the decider (no pytest during legs): the B4b-2 spec + design review (`docs/specs/m76-b4b2-a8-consumers.md`, to write; carry L9:
   every new tg2 consumer passes `grader="tg2"`; L16 `row_scores.py`). The KV vision rubric fix (S26-P19) before any next KV panel.
5. Small fail-closed fixes still owed: the PII hook learning the username pattern from the machine config (C357). S27-P2 (push-time
   binding of the receipt's `pushed_base`, rec B content binding) rides with the next gated code change if the operator agrees.

## Worktrees and scratch (each: resolution)

- `m76-w2-{n16,x}`: Wave 2 tg1 arms — outputs harvested (`benchmark/results/m76/wave2/`, evidence `8b45058f`); keep until stage 4 decides
  whether X legs are reused. `m76-q-{n16,x}` (Wave 1) and `m76-f45-*` (stages 1–4): keep until the stage 4 harvest.
- `m76-g2-{n16,x}`: tg2 arms for stage 3b (session 27) — keep through the A8 harvest.
- `s27-c366` (merged into `main` at `2673ca472`; submodules checked out) — remove. `evidence-s27` (local `evidence` commit
  `1c42f0ef`, tg2 positives evidence) — remove (`git worktree remove`; the branch keeps it).
- `m76-g-{n16,x}`: superseded tg2 arms (pre-S26 code) — remove once the `m76-g2-*` positives run works.
- Session 27 removed (harvested / merged): `fe-s26-*`, `s26-review`, `s26-p9-guard` (+ its merged branch), `evidence-pub`.
- Scratch: `$STACK_WORKDIR/review/s25-p10/` (cold-read clone; harvested to `docs/reviews/s25-p10/`) — remove. `gate/scratch/stack-67908a4b33eb-*`
  (2026-11-14, an unfinished gate run; regenerable) — remove.
- Scratch (keep): superseded first-pass Claude verdicts `m76/panel-claude-order2-first-pass/`, `panel-claude-order2-second-pass-A2/`
  (S26-P18), `m76/panel-strays/`, the archived real `~/.gradle` `archive/s26-dot-gradle-20261117/`, `m76/p426/tg2/attempt1-FAIL/`.

## Rules learned (session 26)

- An inject positive that asks the model to misbehave measures compliance; before calling a non-PASS a decline, check whether the model ran it.
- An agentic leg can mutate the host; the JVM ignores `$HOME` (Gradle needs `GRADLE_USER_HOME`).
- A judge context never holds both orders of one item; never declare a batch of helpers done without each one's report.
- A panel is frozen once, against the final B8; a pre-registered instrument rule changed after seeing data goes to the operator.
- Check new arms with the gate's inventory digest, not `pip freeze`; v8 needs a gate receipt for exactly the reference arm's commit.
- Each harvest re-imports `bench` from `main`'s working tree: while legs run, `main` takes docs commits only; helper briefs on stdin, never a
  BUSY marker in any argv; read-only reviews only between leg censuses.
- `brew uninstall` autoremoves orphans; a refused commit leaves files staged for the next one (check `git status` before committing).

## Rules learned (sessions 18–25, condensed; full text in git history of this file)

- Four-eyes implementers run named tests only; the full suite runs once as the gate. Allowlist exact command forms. A test timeout is a
  margin over a measured duration. "checked" names the check. Sweep docs for the username. A history rewrite renames later commits.
- Waiters match emitted names; run the real path early; refusals never echo PII. `bench.*` modules run from `benchmark/`.
- GPU stages and helpers running pytest cannot overlap. Measure memory per process. After a reboot start OrbStack before any gate.

## Archives (local, no push)

- `$STACK_WORKDIR/archive/tg2-universe-ff76573b/`, `archive/s26-dot-gradle-20261117/`, `m72/superseded-instrument-v{1,2}/`, `archive/p475-base-*`,
  `archive/session18-worktrees/`; branches `archive/*`.
