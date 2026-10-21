# P426 — `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` MTP-ON router-chain re-certification — PLAN v2, 2026-10-21

Authority: P369 v13 §3.1 Restore + §6, C177, C203 (settings-level registry matching, bundled here), C204 (ship a predictor that
speeds up with no or negligible quality / memory downside; operator judgement on ongoing quality / memory / speed signals, no
strict thresholds; opencode ON vs OFF as a primary workload; GPU cost no constraint). P369 phase 2 passed for this entry (E1c 5
cells, E2; C188 carry-over + smoke 15 on production `7207179b`).

v2 applies Cursor plan round 1 (`docs/reviews/p426/plan-round1.*`, R1–R15): per-arm namespaces (R1), committed ID set (R2),
memory via a reviewed R7 OFF mode, ABBA on one build (R3, R4), B1 scope (R5), the tg1 dual-arm schedule (R6), fail-closed
transport (R7), the bundle comparator (R8), per-session reporting (R9), panel coverage (R10), the build DAG + one serving build
+ frozen worktree (R11), within-axis order balance + a power-logging watcher (R12), artifact pins (R13), vision by-eye review
(R14), the estimate (R15).

## 1. What this decides

Whether the entry ships MTP-ON again: its three C177 lines restored (`mtp_verify_scan: joint_v1`, `draft_kind: mtp`,
`draft_model: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter`). The run produces per-axis SIGNALS (§7); the
operator makes the call (C204). No automatic pass / fail.

**Attention flags** (to the operator with a recommendation; never an automatic veto): a quality axis or session with ON − OFF
point < −5 pp or an interval excluding 0 on the negative side; a subjective-panel preference for OFF with Holm p < .05; ON 256K
prefill peak > OFF + 2 GB, or ON > ≈ 48 GB; decode ratio ON / OFF < 1.3× on A1 or A7; pooled acceptance < 0.70 (context only:
M40 Math500 0.78 on TQ4 KV, M42 native16 0.78–0.82); a non-convergence kind or runaway-tax flag present in ON and absent in OFF.

## 2. Build, arms, provenance

- **One serving build for every axis** (R11): stack commit S = the bump that carries B1 (§8); its `src/mlx-vlm` (production
  `7207179b` + B1's logging only), `src/mlx-serve` `86921f02`, `main_models.yaml`. Waves 1 and 2 assert the same three
  pins (submodule SHAs + registry sha256) before every arm; driver code may differ between waves (recorded per arm).
- **Frozen worktree** (R11): every arm runs router AND driver from `$STACK_WORKDIR/worktrees/stack-p426` at S (submodules
  checked out, its own `.venv` via `uv sync`, `.env` copied); the main checkout is free for builds. Wave 2 moves the worktree to
  the commit carrying B2 / B4 / B6 only after asserting the serving pins are unchanged.
- **Arms.** OFF = `main_models.yaml` at S. ON = OFF with exactly the entry's three C177 lines uncommented (the C203 / B4 rule;
  until B4 lands, `registry_states.overlay_on` on fork `494aea2c` gives the same bytes — asserted equal). Written to
  `$STACK_WORKDIR/p426/registry-{on,off}.yaml`; both sha256 in every manifest; a unified diff of exactly those three lines asserted
  before each ON arm.
- **Fixed:** weights, tune (t0.5, medium), native16 KV, cap / preallocation 262,144, prefill step 512, budgets (`max_tokens`
  102,400, thinking 81,920), deployed params via `--sampling-profile deployed`.
