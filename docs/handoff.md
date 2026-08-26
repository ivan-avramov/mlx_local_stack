# Handoff — rewritten 2026-08-26 ~08:30 (M23 INVALIDATED by a C28 orphan cascade; C28 FIXED; M23b re-run IN FLIGHT)

Single box (M5 Max 64 GB). **WORK RUNNING, all PPID 1 (survives session restarts):**

| what | pid | notes |
|---|---|---|
| bench router :8000 | 34276 | lean, **draft-OFF overlay** `$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`, SESSION_MAX=2, APC off |
| M23b official arm | 11247 | `Qwen3.8-27B-4bit` 20/bench, tune `m23b`, **`--probe-timeout 5200` PINNED**; log `$STACK_WORKDIR/m23/arm_official_m23b.log` | <!-- allow-shorthand -->
| M23b watcher | 19803 | 5-min ticks -> `$STACK_WORKDIR/m23/watch_official_m23b.log` |

## 🛑 READ FIRST: the 2026-08-25 M23 result is INVALIDATED. Do not cite any M23 DNF rate.

`Qwen3.8-27B-mlx-uniform-4bit`'s arm was corrupted by a **C28 orphan cascade**: an abandoned
generation is never cancelled, so one runaway starves its successor into a false DNF, which adds
another orphan. mbppplus items 34-39 were a CONSECUTIVE block of six false timeouts and `grade`
failed the run on its own guard (HARNESS-BROKEN, 35 % > 20 % error rows). Every rate quoted that
day (33 % / 25 % / 12 % / 25 %) is RETRACTED.

**Controlled protocol that separated the mechanisms** (reuse it — an uncontrolled re-run
REPRODUCED the artifact and looked like confirmation): `unload` -> **`pgrep` to VERIFY zero workers
resident** -> load fresh -> ONE item. Killing a driver does NOT stop the worker; a killed run's
orphan contaminated the first diagnostic.

| item | in-arm | contended re-run | CLEAN single | `Qwen3.8-27B-4bit` | verdict | <!-- allow-shorthand -->
|---|---|---|---|---|---|
| `Mbpp/803` | DNF 3600 s | DNF 900 s | **CONVERGED 107.2 s** | 10.8 s | cascade ARTIFACT |
| `HumanEval/146` | DNF 3600 s | — | **DNF 1800 s** | 279 s | GENUINE runaway |

**Both mechanisms are real; the observed rate is their sum and is uninterpretable.** Surviving
findings: on GENERATED items `Qwen3.8-27B-mlx-uniform-4bit` scores HIGHER (humanevalplus 94.1 % vs
87.5 %, mbppplus 84.6 % vs 79.6 %) and is ~10x more VERBOSE at a matched seed (`Mbpp/803` 2848 vs
262 tokens). So "our conversion suppresses quality" is NOT supported; "it is verbose and sometimes
fails to terminate" is. The M23 row's pre-registered caveat trigger is **NOT** met — do not apply
the conversion-artifact caveat or re-prioritise M21/M22 until a valid rate exists.

## C28 FIXED (`b2c3542`, `673b65e`) — and it changes how every run is launched

`--probe-timeout` now DERIVES its default from the model's measured slow-tail decode rate
(`budget_timeout.floor_decode_tps` + `derive_timeout`), so the bound always clears full-budget
generation and **nothing is abandoned in normal operation — no orphan, no cascade**. `bench/
budget_timeout.py` had documented this exact defect and had the derivation all along; the main
generate path had simply never adopted it. `probe_timeout_s` now rides in the manifest runtime
block, RECORDED but not blanket-fingerprinted, and `compare` refuses a mismatch only when the
smaller bound COULD have bound (the `max_kv_cache_size` ruling-7 shape).

⚠️ **For a PAIRED A/B, PIN the bound explicitly and identically on both arms.** Per-run derivation
gave 5055 s vs 5134 s for the two models, which `compare`'s own new rule would then refuse. M23b
uses `--probe-timeout 5200` on BOTH arms.

## M23b (IN FLIGHT): the re-run

New tune label `m23b` so the invalidated `m23` rows stay as evidence and cannot pool. 20 items per
bench, seed 0, deployed profile, `--order model`, one resident model with unload between arms.

🛑 **SUPERSEDED 2026-08-26 ~13:00 (session review): the `Qwen3.8-27B-mlx-uniform-4bit` arm is HELD — do NOT launch it.**
C26 escalated: same model, same items, same declared seeds, two sessions (m23 vs m23b official)
→ **0/20 byte-identical**, `HumanEval/146` 7,106 → 82,168 tok (converged → budget-hit). Per-item
PAIRING does not exist on this serving path; every matched-seed M23 contrast dissolves. Unpaired
A/B remains valid (log-token rank corr across sessions 0.84 — chaotic tail redraws, not a session
shift) but spending 8 h on that arm BEFORE the design gate would risk another unusable arm.
Also note: m23b official humanevalplus has 0 DNFs but **2 budget-hits** — a reclassification
(the instrument getting honest), never to be narrated as recovery; budget-hit ≠ completed.

