Revision 2 improves the design, but still leaves unsafe cleanup and cancellation paths and several acceptance criteria that can certify adjacent behavior. I read the first review and rechecked the code and tests. Read-only counterexamples confirmed the trigger and pilot mismatches below; I did not write files or run artifact-producing tests.

**P1 — not answered — blocker — §4 “Deletion authority,” lines 222–236.**  
The specification explicitly admits deleting a file another process created. Before/after listings, uid and birth time establish presence during the item, not creation ownership. An unambiguous `cat /tmp/new-file` can still authorize deletion of another application’s newly created file. Checking an opened inode also does not prevent replacement of the directory entry before `unlink`. Additionally, the top-level listing supplies no recorded inode for nested candidates. **Change:** automatically delete only objects with actual creation ownership in a probe-owned namespace. Keep other paths diagnostic and untouched. Add unrelated-creator and replacement-before-unlink tests; acknowledging this residual does not satisfy “never removes something it did not create.”

**P2 — partially answered — should-fix — §4 “Candidates,” lines 213–220; §7 V1.**  
Native `state.input.path` is correct. I verified the installed executable against [install_bench_opencode.sh:8](<repo>/scripts/install_bench_opencode.sh:8); its native edit/write schemas use `path`. However, `shlex.split` is not complete path extraction:

- `echo hi >/tmp/new` produces `>/tmp/new`, which is missed.
- `touch /tmp/new; echo ok` produces `/tmp/new;`, the wrong path.
- `python3 -c "open('/tmp/bench199_test.go','w')..."` hides the path inside a code token.
- Relative write/edit paths and shell paths require working-directory resolution.

**Change:** call shell extraction a best-effort diagnostic; register these cases and distinguish exact paths from uncertain mentions. Freeze and hash actual pinned-client export fixtures. None of this extraction should confer deletion authority.

**P3 — partially answered — blocker — §3 helpers and escalation, lines 124–127, 185–188, 200–204.**  
Removing the frozen watchdog and refusing to kill path-only processes answers the unsafe sweep concern. That agrees with [proc_guard.py:495](<repo>/benchmark/bench/proc_guard.py:495). But after SIGKILL, the runner checks only cwd/argv paths and container names. It cannot recover the guard’s tracked ownership of a descendant that subsequently changed directory, nor establish that the worker cancelled. Nevertheless, incomplete-block handling unconditionally unloads/reloads. **Change:** persist owned process identities, registered containers and cleanup status per attempt. Require verified probe termination, owned-resource clearance and readable worker-idle evidence before automatic restart. Failed cancellation or uncertain cleanup must terminate the chain for operator intervention.

**P4 — partially answered — should-fix — §3 cooperative cancellation and escalation, lines 168–188.**  
The new cooperative transition correctly distinguishes cancellation from the existing cleanup-only [SIGTERM path](<repo>/benchmark/run_opencode_probe_v2.py:821). Its deadline remains underspecified: the stated **1,445 seconds** assumes a 300-second cancellation bound, while a 240,000-token prompt requires 800 seconds ([proc_guard.py:144](<repo>/benchmark/bench/proc_guard.py:144), [test_m62_revision5.py:146](<repo>/benchmark/bench/tests/test_m62_revision5.py:146)). Cleanup, process waits and report retention are not explicitly accounted for. Cancellation detection outside the active-client loop is also unspecified. **Change:** define a computed deadline with explicit phase bounds and observed prompt provenance; specify cancellation checks before client launch and at terminal/item boundaries. Test cancellation during discovery, grading, export and cleanup—not just generation.

**P5 — answered — blocker in revision 1 — §3 cancellation decision, lines 178–182.**  
Consecutive fresh samples, event/row stagnation, worker identity, reset-on-change, unreadable-metrics refusal and immediate recheck address the original stale-heartbeat counterexample. They follow the existing [silence observer](<repo>/benchmark/bench/proc_guard.py:120). No additional change for this original finding; P17 identifies separate cancellation paths.

**P6 — answered — blocker in revision 1 — §3 schedule and incomplete block, lines 142–147, 200–204.**  
The experimental unit is now the entire model block, both languages share one worker identity, and restarting archives both legs while preserving items/seeds. Distinct identities across blocks are explicitly tested. This answers the mixed-instance objection.

**P7 — answered — should-fix in revision 1 — §3 STOP, lines 205–208; §7 V1.**  
STOP now latches, prevents further legs, archives partial evidence, consumes no restart and exits 3. The four requested lifecycle locations are registered. P21 separately concerns cancellation-file reuse.

**P8 — answered — blocker in revision 1 — §3 A4 gate, lines 129–135.**  
The design now explicitly selects the tg1 carrier, installs both plugins and checks receipt consumption against its carrier hash. Those changes address the current [web-only carrier selection](<repo>/scripts/session_pinning_gate.py:99), [CLI choices](<repo>/scripts/session_pinning_gate.py:239) and [receipt SHA requirement](<repo>/benchmark/run_opencode_probe_v2.py:793). P17 concerns the inherited gate’s timeout behavior.

