# Handoff — 2026-08-13, campaign v3 (M1 settled, Tier-0 half-done)

Read with: `docs/superpowers/plans/2026-08-12-campaign-v3-two-role-selection.md` (the plan, rev 2
after three adversarial reviews), `docs/campaign-queue.md` (durable state + phase table),
`docs/campaign-results.md` (results), `AGENTS.md` (measurement discipline).

**17 commits this session, ALL UNPUSHED.** Working tree clean, 544 tests green.

---

## 1. DO THIS FIRST — the worker is burning cycles on abandoned work

M5's worker is still generating a request that its client abandoned at 22:34 (the Tier-0 distill
cell that hit a 3600s timeout). Verified still consuming CPU at 22:47. Nothing will run correctly
until it is cleared.

```bash
# on M5, kill BY PID and verify (pkill has silently no-op'd on this project)
lsof -nP -iTCP:8000 -sTCP:LISTEN            # note the router pid
pgrep -f "mlx-serve start"; pgrep -f mlx_vlm.server
# kill router parent+child and the worker, verify each is gone, then restart:
cd ~/ws/mlx_local_stack
set -a; . ./.env 2>/dev/null; set +a
MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start >logs/main_model.log 2>&1 </dev/null &
# verify: exactly ONE listener on :8000, APC var count 0, health 200
```

## 2. THE CODE ON M5 IS SCP'd, NOT COMMITTED

M5 was at `266fad2` and none of this session's commits were on it — a full Tier-0 grid launch died
`rc=2` on every cell because `run_convergence.py` there lacked `--sampling-profile`. Ten changed
files were scp'd (sanctioned by AGENTS.md for validation), so **M5 now carries ~12 uncommitted
files**. A push + `git fetch && git merge --ff-only` is the real fix and needs operator
authorisation. Until then, any edit made locally must be scp'd again or it silently won't apply.

⚠️ M5's `main_models.yaml` is **intentionally dirty**: `max_kv_cache_size`/`kv_prealloc_tokens` are
65536 (right-sized for the agentic axis). Do NOT `git checkout` it. Revert to 262144 before any
256K capacity work.

## 3. WORKER PATHS MOVED

The workspace is now `~/ws/...`, no longer `~/Documents/ws/...` — TCC denies protected folders to
publickey ssh sessions and it cost 21 benchmark cases mid-run. `config.sh` is updated. Never put the
repo, aider clone or results back under Documents/Desktop/Downloads.

---

## 4. M1 GATE — SETTLED. The coder role is Qwen3.6-27B-Opus-Distill-OptiQ-4bit.

Paired on **110 byte-identical exercises** (5 languages × 22, both arms, RAN-filtered; `distill/java`
from the `m1g` re-run):

| metric | Ornith-1.0-35B-mlx-uniform-4bit | Qwen3.6-27B-Opus-Distill-OptiQ-4bit | delta | McNemar |
|---|---|---|---|---|
| **final (≤2 attempts)** | 55/110 = **50.0%** | 81/110 = **73.6%** | **+23.6pp** | **p=1.3e-05** |
| attempt-1 | 24.5% | 32.7% | +8.2pp | p=0.122 n.s. |
| **repair rate** | 33.7% | **60.8%** | — | — |
| mean/case | 2.17 min | 8.42 min (3.9×) | — | — |

Every language favours Qwen3.6-27B-Opus-Distill-OptiQ-4bit (+13.6/+36.4/+13.6/+27.3/+27.3pp). Exclusive solves 31 vs 5.
**Mechanism is REPAIR, not raw capability** — attempt-1 is not significant.

Two limits recorded with the number: `final` is a **(model × scaffold × config)** composite (the
repair turn receives the pytest traceback *including the failing test's source and expected
values*), and **sampling is untuned for this axis** — both temps came from single-shot ladders while
unseeded retries are byte-identical, so low temperature anchors attempt 2 on attempt 1's failure.
Resolving that is what P2–P4 is for.

---

## 5. TIER-0 GRID — Ornith complete, distill FAILED. Read before relaunching.

Archives in `/tmp/tier0/` on M5 (11 Ornith cells; **volatile — copy them somewhere durable**).

**Ornith result: convergence 1.0 and `budget_hit_rate` 0.0 in ALL 11 cells.** There is no
convergence knee to find for Ornith at these settings — an answer, not a null.

**Distill: zero cells.** Cascade failure:
- cell 1 ran 21:34:08 → 22:34:17 = **exactly 3600s**, the `driver.complete()` timeout
- the client gave up but **the worker kept generating**
- every later cell's `calibrate_cpt` (timeout **120s**) queued behind it and died at 2 min

**Root design error:** the screen uses `aggregation`@8K for both models. Ornith emits ~39K tokens at
~220 tok/s ≈ 3 min/sample; Qwen3.6-27B-Opus-Distill-OptiQ-4bit emits comparable volume at ~28 tok/s ≈ **23 min/sample**. A
screen that is cheap for one model is an hour-long generation for the other. I sized it from
Ornith's timing.

**Note what the hour was spent on:** the `aggregation` CWE task is a synthetic word-tally
*designed* to blow the thinking budget (see `aggregation.py`). The coding task in the same cell is
only ~3K tokens. So this is not a legitimately large problem — and it is a questionable proxy for
the agentic axis, which is precisely what P3's ρ check exists to test. Prior on that correlation
should be LOW.

**Operator-approved fixes (do these, do NOT just raise the timeout):**
1. clear the abandoned generation (§1)
2. re-scope Qwen3.6-27B-Opus-Distill-OptiQ-4bit screen so a cell is minutes: cap `max_tokens` for the screen only, or use
   the smaller `vartrack` task, or `--samples 1`. All are scope/sample reductions, never generation
   params — AGENTS.md forbids the latter.

