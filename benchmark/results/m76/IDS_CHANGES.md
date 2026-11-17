# m76/ids.json — changes

## 2026-11-16 — the A5 counter renders the served chat template (C355 (3), S25-P1; spec `docs/specs/m76-b8-kv-planned-kinds.md` v1.1 F3 + erratum v1.1a)

Reason: `m76_ids.offline_counter` rendered the chat template without the deployed template kwargs, while the server renders
every request with them (`to_template_kwargs`). Every stage-3a Wave 1 A5 row served `prompt_tokens` 130,776 against the frozen
129,130 (both arms, all 72 keys; ledger K8), so B8's budget guard kept A5 incomplete. The counter now passes the entry's deployed
kwargs (`params_for(entry, profile="deployed")`: `enable_thinking`, `reasoning_effort`, each only when set) to every
`apply_chat_template` call, calibration included, and records them as `counter.template_kwargs`.

Regenerated with its generator (`python -m bench.m76_ids`, from `benchmark/`; local HF cache, transformers 5.15.0).

| | old | new |
|---|---|---|
| ids.json sha256 | `6c9455a25fcb375fc7e50ec9878ff676c3c3d110e2630ca487fbcce9156af85f` | `57fce7c371ce46901cc1d22ff7b492c02db1dc36f9afca01a628129184fd6574` |
| chars per token (calibration) | 4.551045510455104 | 4.610591900311526 |
| counter.template_kwargs | (absent: none rendered) | `{"enable_thinking": true, "reasoning_effort": "medium"}` |
| chat_template_sha256 | `c73e681e…a6e4e` | unchanged |

Per cell (task × rung; n items; min / max over the cell's items):

| cell | n | prompt_tokens old | prompt_tokens new | resolved max_tokens old → new | resolved thinking budget old → new |
|---|---|---|---|---|---|
| reasoning-131072 | 20 | 129130 / 129130 | 130776 / 130776 | 102400 → 102400 | 81920 → 81920 |
| reasoning-159744 | 20 | 157344 / 157344 | 159360 / 159360 | 102400 → 102400 | 81920 → 81920 |
| reasoning-196608 | 20 | 193619 / 193619 | 196108 / 196108 | 68525 → 66036 | 54820 → 52828 |
| retrieval-131072 | 20 | 129131 / 129139 | 130776 / 130784 | 102400 → 102400 | 81920 → 81920 |
| retrieval-159744 | 20 | 157342 / 157352 | 159357 / 159367 | 102400 → 102400 | 81920 → 81920 |
| retrieval-196608 | 20 | 193619 / 193626 | 196108 / 196115 | 68518 / 68525 → 66029 / 66036 | 54814 / 54820 → 52823 / 52828 |
| smoke-reasoning-131072 | 1 | 129130 | 130776 | 102400 → 102400 | 81920 → 81920 |
| smoke-retrieval-131072 | 1 | 129137 | 130782 | 102400 → 102400 | 81920 → 81920 |

Per-item prompt_tokens deltas (new − old): 1,645 – 2,489. Every count stays inside the rung band (−3 % … 0 %).

Diff confinement (432 differing leaves): `axes.longctx.budget` 284, `axes.longctx.budget_inputs.prompt_tokens` 122,
`axes.longctx.budget_inputs.counter` 2 (`chars_per_token`, `template_kwargs`), `axes.longctx.prompt_deviation` 24 (derived from
`prompt_tokens`; erratum v1.1a); nothing else. A5 items, smoke items, blocks, tier list and sampler seeds, and the Math500 /
cjudge / vision / reasoning axes are equal to the old file. `m76_ids.load` accepts the new file.
