# Handoff — 2026-09-03 11:10 (M21b hep k=3 DONE/PROVISIONAL; mbpp k=3 IN FLIGHT; C47 SHIPPED; docs reorganized)

Single box (M5 Max 64 GB). **ONE detached job is LIVE:** the M21b mbpp chain (`$STACK_WORKDIR/m21/mbpp_chain.py`,
pid `m21/mbpp.pid`, log `m21/mbpp.log`, driver logs `m21/mbpp_*.log`; relaunched 11:02 with `MBPP_SKIP_PILOT=1`
after the 5-item pilot gate false-aborted at a 24.3 h projection — the seeded first-5 draw holds two heavy
cores, `Mbpp/306` and `/620`; hep's actual k=3 cost was 102 s/draw). It runs mbppplus n=50 × k=3 on
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 (15 pilot rows resume in place) then
`Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` @t0.6-r2, grades both, compares (+ `--intersect`), ends with
`=== M21b MBPP DONE ===`. Expect 8–12 h. Router UP on the M21 overlay (`$STACK_WORKDIR/m21/bench_overlay_m21.yaml`,
sha `90b3606c…`). **`src/mlx-vlm` WORKTREE IS PINNED at `57177a21`** (stack pointer `7330d3a6`); the chain refuses
to start otherwise. Restore with `git -C src/mlx-vlm checkout 7330d3a6` only after M21b closes (with C47 landed
the pin no longer matters for pairing — `57177a21` ≡ `7330d3a6` on the serving path — but keep it until then).

Stack pushed through `b723bde`. **UNPUSHED: `6ae5772` (docs reorg), `19e6fbb` (C47), + this handoff commit** —
push needs in-turn approval. Working tree: the SIX intentional `main_models.yaml` overrides (NEVER commit),
`M src/mlx-vlm` (the pin, NEVER commit), the live mbpp rows.

## When `=== M21b MBPP DONE ===` appears
Run `.venv-bench/bin/python $STACK_WORKDIR/m21/k3_analysis.py` after pointing its `BENCH`/tune constants at
mbppplus (it hard-codes `humanevalplus`; make `BENCH` a CLI arg), read `m21/grade_mbpp_*.log` and
`m21/compare_mbpp*.log`, and apply P28 on the independent item set: mean strict ≥ ref − 1 item AND (paired
tokens-per-task ratio < 1 with CI excluding 1 OR fewer meanders at equal accuracy). hep k=3 (campaign-results
2026-09-03) met (2a) marginally (0.658, CI [0.39, 0.98], tail-driven; ordinary items 0.83 CI spans 1).
**Decision rule agreed with the operator: mbpp confirms (ratio < 1, CI excluding 1) → the recipe is real →
upload `optiq_mixed` to `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` + registry entry (this checkpoint
is NOT a B-menu pick, so no menu change); mbpp near 1 → hep was three items' tails, recipe stays uncarried.**
Present data + verdict + recommendation; joint review before any registry change. Then commit rows as
`data(bench)`, campaign-results entry, PLAN M21b row → DONE, restore the submodule pin, delete
`$STACK_WORKDIR/optiq_out/…/optiq_mixed` only if the recipe is NOT carried.

## Landed this session (2026-09-02 evening → 2026-09-03 morning)
- M21b hep k=3 (`c4216b9`): strict 44.67 vs 45.00 INCONCLUSIVE; tokens ratio 0.658 [0.39, 0.98]; PROVISIONAL.
- Community-thread + JetBrains review (P43–P48): nothing contradicts the corpus; the one untested claim is
  instruction following → **M31** (ifeval arm for `Qwen3.8-27B-mlx-uniform-4bit` @t0.6, paired with the
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` row) queued after mbpp + C46.
- **C47 SHIPPED (`19e6fbb`)**: fingerprint v5 = serving-path tree hash (spec `docs/specs/c47-serving-path-fingerprint.md`;
  exclusions in `provenance.py`); `compare` refuses on serving-path mismatch, warns on commit-sha mismatch;
  older manifests derive the hash from their recorded sha. The mixed mbpp arm's manifest is v4, the reference
  arm's will be v5 — derivation pairs them (same hash).
- **Docs reorganized (`6ae5772`)**: `docs/superpowers/`, `docs/sketches/`, `docs/work-queue.json` DELETED (git
  history is the archive, last present at `b723bde`); `docs/specs/` holds design docs; `docs/README.md` is the
  index; PLAN.md is the ONLY queue.
- Pre-session untracked rows committed (`5b8f4de` M27/M6d certification rows, `3ea3d9c` M23 rows); C46 filed.

## THE BOX QUEUE (after mbpp)
1. M21b review (above). 2. **C46** pre-C28 timeout re-measurements (open-questions row; `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`
first, then the M25 pair), full n=50 re-runs. 3. **M31** ifeval arm (~2 h). 4. M17 / D11 / M18.

## Standing rules that bit this session
- A 5-item seeded pilot can OVER-project when the draw lands on heavy cores (2/5 here): size from the pilot
  AND the nearest full-run actual; an abort gate on the pilot mean alone false-aborts. Relaunch = resume.
- The commit-msg hook rejects family shorthand in commit bodies ("the uniform-4bit arm") — name the model. <!-- allow-shorthand -->
- zsh: `for x in $VAR` does not word-split; `--include=*.py` needs quoting. Use arrays / quotes.
- Chain scripts must read `BENCH` after `exec`-ing shared helpers (the mbpp chain sets it explicitly).

## Artifacts
`$STACK_WORKDIR/m21/` (chains, logs, `k3_analysis.py`, overlay); `$STACK_WORKDIR/notes/` (the video transcript
that was in the repo root); the mixed artifact `$STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed`
(18 GB, KEEP until M21b closes). HF cache: `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source <!-- allow-shorthand --> (54 GB, deletable).

**Order of resumption: this file → `$STACK_WORKDIR/m21/mbpp.log` (alive? done?) → `docs/PLAN.md` (M21b, M31) → `docs/open-questions.md` (C46, C47).**
