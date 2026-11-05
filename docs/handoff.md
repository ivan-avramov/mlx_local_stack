# Handoff — 2026-11-04 (session 17 IN PROGRESS: P632 fixed; P613 step 4 ACCEPTED + committed, FINAL sheet `3ad97c5e`; gates running; MTP call (P637) with the operator)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P638, C290, C289, P633, P632, C288, C287, P631, C286, C285, P629, P628, P627,
C284 … C276), then `docs/specs/p613-step4-contract.md` + `docs/reviews/p613-step4/dispositions.md`. Model names: FULL registry names
only. Review rounds: 3 per artifact (more only on the operator's word). Operator stance: "keep going towards certifying MTP for the
picks"; bias for quality; updates every 15–20 min; ask only at Go / Accept / pushes / scope changes; lead calls filed as they land.

## THE GOAL

Decide, with evidence the operator can act on, whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships with MTP ON (P426; C204: the
operator makes the call from per-axis signals). The evidence is ONE generated `benchmark/results/p426/SIGNALS.md`. Steps 1–3 are
committed in it; step 4 (divergence section + FINAL) is built and waiting for Accept; then the recommendation. After that, the same
certification for `Qwen3.8-27B-mlx-uniform-4bit`, whose KV choice (P475 matrix, C280 rebuild) comes first.

## Session 17 status (2026-11-04)

- **P632 (C289) done** (`65cf2171`): `BASE_GITLINKS` = `1c7c8fa1` (build-s2 arm world), `LIVE_GITLINKS` = `d94e38a9` (s0 identity
  only). Its gate: pytest 10,912 passed, FAIL only on a stale skip (P638).
- **P613 step 4 ACCEPTED (C290)** after verify P633 (Sol + GLM: all 7 resolved; GLM M1–M3 = P634–P636 declined): code + tests
  `81c39a00` (suites 935 passed, 3 skipped); FINAL sheet `3ad97c5e` (byte-identical twice, B8 identical; the two step-4
  committed-sheet goldens bind and pass).
- **P638** (`fdfcef48`): p613s2 committed-sheet golden added to `benchmark/gate/stack.skips.txt` (superseded by steps 3–4; the
  `b4b69886` precedent). The baseline is in the policy digest → every receipt must be re-earned under it.
- **Gates running (serial; `gate/RUNNING` is a persistent flock file — never wait for its absence):** `fdfcef48` (log
  `$STACK_WORKDIR/scratch/p633/gate-fdfcef48.log`), then `8055b219` under the new digest (expected PASS, the p613s2 entry in
  `baseline_skips_absent`). If the session died: check `$STACK_WORKDIR/gate/stack-{fdfcef48,8055b219}*` receipts; rerun if absent.
- **P637 — the MTP call is with the operator** (ship ON as `CERTIFIED P426 2026-11-04` recommended; per-axis table in the session-17
  transcript = the FINAL sheet). On "ship": the P426 §11 restore in one commit (the `46ca41b9` registry + seeding-test hunks,
  `CERTIFIED P426 2026-11-04`, README / campaign-results rows; no client sampling change), gate, push ask.

## FIRST — verify (each "no" is a blocker)

1. Nothing running (`local_gate`, `cursor-agent`, `claude -p`); :8000 free.
2. The two gates started at session end (they may have been killed with the session): look for the newest receipts in
   `$STACK_WORKDIR/gate/` — `stack-e6986d9e…-<digest>.json` (expected PASS: step 3 + P631 + P627; the previous tip `e2f45998` failed
   1 / 10,849 only on the B2 pin that P631 fixes) and a NEW `stack-8055b219…-<digest>.json` (expected PASS with
   `baseline_skips_absent` = the two `test_b2_frozen_s0_support` entries). If either is missing, rerun:
   `cd benchmark && PYTHONPATH=. ../.venv-bench/bin/python -m bench.local_gate run --repo stack --sha <sha>` (source the machine config).
3. `origin/main` = `c1375c49`; local `main` = `ab9328b9`+ (step 3, P631, P627, the panel, the step-4 contract, docs). Fork `../mlx-vlm`
   `origin/main` = `d94e38a9` (P475a, pushed). `evidence` = `b6ec7819`.

## Next, in order

1. **P613 step 4 Accept (operator).** Candidate = `$STACK_WORKDIR/worktrees/p613s4-impl` (uncommitted: `benchmark/bench/p426_signals.py`,
   new `benchmark/bench/p426_signals_divergence.py`; diff saved at `$STACK_WORKDIR/worktrees/p613s4-tests/.p613-material/candidate-fix.diff`).
   Frozen tests: `$STACK_WORKDIR/worktrees/p613s4-tests/.p613-material/frozen-d3/p613s4/` (110 passed, 2 skipped — the 2 skip until the
   FINAL sheet is committed). One fix round done (fixes 1–4: malformed tool events refuse; FINAL needs b1 + b2 per axis;
   `evidence_ref` = full sha + `evidence_ref_given`; `--evidence-ref` without `--panel` refuses). Golden: 0 / 86 generation-first
   (s1 18 identical / 24 environment / 1 cutoff; s2 17 / 25 / 1). Panel opinion (Sol + GLM) done; no verify run yet (budget allows one).
   After Accept: copy the two modules + `bench/tests/p613s4/` into `main`, run the suites (`p613 p613s2 p613s3 p613s4 test_p426_panel
   test_p371_r7_consumers test_p426_wave1`), commit `feat(bench)`, regenerate with `p426_verify all` + `p426_signals all --panel
   results/p426/panel --evidence-ref b6ec7819` (check byte-identical twice), commit the sheet `data(bench)` BEFORE gating (a skip test
   binds on it), gate the tip, push ask.
2. **Push ask (operator):** `main` gated tip (level full) then the docs-only tail (P541 slices); `archive/p426-wave1-s2-on` (`8055b219`)
   once its re-gate PASSes.
3. **The MTP call** to the operator: per-axis signals from the FINAL sheet, flags with items, a recommendation. Facts to carry:
   - A1 96/100 vs 96/100 (0 discordant; loss ruled out above 3.0 pp); Wave 1 166 / 166 keys byte-identical; decode 1.54–1.78× (A1–A4),
     1.65× A7, 1.20× M1 256K; M1 prefill +0.31 GB.
   - A7 strict WASH both sessions; divergence 0 / 86 generation-first (49 environment: 46 of them vanish when digit runs in tool
     output are masked — clock / ASLR; 35 identical; 2 cut-offs).
   - Panel WASH (Holm 0.196 both; A7-s1 0.728 [0.475, 1.000], A7-s2 0.670 [0.433, 0.826]; both include 0.5): write "no quality
     loss shown", not "improves", not equivalence (C286 / C172).
   - Flags: acceptance < 0.70 A2 / A3 (P620; speed still 1.5–1.8×); rule-6 cross-wave (admitted C276); runaway-tax cut-off asymmetries
     (P616).
   - Ship-ON steps: P426 §11 restore (registry `CERTIFIED P426 <date>`, seeding test, README / campaign-results rows), PLAN M6d triple,
     client configs per AGENTS — registry change only with approval.
4. **P475** (stack, C280): v4 spec (`docs/specs/p475-kv-matrix.md`, R1–R22) needs a Go; P475a is in the fork + stack gitlink
   (`85535982`, pin amended P631); P628 (the second pick's quantized-KV arms are refused by mlx-serve under `fused_v1`).

## Worktrees / scratch (resolve each)

- Keep until step 4 is committed: `$STACK_WORKDIR/worktrees/{p613s4-impl,p613s4-tests,p613s4-panel,p613s4-verify}` (verify outputs
  harvest into `docs/reviews/p613-step4/verify-{sol,glm}.md`).
- `p632-diag` (session 17; diagnostic, pin reverted, nothing to harvest — logs in `$STACK_WORKDIR/scratch/p632/`): remove now-safe
  after the `65cf2171` gate PASS.
- Remove after the push (all harvested into commits / `docs/reviews`): `{p613s2-impl,p613s2-tests,p613s2-panel,p613s3-impl,p613s3-tests,
  p613s3-panel,p624-impl,p624-tests,p624-panel,p627-impl,p627-tests,p627-panel,p475a-tests,p475a-panel}`; `p475a-impl` (fork worktree,
  branch `p475a-kv-arm` = pushed `d94e38a9`): remove + delete the branch; `p624-wave1-on` (`archive/p426-wave1-s2-on`): after its push.
  Carried: `stack-p426-off`, `stack-p426-on`, `stack-c258x-off`, the `$STACK_WORKDIR/p426/*` and `scratch/*` inventory.

## Rules learned (session 16)

- Park on a branch or under `$STACK_WORKDIR`, never in a session scratchpad; check the path exists before recording it (P626).
- Check the receipt's testcases before naming a gate cause (P627: "ran and passed" was really "file absent").
- A brief that names an example file must check it does not exist (the step-2 module overwrote the Wave 1 sequencer).
- Mocked tests miss real-server facts and real git shapes: check the live code path (P475a: `sdpa_forced` omitted under `auto`) and
  the real history (P627 v1.2: the archive commit is divergent, not an ancestor).
- A gitlink bump moves the B2 frozen pin `BASE_GITLINKS` in the same change (P631, P520 precedent).
- Read an interval's endpoints before calling it "above 0.5" (C286).
- Copied helper reports can carry home paths: redact before committing; verbatim judge text can trip the naming hook (programming
  keywords) — model output is data (the P613 exemption), never reworded.

Next decision id C291; discussion ids continue from P639.
