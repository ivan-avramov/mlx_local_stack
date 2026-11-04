# P613 step 2 (Wave 1 adapters + rule 6) — findings and dispositions (designer), 2026-11-04

Sources: panel opinion (GPT-5.6 Sol High, `cursor-agent --mode ask`, findings P1–P17; GLM 5.2, same, "NOTHING OF SUBSTANCE" + minors
M1–M2, test gaps G1–G2, scope notes S1–S3), test-writer delivery 2 (Claude Sonnet 5.5, F1–F5, verdict fix-then-merge), designer.
All original unless marked. Sol finding ids are its own numbering (not the session's P-sequence).

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| D1 new module written over the Wave 1 sequencer `bench/p426_wave1.py` | hazard (designer, brief-caused) | repaired by designer before reveal | the brief named that file as an example; moved to `p426_signals_wave1.py`, sequencer restored, outputs byte-identical, 274 neighbour tests pass |
| D2 contract errata (A4 per-draw list; `request_seeds` location) | contract defect (designer) | fixed `e1f6c70a` | found by both helpers |
| Sol P1 / TW F2 a smoke leg without SCRUB refuses all; smoke files in `inputs` | major | adapted (fix 1) | smokes are coverage only: missing / unreadable / mismatched smoke manifests are recorded in `scrub_coverage`, never a refusal; smoke files leave `inputs` (listed with their shas in `scrub_coverage`) |
| Sol P2 thinking budgets compared as multisets; 81920 not enforced | major | adopted (fix 2) | compare per key; every Wave 1 row's budget must be 81920 or the pair is rejected (the sheet labels `@81920`) |
| Sol P3 either arm's worktree normalised | major | adopted (fix 3) | require the leg's own arm path component before normalising |
| Sol P4 missing identity fields pass as `None == None` | major | adopted (fix 4) | identity text must be a string and A1 / A2 `content_sha256` 64-hex, else refusal |
| Sol P5 inputs read through symlinks outside `rows_root` | major | adopted (fix 5) | committed-only inputs: every resolved input path must stay under the resolved `rows_root`, else refusal |
| Sol P6 a torn rows file refuses before SCRUB can reject the pair | major | declined | a torn / unreadable required file is a refusal in the step-1 contract and the `chain_rows` torn-file rule; fail closed is the stricter outcome |
| Sol P7 / TW F1 no per-arm both-block A1 accuracy | major | adopted (fix 6) | the ranking key both blocks (96/100 each arm) must be in the sheet |
| Sol P8 A1 enters the family "complete" with one block rejected | major | adopted (fix 7) | A1 is a family member only when both A1 blocks are B8-accepted; else the family is labelled incomplete |
| Sol P9 acceptance sums only key-accepted rows | major | adopted (fix 8) | contract: over the ON rows of each accepted block |
| Sol P10 / TW F4 bootstrap order is `ids.json` order | minor | adopted (fix 9) | contract: sorted (block, key) |
| Sol P11 walls / identity include rejected pairs | major | adopted (fix 10) | accepted pairs only; rejected pairs appear in coverage |
| Sol P12 / TW F5 Wave 1 flags carry no items | major | adopted (fix 11) | each flag lists its keys / legs with both arms' values (P616 rule) |
| Sol P13 rejection reasons may serialise raw paths | major | adapted (fix 12) | public repo: reasons pass through one masking helper (absolute / home-relative path tokens → `<path>`); a test with a path in a mismatching argv |
| Sol P14 / TW F3 rule 2a / 2d reasons lack the values | minor | adopted (fix 13) | contract: each rejection names the pair, the rule and both values |
| Sol P15 A3 turn-2 drafts gate the pair | minor (beyond contract) | declined | recert §2: every eligible ON request carries draft activity, every OFF request none; turn 2 is a request; kept, documented in the sheet |
| Sol P16 S-build deny pattern misses `.p426-on-` | major | adopted (fix 14) | match `p426-(off|on)-` after `/` or `.` |
| Sol P17 `render_md` raises on the `all` record | minor | adopted (fix 15) | `render_md` dispatches on the record shape (A7 record → step-1 output byte-identical; `all` record → the new renderer) |
| GLM M1 rejected-key shape differs by axis | minor | adopted (fix 16) | one key shape per axis, accepted or rejected |
| GLM M2 implementer report stale on A4 | minor | no change | report only; erratum D2 |
| GLM G1 / G2 untested: rejected A7 session under `all`; one rejected Wave 1 block | test gap | to the test-writer (delivery 3) | |
| GLM S1 / S3 M1 `status` gate; extra evidence fields | scope note | kept | fail closed / evidence only |
| TW frozen-test defects (draft_n_accepted A4 param; SCRUB-mismatch rows mutation tears the file; two percent-match false positives; the 0.375 collision; "panel" word in A3; identity location; inputs re-key under `all`) | test defects | to the test-writer (delivery 3: amend, keep what the contract supports, refreeze) | candidate values are right (checked) |

## Verify round (GPT-5.6 Sol High — first dispatch failed `ECONNRESET`, one unchanged retry valid; GLM 5.2 valid) and test-writer delivery 4

GLM: all 16 fixes resolved; P6 / P15 declines agreed; A1 (fix report's 9-failure table stale) — answered by delivery 4 (388 passed,
1 skipped, 0 failed on the amended frozen set). Sol: P1, P2, P4, P7–P12, P14, P16, P17 resolved; three partial claims and one new:

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| Sol P3-partial a leg's argv need not name its own worktree | major (claimed) | declined, residual | arm identity is enforced by rule 2a (`state.stack_head` == `stack_head_<arm>`, recorded by the leg wrapper in the worktree it ran from) and rule 2b (registry sha per arm, opened from git); the path is a label |
| Sol P5-partial noise-floor / A7 readers unconfined under `all` | major (claimed) | declined, residual | those are the step-1 readers (step 1 unchanged by contract); the committed tree holds 0 symlinks (0 git mode-120000 entries); confining them is a later step-1 change |
| Sol P13-partial `speed_problems` / `log` copied unmasked | major (claimed) | declined | copied from committed, scrubbed receipts (already public bytes); the mask covers text B8 generates |
| Sol P18 key-rejection reasons omit `rule 3` / one A4 value | minor | residual | literal; no rejected key on the committed data |
| TW d4 mask leaks past a space; Windows paths | minor | residual | no reason text on the committed data |

Post-Accept (designer, comment-only, behaviour-preserving; the repo's naming / PII hooks refused the commit): two edits to frozen
tests — `test_p613s2_signals_flags.py` a class comment's "low turn-1 acceptance" → "turn-1 acceptance under 0.70" (naming hook read <!-- allow-shorthand: the word "low", not a model -->
"low" as model shorthand); `test_p613s2_fixround.py` the three fix-12 lines that must SHOW fake home paths carry `allow-pii-pattern`. <!-- allow-shorthand: the word "low", not a model -->
The two files: 64 / 64 pass after the edits.
