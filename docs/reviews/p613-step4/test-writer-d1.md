Delivery 1 is written: 77 tests in `benchmark/bench/tests/p613s4/`. On the baseline, 6 pass, 5 fail and 66 error. The direct-function and binding tests agree with a throwaway reference implementation. No test has run against a real implementation.

## Files (all in `benchmark/bench/tests/p613s4/`)
- `__init__.py`
- `conftest.py` registers the `p613s4_golden` marker. It builds the hermetic worlds and their panels. It finds `a7_divergence` lazily in `bench.p426_signals_divergence`, then `bench.p426_signals`.
- `s4world.py` is the hermetic world, built on step 3's `A7Case`. It replaces the synthetic events with scenario transcripts. The two arms differ in message ids, session ids, timestamps, step and reasoning events, tokens, and `state.metadata`, `title` and `time`.
- `dview.py` holds tolerant readers for the `divergence` record, because the contract fixes no JSON key names, plus the run helpers.
- `test_p613s4_world_sanity.py`, `test_p613s4_divergence.py`, `test_p613s4_binding.py`, `test_p613s4_sheet.py` and `test_p613s4_golden.py` (marked `p613s4_golden`).
- One empty `__pycache__/` directory is left behind, because `rm -rf` on it was denied. It is untracked and harmless.

## Tests and class
There is no `reproduces-failure` test, because step 4 adds a feature and there is no bug to reproduce.

**`world_sanity` (3, invariant):** the expected tables, the accepted keys and events in the world, and that the arms differ in noise.

**`divergence` (22, direct `a7_divergence`):**
- *new-behaviour:*
  - kinds in worlds A and B;
  - `k` values;
  - environment tool names, including a message with two tools;
  - exactly the 22 accepted keys, with one-arm-pass and neither-pass keys included;
  - counts per session and pooled;
  - first divergence wins (environment at k=0 although a generation difference follows);
  - a duplicated tool call is a generation (the `gen` multiset);
  - a tool-input difference at message 2 is a generation;
  - cutoff in either direction;
  - the rejected key's generation difference is not counted.
- *invariant:*
  - parallel tool calls in a different completion order are identical, including per-call outputs;
  - tool-input key order does not matter;
  - interleaved message events are grouped by `messageID`;
  - the noise fields never matter;
  - deterministic;
  - no checkout (HEAD, branch and work tree untouched);
  - the same bytes on another evidence commit give the same record.

**`binding` (≈29 with parametrisation):**
- *new-behaviour, all `RefusalError`:*
  - altered published bytes (4 items);
  - events file missing from the ref;
  - bad refs;
  - HARVEST edits (`published_sha256` wrong, raw `sha256` wrong, duplicate record, missing record, raw sha used as published sha), each followed by a fresh B8 via `reverify()` so the refusal can only come from the binding;
  - a hash-bound events file that is not JSONL;
  - the CLI exits non-zero with `REFUSED` and writes nothing.
- *invariant:*
  - the unmodified world is accepted (control);
  - tampering with the rejected key's events file changes nothing;
  - absent final-tree objects are not required.

**`sheet` (23, via `all --panel … --evidence-ref`):**
- *new-behaviour:*
  - FINAL status in the title and `header.status`;
  - no pending "step 3/4" entry left;
  - header records the ref outside `header.panel`;
  - heading, position (after §4.5, before Flags) and label;
  - the JSON `divergence` record;
  - every item with its kind (and tool name) in the text, sorted by id;
  - flag raised in world A, listing the items, and not raised in world B;
  - 44 `evidence:<ref>:` inputs holding the sha of the bytes read;
  - byte-identical regeneration, including from a copy of the repo at another path;
  - refusals for a bad ref;
  - `--evidence-ref` without `--panel` is never FINAL.
- *invariant:*
  - the flag is not a veto;
  - existing inputs are unchanged;
  - no transcript noise leaks into the outputs;
  - the no-ref path is the step-3 record;
  - adding the ref is additive;
  - no panel and no ref gives the step-2 record;
  - a refusal keeps an existing output.

