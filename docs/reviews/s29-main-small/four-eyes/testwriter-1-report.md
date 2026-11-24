# Test-writer report, delivery 1 — S29 main-small (K2, V1)

Baseline `f8851c108a55053e1c6413efaa1eec186d0056ff`. Files added (nothing else touched):
`benchmark/bench/tests/s29d_frozen/{__init__.py,test_k2_recheck_ack.py,test_v1_vision_rubric.py}`.

## Run
`../fe_test.sh stack bench/tests/s29d_frozen` on the baseline: **14 failed, 11 passed** (25 tests, 0.59 s). Red on the baseline is
expected; the 14 failures are the behaviour the spec asks for. I did not run the wider suite, so "nothing that passed on the
baseline fails" is not yet checked.

## Interface guesses (the spec names none) — implementer/reviewer must confirm
The K2 tests need to pass an actor and a ruling. I assumed:
- Sequencer args `recheck_ack_actor` and `recheck_ack_ruling` (CLI `--recheck-ack-actor`, `--recheck-ack-ruling`), actor in {`operator`, `designer`}.
- Record at `rechecks.s1.ack` gains `actor` and `ruling` beside the existing `sha256` and `at`.
All guesses sit in constants at the top of `test_k2_recheck_ack.py` (`ACTOR_ARG`, `RULING_ARG`, `ACK_ACTOR_KEY`, `ACK_RULING_KEY`). If the
implementation spells them differently, change those four constants; no test body depends on the spelling. The CLI flags themselves
are not tested.
- Refusal is accepted as either `W2.Stop` or `fz.Refusal`, raised from `ensure_recheck`.
- Not specified, so not tested: refusal when the ruling is missing; refusal at CLI parse time.

## Tests and baseline result
K2 (`test_k2_recheck_ack.py`)
| test | baseline |
|---|---|
| actor + ruling recorded in sequence.json (operator, designer) | FAIL (no `actor` key) |
| log line names actor, ruling, sha prefix, and not the other actor (operator, designer) | FAIL (log says "the operator", no ruling) |
| designer ack never logged as "acknowledged by the operator" | FAIL |
| ack without a valid actor (absent / empty / blank / `robot`) refuses; sequence.json byte-identical; no ack log line; next resume still rc 5 | FAIL x4 (baseline accepts) |
| refused ack can be redone with an actor | FAIL |
| legacy actor-less `{sha256, at}` record accepted on resume, flag-only and no-flag; record unchanged; log asserts no actor | PASS (baseline already accepts; guards against regression) |
| legacy record not rewritten by a later resume with an actor | PASS (same) |
| wrong sha still stops rc 5, nothing recorded | PASS |

V1 (`test_v1_vision_rubric.py`)
| test | baseline |
|---|---|
| rubric has no "caption" / "reference" / "human" | FAIL |
| rubric asks accuracy / coverage / precision / image, keeps hallucination penalty and the JSON reply contract | PASS |
| rubric text and sha changed, sha follows text | FAIL (unchanged) |
| other rubrics unchanged | PASS |
| frozen A3 FROZEN.json rubric sha equals sha of the old text (pinned verbatim in the test) | PASS |
| frozen A3 packets carry the old text under the old `prompt_sha` | PASS |
| `kv_check_frozen(A3)` still verifies; frozen file shas unchanged | PASS x2 |
| new export (`_kv_write_packets`) binds the new text and its own sha, packets carry no captions | FAIL |
| new `kv_freeze` records the new `rubric_sha256` | FAIL |

## Notes for the implementer
- The A3 pass tests are the trap: `_kv_check_manifest` currently requires `doc["rubric_sha256"] == rubric_sha(doc["rubric"])`. Changing
  `RUBRICS["vision"]` in place will break `kv_check_frozen(A3)` (and `_kv_check_inputs` consumers), so the frozen record must verify
  against its own recorded sha/text while new exports bind the new one.
- V1 export tests call the private `P._kv_write_packets` and `P.kv_freeze` directly (the public `kv_export` needs a full B8 world); if
  those are renamed the tests need adapting.
- Existing tests that pin the old wording or the old log line were not searched for or changed (outside this brief's file list); the
  implementer's list of changed tests is still owed (spec acceptance).
