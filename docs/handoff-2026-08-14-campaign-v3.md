# Handoff — 2026-08-14, campaign v3 (end of day)

Read with: `docs/open-questions.md` (decision queue — **only O15 open**), `docs/campaign-results.md`
(the USE-CASE LEADERBOARD, which now leads that file), `docs/campaign-queue.md` (durable state),
`docs/work-queue.json` (the live job plan), `AGENTS.md` (rules — several amended today).

**Everything is pushed. Both boxes at `2b25324`. Suite 774 green. M5 is BUSY.**

---

## 1. WHAT IS RUNNING RIGHT NOW

A **work-queue daemon** on M5 (`bench/workqueue.py`), so a finished job no longer means an idle box:

```
nohup env PYTHONPATH=benchmark .venv-bench/bin/python -m bench.workqueue \
    docs/work-queue.json --state /tmp/workqueue.state.json \
    --log /tmp/workqueue.log --logdir /tmp/qlogs >/dev/null 2>&1 &
```

- **plan** = `docs/work-queue.json` (committed; reorder/append freely, the runner re-reads between jobs)
- **state** = `/tmp/workqueue.state.json` (keyed by job NAME, so reordering is safe)
- **per-job output** = `/tmp/qlogs/<name>.joblog`

| job | state |
|---|---|
| archive results tree | ✅ done (runs first, before any `--clean-stale`) |
| **RE-BASELINE evalplus H2H on `0c1c8b17`** | ▶ **running** — Ornith both arms DONE at n=100; `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` mid-humanevalplus |
| runaway-tax temperature ladder | ✅ done — **verdict below** |
| BFCL smoke | ⚠️ **INVALID** — see §4 |
| gemma-4-31B-it-qat-6bit evalplus | ⏸ deferred, reason in the state file |
| gemma-26B, ifeval, math500, LCB | queued, with MEASURED costs in the plan |

---

## 2. THE TWO RESULTS THAT MATTER

### The runaway tax is real, and TEMPERATURE moves it
Ornith at n=100 on the current sha: **2% of humanevalplus items eat 34% of wall-clock; 4% of mbppplus
items eat 63%**. Not an artifact of the old code — measured post-bump.

Ladder on the 3 known runaway ids, with a same-sha control (`--ids`, one results tree per rung):

| item | t0.4 pre-bump | **t0.4 post (CONTROL)** | t0.2 | t0.6 |
|---|---|---|---|---|
| `HumanEval/94` | RUNAWAY 82,101 | ok 7,147 | ok | ok |
| `HumanEval/83` | RUNAWAY 82,005 | **RUNAWAY 81,979** | ok 4,724 | ok 3,023 |
| `HumanEval/144` | RUNAWAY 81,995 | **RUNAWAY 81,996** | ok 897 | ok 6,681 |

**The merge did NOT fix it; temperature did — 6/6 converged at BOTH neighbours of t0.4.** Independently
corroborated at n=100: the two items the control said still run away are exactly the two that ran away
in the full re-baseline.
⚠️ **NOT yet a recommendation.** Three caveats: n=3 items × 1 draw; the items were SELECTED for running
away at t0.4, so that half is partly definitional; and **pass@1 is unmeasured**, which AGENTS.md makes
the HARD constraint with convergence strictly secondary. The non-monotonicity (both 0.2 and 0.6 work,
0.4 fails) is unexplained and interesting.
**→ NEXT EXPERIMENT: a proper ladder on a REAL item set (n≈40, t0.2/0.4/0.6) measuring pass@1 AND
convergence. Size it from a 5-item pilot.** Highest-value work on the board.

