# Handoff — rewritten 2026-08-24 ~18:15 (M18 surgical re-runs IN FLIGHT at 195/200; O40 fork set PUSHED + submodule BUMPED; restart-safe checkpoint)

Single box (M5 Max 64 GB). **WORK IS RUNNING, all PPID 1 (survives session restarts):**

| what | pid | notes |
|---|---|---|
| lean router :8000 | 21160 | old code in memory (started 00:14); serves the surgical run |
| surgical driver | 47134 (child 54373) | `$STACK_WORKDIR/bfcl_m18/surgical_all.sh`; log `…/surgical_all.log` |
| M18 watcher | 57570 | busy-threshold fixed to >10% CPU (dense decode reads ~35%, NOT idle) |

**RESUMING SESSION: (1) verify the table above; (2) re-arm the alert tail on
`…/bfcl_m18/m18_watch.log` + `…/surgical_all.log` (grep SUSPECTED|POISONED|SURGICAL|RESCORE|
Traceback); (3) WAIT for `=== SURGICAL ALL DONE ===` — the three rescores run inside the
script, zero model time; (4) then run the O40 smoke: `$STACK_WORKDIR/o40_smoke/smoke.py`
(port 8093, overlay configs, checks fail-loud + engagement on batched AND cached paths).**

## State of the surgical leg (the last one)

`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` full `parallel_multiple` (200 items): started 11:28,
195/200 at 18:12. ~6 h, not ~1 h — because **the model's "0 runaways in 1000" was an artifact
of the dead-port poisoning: this category runs ~2% full-budget runaways (4 in 197), each
82K tokens at ~20 tok/s = 66-81 min wall.** That inverts the morning's runaway-tax comparison:
similar RATE to `Ornith-1.0-35B-mlx-uniform-4bit` (~2% in parallel categories) but ~3.5x the
per-event cost. Record this with the final scores. `Ornith-1.0-35B-mlx-uniform-4bit` and
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` result trees are already fully clean (0 poisoned).

## O40: fork set PUSHED, submodule BUMPED (operator-directed, no cross-repo path hacks)

`../mlx-vlm` pushed `0be496bf..05a41b1b` (3 commits: fail-loud drafter config; thinking_budget
in `_mtp_rounds` inline; mtp on the cached path + scoped gate; thinking_budget on the batched
path B==1). Fork suite 3269 passed. Stack bump committed `4c36a5f`; verified `.venv` imports
`mlx_vlm` editable from `src/mlx-vlm` (the O40 symbols resolve). mlx-serve needed NO work
(registry `draft_kind`/`draft_model` -> worker cmdline already plumbed). The in-flight leg's
worker runs the NEW sha at plain decode — verified NO draft flags at the worker cmdline, and
every O40 hunk is drafter-gated, so the serving path is unchanged for this measurement
(mixed-sha justification; note it in the lab notebook with the scores).

**After the smoke passes**: results-data commit (`data(bench)`; trees are clean of PII once
poisoned rows are gone — VERIFY with bench.piicheck before staging), lab-notebook entry
(final 3-model table + runaway-tax correction + watcher busy-threshold lesson), then M6b
quality OFAT (mtp ON vs OFF at deployed params, engagement tripwire on every arm), M23
(~4 h), M24. Stack is 2 commits ahead of pushed `493b24e` (the bump `4c36a5f` + docs) — push
needs a fresh operator word.

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
