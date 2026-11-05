# P475 stage 1 build — findings and dispositions (designer), round 1 of 3, 2026-11-05

Cast: implementer Claude Opus 5.5 (`claude -p`, session `0ce355dd…`); test-writer Claude Sonnet 5.5 (`claude -p`, session `51237d4c…`,
continued d1 → d2); panel GPT-5.6 Sol High + GLM 5.2 (`cursor-agent 2026.10.22 --mode ask`, fresh, `checkout` with the candidate
applied; user instructions unconfirmed). Tests frozen d1 2026-11-05T07:42:28Z, candidate revealed 07:43:19Z, d2 refrozen 08:03:43Z.
Candidate on the d2 tests: 433 / 434 frozen, 161 / 161 implementer, 557 touched-suite tests pass.

| Finding | By | Disposition | Why / change (contract v1.2) |
|---|---|---|---|
| Arm worktrees cut from a base without the candidate's instrument | Sol P1 (blocker), TW F4 | adopted | base = the main commit carrying the accepted code; pre-check: the arm's instrument files byte-identical to the orchestrator's |
| N16 removes `kv_quant_scheme`; the fork's `--kv-arm` gate keeps it | Sol P2 (blocker) | adopted — designer error (contract v1.1 deviated from spec v4) | N16 = `kv_bits: 0` only; the TW test "N16 keeping the turboquant line refuses" is amended |
| Dossiers not bound to model / base / arm commit / gitlinks; duplicates overwrite | Sol P3 (major) | adopted | validate each receipt against the run; a second usable dossier per slot refuses |
| A rung valid with missing peak memory / decode rate | Sol P4 (major) | adopted | both finite and > 0 in `rung_problems` |
| Driver / router process groups not verified empty | Sol P5 (major), TW F3 | adopted | `Ops.group_alive(pgid)`; signal while any member lives; verify both groups empty |
| Harvest misses e-mail addresses | Sol P6 (major) | adopted | `p426_harvest.Gate.check(..., dest="main")` on every dossier file |
| `--blocks` vs the deciding block on resume | Sol P7 (major), GLM F5 (minor) | adopted | persist block count + deciding identity / completion; refuse a changed `--blocks` |
| A stale canonical matrix survives a partial regeneration | Sol P8 (major) | adopted | exactly one of canonical / PARTIAL after any regeneration |
| INVALID smoke leg not terminal on resume | TW F1 (must fix) | adopted | INVALID smoke stops the run, also on resume |
| `evidence-stage/<leg>` not a destination; overwritten | TW F2 | adopted | absent at pre-check, never overwritten |
| Unresolved instability exits 0 | TW F6 | adopted | nonzero + labelled |
| The worker-env check's macOS assumption (D1) is untestable by fakes; an N16 smoke cannot refute it | GLM F1 (major) | adapted (contract, no code) | the smoke covers N16 and TQ4 and records the worker environment |
| Telemetry identities (`prompt_n == prompt_tokens`, 2 % prefill) unverified live | GLM F3 (major) | declined (code) | R21 as pre-registered; fails closed; the two smoke legs record them before the full run — a mismatch returns to the operator as a contract change |
| Frozen-test call shapes differ from the candidate | GLM F2 (major) | resolved | the test-writer adapted `helpers.py` / `fakes.py` in d2 (433 / 434 pass) |
| NOT_STARTED cap run-wide, not per leg | TW F5 | declined | fail-safe; a resume continues |
| `busy()` may count a zombie / unrelated process as a survivor | GLM F4 (minor) | declined | fail-safe on a benchmark box (an unrelated busy process is itself a refusal reason) |
| Worker log read in full twice per leg | GLM F6 (minor) | declined | performance only; the fallback is correct |
| Record the watcher's `--capacity-rows` path in the receipt and assert it | GLM F7 | scope request → operator | |

Adopted findings go once to a fresh implementer session (the fix round); the test-writer's d3 adds a failing-case test per adopted
defect; then the panel's verify (round 2 of 3).

## Verify — round 2 of 3 (2026-11-05)

Fix implementer: Claude Opus 5.5 (`claude -p`, fresh session `b463ca94…`; P651 added in the same session by C293). Test-writer d3 (same
session `51237d4c…`): fixture amended to the v1.2 facts, four v1.1-only tests amended, 60 + 18 failing-case tests (red on the round-1
candidate) — frozen `512 passed` (+1), implementer `242 passed`, touched `557 passed`; verdict merge. Panel verify (fresh sessions,
checkout with the fixed candidate): GLM 5.2 — every adopted row resolved, H1 / H2 operational notes; GPT-5.6 Sol High — 9 resolved, 4
new findings:

| Finding | By | Disposition |
|---|---|---|
| vP1 a VALID dossier can lack `watch.jsonl` / the capacity manifest (harvest skips missing sources) | Sol, major, confirmed | → operator (second fix round recommended) |
| vP2 `RealOps.spawn` leaks a started driver if create-time capture raises; a failed router start loses group ownership | Sol, major, confirmed | spawn half → operator (second round); router half declined (inside `chain_ops`, a non-goal) |
| vP3 matrix accepts off-plan block dossiers (a stale `b4`) | Sol, major, confirmed | → operator (second round; cheap) — receipts are already bound to base / arm commits, so only a same-run stale dossier triggers it |
| vP4 standalone `matrix` exits 0 on an unresolved flag | Sol, minor, confirmed | → operator (second round; one line) |
| H1 operator e-mail falls back to `git config user.email` | GLM, minor | residual: the live run passes `--operator-email` or relies on the box's git setting |
| H2 the instrument check assumes the orchestrator checkout is at the base | GLM, minor | residual: fails closed; the designer runs from the base commit |