### The upstream merge changed generation — the corpus splits at `8b7100b8 → 0c1c8b17`
Byte-equivalence check on a matched item: identical prompt (161 tok), identical sampling, deterministic
3/3, but 2,475 → 3,526 completion tokens. Model impl (`qwen3_5_moe`) and sampler (`sample_utils.py`)
were byte-unchanged; `server/generation.py`, `models/cache.py`, `utils.py`, `generate/{ar,dispatch}.py`
were not. Attribution unresolved; my prior is #1848's thinking-state/response-template change altering
a stop condition. A bisect over the 30 commits would settle it — the repro is one item, ~35 s.
⚠️ **CORRECTION to my own earlier report:** I said the bump made things slower from that one item. In
AGGREGATE it is FASTER — Ornith/humanevalplus total fell 69.4 → 50.6 min, because one fewer item runs
away. Both are true; the aggregate is what matters for cost. The split was still correct.

---

## 3. FIVE DEFECTS FIXED TODAY (all TDD; suite 714 → 774)

1. **The declared thinking budget was not the one in force** (`aca967b`). Server silently clamps
   `thinking_budget` to `0.8 × (max_kv_cache_size − prompt)`. IFEval declared 81,920 against a 65,536
   cap → really ~52,390, so 33 rows scored CONVERGED when they were externally truncated. Corrected
   IFEval: conv 99.3%→94.6% / 98.6%→93.2%; `acc_strict` 89.8%→86.7% / 88.5%→85.1%. `acc` unaffected and
   the "two winners are equivalent" headline survives.
2. **A manifest could outlive its rows** (`a45a139`) — a killed zero-row run left an orphan the next run
   wouldn't overwrite, so rows got stamped with a config that never produced them.
3. **`max_kv_cache_size` missing from the provenance fingerprint** (`a45a139`).
4. **The deployed CODE SHA missing from the fingerprint** (`c14c2ad`) — this one bit immediately: the
   re-baseline job reported `DONE rc=0` in seconds having generated NOTHING, because `done_ids` skipped
   all 200 items.
5. **`current_manifest_lite` had no git block, and `_git_shas` was CWD-dependent** (`2b25324`). The fix
   for (4) was right for the WRONG REASON — `current` read `None`, which would have made every row look
   stale forever and had `--clean-stale` delete the corpus.

Plus: `generate --help` crashed on a bare `%`; **`generate --ids`** added (vary one knob on the SAME
items — previously inexpressible); per-pair `.score.json` persistence so `scores.json` no longer erases
other models' results, and the scoreboard now shows `acc`/`acc_strict`.

---

## 4. OPEN WORK, IN PRIORITY ORDER

1. **The real temperature ladder** (§2). Pass@1 + convergence, n≈40, pilot-sized.
2. **BFCL is UNSTARTED and my queue entry was INVALID.** `run.py generate --benches bfcl` fails with
   `unknown benchmark 'bfcl'`; it runs through **`bench/bfcl_adapter.py`** (driving `bfcl-eval`) plus
   `bfcl_shim/` and `bfcl_diag.py`. It fills an EMPTY use case and is the only POWERED axis the suite
   owns (0.94 vs 0.749 at n=1000 ≈ 12σ). Known risk: the shim posts a pre-formatted prompt to
   `/v1/completions`, bypassing the chat template that `enable_thinking` drives — verify `<think>`
   actually appears.
3. **Grade the re-baseline as a matched set** once `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`'s arms finish.
4. **`evalplus` in docker PRINTS RESULTS THEN NEVER EXITS.** `subprocess.run` waits out our 3600 s
   timeout, a COMPUTED result is discarded as `TimeoutExpired`, and a ~4.5 GB container leaks (found one
   up 7 hours). Fix: parse output rather than relying on exit, or treat "results present" as success.
