Reviewed `f70fdcd` / implementation `c67769e`. **V2 passes, but I would hold V3.** Repository unchanged; adversarial fixtures are under `$TMPDIR`.

1. **P1 — BLOCKER: H1 can kill an unrelated operator shell.**  
   [proc_guard.py:414]($STACK_REPO/benchmark/bench/proc_guard.py:414) excludes only the probe’s ancestors/session. At [line 439]($STACK_REPO/benchmark/bench/proc_guard.py:439), cwd/argv matching alone authorizes killing another process, regardless of its age or ownership. A pre-existing shell in another terminal session, cd’d into scratch, was killed in the isolated fixture. Router/worker identities have no explicit protection either, although their usual paths should not match.

   **Fix:** protect pre-existing processes, operator sessions, and router/worker identities explicitly. Treat ambiguous path-only attribution as cleanup uncertainty, rather than permission to kill.

2. **P2 — MAJOR: interruption between spawn and registration leaks the child.**  
   [proc_guard.py:338]($STACK_REPO/benchmark/bench/proc_guard.py:338) calls `Popen` before registering ownership, without deferring termination signals. If SIGTERM/SIGINT intervenes, cleanup has no tracked entry. Because the child inherits the probe’s session, the sweep then excludes it at line 435. My acquisition-interruption fixture reproduced this leak.

   **Fix:** defer signals across process creation and registration, then deliver the pending termination after ownership is established. Keep a fallback handle that cleanup can terminate if registration fails.

3. **P3 — MAJOR: a watchdog-killed client can bypass cancellation until after export and grading.**  
   The main loop exits immediately when `proc.poll()` observes the watchdog’s kill ([tg1_runner.py:337]($STACK_REPO/benchmark/bench/tg1_runner.py:337)). The post-loop branch merely records `client_resource`, then exports ([line 405]($STACK_REPO/benchmark/bench/tg1_runner.py:405)). Descendant cleanup and cancellation occur in `finally`.

   The fixture observed **`export → cleanup → cancel`**. An opencode server descendant can therefore continue generation while the probe exports incomplete evidence, turning a scored resource outcome into a reconciliation abort. Kill-time diagnostics also remain unset.

   **Fix:** route every client-kill outcome through one termination path: record diagnostics, kill owned client/model descendants, await worker cancellation, then drain/export/reconcile.

4. **P4 — MAJOR: §3a reconciliation accepts incomplete terminal evidence.**  
   [token_turn_gate.py:387]($STACK_REPO/benchmark/bench/token_turn_gate.py:387) accepts any truthy `finish` for an unmatched normal final message. Consequently, rc=0 plus `finish="tool-calls"` is accepted as normal completion. The finished-session restriction exists only for `client_exit_hang`.

   Separately, [line 400]($STACK_REPO/benchmark/bench/token_turn_gate.py:400) checks that the active message exists in the export only for normal exits. A killed trace with `step_start(m2)` but an export containing only completed `m1` is accepted as `stalled`. Both cases reproduced.

   **Fix:** validate the terminal session state for normal exits, and require an observed active message to reconcile to the permitted interrupted/completed trailing message after a kill. Abort when that evidence is missing.

5. **P5 — MAJOR: Go `TestMain` detection has false negatives and false positives.**  
   The regex at [structured_grade.py:115]($STACK_REPO/benchmark/bench/structured_grade.py:115) misses legal syntax:
   ```go
   func /* comment */ TestMain(m *testing.M) { m.Run() }
   ```
   Conversely, a harmless comment containing `func TestMain(` marks the snapshot tampered. Both reproduced. This violates §3’s forbidden-addition rule and can incorrectly fail legitimate solutions.

   **Fix:** detect top-level declarations with a Go lexer/parser, ignoring comments and string literals. Test both examples, including additions to an existing solution file.

6. **P6 — MINOR: malformed tool events can become scored K stops.**  
   [token_turn_gate.py:307]($STACK_REPO/benchmark/bench/token_turn_gate.py:307) checks the tool name and input presence but never validates completion status. Eight `tool_use` events with `state.status="running"` produce `looping`, rather than §2’s `TransportAbort`.

   **Fix:** validate the pinned completion/error event projection before updating K. Add malformed-status and malformed-state tests.

7. **P7 — MAJOR: scoring dependency changes can retain identical code/policy identities.**  
   The hash allowlist at [tg1_runner.py:202]($STACK_REPO/benchmark/bench/tg1_runner.py:202) excludes `bench/convergence.py`, although that module determines every resolved budget and `budget_hit`. Substituting its source bytes left **both hashes unchanged**. Resume checks at [line 662]($STACK_REPO/benchmark/bench/tg1_runner.py:662) therefore cannot detect this scoring change through those identities.

   **Fix:** hash scoring dependencies, especially `convergence.py`, and add mutation tests proving that changing the clamp changes identity and refuses append. Audit the remaining transitive scoring dependencies.

