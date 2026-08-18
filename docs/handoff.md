# Handoff — the one handoff document

**DATING NOTE (2026-08-18 merge):** this handoff was written 2026-08-17 07:58 on the OLD driver
box, before that box was retired. The single-box (M5 Max) sessions of 2026-08-17/18 executed or
superseded most of it — `docs/PLAN.md` is current; read this as the last old-box narrative until
the next session rewrites it.

**Rule, operator instruction 2026-08-16: there is exactly ONE handoff.** Each session REWRITES this file
in place. Six earlier handoff/handover docs were mined for every still-open item and then deleted; do not
create a second one.

**Read `AGENTS.md` first, then `docs/PLAN.md`, then `docs/open-questions.md`.** This file is only the
last session's narrative: what moved, what is running, and what to distrust.

| file | role |
|---|---|
| `AGENTS.md` | the rules, the traps, the operational facts |
| `docs/PLAN.md` | the plan: two decisions, model field, ordered queue (§3, §3.1, §3.2, §3.3) |
| `docs/work-queue.json` | the EXECUTABLE queue, run by the `bench.workqueue` daemon |
| `docs/open-questions.md` | the decision queue — **2 items open**, everything else closed |
| `docs/campaign-results.md` | recommendations + the GENERATED scoresheet |
| `docs/lab-notebook.md` | THE history (the retired campaign-queue.md was folded into it) |

---

## STATE: nothing is running. The worker is idle with `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` resident.

**The paired suffix OFAT COMPLETED** — 400/400 draws, ~5 h. All four arms are on disk:
`{humanevalplus, mbppplus}` × `{Ornith-1.0-35B-mlx-uniform-4bit, Qwen3.6-27B-Opus-Distill-OptiQ-4bit}`,
suffix OFF, cap 131072, `deployed` sampling, `presence_penalty 0.0`, fingerprint v3 recording
`draft_kind: off`. The suffix-ON arms are archived beside them as `<bench>.suffixon.{jsonl,manifest,score}`.

**IT IS NOT GRADED, and that is the first thing to do because it costs ZERO worker time** (`grade_evalplus`
runs the official evaluator in docker). Until it is graded there is **no accuracy number**, so the ≤5%
gate — the whole point of the OFAT — is unanswered and **O25 cannot be decided.**

```
PYTHONPATH=benchmark .venv-bench/bin/python benchmark/run.py grade \
  --models Ornith-1.0-35B-mlx-uniform-4bit,Qwen3.6-27B-Opus-Distill-OptiQ-4bit \
  --benches humanevalplus,mbppplus
PYTHONPATH=benchmark .venv-bench/bin/python -m m1.suffix_ofat \
  --model Ornith-1.0-35B-mlx-uniform-4bit --bench humanevalplus --json-out /tmp/ofat_o_hep.json
```

---

## What the OFAT established, and the one claim I retracted

**ESTABLISHED — suffix changes the text on most items.** Per-item divergence **74% / 78% / 57% / 49%**
across the four arms. Not arguable any more, and it is why the state had to enter the fingerprint.

**ESTABLISHED — the speed benefit is real but generalises badly.** Decode delta (ON − OFF) is
**+35.0 and +28.1 tok/s** on `Ornith-1.0-35B-mlx-uniform-4bit` but only **+5.8 and +3.7** on
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Per item, suffix SAVED 165 s on
`Ornith-1.0-35B-mlx-uniform-4bit` humanevalplus and COST 21–41 s on both
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` arms. **Do not quote "1.27×" as a general figure.**

**RETRACTED — "suffix suppresses degeneracy".** I reported this from arm 1 mid-run at 5–0 then 6–0
discordant. The completed experiment does not support it:

| model | bench | OFF deg | ON deg | discordant | McNemar p |
|---|---|---|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` | humanevalplus | 14 | 2 | **12–0** | **0.0005** |
| `Ornith-1.0-35B-mlx-uniform-4bit` | mbppplus | 4 | 4 | 3–3 | 1.000 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | humanevalplus | 0 | 1 | 0–1 | 1.000 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | mbppplus | 0 | 2 | 0–2 | 0.500 |
| **pooled** | | 18 | 9 | **15–6** | **0.078** |