5. **Nemotron is ready to queue.** `mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, 16.6 GB,
   262,144 native context, loads in 5 s cached (peak 16.56 GB). `nemotron_h` was ALREADY in the fork,
   `sanitize` strips `mtp.*` so MTP is off by construction, MoE implemented, and the **server calling
   convention verified working** (`get_input_embeddings` → `inputs_embeds`-only prefill + decode). Needs
   a registry entry (`type: vision` is the correct BACKEND SELECTOR for a text-only model) and a router
   smoke to confirm stop tokens / thinking-tag handling — its raw output showed a stray `</think>` after
   `<|im_end|>`.
6. **O15** (`docs/open-questions.md`) — the only open question. Does `kv_prealloc_tokens` actually
   reserve RAM? My evidence was INVALID (a ~2,868-token probe never grows the cache, so peak memory
   measured nothing). An actual OOM has been hit in testing, so the protection matters. Needs a
   long-context run crossing 128K→256K, prealloc on vs off.

---

## 5. TRAPS — read before touching anything

- **THE TOOL SANDBOX CAN LOSE ALL NETWORK.** Mid-session, `ping 1.1.1.1` went 100% loss and
  `DNSServiceQueryRecord failed -65563 (Service Not Running)`; the operator's own shell was fine. The
  worker alias resolves via **mDNS `.local`**, which the sandbox cannot reach. **Use
  `dangerouslyDisableSandbox: true` for every ssh call.** I lost ~25 min of worker time misreading this
  as a possible worker outage.
- **`| tail` MASKS FAILURES IN `&&` CHAINS.** It bit three times, including hiding a `git merge --ff-only`
  that FAILED (HEAD stayed put while I believed it had advanced) and a failing lint that let a bad commit
  through. Redirect to a file and check `$?`.
- **Single quotes inside a single-quoted ssh command terminate the quote.** `a['x']` breaks. Use double
  quotes only in remote python. Cost two mangled heredocs.
- **`timeout` does not exist on macOS.** A whole 3-arm OFAT silently ran nothing. Bound work with
  `--probe-timeout` instead, which also records a non-completion as an error ROW.
- **A tool/ssh timeout kills the LOCAL client, not the remote job.** Verify with `pgrep`; never relaunch
  blind. Confirmed again today — a control run survived its dead client and finished correctly.
- **`pkill -f mlx-serve` does not always kill the router.** Force-kill by PID; verify 0 listeners on :8000.
- **A flat item counter is NOT a stall**, and a stall is not always a long tail. Distinguish with worker
  CPU accrual and the resolved-budget ceiling. `/metrics` `summary` only records on COMPLETION, so
  in-flight token progress is unreadable — that gap is why one stall took 19 min to call.
- **Don't stop the runner to kill a job.** Mark the job `failed` in the state file and let the runner
  advance; stopping it reintroduces the human dependency the daemon exists to remove. Both of today's
  idle gaps came from this.
- **M5's `main_models.yaml` is intentionally dirty** — caps RIGHT-SIZED per axis to
  `max_tokens + 2048`, verified to preserve every declared budget exactly: gemma-31B 49152, gemma-26B
  65536, both winners 131072. Do NOT `git checkout` it. Backup `/tmp/mm.rightsized.bak`.
  Reason: gemma at its shipped 196608 cap drove the box to `memory.pressure.CRITICAL` (93.8%, 4.3 GB
  free, 6.7 GB swap) and one item took 46+ min. Unloading recovered 54.3 GB.
- **`.venv-bench` deliberately has NO `mlx_audio`** (that is what lets its tests collect). The bump to
  `>=0.4.8` applies to the model-serving venvs only.
- **My COST ESTIMATES were wrong four times today, always optimistically** (LCB "a few hours" → ~55 h;
  gemma n=100 "7.5 h" → 36 h; gemma n=40 "14 h" → 10.4 h for less data; grading "free" → a 60-min cell).
  Cause: extrapolating from medians or small clean samples when the cost is runaway-dominated — on these
  benchmarks **the tail IS the measurement**. **RULE ADOPTED: no job at n≥40 enters the queue without a
  5-item pilot, and sizing comes from the pilot's MEAN including runaways.**
- **Never `|| true` in a queue entry.** It laundered the invalid BFCL smoke into a green tick. The runner
  already continues past failures and records them honestly.
