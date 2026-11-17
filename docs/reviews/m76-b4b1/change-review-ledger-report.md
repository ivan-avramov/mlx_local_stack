# M76 B4b-1 tg2 runner — change review ledger (four-eyes strict, opinion; round 1 of 3), 2026-11-16

Candidate 1: implementer Claude Opus `claude -p`, session `7352f2ff`, on `3c199587`. It hit its 4 h limit (rc 142) before
reporting; the report was recovered by a read-only resume. Spec `docs/specs/m76-b4b-tg2-runner.md` v5. Test-writer Claude Sonnet,
session `55abb7d4`: delivery 1 frozen 2026-11-17T03:48:04Z (1,443 files), 26 failed / 264 passed on the candidate (139 s). Delivery 2
(candidate revealed 04:29:08Z) classed all 26 as seam guesses and amended them; the designer re-ran 392 passed (46 s). The copy's
full suite on the final tree fails only the environment set (no `.venv-bench` in the copy) plus `test_registry_published_set` (2).

Panel: Sol `gpt-5.6-sol-high` and GLM `glm-5.2-high` (cursor-agent, `--mode ask`, read-only checkout snapshot, rule files renamed;
user instructions unconfirmed; no session id, so the verify round will be fresh sessions). Both returned (Sol 7 findings, GLM 10).
Raw: `opinion-change-{sol,glm}.md`. Verified by the designer in the candidate source: L1, L2, L3, L4, L8.

| id | raised by | finding | sev | disposition |
|---|---|---|---|---|
| L1 | Sol P1 | `m62/inject_verify.check_files` requires `evidence_sha256` keys exactly `{events, export, stderr}`; a v2 row (date-frozen) also carries `datefreeze` (+ `toolwindows` when present) → every real tg2 inject positive is `FAIL:evidence_sha256_keys`, v8 refuses, no tg2 leg can start; both test sets use a fake `inject_verify` | blocker | adopted: for the v2 scaffolds the key set is the row's recorded artifacts (`events`, `export`, `stderr`, `datefreeze`, optional `toolwindows`), each path present and hashing to its digest; a red test on a real-shaped v2 row through `BoxSeqOps.positive_inject` → `inject_verify` |
| L2 | Sol P2 | `Tg2Corpus.load_universe` checks the universe's polyglot sha against the image record but never the live checkout (`source_sha()`), nor the items' recorded `inputs_sha256` (`.docs` included) → a drifted checkout produces prompts for different tasks and v8 freezes it | major | adopted: refuse unless `source_sha() == universe.polyglot_sha`, and each selected item's `inputs_sha256` (via `m65.tg2_universe.inputs_sha256`) equals the recorded one, before prompt / materialisation |
| L3 | Sol P3, test-writer R2 | `ensure_recheck`: a `sequence.json` record without its sealed file re-runs the re-check and overwrites the record ("re-verifies, never re-runs" broken); a sealed file without a record (crash between seal and save) stops rc 1 | major | adopted: record without file → Stop (the operator decides); sealed-OK file without record → re-verify the seal, record it from the file, log it (the crash window); compute only when neither exists |
| L4 | Sol P4, GLM F1, delivery-1 test | `tg2_strict_rows` ignores stray rows, stray DNFs and row / DNF overlap | major | adopted: rows ∪ DNFs == planned slots exactly, rows ∩ DNFs = ∅, else refuse; the test-writer restores the refusal test |
| L5 | GLM F3, test-writer (dropped assertion) | tg2 `v8` silently ignores `--r1-off` / `--r1-on` (spec: "no R1") | minor | adopted: tg2 v8 refuses either flag |
| L6 | Sol P5 | the direct tg2 freeze / positives / chain entry points accept arm `v` and pairs with it (B4b-1 is N16 / X; only the sequencer refuses) | minor | adopted: one tg2 pair contract `("n16", "x")` enforced at every tg2 entry point |
| L7 | Sol P6, test-writer R1, implementer | `test_registry_published_set.EXTRACTORS` lacks the new target `opencode-bench-v2-web-tg2` (2 failures) | minor | adopted: the designer adds `_opencode_ids` for it (test-only, in the fix round) |
| L8 | GLM F2 | `t_coop` "double-counts" the 2× (join 2545 vs 1825) | — | declined: the corpus bound `2 × max(timeout_s) + 300` is ONE grade (compile + execute); the join's 2× is the active grade plus one queued capture — `arm_runner.grade_join_timeout_s`, the formula the real `GradeWorker` uses (traced); Sol P7 and the test-writer agree |
| L9 | GLM F4 | `validate_reports` tg2 rules opt-in (`grader="tg2"`) | minor | declined for B4b-1: both production callers pass it (traced); auto-selecting by language breaks the M64 four-language fake corpus. Carried to B4b-2's spec: every new tg2 consumer passes `grader="tg2"` |
| L10 | GLM F5 | slot base arm field `oc`, not `n16` / `x` | minor | declined: tg1 parity (golden); arms are identified by the pair gate on the worker argv and by the leg name |
| L11 | GLM F6 | `--print-identity` omits the universe / draw sha | minor | declined: tg1 parity; the universe enters through `scaffold_policy_sha256` (the test-writer's amended tests show it rotates) |
| L12 | GLM F7, F10 | `--rehearsal r2 --kv-arm n16` refuses instead of overriding | minor | declined: refusing a contradictory command is fail-closed and the spec table fixes R2 → X |
| L13 | GLM F8 | `--tg2-inject` dest is `tg1_inject` | minor | declined: internal attribute; the CLI surface is `--tg2-inject` |
| L14 | GLM F9, implementer deviation 10 | spec v5 says re-check 2 "after s2" in the text and "after reload" in the order line | minor | spec erratum v5a (designer): the order line holds (re-check 2 after the reload pair, over s1 + s2; it never stops); candidate unchanged |
| L15 | test-writer R3 | `positive_inject`: a probe crash with no output reads as a transport abort (one retry) | minor | declined: fail-closed either way (retry once, then the kind fails, v8 refuses) |
| L16 | test-writer R4, implementer | `row_scores.py:43` matches only the tg1 label | — | B4b-2 (consumer side) |
| L17 | GLM (seams), Sol P1, implementer | box-side positives seams (`positives_session`, `positive_inject`, `inject_verify`) only ever ran through fakes | scope | L1's real-shaped row test covers the verify seam; the rest is acceptance criterion 3 (real output on the box), unchanged |
| L18 | designer (S25-P2) | the committed universe refuses in `m65.tg2_universe.load()` on `main` (freezer closure rotated by tg1-side edits); the grader fix will bump `VERSION` | — | → operator, S25-P2: re-freeze after the grader fix, then bump `TG2_UNIVERSE_SHA256`; B4b-1's recorded-facts check (+ L2) stays |

Next: fix round 1 (fresh implementer on candidate 1: L1–L6; the designer L7 and L14), test-writer delivery 3 (a test per adopted
defect, L4's refusal test restored), panel verify (fresh Sol + GLM, round 2 of 3), Accept → operator.
