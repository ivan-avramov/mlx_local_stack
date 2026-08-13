# Campaign work queue (durable)

The comprehensive, durable backlog for the 256K agentic-coding selection campaign — a
candidate × axis status matrix feeding a per-box worklist, so a freed box always pulls its
next item (never "TBD"). Companion docs: results + rankings in `docs/campaign-results.md`
(the AGGREGATE record); process/recipes (sampling profiles, temperature-ladder, budget
mechanics, convergence rule, full-model-name rule) in `AGENTS.md`. **Keep this file current.**

**⚠️ BOX TOPOLOGY CHANGED 2026-08-11 — the M2 Max 64GB laptop is GONE.** Local is now an **M4 Pro,
48GB**, which after the ~22GB AI session has ~26GB headroom and therefore hosts **NO campaign
models** (stricter than the old M2 Max, which was merely unreliable >192K). **ALL model runs now go
to M5 — there is ONE worker box, so the old parallel box-split is dead and remaining work
SERIALIZES.** The driver does harness dev, grading, orchestration and docs only. Every `M2`
reference below is HISTORICAL: those results are not re-measurable (apples-to-apples bars cross-box
baselines and the box no longer exists), so anything needing a LIVE baseline must be re-run on M5.

**Box-split note:** each box has its OWN `benchmark/results/` — campaign state is scattered
across the retired M2 Max + M5; `campaign-results.md` is the single aggregated truth. Two KV configs are
tracked per model: production-KV (4-bit, daily-driver) and the `-kv16` (bf16-KV) ceiling variant.

**Durability:** SURVIVES a reboot — this file + per-box `benchmark/results/*.jsonl` +
`.manifest.json` (generation RESUMES via done_ids; `--clean-stale` reconciles config). DOES NOT
survive — the nohup'd drivers + monitors. After a reboot, relaunch each `[RUNNING]` driver per
**Reboot recovery**. (Full registry names only — per the AGENTS.md rule; no shorthands.)

Last updated: 2026-08-11. **HARNESS V2 IS THE LIVE WORKSTREAM** (see below); **AGENTIC AXIS LIVE**; **local OptiQ self-convert capability CONFIRMED** (`.venv-optiq` = `mlx_optiq` 0.2.6, CLI `optiq`; we already self-converted the Opus-distill).

## ▶ STATE 2026-08-13 — Tier-0 rev A audited + rev B running; suffix nondeterminism isolated

### The "runaway worker" in handoff §1 had already cleared itself — premise was WRONG
The abandoned distill request did **not** need killing: it **completed at 23:40:06** (200,
`completion=39479`, `prompt=16214`, 10.4 tok/s, 3,801,911 ms = **63.4 min**) and the model
**idle-unloaded cleanly at 02:36:56** after 14,412s. At 07:47 there was no `mlx_vlm.server` process
at all and no python burning CPU — only a healthy 14h-old router. So the cost was ~63 min of worker
time, not an open-ended burn. Note it also **CONVERGED** (39,479 < 81,920 budget), which is what
makes the cell's cost a *task-scope* problem rather than a model pathology.
Router nonetheless restarted for a known-clean baseline: **exactly one listener on :8000, APC var
count 0 (checked on the pid, not assumed), health 200, 4 models registered.**

### P2 TIER-0 rev A — Ornith arm VERIFIED, then audited; two design defects found
Archived off volatile `/tmp` to `~/mlx_bench_snapshots/tier0-2026-08-12/` (11 JSONs + logs, all 11
md5-distinct → the stale-copy failure did NOT recur). Claim **confirmed at the per-draw level**:
**33/33 draws converged, 0 budget hits, all `finish_reason=stop`**, max 40,607 tok vs 81,920 budget;
`converged_rate` 1.0 and `budget_hit_rate` 0.0 in all 11 cells; 0 label-vs-param mismatches.
**⇒ There is no convergence knee for Ornith at these settings — an ANSWER, not a null.**
**⇒ P3's ρ on `conv%` is UNDEFINED for Ornith** (a constant vector has no rank correlation), and
P3's other half — per-config *agentic* results — does not exist yet (P4 unrun). Full detail +
the two defects (inert `min_p`/`top_p`/`top_k`; a mis-specified collapse cell that was an exact
duplicate of `t0.4_mp0.0`) in `docs/campaign-results.md`.

### ⚠️ DETERMINISM IS CONFIG-DEPENDENT — suffix decoding is the source, truncation masks it
The suffix isolation test was run **before** touching that config, and the naive version of it
would have been CONFOUNDED. 2x2 (suffix {ON,OFF} × truncation {deployed 0.95/20, none 1.0/0/0.0}),
Ornith, 3 reps, byte-identity on sha256 of reasoning+content, suffix verified OFF **at the worker
cmdline**:

| | truncation ON | truncation OFF |
|---|---|---|
| **suffix ON** (shipped) | identical 1 sig/3 | **DIVERGENT 3 sigs/3** (ct 2,825/4,467/3,736) |
| **suffix OFF** | identical 1 sig/3 | identical 1 sig/3 |

**KEEP SUFFIX ON** — measured 1.27× faster same-box/same-session (23.8s vs 30.3s mean), and the
deployed config truncates, so every client and every `deployed`-profile row is already on the
reproducible path. But **AGENTS.md's "unseeded requests are byte-identical" now carries a
condition**, and rev A's `min_p=0.0` column (4 of 11 cells) was measured on the nondeterministic
path. Probe: `benchmark/bench/probe_determinism.py` (+15 tests; suite 544 → **559 green**).

### ✅ P2 TIER-0 rev B COMPLETE — 22/22 cells, both models, **50 min total**, zero failures
Full table in `docs/campaign-results.md`. Headlines:
- **Determinism fix CONFIRMED independently:** rev B's duplicate-config pair (`collapse_3knob` ≡
  `t0.4_mp0.0`) is **byte-identical on both models**, where rev A's equivalent pair diverged.
- **Convergence SATURATED: 66/66 draws converged, 0 budget hits, all `finish=stop`.** Neither winner
  has a knee anywhere in temp 0.2–0.6 × min_p 0.0–0.15. **⇒ `conv%` is the wrong screen metric** —
  it has no variance for either winner, while cost varies **47×** within one model.
- **Ornith is FLAT** (coding 2,921 → 2,016 tok, 31 → 24 s as temp rises; no instability anywhere).
  **The distill is unstable at temp 0.6:** one draw ran **52,833 tok / 16.6 min** on the same problem
  it does in 1,122 tok / 41 s at temp 0.4 — and `conv%` scored it a clean pass. Independently
  **confirms the distill's op-temp 0.3** from a new task and harness path.
- **`min_p` is inert at low temp and only bites at high temp:** at 0.2 all three values are
  byte-identical; at 0.4 only 0.15 differs; at 0.6 all three differ. So a `min_p` axis is only
  meaningful above ~0.4 — rev A's inertness was not merely a spacing choice.
- **Collapse test PASSES, properly specified** (genuine min_p-only comparator) ⇒ 4D→2D validated in
  the regime tested.
- ⚠️ **HARNESS DEFECT:** `run_convergence` uses `driver.complete`'s default **3600 s** timeout while
  `thinking_budget` is 81,920. At the distill's 10–16 tok/s on long prompts the budget needs
  **85–136 min**, so a genuine `budget_hit` is **UNOBSERVABLE** — the client abandons at ~37–58K
  tokens and the worker keeps generating. This IS the rev-A cascade mechanism (that cell ran 3,802 s
  vs the 3,600 s timeout). Fix proposed, NOT applied: derive the timeout from
  `thinking_budget ÷ measured decode rate`, or fail loudly when it is below that ratio.

### ✅ P1a opencode go/no-go — **GO** (all gates pass), after fixing a blocker in our own config
- ⚠️ **BLOCKER, now confirmed:** `configgen/emitters/opencode.py:17` emits a top-level
  **`_generated`** key; opencode 1.18.15 rejects the file outright (`Unrecognized key: _generated`),
  so **zero requests reached :8000** and every gate failed `rc=1`. Removing only that key makes the
  config load with all four models. **This would have been misread as "#5674 confirmed, opencode
  unusable"** — cancelling the plan's primary driver over a defect in our own emitter.
  **FIX PROPOSED, NOT APPLIED** (awaiting authorisation): drop `_generated` from the opencode
  emitter's doc. `configgen/emitters/vscode.py:11` also emits it, but into an array element for a
  different consumer — **verify separately, do not assume broken**. No configgen test asserts on
  `_generated`, so the fix needs a new test pinning that the opencode doc has no unrecognized
  top-level keys.
- **With that fixed, #5674 does NOT affect 1.18.15 and the tuned sampling genuinely LANDS:**
  (a) endpoint reach 200; (b) `max_tokens: 7` → `completion=8` vs 45 baseline (standard AI-SDK
  path); (c) `thinking_budget: 16` → `completion=261` vs **740** baseline (non-standard extras path);
  (c′) `enable_thinking: false` → `completion=200` **and the prompt count shifts 18,093 → 18,095**,
  i.e. it reached the worker and changed the chat template. (b) and (c) are different mechanisms, so
  (b) alone would not have implied (c); both pass. (d) `opencode run` is a real non-interactive mode.
