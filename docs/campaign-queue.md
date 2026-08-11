# Campaign work queue (durable)

The comprehensive, durable backlog for the 256K agentic-coding selection campaign — a
candidate × axis status matrix feeding a per-box worklist, so a freed box always pulls its
next item (never "TBD"). Companion docs: results + rankings in `docs/campaign-results.md`
(the AGGREGATE record); process/recipes (sampling profiles, temperature-ladder, budget
mechanics, convergence rule, full-model-name rule) in `AGENTS.md`. **Keep this file current.**

**Box-split note:** each box has its OWN `benchmark/results/` — campaign state is scattered
across M2 + M5; `campaign-results.md` is the single aggregated truth. Two KV configs are
tracked per model: production-KV (4-bit, daily-driver) and the `-kv16` (bf16-KV) ceiling variant.

**Durability:** SURVIVES a reboot — this file + per-box `benchmark/results/*.jsonl` +
`.manifest.json` (generation RESUMES via done_ids; `--clean-stale` reconciles config). DOES NOT
survive — the nohup'd drivers + monitors. After a reboot, relaunch each `[RUNNING]` driver per
**Reboot recovery**. (Full registry names only — per the AGENTS.md rule; no shorthands.)

Last updated: 2026-08-11. **HARNESS V2 IS THE LIVE WORKSTREAM** (see below); **AGENTIC AXIS LIVE**; **local OptiQ self-convert capability CONFIRMED** (`.venv-optiq` = `mlx_optiq` 0.2.6, CLI `optiq`; we already self-converted the Opus-distill).

## HARNESS V2 — LIVE 2026-08-11 (build the harness before any more model runs)

Plan: `docs/superpowers/plans/2026-08-11-harness-v2-reliability-and-agentic-axes.md`. A critical
review found the 256K-agentic verdict rests on evidence that never exercised the claim: **no repeated
sampling** (every quality row is n=1 → most deltas are noise and run-to-run reliability is
unmeasured), **run-level convergence invalidation** discarding ~40 rows that get read anyway,
**agentic failure modes structurally invisible** (`agent_loop.py` counts no tool errors, no deadline,
no loop guard), **256K cleared on needle retrieval only** (vartrack/CWE built, never run, capped at
131K; all coding evidence <4K input), and **zero evaluation through opencode**, the declared primary
driver.

**Rev 2 after adversarial review (3 reviewers, findings spot-checked against the code).** Rev 1's
central premise — buy power with more samples per item — was **wrong** and is reversed:
`Var(pass@1) = σ²_btw/N + E[pq]/(N·k)`, so at N=15 going k=1→5 shrinks SD only 12.7→10.8pp (−14% for 5×
model time) while N=15→75 at k=1 gives −55%. **Items buy power; samples buy only reliability (k=2–3 is
enough).** MDE (paired binary, α.05/power.80, p_d≈0.2): N=15 → **±32pp**, N=40 → ±20pp, N=100 → ±12.5pp.
So the live deltas (LCB 6.7pp, aider 13pp) need N≈100–470 matched items. **"Inconclusive" is a valid,
likely answer** — if quality ties within resolution, Ornith's 4× decode + 5× memory margins decide.

Phases: **0** bootstrap (`.venv-bench`/`.venv-lcbgrade`/`config.sh` are all MISSING on M2; snapshot M5
results before touching provenance) + results-root seam + **`model_params.py` drift fix** (QWEN is
t0.7/min_p0.03/presence0.3 — none of it deployed, and the distill isn't even registered → every new
axis would mis-measure) + **APC policy** (`runserver.sh:74` sets `APC_ENABLED=1`, the AGENTS.md
benchmarking recipe omits it → past benchmark runs silently differed from the daily driver) · **1**
stats core: items-first power, **cluster bootstrap** (pooled Wilson is ~2× too tight), graded outcomes,
per-sample plumbing incl. the **`grade_evalplus`/`grade_lcb` bug that silently grades 1/k of the data**,
trace capture, recovery annotate-and-exclude, convergence **vector**, `compare` with TOST + Holm ·
**2** failure taxonomy + loop guard + deadlines + correct time-to-success + aider `.aider.results.json`
parse · **▶M1 GATE◀** matched-34-item Ornith-vs-distill aider H2H — *no phase starts until this row is
committed* · **3** BFCL **repaired** thinking-ON (kept: 0.94 vs 0.749 at n=1000 is ~12σ, the only
powered axis we own) + toolprobe as a labelled ±25pp *diagnostic* · **4** long context:
**distractor-padding OFAT** on existing graded items (isolates length from difficulty, paired by
construction) + haystack tasks with a **mandatory no-context control** (a pinned public repo is
training data) · **5** scorecard v2 + **breakage detector** (~40 items; explicitly NOT the ≤5% gate —
MDE ±20pp) + edit-format & canary preflights · **6** CONDITIONAL brownfield spec-to-feature, gated on a
saturation probe.