- **Router per arm:** lean start, `MLX_VLM_CACHE_SESSION_MAX=1`, `APC_ENABLED` absent, no OWUI / docker, `MLX_SERVE_CONFIG=<arm
  registry>` exported to router AND driver, fresh start (`scripts/stack_stop.sh`, :8000 free, new ownership, M50 checks, PID
  and config hash re-verified at exit). Worker argv asserted exactly (R13): ON has `--model <entry hf_path> --draft-kind mtp
  --draft-model caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter --mtp-verify-scan joint_v1`, OFF has the same
  `--model` and none of the three. Before every arm the HF snapshot files of the target and (ON) the drafter are hashed against
  fork `dev/p369_phase2/pins.json` (the reviewed per-file pins for this entry); any mismatch refuses. First manifest's
  `runtime.draft_kind` and `registry.sha256` verified before item two.
- **Machine state:** quiet box (no pytest, no other GPU process), `pmset -g ac` 140 W / 28 V and battery > 20 % before every
  arm; ≥ 10 min idle between arms; `pmset -g log` checked against every arm window (P418): an on-battery interval marks that
  arm's speed signals invalid (quality stands, labelled).

## 3. Order balance (R12)

Speed is compared only within an axis, under AB / BA: every axis runs as two blocks, block 1 OFF → ON, block 2 ON → OFF,
each arm a fresh load, ≥ 10 min idle between all legs. Items split into the two blocks by a seeded shuffle (seed 426) committed
with the ID sets. Quality pairs per item across the two arms; for bench axes the two loads per arm are disjoint item halves (no
item is pooled across loads within an arm).

## 4. Axes and namespaces (R1, R2)

Every destination below must NOT exist before its leg (the runner refuses otherwise); smokes use the same names with `-smoke`.
Tune / tag labels: `p426-{off,on}-b{1,2}` (labels only; sampling comes from the deployed profile).

