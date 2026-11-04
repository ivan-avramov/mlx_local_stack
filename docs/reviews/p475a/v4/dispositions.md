# P475a v4 (fork `qualify --kv-arm`) — findings and dispositions (designer), 2026-11-04

Sources: panel opinion (GPT-5.6 Sol High P1–P2; GLM 5.2 F1–F3), implementer notes 1–5, test-writer delivery 2 (pending at first write).

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| Sol P1 `sdpa_forced` missing / None / negative / NaN read as 0 | major | adopted (fix 1) | when the expected manifest is available the counter must be a present finite integer ≥ 0; `> 0` required iff fused with a native leaf, exactly 0 otherwise; else a problem |
| Sol P2 missing manifest + `auto` + forced > 0 gives a spurious attention problem | minor | adopted (fix 2) | no attention verdict whenever the expected manifest is unknown, under any policy |
| GLM F1 / impl note 3 `--kv-arm --predictor on` cannot pass P542's certified-argv binding for a non-empty KV delta | major | adapted (fix 3) + spec v4.1 | an MTP-ON KV arm is uncertified: `--kv-arm --predictor on` with a non-empty delta refuses with that reason (preflight such arms with `--predictor off`; P475 proves the ON state per leg from drafter counters); an empty delta behaves as `--predictor on` today; the C199 binding is never waived |
| GLM F2 `expected_manifest` computed twice | minor | declined | pure function; negligible cost |
| GLM F3 untested: `--kv-arm` without `--predictor`; `--predictor on` without a summary | test gap | to the test-writer | |
| impl notes 1, 2, 4, 5 (no 16-state gate for `off` at `fd67082a`; the `classify` closure; the attention rule and exact widths also without the flag) | — | accepted | consistent with v4 and P542 |
