# M76 B3 + B5 — P426 lever `kv`, build label `s3`, Math500 300, A5 `longctx` — four-eyes light — ledger

Spec `docs/specs/m76-b3-b5-p426-kv-lever.md` v1 → v1.5a (v1.1 B7 v1.1 / C331; v1.2 change-review dispositions; v1.3 verify
dispositions; v1.4 C339 A5 two looks; v1.5 / v1.5a the token-counter defect and the prompt-size band, S23-P82). Baseline stack
`ce77b5b2`. Copies `$STACK_WORKDIR/fe-m76b3/{impl,tw}`; integration clone `fe-m76b3/integ` (`main` with B7 + B7.1 + the candidate).

## Cast

- Designer: Claude Opus 5.5 (this session).
- Implementer: Claude Opus via `claude -p` — candidate `f18a2c98`; fix rounds `a75191c1`, `4aae1a9c`, `8f7297c7`, `69581800`,
  `8b09108d`, `aa93fec4` (fresh each; round 1's report recovered by a read-only resume of its own session after a late background
  notification overwrote its final message).
- Test-writer: Claude Sonnet via `claude -p`, one session continued (`ecc546e6`): delivery 1 frozen 2026-11-14T03:34:32Z before the
  candidate was revealed 04:47:37Z; deliveries 2–6 (verdicts: d2 fix then merge; d3–d5 merge; d6 amendments).
- Panel: GPT-5.6 Sol High and GLM 5.2 High, `cursor-agent --mode ask`, read-only snapshot, user instructions unconfirmed; opinion on
  candidate 1; verify (fresh sessions, briefed with the opinion) on fix round 1.
- Shared: implementer, test-writer and designer are Anthropic; the panel is two other vendors.

## Findings

| # | raised by | finding | disposition |
|---|---|---|---|
| 1 | Sol P1 | A4 and A5 share a tune; A5's glob matches A4 outputs | adopted (fix 1): axis-specific A5 tune; populated-directory test |
| 2 | Sol P2, test-writer | `ids.json` not generated | designer step: generated with the final code (S23-P85); in the candidate |
| 3 | Sol P3 | signals bypass B7's `axis_verdict`; size warnings not blocking | adopted (fix 1) |
| 4 | Sol P4, implementer | A7 has no s3 | adopted (fix 1; scope correction: `schedules.py`, `chain_core.py`) |
| 5 | Sol P5 | `kv` panel lacks export / freeze / judge / seal, two-family enforcement | adopted (fix 1) |
| 6 | Sol P6 | seed-mismatched keys leave the pair accepted | adopted (fix 1) |
| 7 | Sol P7, GLM F4, test-writer | A5 budget: invented overhead; no frozen per-item counts / equality | adopted (fix 1) |
| 8 | Sol P8 | B8 compares only sampling + some KV fields | adopted (fix 1): full provenance, whitelist |
| 9 | Sol P9 | stage-4 V-only / X-reuse / sentinel workflow | deferred: outside B3's spec; a stage-4 item (S23-P49) |
| 10 | Sol P10 | V M1 fails late | adapted (fix 1): V refuses at preflight |
| 11 | Sol P11, test-writer | decode not P426's T2 | adopted (fix 1) |
| 12 | GLM F1 / F2 | `lever=` surface / `--lever` placement as specified | adopted (fix 1) |
| 13 | GLM F3 | golden over-captures `EXPECTED_BUILDS` | test-side: amended by the test-writer (d3) |
| 14 | GLM F5 | A5 panel reuses the math500 rubric | adapted (fix 1): chain-4 both-correct under the reasoning rubric; retrieval excluded |
| 15 | Sol verify P8 | A7 session pairs do not compare provenance | adopted (fix 2) |
| 16 | Sol verify P16 | panel inputs caller-supplied, not bound to B8's items | adopted (fix 2): derived from the benchmark inputs, per-item shas frozen |
| 17 | Sol verify P17 | an incomplete panel does not block | adopted (fix 2): `panel_incomplete` blocking; `--partial` labelled |
| 18 | Sol verify P18 | exclusion accounting drops rejected keys | adopted (fix 2) |
| 19 | operator C339 | A5 two looks (72 → 120) | v1.4 (fix 3): 48 nested tier-2 items; two-look signals from `axis_plan("A5")` |
| 20 | designer (running the generator) | the offline counter counted a `BatchEncoding`'s keys: every count 2, prompts ≈ 1,600× too long, the generator never finished | v1.5 (fix 4): count `input_ids`, refuse bad counts / calibrations, real-tokenizer tests |
| 21 | implementer (fix 4) | real prompts land ≈ −1.5 % from the rung (1 % tolerance) | designer lead call S23-P82: band [−3 %, 0 %], never above; deviation recorded (fix 5) |
| 22 | integration run (designer) | 6 tests assumed pre-v1.4 layouts / single-look A5 / M1 without `--certified-by` | test-side: the test-writer amended its 5 (d6), the implementer fixed its 1 and added a real two-look test (fix 6) |
| 23 | test-writer d5 F1 | `load()` does not re-check the prompt band | residual → light-path follow-up (S23-P88; fail-closed) |
| 24 | test-writer d5 F2 | the worker venv's transformers version is recorded, not enforced | residual: B8's per-row count equality is the guard (S23-P88) |
| 25 | test-writer d5 F3 | plan vs `ids.json` disagreement is a blocking flag, not a refusal | kept: the existing size-warning → operator path |
| 26 | test-writer d4 F1 | panel inputs not re-derived at read time | residual (needs write access to the frozen panel directory; the export derives every input) |
| 27 | implementer | judgement calls: s3 shaped as s1; `kv_quant_scheme` whitelisted (derived from `kv_bits`); A1's deciding look rule; A7 manifest normalisation keys | accepted by the designer |

## Accept

Operator Accept 2026-11-14 ("accepted: awesome work so far!", S23-P90; C341). Applied to `main`: the final candidate (29 files incl.
`benchmark/results/m76/ids.json` sha `6c9455a2…`), the test-writer's tests (`test_m76_b3_fe_*.py`, `fixtures/m76_b3_fe/`). Verified on
`main` + B7 + B7.1 + the candidate (the operator's tree is byte-identical to that clone): 1,186 passed, 2 skipped.

```
[four-eyes 0.7.0] outcome: completed; mode: light
designer, implementer, fixes: Claude Code: Claude Opus 5.5 (designer); claude -p: Claude Opus, candidate f18a2c98, fixes a75191c1, 4aae1a9c, 8f7297c7, 69581800, 8b09108d, aa93fec4
test-writer: claude -p: Claude Sonnet, ecc546e6; continued; tests frozen 2026-11-14T03:34:32Z, candidate revealed 2026-11-14T04:47:37Z
panel: cold on candidate 1: cursor-agent gpt-5.6-sol-high, read-only snapshot, user instructions unconfirmed, returned; cursor-agent glm-5.2-high, same, returned; verify (fix 1, fresh sessions, briefed with the opinion): sol returned, glm returned
shared: implementer, test-writer and designer are Anthropic; not covered by them: errors Claude models make consistently (the panel is two other vendors)
go: C325 (2026-11-11, "go"); accept: C341 (2026-11-14, "accepted"); commit: see git log; push: none
```
