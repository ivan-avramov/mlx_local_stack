# Test-writer report, delivery 2 — S29 main-small (amend, then verify)

Baseline `f8851c108a55053e1c6413efaa1eec186d0056ff`; candidate `.fe-material/candidate-1.diff` (re-applied after the baseline run; working tree is at the candidate).

## Amendments (only these two files changed)
- `test_k2_recheck_ack.py`: constant `ACTOR_ARG` is now `recheck_ack_by` (ruling `recheck_ack_ruling`, record keys `actor` / `ruling` unchanged). Nothing else edited.
- `test_v1_vision_rubric.py`: V1 assertions now resolve the rubric through `P.kv_rubric("A3")` (helpers `KV_KEY()`, `NEW_TEXT()`, `NEW_SHA()`) instead of the key `vision`. The frozen-record tests still pin the old text and sha `5987d169…97b8` verbatim and still expect the frozen A3 record to say `rubric == "vision"`. Export / freeze tests pass `KV_KEY()`.

sha256:
- `test_k2_recheck_ack.py` `cdbe905bb82bc5357898743b93f42fea3001e30833a9c465f207bc9cb51fb43a`
- `test_v1_vision_rubric.py` `a5903060d7732333c8e63dc371126e57e455aca658db18fa15a75c7d49df7a82`
- `__init__.py` `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty, unchanged)

## Runs (`../fe_test.sh stack …`)
| run | result |
|---|---|
| `bench/tests/s29d_frozen`, baseline (candidate reverse-applied) | **14 failed, 11 passed** (same 14 as delivery 1: K2 record/log/refusal x10, V1 text/sha/export/freeze x4) |
| `bench/tests/s29d_frozen`, candidate | **25 passed** |
| wide set, candidate (45 test modules importing `p426_wave2`/`p426_panel` + `s29_frozen`, `s26_frozen`, `p613s3`, `p613s4`, + the implementer's 2 new files + s29d_frozen), `tw2-candidate.xml` | 2111 tests, **1 failed**, 0 errors, 0 skipped |
| same set minus s29d_frozen and the implementer's 2 new files, baseline, `tw2-baseline.xml` | 2069 tests, **1 failed**, 0 errors, 0 skipped |

The one failure is identical on both: `s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path`
(the pytest temp dir sits under `$HOME` on this box, so the home path appears in the message). It is pre-existing and unrelated; nothing
that passed on the baseline fails on the candidate. 2111 − 2069 = 42 = my 25 + the implementer's 17.

Caveats: the wide set is the modules that grep-match `p426_wave2|p426_panel` (plus the directories), not the whole suite. An earlier
candidate run piped through `tail` was cut off by a tool timeout (BrokenPipe); its numbers are discarded, the figures above are from the
complete redirected re-run. I did not run the implementer's own tests on the baseline.

## Review of the candidate against the spec
- K2 success path, record (`ack = {sha256, at, actor, ruling}`), log line naming actor and ruling (and not the other actor), missing / invalid actor or ruling refuses before any write, legacy actor-less `ack` kept as recorded: all met.
- V1: new `kv-vision` text has no caption / reference / human clause, asks accuracy / coverage / precision against the image; `KV_MEMBER_RUBRIC["A3"]` points to it; frozen A3 verifies against its pinned `(vision, 5987d169…)` pair; frozen records untouched; shared `vision` text unchanged. Met.

Findings:
1. **(medium) The legacy resume command is refused at the CLI.** `check_args` -> `_check_recheck_ack_args` demands `--recheck-ack-by` and `--recheck-ack-ruling` whenever `--recheck-ack` is passed, before `sequence.json` is read. The documented contract is "resume = the same command"; the S29-P13 resume was `--recheck-ack <sha>` alone, which now refuses even though `ensure_recheck` would accept the recorded legacy ack. The legacy record is only accepted if the operator drops `--recheck-ack`. Spec K2 says the legacy record "is accepted on resume"; whether dropping the flag counts is a designer call. My tests exercise `ensure_recheck` (both with and without the flag), so they do not catch this; a CLI-level test would pin it either way.
2. (low) A new ack is silently ignored when any ack is already recorded (`rec.get("ack")` returns first), even with a different actor; consistent with "stays as recorded", but no log line says the supplied actor was ignored. <!-- allow-shorthand -->
3. (low) The `ensure_recheck` docstring line exceeds the repo's line width; ruling is free text (non-empty only), as the implementer notes. <!-- allow-shorthand -->
4. (note) The P426 B3 `vision` axis still carries the "reference captions" clause; out of this spec, as the implementer says.

## Verdict
**Pass with one open design question (finding 1).** The amended frozen tests are red on the baseline (14) and green on the candidate (25), and
the wider related set shows no regression (one identical pre-existing environmental failure). Recommend the designer rule on finding 1 before
adoption.