| Id | Axis | Run (from the frozen worktree) | Signals |
|---|---|---|---|
| A1 | Math500 100 (M40's ids) | `benchmark/run.py generate --models <entry> --benches math500 --limit math500=0 --ids math500=<block ids, inline> --sampling-profile deployed --tune p426-<arm>-b<k> --order roundrobin --seed 0 --seed-base 0 --samples 1`; timeout derived; ids from `benchmark/results/p426/ids.json` (B9) | `acc_strict@81920`, conv%, nonconv kinds; per-row decode tok/s, acceptance (`row.draft`); wall |
| A2 | cjudge 40 | same, `--benches cjudge` | generations for the panel; conv%; decode; acceptance |
| A3 | Vision gate 20 | `benchmark/vision_gate.py --model <entry> --out benchmark/results/<entry>/vision_gate.p426-<arm>-b<k>.jsonl --limit <block>` | self-pass /20 (lenient, labelled); blinded by-eye review (§6); turn-1 latency + decode |
| A4 | Reasoning depth 128K | `bench.run_reasoning --model <entry> --grid 128000 --samples 3 --chain-len 4 --sampling-profile deployed --out-tag p426-<arm>-b<k>` — each block runs all 3 draws (seeds 128000000–002), so each arm has 2 same-seed loads | strict draws, budget hits, same-seed agreement across loads; decode; acceptance |
| M1 | Memory at 256K | fork `dev/p369_phase2/qualify.py --entry <entry> --predictor {off,on}` (B7) — 260,096-token prompt, shipped settings, `mx.get_peak_memory` prefill spike, ABBA OFF / ON / ON / OFF | prefill / decode / retire peaks per leg, ON − OFF; prefill and decode tok/s, acceptance |

The router capacity ladder is dropped (R4: its `peak_mem_gb` is a worker-lifetime high-water and its probe overrides budgets);
row `peak_mem_gb` is reported only as "arm-lifetime high-water". Historical numbers (R7 MTP-ON 38.25 GB, M40, M42) are context
with a fingerprint-labelled delta (C199), never a pair.

## 5. A7 — opencode tg1 (the primary agentic benchmark; R6, R7, R9)

- Corpus: tg1 (`benchmark/m62/universe.json`, 43 items: 22 Python + 21 Go), probe `run_tg1_probe.py` (P311-lite), hermetic v2
  env, `--sampling-profile deployed`; probe-code sha, skill policy and config hash recorded; never pooled with M63 (identity
  changed, C173).
- **Schedule (one frozen P426 chain record):** pilot (5 seeded-random items, per arm, fresh loads; gate: zero transport errors,
  both arms engaged / not engaged as expected) → **s1** (seed 1001) block OFF → ON → **s2** (seed 2002, opposite item order) block
  ON → OFF → **reload** control per arm (the pilot's 5 Python items at seed 1001 on a fresh load). Every leg a fresh router load
  (k = 2 independent loaded instances per arm: s1 and s2), ≥ 10 min idle between legs. The chain record freezes the stack
  commit, serving pins, both registry shas, probe-code sha, pins.json sha, and refuses resume on any drift.
- **Fail closed (R7):** the first transport incident (HTTP / connection error, timeout, served-config drift) INVALIDATES that
  leg; no `abort_restart` / archive-and-rerun inside P426; a rerun is an operator decision, labelled. Retries 0.
- **Reporting (R9):** per session (s1, s2) separately: paired `acc_strict@budget` ON − OFF with its own two-stage cluster
  bootstrap interval and MDE, convergence, runaway tax (budget-hit / turn-cap / exec-timeout + per-session union), session
  wall; never pooled across sessions. Reload control: diagnostic only (agreement count). Pooled tax rates descriptive, no interval.
- Speed: per-request decode tok/s and acceptance from the B1 log line, attributed to items by session id + request window (B6).

## 6. Subjective quality (R10, R14)

The C161 / C166 two-judge, two-provider blind pairwise panel (B3 = P427), both orders, length-adjusted, judge model id / client
version / prompt sha per verdict, retries 0, over execution-PASSING paired outputs of every quality axis: A1 (both-correct
pairs), A2 (all 40), A4 (strict draws), A7 (both-pass items, per session). A3: the 20 descriptions judged blind against image +
caption by the panel judges that accept images (a single-provider result is labelled so), reported beside — never merged with —
the self-pass count. Panel results enter the signals sheet as they land; judging needs no GPU.

## 7. Signals sheet (the operator's view)

B6 generates `benchmark/results/p426/SIGNALS.md` from rows / manifests / logs (never hand-copied), regenerated after every leg,
only through the B8 gates: one row per axis (A7 per session): quality (ON, OFF, ON − OFF, paired two-stage cluster-bootstrap 95 %
interval, axis MDE; a WASH labelled per C172), subjective panel, memory (M1 per-phase peaks, Δ), speed (decode ON / OFF and the
paired ratio with interval; pooled and per-row acceptance; wall ratio; power-invalid legs excluded and listed), coverage (legs
done / pending / invalid), flags (§1). Holm across the quality axes. Descriptive; no composite.

## 8. Builds and DAG (R5, R8, R11)

Each test-first, own Cursor code review ≤ 3 rounds, suites in both repos where touched.

- **B1 (fork, production, log-only):** thread `draft_kind / draft_rounds / draft_n / draft_n_accepted` from `GenerationMetrics`
  through `_build_metrics_envelope` and every chat-completions `record_success` call site (non-streaming, streaming; plus
  `/v1/responses` and Anthropic messages if opencode reaches them — checked in the red tests) into the `Request completed` line;
  absent when no drafter ran. Red: end-to-end ON / OFF, streamed and non-streamed. No memory field (memory is M1's).
- **B7 (fork, dev):** `qualify.py --predictor off` for this entry (today forced `mtp_on`); the OFF leg serves the committed
  registry; same harness checks. Red: the flag is refused / ignored today.
- **B9 (stack, data):** `benchmark/results/p426/ids.json` — A1's 100 ids (= the `math500.m40on.jsonl` id set, asserted unique and
  equal), A2's 40, A3's 20, the block split (seed 426), sha256 recorded here at commit.
- **B5 (stack):** `bench_watch.py` follows `reasoning.<tag>.partial.jsonl` and vision files, and logs watts / volts / battery each
  tick with a sticky failure; tg1 legs keep the chain's 5-min watch plus the same power fields.
- **B8 (stack):** `compare_predictor` bundle mode: must-differ = exactly {`draft_kind`, `draft_model`, `mtp_verify_scan`} jointly,
  everything else must match (sampling, KV, code, box, budgets, item / sample sets, timeouts, M50, serving path).
- **B4 (fork + stack, C203):** the settings-level matcher in `registry_states`; the stack's overlay builder uses the same rule
  (a pinned table mirrored from `ENTRY_OFF`, cross-checked against the fork module in a test).
- **B2 (stack):** the P426 tg1 schedule (§5) in `benchmark/chains/c147` (`LEGS`, `schedules`, `ChainOps.ensure_overlay` via B4),
  single entry, the frozen chain record, `abort_restart` off; tests for AB / BA order, fresh roots per leg, drift refusal.
- **B6 (stack):** `bench/recert_signals.py` → `SIGNALS.md` (§7); B1 log parsing with exact reconciliation (every probe request
  has exactly one log record; missing / duplicate / transport / archived / drift → refuse).
- **B3 (stack, P427):** the panel (§6) — per-box judge config, family map for the Cursor label, the two-judge length-adjusted
  estimator.

**DAG:** (1) now, while R5 runs: write B1, B7, B9, B5, B8 code + red tests (no test runs during R5). (2) R5 ends → test window:
red / green, fork suites ×2 + 8 audits, stack suite; Cursor code reviews. (3) Fork commit → **fork push (operator approval)** →
stack submodule bump = S → stack suite. (4) Wave 1 (A1–A4, M1) on S from the frozen worktree. (5) During Wave 1: B4, B2, B6, B3
written; tests only in scheduled windows between axes, each followed by ≥ 10 min idle before the next leg. (6) Wave 2 (A7) on S's
serving pins + B2 / B4 / B6 driver code. Panel judging as outputs land.

## 9. Estimate (R15)

GPU (lower bounds from M40 / M42 / M63 / R7 walls; +30 % heavy-tail allowance in brackets):
Wave 1 — A1 3.4 h, A2 2.7, A3 0.3, A4 1.9 (two loads per arm), M1 1.0, extra loads 0.3, idle 19 × 10 min = 3.2 → 12.8 h [16.6].
Wave 2 — tg1 ON 3.1 h + OFF 7.0, pilots 0.6, reloads 0.6, idle 7 × 10 min = 1.2 → 12.5 h [16.3].
Total ≈ 25 h [33 h]. Not GPU: builds + reviews (B1 / B7 / B5 / B8 / B9 ≈ 1 day before Wave 1; B2 / B4 / B6 / B3 during it),
test windows (≈ 0.75 h each), panel judging (judge tokens). Recalibrated from each smoke before its full leg.

## 10. Restore

On the operator's ship-ON call: restore exactly the three C177 lines, `CERTIFIED P426 <date>` (or `PROVISIONAL`) in
`generation_defaults`, `benchmark/bench/tests/test_opencode_probe_seeding.py` (`per_query` → `joint_v1`, source "registry"),
README / campaign-results evidence rows, one commit; under C203 no fixture refresh. No client sampling change. Ship-OFF: signals
recorded, lines stay commented. Then the same plan per entry: `Qwen3.8-27B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
(after P405 R6, on their codec), `Ornith-1.0-35B-mlx-uniform-4bit`.

## 11. AGENTS.md amendment (operator)

C204 replaces "ship OFF if OFF wins beyond ±5pp on any axis". Proposed Registry-section wording: "Certify the predictor ON vs
OFF on every supporting axis plus memory and speed; ship it when it speeds up with no or negligible quality / memory downside —
the per-axis signals go to the operator for the call; −5 pp on an axis is a flag, not a veto."
