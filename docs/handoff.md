# Handoff — 2026-11-04 (session 17: P426 DONE + pushed; P475 stage 1 four-eyes build IN FLIGHT (C292), contract `docs/specs/p475-stage1-contract.md` v1.1)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C292, P644, P643, P642, C291, P640, P638, C290, C289, P633, P632, C288, C287, P631, C286, C285, P629, P628, P627,
C284 … C276), then `docs/specs/p613-step4-contract.md` + `docs/reviews/p613-step4/dispositions.md`. Model names: FULL registry names
only. Review rounds: 3 per artifact (more only on the operator's word). Operator stance: "keep going towards certifying MTP for the
picks"; bias for quality; updates every 15–20 min; ask only at Go / Accept / pushes / scope changes; lead calls filed as they land.

## THE GOAL

Decide, with evidence the operator can act on, whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships with MTP ON (P426; C204: the
operator makes the call from per-axis signals). The evidence is ONE generated `benchmark/results/p426/SIGNALS.md`. Steps 1–3 are
committed in it; step 4 (divergence section + FINAL) is built and waiting for Accept; then the recommendation. After that, the same
certification for `Qwen3.8-27B-mlx-uniform-4bit`, whose KV choice (P475 matrix, C280 rebuild) comes first.

## Session 17 status (2026-11-04)

- **Pushed (C291):** `main` `c1375c49..fdfcef48` (level full, receipt `…-6dd0867a4d0f`) and `..67df67e6` (docs-only);
  `archive/p426-wave1-s2-on` (`8055b219`, receipt `…-6dd0867a4d0f`, new remote branch).
- **P426 DONE — SHIP ON (C291):** `801ca28d` moves the registry annotation PROVISIONAL C244 → `CERTIFIED P426 2026-11-04` (served
  state unchanged: MTP ON since C244), README evidence row, campaign-results 2026-11-04, PLAN status. Its gate FAILED 1 / 11,026 on
  the P642 race (below) — not on the certification change.
- **P642 = P433 (C209, approved 2026-10-22, never implemented):** the v2 pre-check's plugin-load proof read `/api/config` stderr,
  which does not await plugin activation; ≈ 1 in 7 failures under load. Fixed test-first (`6cb26e40` red → `1c36c451`), proof from
  `/api/integration` with the caller's env; 0 / 40 stressed runs fail; review Sol + GLM (`docs/reviews/p642/`). **Gate on
  `1c36c451` PASS** (11,034 passed, receipt `…-6dd0867a4d0f`). Push ask: `main` `67df67e6..1c36c451` (full) + docs tail.
- Done this session: P632 (pin split, C289), P633 verify, P613 step 4 accepted (C290) + FINAL sheet `3ad97c5e`, P638 (skip
  baseline), P640 (first-divergence bounds only the identical-context prefix: 439 / 439 messages).
- `gate/RUNNING` is a persistent flock file — never wait for its absence; queue gates on the previous receipt's appearance.

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

1. **P475 stage 1 build (C292 Go), four-eyes light**, contract `docs/specs/p475-stage1-contract.md` v1.1 (`bc3ad13e`):
   `Qwen3.8-27B-mlx-uniform-4bit` only; arms N16 / AF8 / TQ8 / AF4 / TQ4 (base) / TQ4-OFF. Cast: implementer Claude Opus 5.5
   (`claude -p`, worktree `$STACK_WORKDIR/worktrees/p475s1-impl`), test-writer Claude Sonnet 5.5 (`claude -p`, resumable, worktree
   `p475s1-tests`, tests in `benchmark/bench/tests/p475s1/`), panel GPT-5.6 Sol High + GLM 5.2 read-only (`p475s1-panel`). Outputs
   `$STACK_WORKDIR/scratch/p475s1/{impl,tw-d1}-out.json` (session ids inside). Next: freeze the d1 tests (copy + time) BEFORE revealing
   the candidate → d2 (resume the test-writer session) → panel opinion → one fix round → Accept ask → commit → gate → push ask → on
   the box: `prepare`, preflights, N16 smoke (grid 8192), full run (≈ 13 h GPU).
2. Open small items: P643 (timing test, proposal), the two P642 process gaps (gate keeps no failure detail; an approved fix went
   unqueued).
3. After the KV choice: `Qwen3.8-27B-mlx-uniform-4bit` MTP ON vs OFF re-certification on S′ (P426 process, tooling reused).

## Worktrees / scratch (resolve each)

- Removed this session (resolved; untracked material archived to `$STACK_WORKDIR/archive/session17-worktrees/<name>.{tgz,files,diff}`):
  p613s2-*, p613s3-*, p613s4-*, p624-*, p627-*, p632-diag, p624-wave1-on; fork p475a-*; local branches `p475a-kv-arm` (fork) and
  `archive/p426-wave1-s2-on` (both equal to their pushed refs).
- Carried: `stack-p426-off`, `stack-p426-on`, `stack-c258x-off` (+ local branches `archive/p426-rehearsal.20261102a-*`,
  `archive/p426-wave2.v8-*`), the `$STACK_WORKDIR/p426/*` and `scratch/*` inventory. P426 is done: proposing their resolution
  (harvest check → remove) is a next-session item.

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

Next decision id C293; discussion ids continue from P646.
