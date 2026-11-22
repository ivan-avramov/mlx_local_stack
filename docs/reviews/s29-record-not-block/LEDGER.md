# S29 record-not-block — four-eyes record (C384, S29-P6; accepted C385)

```
[four-eyes 0.7.0] outcome: completed; mode: light (data boundary: the harvest; not security / architecture, per the operator's standing rule)
designer, implementer, fixes: Claude Code: claude-opus-5-5 (designer, this session); claude -p: claude-opus-5-5, 60a04d2a (implementer); claude -p: claude-opus-5-5, 7218c583 (fix round 1, fresh)
test-writer: claude -p: claude-sonnet-5-5, 345cbacf; continued (deliveries 1–4); tests frozen 2026-11-22T18:03:37Z, candidate revealed 2026-11-22T18:57Z; amended to spec v1.1 and refrozen 2026-11-22T20:03:09Z
panel: cold on candidate 1: sol: cursor-agent: gpt-5.6-sol-high, no session id, briefed, user instructions unconfirmed, returned; verify of candidate 2: sol: fresh session (the runtime cannot resume), returned
shared: implementer, fixes, test-writer and designer are all Anthropic; not covered: errors Anthropic models make consistently, except where the one Sol review saw them
go: 2026-11-22, "go"; accept: 2026-11-22, "accepted: proceed as recommended"; commit: this commit; push: none
```

Baseline `204a8da16`; spec `docs/specs/s29-record-not-block.md` v1.1.

## Findings

| id | source | finding | disposition | why | kind |
|---|---|---|---|---|---|
| F1 | Sol P1, TW-2 #3, TW-1 | the listing published the sha256 of unscanned bytes | adapted | dropped: path (scrubbed) + size only; references keep a match boolean (spec v1.1) | original |
| F2 | Sol P2 | reference relaxation extends beyond row references | declined | C384: an unrecognised file never refuses, whoever references it; checks on published files unchanged; spec v1.1 says "any harvested record" | scope |
| F3 | Sol P3 | partial `leg.c360.json` after a crash stops every resume | adopted | temp + fsync + exclusive link + dir fsync | original |
| F4 | Sol P4 | stale `host_env_after_last_leg` after a resume | adopted | rewritten on every final check (H3b) | original |
| F5 | TW-2 frozen failure | an account-named listed path refused the harvest | adopted | listed paths scrubbed | original |
| F6 | TW-2 #1 | H5 after a committed but unrecorded harvest | adopted | left as recorded when the published HARVEST.json exists | original |
| F7 | TW-2 #2 | supersession link never checked downstream | adopted | the harvest checks the kept original (exists, regular, bytes hash, self-hash) | original |
| F8 | TW-2 #4 | digest mismatch on an unrecognised reference only listed | declined | the file is not published; recorded as `sha256_matches: false` (C384) | original |
| F9 | TW-2 #5 | loose file in a `.final_tree` no longer refuses | declined | C384; listed, does not affect grading | original |
| F10 | TW-2 #8 | kv test pinned a fixture KeyError | adopted | asserts the C384 outcome at the first leg | original |
| F11 | TW-2 #9 | spacing nits | adopted | — | original |
| F12 | Sol verify P5 | link check does not compare `superseded_sha256` / the kept name | declined (residual) | the bytes hash already binds the kept file, whose own seal is that sha256; only a forged correctly-sealed record could disagree | introduced by a repair |
| F13 | Sol verify P6 | 22 frozen tests failing | declined (stale) | Sol saw the pre-refreeze report; refrozen tests 87/87 pass on candidate 2 | — |
| F14 | operator side note (S29-P10) | `leg.json` rewritten in place | kept (C385: designer's call, quality bias) | original bytes kept and published as `leg.c360.json`, link checked; zero consumer changes vs five for a side record | — |

## Tests

- Frozen (`bench/tests/s29_frozen/`, 87): baseline 67 failed / 20 passed; candidate 1 24 failed (all v1.1); candidate 2 87 passed.
- Scope run (132 modules + `test_s29_impl_*`): candidate 2 4047 tests, 1 failure = the baseline's environment-dependent
  `test_s26_positives.py::…absolute_home_path` (temp dir under `$HOME`); no baseline pass fails. Baseline also had the order-dependent
  `test_s27_fe_r1.py::test_x10_…` (S29-P9).
- Real record: dry-run harvest of `tg2-m76-x-s1.a3` — baseline code rc 4 on `execute.marker` (known positive), candidate 2 rc 0,
  no problem, `leg.json` untouched.
- Not run: the full stack gate (after the decider, before the push).