Decisions: **D1 THREE candidates, none excluded** — `Ornith-1.0-35B-mlx-uniform-4bit`,
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `gemma-4-31B-it-qat-6bit`. **256K is a goal, not a mandate:**
both reviewers argued for cutting gemma (192K ceiling per `main_models.yaml:55`; ~56 min/aider-case ≈ 9×
Ornith) and that was **rejected by operator decision** — characterise each candidate at what it *can*
do. Handled by: **per-candidate rungs** (gemma 0/64K/128K/192K, qwen-arch pair adds 256K) with
cross-model deltas at the **common rungs only** and the ceiling recorded as a config fact (never a blank
or a zero); gemma **sequenced after** the winners on whichever box is free so it never blocks the M1
verdict question; and the **edit-format confound measured first** (gemma runs `whole` because its
SEARCH/REPLACE diffs don't apply, the qwen-arch pair runs `diff` → the edit-format preflight moves to
P2/Task 2.4, before M1, and every cross-family agentic row carries the confound label).
**D2 revised: convergence is a VECTOR**, `(pass@1|converged, conv%, nonconv_kinds)` with `conv% ≥ 0.90`
as a gate and `pass@1|converged` ranking within it; `acc_strict@<budget>` is a derived deployment
number, never the ranking key (rev 1's strict-as-headline made `thinking_budget` a knob on the
headline, which AGENTS.md forbids). `acc` keeps its historical meaning. Needs the AGENTS.md amendment
in P1/Task 1.7 **plus a backfill/relabel of the ~40 legacy INVALID rows**. **D6 BFCL is repaired, not
replaced.**

**Stop-building rule:** if M1 is `inconclusive` AND P4 shows no length-dependent separation, the
verdict is settled on speed+memory margins — stop building axes and write it up.

**NOT PURSUED — operator decisions 2026-08-11, do not re-raise.** (1) **APC quality gate:** APC is a
serving-layer cache, **not a model capability**, so it is out of scope for the benchmarks. Its state is
still recorded as provenance (P0/Task 0.4) purely so speed rows are comparable — `runserver.sh:74` sets
`APC_ENABLED=1` while the AGENTS.md benchmarking recipe omits it, a knob worth 34–147× on TTFT, so past
benchmark runs silently differed from the daily driver. (2) **Vision axis:** not a primary focus, no
signal will be gathered; the registry advertises `vision` on every entry and the 4-bit converts' visual
tower stays an accepted untested capability rather than a measurement gap.

