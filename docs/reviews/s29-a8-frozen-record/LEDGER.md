# S29 B8-A8 rule 3.6 — four-eyes record (S29-P21, under C388)

```
[four-eyes 0.7.0] outcome: completed; mode: light (the A8 verdict's input path; a consumer fix)
designer, implementer, fixes: Claude Code: claude-opus-5-5 (designer); claude -p: claude-opus-5-5, 518a94f8 (implementer); fresh claude-opus-5-5 sessions for fix rounds 1–3
test-writer: claude -p: claude-sonnet-5-5, b17d2dd3; delivery 1 only (its sandbox refused the test command: the designer ran the frozen tests on the baseline, 12 failed / 15 passed, and froze them 2026-11-23T17:29:41Z, before any candidate was revealed); deliveries 2+ replaced by the designer's clean-copy runs, said so
panel: cold on candidate 3: sol: cursor-agent gpt-5.6-sol-high, briefed, returned (P1); verify of candidate 4: sol, fresh session (runtime cannot resume), returned (P1 resolved, P2)
shared: implementer, fixes, test-writer and designer are Anthropic; not covered: their shared blind spots, except where the one Sol review saw them
go / accept: the designer under C388 (standing authority for session 29); commit: this commit; push: none (gate first; C387)
```

Spec `docs/specs/s29-a8-frozen-record.md` v1.2. Baseline `a073d594e`.

| id | source | finding | disposition | why |
|---|---|---|---|---|
| F1 | implementer r0 | seven real-record tests assert the pre-decider world | adopted (fix 1) | stale premises; intent kept, names updated; 4 already failed on `main` after the decider data (S29-P22) |
| D1 | frozen tests (test-writer) | a pilot pair rejected by B8-A8 rejected every decider pair | adopted (fix 2, spec v1.1) | the amendment binds the pilot dossier the sequencer recorded, independent of B8-A8's pilot view |
| J1 / Sol P1 | implementer r0, Sol opinion | a decider naming the v8 base passed rule 3.6 | first declined as residual, then adopted (fix 3, spec v1.2) | the consumer checks recorded facts: a decider on v8 skipped the pilot gate's amendment; fixtures now model the real records |
| Sol P2 | Sol verify | the amendment's other fields (walls, deadlines, created) not validated | declined (residual) | outside the supported conditions: our writer is the only source; seal + v8 and pilot-dossier bindings pin it; the sequencer validates it fully at every launch |

Tests: frozen `s29b_frozen` 27 (baseline 12 failed / 15 passed); candidate 4 on a clean copy: 1747 tests (frozen + implementer + every real-record module + all `test_m76_b4b2_*`), 0 failed, 0 skipped. Real records: B8-A8 `complete`, s1 / s2 / pilot / reload accepted, `B8.json` byte-identical.
