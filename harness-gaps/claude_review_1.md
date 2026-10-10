# Claude cold review 1: harness-gaps diff (handoff item 4 + Codex review 10 residuals)

**Scope note.** The working tree changed while I was reviewing. `provenance.portable_path`/`expand_portable` were rewritten from `root+sep in v` to a boundary regex (provenance.py:1182-1210, marked "cold review 1, B1"); `tests/test_run_agentbench_os.py` and `tests/test_serving_state_drivers.py` were edited; `test_runtime_portable_paths.py` gained two boundary tests. This review covers the tree as of mtime 17:41. All 8 touched test files pass (104 tests), and so do 15 neighbouring files (492 tests: provenance, agentbench_os, vision_gate, run_capacity, m50, opencode probe, tune).

## Verdict: SHIP-WITH-RESIDUALS

I found no blocking correctness bug. All five rulings (a)-(e) are implemented as described. The ExitGuard interaction is sound. No consumer chokes on the new row keys.

Verified non-findings:
- `return 3` inside `with guard:` (run_retrieval.py:72/155, run_reasoning.py:152/307, run_capacity.py:98). With `__exit__(None)` and `_verified=False`, `verify()` runs (provenance.py ExitGuard.__exit__). With no drift, rc 3 stands and nothing is quarantined. Nothing is tracked yet at the preflight, and capacity's tracked destinations do not exist yet, so `_quarantine` skips them. With drift, ServedConfigError replaces rc 3 and the staged `.pending` result, journal and sidecar are set aside. That is correct.
- At exit-gather failure, reasoning keeps `partial.jsonl` and `.provenance.json`, so `--resume` recovers the rungs.
- The preflight is cheap and has no result-side writes. It does safetensors header reads (quant_info.py:43-48) plus `git submodule status`/`ls-tree`/`diff --quiet` subprocesses (provenance.py `_git_shas`, `_registry_state`). Its manifest is discarded.
- Path-valued runtime keys (`transcripts_dir`, `corpus`, `exclusions_path`) are not in `_FINGERPRINT_RUNTIME` (provenance.py:293), `RESUME_IDENTITY_KEYS` (run_agentbench_os.py:302), `_MUST_MATCH_RUNTIME` (compare.py:60) or agentbench_compare.py:66-79. So placeholder conversion cannot cause false STALE results, resume refusals or `--clean-stale` deletions. The only path read-back is run_agentbench_os.py:189-193, and it expands.
- I found no strict row-key whitelist in rowschema.py or the capacity consumers, so the new `sdpa`, `content_sha256` and `reasoning_sha256` keys are additive.
- Substring safety: `/Users/xy/ws`, `/backup/Users/x/ws` and `$HOMEwork` stay untouched; `cwd=/Users/x` and `"/Users/x/a"` are converted. I checked this in an isolated interpreter.
- Capacity still publishes its scorecard without a manifest at rc 1 when the exit gather fails (run_capacity.py:167-187). The ruling scoped this out, and the fresh-out-tag refusal (run_capacity.py:86-87) means no older manifest can be mixed in.

## Findings

**B1: MEDIUM. Boundary regex misses some leak shapes.**
- Location: provenance.py:1182-1183, 1213-1218. VERIFIED by running against HOME=/Users/x.
- Failure: these strings pass through unchanged:
  - `file:///Users/x/ws/a`
  - `//Users/x/a`
  - `/Users/x.` (an error message ending in a period)
- The old `_scrub` (plain `replace`, provenance.py:1154-1162) would have caught all three.
- `_portable_deep` also leaves dict KEYS unscrubbed (`{'/Users/x/k': ...}` keeps the key). It passes `os.PathLike` through unscrubbed, and run_reasoning.py:134 `json.dump(..., default=str)` would then persist the raw path.
- No current caller hits these shapes (all use `str(...)`), but the "central guarantee" claim in the `_runtime_block` comment (provenance.py:1511) is stronger than the code.
- Fix:
  - BEFORE = `(?<![\w.\-~$])(?<![\w.\-~$]/)`. This still rejects `/backup/Users/x`, and accepts `file:///` and `//`.
  - AFTER: add `|\.(?!\w)`.
  - In `_portable_deep`: apply `os.fspath` to PathLike values and scrub keys.

**B2: LOW-MEDIUM. `expand_portable` leaves an unresolvable placeholder literal, which becomes a relative write path.**
- Location: provenance.py:1200-1210, run_agentbench_os.py:193.
- VERIFIED: with no STACK_WORKDIR env and no config.sh declaration, `expand_portable("$STACK_WORKDIR/m54/...")` returns the literal string.
- `Path(...)` of that string is relative. `confine_path` (paths.py:110-118) resolves it against the cwd, and the repo root is an allowed root. So a resume launched from the repo root with an explicit `--transcripts-dir` (which skips the `required=True` at run_agentbench_os.py:171-172) would write into `<repo>/$STACK_WORKDIR/...`.
- Reachability (ASSUMPTION): it needs the original run to have had STACK_WORKDIR set and the resume shell to have none. I did not check whether AgentBench's other components demand the workdir first.
- AGENTS.md says missing redirection is a blocker.
- Fix: `expand_portable(v, strict=True)` raises `MissingWorkdirError` if a bounded placeholder survives, or `run_transcripts_dir` refuses a result that still starts with `$`.

