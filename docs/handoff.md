# Handoff — 2026-11-04 (session 16: P613 steps 2–3 done; P624 / P627 gate rules; P475a in the fork; next: P613 step 4 → the MTP call)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C287, P631, C286, C285, P629, P628, P627, C284 … C276),
then `docs/specs/p613-step4-contract.md` (next build) and `docs/specs/p613-b8-b6-signals.md` v2. Model names: FULL registry names only.
Review rounds: 3 per artifact (P627 needed 4, operator-approved each). Operator stance: "keep going towards certifying MTP for the picks";
bias for quality; updates every 15–20 min; ask only at Go / Accept / pushes / scope changes; file lead calls in open-questions as they land.

## THE GOAL

Decide, with evidence the operator can act on, whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships with MTP ON (P426; C204: the
operator makes the call from per-axis signals). The evidence is ONE generated `benchmark/results/p426/SIGNALS.md`. Steps 1–3 are in it;
step 4 adds the generated A7 first-divergence section (C284) and the FINAL status; then the recommendation. After that, the same
certification for `Qwen3.8-27B-mlx-uniform-4bit`, whose KV choice (P475 matrix, C280 rebuild) comes first.

## Where the evidence stands (all generated, committed locally on `main`)

- A1 math500 strict 96/100 vs 96/100 (0 discordant; loss ruled out above 3.0 pp); A2 / A3 / A4: outputs byte-identical ON vs OFF.
  Wave 1: 166 / 166 keys identical. Decode ON / OFF 1.54–1.78× (A1–A4), 1.65× A7, 1.20× M1 256K; M1 prefill peak +0.31 GB.
- A7 tg1: strict WASH both sessions (s1 −2.3 pp, s2 +2.3 pp). P629 (exploratory, to be generated in step 4): ON vs OFF never first
  diverge in generation (0 / 86); 49 first diverge at a tool output (clock / ASLR), 35 identical, 2 cut-offs.
- Panel (step 3, 83 / 84 verdicts; Claude Opus 5.5 blind-judge + GPT-5.6 Sol High): A7-s1 0.728 [0.475, 1.000], A7-s2 0.670 [0.433,
  0.826], Holm 0.196 both — WASH, ON lean direction only; write it as "no quality loss shown" (C286 correction: both intervals include 0.5).
- Flags: acceptance < 0.70 on A2 / A3 (P620; speed still 1.5–1.8×); rule-6 cross-wave (admitted, C276); runaway-tax cut-off asymmetries (P616).

## FIRST — verify

1. Nothing running (`local_gate`, `cursor-agent`, `claude -p` helpers); :8000 free.
2. The two background gates of this session's end finished: `$STACK_WORKDIR/scratch/gate-e6986d9e.txt` (expected PASS) and
   `gate-8055b219-r3.txt` (expected PASS with `baseline_skips_absent` = the two `test_b2_frozen_s0_support` entries).
3. `origin/main` = `c1375c49`; local `main` ahead (step 3, P631, P627, the panel, docs) — the push ask is pending (below).
   Fork `../mlx-vlm` `origin/main` = `d94e38a9` (P475a, pushed). `evidence` = `b6ec7819`.

## Next, in order

1. **Push ask (operator):** `main` — the gated code tip `e6986d9e` (level full), then the docs-only tail; `archive/p426-wave1-s2-on`
   (`8055b219`) once its re-gate PASSes (P624 / P627). Push homogeneous slices (P541).
2. **P613 step 4** (contract `docs/specs/p613-step4-contract.md`, needs the operator's Go): four-eyes light; the divergence section
   + FINAL status; regenerate the sheet with `--panel benchmark/results/p426/panel --evidence-ref b6ec7819`; gate; push ask.
3. **The MTP call** to the operator: per-axis signals, flags with their items, a recommendation (registry change only with approval;
   certified triple per PLAN M6d; client configs per AGENTS; P426 §11 restore steps).
4. **P475** (stack, C280 rebuild): v4 spec ready (`docs/specs/p475-kv-matrix.md`, R1–R22); its build needs a Go; P475a is in the fork and
   the stack gitlink (`85535982`, P631 pin amended). P628: the second pick's quantized-KV arms are refused by mlx-serve under `fused_v1`.

## Worktrees / scratch (resolve each)

- Remove after the push: `$STACK_WORKDIR/worktrees/{p613s2-impl,p613s2-tests,p613s2-panel,p613s3-impl,p613s3-tests,p613s3-panel,
  p624-impl,p624-tests,p624-panel,p627-impl,p627-tests,p627-panel,p475a-tests,p475a-panel}` (all harvested into commits / docs/reviews);
  `p475a-impl` (fork worktree, branch `p475a-kv-arm` = pushed `d94e38a9`): remove + delete the branch; `p624-wave1-on`
  (`archive/p426-wave1-s2-on` checkout): remove after the archive push. Carried from session 15: `stack-p426-off`, `stack-p426-on`,
  `stack-c258x-off`, the `$STACK_WORKDIR/p426/*` and `scratch/*` inventory.

## Rules learned (session 16)

- Park on a branch or under `$STACK_WORKDIR`, never in a session scratchpad, and check the path exists before recording it (P626:
  the parked P475 candidates were lost to the /tmp cleanup; C234 named a path that never existed).
- Check the receipt's testcases before naming a gate cause (P627: "ran and passed" was really "file absent").
- A brief that names an example file must check it does not exist (D1: the step-2 module overwrote the Wave 1 sequencer).
- Mocked tests miss real-server facts: check the live code path (P475a fix 1: `sdpa_forced` is omitted under `auto`) and real git
  history shapes (P627 v1.2: the archive commit is divergent, not an ancestor).
- Read an interval's endpoints before calling it "above 0.5" (C286).
- Copied helper reports can carry home paths: redact before committing (the PII hook caught one).

Next decision id C288; discussion ids continue from P632.