**P9 — partially answered — should-fix — §2 policy, prompt and predicates, lines 29–63.**  
Noncompliance classification and fixed retry seeds improve the design. Two claims remain wrong:

1. Lowering one threshold cannot guarantee that other conditions do not fire first. Executing the current gate with `N=4` and an initial 81,920-token completion stops at request **1**. The proposed stall PASS predicate accepts this, without proving the lowered request threshold.
2. Native shell input is not necessarily exactly `{command, workdir}`. The SHA-verified executable’s schema also permits `timeout` and `background` at byte offset **136622888**. Equal command/workdir with differing optional fields does not produce identical signatures; [token_turn_gate.py:90](<repo>/benchmark/bench/token_turn_gate.py:90) hashes the entire input.

**Change:** remove the guarantee; require the registered live crossing for the lowered threshold, treating an earlier token crossing separately. Request identical **full input objects**, and independently derive signatures and crossings from raw events.

**P10 — partially answered — blocker — §2 “Causal evidence,” lines 65–75.**  
Kill records and a busy observation improve the evidence, but the stop positives require only a client kill; the allocation positive proves descendant killing separately. Thus all three can pass without proving C147’s combined **stop → owned-descendant kill → worker cancellation → reconciliation** path ([open-questions.md:20](<repo>/docs/open-questions.md:20)). A sampled busy worker followed by idle also permits natural request completion between observations. **Change:** require at least one stop positive with a tracked model descendant alive at stopping, verified descendant termination, and cancellation evidence linked to the same worker request/session. Register a negative case where the worker finishes naturally without cancellation.

**P11 — answered — blocker in revision 1 — §3 completion; §6 provenance, lines 189–199, 254–259.**  
The pinned campaign policy, explicit probe/client/carrier/universe identities, serving-path comparison, typed worker identities, retained return codes and driver/helper hashes address the original fingerprint objection. The existing [resume identity comparison](<repo>/benchmark/bench/tg1_runner.py:732) supports that approach. P19 identifies an additional per-leg schedule-validation omission.

**P12 — partially answered — should-fix — §5 retention, lines 242–251.**  
Copy-before-parse, both Go artifacts, stdout/stderr, sequence numbers and final-grade identification address most of the original finding. Exception handling remains undefined: malformed reports and missing runtimes raise `TransportAbort`, so no `Grade.artifacts` reaches the caller ([structured_grade.py:172](<repo>/benchmark/bench/structured_grade.py:172), [structured_grade.py:319](<repo>/benchmark/bench/structured_grade.py:319)). The ordinary abort manifest currently retains only an error ([tg1_runner.py:868](<repo>/benchmark/bench/tg1_runner.py:868)). Python output is captured as text, and timeout cleanup discards the final `communicate()` output ([proc_guard.py:400](<repo>/benchmark/bench/proc_guard.py:400)). **Change:** retain raw output from launch, and persist a hashed report index even when grading raises. Infrastructure failure must remain an abort, not become an all-failing grade. Require immutable replay-manifest bytes and unchanged per-fixture outcomes, not merely aggregate “8/8.”

**P13 — partially answered — should-fix — §7 V2/V3, lines 285–298.**  
The real-client cancellation test is useful, and marking live clearance pending is appropriate. But `run_item` does not write the manifest; its caller does. A `run_item` test cannot verify the actual CLI dispatch, outer abort handling or promised `cancelled_item` manifest retention. Existing [real-client tests already call the probe entry point through `tg_fixture`](<repo>/benchmark/bench/tests/test_tg1_integration.py:84). A live five-item pilot also does not exercise pilot→full resume, cancellation or restart. **Change:** test `p.main()` with the pinned client and mocked external boundaries, without adding any production M50 bypass. Register manifest/exit/row assertions and real-client loop/allocation cases. Explicitly keep clearance pending if any load-bearing test is skipped.

**P14 — answered — should-fix in revision 1 — §3 helpers, first-manifest check and watcher, lines 118–121, 155–164.**  
Voltage, strictly greater than 20% battery, token/convergence distributions and the required manifest fields are now explicit. P17 addresses whether the specified runner mechanism actually enforces the promised pre-item-two check.

**P15 — NEW — blocker — §2 contains two incompatible “Verifier” definitions, lines 77–83 and 98–107.**  
The second definition drops report-hash checks and stronger causal requirements, and restores the global `docker ... name=mlxbench-` check instead of the run-specific check. A build can follow the weaker definition and claim compliance. The driver also verifies each kind immediately, while cancellation proof is assessed across stall and loop together. **Change:** replace both blocks with one authoritative verifier contract. Define per-row checks, suite-level checks, exit codes, retryable outcomes and which retained attempts constitute the final clearance suite. Test that unrelated containers neither fail clearance nor become cleanup targets.

