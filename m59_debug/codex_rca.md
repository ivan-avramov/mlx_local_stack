**P5 — Overall verdict: UNSUPPORTED.** These records do not establish that opencode 2.0.20 reduces model accuracy. They establish higher **median output tokens on commonly solved items**, without a consistent wall-time increase. My recommendation: correct the analysis defects below, then run a small prompt ablation before the full re-baseline.

**P6 — C-a: VERIFIED arithmetic; UNSUPPORTED “accuracy is not worse.”** Independently counted `acc_strict@budget`, all denominators 22:

| Model | Python: 1.18 → v2 s1/s2 | Go: 1.18 → v2 s1/s2 |
|---|---:|---:|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 22 → 21/20 | 22 → 20/20 |
| Qwen3.8-27B-mlx-uniform-4bit | 19 → 20/20 | 16 → 18/18 |

The descriptive totals are **79/88 versus 157/176**; substituting all successful stall reruns gives **171/176**. That substitution combines selected retries and different budgets; it is not a valid accuracy estimate at one budget.

Reported per-language delta intervals include zero: negative comparisons span approximately **[−23, 0] pp**, positive comparisons **[0, +14]**, **[0, +23]**, or **[−9, +27] pp**. They cannot establish ±5pp equivalence or capture baseline between-session variability with k=1. At n=22, the repository’s default power assumptions give approximately **27pp MDE**. [Rows/report]( $STACK_WORKDIR/m59/M59_REPORT.md)

**P7 — C-b: VERIFIED contamination; UNSUPPORTED exact historical prompt reconstruction.** The copied database contains the successful `.meta/example.go` fetch in `Qwen3.8-27B-mlx-uniform-4bit`’s `go/matrix` session, plus the cited personal-style output. That pass is contaminated; marking it unclean leaves **at most 15/22 uncontaminated Go successes**.

The September probe inherited its environment; `--pure` disabled plugins, not instruction discovery. However, the reconstruction copies **current** instructions/skills, discovers the real ancestor `~/AGENTS.md`, and adds literal task quotes absent from the probe source. Thus it demonstrates a leakage route, not September’s exact prompt bytes. [Capture script]($STACK_WORKDIR/m59_debug/capture/capture.py), [September probe]($STACK_WORKDIR/m59_debug/probe_878d720.py:237)

**P8 — C-c: VERIFIED token shift; UNSUPPORTED principal cause.** After recovering nine omitted baseline sessions, median paired output-token ratios on items solved in all three arms are:

- **Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed:** Python **1.30×**, Go **1.35×**.
- **Qwen3.8-27B-mlx-uniform-4bit:** Python **1.37×**, Go **1.71×**.

Ratios of summed tokens are smaller: respectively **1.13×/1.10×** and **1.05×/1.36×**. Visible-text totals rise **2.36–2.80×**, supporting a verbosity change, but not proving it causes the reasoning increase.

Mean whole-arm wall-time ratios, averaging v2 sessions, are respectively **0.99×/1.22×** and **0.89×/0.99×**. The 1.22× includes a 3600-second failure; machine conditions also differ.

The captured base prompts contain **8,529 versus 3,710 characters**, with strong brevity instructions removed. But v2 still explicitly requests concise communication. Prompt length alone establishes no causal effect; tools and serving changed simultaneously. [Prompts/captures]($STACK_WORKDIR/m59_debug/capture/out)

**P9 — C-d: VERIFIED history-growth observation; UNSUPPORTED categorical exclusion.** For `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, September `python/paasio` has **9,228 output tokens → 9,246 additional next-prompt tokens**; v2 s1 `python/pov` has **11,377 → 11,399**. Both turns contain substantial reasoning and tiny write-tool responses.

This strongly supports reasoning-sized history retention in both versions. It does not prove identical wire serialization or server cache handling; the supplied mock responses contain no reasoning with which to test that distinction.

**P10 — C-e: VERIFIED gate sensitivity; REFUTED claimed attribution of ten conversions.** All **18 v2 stalls** were retried; **14 passed**, four remained stalled. However, the report classifies “allowance” using **completion time**, not first-write/progress time. Three supposedly allowance-dependent successes wrote their solution before the original deadline:

- **Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed**, s2 `python/paasio`: **635s < 662s**.
- **Qwen3.8-27B-mlx-uniform-4bit**, s1 `go/bowling`: **582s < 630s**; `go/ledger`: **564s**, revised at **612s < 630s**.

Only seven conversions even satisfy the claimed first-write timing criterion. Their causality remains unproven without matching pre-cut trajectories. Also, **all nine baseline failures were stalls**: gate sensitivity predates v2. [Classification bug]($STACK_WORKDIR/m59/m59_report.py:126)

**P11 — Additional VERIFIED analysis defects.** [pair.py]($STACK_WORKDIR/m59_debug/pair.py) excludes nine sessions preceding its manifest-minus-ten-minute cutoff. Ten s2 transcript paths resolve to reruns, not their row’s session ID. [firstwrite.py]($STACK_WORKDIR/m59_debug/firstwrite.py) treats never-written, interrupted sessions as completed first-write observations. Restricting to identity-matched, successful write events gives first-write ratios **0.99×/1.24×** and **1.86×/1.51×**, respectively; these exclude censored cases. The report also incorrectly labels all baseline rows converged because it ignores legacy `stop_reason`.

**P12 — Ranked mechanisms and cheapest tests.**

1. **Gate/censoring:** strongest explanation for observed misses; not evidence of diminished coding capability.
2. **Prompt/tool changes:** strongest scaffold hypothesis for token growth; brevity removal, different schemas, and reference access are confounded.
3. **Serving changes:** material alternative—both serving hashes changed; `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` additionally changed KV4→native16, attention, and embedding settings.
4. **Seeds/cache-path variation:** baseline unseeded k=1 and demonstrated cache-path numerical divergence prevent causal attribution.

First fix joins/accounting: **zero box-hours**. Then prompt-only A/B on five preregistered items, both models, two independent sessions: **40 episodes**, approximately **2–4.5 box-hours**, reserve **6–8** for tails. Hold tools, serving, seeds, dates and generous gates fixed. A repeatable reduction removing most token excess without lost solves supports prompt causality; a null result shifts priority to tool-only A/B. Identical-request old/new-serving replay can isolate serving sensitivity in approximately **2–4 additional hours**. These are mechanism screens, not ±5pp accuracy certification.

