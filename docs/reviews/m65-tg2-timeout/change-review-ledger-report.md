# M65 tg2 grader timeout evidence — change review ledger (four-eyes light, opinion; round 1 of 3), 2026-11-16

Candidate 1: implementer Claude Opus `claude -p` (session `34758ec5`) on `0424892c`; spec `docs/specs/m65-tg2-grade-timeout-evidence.md` v1
(+ erratum v1a, S25-P5). Test-writer Claude Sonnet (session `65a87647`): delivery 1 frozen 2026-11-17T05:20:16Z (44 failed / 34 passed on the
candidate, 127 s), delivery 2: all 44 seam guesses, amended; every test green incl. real docker (spins all four languages, 21 grader docker tests,
the regrade: 19 / 19 rows as SUMMARY.json, the Rust spin `transport_abort` → `timeout`). Panel: Sol `gpt-5.6-sol-high`, GLM `glm-5.2-high`
(cursor-agent ask, read-only snapshot; user instructions unconfirmed). Mechanism (implementer, box): GNU `head` writes through stdio, so a
piped step's output sits in its buffer and a kill loses it — the stream marker included.

| id | raised by | finding | sev | disposition |
|---|---|---|---|---|
| G1 | Sol P1 | both test sets' spin step timeouts below erratum v1a (2 / 2 / 6 / 6 s; implementer 5 / 5 / 8 / 10 s) | major | adopted: 5 / 5 / 15 / 18 s (rust / javascript / cpp / java) in both sets, measurement stated |
| G2 | GLM F2 | the read-back's exit status is tar's; at `READBACK_CAP + 1` tar takes SIGPIPE → rc 141 → a real timeout becomes `TransportAbort`; latent (≈ 1 MB slack over a full `.out`), silently coupled to `OUTPUT_CAP` | major | adopted: named invariant asserted at import (erratum v1b) + a test at a full `.out` |
| G3 | Sol P4 | file-only marker + OOM / mem-kill, no-marker mem-kill, read-back OOM / mem-kill unpinned | minor | adopted: fake cases |
| G4 | GLM F5 | no real-box hang of the compile step (compile timeouts were seen misclassified on the baseline: java 4 s, cpp 3 s) | minor | adopted: one docker test, a Rust `build.rs` that loops, 5 s → `timeout` |
| G5 | test-writer D2 (D6) | the regrade test waits 300 s on the Rust spin at the universe's 180 s timeout | minor | adopted: the spin variant re-graded at 5 s (classification identical; the 19-row comparison kept) |
| G6 | Sol P2, GLM F3, implementer D2 / D3 | collect writes no `.out`; the existing `VERSION` pin edited | minor | spec erratum v1b; candidate unchanged |
| G7 | GLM F1, F5 | solution code can delete / overwrite its marker file after the echo → a runaway becomes `TransportAbort` | — | declined (hardening): the spec's recorded known limit; agentic outputs are not adversarial; one fake test documents it (outcome `TransportAbort`) |
| G8 | Sol P3, GLM F4 | the `VERSION` bump means the frozen universe must be re-frozen | — | already ruled (C356 (2)): re-freeze after this lands |
| G9 | GLM F5 | FIFO / hardlink marker, truncated tar on the real box | minor | declined: `parse_readback` rejects non-regular members and checks the content line; fake coverage of tar damage exists |

Next: fix round 1 (implementer: G2, G3, G4, G5, G1 in its tests; test-writer delivery 3: G1 in its tests + a test per adopted row, G7's
documenting test), panel verify (round 2 of 3), Accept → operator.