- **Measured cost for the gradient:** opencode sends **~18,050 prompt tokens for a four-word
  request**. That is the heavy end quantified — budget ~18K prefill per turn. `pi` is still absent
  from both boxes.
- Caveat: results are **opencode 1.18.15 only** (driver box is 1.18.0; #5674 is version-dependent).
  `small_model` still points at :8092, which the lean bench router does not start.

### (superseded) ~ RUNNING — P2 TIER-0 rev B, 22 cells, both models (`benchmark/m1/tier0b_grid.sh`)
Launched 08:08. Three evidence-forced changes vs rev A, all scope/ordering — **no generation param
was touched** (capping `max_tokens` was explicitly REJECTED: it would manufacture the
non-convergence the screen measures, per AGENTS.md):
1. **task = `vartrack`, not `aggregation`@8K.** Measured on the distill: aggregation = 39,479 tok /
   **63.4 min per sample**; vartrack = **550/558 tok / ~31 s**, converged, acc 1.0. Full cell
   **2m04s** instead of >2h — a ~60× cell-cost reduction, and it drops the synthetic word-tally
   that the handoff itself flagged as a poor agentic proxy.
2. **truncation held at deployed** `top_p 0.95 / top_k 20` → every cell deterministic.
3. **`min_p` spacing widened** to 0.0 / 0.05 / 0.15 (0.0/0.02/0.05 was inert).
Collapse test re-specified with a genuine min_p-only comparator (`min_p 0.05`, top_p/top_k off).
Archive is DURABLE: `~/mlx_bench_snapshots/tier0b-2026-08-13/`. Param verifier
`benchmark/m1/tier0b_check.py` now checks **all four truncation knobs + presence_penalty +
thinking_budget + max_tokens** (rev A's checked only temp and `min_p` — blind to the very knobs
rev B depends on), and was smoke-tested in BOTH directions before use.

### P1a opencode go/no-go — two blockers found before spending worker time
- **(c) PASS on inspection:** `opencode run [message..]` is a real non-interactive mode.
  opencode is installed on both boxes, but versions SKEW (driver 1.18.0, M5 **1.18.15**) and
  #5674 is version-dependent. **`pi` is ABSENT on both boxes** — confirms the plan's note.
- **⚠️ M5's DEPLOYED opencode config is STALE and predates both winners.**
  `~/.config/opencode/opencode.json` lists `gemma-4-31b-4-256`, `Qwen3.6-27B-UD-MLX-6bit` etc. and
  **neither `Ornith-1.0-35B-mlx-uniform-4bit` nor `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`**. The
  repo's generated `opencode_config/opencode.json` is correct (tuned sampling + `presence_penalty
  0.0`); it simply was never deployed. The smoke deploys it and restores the backup after.
- **⚠️ THE GATE AS SPECIFIED IS NOT EXECUTABLE — there is no resolved-sampling log line.**
  AGENTS.md/FU-2 says "resolved sampling is logged at INFO"; the fork has **no such line**
  (no log of the merged params in `mlx-vlm/mlx_vlm/server/generation.py`), and the live worker logs
  confirm it — mlx-serve sends worker **stdout to DEVNULL**, only stderr to
  `$TMPDIR/mlx-manager-logs/<model>.log` (`process_manager.py:387`, truncated per load), which
  contains no sampling fields. **And a resolved-sampling line would not answer the question
  anyway:** under FU-2 the registry fills every omitted field, and opencode's configured values are
  IDENTICAL to the registry's — so "temperature=0.4" appears whether opencode forwarded it or sent
  nothing. Readback must use a value that DIFFERS from the registry default.
  **Replacement (behavioural, reads `completion=<n>` off mlx-serve's own metrics line):**
  `benchmark/m1/p1a_opencode_smoke.sh` — gate A endpoint reach; gate B `max_tokens: 7` (standard
  AI-SDK param path); gate C `thinking_budget: 16` (non-standard extras path). **B and C are
  different mechanisms and can disagree; C is the one the campaign depends on, so B-pass/C-fail is
  a NO-GO for tuned comparisons through opencode, not a partial success.**
  Runs after rev B (opencode would swap the resident model and evict the grid's).

## ▶ STATE 2026-08-12 — M1 SETTLED; CAMPAIGN V3 IS THE LIVE PLAN

Plan: `docs/superpowers/plans/2026-08-12-campaign-v3-two-role-selection.md` (rev 2, after three
adversarial reviews). **The campaign now targets TWO outputs, not one winner: a CODER and an
interactive DAILY DRIVER.** Models (incl. quant technique/level/distillation) are the INPUT that
changes over time; sampling config and KV quant are searched inputs; context reach and speed are
MEASURED, not gated. **APC is OFF everywhere and out of scope** — not an axis, not discussed.

### M1 GATE — COMPLETE at n=110 (runs `m1f` + `m1g`, 2026-08-12). Coder role: the distill.
All 5 languages x 22 pinned-by-name exercises, both arms, RAN-filtered. `distill/java` comes from
the `m1g` re-run after a TCC failure truncated it in `m1f`; the truncated dir is excluded by the
RAN filter (empty `tests_outcomes`), not by a hand-maintained skip list.

| metric | Ornith-1.0-35B-mlx-uniform-4bit | Qwen3.6-27B-Opus-Distill-OptiQ-4bit | delta | McNemar exact |
|---|---|---|---|---|
| **final (<=2 attempts)** | 55/110 = **50.0%** | 81/110 = **73.6%** | **+23.6pp** | **p = 1.3e-05** |
| attempt-1 | 27/110 = 24.5% | 36/110 = 32.7% | +8.2pp | p = 0.122 (n.s.) |
| **repair rate** | 28/83 = **33.7%** | 45/74 = **60.8%** | — | — |
| mean/case | 2.17 min (4.0h total) | 8.42 min (15.4h total) | 3.9x | — |

Exclusive solves: only-Ornith **5** (`python/forth`, `javascript/list-ops`, `go/counter`,
`java/bank-account`, `java/dominoes`) vs only-distill **31**. **Every language favours the distill**
(python +13.6, javascript +36.4, go +13.6, rust +27.3, java +27.3pp) — the result is not carried by
one language.

**MECHANISM: it is REPAIR, not raw capability.** Attempt-1 differs by only +8.2pp and is NOT
significant (p=0.122); the distill's edge is that it fixes its own failure when shown the failing
test 60.8% of the time vs 33.7%. Per-arm well-formed was 90.9-100% for Ornith and 100% for the
distill, so `diff` handicaps neither.

Config: APC absent, `deployed` sampling, `max_kv_cache_size` 65536 (right-sized for this axis;
memory/speed here are NOT comparable to a 256K row), aider `diff`, `tries=2`, items pinned by name.

⚠️ `final` is a **(model x scaffold x config)** composite, NOT a model property: the repair turn
receives the pytest traceback INCLUDING the failing test's source and expected values. The paired
design licenses the COMPARISON (scaffold constant) but the result does **not transfer across
scaffolds** — this is an *aider* result and the campaign still has ZERO opencode evidence.

⚠️ **SAMPLING IS UNTUNED FOR THIS AXIS.** Both temps came from SINGLE-SHOT ladders. Since unseeded
retries are byte-identical, low temperature anchors attempt 2 on attempt 1's failed approach, so the
multi-turn optimum is plausibly higher — and the two models are mis-tuned by DIFFERENT amounts
(0.4 vs 0.3). Campaign-v3 P2-P4 exists to resolve this before the verdict is called final.

### FIVE CAMPAIGN CLAIMS FALSIFIED 2026-08-12 — check the record before trusting it
| claimed | actual |
|---|---|
| aider 13.2pp gap decides the campaign | two unrelated UNSEEDED subsets with different language mixes — never a measured gap |
| LCB 6.7pp differentiator | **three-way tie at 80%**; the gap was a grading bug (`-1`/`-2` sentinels truthy) |
| LCB `by_difficulty` is broken | it was CORRECT; `acc` was the broken number. Quarantine lifted |
| IFEval blocked by `datasets` "Feature type 'List'" | loads fine on BOTH boxes; the gap was 4 missing verifier deps |
| runaway turns cost 31× (justifying `successes_per_hour`) | **0/284 turns** ran away at the current config; 0.0% wasted wall-clock |

### Local fixes landed 2026-08-12 (no worker time)
- `bench_heartbeat.sh` — harness-agnostic monitor (works for pi/opencode/aider); a broken
  progress command REFUSES to print numbers rather than reporting 0.
- `grade.py` — LCB `-1`/`-2` sentinels were scored as PASSES; `acc` inflated over the official
  `pass@1`. Fixed + re-graded.
- `bfcl_shim/local_handlers.py` — the request sent NONE of the tuned sampling and never asked for
  thinking. **Not a complete repair:** it posts a pre-formatted prompt to `/v1/completions`, which
  bypasses the chat template that `enable_thinking` normally drives; needs a live smoke.
- `run_convergence.py` — used the DRIFTED `production` profile (presence_penalty 0.3 DISABLES
  suffix decoding = different serving path) and accepted `--set` typos silently. Both fixed.
- `judge_extract.py` — panel v3 extractor: RAN-filtered, reference-guided, counterbalanced.
- IFEval verifier deps installed on the driver (`uv pip`, the venvs have no `pip`).

### ⚠️ TRAP: a file count is NOT a progress metric
aider writes `.aider.results.json` for every exercise it SETS UP, with `tests_outcomes: []` until
the case runs. `distill/java` showed **22 files for a batch that ran 1**. Every progress metric and
every extractor must filter on non-empty `tests_outcomes`.

### Phases (campaign v3) — worker-gated unless noted
| # | phase | state |
|---|---|---|
| P0 | `m1f` baseline | ✅ settled (above) |
| — | `m1g`: recover `distill/java` (21 cases lost to a TCC failure) | ~ RUNNING |
| P1a | pi + opencode go/no-go smokes — endpoint reach AND sampling actually landing | queued (gates ~24h) |
| P1b/c | harness recon + agnostic monitor | ✅ |
| P2 | Tier-0 grid, 9 configs (3 temp × 3 min_p) + TEST the 4D→2D collapse | queued |
| P3 | proxy validation: Spearman ρ + **exact permutation p** on the Tier-0 grid | queued |
| P4 | Tier-1 agentic tune @ `tries=4`, Tier-2 confirm on **held-out EXERCISES** (89 unused) | queued |
| P5 | daily role: Ornith temp-ladder, IFEval (ready now), multi-turn chat eval (missing) | partly ready |
| P6 | repo-level via **SWE-bench (built, never run)** + harness gradient | queued |
| P7 | context curves (task-based), then KV squeeze via **TOST, three-state rule** | queued |
| P8 | BFCL live smoke + judge panel v3 (meta-judge, anchoring control) | harness ready |

Cost, re-derived from measured 2.2 / 6.3 min/case: **~185 worker-hours ≈ 8 days on one box**, split
**~45h one-time infra + ~55–60h per additional model**.

### ⚠️ WORKER PATHS MOVED 2026-08-12
The worker workspace is now `~/ws/...`, no longer under `~/Documents` — TCC denies protected
folders to publickey ssh sessions, which cost 21 java cases mid-run. `config.sh` updated. Do not
put the repo, the aider clone or results back under Documents/Desktop/Downloads.

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
So the live deltas (~~LCB 6.7pp~~ **RETRACTED 2026-08-12 — see below**, aider 13pp) need N≈100–470
matched items. ⚠️ **THE LCB DELTA DOES NOT EXIST.** Re-graded at `d214bf9` after fixing a grading
bug (lcb_runner's `-1` timeout / `-2` error sentinels were truthy and scored as PASSES), all three
candidates land on **acc = pass@1 = 0.800** — a three-way tie, n=15, MDE ±32pp. Any arm sized to
"resolve the 6.7pp LCB gap" is sized against an artifact; the aider delta is the only live one, and
M1 is measuring it. **"Inconclusive" is a valid,
likely answer** — if quality ties within resolution, Ornith's 4× decode + 5× memory margins decide.

Phases: **0** bootstrap (`.venv-bench`/`.venv-lcbgrade`/`config.sh` were all MISSING on the driver box; snapshot M5
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

### ⚠️ THE `conv% ≥ 0.90` GATE IS WITHDRAWN (2026-08-11) — unratified and unsound
It was never derived or agreed; it came from the adversarial review's suggested scheme and I adopted
it verbatim while calling it "pre-registered". Measured problems: conv% is quantized so the gate's
strictness tracks n (n=5 demands perfection, n=100 tolerates 10 misses); a point estimate against a
hard threshold ignores sampling error, so a model whose TRUE rate is exactly 0.90 fails 35–45% of the
time by chance; and on cost grounds 0.90 is ~10× too LENIENT — a runaway turn is 102,401 tokens vs a
3,294 median (**31×**), so even conv 0.99 spends 24% of session wall-clock on non-self-terminating
turns, and Ornith's agentic 0.94 spends ~62%. Empirically those turns are wasted, not merely slow:
both output-limit cases so far (`python/paasio`, `javascript/grep`) FAILED both attempts while
burning 920s and 775s (n=2 — suggestive, not established).
**Replacement (proposed, awaiting ratification):** rank on `successes_per_hour`
(`stats.time_to_success`) — it internalizes the runaway cost in measured seconds and needs no
invented constant — and report `conv%` + `nonconv_kinds` + the cost-weighted share as DIAGNOSTICS.

### [QUEUED — operator-approved 2026-08-11] Ornith temp-ladder re-check, runs after M1's two arms
Script staged at `/tmp/ornith_ladder.sh` on M5 (syntax-checked, NOT started — M1 owns the worker).
Rungs 0.5 / 0.4 / 0.35 / 0.3 / 0.2 via the FAST mechanism (`bench.run_convergence`: aggregation@8K +
one real coding prompt, `--samples 5 --coding-samples 3`; only the SAMPLE COUNT is reduced, never a
generation param), archiving `convergence.t<T>.json` per rung. ~1–2h total.
QUESTION IT ANSWERS: Ornith's op-temp 0.4 was picked under the old rule, which accepted conv 80%,
and no rung in its recorded ladder (0.6→33%, 0.5→20%, 0.4→80%, 0.3→73%) ever reached 90%. Is that
~80% ceiling REAL (a model property, and a documented limit for the pick) or an artifact of rung
selection? Note the ladder tunes on single-shot probes; sampling has NEVER been tuned for the
agentic loop, which is a separate open gap.

### STATE 2026-08-11 (evening) — M1 GATE LAUNCHED on M5; re-grade DONE
Unblocked by the operator: commits pushed (`eddc082`), M5 synced ff-only, aider + polyglot cloned to
`~/Documents/ws`, `aider-benchmark:latest` image built, model-metadata entries added for all three
candidates, router up on M5 `0.0.0.0:8000` with `APC_ENABLED=1`.

**DONE, zero model time:** all 83 existing M5 result files re-graded under the convergence vector
(table in `campaign-results.md`). This is Phase 1's committed row. Headlines: Ornith **fails the
conv gate** on math500 (70%) / LCB (80%) / aime (80%) while the distill and gemma-qat-6bit clear it
everywhere; Ornith's evalplus data is **n=100 (±13pp), not the n=10 the scoreboard recorded**;
"AIME 100% (5/5)" is ±56pp and never was a differentiator. Off-box backup at
`~/mlx_bench_snapshots/m5-results-2026-08-11/` (closes the deferred P0 snapshot item).

**M1 DESIGN CHANGED after inspecting aider's enumeration — it is STRATIFIED now.** aider enumerates
cpp first, so the historical `Ornith n=34` was 26cpp+8go and the `distill n=16` was 16cpp: those runs
differed in **language mix**, not merely in N, making that comparison worse than "unmatched item
sets" implied. aider does expose `--languages`/`--keywords`, so M1 runs **6 languages × 18 exercises
= 108 matched cases per model** (deterministic per language, so both models get byte-identical
items). n=108 → MDE **±12.0pp**, and `n_for(13.2pp)=91`, so the gap that currently decides the
campaign is RESOLVABLE; the originally-planned n=34 (±21.5pp) was guaranteed inconclusive.
Driver: `/tmp/m1_driver.sh` on M5 (nohup, launcher `/tmp/m1_launch.sh` waits out the smoke), logs
`/tmp/m1_run.log` + `/tmp/m1_<tag>_<lang>.log`. Ornith first (`diff`), then the distill (`diff`),
with an unload between — ONE resident model.

**~~SHIPPED-CONFIG BUG~~ — WITHDRAWN 2026-08-11, the shipped config is CORRECT. Read this before
"fixing" it:** the claim was that `aider_config/aider.model.settings.yml` points every model's
`weak_model_name` at `openai/mlx-community/Qwen2.5-1.5B-Instruct-4bit`, which lives only on :8092
and is deliberately not a router entry, so every weak-model call 404s against aider's single
:8000 endpoint. **aider does NOT have a single endpoint.** `configgen/emitters/aider.py:20-24`
deliberately emits a 5th settings entry for the task model carrying its own
`extra_params.api_base: http://localhost:8092/v1` (asserted by `configgen/tests/test_aider.py:45`),
and aider honours it: `models.py:617` builds the weak model as its OWN `Model` (so it does its own
settings lookup by name) and `models.py:1010-1011` does `kwargs.update(self.extra_params)`, putting
`api_base` straight into the litellm call. Weak-model traffic therefore goes to :8092 as designed,
which is also why the 1-case smoke showed 0 404s. **Pointing `weak_model_name` at the served model
would be a REGRESSION** — every commit message and history summarisation would run on the 19-29GB
agent model instead of the 1.5B task model.
**The REAL hazard is benchmark-only, and narrower.** The AGENTS.md bench router recipe starts
:8000 ONLY — no :8092 task model — so under that recipe a weak-model call gets ECONNREFUSED (not a
404) and then retries against aider's 24h `RETRY_TIMEOUT`. `benchmark/m1/m1_driver.sh`'s generated
`/tmp/aider.bench.settings.yml` (weak -> self) is the correct mitigation FOR BENCHMARKS and stays.
The alternative for future runs is to start the :8092 task model alongside the bench router.
No carrier change is needed, and none of the four sampling carriers is involved.

**COST NOTE — the 384s/case prior is not holding.** The 1-case cpp smoke (spiral-matrix, 2 attempts)
ran ~16 min with model calls of 42s / 41s / **202s**, i.e. 2-3× the 6.4 min/case prior (which came
from the historical cpp+go n=34 run). Not extrapolated from one case: the driver runs
language-by-language, so real throughput is measured on the cpp wave and n can be trimmed at a
language boundary before the whole 108 is committed. cpp first is the conservative order.

### STATE 2026-08-11 (earlier) — Phases 0/1/2 DONE (531 tests). BLOCKED at the M1 gate.
Committed: `a11cfe9` (plan) → `6a84a3f` (P0) → `f5d5230` (P1) → `9d9f2d5` + `fef0ed2` (P2).
Shipped: results-root seam, `deployed` sampling profile (registry-sourced), fingerprint v2,
`stats.py`, `traces.py`, `rowschema.py`, `--samples k` with mandatory per-draw seeds, the
convergence vector, per-sample evalplus/LCB grading, `compare` with TOST/Holm,
`agent_outcomes.py` + loop guard + deadlines, aider `.aider.results.json` parsing,
`check_edit_format`, and the `run_canary` profile fix (queue item at "HARNESS ISSUE
(preflight-profile mismatch)" is now CLOSED).

**The M1 gate cannot proceed without operator input — hard blockers (rechecked 2026-08-11):**
1. **No aider harness on EITHER box.** `~/aider` and `~/polyglot-benchmark` are absent on the M4 Pro
   driver AND on M5 (filesystem-verified 2026-08-11), `AIDER_BENCHMARK_DIR` unset, no `tmp.benchmarks`.
   The Homebrew install ships the pip package only; `benchmark/benchmark.py` lives in the REPO. Both
   repos must be cloned **on M5** (that is where every model run now happens) before any agentic run.
2. ~~**M5 is unreachable.**~~ **RESOLVED 2026-08-11:** passwordless ssh is live (ECDSA key, mDNS-alias
   `Host` block, ControlMaster multiplexing) and the driver's `config.sh` now carries real
   `REMOTE_HOST`/`REMOTE_USER`/`REMOTE_REPO` values. M5 is synced to `origin/main` with submodules
   forced to their pinned SHAs, and has repo + all three venvs + docker (`linux/amd64` emulation OK).
3. **M1 is 18h (Ornith, M5) + ~41h (distill) + ~32h (gemma) of model time**, and gemma additionally
   cannot share a box with an agent session (see campaign-results HARNESS V2 §4). **Now WORSE than
   when written:** with the M2 Max gone these cannot run in parallel across two boxes — all ~91h
   serializes onto M5.
4. **NEW — the harness-v2 code is NOT on M5.** Phases 0–2 (`a11cfe9`…`1b02681`, 6 commits) are
   committed locally but UNPUSHED, so `origin/main` (and therefore M5) is still at `36f6782`. M5
   cannot run the new harness until those are pushed and it is re-synced.

**Per the anti-graveyard rule, Phases 3-6 are NOT started** — building more axes before M1 produces
a committed row is exactly the pattern that left four axes built-and-never-run.

⚠️ **The local stack is DOWN** (router :8000, task model :8092, OWUI :3000) — taken out by the 29GB
gemma load. Restore with `/mlx`. Deliberately not restarted automatically: `runserver.sh:40` runs
`git submodule update --remote`, which would move the deployed submodule pointers off their pinned
SHAs, and a bare router restart would then collide with `/mlx` on :8000.

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
`Ornith-1.0-35B-mlx-uniform-4bit` + `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Box split (HISTORICAL —
phase complete, and the M2 Max is retired): M5 = speed/mem (single-box, apples-to-apples) + LCB
quality; M2 = parallel he+/mbpp+ quality + APC.
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
- **[DONE — ran on the now-retired M2 Max] LCB t0.4** (thinking_budget 81920): item 1 **CONVERGED** (24,341 tok) — DNF was a temp artifact. item 2 `abc358_e` errored (sleep) → needs regen. Final result recorded below (9/15 conv). Log `/tmp` … `logs/distill_lcb_t04.log` (on the retired box — gone).
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
- **M2 (RETIRED BOX — historical record; any `[RUNNING]` state here is dead, and its local `benchmark/results/` and `/tmp` logs are gone with the machine):** distill **LCB t0.4 DONE** = 9/15 (60%) conv (+1 err abc358_e) → confirms op-temp 0.3 (vs t0.3 15/15).
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
- **RECOVERY if session drops (nohup survives, watchers + caffeinate do NOT)** — *M5-only as of 2026-08-11; the
  M2 half of this procedure is void, that box and its `logs/distill_lcb_t04.log` are gone:* re-check
  `pgrep -f "run.py generate"`
  + `logs/m5_distill_chars.log` on M5; relaunch any dead driver (M5 driver =
  `/tmp/m5_distill_chars.sh` but edit the `kill -0 5704` guard if 5704 is gone → just run its 3 generate/BFCL cmds);
  re-apply caffeinate; re-launch background pollers. Grades are re-runnable (jsonls persist). (M5 IP churn is
  no longer an issue: reach it as `ssh $REMOTE_HOST` via the mDNS-based `Host` block — no subnet scanning.)

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
7. **[NEXT — RE-HOMED from M2 2026-08-11, ATTENDED first-run]** Aider polyglot SMOKE (`--limit` small) on the
   dense front-runner (`gemma-4-31b-it-6bit` / `gemma-4-31b-it-UD-MLX-4bit`), then full Aider →
   SWE-Verified-40. CORE agentic axes, never run — the real "256K agentic coding" test. **BLOCKED on M1-gate
   blocker #1:** `~/aider` + `~/polyglot-benchmark` must be cloned ON M5 first (absent there as of 2026-08-11).
   The old "box-idle monitor pings M2-IDLE → launch" trigger is void; M5 idleness is the trigger now.
8. **[QUEUED — RE-HOMED from M2 2026-08-11]** BFCL native-FC on the lead gemma candidates.

### M2 Max — RETIRED 2026-08-11 (historical record only; pending items re-homed to M5 above)
1. **[DONE]** dense-gemma LCB @ production t0.7: gemma-4-31b-it-6bit **86.7%** (conv 12/15) +
   gemma-4-31b-it-UD-MLX-4bit **86.7%** (conv 14/15) — both BEAT the MoE (80%, H60→H80) with
   cleaner convergence. Graded + recorded.
2. **[DONE]** math500 (N=30) @ production — graded 2026-06-26: gemma-4-31b-it-6bit **83.3% / 100%
   conv / VALID** (median 2000); gemma-4-31b-it-UD-MLX-4bit **83.3% raw but 67% conv / INVALID**
   (over-reasons, median 8165, 10 loops — 4-bit tail-fragility). With gemma-4-31B-it-qat-6bit
   (83.3% / 100% conv / VALID, M5) → all 3 dense gemmas done on math500. Recorded in campaign-results.md.
3. **[RE-HOMED → M5 worklist item 7 (2026-08-11)]** Aider polyglot SMOKE, then full Aider →
   SWE-Verified-40. Was never started here; the box is gone.
4. **[RE-HOMED → M5 worklist item 8 (2026-08-11)]** BFCL native-FC on the lead gemma candidates.

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
- ~~**IFEval**: `datasets` load fails "Feature type 'List' not found"~~ **STALE — NOT BLOCKED
  (re-verified 2026-08-12).** The datasets incompatibility is gone: `benchmarks.load("ifeval")`
  loads 541 examples cleanly on BOTH boxes (driver `datasets` 5.0.1, M5 3.6.0). The only real
  gap was the vendored verifiers' deps (`absl-py`/`langdetect`/`nltk`/`immutabledict`), which M5
  already had and the driver box was missing; installed via `uv pip install --python
  .venv-bench/bin/python` (the venvs are uv-managed and have no `pip`). **IFEval can now be RUN
  — it is a named daily-role axis and its harness is functional.** Note the graceful-degrade
  design is correct and was never at fault: `grade._load_ifeval_lib` raises by design and the
  caller returns `acc:null` + a note rather than crashing the batch.
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
- Gates: ≤46GB MLX-peak @256K (≤56GB browser-closed, metric = `mx.get_peak_memory`); the M4 Pro driver
  hosts NO models at all (so every capacity/quality/speed run is an M5 run — there is no local rung);
  ONE resident model per box; judge over execution-PASSING outputs only; two eff-ctx curves separate.

## Reboot recovery
1. Restart the router (per-box recipe in AGENTS.md): `MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start …` → :8000.
2. For each `[RUNNING]` item, relaunch its driver (`lightsweep.sh`/`tempsweep.sh`, same args) — it resumes from disk via done_ids / `--clean-stale`.
3. Drive M5 MANUALLY against this worklist. Reaching it is no longer the problem it was: `ssh $REMOTE_HOST` resolves via an mDNS-based `Host` block (ECDSA key per the box's FIPS ssh policy, ControlMaster multiplexed), so IP churn needs no subnet scan. If the name ever fails to resolve, find it with `dns-sd -B _ssh._tcp local` rather than sweeping the subnet. Note M5 is Jamf-managed: confirm Remote Login is still enabled (`systemsetup -getremotelogin`) if it goes unreachable, since a compliance policy can switch it off.
4. Sanity-check with `benchmark/preflight.sh` before trusting a resumed run.
