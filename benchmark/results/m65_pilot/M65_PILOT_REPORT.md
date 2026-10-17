# M65 step 1 — headroom pilot (Python + Go items outside tg1), k = 1, predictor OFF

Chain `$STACK_WORKDIR/m65-pilot` (2026-10-16 23:46Z → 2026-10-17 05:48Z, rc 0), `run_tg1_chain.py chain s1 --universe
benchmark/m65/pilot_universe.json --policy-sha 028e0345… --probe-code-sha ebcfe6fb…` (P351 runner; pre-G1 guard).
Universe: 29 items = 12 Python + 17 Go (every polyglot Python/Go item outside the tg1 universe; `go/counter` invalid,
C145), sha256 `5cdc9900…`; every reference passes. Deployed sampling, thinking ON (tg1 budget), seed base 1001. Smoke
`m65-pilot-smoke` rc 0 (rehearsal rows only). Descriptive: k = 1, no session replication (C168 screen semantics).

| Model | Python strict | Go strict | conv | budget hits | out tok p50 / p90 / max (Py; Go) | leg wall (Py; Go) |
|---|---:|---:|---:|---:|---|---|
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` | 12/12 | 17/17 | 100 % | 0 | 3,170 / 12,436 / 12,436; 4,478 / 15,117 / 32,852 | 1.01 h; 1.73 h |
| `Qwen3.8-27B-mlx-uniform-4bit` | 12/12 | 17/17 | 100 % | 0 | 5,319 / 12,295 / 15,246; 8,122 / 18,578 / 35,194 | 0.92 h; 2.14 h |

Token quantiles are the runner's last WATCH tick per leg (one item per leg finished after it). Mean wall per item:
Python 304 s / 276 s, Go 366 s / 453 s; max 1,710 s. No nonconvergence of any kind; 0 transport failures; 0 restarts.

Web: one row with fetches (`Qwen3.8-27B-mlx-uniform-4bit` `go/robot-simulator`: a go.dev blog page and one search
query); P201 Cursor `gpt-5.6-sol-high` audit labels both `generic` (no solution content); `answer_key_contact` false →
the row stands.

**Reading.** Both picks solve every Python and Go item outside tg1 as well (58/58 strict; tg1 83–86/86): Python/Go
polyglot is saturated for these models on this harness, not just the 43 tg1 items. Accuracy headroom for separating the
picks (or scaffolds) is not available in Python/Go; it must come from tg2 (Rust / Java / JavaScript / C++; M55 61–86 %).
The second pick runs ≈ 1.3–1.8× more output tokens per item at the median (Go 8.1K vs 4.5K) — the only separating signal
here (descriptive, k = 1). Sizing input for tg2: current-harness mean ≈ 5–7 min per item, tail ≈ 28 min.