8. **P8 — MINOR: the internal heartbeat does not satisfy live-run watch requirements.**  
   [tg1_runner.py:382]($STACK_REPO/benchmark/bench/tg1_runner.py:382) prints gate state only while the client is alive. It provides no mean-based ETA, token distribution, correction assessment, or heartbeat during terminal grading/cancellation. No independent watch daemon is launched here.

   Using the existing watcher unchanged also misreports convergence: [bench_watch.py:159]($STACK_REPO/benchmark/m1/bench_watch.py:159) counts only `converged is False`, while tg1 rows emit `nonconv_kind` without `converged`.

   **Fix:** wire a tg1-aware daemon into the V3/V4 launcher, covering terminal phases and interpreting every non-null `nonconv_kind` as non-converged.

9. **P9 — MINOR: abbreviated legacy flags bypass refusal.**  
   Argparse permits abbreviations ([run_opencode_probe_v2.py:831]($STACK_REPO/benchmark/run_opencode_probe_v2.py:831)), but tg1 checks raw arguments against exact option names ([tg1_runner.py:521]($STACK_REPO/benchmark/bench/tg1_runner.py:521)). `--tick 1` was accepted as `tick_s=1`, then silently ignored.

   **Fix:** track explicitly supplied options after parsing, or disable abbreviation for tg1 without changing legacy behavior. Test abbreviated forms.

10. **P10 — MINOR: the frozen replay-manifest builder bypasses H3 and overwrite protection.**  
    [build_replay_manifest.py:60]($STACK_REPO/benchmark/m62/build_replay_manifest.py:60) directly overwrites the committed manifest with `write_text`. An interrupted invocation can truncate it; an accidental invocation replaces frozen evidence without refusal.

    **Fix:** use atomic replacement and refuse an existing destination by default. Make deliberate re-freezing explicit.

11. **P11 — MINOR: several V1 tests are weaker than their acceptance claims.**  
    The suite contains meaningful oracles—especially slow-grade scheduling, threshold boundaries, real pinned-client plugin feedback, and actual host allocation. These are the weakest areas:

    | Test | Plausible bug it misses |
    |---|---|
    | `test_f13_sweep_excludes_probe_ancestors_and_session` | P1: a pre-existing operator shell in another session. |
    | `test_cleanup_defers_second_signal` | P2: interruption during acquisition, before cleanup starts. |
    | `test_host_grader_and_aggregate_memory` | P3: watchdog state is correct, but runner cancellation ordering is wrong. |
    | `test_snapshots_consistency_exclusions_and_symlinks` | Removing the copied-manifest comparison: its simulated race changes **every** manifest, so A≠B still rejects. |
    | `test_f10_exact_fixture_outcomes` | Feeds expected reports directly into `criteria`; cannot detect broken event ingestion or gate behavior. The separate V2 replay supplies that oracle. |
    | `test_go_container_limits_registration_and_oom` | Checks flag presence and mocks OOM=true; wrong memory values or broken real OOM observation would pass. |

    **Fix:** add the corresponding counterexamples and lifecycle tests. For snapshots, specifically test **A=B but copied manifest differs**.

**P12 — Verification and conformance checked.**

- Targeted M62/configgen suites: **181 passed**.
- Existing v2 probe/provenance suites: **128 passed**.
- [Scratch adversarial fixtures]($STACK_WORKDIR/m62/tmp/v5a-review-5t0icpqa/test_v5a_adversarial.py): **7 failed**, reproducing P1–P6, with process effects mocked.
- V2 rerun: **exit 0, all eight criteria PASS**. All 374 valid historical passes remained unstopped; fixtures matched `looping@15`, `looping@22`, and book-store/no-stop.
- Frozen hashes matched: universe `4e3d88b6…`, replay manifest `c5312f4e…`; universe contains 43 items.
- Read-only Docker inspection found the ARM64 `aider-benchmark` image and no `mlxbench` containers. I did not rerun V1b or container allocation/OOM experiments.

I found no additional defect in charge→enqueue→check ordering, frozen pending-grade cohorts, sticky stops, cache/reasoning budget arithmetic, canonical K identity, three-manifest snapshot implementation, structured-final-grade/changed/untampered pass composition, live atomic row writes, H4 checks, per-attempt evidence naming, or legacy dispatch isolation. `client_exit_hang` correctly remains diagnostic with null `nonconv_kind`; `rr_report.py`-style strict scoring handles that correctly.

**Verdict: not ready. Fix P1–P7 and establish the watch coverage in P8 before V3.**