**P16 — NEW — blocker — §2 allocation predicate and instrumentation, lines 36, 63, 68–69.**  
The native shell adapter can represent a killed command as a **completed tool with exit/signal metadata**, rather than `state.status == "error"`. The pinned binary constructs this result at byte offset **136625958**, with metadata projection at **136622483**; its SHA matches [the install pin](<repo>/scripts/install_bench_opencode.sh:8). The indexing contract is also inconsistent: “completed requests at the kill” is a boundary count, whereas the carrying request is one-based ([token_turn_gate.py:100](<repo>/benchmark/bench/token_turn_gate.py:100)). If zero requests have completed, `requests_completed > 0` can mean only that the allocation request finished—not that a subsequent request occurred. **Change:** use an actual pinned-client killed-command fixture to register accepted failure evidence. Record separate `completed_boundary_at_kill`, owning message/tool-call identity and carrying request index. Require a distinct later request for continuation, and corroborate RSS against the effective threshold.

**P17 — NEW — blocker — §3 A4, first-manifest deadline, escalation and restart, lines 129–135, 155–159, 183–204.**  
Automatic busy-kill paths remain:

- A missing manifest after 120 seconds triggers cancellation without the idle/wedge predicate.
- The extracted A4 gate retains its fixed timeout and unconditional process-group SIGKILL ([session_pinning_gate.py:153](<repo>/scripts/session_pinning_gate.py:153)); the M59 wrapper also has an outer 1,800-second timeout ([run_m59.py:171](<repo>/benchmark/chains/m59/run_m59.py:171)).
- Escalation does not revalidate activity, and restart does not distinguish failed worker cancellation from a restartable incomplete block.

Also, asynchronously observing a manifest provides no barrier preventing a fast probe from reaching item two before validation ([tg1_runner.py:751](<repo>/benchmark/bench/tg1_runner.py:751)). **Change:** add a pre-generation manifest acknowledgement barrier. Make missing-manifest time an alarm while activity is present; give tg1 A4 an ownership-aware cancellation path; recheck automatic escalation conditions. Treat worker-health/cleanup failure as non-restartable. Keep explicit operator STOP distinct.

**P18 — NEW — should-fix — §3 pilot and execution, lines 148–154; §7 V2.**  
The execution rule assigns the leg’s full expected set to every invocation, but a pilot writes only five items. The real probe applies `--limit` before running and then validates the exact supplied expectation ([tg1_runner.py:606](<repo>/benchmark/bench/tg1_runner.py:606), [tg1_runner.py:866](<repo>/benchmark/bench/tg1_runner.py:866)). A five-row pilot with a 22-item expectation therefore fails; I reproduced that through `expect_items`. **Change:** specify the pilot’s exact five-item expectation and the full invocation’s full-language expectation separately. Test the actual argument vectors and successful resume into the same rows file.

**P19 — NEW — blocker — §3 `validate_leg`, lines 189–199.**  
Common runtime equality explicitly excludes `seed_base` and `lang`, but no separate requirement validates either against the scheduled leg. Nor does it require each row’s sampler seed to equal `rowschema.sample_seed(id, 0, expected_base)`. Two independently loaded sessions accidentally using seed base 1001 can satisfy every listed completion check, violating the distinct paired schedules in [AGENTS.md:46](<repo>/AGENTS.md:46). **Change:** pass an explicit leg descriptor containing model, language, session, seed base and expected ids. Validate manifest and row identities against it, including sample number, sampler seed and seed-overlay hash. Reject mutations of each field. Define startup resume eligibility so an aborted attempt cannot become clean merely through manifest replacement; the current [resume path](<repo>/benchmark/bench/tg1_runner.py:727) does not reject `transport_abort`.

**P20 — NEW — should-fix — §3 helpers, schedule and execution; §7 operational tests.**  
The proposed command omits the expressly required `--sampling-profile deployed`, which the current CLI does not expose ([run_opencode_probe_v2.py:842](<repo>/benchmark/run_opencode_probe_v2.py:842), [AGENTS.md:42](<repo>/AGENTS.md:42)). There is also no registered ten-minute idle interval/start-state capture between arms ([AGENTS.md:52](<repo>/AGENTS.md:52)). M59’s inherited load helper checks predictor argv, not the required worker environment ([run_m59.py:136](<repo>/benchmark/chains/m59/run_m59.py:136)). **Change:** explicitly expose/pass the deployed profile, register arm cooling/start-state capture, and verify router **and worker** environments. Test these instead of treating inherited helpers as sufficient.

**P21 — NEW — should-fix — §3 cancellation file and incomplete-block archival, lines 154, 168–182, 200–208.**  
The cancel path is reused as `<leg>.CANCEL`, but archival names only rows, manifest and log. An automatically cancelled attempt leaves its cancellation file behind; the restarted probe can immediately consume that stale file and kill a fresh client. **Change:** use a unique cancellation path per attempt, record its attempt identity and archive it with the attempt. Refuse stale cancellation state before spawning. Test cancellation followed by restart using the same logical leg.

**P22 — NEW — nit — §1 scope, line 11; §3 A4, line 129.**  
“All under `benchmark/`” contradicts the required edit to `scripts/session_pinning_gate.py`. **Change:** name that script as the explicit scope exception so implementation review has an unambiguous file boundary.

**redesign — revision must answer P1, P2, P3, P4, P9, P10, P12, P13, P15, P16, P17, P18, P19, P20, P21, P22.**