**`golden` (7, marked):**
- *new-behaviour:*
  - the golden counts (s1 18/24/1/0, s2 17/25/1/0, 86 items, no generation);
  - each environment item carries a tool and an integer `k`;
  - the CLI on committed data gives FINAL, the section, no flag, the header ref and 172 evidence inputs;
  - byte-identical regeneration;
  - once step 4 commits its sheet, the committed `SIGNALS.md` and `SIGNALS.json` equal the `all --evidence-ref b6ec7819` output. This skips with a reason until then.
- *invariant:* without `--evidence-ref`, the output is byte-identical to the committed step-3 sheet at `e8383713`.

## Baseline run
Command, from `benchmark/`: `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/p613s4`

Result: `5 failed, 6 passed, 66 errors in 51.62s`.

- **6 passed**, all of which test unchanged behaviour (no-ref path, step-2 path) or world sanity:
  - the 3 `world_sanity` tests;
  - `test_no_panel_no_ref_is_step2`;
  - `test_no_ref_path_is_step3`;
  - `test_golden_no_ref_path_reproduces_step3_sheet`.
- **5 failed, interface missing:**
  - `test_cli_binding_refusal_writes_nothing`
  - `test_ref_without_panel_is_not_final`
  - `test_cli_bad_ref_refused` (2 cases)
  - `test_refusal_keeps_existing_output`

  Each fails on argparse `unrecognized arguments: --evidence-ref …` (a usage error, not a refusal).
- **66 errors, interface missing:**
  - Direct tests: the `divmod_` fixture fails with `no module defines a7_divergence`.
  - CLI tests: the `final_a`, `final_b` and golden fixtures hit the same argparse error.
- Nothing in the 71 failing or erroring tests failed for a reason other than the missing interface.

## Validation
- I wrote a throwaway reference `a7_divergence` from the contract and ran the direct tests against it: 41 of 43 in the `divergence` and `binding` files passed.
  - The two failures were a test bug in an empty-ref case, which I fixed, and the CLI test that needs `--evidence-ref`.
  - It reproduces the designer's golden counts on the committed data through my extractors.
  - I deleted the reference. Nothing reads it.
- The sheet and CLI tests (`final_a`, flags, inputs, regeneration, golden CLI) have never run against any implementation. Their expectations come from the contract text only.

## Ambiguities and the reading I tested
- **A1, JSON shape:** the contract fixes no key names. Tests accept any shape holding item dicts with `kind` and an id, `k` and tool under aliases, and per-kind count dicts under `s1`/`s2`/pooled. Failure messages list the keys tried. The top-level key `divergence` is assumed, from the heading.
- **A2, `k` for `cutoff`:** not asserted. `k` is the 0-based message index for `generation` and `environment`.
- **A3, several differing tools:** "the first differing tool name" is only tested where exactly one tool differs. The order for several differing tools is unspecified.
- **A4, events matching the raw sha directly:** step 3's code accepts events whose hash equals the row's raw sha without a HARVEST record. The step-4 contract says "bound through HARVEST … else RefusalError". I tested only the refusal cases, not this path.
- **A5, `--evidence-ref` as a branch name:** not tested. A non-hex ref is expected to refuse.
- **A6, `--evidence-ref` without `--panel`:** the contract does not say. I tested only that it is never FINAL (refusal or a non-final status).
- **A7, inputs value:** I read it as the sha256 of the published (scrubbed) bytes read from the ref, with the path repo-relative (`benchmark/results/p426/wave2/…events.jsonl`).
- **A8, header ref:** `header.panel` already carries the panel's own evidence ref (step 3). I tested that the new record sits outside `header.panel`.
- **A9, rejected key:** `p426_signals all` refuses a B8 edited to reject a key ("pair keys differ from B8.json"), which is why step 3's signals tests build without one. The rejected-key tests are therefore direct calls on world A and B. The CLI worlds (`cli_a`, `cli_b`) have no rejected key.
- **A10, vacuous passes:** `test_refusal_keeps_existing_output` fails on the baseline only because its first run needs the new flag. After implementation it would also pass if the output directory check refuses an existing file. That is the invariant I intended, not a stronger one.
- **A11, pending entries:** `test_no_pending_step_left` assumes the FINAL sheet leaves no `pending` value mentioning "step 3" or "step 4".
- **A12, the last golden:** `test_golden_committed_sheet_is_the_final_output` skips with a reason until the implementer commits the regenerated sheet.

No commits, pushes, resets or history rewrites; no files written outside the copy's test directory.
