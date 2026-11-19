## Round-2 adopted findings — resolved status

**Sol P2 (erratum 11, v8 `declined_ok` row-hash) — RESOLVED.**
`bench/p426_freeze.py:84-92` `declined_ok` requires `hex64(ev.get("row_sha256"))` AND `ev.get("row_sha256") == entry.get("row_sha256")`. Since the evidence's `row_sha256` must be 64-hex and equal the entry's, the entry's is implicitly bound to the same 64-hex value; a missing/None entry hash fails the equality. `positives_problems` (line 776-778) accepts DECLINED only when `declined_ok(p)` holds. Confirmed in source.

**Sol P3 (erratum 12, tg2 campaign-core closure) — RESOLVED.**
`chains/c147/run_tg2_chain.py:44-47` adds `benchmark/bench/tg2_gradle_home.py` to `CORE_SPECS["probe_data"]` (tg2 only); tg1's `run_tg1_chain.py` is not in the diff, so tg1's closure is untouched. The designer's GLM R2-3 measurement confirms `probe_code_sha256` rotates (e9c487c1…→8a456ade…) while `scaffold_policy_sha256` is unchanged (f56705f9…), matching C178 and the B4b-1 tg1 golden passing unmodified.

**GLM R2-1 (erratum 13, `not_declined` documented) — RESOLVED.**
Spec erratum 13 documents the field; `p426_wave2.py` `cmd_positives` writes `entry["not_declined"] = he.portable(why)` when `why` is not None (diagnostic). Spec + code present.

**GLM R2-2 (erratum 14, flat fail-closed Stop messages) — RESOLVED.**
All guard Stop messages in `p426_wave2.py` are flat: `host_refusal` (line 459), `host_baseline` unreadable (line 444-445), `host_env_final` (line 503), `after_leg` host-INVALID (line 592). No "operator decides" / "operator decision" wording remains.

## Anything else the diff breaks or leaves failing

I traced the four adopted fixes and the surrounding new code (`host_env.py`, `tg2_gradle_home.py`, the sequencer guard, `positive_entry`/`decline_evidence`, the `inject_verify` alloc rule, `arm_opencode`/`arm_runner`/`run_config` identity wiring, bootstrap step 5b) and found no defect that fails the request's purpose or a real consumer:

- The sequencer's launch-region `try/except BaseException` re-raises after logging; `host_changed`/`cls` are only referenced on the no-exception path, so no `NameError`.
- `decline_evidence` enforces erratum 1 in full: `not_observed*` verdict, probe rc 0, `row_sha256` verifies, no kill (`mem_kills` + `termination.killed` both empty), evidence verifies (V3), no marker in any tool-call input. `declined_ok` (v8) re-checks the same facts against the entry's own `row_sha256`.
- The alloc rule (`inject_verify.py:262`) counts only EXECUTED shell calls carrying `bytearray(` (`never_executed` excludes tool-bounds-rejected calls) and requires exactly one whose `part_id` equals the kill's `tool_call_id`.
- `host_env_final` runs on both normal exits before publishing; a host-INVALID `Stop` from `after_leg` propagates without it, consistent with erratum 8 (leg-level diff already in `leg.json`/`sequence.json`; `main`'s `finally` publishes).
- `host_env_paths()` is added to `publish_run_files_or_stop` for both tg2 and non-tg2 corpora, so the baseline publishes with the run files.
- The test-writer's run reports 15227 passed / 0 failed and 202 frozen tests pass; the frozen-suite gaps the implementer noted (missing `src/mlx-vlm/dev/p369_phase2/pins.json` submodule, `host_env`/`arm_identity` single failures) are in code this round did not touch and are not caused by this diff.

One non-blocking coverage note (already raised by the test-writer, not a defect in this material): the first-run baseline write and the post-leg INVALID path have no frozen test. Acceptance criterion 1 covers them via mocked/temp-tree tests, which pass.

NOTHING OF SUBSTANCE