**B3: LOW. Docstrings say "display only" for something that drives a write target, and it bypasses the conftest trap.**
- Location: provenance.py:1171, paths.py:73-76. VERIFIED.
- Both say `resolve_stack_workdir` is "display only, never a write target". But `expand_portable` uses the same roots to build the AgentBench transcripts write directory.
- The conftest trap wraps only `paths.stack_workdir`. A test that follows the trap's own advice ("monkeypatch ... paths.stack_workdir") without setting the env gets the operator's REAL workdir from config.sh inside `expand_portable`. Only `confine_path` stops the write.
- Fix: `expand_portable` resolves through `paths.stack_workdir(required=False)` (trapped); only `portable_path` uses the untrapped resolver. Correct both docstrings.

**B4: LOW-MEDIUM. "The ladder is not lost" has no supported recovery path for retrieval, and a manual re-gather would carry false provenance.**
- Location: run_retrieval.py:148-155, run_reasoning.py:300-307, provenance.py:596-605. VERIFIED: no code handles `.pending-` files (repo-wide grep).
- A re-gather after the fact stamps the git, registry and router state of the re-gather time, not the run's. That is exactly the false-provenance case AGENTS.md M50 says to archive.
- The preflight manifest, which IS the run's entry provenance, is computed and thrown away at all three call sites.
- Leftover `.pending-<pid>` files accumulate.
- Fix: keep the preflight return value. On exit-gather failure, stage it as `<stem>.manifest.json.pending-<pid>` with `provenance_source: "preflight"` and `result_sha256`. Alternatively, document that retrieval must be rerun and reasoning recovered with `--resume`.

**B5: LOW. `content_sha256` in generate rows means something different from the same key in parity_replay, and inline thinking is in neither digest.**
- Location: generate.py:561-562 vs parity_replay.py:109; client.py:87, 141. VERIFIED.
- generate digests `strip_thinking(content)`, which also `.strip()`s whitespace. parity_replay digests the RAW content, and its reasoning falls back to `reasoning_content`; client.probe reads only `reasoning`.
- A cross-tool identity check reports false differences. A generate-only check misses changes in boundary whitespace and in inline `<think>` text. The new test itself digests `<think>tt</think>`, and "tt" is in neither digest (test_generate_run.py new test).
- Empty reasoning gets sha256("") rather than null.
- Ruling (c) approved the persisted-content semantics. Residual fix: add `raw_content_sha256` over `p["content"]`, or rename the key, and record `reasoning_sha256: None` when there is no reasoning.

**B6: LOW. Stale comments and dead branches.**
- Location: run_retrieval.py:135-137, 159, 165; run_reasoning.py:285-287, 311, 319. VERIFIED.
- The comments still say "best-effort, never lose a finished ladder to a provenance failure".
- `man = None` and `if man is not None` are now always true at the point they are tested, because the except branch returns. They mask the `publish_pair` precondition (provenance.py:720-721: "must not reach ... with manifest_stage=None").
- Fix: delete the stale comment and replace the guards with `assert man is not None`.

**B7: LOW. Test quality.** VERIFIED by running the new tests against a `git archive HEAD` copy. 20 fail on HEAD, as they should. Remaining gaps:
- `test_pair_publication.py:143` (`test_manifest_write_failure_leaves_the_old_pair_and_only_pending_files`) PASSES on HEAD. It pins existing behaviour; it is not a fail-first test for B3. It also leaves an empty `*.manifest.json.pending-<pid>` that it does not mention.
- The gather stubs treat "call 1 = preflight". In test_exit_guard_drivers.py `_late_serving_state_boom` nothing asserts that the ladder ran before the raise. test_serving_state_drivers.py does assert this (`ladder_calls == [1]`). Copy that assert.
- The capacity entry-refusal case (test_serving_state_drivers.py:153) checks only rc and the ladder. Add `assert not out_dir.exists()` to cover "nothing created".

**B8: LOW. The preflight does not fully mirror the exit path.**
- Location: provenance.py:604-605; run_capacity.py:157-164, 179. VERIFIED.
- The preflight uses a different runtime, has no overrides, and never serializes. Capacity's exit write uses `allow_nan=False`, so a NaN or non-JSON value fails only at the end.
- The error text "the end-of-run manifest could not be written either" (provenance.py:609-610) is an inference, not a fact.
- Fix: `json.dumps(man, allow_nan=False)` inside `preflight_gather`, and soften the message.

**B9: LOW. Perf.**
- Location: provenance.py:1165-1218. VERIFIED.
- `_placeholder_roots()` re-reads and re-parses config.sh for every string in `_portable_deep` when STACK_WORKDIR is not exported. That means hundreds of reads for an AgentBench runtime that has `image_ids` or `pilot_ids` lists.
- Fix: compute the roots once per `_portable_deep` call.

Out of scope, as the brief says: an M50 check for `run_dsh_probe.py` (run_dsh_probe.py:453-466 still gathers best-effort without a router block).
