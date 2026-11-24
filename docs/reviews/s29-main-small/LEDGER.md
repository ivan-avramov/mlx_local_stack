# S29 main-small — four-eyes record (K2 re-check ack actor, V1 KV vision rubric; PLAN M85 phase 1)

```
[four-eyes 0.7.0] outcome: completed; mode: light (main-side, no identity change)
designer, implementer, fixes: Claude Code claude-opus-5-5 (designer); claude -p claude-opus-5-5 (implementer — its sandbox refused python / git, the designer ran and exported candidate 1); fresh claude-opus-5-5 (fix round 1)
test-writer: claude -p claude-sonnet-5-5 59b18a86; continued (deliveries 1–2); frozen 2026-11-24T16:10:38Z; amended (K2 constants, V1 via kv_rubric("A3")) and refrozen
panel: opinion r1 + verify r2 — sol: cursor-agent gpt-5.6-sol-high, briefed, fresh sessions
shared: implementer, fixes, test-writer, designer are Anthropic; not covered beyond the Sol rounds
go / accept: the designer (C390); push: the operator's word
```

| id | source | finding | disposition |
|---|---|---|---|
| TW-1 / Sol P1 | test-writer, Sol r1 | the legacy bare `--recheck-ack <sha>` resume refused at the argument check | adopted (accepted only when sequence.json records the matching ack) |
| Sol P2 | Sol r1 | the old-rubric exception scoped to member A3, not to the frozen record | adopted (bound to the frozen A3 FROZEN.json sha) |
| Sol P3 | Sol r1 | control characters in a ruling can forge log lines | adopted (refused) |
| TW-2 | test-writer | a second ack silently ignored when one is recorded | declined (minor; "stays as recorded") |
| V-P1 | Sol r2 | the legacy check accepts a matching ack from any gate | declined (residual): re-check 2 never stops, so no gate but s1 ever holds an ack; `ensure_recheck` still requires the actor before any write |
| note | implementer | the non-KV P426 B3 `vision` rubric keeps its caption clause | out of scope (frozen P426 records bind it) |

Tests: frozen `s29d_frozen` 25 (baseline 11 / 25), candidate 2 63 / 63 targeted, 2139 / 2140 related (the known home-path temp-dir case).
