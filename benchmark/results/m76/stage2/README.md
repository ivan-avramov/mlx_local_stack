# M76 stage 2 — `m72_exact` exactness at scale (P369 phase 2 E1c + E2, tuple `m76-x`) — PASS

`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, arm X (TQ4 KV `kv_bits: 4` + `tq4_attention: m72_exact`, MTP ON; stack arm
`ec114753`, fork `34a21208` = `--reviewed-head`, production ref `f9bf743f`), cross-load OFF = arm XO (`b9e6b91e`). Spec
`docs/specs/m76-tq4-certification.md` §7 stage 2. Box m5max-128, 140 W / 28 V throughout, no errors.

| run | dir | status | wall |
|---|---|---|---|
| smoke (binding; `--reviewed-head`) | `m76-x-smoke-rh/` | SMOKE_PASS; projected full 4.1 h (6.1 h with tail) < 8 h | 17.6 min |
| full | `m76-x-full/` | **PASS** (exit 0) | 4.41 h (2026-11-13 17:25 → 21:50 PST) |

Full run, per E1c cell (same-instance ON vs OFF1, 160 tokens, deployed sampling, fixed seeds; C1 control OFF1 vs OFF2):

| cell | compared positions | mismatches | max TV | C1 | verify route (expected) | d2_verify / per_query:short | fallbacks |
|---|---|---|---|---|---|---|---|
| short | 160 | 0 | 0.0 | identical | per_query:short | 0 / 990 | 0 |
| T1024 | 158 | 0 | 0.0 | identical | per_query:short | 0 / 1005 | 0 |
| T2048 (straddle) | 158 | 0 | 0.0 | identical | d2_verify + per_query:short | 585 / 420 | 0 |
| T8192 | 158 | 0 | 0.0 | identical | d2_verify | 1110 / 0 | 0 |
| T32768 | 158 | 0 | 0.0 | identical | d2_verify | 990 / 0 | 0 |
| T65536 | 158 | 0 | 0.0 | identical | d2_verify | 1080 / 0 | 0 |
| S131072 | 158 | 0 | 0.0 | identical | d2_verify | 1050 / 0 | 0 |
| S260096 | 158 | 0 | 0.0 | identical | d2_verify | 1065 / 0 | 0 |

- T2048 and T8192 took a second attempt: the first was invalid for straddle coverage only ("no observed straddle at the TQ4
  threshold" / "no straddle counter"), neutral, C1 identical, no mismatch; the harness re-drew the offset.
- E2 (greedy, 27 requests: the 20 C84 items at 512 tokens + straddle / scale prompts at 160): all identical ON vs OFF1, C1 identical,
  cross-load (XO) identical — PASS. E7b continuity OBSERVED.
- Claim (spec wording): MTP ON equals plain decoding on the same loaded instance at the tested cells — transformed target
  distributions (E1c, 160 tokens) and greedy tokens (E2, 512 / 160 tokens); nothing beyond the tested positions. This is the C258
  basis for running X's stage-3 quality legs MTP ON only.

Files: `verdict.json` (generated from the two runs' `summary.json`: status, bindings, per-cell evidence, E2, and the sha256 of each run's `summary.json` / `manifest.json` / `monitor.log`); the full files (paths
scrubbed to `$STACK_WORKDIR` / `$HOME`) are staged for the `evidence` branch in `$STACK_WORKDIR/m76/stage2-evidence-stage/`. Raw arrays (`*.npz`, 2.3 GB) and worker logs stay in `$STACK_WORKDIR/p369/phase2/m76-x-full/`
for the evidence / dataset backfill (C212 / C260). Not cited: the first smoke `m76-x-smoke` (SMOKE_PASS but without
`--reviewed-head`, so it could not bind; S23-P4 / C333) and the refused full `m76-x-full.refused-unbound-smoke/`.