**Pooled it is NOT significant and the sign is inconsistent** — both
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` arms went the other way. One cell of four carries the whole effect,
and it is the cell I happened to be watching live. That is consistent with the theory: accept-iff-equal on
a deterministic proposer is distribution-preserving, so suffix *cannot* change the degeneracy rate.

⚠️ **But that cell survives Holm on its own** (0.0005 × 4 = 0.002), and it is a 12–0 split where items went
from ~1,500 to ~82,000 tokens. A genuine anomaly confined to one model×bench cell, not dismissible as
multiplicity. **The cheap test that settles it: re-draw those 12 discordant items at suffix-OFF with fresh
seeds (`--samples 3`).** Degenerate every time → a real property of the non-speculative path, and then read
that path for a bug, because the theory says this should not happen. Degenerate sometimes → variance, and
the paired design needs samples rather than items.

---

## Everything else that changed (29 commits, 9 unpushed)

- **Suffix OFF on all five models**, verified at the WORKER COMMAND LINE in both directions.
- **Fingerprint v3**: `draft_kind` is now POPULATED (it was named-but-never-written, so it read as a
  wildcard on every row). `compare` refuses across draft state for quality metrics as well as speed.
- **THREE guard gaps found and closed, all the same shape** — a knob was in the provenance fingerprint and
  never mirrored into `compare`'s guard list: `draft_kind` (refuses), `max_kv_cache_size` (WARNS per
  operator ruling, plus `cap_partition()`), and the PENALTIES (refuses — a nonzero penalty also turns
  suffix off, so it changes the serving path too). **Worth a systematic pass rather than a fourth
  discovery: diff `_FINGERPRINT_SAMPLING` + `_FINGERPRINT_RUNTIME` against `_MUST_MATCH_SAMPLING`.**
- **PII scrub**: 11 tracked files carried a username in a home path into this public repo. History
  rewritten and force-pushed; `bench.piicheck` in `githooks/pre-commit` blocks recurrence. O27 closed —
  wait for GitHub's own gc, so the pre-scrub commit stays fetchable by sha until then (accepted risk).
- **The scoresheet was publishing the pre-correction ifeval `conv%` (99/99 vs the true 95/93)** because
  `scoreboard.py` re-derived convergence from rows that never persisted `resolved_thinking_budget`. It now
  reads graded numbers and never recomputes them, with a staleness detector.
- **Docs: 13 files → 6.** Seven handoffs → one. Two queue files → one queue in two forms. Two history files
  → one. The decision queue went from 37 blocks under an "OPEN" heading to **2 genuinely open**.
- **O28 closed by code reading:** the `presence_penalty`-disables-suffix gate is REAL —
  `_suffix_structured_fallback`, mlx-vlm `generate/ar.py:163`, called `:648`. And the lever is a measured
  NO-GO: `context_size` is 20 so it reaches only cycles of period ≤20 tokens; all 17 reachable rows are
  ifeval and zero are coding; the accuracy ceiling is 1.1pp against a ±5.4pp MDE; and **degenerate loops
  cost TIME, not accuracy — 6 of 10 degenerate coding rows still PASSED their plus-tests.**
- **O29 closed:** cap mismatch WARNS and `cap_partition()` names the rows the cap could have touched — only
  **39 of 889** IFEval draws are cap-sensitive, so that re-run is 22.8× cheaper than the axis re-run.
- New tools: `benchmark/m1/suffix_ofat.py` (paired analyser), `benchmark/bench/cycles.py` (loop-shape
  measurement), `benchmark/qwen38_smoke.py`, `run.py --presence-penalty/--repetition-penalty`.
- **864 tests pass.**

---

## Distrust these

- **`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`'s "43.3 GB peak @262144" matches NO field in its own
  `capacity_ladder.jsonl`** (`server_peak_gb` 37.576, footprint 42.70, system 56.25), while the other two
  models match `server_peak_gb` exactly. The memory-gate table mixes metrics on the one model where the
  46 GB margin is tight. **Unresolved.**
- **`campaign-results.md`'s recommendation section still needs corrections**: the B-pick "rests on a retired
  harness" sentence, the serving-path caveat on the 3.75-malformed figure, and four latency numbers that do
  not reproduce (median 18 s vs 21 s is really 15.6 vs 20.6; "3.1× more tokens" is 2.07×).
- **`Ornith-1.0-35B-mlx-uniform-4bit-suffix/`** has 100 humanevalplus rows with **0 degenerate** at cap
  262144, but its model name was not in the committed registry at its sha, so its suffix state is
  **unresolvable from provenance**. Tempting as an independent arm; do not use it until settled.
- **The reasoning axis is unusable as a comparison for anyone.** The winners' `math500`/`aime`/
  `livecodebench` rows are `official` profile from a retired box;
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` has none. GPQA is the only clean route (nobody has legacy
  rows) but needs a 5-item pilot first.
- **The `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` aider artifacts are UNCOMMITTED**, living only under
  the worker's aider tree. They reproduce 3.75/case exactly. Commit them or they die with the box.

---

## My error pattern this session — four instances of ONE mistake

Every one was *trusting an instrument or a subset instead of checking it*, and each produced a confident
wrong number:

1. **Reported from a prefix of ARMS** — the retracted degeneracy finding. A new variant of the rule
   AGENTS.md already carries for item prefixes.
2. **A field name read as a definition** — `truncated` means the persisted reasoning TEXT was excerpted for
   storage, not that generation was truncated. It made 249 of 541 rows look cap-sensitive; the real figure
   is 29.
3. **A false zero from a path assumption** — checked `.suffixon.jsonl` on the driver when those archives
   live on the worker; got "0 of 0" degenerate rows and nearly believed it.
4. **Sized a job from a median when the items were selected FOR being runaways** — quoted "~15 min" for a
   job that is ~40. The pilot rule exists for exactly this.

The corollary now in AGENTS.md: **verify elapsed time from `ps -o etime`, not from your sense of when you
launched something** — I raised a "13× slowdown" alarm on a run that was 21 minutes old, not 47.
