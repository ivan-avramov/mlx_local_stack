I wrote the step 3 tests into `benchmark/bench/tests/p613s3/`. On the baseline (`27fa4233`) 78 fail, 29 error, and 10 pass; the 10 are the world-sanity checks. None of the tests has run against an implementation, so none is proven correct yet. I wrote nothing outside the test directory, committed nothing, and never printed `POLYGLOT_DIR`.

## Baseline run
Command, from `benchmark/`: `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/p613s3`

Last line, verbatim: `78 failed, 10 passed, 29 errors in 29.63s`

Failure kinds:
- **Missing function** (`AttributeError`): `a7_select`, `a7_packet`, `freeze` and `check_frozen` do not exist in `bench.p426_panel`. This covers all select, packet and golden tests.
- **No CLI**: `python -m bench.p426_panel` has no `main`, so every `a7-export`, `a7-cursor` and `a7-seal` call exits 0 and writes nothing. Tests then fail on a missing `manifest.jsonl` or `FROZEN.json`, or on `assert 0 != 0` in the refusal tests.
- **29 errors**: module-scoped fixtures that need the export. These are the packet fixture and the S1, S2 and S3 verdict scenarios.
- **Vacuous passes removed**: refusal tests that `pytest.raises(Exception)` would have passed on the missing-attribute error. They now use `S.refuses`, which rejects `AttributeError` and `TypeError`, and `S.refused_cli`, which rejects rc 0 and argparse usage errors, plus positive controls.
- **Golden tests**: they ran rather than skipped, so `b6ec7819` and `POLYGLOT_DIR` are available.

## Files
- **Support:** `__init__.py`, `conftest.py` (marker `p613s3_golden`), `s3world.py`, `sigview.py`.
- **`s3world.py`:** builds the hermetic world: the step 2 Wave 1 world, with A7 session s1 holding 6 selectable items and s2 holding 8, plus an `evidence` commit built by `git fast-import`, a fake polyglot tree, a fake universe, a fake `judges.json` and a fake `cursor-agent` placed first on PATH.
- **Tests:** `test_p613s3_select.py` (12), `test_p613s3_packet.py` (27), `test_p613s3_export.py` (27), `test_p613s3_judges.py` (12), `test_p613s3_signals.py` (27), `test_p613s3_golden.py` (5), `test_p613s3_world_sanity.py` (10).
- **Class:** each test has a `# class:` comment. All are `new-behaviour` except the `invariant` ones. There are no `reproduces-failure` tests, because step 3 adds features and fixes no bug.

## Coverage
- **Selection:** both-pass non-identical keys, each exclusion kind, pilot and reload never selected, `passed is True` strict, and B8's `identical` flag honoured.
- **Packet text:** diff text and tool counts on a known case, new and unchanged files, the append instructions file.
- **Packet checks:** leak checks, and a protected test file that differs from its start version.
- **Hash refusals:** object, events, start-tree file, universe, main manifest, and the B8 per-key manifest sha.
- **Export and freeze:** A/B balance, slot follows the manifest, byte-identical re-export, three leak variants, existing directory, verdict present, bad judges.
- **`check_frozen`:** changed packet, missing packet, missing `FROZEN.json`, verdicts ignored.
- **Judges:** `a7-cursor` (one call per packet, failures missing and not retried, garbage, resume, changed packet) and `a7-seal` (binding, idempotent, changed packet).
- **§4.5 numbers:** three hand-computed verdict scenarios.
  - S1: exact p 0.125 and 2/256, Holm m = 2 and its algebra, flag raised.
  - S2: ON favoured, no flag.
  - S3: one verdict missing is counted and the item excluded, and a member with fewer than 5 judged items is untested, giving m = 1.
- **§4.5 sheet and refusals:** status line, Wave 1 members at 0.5 with judged 0, A4 never tested, provenance, byte-identical regeneration, no absolute path, and the `--panel` refusals.
- **Golden:** 21 packets, excluded counts and ids, 84 planned verdicts, and Wave 1 identical = 166.
- **Not covered:** the golden subjective family {A7-s1, A7-s2} with m = 2, because no committed verdicts exist yet.

## Ambiguities and the reading I tested
- **A1. `freeze`'s `packets_meta` shape is unspecified.** I never call it with real metadata. `freeze` is tested through the export CLI, and by calling it with `[]` on a directory holding a verdict and expecting `RefusalError`. A different error type would fail that test.
- **A2. `a7_select` `excluded` layout.** I read `excluded[session][kind]` (also accepting the transposed layout), as an int or a collection of ids, with `one-arm-pass` as ids.
- **A3. `FROZEN.json` keys are not fixed.** Tests search for the recorded values anywhere in the document (hashes, ids, judge fields, 56 planned, Wave 1 identical).
- **A4. `a7_packet` rendering.** I assume the `difflib` diff lives in `off` / `on`, and the solution file names plus instructions in `task`. `len_*` equals the diff character count on files ending in a newline. The grader sentence is searched across `task + off + on`. The tool line is `edit 1, read 2` style.
- **A5. A/B balance.** I test only that exactly half of the 14 items show ON as A, which holds whether `make_pairs` runs per session or over all items.
- **A6. §4.5 JSON key names are not specified.** `sigview.py` searches alias keys and fails with the keys tried if none match. Expect this to be the first thing to settle with the implementer.
- **A7. §4.5 count semantics.** Fixtures make "missing" equal 1 verdict and 1 item for s1, and 4 and 4 for s2, so either reading passes.
- **A8. CLI refusals.** I assume a refusal exits non-zero with a stderr message. Only the hash, `FROZEN.json`, changed-packet and B8 cases also assert rc 2 and `REFUSED`.
- **A9. Readings the contract does not state.**
  - `a7-cursor` and `a7-seal` run `check_frozen` first.
  - `all --panel` refuses if B8.json changed since the freeze.
  - An export containing a leak mentions "leak" on stderr.
  - A modified test file raises `RefusalError` or `AssertionError`.
- **A10. The `passed` check.** A truthy non-bool such as `1` is tested only as "not selected", not as a particular exclusion bucket.