**NEXT STEPS: (1)** when 11247 exits: unload `Qwen3.8-27B-4bit`, **VERIFY `pgrep -f <!-- allow-shorthand -->
mlx_vlm.server` EMPTY**, then STOP — no new arms. **(2)** grade the m23b official rows
(`run.py grade --models Qwen3.8-27B-4bit --benches humanevalplus,mbppplus --tune m23b`) and <!-- allow-shorthand -->
extract the mbppplus half of the m23/m23b session replicate for C30. **(3) C26 FORK FIX**
(../mlx-vlm, TDD: per-request seeds must reach the cached-path sampler; C24's
`speculative_stats_since` plumbing is the pattern for threading per-request state). **(4) the
design gate**: one item, same seed, TWO sessions, byte-compare → equal: paired m23c re-run, both
arms pinned 5200 s; different: unpaired, ≥2 sessions/arm, ABBA order, quote the ~√2-worse MDE.
**(5)** then M24; cancel-on-disconnect stays queued as defence-in-depth.

## New since 2026-08-24 evening (all committed; pushed through `a55d382`, LOCAL AFTER THAT)

1. **M6b PASSED — the pick ships its (model, tune, predictor) triple.**
   `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` + t0.3 + `draft_kind: mtp` (native sidecar
   drafter). Paired 63-item OFAT: acc 0.9524 vs 0.9365 (delta +1.6pp CI [0.0,+4.8],
   TOST ±5pp EQUIVALENT, p_d=0.016, powered), 100% engagement @ 0.923 acceptance,
   ~2× decode, 0 degeneracy. Registry commit `ca4ed0f` (drafter = `caslca/` placeholder,
   NOT-YET-UPLOADED; local override in the working tree). Lab-notebook entry has the
   full table.
   **⚠️ STANDING CHANGE: bench router starts MUST strip draft fields** (the registry now
   serves mtp for the pick; measurement stays predictor-OFF). Overlay generator output:
   `$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`; regenerate after any registry edit.
2. **O39: the M3 inversion does NOT replicate on go** — 11/22 vs 12/22, McNemar p=1.0.
   M9 NOT triggered (C21 rule); C27 records it. Mechanism: path-infidelity give-ups are
   model-general (`Ornith-1.0-35B-mlx-uniform-4bit` shows them in go); TMPDIR prefix
   shape is output-determining for that mode (raw `$TMPDIR` vs `scratch/octmp`: 0/5 →
   2/5 same items). opencode pinned 1.18.15 via downloaded binary (brew drifted to
   1.18.20; version guard caught it).
3. **O40 COMPLETE at fork `61845457`**: batched PASS, cached PASS (C24 counters live),
   fail-loud verified at the worker contract (rc=3; note worker stderr lands in
   `$TMPDIR/mlx-manager-logs/<model>.log`, reopened per start). C25 fixed (penalties +
   inline mtp now fall back to plain decode). Bench rows persist `draft` counters
   (`479fd37`) — the engagement tripwire instrument.
4. **C26 seed bug CONFIRMED**: per-request seeds IGNORED on the cached path (byte-identical
   at t=1.0 across seeds). Single-sample runs unaffected; audit any multi-sample
   cached-path run before trusting pass^k/reliability numbers. Fork fix QUEUED (not started).

## M23 (IN FLIGHT): conversion-bias A/B, `Qwen3.8-27B-4bit` (official) vs `Qwen3.8-27B-mlx-uniform-4bit` <!-- allow-shorthand -->

Gate-3 2×50 recipe (humanevalplus 50 + mbppplus 50, seed 0 — REPLICATES the O37-era
draws), both arms fresh, t0.6 via registry `generation_defaults` (deployed profile, no
overrides), tune label `m23`, `--order model`, one resident model with unload between
arms, 5-item pilot per arm first (nested seeded draw → resume-clean). Official arm
pilot first (model already in hf cache). Rows: `benchmark/results/<model>/<bench>.m23.*`.

## Operator actions — ALL THREE RESOLVED 2026-08-25 (afternoon session)

- **Drafter UPLOADED**: `caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter` is
  public (anonymous resolve 200, all four files). Registry note cleared in `fee1721`;
  the box keeps its local workdir `draft_model` override in the working tree.
- **Pushed** through `722e739` (operator-approved in turn); `fee1721` + docs commits
  after it are LOCAL and need fresh approval as usual.
- **C26 fork fix funded AHEAD of M24** (operator ruling): starts after the M23 arms
  complete — no fork test runs against the box mid-measurement.

## Standing footguns (delta from 2026-08-24)

- The mtp certification makes a **stale bench router the new top hazard**: a router
  started from the raw registry serves the pick mtp-ON and poisons any measurement that
  touches it. Always start bench routers from the draft-stripped overlay and verify
  drafter-flag state at the worker cmdline per arm.
- The evalplus per-item results file pads to the FULL corpus (164/378); restrict paired
  analyses to the generated ids or the CI tightens artificially.
- opencode brew updates silently; the probe's pin guard is the only defense — keep the
  1.18.15 binary in `$STACK_WORKDIR/o39/opencode-1.18.15/` for replications.
- A single-notification waiter must match FAILURE modes too, not only the success
  string — a grep-until armed on a condition that can never occur idles the pipeline
  silently (cost: ~9 h on 2026-08-24 night).
- rtk condenses git output — verify `rc` + `git log -1` after every commit; both guard
  hooks fired real rejections this session and the condensed output looked like success.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md` (C24–C27
closed/recorded; C26 fix and the drafter upload are the open items).**