**Two further problems found in the Ornith data:**
- **`min_p` is inert over most of the chosen range.** Distinct generation fingerprints: **8 across
  11 cells**. `t0.2_mp0.02 ≡ t0.2_mp0.05`, and `t0.4_mp0.02 ≡ t0.4_mp0.05 ≡ collapse_3knob`. So the
  "9 configs" the ρ analysis assumes are ~6 distinct ones. Widen the spacing or drop `min_p`.
- **Identically-configured cells diverged** (`t0.4_mp0.0` vs `collapse_minp_only`: 18,640 vs 32,227
  tokens on the same sample), with the task provably fixed (`cpt=4.61` in all 11 cells). Cause NOT
  isolated.

### SUFFIX DECODING — keep it ON. Test before touching.
I proposed disabling it and that was over-claiming. `AGENTS.md` records BOTH that it is
**quality-neutral** (measured on he+/mbpp+/LCB) **and** "inherently non-lossless — kernel numerics
flip greedy argmaxes". Those are different claims: aggregate quality is unaffected, byte-identical
output is not guaranteed. Keeping it on for latency is well-founded (operator's stated reason).
**Before anyone disables it, run the cheap isolation test:** one config twice with suffix ON, then
twice with suffix OFF (~15 min on Ornith). If the OFF pair is reproducible and the ON pair isn't,
that's evidence; if both diverge, suffix is exonerated and the cause is elsewhere.

---

## 6. CAMPAIGN CLAIMS FALSIFIED — check the record before trusting it

| claimed | actual |
|---|---|
| aider 13.2pp gap decides the campaign | two unrelated UNSEEDED subsets, different language mixes — never a measured gap |
| LCB 6.7pp differentiator | **three-way tie at 80%**; the gap was a grading bug (`-1`/`-2` sentinels truthy) |
| LCB `by_difficulty` is broken | it was CORRECT; `acc` was the broken number. Quarantine lifted |
| IFEval blocked by `datasets` | loads fine on BOTH boxes; the gap was 4 missing verifier deps (now installed). **IFEval can be RUN** |
| runaway turns cost 31× | **0/284 turns** ran away at the current config; 0.0% wasted wall-clock |
| `run_convergence` measures deployed sampling | it used the DRIFTED `production` table (presence_penalty 0.3 DISABLES suffix decoding) — fixed |

## 7. TRAPS THAT COST TIME THIS SESSION — do not re-learn

- **A file count is NOT a progress metric.** aider writes `.aider.results.json` for every exercise it
  SETS UP, `tests_outcomes: []` until it runs. `distill/java` showed **22 files for a batch that ran
  1**. Filter on non-empty `tests_outcomes`.
- **`cp` after a run treats a STALE file as success.** My archiver produced 11 copies of one old
  result labelled as 11 configs. Delete the target BEFORE the run; check `rc`; verify the output's
  params match the request.
- **"worker=GENERATING" ≠ "run progressing."** It was generating an *abandoned* request for 13 min
  while I reported "on track". Track the progress counter, not worker busyness.
- **`ssh` inside `while read` eats stdin** — only the first file copied. Use `ssh -n`.
- **zsh doesn't word-split unquoted vars**, so `for p in $LIST` runs once with the whole string; and
  an unmatched glob aborts the command (my `rm` never ran).
- **macOS has no `pgrep -c`, no `timeout`** (m1 README says so; I forgot 3×).
- **`/usr/local/bin` must be on PATH** or `docker` reads as MISSING while running.
- **`grep -c` exits 1 on zero matches**, so `|| echo 0` appends a second zero → `"0\n0"`.
- **Monitors must be armed detached with output to a FILE.** A monitor armed inside an ssh session
  writes to a dead pipe. And a finite loop (`seq 1 200`) silently expires — mine did, 3 min before
  the run it was watching ended.
- **Verify code is ON the box.** A whole grid launch died because 14 local commits weren't on M5.

## 8. IMMEDIATE NEXT STEPS (in order)

1. §1 clear the abandoned generation; verify one listener / APC absent / health 200.
2. Copy `/tmp/tier0/*.json` off `/tmp` (volatile) and record the Ornith result in
   `campaign-results.md`.
3. Re-scope + relaunch Qwen3.6-27B-Opus-Distill-OptiQ-4bit Tier-0 arm per §5.
4. Suffix isolation test (§5) before any config change.
5. Then P3 (ρ + **exact permutation p**, n=9 per operator), P4, and the still-untouched
   **P1a pi/opencode go/no-go smokes** — which gate ~24h of harness-gradient work and must verify
   the endpoint is reached AND the tuned sampling actually lands (opencode#5674 may not forward
   `baseURL`; if `options` don't forward it silently ignores the sampling under test).

Ready-to-run and NOT blocked: **IFEval** (harness functional, a named daily-role axis),
**judge panel v3** (`benchmark/m1/judge_extract.py`, dry-run clean at 43 both-solve pairs — will be
~53 with java), **BFCL** live smoke (request fix landed; whether `<think>` appears needs verifying
because that path posts a pre-formatted prompt to `/v1/completions`, bypassing the chat template).

## 9. OPEN DECISIONS FOR THE OPERATOR
- **Push authorisation** — 17 commits local, and M5 is running scp'd copies.
- Whether the daily driver keeps APC enabled in `runserver.sh` (worth 34–147× TTFT on the
  interactive role; benchmarks are unaffected, they run with APC absent).
- Multi-turn chat eval: still the one genuinely missing daily-role axis, needs design.
