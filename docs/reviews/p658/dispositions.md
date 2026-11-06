# P658 (a) — four-eyes light: dispositions (designer)

Spec: `docs/specs/p658-qualify-engagement-only.md` v1. Go C299, Accept C300 (2026-11-06). Fork commits `a1e23203` (frozen tests, red)
and `e3e38397` (implementation, green) on `d94e38a9`.

```
[four-eyes 0.7.0] outcome: completed; mode: light (dev/ harness, no security / architecture area)
designer, implementer, fixes: claude-code: Claude Opus 5.5 (this session); claude -p: Claude Opus 5.5, session eea10b11; fixes: none
test-writer: claude -p: Claude Sonnet 5.5, session 23081782; continued; tests frozen 2026-11-06T07:46:03Z, candidate revealed 2026-11-06T08:14:33Z
panel: cold on candidate (checkout, read-only; user instructions unconfirmed): cursor-agent: gpt-5.6-sol-high, no session id, returned; cursor-agent: glm-5.2-high, no session id, returned; verify: none
shared: implementer and test-writer share a vendor (Anthropic), and the designer shares the implementer's model; not covered: errors Anthropic models make consistently, covered only by the panel (OpenAI, Zhipu)
go: 2026-11-05, "go"; accept: 2026-11-06, "accepted: keep up the great work!"; commit: fork a1e23203 + e3e38397; push: none
```

## Tests

- Frozen (test-writer, 112): baseline 79 fail / 33 pass; candidate 112 pass. The final, black-formatted candidate passes 1,404 tests
  (1 skipped) across the frozen tests and the qualify / orchestrate / worker / kvmanifest / P415 / P426 / P452 / P475a / P542 regression
  set.
- Implementer (44, `test_p658_impl_engagement.py`): baseline 34 fail / 10 pass / 1 skip; candidate 44 pass.
- Full serial suite in a worktree: 10,004 passed, 1 failed. The failure is `test_check_sources_refuses_a_module_outside_the_reviewed_tree`,
  a worktree artifact: the shared venv's editable install resolves `mlx_vlm` to the main checkout. It fails the same way on a pristine
  `d94e38a9` worktree and passes in the main checkout (designer-checked). The fork gate runs on the real checkout.
- Formatting: the implementer could not run the hooks; the designer ran `pre-commit` (black reformatted three files). The ASTs are
  identical except two docstrings' closing-quote whitespace.

## Findings

| Finding | Raised by | Kind | Disposition |
|---|---|---|---|
| F1: the K3 drafter check is tested only against fake drafters, never the real `qwen3_5_mtp` drafter; a future batched path would fail every arm while the suite stays green | GLM 5.2 (major, as a test gap) | original | **Declined (residual), shown to the operator as a declined major.** GLM's own trace: no false PASS and no false refusal under the supported conditions (the cached-session B==1 path, `_mtp_rounds`, `reset(model)` without `left_padding` → unbatched `KVCache`). The scenario needs a future code change, and its failure is a loud refusal, never a false PASS. The first live engagement runs check the real drafter. Counterpoint: a CPU test with a tiny real drafter would pin it in the suite. |
| P1: a failed engagement entry omits `reference: None` (the spec says each entry's is `None`) | Sol (minor) | original | Declined: no consumer reads `reference` on a failed entry; failure is carried by `status`. |
| F2 / R4: `"no drafter cache manifest (malformed leaf record)"` beyond the spec; a duplicate `served_on` guard in `entry_problems` | GLM 5.2 (minor), test-writer | original | Kept: both are defensive; the first turns a `KeyError` into a refusal. |
| R1: is the real drafter's `_cache` populated when read? | test-writer (medium, unproven) | original | Resolved by trace: `mtp_base` sets `_cache` only in `__init__` (`[]`) and `reset()` (`make_cache()`); nothing clears it at request end. |
| R2: a missing `rg.draft_model` raises only after the full request | test-writer (minor) | original | Declined: `check_loaded_drafter` guards the MTP case before the request; it would only save wall time. |
| R3: under the flag an entry reports `COMPLETED`; only the top level says `certifies: false` | test-writer (minor, design) | scope | Adapted to the stack: the `p475_kv` ON-arm wiring (handoff step 2) requires `engagement_only: true` and `certifies: false`. |
| R5: formatters never ran | test-writer, implementer | process | Done by the designer (above). |
| `test_speculative.py::test_qwen3_5_ragged_decode_attention_matches_two_pass_singleton` fails intermittently under `-n 4` only | implementer | outside the change | Recorded as S18-P8 (the fork gate runs serially). |
