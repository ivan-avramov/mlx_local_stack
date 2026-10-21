# P426 — `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` MTP-ON router-chain re-certification — PLAN v1, 2026-10-21

Authority: P369 v13 §3.1 Restore + §6 (router-chain ON / OFF re-certification before restoring an entry's C177 lines), C177,
C203 (settings-level registry matching, bundled here), C204 (operator: ship a predictor that speeds up with no or negligible
quality / memory downside; operator judgement on ongoing quality / memory / speed signals, not strict thresholds; opencode
ON vs OFF as a primary workload; GPU cost no constraint). P369 phase 2 already passed for this entry (E1c 5 cells, E2; C188
carry-over + smoke 15 on production `7207179b`).

## 1. What this decides

Whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships MTP-ON again (its three C177 lines restored:
`mtp_verify_scan: joint_v1`, `draft_kind: mtp`, `draft_model: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter`).
The run produces per-axis SIGNALS (§4); the operator makes the call (C204). No automatic pass / fail.

**Attention flags** (raise to the operator with a recommendation; never an automatic veto): any quality axis with ON − OFF point
< −5 pp, or an interval excluding 0 on the negative side; ON 256K peak > OFF + 2 GB, or ON > ≈ 48 GB; decode ratio ON / OFF
< 1.3× on any axis; pooled acceptance below 0.70 (references, context only: M40 Math500 0.78 pooled on TQ4 KV, M42 native16
0.78–0.82 at 131K–262K); any non-convergence kind present in ON and absent in OFF.

## 2. Arms (identical except the predictor)

- **OFF** = the live registry as committed (Fable's C177 lines commented). **ON** = `registry_states.overlay_on(live, fixture,
  "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed")` (fork `dev/p369_phase2`, byte-level today; the C203 matcher once landed),
  written to `$STACK_WORKDIR/p426/overlay-on.yaml`; both texts' sha256 recorded. The overlay differs from the live registry in
  exactly those three lines (asserted before every ON arm).
- Same stack commit, `src/mlx-vlm`, weights, tune (t0.5, medium effort), native16 KV (`kv_bits: 0`), cap / preallocation
  262,144, prefill step 512. `joint_v1` is ON-only by construction (requires `draft_kind: mtp`).
- Lean router per AGENTS.md: `MLX_VLM_CACHE_SESSION_MAX=1`, `APC_ENABLED` absent, no OWUI / docker; `MLX_SERVE_CONFIG=<arm
  registry>` exported to router AND driver; fresh router start per arm (`scripts/stack_stop.sh`, :8000 free, new ownership,
  M50 checks); worker cmdline recorded — ON has `--draft-kind mtp`, OFF has none; first manifest's `runtime.draft_kind` and
  `registry.sha256` verified before item two.
- **Waves.** Wave 1 runs on production `7207179b` (current `src/mlx-vlm` `2e66d89d`). Wave 2 (opencode) runs after the B1
  logging bump. Pairs are always within one wave (ON and OFF on the same build); nothing pools across waves.

## 3. Axes

Wave 1 (existing tools; no build needed):

| Id | Axis | Run | Signals | Wall (M40 / M42 reference) |
|---|---|---|---|---|
| A1 | Math500 100×1 | `run.py generate --benches math500 --ids` = M40's 100 ids (recovered from `math500.m40on.jsonl`, committed as `benchmark/results/p426/math500_ids.txt`), `--sampling-profile deployed --order roundrobin --seed 0 --seed-base 0 --samples 1`, timeout derived | `acc_strict@81920`, conv%, nonconv kinds; decode tok/s; acceptance (`row.draft`); wall | ON 1.2 h, OFF 2.2 h |
| A2 | cjudge 40 generation | same runner, `--benches cjudge` | outputs for the panel (judging under B3); conv%; decode; acceptance | ON 1.1 h, OFF 1.6 h |
| A3 | Vision gate 20 | `benchmark/vision_gate.py --model …` | pass / 20; turn-1 latency, decode | ≈ 10 min each |
| A4 | Reasoning depth 128K, 3 draws | `bench.run_reasoning --grid 128000 --samples 3 --chain-len 4 --sampling-profile deployed` | strict draws, budget hits; decode; acceptance | ON 24 min, OFF 33 min |
| A5 | Memory: capacity ladder | `bench.run_capacity` 131,072 / 196,608 / 262,144 through the router | MLX peak per rung (`mx.get_peak_memory` prefill spike), prefill / decode tok/s, acceptance | ≈ 40 min each |
| A6 | Memory: R7 OFF control | fork `p400_perf_probe.py qualify --entry …` as served (MTP-OFF) | 256K peak paired with R7's MTP-ON 38.25 GB | ≈ 15 min |

Wave 2 (needs B1, B2):

| Id | Axis | Run | Signals |
|---|---|---|---|
| A7 | opencode tg1, the primary agentic benchmark (README: 43 items × 2 sessions) | the c147 tg1 chain, Fable only (B2): pilot (5 seeded-random) → s1 (seed 1001) → s2 (2002, opposite order) per arm, each block a fresh load (k = 2 instances per arm), + same-seed reload control (5 items); ON and OFF in the same epoch | `acc_strict@budget` per session (two-stage cluster bootstrap), runaway tax (budget-hit / turn-cap / exec-timeout); session wall; per-request decode tok/s + acceptance from the B1 log line; per-session MLX peak |

Before n ≥ 40 enters the queue: `--limit 5` smoke (seeded-random items) per runner. Order: arms alternate per axis (A1 OFF→ON,
A2 ON→OFF, A3 OFF→ON, …); ≥ 10 min idle between arms; power (`pmset -g ac` 140 W / 28 V, battery > 20 %) logged per tick and
`pmset -g log` checked against every arm window (P418) — an on-battery interval in a window marks that arm's SPEED signals
invalid (quality stands). `benchmark/m1/bench_watch.py` (B5 for reasoning) or the chain's built-in watch every 5 min.

## 4. Signals sheet (the operator's view)

B6 generates `benchmark/results/p426/SIGNALS.md` from rows / manifests (never hand-copied), regenerated after every arm. One row
per axis: quality (ON, OFF, ON − OFF with paired two-stage cluster-bootstrap 95 % interval, axis MDE; a WASH is labelled per
C172), memory (ON / OFF peak, Δ), speed (decode tok/s ON / OFF, paired ratio with interval; pooled and per-row acceptance; wall
ratio), coverage (arms done / pending), flags (§1). Holm across the quality axes. Descriptive only — no composite.

## 5. Builds (test-first; each its own Cursor code review, ≤ 3 rounds)

- **B1 (fork, production log-only):** the `Request completed` line gains `draft_kind=… draft_rounds=… draft_n=… draft_n_accepted=…`
  when a drafter ran (absent otherwise). Red test: a drafted request's line lacks them. Production diff = the format string and
  its arguments only. Stack bump after review + suites (both repos).
- **B2 (stack):** the tg1 chain driver takes a single model (Fable) and builds its ON overlay through the shared overlay
  function (C203), replacing the verbatim copy that refuses when `draft_kind: mtp` is absent.
- **B3 (stack, own proposal P427):** the C161 / C166 two-judge, two-provider panel configured per box (m5max-128: Claude Opus via
  Claude Code + Cursor `gpt-5.6-sol-high`), model id / client version / prompt sha recorded per verdict, the family map covering the
  Cursor label, the length-adjusted two-judge estimator. A2's judging waits for it; A2 generation does not.
- **B4 (fork + stack, C203):** the settings-level registry matcher (`registry_states`), the overlay uncommenting the live text;
  the stack's overlay builder uses the same rule (pinned table mirrored from `ENTRY_OFF`, cross-checked against the fork module).
- **B5 (stack):** `bench_watch.py` follows `reasoning.<tag>.partial.jsonl`.
- **B6 (stack):** `benchmark/bench/recert_signals.py` → `SIGNALS.md` (§4); also parses the B1 log lines and attributes them
  to tg1 items by session id and the item's request window.

## 6. Restore

On the operator's ship-ON call: restore exactly the three C177 lines, add `CERTIFIED P426 <date>` (or `PROVISIONAL`) in
`generation_defaults`, update `benchmark/bench/tests/test_opencode_probe_seeding.py` (`per_query` → `joint_v1`, source
"registry"), README / campaign-results evidence rows, in one commit; under C203 no fixture refresh is needed. Clients: no
sampling change (registration-only clients unaffected). On ship-OFF: record the signals; lines stay commented.
Then the same plan per entry: `Qwen3.8-27B-mlx-uniform-4bit` and `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` after P405 R6 (their
codec), `Ornith-1.0-35B-mlx-uniform-4bit`.

## 7. Estimate and order

R5 (running, ≈ 6.5 h) → Wave 1 (≈ 9.5 h GPU: A1 3.4, A2 2.7, A3 0.3, A4 1.0, A5 1.3, A6 0.25, idle ≈ 2) while B1–B6 are built
and reviewed → B1 bump → Wave 2 (≈ 12 h: tg1 ON 3.1 + OFF 7.0 from M63, pilots, reload, idle). Lower bounds; heavy-tail allowance
+30 %. Signals sheet after every arm.

## 8. AGENTS.md amendment (operator)

C204 replaces "ship OFF if OFF wins beyond ±5pp on any axis" with a judgement call. Proposed wording for the Registry section:
"Certify the predictor ON vs OFF on every supporting axis plus memory and speed; ship it when it speeds up with no or negligible
quality / memory downside — the per-axis signals go to the operator for the call; −5 pp on an axis is a flag, not a veto."