**Top remaining unmeasured gap (follow-on #1): multi-turn session depth.** Every axis, old and new, is
single-task and fresh-context; the daily driver fails at turn 40 with 180K of accumulated context.

All model-run items below are QUEUED BEHIND Phase 1 — re-running axes on the current harness would add
rows we can't rank on (and, via the evalplus/LCB per-sample bug, rows that would be wrong).

## PHASE 2 — OPTIMIZATION (perf + KV memory) — LIVE 2026-07-08
Spec: `docs/superpowers/specs/2026-07-07-phase2-optimization-program-design.md`. Winners:
`Ornith-1.0-35B-mlx-uniform-4bit` + `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Box split: M5 =
speed/mem (single-box, apples-to-apples) + LCB quality; M2 = parallel he+/mbpp+ quality + APC.
- **Baselines (M5, mx-peak = server_peak_gb):** Ornith fp16-KV = **32.6 GB / 37.9 tps decode /
  794 tps prefill @256K**, ret 1.0 (⚠ 128K ret 0.2 — RE-PROBE queued). distill 4bit-KV =
  **43.3 GB / 9.4 tps / ~124 tps prefill @256K** (2.7 GB headroom).
- **#1 APC prefix caching = DONE → SHIP:** lossless, flag-flip (`APC_ENABLED=1`). Agentic
  multi-turn TTFT **54.5×@7.5K → 147×@25K** (distill), **34×@25K** (Ornith); warm ~0.3–2 s flat.
  APC-on @256K fits gate on BOTH: Ornith 32.6 GB (=off), distill 30.8 GB. **No memory/speed cost.**
  Reuses only at prefix boundaries (growing-conversation agentic pattern); single-shot benches
  don't show it. **RECOMMEND: enable `APC_ENABLED=1` in the production router env.**
- **#2 quant-KV:** **Ornith KEEP fp16** (DONE — 4-bit is −27%/−60% speed for memory it doesn't
  need). **distill kv3 = PARKED** (2026-07-08): −2.9 GB but he+ gate (96.5% vs 95.7%) is too weak —
  ceiling'd short-chain coding does NOT stress KV fidelity; worry = multi-step math / precise
  retrieval. Needs math500+aime+multi-needle OFAT gate before adoption; deferred (low mem value).
  Insight: turboquant KV = memory-for-SPEED trade (slower than fp16).
- **#4 suffix decoding = DONE → SHIPPED both winners** (2026-07-09): quality-neutral (distill
  he+94/mbpp+77; Ornith he+93/mbpp+86/LCB93.3 ≈ OFF, conv intact, loops item-intrinsic) +
  speed-positive (distill 1.2–2.7× edit; Ornith 2.41× verbatim / 1.09× novel — the MoE-hostile
  prior was WRONG, linear-attn backbone keeps verify cheap). `draft_kind: suffix`, NO cooldown
  (phase-1: cooldown hurts reuse). Registry-side; carriers send presence_penalty 0.0 so it engages.
- **#5 fused GQA-tile-reuse DECODE kernel = DONE → SHIPPED** (fork bf7c793, submodule bumped):
  lossless (fp32-exact), ~1.3× over legacy TQ; +2–7% end-to-end (attention is ~10/40 layers of the
  hybrid models), does NOT beat native fp16 → Ornith stays fp16. Prefill MMA / Prod codec / gemma4
  generality = deferred follow-ons (low ROI — APC amortizes prefill).
- **#3 eviction / #6 MTP:** low ROI (hybrid attn / net-slowdown prior) — NOT PURSUED.
- **STATE @ 2026-07-09 — Phase-2 COMPLETE + FU-2 SHIPPED.** Shipped: APC (#1), suffix both winners
  (#4), decode kernel (#5). Ornith = fp16 KV + suffix; distill = tq-4bit KV + suffix. Stack pushed
  (`main` @ 7a1b311); forks pushed (mlx-serve 8333436, mlx-vlm 9f087c2); M2 + M5 deployed + router-restarted.
- **FU-2 (registry-side default sampling) = SHIPPED 2026-07-09.** Per-model `generation_defaults` in
  `main_models.yaml`, forwarded opaquely by mlx-serve, applied by mlx-vlm when a request omits a field
  (request > yaml > checkpoint > hardcoded; unknown key fails loud; resolved sampling logged at INFO).
  Closes the vscode/zed no-sampling gap — runtime-verified on M2+M5 (no-sampling distill request resolves
  to temp 0.3, not the checkpoint's 1.0). Spec: `docs/superpowers/specs/2026-07-09-registry-default-sampling-design.md`.
- **FU-1 (distill-kv3 gate) = PARKED 2026-07-09 with a staged plan.** Question: adopt turboquant
  **3-bit KV** on the distill? Saves **2.9 GB @256K, zero speed change**, on the *alternative* model
  (which already fits the 46 GB gate with headroom). Worry: 3-bit KV compounds attention error →
  degrades precise long-context retrieval + multi-step math; the he+ gate (96.5 vs 95.7) is too weak.
  **OFAT setup:** kv4 vs a `-kv3` registry variant (clone distill entry, `kv_bits: 4→3`, keep
  `generation_defaults`+suffix identical), same box/session; provenance stamps `kv_bits` so
  `--clean-stale` separates arms. Run on M5 (256K-capable, free). Needs a tiny `run_retrieval.py
  --temp` add (TDD) for a clean temp-0 fidelity read.
  **Cheap→heavy staging (fast-fail):**
  - **Tier 0 smoke (~15 min):** load `-kv3`, single-needle @64K temp0 → retrieves? (wiring + gross sanity).
  - **Tier 1 cheap reject filter (~1.5–2 h):** multi-needle (5×5) retrieval @{32K,64K,128K}, kv4 vs kv3,
    temp 0, samples 3. kv3 drops needles vs kv4 → **REJECT now**; kv3 ≈ kv4 → escalate.
  - **Tier 2 overnight gate:** multi-needle @{192K,256K} + math500 N=30 + aime N=15 @t0.3, kv4 vs kv3.
    **Adopt kv3 only if quality-neutral on BOTH** retrieval (per-depth ≈ kv4 @256K) and reasoning
    (pass@1 within single-sample noise + convergence intact). Any dramatic drop → keep kv4.
  **ROI note:** low value (2.9 GB on the alternative model, no speed) — do Tier 0+1 first, then decide
  whether the overnight is worth it. Full design context: chat 2026-07-09; spec-worthy if pursued.

## Quant question — CLOSED: uniform-4bit is Ornith's definitive config (2026-07-06)
Both "better quant" avenues investigated + closed:
1. **[DONE]** `Ornith-1.0-35B-mlx-uniform-6bit` OFAT — **NO quality gain**: light he+/mbpp+ **identical (90/80)**; LCB @t0.4 convergence **WORSE (7/15 vs 4bit's 12/15**, median 82K vs 32K, same budget). uniform-4bit is the quality ceiling (RL model is quant-robust). Recorded.
2. **[DONE — FAILED]** OptiQ-convert Ornith (`.venv-optiq/bin/optiq convert … --target-bpw 4.0 --reference auto`): MoE **loaded** in mlx_lm + calibration ran, but the mixed recipe APPLY failed — `Static mixed recipe failed: 30720 params not in model` (= 256 experts × 40 layers × 3 proj; OptiQ allocates bits per UNFUSED expert, mlx_lm loads them FUSED) → broken **8.376bpw/34G** artifact, not a valid 4-bit. **OptiQ mixed recipe does not support the qwen3_5_moe fused-expert layout.** 52G artifact `~/models/Ornith-1.0-35B-OptiQ-4bit/` reclaimable. Recorded.
→ **`Ornith-1.0-35B-mlx-uniform-4bit` is definitive.** Ornith-OptiQ ladder (was 6a) is MOOT.

## DISTILL — the re-opened candidate (temp-ladder RUNNING, 2026-07-06)
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (dense qwen3_5, Opus-reasoning distill, self-OptiQ 3.97bpw at `~/Documents/ws/models/.../optiq_mixed`) was DNF'd at official t0.6 ONLY — **never got the temp-ladder**. Now properly tested:
- **[RUNNING M2] LCB t0.4** (thinking_budget 81920): item 1 **CONVERGED** (24,341 tok) — DNF was a temp artifact. item 2 `abc358_e` errored (sleep) → needs regen. Watcher-driven. Log `/tmp` … `logs/distill_lcb_t04.log`.
- **[RUNNING M5] LCB t0.3** (parallel rung): `logs/distill_lcb_t03.log`. (Cross-box OK — convergence/pass@1 are box-independent; only speed/mem need same-box.)
- **[DONE] BFCL n=200 = 0.94** (s96/m96/p94/pm90) — tied with the gemma-MoE tool-calling leader. Recorded (flagged N=200).
- Distill is genuinely strong (Opus reasoning + 0.94 tool-calling + converges at low temp), BUT dense 27B → slower decode than Ornith's MoE; for 256K AGENTIC, Ornith's speed likely keeps it the pick. Finish the ladder → decide op-temp → then its other axes (light, agentic) if worth it.
- **NOTE — LCB pass@1 grading BROKEN** (see Blocked): ladders yield CONVERGENCE only until fixed; jsonls persist (re-gradable). Light pass@1 (evalplus docker) still works.

## AUTONOMOUS PLAN — user away ~hours 2026-07-06 evening (keep BOTH boxes busy; drive on watcher pings)
Fully characterize the DISTILL (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, re-opened candidate) at its op-temp,
split across both boxes. Both caffeinated (`caffeinate -i -s -w <pid>`) so idle-sleep won't disrupt.
- **M5 chain DONE (recorded):** distill @ t0.3 = he+ **100%** / mbpp+ 60% / aime **100%** (4/4) / math500 **80.8%**,
  all **100% conv**. (BFCL n=1000 re-run ABANDONED — `run_bfcl` couldn't find the `bfcl` CLI in the ssh env even
  with `.venv-bench/bin` on PATH; the n=200 **0.94** stands + raw preserved. NB each failed run_bfcl clobbers
  `bfcl.json` to null — re-parse raw or ignore; scoreboard is truth.) **NOW RUNNING: distill CAPACITY ladder to
  256K** (`bash benchmark/run_capacity_seq.sh Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, grid 160/192/224/256K, log
  `logs/distill_capacity.log`, watcher). KEY question: does the distill (qwen3_5 dense + linear-attn, kv_bits4)
  clear 256K ≤46GB like Ornith? 160K already = 28.6GB/ret1.0 → very likely yes. On finish → record + it becomes
  a full 256K competitor (Ornith still pick on MoE decode speed). LCB pass@1 still blocked (datasets bug).
