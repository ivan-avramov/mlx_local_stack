# Handoff — rewritten 2026-08-24 ~10:45 (M18 GENERATION COMPLETE all 3 models; O41 fix LANDED; operator ratified O39/O40/O41 + sequencing; surgical re-runs are the next machine work)

Single box (M5 Max 64 GB), single attended session. **No benchmark is running at this checkpoint.**
The lean router on :8000 (pid 21160, PPID 1, `MLX_VLM_CACHE_SESSION_MAX=2`, no APC) is UP and idle
with `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` resident — kept deliberately: it is the first
surgical-re-run target. Suite: **1197 passed, 0 failed.** `origin/main = bcc6d37`; local commits
now include this session's six (M24 harness `de2d6d8`, mtp tripwire `042e402`, O41 fix `ede38e6`,
test repairs `65d6730`, registry M23 entry `44589e7`, docs — see log). **NO push yet: needs the
operator's explicit in-turn word.**

## M18 BFCL native-FC — generation complete (10:27:42), scores pre-re-run

| category | `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | `Ornith-1.0-35B-mlx-uniform-4bit` | `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` |
|---|---|---|---|
| simple_python | 0.9475 | 0.935 | 0.8875 |
| multiple | 0.970 | 0.945 | 0.895 |
| parallel | 0.895 | 0.880 | 0.840 |
| parallel_multiple | 0.896 (48 surviving) | 0.845 | 0.785 |
| **overall** | **0.9375 provisional (848 clean)** | **0.908 (bound –0.912)** | **0.859 (bound –0.860)** |

Leader on every category is `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, but the ~2.7 pp overall gap is
INSIDE the axis MDE — **inconclusive until its `parallel_multiple` re-runs at full 200**. Runaway
tax (4th ranking number): 0/1000 vs 4/1000 vs 1/1000 — real, model- and category-specific (all in
the parallel categories). Full story: lab-notebook 2026-08-24 entries; refusal semantics below.

## O41 (landed, `ede38e6`): transport failures ESCALATE, never grade

The 600 s OpenAI-SDK default client timeout was SHORTER than a legitimate full-budget generation
on every pick (20.7 min / 66.3 min / 11.7 min measured or projected) — every budget-hit became an
error row graded as a wrong answer, the worker (no cancel-on-disconnect) burned ~95 min per
runaway across 3 retries and starved one healthy neighbour each. Now: timeout = max generation ÷
12 tok/s floor + 300 s headroom (`MLX_BFCL_TIMEOUT_S` overrides), `max_retries=0`, any
`openai.APIError` → SystemExit(86) past every `except Exception`, and the grader REFUSES any tree
holding `"Error during inference"` rows (acc null + ids). 9 tests, TDD.

## NEXT (operator-ratified sequencing, C20)

1. **Surgical re-runs** (zero-cost recovery of answered-but-discarded items):
   - `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (RESIDENT NOW — do first): `parallel_169`.
   - `Ornith-1.0-35B-mlx-uniform-4bit`: `parallel_80/81`, `parallel_104/105`,
     `parallel_multiple_70/71`, `parallel_multiple_91/92`.
   - Mechanism: bfcl_eval run_ids file with EXACTLY these ids, `run_ids=True` (update-in-place),
     ONE resident model at a time (`POST /v1/models/unload` between).
2. **`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` `parallel_multiple` full 200** (~1 h + runaway margin;
   152 rows were dead-port poisoned, unrecoverable by re-grade).
3. Re-score all three via the poison-guarded rescore (`$STACK_WORKDIR/bfcl_m18/rescore_m18.py`),
   un-null the accs, THEN commit `benchmark/results/**/bfcl_fc` — **results are deliberately
   uncommitted until then: poisoned rows carry `traceback` fields with absolute home paths (PII)**.
4. **O39 (C21)**: go-language M3 replication (~40 min/model) BEFORE any M9 spend.
5. **O40 (C19, GO)**: MTP fork work — cached-path dispatch + thinking_budget + fail-loud. DESIGN
   PLAN FIRST (the MTP path produced silent no-ops twice). M6b OFAT follows it.
6. M23 (both arms fresh, ~4 h), M24 (harness committed `de2d6d8`).

## Standing footguns (new ones from this session)

- **rtk condenses git output — a rejected commit can print what looks like success. ALWAYS verify
  `rc` + `git log -1` after committing; never pipe the attempt through `| tail`.** Two hook
  rejections (bench.modelnames) were initially misread as landed commits this way.
- The modelnames hook rejects shorthand in ADDED lines incl. comments — full registry names or
  `allow-shorthand` marker.
- A silent-but-BUSY worker is a runaway (do NOT kill); silent-and-IDLE is a wedge (kill by PID).
  Watcher with the discriminator: `$STACK_WORKDIR/bfcl_m18/m18_watch.py` (exits when its driver
  dies; re-arm alongside any new run).
- `MLX_VLM_CACHE_SESSION_MAX=2` on every router start; `os.setsid` for anything long-lived;
  full registry names everywhere incl. chat prose.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md` (C19–C23 are the
fresh operator decisions).**
