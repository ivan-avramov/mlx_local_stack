# Implementer report: S29 main-small, candidate 1 (K2 ack actor, V1 vision rubric)

Copy: `fe-s29d/impl/stack`. Baseline: `f8851c108a55053e1c6413efaa1eec186d0056ff`. Spec: `docs/specs/s29-main-small.md` v1.0.

## Status: implemented, NOT RUN, diff NOT EXPORTED

- **No test has run.** The permission layer refused every Python call in this session: `.venv-bench/bin/python`, `python3 -m pytest`, `uv run … pytest`, and even `python --version`. Nothing here was executed. I haven't confirmed that the new tests fail on the baseline or pass on the candidate.
- **`candidate-1.diff` was not written.** The `git add -A -- benchmark` call, the `git diff --cached …` call and `git status` were all refused. Nothing is staged. The changes exist only as working-tree edits in the copy.
- Still to do: run the named tests below and the export command from the brief.

## K2: re-check acknowledgement actor (`benchmark/bench/p426_wave2.py`)

- New `run` flags: `--recheck-ack-by {operator,designer}` (`RECHECK_ACK_ACTORS`) and `--recheck-ack-ruling <text>`.
- `recheck_ack_actor(a)` returns `(actor, ruling)`. It refuses (`fz.Refusal`) unless the actor is `operator` or `designer` and the ruling is non-empty. It never fills in a default actor.
- `check_args` now starts with `_check_recheck_ack_args`. The three flags must come together or not at all, so an incomplete ack refuses before the lock, before any leg and before any write ("nothing resumes").
- `ensure_recheck`, when the ack sha matches:
  - It calls `recheck_ack_actor` before writing anything. This guards callers that skip the CLI.
  - It records `rechecks.s1.ack = {sha256, at, actor, ruling}`.
  - It logs `RE-CHECK s1: <outside|operator review>, acknowledged by the <actor> under <ruling> (<sha16>)`. The old line always said "outside, acknowledged by the operator". It now gives the actor it was handed and the real state.
- An `ack` already recorded, with or without an actor (the S29-P13 shape), returns at once as before. It is never rewritten, even when a new ack with an actor is passed.
- The rc 5 stop message now names the two new flags. The docstring is updated.

## V1: KV vision rubric (`benchmark/bench/p426_panel.py`)

- **Judgement call: I added a new rubric instead of editing `vision`.**
  - New key: `RUBRICS["kv-vision"]`. It asks for accuracy, coverage and precision against the image itself and mentions no captions or references.
  - `KV_MEMBER_RUBRIC["A3"]` now points to `"kv-vision"`, so a new A3 export binds the new text and its own `rubric_sha256`.
  - `RUBRICS["vision"]` stays word for word. The frozen stage-3 A3 record is bound to it (sha `5987d169…97b8`). The non-KV P426 B3 `vision` axis (`AXIS_RUBRIC`) also uses it, and that axis is outside this spec.
  - The alternative is to rewrite `vision` in place and keep the old text in a history table. That would also change the P426 B3 axis.
- `KV_FROZEN_RUBRICS = {"A3": (("vision", "5987d169…97b8"),)}` pins the one older `(rubric, sha)` pair a member's frozen record is allowed to carry.
- `_kv_rubric_ok(member, rubric, sha)`, used by `_kv_check_manifest`:
  - The rubric must be known, and the recorded sha must equal the sha of that rubric's current text.
  - The pair must then be either the member's current rubric or the pinned frozen pair.
  - A side effect: an unknown rubric name used to raise `KeyError` and now refuses cleanly.
- Frozen records under `benchmark/results/m76/panel/` are untouched.

## Tests

New tests (in `benchmark/bench/tests/`):
- `test_s29d_impl_k2_ack.py`:
  - success path, both actors: the record has actor and ruling, and the log names the given actor and not the other one;
  - missing actor or ruling (5 cases) refuses, with the bytes of `sequence.json` unchanged, no `ack` written and no ack log line;
  - the CLI refuses incomplete flag sets (4 cases) and a bad actor choice;
  - a legacy actor-less ack stays as recorded and is accepted on resume, with or without new ack flags.
- `test_s29d_impl_v1_vision.py`:
  - the new A3 text has no caption or reference clause and asks for accuracy, coverage, precision and the image;
  - a new export's sha is the new text's sha, which differs from the frozen one;
  - the frozen A3 record passes `kv_check_frozen`, and `kv_ingest` rows carry the frozen sha;
  - the other frozen KV members (A1, A2, A4, A5, A7-s1..s3) still pass `kv_check_frozen`.

Existing tests changed because they pinned the old behaviour:
- `test_m76_b4b1_impl_wave2.py::_seq`: when an ack is passed it now also passes `recheck_ack_by="operator"` and `recheck_ack_ruling="test ruling"`. This affects `test_an_unrealisable_recheck_stops_with_rc_5_until_acked` and `test_l3_an_outside_sealed_file_without_its_record_still_stops_until_acked`.
- `test_m76_b4b1_fe_fix1.py::_sequencer`: the same change. This affects `test_l3_state_file_without_record_outside_still_needs_the_ack`.
- `test_m76_b3_impl_panel.py:32`: `kv_rubric("A3") == "vision"` became `== "kv-vision"`.

Tests to run, all NOT RUN (from `benchmark/`):
- the two new files: `test_s29d_impl_k2_ack.py`, `test_s29d_impl_v1_vision.py`;
- the three edited files above;
- the modules that import `p426_wave2` or `p426_panel` (about 47 more test files, including `s26_frozen/`, `s29_frozen/` and `p613s4/`; grep `p426_wave2|p426_panel` under `bench/tests`);
- `p426_signals*`.

## Risks for the reviewer

- **Brief vs. spec.** The spec says "the KV `vision` rubric". I kept the P426 B3 `vision` text as it is. If P426 vision packets also carry no captions, that rubric has the same false clause. That would be a separate proposal.
- **Assumptions only a run can confirm:**
  - The frozen sha `5987d169…` equals the sha of the current `vision` text. The A3 packets contain that text, but I couldn't hash it.
  - The A1–A7 frozen records pass `kv_check_frozen` on the baseline.
- **Ruling is free text.** It is checked to be non-empty, with no C-number format check.