- **M2:** distill **LCB t0.4 DONE** = 9/15 (60%) conv (+1 err abc358_e) → confirms op-temp 0.3 (vs t0.3 15/15).
  abc358_e regen SKIPPED (t0.4 stays INVALID regardless; op-temp settled). **Now RUNNING distill AIDER** n=5 @
  t0.3 diff (agentic axis — the one M5 isn't covering): `bash benchmark/run_aider_docker.sh
  Qwen3.6-27B-Opus-Distill-OptiQ-4bit 5 diff distill-diff-t03`, log `/tmp/aider_distill_t03.log`, container
  `aider-Qwen3_6-27B-Opus-Distill-OptiQ-4bit` (survives session). Added distill entries to
  `aider_config/aider.model.settings.yml` (diff, temp0.3, budget81920) + M2 aider-clone `model-metadata.json`
  (context 131072). Dense-27B + diff-format (qwen arch, proven w/ Ornith).
  - **n=5 DONE = 80% pr2 (4/5), CLEAN** (well-formed 100%, 0 loops/ctx-exhaust, ~14.5min/case — agentic-viable,
    not prohibitive). Highest of the 4, BUT n=5 small-sample (cf Ornith n=10 80%→n=34 62%). **NOW RUNNING n=34**
    (`distill-diff-t03-n34`, log `/tmp/aider_distill_n34.log`, container survives, watcher) to confirm vs regress —
    direct parity with Ornith's n=34. On finish → grep pass_rate_ → record. If it holds ~70%+, distill = top
    agentic ALTERNATIVE (then worth a 256K-capacity probe); Ornith still pick (faster MoE + proven 256K).
- **RECOVERY if session drops (nohup survives, watchers + caffeinate do NOT):** re-check `pgrep -f "run.py generate"`
  + `logs/m5_distill_chars.log` on M5, `logs/distill_lcb_t04.log` on M2; relaunch any dead driver (M5 driver =
  `/tmp/m5_distill_chars.sh` but edit the `kill -0 5704` guard if 5704 is gone → just run its 3 generate/BFCL cmds);
  re-apply caffeinate; re-launch background pollers. Grades are re-runnable (jsonls persist). M5 IP churns — subnet-scan.

## Status matrix (✓ done · ~ running · ◻ pending · ⚠ stale/blocked · – n/a)

| candidate (full name) | arch | capacity | light | LCB (prod-KV) | notes |
|---|---|---|---|---|---|
| gemma-4-26B-A4B-it-OptiQ-4bit | MoE | ✓ | ✓ | ✓ (temp-ladder → keep t0.7) | lead MoE 4-bit |
| gemma-4-26b-a4b-it-8bit | MoE | ✓ | ✓ | ✓ | +kv16 LCB ✓ |
| gemma-4-26b-a4b-it-4bit | MoE | ◻ | ✓ | ✓ INVALID (over-reasons) | dominated |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | MoE | ✓ | ✓ | ✓ INVALID (loop-prone) | dominated |
| gemma-4-31b-it-6bit | dense | ◻ | ✓ | ✓ **86.7%** (conv 12/15) | +kv16 LCB ✓; beats MoE |
| gemma-4-31b-it-UD-MLX-4bit | dense | ✓ | ✓ | ✓ **86.7%** (conv 14/15) | cleanest LCB conv; beats MoE |
| gemma-4-31B-it-qat-6bit | dense | ◻ | ✓ **AIME 100%/100%conv** | ✓ 80% (conv 14/15) | **convergence + reasoning leader** |
| Qwen3.6-27B-UD-MLX-6bit | dense | ✓ | ✓ | ⚠ DNF-MEANDER (item1 ct82507>81920, ~114min/item) | 3rd Qwen-arch LCB DNF; +kv16 LCB ✓ |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | MoE-distill | ✓ | ✓ | ⚠ DNF-MEANDER (median 82,855>bud) | |
| Qwen3.6-27B-OptiQ-4bit | MoE | ✓ | ✓ | ✓ | only prod-KV Qwen LCB done |
| Qwen3.6-27B-MLX-8bit | MoE | ◻ | ⚠ DNF (meander) | ◻ | DEPRIORITIZED; +kv16 LCB ✓ |
| Ornith-1.0-35B-mlx-uniform-4bit | MoE-hybrid | ✓ **256K@32.4GB, ret1.00** | ✓ (he90/mbpp80 VALID; aime 1 budget-hit) | ✓ **80%@t0.4** (op-temp; conv 12/15; =0.3 pass@1 but better conv; 0.5/0.6 meander) | GATE PASS (first true 256K); fast; agentic DONE (aider 61.8% pr2); BFCL DONE (74.9%, last of 3); NEXT=(optional) uniform-6bit quality variant |

**Higher tiers — `◻` PENDING for ALL candidates** (none run): math500, IFEval (⚠ blocked), GPQA,
BFCL (tool-calling), Aider polyglot, SWE-Verified-40 (agentic), judge panel.

## Per-box worklist (pull next from here)

### M5 (256K-capable, quiet box)
1. **[DONE]** Qwen3.6-27B-MLX-8bit — light: **DNF/DEPRIORITIZED** (MEANDERING non-convergence,
   82K-token budget-saturating traces incl. easy coding; suspect the unsloth 8bit checkpoint;
   8-bit won't fit ≤46GB@256K). See campaign-results.md.
2. **[DONE]** gemma-4-31B-it-qat-6bit — light: STANDOUT (HE+ 100% / MBPP+ 80% / AIME 100%, all
   100% convergence, all VALID). Graded + recorded.
3. **[DONE]** M5 LCB sweep:
   a. gemma-4-31B-it-qat-6bit LCB ✓ — 80% (E100/M86/H60), conv 14/15 (cleanest dense conv).
   b. Qwen3.6-27B-Opus-Distill-OptiQ-4bit LCB ⚠ **DNF-MEANDER** (stopped at 8/15; median 82,855 >
      budget) — same pathology as Qwen3.6-27B-MLX-8bit.
4. **[DONE — DNF]** Qwen3.6-27B-UD-MLX-6bit LCB @ qwen official — **DNF-MEANDER** (2026-06-26):
   item 1 (id 3496) `finish=stop` but `ct=82507 > 81920` budget = NON-CONVERGED, ~114 min/item,
   driver ETA ~26h → cut at N=1 (strong priors: prior run 11–17h ETA + 8bit + distill both DNF'd).
   3rd Qwen3.6-27B-arch LCB DNF. Recorded in campaign-results.md.
5. **[DONE]** math500 (N=30) gemma-4-31B-it-qat-6bit @ production — **83.3% / 100% conv / VALID**
   (median 2409). All 3 dense gemmas done on math500. Recorded in campaign-results.md.
6. **[DONE — light + capacity + LCB-ladder complete; op-temp 0.3] deepreinforce-ai/Ornith-1.0-35B** (uniform-4bit).
   **VERDICT (2026-06-27):** light he+90/mbpp+80 (100% conv); capacity **256K@32.4GB, retrieval 1.00** (first to
   clear true 256K); LCB temp-ladder → **80% pass@1 @ t0.3** (E100/M71/H80, conv 73% — the KNEE; meanders @0.5/0.6).
   Operating temp for Ornith coding = **0.3**. **NEXT = agentic axes** (its self-scaffolding differentiator) + a
   rung-0.6 re-run to pin the pass@1 baseline (0.6/0.5 raw lost to /tmp cleanup). Historical detail below.
   - **2026-06-26 STATUS:** converted (uniform-4bit, ~19GB, 4.649bpw, M5-local registry entry, uncommitted)
     + smoke-loaded (all keys map) + canary-generated coherent code. Decode is FAST: **69 tok/s** (linear-attn
     payoff, ~5-7x the dense gemmas). Light tier (he+/mbpp+/aime) RUNNING @ official **temp 0.6** (pid via
     logs/ornith_light_t06.log), launched DIRECTLY (run.py generate, --clean-stale) — see CANARY note below.
   - **CONVERGENCE — the open question:** Ornith inherits the qwen3_5_moe meander. Preflight canary @ PRODUCTION
     **temp 0.7** MEANDERED on a trivial is_palindrome: finish=stop but ct=49221 > 49152 budget = NON-CONVERGED
     (cousin Qwen3.6-27B-UD-MLX-6bit converged the same canary in 1941 tok @ 0.7). BUT manual canary @ **temp 0.6**
     converged is_prime in 1369 tok → sharp temp knee. Running light tier @ 0.6 to test convergence on real benches;
     if it meanders @ 0.6 too → temp-ladder (0.5/0.3) or DNF. Watcher reports first-items convergence.
   - **HARNESS ISSUE (preflight-profile mismatch):** preflight.py run_canary HARDCODES production params
     (temp 0.7), ignoring the run's :official profile → false-fails qwen-arch models we eval @ 0.6. FIX (TDD):
     thread the sampling profile through preflight.sh -> preflight.py:run_canary. Queued.
   - **LOADER FIX SHIPPED 2026-06-26** (fork f0d50c9, stack submodule bump af992b6, synced to M5):
     `qwen3_5_moe.sanitize` now tolerates the UNFUSED per-expert layout (stacks
     `experts.{e}.{proj}.weight` → `switch_mlp.{proj}.weight`); fused Qwen3.6-VL path preserved.
     TDD: `mlx_vlm/tests/test_qwen3_5_moe_sanitize.py` (both layouts, 24 tests pass). The fork's
     `qwen3_5_moe` already implements the full hybrid arch (GatedDeltaNet `linear_attn` + full-attn,
     MoE with `shared_expert` + router) — this sanitize gap was the only blocker.
   - **NEXT (needs M5 free — currently running math500 on qat-6bit):**
     (i) smoke-load real Ornith via PYTHONPATH, confirm ZERO missing/unexpected keys;
     (ii) `python -m mlx_vlm.convert --hf-path <snap 5df2ed3f> -q --q-bits 4 --mlx-path <out>` (uniform-4bit, ≈27GB);
     (iii) M5-local uncommitted `main_models.yaml` entry (kv_bits 4, max_kv_cache_size, prefill_step_size 512);
     (iv) capacity `mx.get_peak_memory`@256K → retrieval → LCB → BFCL native-FC → SWE-Verified-40.
   - a. [DONE] BF16 → 65G / 16 shards in cache (snapshot 5df2ed3f).
   - b. **ROOT CAUSE (2026-06-26):** NOT a simple prefix issue. Ornith is a **hybrid linear-attention
     MoE** (Qwen3-Next-style): layers use `linear_attn.*` (A_log/conv1d/dt_bias/in_proj_qkv|a|b|z/
     out_proj), MoE = router `mlp.gate` + **256 UNFUSED experts** (`experts.{0..255}.{gate,up,down}_proj.weight`)
     + a **shared expert** (`mlp.shared_expert.*` + `shared_expert_gate`), all under the VL wrapper
     (`model.language_model.*` + `model.visual.*`). config: model_type qwen3_5_moe / text qwen3_5_moe_text,
     40 layers, 256 experts / 8 active, moe_intermediate 512, shared_expert_intermediate 512, tie=False.
   - `mlx_vlm.convert` (right tool, routes through `qwen3_5_moe.sanitize`) FAILED:
     `KeyError: model.language_model.layers.0.mlp.experts.gate_up_proj` — the fork's sanitize expects
     the **fused** Qwen3.6-VL expert layout, Ornith ships **unfused** experts + a shared expert.
   - **FIX (engineering, attended):** patch `../mlx-vlm/.../qwen3_5_moe/qwen3_5_moe.py:sanitize` to
     STACK the 256 unfused `experts.{e}.{proj}.weight` → 3D `switch_mlp.{proj}.weight`, handle the
     `shared_expert` keys, and CONFIRM the fork's `language.py` actually implements the `linear_attn`
     layer (conv1d handling in sanitize suggests yes — verify). Smoke-load via PYTHONPATH before
     converting. Alt route: mlx_lm `qwen3_next` text loader + key-remap (strip `model.language_model.`,
     drop `model.visual.*`). **QAT is NOT possible for us** (training-time).
   - DECISION PENDING: worth the port vs deprioritize? Front-runner (dense gemma-4-31B) is already clear.
   - EVAL (if built): capacity @256K → retrieval → LCB → BFCL native-FC → SWE-Verified-40.
   - MEMORY @256K: uniform-4bit + 4-bit KV ≈ 27GB; uniform-6bit + 4-bit KV ≈ 36–40GB — both fit ≤46GB.
     (OptiQ NOT reachable via `mlx_vlm.convert` — q_modes are affine/mxfp4/nvfp4/mxfp8; OptiQ = separate tool.)

### M2 (local laptop, ≤192K only — co-resident ~22GB)
1. **[DONE]** dense-gemma LCB @ production t0.7: gemma-4-31b-it-6bit **86.7%** (conv 12/15) +
   gemma-4-31b-it-UD-MLX-4bit **86.7%** (conv 14/15) — both BEAT the MoE (80%, H60→H80) with
   cleaner convergence. Graded + recorded.
2. **[DONE]** math500 (N=30) @ production — graded 2026-06-26: gemma-4-31b-it-6bit **83.3% / 100%
   conv / VALID** (median 2000); gemma-4-31b-it-UD-MLX-4bit **83.3% raw but 67% conv / INVALID**
   (over-reasons, median 8165, 10 loops — 4-bit tail-fragility). With gemma-4-31B-it-qat-6bit
   (83.3% / 100% conv / VALID, M5) → all 3 dense gemmas done on math500. Recorded in campaign-results.md.
3. **[NEXT — on M2-idle, ATTENDED first-run]** Aider polyglot SMOKE (`--limit` small) on the dense
   front-runner (gemma-4-31b-it-6bit / UD-4bit), then full Aider → SWE-Verified-40. CORE agentic
   axes, never run — the real "256K agentic coding" test. Box-idle monitor pings M2-IDLE → launch.
4. **[QUEUED]** BFCL native-FC on the lead gemma candidates.

## Backlog (unassigned — priority order)
1. **Finish LCB across ALL candidates** (the differentiator) — partly in the worklists above.
2. **Agentic axes: Aider polyglot + SWE-Verified-40** on LCB survivors — the campaign's CORE; built, never run.
3. **BFCL native-FC** (tool-calling) — built, never run.
4. **Judge panel** (Sonnet+Opus+codex, blind, over execution-PASSING outputs only) — built, never run.
5. **math500 + GPQA** (reasoning) — built, never run.
6. **New candidates to acquire:** Qwen3.6 oMLX-6bit, Qwen3.6-27B-MTP variants.
7. **WATCH-FOR-RELEASE — `deepreinforce-ai/Ornith-1.0-31B` (Dense, Gemma-4-based):** announced in the
   Ornith-1.0 blog/news (family = 9B Dense / **31B Dense (Gemma-4)** / 35B MoE (Qwen-3.5) / 397B MoE),
   but NOT yet on HF as of 2026-06-26 (authoritative API list with token = 35B/9B/397B only; the 31B repo
   404s). HIGH PRIORITY when it lands — it's our converging dense front-runner's base (gemma-4-31B) PLUS
   Ornith's self-scaffolding agentic-coding RL, directly targeting the campaign's open differentiator.
   Re-check HF periodically. (35B MoE = ours, already converted/eval'd. 9B Dense available now but below the
   64GB capability target — low value.)
8. **Effective-context curves** (retrieval-depth + reasoning-depth, kept SEPARATE; retrieval
   partial, reasoning-depth not started) — the ≥0.85 gate.
9. **bf16-KV ("kv16") ceiling sub-study** — kv16 LCB exists for Qwen3.6-27B-MLX-8bit /
   Qwen3.6-27B-UD-MLX-6bit / gemma-4-26b-a4b-it-8bit / gemma-4-31b-it-6bit; extend + compare vs
   production-KV per the quality-first plan.

## Blocked
- **IFEval**: `datasets` load fails "Feature type 'List' not found" (version incompatibility) — fix
  before the instruction-following axis runs; the sweep currently skips it (acc:null, no crash).
- **LCB pass@1 grading** (diagnosed 2026-07-06): ROOT CAUSE = **`datasets 4.8.5` removed `trust_remote_code`**,
  and LCB `code_generation_lite` is a **script-based** dataset; `lcb_runner`'s `load_code_generation_dataset`
  calls `load_dataset(..., trust_remote_code=True)` → hard fail (`trust_remote_code is not supported anymore`).
  (The HF cache is also incomplete — `.incomplete_info.lock`, no `.arrow` — from the network churn.)
  **Generation is unaffected** (it reads the cached prompts JSON `~/.cache/livecodebench/lcb_<rel>_prompts.json`);
  only GRADING needs the full script-dataset load (test cases). **Convergence still grades from the jsonl**
  (the temp-ladders' primary signal); only LCB *pass@1* is blocked. Affects 6bit LCB + both distill ladders.
  **FIX (deferred — needs stable network; do NOT downgrade `.venv` in-place while runs use it):** make a
  dedicated `.venv-lcbgrade` with `datasets<3` (e.g. 2.21.0) + `lcb_runner` grading deps, clear the incomplete
  cache (`rm -rf ~/.cache/huggingface/datasets/livecodebench___code_generation_lite`), re-download, and grade
  via that venv's python. jsonls persist → all LCB pass@1 is re-gradable retroactively. Light pass@1 (evalplus
  docker) is unaffected.
  **RESOLVED 2026-07-07:** built `.venv-lcbgrade` with **`uv venv --python 3.11`** + `uv pip install
  'datasets<3' json_repair requests numpy` (pyext NOT needed — codegen_metrics grades pass@1 without it; the
  py3.12 pyext build wall is avoided by py3.11). LCB dataset loads (880 problems) + grading works. Grade any LCB
  run with: `PYTHONPATH=$HOME/.cache/livecodebench/LiveCodeBench .venv-lcbgrade/bin/python benchmark/run.py grade
  --models <M> --benches livecodebench`. Retroactively graded: distill t0.3 = **80% (E100/M86/H60)**; 6bit in progress.

## Gating policy
- Breadth-first: capacity → light → LCB → (survivors) reasoning/tool → agentic → judge.
- **NO pruning on partial results** — cuts decided only across the full suite.
- Emerging signal: DENSE gemma-4 converges where the MoE loops (gemma-4-31B-it-qat-6bit leads);
  the MoE's edge is decode speed. Pending the LCB-differentiator completion + agentic axes.
- Gates: ≤46GB MLX-peak @256K (≤56GB browser-closed, metric = `mx.get_peak_memory`); M2 ≤192K;
  ONE resident model per box; judge over execution-PASSING outputs only; two eff-ctx curves separate.

## Reboot recovery
1. Restart the router (per-box recipe in AGENTS.md): `MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start …` → :8000.
2. For each `[RUNNING]` item, relaunch its driver (`lightsweep.sh`/`tempsweep.sh`, same args) — it resumes from disk via done_ids / `--clean-stale`.
3. The deferred wrappers + box-idle/per-model monitors are unreliable across M5 IP changes — drive M5 MANUALLY against this worklist; find M5 by ssh-scanning the subnet (`nc -G 3`, not `-G 1`).
4. Sanity-check with `benchmark/preflight.sh` before trusting a resumed run.
