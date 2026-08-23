# Handoff — rewritten 2026-08-23 ~15:00 (M19/M20 closed; C picks set; HF namespace audited; M3 rerun arm 3 LIVE; vision restoration approved & staged)

Single box (M5 Max 64 GB), SINGLE attended session owns everything. If generate processes
you didn't launch appear (`pgrep -f "run.py generate"` / `run_opencode_probe`), investigate
ownership before acting.

## Standing footguns

- `run.py generate` DEFAULTS to the retired `production` profile (O36) — EVERY generate
  command carries `--sampling-profile deployed` EXPLICITLY.
- `run_opencode_probe.py` scratch dirs are realpath-resolved as of `bcc6d37` (macOS
  `/var`→`/private/var` alias broke opencode's project boundary → silent auto-rejects; the
  first M3 run was invalidated by it, rows quarantined at
  `$STACK_WORKDIR/status/m3/invalid_tmpdir_run/`). The M3 runner script ALSO exports
  `TMPDIR=$STACK_WORKDIR/scratch/octmp` (belt+braces).
- The opencode probe APPENDS rows (no resume) — dedupe before re-running a partial arm.
- A background waiter whose `pgrep` pattern appears in its own cmdline never fires
  (self-match) — quote-break the pattern or match the interpreter path.
- `Qwen3.8-27B` family chat template defaults `reasoning_effort=xhigh` <!-- allow-shorthand -->
  — the whole 3.8 corpus is measured at MAX effort (M24). The winners' templates lack the knob.

## LIVE right now (restart-safe)

**M3 opencode rerun**, driver pid 65405, nohup-detached, script
`$STACK_WORKDIR/status/m3/run_m3.sh` (exports TMPDIR; 22 python items/arm; rows →
`benchmark/results/<model>/opencode.jsonl`). Arm 1 `Ornith-1.0-35B-mlx-uniform-4bit` DONE
22/22; arm 2 `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` was 21/22 at ~13:25; arm 3
`Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` follows (~2.5 h; expect stall-kills — its
xhigh thinking wedges sessions; the progress gate bounds them at ~601 s). Logs:
`$STACK_WORKDIR/status/m3/arm_<model>.log`, driver2.log. **A fresh session must re-arm an
exit-waiter on pid 65405** (session waiters die with the session).

## On M3 completion (the sequence, all operator-approved)

1. **Score the 3 arms**: pass counts, stop_reasons, exclusive solves, per-arm wall stats;
   classify failures (permission-rejects should now be ~zero; nonzero → investigate before
   trusting). Ledger + PLAN M3 row; commit rows.
2. **One-image probe** on `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (expect vision ABSENT —
   tower stripped at conversion; confirms before surgery).
3. **M4**: opencode arm for `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (~40 min; same
   runner pattern; its known defect is malformed edits — that rate is the headline).
4. **Vision restoration (operator-approved plan, sources STAGED in HF cache: TeichAI +
   unsloth, 52 G each)**: (a) pick = TOWER GRAFT — quantize ONLY the vision tower (8-bit,
   operator-approved) from `TeichAI/Qwen3.6-27B-Claude-Opus-Reasoning-Distill-v2`, merge
   into the existing checkpoint; text trunk must stay BIT-IDENTICAL (tensor checksums) or
   STOP and report; (b) `Qwen3.8-27B-mlx-uniform-4bit` + `Qwen3.8-27B-static-mixed-4bit` =
   re-convert via the vision-retaining `mlx_vlm` path; uniform quant is deterministic →
   verify trunk bit-identity, mismatch → STOP. Per model: one-image smoke + 5-item text
   sentinel (unseeded requests are byte-deterministic — a real test). Re-upload to caslca
   with card note "text trunk bit-identical to the evaluated artifact; vision tower added".
   `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is architecturally text-only — NOT fixable
   (O38 revisit strike).
5. **Submodule bump** (operator: "soon"): fork `0be496bf`, submodule `0c1c8b17`, 125
   commits, output-determining. Recipe: pointer commit → `git submodule update --force` →
   router restart → `--limit 5` smoke + resolved-sampling readback (value ≠ registry
   default) + worker cmdline check (`ps -o command=`). `THINKING_BUDGET_CLAMP_RATIO` still
   0.8 (`generation.py:537`).
6. Then per PLAN §3: **M6a/M6c/M6d** predictor probes (nemotron_h_mtp + dspark need the
   bump; suffix leg gated on the agentic acceptance probe) interleaved with **M18 BFCL** →
   **M23** conversion-bias A/B → **M24** reasoning-effort diagnostic (effort must join the
   fingerprint FIRST — O36-class hazard) → M9 multi-language.

## Today's rulings (all executed, 2026-08-23)

- **O37 CLOSED**: t0.55 certified for `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`
  (registry-only fan-out — model in no client carrier).
- **O38 CLOSED then REVISED**: provisional C picks = `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
  (1st) + `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (2nd) — operator adopted the session
  recommendation; `Ornith-1.0-35B-mlx-uniform-4bit` is B-runner-up only. Recorded in
  registry comments + `docs/model-ledger.md` §1 (old "no C rec" section marked superseded).
- **Registry rules (AGENTS.md)**: `main_models.yaml` is the registry of record for B/C
  1st+2nd picks at certified params, updated in the SAME commit as any certification; picks
  must be public on HF from any org + a `caslca/` insurance clone; a pick ships as a
  **(model, tune, PREDICTOR) triple** — predictor certified by PLAN M6d, measurement stays
  predictor-OFF forever.
- **xhigh framing (M24)**: xhigh IS the target — best-quality reasoning with converging
  token patterns; medium is a diagnostic reference only.
- Certified tunes recorded in registry: `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` t0.6,
  `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` t0.55, `Qwen3.8-27B-mlx-uniform-4bit` t0.6.

## HF namespace (audited 2026-08-23, ALL DONE)

All 8 `caslca/` repos PUBLIC with corrected cards (true param counts — HF's badge
undercounts packed 4-bit ~6-8× and cannot be overridden; measured bpw from manifests —
`Ornith-1.0-35B-mlx-uniform-4bit` card was wrong at 4.649, measured 4.019;
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` card was wrong at 3.97, measured 4.97; certified
sampling on every card; the `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` mirror card created). `pipeline_tag` matches checkpoint
truth: towers present → `image-text-to-text` (`Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`,
`Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`, `Qwen3.8-27B-OptiQ-4.5bpw-mixed`); absent →
`text-generation` (`Qwen3.8-27B-mlx-uniform-4bit`, `Qwen3.8-27B-static-mixed-4bit`).
Weight uploads all complete + verified. Only `Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit`
stays local-only (Stage-0; upload deferred).

## Push state

origin/main = `bcc6d37` (verified via ls-remote). Local-only since: 43fb0ca, e8ea581,
078b049, 46873cb, 608b1fc, 7621040, 9bc4233, 8f226a1, e2337bf, 9857308, 473fc85 + this
checkpoint. NO push without explicit in-turn approval. Registry dirt = exactly 3 local
`hf_path` lines (the committed file carries caslca paths). `transcript.md` + NVSY stay
untracked. Commit dance for the registry: swap the 3 lines to their committed caslca form,
stage, commit, restore (pattern used 4× today, in the git log).

**Order of resumption: this file → `docs/PLAN.md` → `$STACK_WORKDIR/status/` (live runs).**
