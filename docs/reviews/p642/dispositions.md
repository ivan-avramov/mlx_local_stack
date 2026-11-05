# P642 / P433 (C209) — the v2 pre-check's plugin-load proof from the activation call — review dispositions (designer), 2026-11-04

Opinion, round 1 of 3. Members: GPT-5.6 Sol High (`gpt-5.6-sol-high`) and GLM 5.2 (`glm-5.2-high`), `cursor-agent 2026.10.22 --mode ask`, fresh sessions, `checkout` (the change applied; user instructions unconfirmed); both exit 0, no file modified. Raw: `opinion-sol.md`, `opinion-glm.md`.

| Finding | By | Disposition | Why |
|---|---|---|---|
| P1 `test_real_missing_print_logs_refuses` matches `"plugin"`, which the new activation-exit refusal also satisfies | Sol, minor, confirmed | adopted | match `"lacks loading plugin"`: pins the missing-log refusal itself |
| P2 the activation-call test checks only `OPENCODE_PRINT_LOGS` | Sol, minor, confirmed | adopted | asserts the full argv, env (== the caller's), cwd, timeout, stdin, capture flags |
| F1 AGENTS.md C114 reads "the probe's one pre-check discovery call"; the v2 pre-check now makes two (as tg1 already does) | GLM, minor, hypothesis | to the operator (P644) | an AGENTS.md wording question, not code; the tg1 precedent exists |
| F2 `test_destination_documents` no longer asserts the whole call sequence | GLM, minor, confirmed | declined | covered by the new activation tests; symmetry only |

GLM's verdict: NOTHING OF SUBSTANCE (race removed, fail-closed kept, no other caller or scaffold changed; D1 holds as a server-handler property). No blocker, no major.
