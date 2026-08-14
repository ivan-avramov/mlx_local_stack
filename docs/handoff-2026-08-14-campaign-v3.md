# Handoff — 2026-08-14, campaign v3

Supersedes `handoff-2026-08-13-campaign-v3.md` (deleted). Read with: `docs/open-questions.md` (the
operator's decision queue — START HERE), `docs/campaign-queue.md` (durable state), `AGENTS.md`
(rules), `docs/regrade-vs-rerun-guideline.md`, `docs/campaign-results.md` (results).

**Everything is pushed. Both boxes are at the same commit. 714 tests green. The worker is IDLE.**

---

## 1. STATE — no action needed before starting

| | |
|---|---|
| M5 worker | **idle**: 0 models resident, 0 clients, router up on :8000, health 200, **APC absent** |
| Boxes | driver + M5 both at `origin/main`, only M5's `main_models.yaml` intentionally dirty (kv 65536) |
| Tests | 714 pass (`PYTHONPATH=.:benchmark .venv-bench/bin/python -m pytest benchmark/bench/tests/ configgen/tests/ -q`) |
| Next per ratified sequence | **P4 → BFCL → judge panel → SWE-bench** |

⚠️ **`run.py` must be invoked from the REPO ROOT.** Paths are now module-relative (`bench/paths.py`) so
it no longer writes a phantom `benchmark/benchmark/results/`, but the documented invocation is repo root.

---

## 2. THE PARAMETER SEARCH — how it is designed, and what survived

The plan is a **tiered narrowing**, not a gradient descent — the space is discrete and each evaluation
costs minutes-to-hours, so it is a cheap-screen → expensive-confirm ladder:

| tier | what it varies | items | status |
|---|---|---|---|
| **Tier-0** | 3 temps × 3 `min_p`, + a test of the 4-knob→2-knob collapse | a convergence screen (minutes/cell) | ✅ **DONE rev B** — 22/22 cells, both winners |
| **P3** ρ validation | does the cheap screen predict the agentic axis? | — | ❌ **CANCELLED** (operator) |
| **Tier-1** | 3 configs, aider `tries=4` | 44 × 2 models | ▶ **NEXT (P4)**, ~28h |
| **Tier-2** | tuned vs shipped, **held-out** exercises | 89 unused | queued, ~14h |

**What Tier-0 established, and why P3 died.** `converged_rate` was **1.0 in 66/66 draws** across both
winners — a constant. Spearman ρ on a constant vector is *undefined*, not weak, and P3's other half
(per-config agentic results) does not exist until P4 runs. So P3 was cancelled rather than run.

**Three measured facts that should shape P4:**
1. **The truncation knobs are mutually redundant.** `top_p` / `top_k` / `min_p` collapse to one
   distinction — truncation ON vs OFF. `min_p` is fully inert at temp 0.2 (all of 0.0/0.05/0.15
   byte-identical) and only bites above ~0.4. **⇒ do not spend P4 cells on `min_p` below temp 0.4.**
2. **The untruncated path is NONDETERMINISTIC** under suffix decoding: 3 identical unseeded requests
   → 3 outputs, 1.6× length spread. **⇒ never run a cell at `top_p 1.0 / top_k 0 / min_p 0.0`.**
   Rev A did, in 4 of 11 cells, and those cells are noise.
3. **Temperature is the only knob that moved anything.** `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` at temp
   0.6 emitted 52,833 tokens on a problem it solves in 1,122 at temp 0.4 — 47× tokens, 24× wall. Its
   op-temp 0.3 is confirmed from a second task and harness path.

**Quant algorithm / bit-width is NOT in this ladder** and should not be folded in: it is a separate
OFAT with its own gate (≤5% quality drop, measured per-axis), and the two runs we have both came back
negative — `Ornith-1.0-35B-mlx-uniform-6bit` is no better than 4-bit on `acc` and **worse on
`acc_strict` (40% vs 60%)**, and OptiQ-converting Ornith failed outright on the fused-expert layout.

---

## 3. THE SCOREBOARD — new, and this is what to show for "how did each model do"

`benchmark/m1/scoreboard.py` (run from repo root, `--md` for markdown). One row per (model, bench)
plus explicit **role coverage** for reasoning / coding / daily. It reads the per-item rows, NOT
`scores.json` — that file only holds the last `grade` call, so a scoreboard built from it silently
drops models.

**It answers the question `compare` cannot:** `compare` says "A vs B → equivalent", which tells you
nothing about whether either is usable. The scoreboard says what was measured, at what n, and what is
**missing** — an unmeasured combination reads `NOT MEASURED`, never as a pass.

**The headline it exposes: coverage is thin and lopsided.**
- `daily` is **NOT MEASURED for 14 of 17 models** — only IFEval exists, and only for the two winners.
- `aider` (the only axis that ever separated the winners) is missing from **every** row of the
  scoreboard because it is scored outside this tree — join it manually from `campaign-results.md` M1.
- `gpqa` is measured for **nobody**. `aime` is `n=4–6` everywhere, i.e. **±56pp** — it never was a
  differentiator and the scoreboard now says so out loud.

**Ranking key is `acc_strict` at a matched budget** (operator ruling): a DNF scores 0 with the
denominator intact, so 99 DNFs of 100 scores 1%, not 100%. `pass@1|converged` is a DIAGNOSTIC that
must never rank — it conditions on convergence and would score that model 100%.

---

## 4. RESULTS THAT LANDED THIS SESSION

- **IFEval (first daily-role axis ever run).** `Ornith-1.0-35B-mlx-uniform-4bit` **541/541,
  `prompt_strict` 90.0% [87,93] ±5pp** — the first axis in this campaign with real resolution.
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` stopped at **148/541**; paired on the shared 148 both score
  **89.9%, gap +0.0pp, `equivalent`**. **⇒ the two winners are equivalent on instruction-following.**
  Resume procedure in `campaign-queue.md`; 148 rows + manifest intact.
- **LiveCodeBench re-graded (all 7 persisted runs, zero worker time).** The "three-way tie at 80%"
  holds on `acc` — but `acc_strict` spreads **60–80%**, i.e. the tie was an artifact of not charging
  truncation. ⚠️ **20pp is inside the ±32pp MDE at n=15, so this is a live question, not a result.**
  **Highest-value cheap run available: LCB at n≈100 on the three D1 candidates (MDE ±12.5pp).**
- **Degenerate repetition loops are a real, large cost.** `Ornith-1.0-35B-mlx-uniform-4bit`: 30 loops =
  **42% of IFEval wall-clock**. `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`: **57%**. Concentrated on
  *counting* instructions (`capital_word_frequency` 33% vs 4.5% base). ⚠️ This **revises "the runaway
  tax has nothing to charge"** — that was measured on budget-hits and `max_tokens` only, and these are
  neither. **Operator ruling: these are NOT DNFs** — the model self-terminated, the answer verified,
  so they count in `acc` and the cost is reported beside capability.
- **APC is INERT and now OFF everywhere** (including `runserver.sh`). Session caching *shadows* it by
  construction: `generation.py:2455` dispatches any request with a `prompt_cache_state` and `continue`s
  past the only site passed `apc_manager`. Session caching is what makes multi-turn cheap (measured:
  cost per NEW token flat, per TOTAL token −17×). Phase-2's "TTFT 34–147×" does **not** reproduce.
- **Phase-2 re-verify:** suffix decoding **confirmed real** (1.27×, same box/session). The GQA decode
  kernel was **unfalsifiable** — its A/B toggle was dead code; now reachable via
  `TQ_DECODE_2PASS_LEGACY` (fork `8b7100b8`, submodule bumped, verified live). **The A/B has not run.**

## 5. HARNESS DEFECTS FIXED — all TDD, all with the failure recorded in the test

`_finalize` nulling a grader's own `acc` · IFEval `punkt_tab` missing (**21% of items silently dropped,
biasing acc UP 3pp**) · silent verifier skips shrinking `n` · CWD-relative paths writing a phantom
results tree while printing COMPLETE · `run_convergence`'s fixed 3600s timeout below the budget time
(now derived from measured decode rate, with loop/meander classification) · degenerate-loop detection
(two signatures: line-level and content-level) · scoreboard printing a **withdrawn** conv gate as
"pre-registered" · `run.py` mislabelling its own sampling profile · full-registry-name lint over all
docs.

## 6. TRAPS ADDED THIS SESSION (read before writing shell)

- **A tool/ssh timeout kills the LOCAL client, not the remote job.** A probe I believed dead kept
  generating for 13 min, appended 3 rows, and presented as an orphaned generation. Verify with `pgrep`,
  kill BY PID, `nohup` anything that may outlive the call.
- **`--chunks 0` is NOT a dry run** — it generates. To inspect resume state, read `done_ids`.
- **The 5-minute cadence must live in a DAEMON**, not in the agent — an agent only runs when the
  operator messages it. Use `benchmark/m1/bench_watch.py`; a counter-only monitor is "reported", not
  "evaluated".
- **A monitor that false-alarms gets ignored** — it cried STALL on a model the driver had not reached.
- zsh does not word-split unquoted vars; use `-F file` for commit messages (backticks in `-m` get
  command-substituted and silently eat words).

## 7. WHAT TO DO NEXT

1. **P4 / Tier-1 agentic tune** (~28h, ratified next). Apply §2's three facts: no `min_p` cells below
   temp 0.4, never the untruncated config, temperature is the live knob.
2. **Cheaper and arguably first: LCB at n≈100** on the three D1 candidates — it converts the
   `acc_strict` 60–80% spread from unresolved into resolved for a few hours.
3. **Free, no worker:** re-grade `humanevalplus`/`mbppplus`/`aime`/`math500` across all 17 model dirs
   under the convergence vector + `acc_strict`. Never done.
4. **Acquire `NVIDIA-Nemotron-3.5-Lightning-30B-A3B`** (operator-approved). 256K native, 30B MoE/3B
   active, MLX 4-bit exists at 17.8GB. Risks: text-only vs a vision-only registry, Mamba-2 arch,
   ships MTP (a net slowdown for us — disable it).
5. **Open questions:** `docs/open-questions.md` — only **O9** (judge panel on looped answers, held on
   panel reliability) and **O10** (now largely settled) remain.
