# Implementer report, fix round 1 — S29 main-small

Baseline `f8851c108a55053e1c6413efaa1eec186d0056ff`; candidate 2 = candidate 1 + the three fixes below. Export
`out/candidate-2.diff` (sha256 `02822d938e919ff375aee9b264ebdbe6352e4c6864f1f3d8cadf470dc1050d55`; frozen tests excluded as briefed).
Files touched this round: `benchmark/bench/p426_wave2.py`, `benchmark/bench/p426_panel.py`, and the implementer tests
`benchmark/bench/tests/test_s29d_impl_k2_ack.py`, `benchmark/bench/tests/test_s29d_impl_v1_vision.py`. Frozen tests and the spec are untouched
(sha256 of `s29d_frozen/*.py` identical to test-writer delivery 2). No file under `benchmark/results/` changed. Nothing committed.

## Fixes
1. **Sol P1 (legacy resume at the CLI).** `_check_recheck_ack_args` now accepts `--recheck-ack <sha>` with neither `--recheck-ack-by` nor
   `--recheck-ack-ruling` only when `_recorded_ack(a)` finds, in `<out-base>/sequence.json`, a `rechecks.<gate>` whose sealed `sha256` equals
   the given sha and whose recorded `ack.sha256` equals it too (the S29-P13 shape). Otherwise (no ack recorded, another sha, unreadable /
   non-object `sequence.json`, or only one of actor / ruling given) it still calls `recheck_ack_actor` and refuses before anything is written.
   `ensure_recheck` is unchanged: a recorded ack stays as recorded.
2. **Sol P2 (old rubric bound to the exact frozen record).** `KV_FROZEN_RUBRICS["A3"]` entries are now
   `(rubric, rubric_sha256, FROZEN.json sha256)` = `("vision", 5987d169…97b8, 9ff014b5f52a7d25e1ef24d70f2e51933353b54fed8a0d279be33409944e7d06)`;
   the last is the sha256 of `benchmark/results/m76/panel/A3/FROZEN.json` at the baseline (verified with `git show f8851c108:… | shasum`).
   `kv_check_frozen` passes the sha256 of the FROZEN.json it read to `_kv_check_manifest` → `_kv_rubric_ok`; without that identity
   (default `None`) or with any other record, the old pair is refused ("member / rubric is not this member's"). Current-rubric records are
   unaffected. The FROZEN.json sha covers the whole frozen set via its `files` map.
3. **Sol P3 (control characters in a ruling).** `recheck_ack_actor` refuses a ruling containing any Unicode category `C*` character
   (Cc incl. CR / LF / TAB / ESC / NUL, Cf incl. bidi overrides, Co, Cs, Cn) or a line / paragraph separator (Zl / Zp). It is reached both from
   `check_args` and from `ensure_recheck`, so the refusal is before any write either way.

## Tests added (implementer files)
- K2: `test_k2_fix1_the_legacy_resume_command_passes_the_argument_check_and_resumes` (parse_args → check_args → Sequencer.ensure_recheck
  with the S29-P13 command; `sequence.json` bytes unchanged, ack still actor-less); `test_k2_fix1_a_new_ack_without_its_actor_still_refuses_at_the_argument_check`
  ×3 (no ack recorded / other sha / ruling-only with a recorded ack; sequence bytes unchanged); `test_k2_fix1_a_new_ack_with_actor_and_ruling_passes_the_argument_check`;
  control-character rulings ×7 through `ensure_recheck` (no write, no "acknowledged" log line) and ×7 through `check_args`.
- V1: `test_v1_fix1_the_old_pair_is_bound_to_the_exact_frozen_a3_record` (copied frozen bytes verify; `_kv_rubric_ok` false without / with a
  wrong identity / for another member); `test_v1_fix1_a_new_a3_record_carrying_the_old_pair_refuses` (a copy of the A3 record with one added
  key, same `(vision, 5987d169…)` pair, refuses on the rubric check).

## Runs (all via `../fe_test.sh stack …`)
| run | result |
|---|---|
| the 21 new `fix1` tests on candidate 1 (my source changes reverse-applied, then re-applied; `git diff --stat` checked both ways) | **17 failed, 4 passed** (the 4 are guard rails that already held: 3 incomplete-ack refusals, 1 full-ack accept) |
| `test_s29d_impl_k2_ack.py` + `test_s29d_impl_v1_vision.py` + `s29d_frozen`, candidate 2 (after the final edit) | **63 passed** (25 frozen + 38 implementer) |
| wide related set, candidate 2: the 47 test modules that import `p426_wave2` / `p426_panel` plus the directories `s29d_frozen`, `s29_frozen`, `s26_frozen`, `p613s3`, `p613s4` | **2140 tests, 1 failed, 2139 passed**, 0 errors / skips (counted from the progress lines; the wrapper prints no totals line) |

The one failure is `s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path`. It is the same
pre-existing environmental failure the test-writer saw on both the baseline and candidate 1: the pytest temp dir sits under `$HOME` on this
box. Caveat: the wide run started before the last one-line edit, which added `AttributeError` to `_recorded_ack`'s except tuple so a
non-object `sequence.json` refuses instead of raising. The targeted set (63) was re-run after that edit and passed. The wide set was not re-run.

## Notes / open
- The legacy allowance keys on what `sequence.json` records, not on a flag, per AGENTS "guards check recorded facts". It does not
  distinguish an actor-less legacy ack from a full one; both resume with the bare sha, which is harmless since nothing new is recorded.
- Test-writer finding 2 (a supplied ack silently ignored when one is already recorded) is not in this brief; unchanged.
- The P426 B3 `vision` rubric still carries the "reference captions" clause (out of spec, unchanged, as frozen records bind it).
