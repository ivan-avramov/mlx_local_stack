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
| TW d2 the 7 third-entry / unknown-entry driver tests fail in their own `control()` helper (TQ4 registry, AF8 manifest) | test defect | to the test-writer (d3) | candidate verified by the test-writer's scratch probe |
| TW frozen AST test "no `quantized_kv_start` literal in `classify_kv_arm`" | test defect (source structure) | to the test-writer (d3): replace with behaviour | four-eyes: tests constrain behaviour, not source; the behaviour (non-zero start refuses) is already tested |
| TW d2 black / isort not run (not installed in the fork venv) | — | designer at Accept | the fork's pinned formatters via `dev/ci.py` / pre-commit |

## After fix round 1 (test-writer delivery 4: 476 / 476 + 698 neighbours pass; verdict fix then merge)

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| TW d4 P1 fix 1 makes every `auto`-attention entry fail on a real worker (introduced by the repair) | major (verified: `mlx_vlm/server/schemas.py` omits `sdpa_forced` when unset under `auto`; `worker.py:1587` records the absent key as `None`) | proposed fix round 2 (operator) | the strict counter check is right only under `fused_v1`, where the server always emits the counter; under other policies an absent / None counter means no forced calls (0); a present value must still be an int ≥ 0 and must be 0 |
| TW d4 P2 `640.0` rejected | minor | declined | JSON counters are integers |
