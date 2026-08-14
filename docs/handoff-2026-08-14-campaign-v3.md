# Handoff — 2026-08-14, campaign v3

Rewritten late 2026-08-14, superseding the morning version. Read with: `docs/open-questions.md`
(**your decision queue — START HERE, four items open**), `docs/campaign-results.md` (results),
`docs/campaign-queue.md` (durable state), `AGENTS.md` (rules, two amended today).

**Five commits ready, NOTHING PUSHED. Suite 714 → 751 green. M5 is BUSY and healthy.**

---

## 1. THE SESSION IN ONE PARAGRAPH

The plan was P4 vs LCB. Neither ran, because a provenance audit found **every non-IFEval row in the
corpus is from the retired M2 Max at the `official`/`production` profile** — so no baseline was
extendable, and LCB n≈100 was ~46 h from scratch rather than the assumed "few hours". I ran a
from-scratch `deployed` evalplus H2H instead. While setting it up I found that **the thinking budget we
declare was not the one in force** — the server silently clamps it — which turned 33 published IFEval
rows into false passes and **falsified O11's premise**. Then the run stalled, exposing that
**`kv_prealloc_tokens: 262144` — the value we ship — destroys decode throughput (>47× on a matched
item)**. Diagnosing *that* exposed two more provenance defects. The first completed arm then produced a
**clean confirmation of O11's cost claim** on a correct footing: 3% of turns eat 42% of wall-clock.

**Net: O11's number was right, its mechanism was wrong, and the config had three independent defects
that would have corrupted anything measured today.**

---

## 2. WHAT IS RUNNING RIGHT NOW

`run.py generate` on M5: both winners × {`humanevalplus`, `mbppplus`} × **n=100**,
`--sampling-profile deployed --order model --probe-timeout 9000`, `max_kv_cache_size 131072`.
Logs `logs/evalplus_deployed_2026-08-14.log`; two `bench_watch.py` daemons →
`/tmp/watch_{humanevalplus,mbppplus}.log`.

| arm | state |
|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` / humanevalplus | ✅ **100/100, graded** (§3) |
| `Ornith-1.0-35B-mlx-uniform-4bit` / mbppplus | ▶ ~50/100 at 02:15 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` / both | queued behind Ornith (`--order model`) |

