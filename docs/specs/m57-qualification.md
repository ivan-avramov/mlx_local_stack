# M57 qualification — frozen design (2026-10-05; needs operator sign-off before the first arm)

Model `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, shipped state (native16 KV, MTP ON, deployed sampling, thinking ON),
MLX 0.32.2, single box. Code under test: fork `m57-attention-policy`, router `m57-attention-policy`, stack provenance branch.
Phase 2 serving optimization; no B/C ladder implication. Nothing here changes `main_models.yaml`.

## Arms (overlays in `$STACK_WORKDIR/m57/overlays/`; every arm runs the SAME branch code)

| arm | registry delta vs the first pick's entry | role |
|---|---|---|
| A | none (`auto`, step 512) | baseline, full |
| B | `attention_policy: fused_v1` | candidate, full |
| S | none, SHIPPED submodule code (no branches) | control: branch `auto` ≡ shipped, latency only |
| C | B + `cache_limit_gb: 3` | screen: smaller pool, latency / peak only |
| D | B + `prefill_step_size: 1024` | screen, latency / peak only |
| E | B + `lazy_prompt_embeddings: true` | screen, latency / peak only |

## Machine-state protocol (AGENTS.md warm-state rule)

- Stack stopped, :8000 free, no stray bench / worker processes, 140 W / 28 V, battery > 20 %, swap noted.
- 10 minutes idle before EVERY arm-session; start state and wall-clock recorded in the run log.
- One fresh lean router per arm-session (`MLX_VLM_CACHE_SESSION_MAX=1`, `APC_ENABLED` absent, verified on router and worker
  pids; worker command line and resolved serving controls logged). Rungs run in the same ascending order in every arm, so arms
  are matched rung by rung.
- Full arms A and B: k=2 sessions, order A→B then B→A. Screens and the control: one session each, interleaved after the full
  arms; each is compared with the A / B session that started from the same state.
- Daemon monitor per run; transport failures abort; `sdpa_forced` / `sdpa_auto` logged per request (B, C, D, E must show forced
  calls on every cold rung ≥ 8K; A and S must show none).

## Measurements

1. **Latency / capacity ladder** (`bench.run_capacity`, fresh `--out-tag` per arm-session, `--sampling-profile deployed`):
   cold rungs 8192, 32768, 65536, 131072, 262144. Per rung: prefill s, decode tok/s, `mx.get_peak_memory`, retrieval check,
   MTP counters. The 262144 rung is capacity + retrieval only (≤ 556 thinking tokens of headroom).
2. **Cached continuations** (workdir script, pinned chat id): at 65536 and 131072 tokens of context, three follow-up turns
   adding ≈ 100, 600 and 5000 new tokens. Per turn: wall, cached tokens, prefilled tokens, counters.
3. **Short-context quality**, arms A and B, both sessions: humanevalplus + mbppplus, n=100 seeded sample (50 + 50), paired
   `acc_strict@81920`, cluster bootstrap; convergence vector reported.
4. **Long-context quality**, arms A and B, both sessions: `bench.run_retrieval` and `bench.run_reasoning --chain-len 4` on grid
   65536, 98304, 131072 with 4 samples per rung (12 + 12 items per arm-session), seeded and paired across arms.
5. **AgentBench OS 5-item smoke**, arms A and B, one session each (multi-turn tool continuation; not a quality axis).

## Pilots before any arm

- Seeded 5-item pilot of measurement 3, run TWICE on one loaded instance per arm (byte-identical outputs required).
- One 65536-token retrieval item and one chain item per arm to size measurement 4 from their mean and max (lower bound).
- Estimated cost before pilots (lower bound): ladders ≈ 4.7 h, short-context quality ≈ 2–3 h, long-context quality ≈ 6 h,
  smokes and pilots ≈ 1 h → ≈ 14 box-hours plus cooldowns.

## Predictions on record

128K TTFT −16 % (warm) to −22 % (cool); 256K ≈ −30 %; 8K and 32K within ±3 %; peak −3.9 GB at 128K and −7.9 GB at 256K under B,
a further ≈ 1.3 / 2.7 GB under E; decode unchanged; S ≡ A within noise.

## Decision rule (pre-registered; the operator approves any registry change; adoption is PROVISIONAL)

Adopt `fused_v1` iff ALL of:

- Q1 short-context quality: paired strict delta (B − A) ≥ −5 pp in each session; convergence no worse by more than 5 pp;
  intervals and the axis MDE reported; a result inside tolerance without a passed TOST is labelled "within tolerance, not proven
  equivalent".
- Q2 long-context quality: per axis (retrieval, chain reasoning), paired losses minus paired wins ≤ 1 in each session and ≤ 2
  pooled over both sessions (24 pairs per axis).
- Q3 no rung slower: B's TTFT not more than 3 % above A's at any cold rung or continuation turn, in both sessions.
- Q4 no raise, no 500, counters consistent with the policy on every request.
- Q5 at least one benefit in both sessions: 262144-rung peak lower by ≥ 5 GB, OR 131072-rung TTFT lower by ≥ 8 %.

Red flags that stop adoption pending investigation: decode tok/s differing by more than 5 % between A and B at any rung; S
differing from A by more than 5 % at any rung; MTP acceptance moving by more than 0.03.

Screens C, D, E inform follow-up recipes only; none is adopted by this qualification. Results go to
`docs/campaign-results.md`; README evidence tables are updated; no ladder movement is expected or proposed.
