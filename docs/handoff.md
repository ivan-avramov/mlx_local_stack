# Handoff — 2026-10-30 (session 12 END: C249 recorded → C258 MTP ON CERTIFIED for three entries; B2 ACCEPTED (C259) and landed on `main`; end-of-session push + drafter cards pending the gate)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C259, C258, P551, C257, P550, P547, P546,
C256, C255), `docs/specs/p426-b2-tg1-wave2.md` (v3.2; §16.8 to the end), `docs/PLAN.md` (the queue after B2). Model names: FULL registry
names only, always. Review rounds: 3 per artifact (AGENTS.md).

## FIRST, before anything else

1. **The end-of-session push (C259) may be unfinished.** Operator-approved as one push: stack `main` at level **full** (the gate on the
   tip, receipt read BEFORE pushing, P541) + the three drafter cards. Check: `git status`, `git log origin/main..main`, the gate log
   `$STACK_WORKDIR/gate/stack-<tip8>.log` and its receipt in `$STACK_WORKDIR/gate/`. If the gate FAILED or the tip moved, the push is
   not authorized — fix forward, re-gate, ask the operator again.
2. **Drafter cards** (C258 / C259): `caslca/{Qwen3.8-27B-mlx-uniform-4bit,Qwen3.6-27B-Opus-Distill-OptiQ-4bit,Ornith-1.0-35B-mlx-uniform-4bit}-mtp-drafter`
   `README.md` — a new section "Predictor-ON certification on the current runtime, 2026-10-30" + the card date; README only, no artifact
   change; uploaded with the push. If not yet uploaded, the edited copies are lost with the scratchpad: regenerate from the C249 README
   row (numbers there) and the live cards.

## State — 2026-10-30 ~21:30Z

- **C249 DONE** (README row "C249 MTP ON vs OFF memory + speed on S′"): normal-length decode ON / OFF `Qwen3.8-27B-mlx-uniform-4bit`
  1.72×, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 1.74×, `Ornith-1.0-35B-mlx-uniform-4bit` 1.45× (tight item intervals; outputs byte-identical
  60 / 60); 256K decode −13% / −6% (directional, P550) / −9%; 256K prefill-spike peak +0.3–0.5 GB. Rows on `main` (`80df5db8`).
- **C258**: MTP ON CERTIFIED for those three (registry annotations, README). `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` stays
  PROVISIONAL (C244) until Wave 2. TurboQuant-KV provisional labels (C189 / C202) unchanged.
- **B2 ACCEPTED (C259) and landed** on `main` as `97db61da` (the B2 benchmark diff through fix round 5 + the independent frozen set; one
  merge conflict in `local_gate.py` resolved: B2's lock `finally` + P541's level lines). Full suite on the clean candidate 8547 passed
  (+ 2 baseline-only s0 checks, by design); frozen set 525 / 527. Open items P552–P555 accepted per the designer's recs.
- **P547** (C249 part (2) ran without its monitor: launcher bug) fixed in `bench_watch.py`'s usage line (`b0adf0dd`, test red first).
- Pushed state: `origin/main` = `e3c70a79`; local `main` ahead by the session's commits (docs, data, C249, P547, C258, B2 filings, B2
  landing, registry note, handoff).

## Next, in order

1. FIRST 1–2.
2. **Wave 2 per PLAN** (B2 accepted): v8 freeze → rehearsals R1–R3 → pilots → amendment → Wave 2 legs (first pick
   `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; OFF arm = `main` + revert of the C244 hunk, P525) → B8 / B6. Read spec §1, §7, §9, §16.8
   before launching; run the sequencer as shipped from an arm worktree.
3. Optional (C258): a 128K / 192K `qualify.py` ABBA point per C258 entry to locate the 256K crossover (≈ 2 h GPU, descriptive) — a
   GPU filler while CPU-side work runs elsewhere, never during a gate or a suite.
4. P503 (load-sensitive stack tests).

## Copies to resolve

- `$STACK_WORKDIR/b2/*` — harvested (`97db61da`, reviews in `docs/reviews/p426-b2/`): delete after the push is confirmed (`chmod -R u+w`
  first for read-only review checkouts).
- Worktrees `stack-c249` (ON), `stack-c249-off` (all OFF): rows harvested; keep only if Next 3 runs, else `git worktree remove`.
  `stack-p369-full-off` (branch `p369-full-off`): remove. `stack-p426-s2-{off,on}` (branch `p426-on-s2`): until Wave 2's freeze.
- Fork roots `$STACK_WORKDIR/p369/fork-{1cce312f,a4cd07e0,fd67082a}`: C249 recorded — delete (keep `fd67082a` if Next 3 runs).
- `$STACK_WORKDIR/p541`, `p542`: delete. `$STACK_WORKDIR/gate/scratch/stack-574cf04b*` (a gate stopped by PID when B2 landed): delete.

## Rules learned (session 12)

- A measurement launcher checks its monitor is alive after start and stops the measurement if it died (P547); run `bench_watch.py`
  with `PYTHONPATH=benchmark`.
- A replicate claim needs the replicates read: "tight" held for two of three entries (P550).
- Never edit a running bash script (bash reads it incrementally).
- A wrapper whose default path is `set -- <path>` when `$# = 0` loses that default as soon as any flag is passed: give the path.
- A clean candidate copy without a local `main` fails merge-base tests: create `main` from `origin/main` before the full suite.
- Scratch commits in review copies bypass the public-repo scans: expect naming / PII findings when landing on `main` (variable names
  that look like model suffixes, placeholder home paths in fixtures → rename / `allow-pii-pattern`).
- Check a Write succeeded before committing what it wrote.

Next decision id C260; discussion ids continue from P555.