**Why `--order model`:** one resident model per box, and at these prealloc sizes the two cannot coexist.
A stopped run therefore leaves `Ornith-1.0-35B-mlx-uniform-4bit` complete and
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` partial — which still pairs, exactly as
the IFEval n=148 stop did (prefix-nested seeded shuffle).

**⚠️ The M2 rows were archived before `--clean-stale` deleted them** →
`~/mlx_bench_snapshots/pre-deployed-evalplus-2026-08-14/`. They are NOT re-measurable. That archive is
the only copy.

---

## 3. RESULTS THAT LANDED

### First `deployed`, current-box coding row — and the runaway tax, measured cleanly
`Ornith-1.0-35B-mlx-uniform-4bit / humanevalplus`, n=100, budget genuinely 81,920, 0 errors:
`acc` **93.0%** [87,98] ±13pp · **`acc_strict` 90.0%** · `conv` **97%** · median **108 tok/s** ·
median 18 s, p95 106 s.

| non-self-terminating turns | humanevalplus (n=100) | mbppplus (n=50 so far) |
|---|---|---|
| rate | 3% | 4% |
| **share of WALL-CLOCK** | **42%** | **57%** |
| share of tokens | 49% | 66% |

All ran to ~82,000 tokens against a budget **actually in force**, classified `degenerate_repetition`.
**⇒ ~40–57% of wall-clock lost to non-self-terminating turns, confirmed on three independent axes.**
Larger than everything Phase 2 shipped (1.27× suffix + 2–7% GQA).

### Corrected IFEval — the headline survives
`acc` unchanged (90.0% / 89.9%). `conv%` 99.3%→**94.6%** and 98.6%→**93.2%**; `acc_strict`
89.8%→**86.7%** and 88.5%→**85.1%**. Both arms moved the same way, so **"the two winners are EQUIVALENT
on instruction-following" stands.**

### Free re-grade of the whole corpus (68 cells, zero worker time)
`math500` under the vector for the first time: Ornith `acc` 83.3% but **9/30 budget hits → `acc_strict`
60.0%**, vs `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`'s **81.5%** at a matched 81,920 — same direction and
magnitude as LCB's spread.
Everything else is n=3–10 (±40–72pp), now labelled unrankable rather than shown as a number.
`Ornith-1.0-35B-mlx-uniform-4bit` has the only n=100 rows in the corpus besides IFEval.

---

## 4. THREE DEFECTS FOUND, ALL FIXED, ALL TDD

1. **The declared thinking budget was not the one in force** (`aca967b`). The server clamps
   `thinking_budget` to `0.8 * (max_kv_cache_size - prompt)` **silently** (its sibling `max_tokens`
   clamp logs a warning). IFEval declared 81,920 against a 65536 cap → really ~52,390. Reproduced to
   the token: every loop stop matches `int((cap - prompt) * 0.8)`, every `fr=length` row lands on
   `prompt + completion == cap + 1`. Fixed at the one seam every grader loads through.
2. **A manifest outlived its rows** (`a45a139`). Staleness is checked only when the jsonl exists, so a
   killed zero-row run leaves an orphan the next run won't overwrite. Rows generated at 131072 were
   stamped 262144.
3. **`max_kv_cache_size` was not in the provenance fingerprint** (`a45a139`) — `--clean-stale` was blind
   to a cap change and resume would have **silently pooled rows with different effective budgets**.
   ⚠️ Consequence: `--clean-stale` can now delete rows it previously kept.

Plus: `generate --help` crashed on a bare `%` (`aca967b`), and **`generate --ids`** now exists
(`78de435`) so a probe can vary one knob on the same items — previously inexpressible.

---

## 5. WHAT I DID NOT DO, AND WHY

- **The temperature-ladder probe on the runaway items is BLOCKED ON THE PUSH.** Well-posed and cheap
  (~90 min worst case): exact ids known (`HumanEval/94`, `/83`, `/144`, `Mbpp/560`, `/253`), budget
  genuinely in force, `--ids` written. But `--ids` is only in local commits, git is the only sanctioned
  cross-box transport, and AGENTS.md requires anything producing a recorded result to be committed
  first — so I did not work around it with a `/tmp` script.
  **Run it per temp with `MLX_BENCH_RESULTS` pointed at a separate tree per rung** — the manifest
  fingerprint includes temperature, so a shared tree would either clobber the baseline
  (`--clean-stale`) or skip every item (`done_ids`).
- **The `max_tokens <= cap` invariant test** — an honest assertion FAILS against the shipped config, so
  landing it would encode your O13 decision rather than surface it.
- **The prealloc-vs-cap OFAT** (O14's disentangling cell) needs NO new code — registry edit, router
  restart, a few items. **That is the right thing to run next**, since it keeps the box busy without
  waiting on a push.

---

## 6. YOUR DECISION QUEUE — four open (`docs/open-questions.md`)

| # | question | my recommendation |
|---|---|---|
| **O14** | `kv_prealloc_tokens == max_kv_cache_size` is an AGENTS.md rule costing >47×. The rule, the shipped registry, and which historical speed numbers to re-measure. | Run the disentangling OFAT first, then decide. The effect is CONFOUNDED — cap and prealloc moved together. |
| **O13** | `max_tokens` 102400 exceeds usable context on every shipped model; the resolved budget collapses to **9,708** at a 250K prompt. | Accept + document + log loudly. Lowering either knob trades capability at the prompt lengths that dominate use. |
| **O12** | M1's "not a DNF" ruling turned on item 2849 at "64% of budget" — really **100.2%** of the budget in force. | Re-rule as budget hits (the harness already does). Keep the M1 *principle*; it now applies to exactly 1 row. |
| **O9** | judge panel on looped-but-correct answers | **Drop it** — n is now 1, not worth panel time. |

**O11 → CLOSED-BY-MEASUREMENT.** 39 of 40 rows were external truncations, not self-terminations
(genuine share of wall-clock 0.3% / 0.0%, not 42% / 57%). **But its cost claim is CONFIRMED on a clean
footing** (§3), and its "prompt-triggered by counting instructions" hypothesis is **weakened** — the
loops appear on plain HumanEval code generation with no counting instruction present.

⚠️ **M1's recorded numbers have three problems** (details in `campaign-results.md`):
`.aider.results.json` records `completion_tokens` as a **per-case SUM across turns**, so "max completion
62,083 against an 81,920 budget" compared a sum to a per-turn budget (real max 148,908; 2 Ornith cases
exceed 81,920); "context-exhaustion 0 for both" is wrong (2 Ornith, 1 distill); and "0 of 284 turns hit
the budget" is **unverifiable** from the rows. **The M1 capability verdict is untouched** — 50.0% vs
73.6%, p=1.3e-05 rests on per-case pass/fail.

---

## 7. WHAT TO DO NEXT

1. **Push the five commits** (`aca967b`, `a45a139`, `e1404d9`, `78de435`, `9d0c70d`), then
   `git fetch && git merge --ff-only` on M5 — **do NOT `git checkout main_models.yaml`**, its 131072 is
   intentional (§8).
2. **Let the current run finish** (~2 h) → the campaign's first matched, current-box, `deployed`,
   execution-gated coding H2H at n=100, MDE ±13pp.
3. **The prealloc-vs-cap OFAT** — no push needed, answers O14.
4. **The temperature ladder on the runaway ids** — after the push. Highest-value performance work on the
   board: the tax is ~40–57% of wall-clock.
5. **Then** P4 / BFCL per the ratified sequence — but P4 must choose its cap deliberately: M1 ran at
   65536, so matching M1 means re-accepting the clamp.

---

## 8. TRAPS ADDED TODAY

- **M5's registry is intentionally dirty at `max_kv_cache_size`/`kv_prealloc_tokens` 131072** for both
  winners: it is the tightest cap that keeps the declared 81,920 budget in force, and 262144 destroyed
  throughput. `.bak` beside the file; the older 65536 dirt is at
  `/tmp/main_models.yaml.dirty-kv65536-backup` (md5 `6f758126068afee41c781b7189bd40fe`).
- **The documented IFEval resume now reports STALE** (148 rows at 65536 vs a 131072 registry). Without
  `--clean-stale` it warns and keeps them. **WITH `--clean-stale` it deletes all 148.**
- **`pkill -f mlx-serve` does not always kill the router** — it left pids 61111/61113/61295 alive.
  Force-kill by PID and verify 0 listeners on :8000 before restarting.
- **A flat item counter is not a stall.** This run had 9–10 min plateaus at n=21, 34, 41, 50 — every one
  a genuine ~82,000-token budget-runner. Distinguish with worker CPU time and the resolved-budget
  ceiling, not with impatience. Conversely the 262144 stall WAS real: same item, 19.5 min, no row.
- **`/metrics` `summary` only records on COMPLETION** (`generated_tokens_total` stays 0 while a request
  is in flight), so in-flight token progress is unreadable. That is why the first stall took 19 min to
  call — a real instrumentation gap.
- **Beware `a['x']` inside a single-quoted ssh command** — it terminates the shell quote. Two of my
  heredocs died this way.
