**P16 — REVISION 4 implementation is present, but acceptance is incomplete.** No live inference, serving changes, or commits were made. I did not edit the protected files. Concurrent commit `42ff111` advanced the spec and replay manifest to REVISION 5; those changes are not implemented here.

**P17 — Validation**

- Full benchmark and configgen suites: **3,861 passed, 2 failed, 1 xfailed**. [Full log]($STACK_WORKDIR/m62/tmp/m62-final-suite-v2.log)
- M62, unchanged legacy-v2 tests, and configgen: **334 passed, 1 failed**.
- `configgen check` and `git diff --check` pass.

The failures are:

1. `test_real_tg1_preflight_proves_both_plugins`: native `/api/config --standalone` returns before `toolbounds.js` finishes loading. The pinned config handler does not await plugin activation. Production correctly refuses; I did not add a speculative workaround. Isolated real-client tests prove all three bounds produce model-visible feedback, exact rejection counts, and session continuation.
2. Existing `test_real_dsh_closed_port_escalates_transport_failure_and_writes_no_row`: its fixture leaves `STACK_WORKDIR` pointing outside its temporary directory, triggering the existing test safety guard.

**P18 — Files changed/added**

Modified:

- [run_opencode_probe_v2.py]($STACK_REPO/benchmark/run_opencode_probe_v2.py): isolated tg1 dispatch.
- [provenance.py]($STACK_REPO/benchmark/bench/provenance.py): scoped plugin verification.
- [modelnames.py]($STACK_REPO/benchmark/bench/modelnames.py): generated-carrier exemption.
- [opencode.py]($STACK_REPO/configgen/emitters/opencode.py) and [targets.py]($STACK_REPO/configgen/targets.py): tg1 target.

Added:

- [token_turn_gate.py]($STACK_REPO/benchmark/bench/token_turn_gate.py)
- [structured_grade.py]($STACK_REPO/benchmark/bench/structured_grade.py)
- [proc_guard.py]($STACK_REPO/benchmark/bench/proc_guard.py)
- [tg1_runner.py]($STACK_REPO/benchmark/bench/tg1_runner.py)
- [universe_preflight.py]($STACK_REPO/benchmark/m62/universe_preflight.py)
- [replay.py]($STACK_REPO/benchmark/m62/replay.py)
- [toolbounds.js]($STACK_REPO/benchmark/opencode_plugins/toolbounds.js)
- [opencode_bench_v2_web_tg1.json]($STACK_REPO/benchmark/opencode_bench_v2_web_tg1.json), regenerated through configgen.
- Eight test files identified below. Existing tests were not edited.

**P19 — REVISION 4 §6 V1 coverage**

Test names below omit the common `test_` prefix.

| Requirement | Tests |
|---|---|
| Exact thresholds, precedence, sticky stops, boundary reset, pending grades | `exact_thresholds`; `precedence_sticky_boundary_reset_and_backlog`; `k_and_ceiling_skip_unnecessary_grading` |
| Fragmented input, duplicates, malformed input, draining, parallel-tool order | `fragmented_utf8_json_terminal_drain`; `ingestion_refuses`; `duplicate_tool_call_id_different_projection_rejected`; `parallel_tools_completion_order_and_tool_free_request` |
| Slow grading, exit during grading, final-request crossings | `slow_grading_backlog_and_exit_during_grade`; `final_request_k_crossing`; `terminal_normal_final_usage_charged_once_and_final_ceiling` |
| Cache-aware budgets, exact boundary, invalid usage, ID mismatch | `cache_budget_boundary`; `missing_bool_negative_usage`; `terminal_other_states_abort`; `carrier_budget_context_and_metrics_refusal` |
| Every terminal-table outcome | `terminal_normal_final_usage_charged_once_and_final_ceiling`; `terminal_kill_backlog_and_interrupted_last`; `terminal_context_overflow`; `terminal_other_states_abort` |
| Panic, build/collection errors, timeout, infrastructure failure | `go_leaves_panic_mid_suite_and_build_error`; `python_collection_error_and_tuple_ids`; `grader_timeout_counts_unreported`; `infrastructure_failure_aborts` |
| Equal-count changes, alternating drafts, ungradeable/inconsistent snapshots | `equal_count_alternating_tampered_ungradeable_never_progress`; `snapshots_consistency_exclusions_and_symlinks` |
| Protected edits and every forbidden addition | `protected_edit_delete_and_helper_allowed`; `each_python_forbidden_addition`; `each_go_forbidden_addition`; `empty_vendor_and_testmain_in_existing_solution`; `snapshot_retains_forbidden_empty_directory`; `tg1_protected_final_edit_fails` |
| Silence and cancellation | `silence_observations`; `silence_tracks_shell_ancestry_not_opencode_server`; `cancellation_summary_and_timeout` |
| H1 detached processes, rapid escape, repeated signals, unstarted container | `real_detached_child_and_host_grader_allocation`; `real_rapid_fork_detach_chdir_is_attributed_or_diagnostic`; `cleanup_defers_second_signal`; `container_never_started_removed_and_verified` |
| H2 host allocation, aggregate pressure, monitor death, container OOM | `real_detached_child_and_host_grader_allocation`; `host_grader_and_aggregate_memory`; `monitor_death_aborts`; `go_container_limits_registration_and_oom` |
| H3 interrupted writes | `interrupted_atomic_write_and_torn_loader` |
| H4 identity and exact item set | `identity_drift_append_and_exact_items`; `mocked_tg1_rows_evidence_resume_and_worker_drift` |
| Immutable evidence | `immutable_evidence_refuses`; `mocked_tg1_rows_evidence_resume_and_worker_drift` |
| Real plugin feedback, continuation, rejection counts, denied tools | `real_toolbounds_feedback_continuation_and_exact_count`; `real_subagent_and_code_mode_denied` |
| Title/compaction, plugin isolation, legacy isolation | `tg1_destination_both_plugins_and_policy`; `tg1_web_plus_subagent_only_and_daily_untouched`; `legacy_never_constructs_tg1` |
| Real preflight plugin proof | `real_tg1_preflight_proves_both_plugins` — **blocked/failing** |

These reside in `benchmark/bench/tests/test_{token_turn_gate,structured_grade,proc_guard,tg1_provenance,tg1_runner,tg1_integration}.py` and `configgen/tests/test_opencode_tg1.py`.

`benchmark/bench/tests/test_m62_tools.py` additionally tests universe mapping/baselines/freezing, hash refusal, replay ingestion, and replay criteria using small fixtures.

**P20 — Remaining lead work**

- Resolve plugin readiness proof before using tg1.
- Align implementation with REVISION 5. The original REVISION 4 manifest lacked final-request usage; `replay.py` refuses to certify incomplete accounting. The concurrently added export hashes now permit implementing the revised reconciliation contract.
- Update documentation, handoff, and AGENTS.md M50 wording.
- Run the full 43-item V1b preflight with Docker, then the completed V2 replay.
- Complete V5a before V3/V4. **This state is not ready for live tg1 runs.**