Q1. Subagent counting and exclusion → `test_subagent_count_and_incomplete_row`.
Q2. A4 carrier SHA parity; M59 default retained → `test_a4_receipt_matches_probe_written_carrier`.
Q3. Reporters explicitly refuse web-audit rows → `test_compare_refuses_web_audit_rows`, `test_scoreboard_refuses_web_audit_rows`.
Q4. Hermetic auditor flags and versioned idempotence → `test_auditor_hermetic_flags`, `test_auditor_version_records_and_idempotence`.
Q5. Network-only denial counts and error messages → `test_web_denied_only_network_rejections_with_messages`.
Q6. Audit errors preserve legs and exclude rows; surrogate/null handling → `test_web_audit_exception_does_not_abort_leg`, `test_web_audit_surrogates_and_null_content`.
Q7. Python methods and adjusted threshold; Go methods retained → `test_preflag_methods_and_small_identifier_sets`.
Q8. Uppercase denies; M59 unchanged → `test_web_carrier_changes_only_ordered_permissions`, `test_real_code_search_denied`.
Q9. Expanded network detection and file-output exclusion → `test_network_package_commands_captured`, `test_network_output_file_incomplete`.
Q10. Retry latest audit errors → `test_retry_errors_uses_latest_record`, `test_retry_errors_cli`.

Q11. Benchmark: **3496 passed, 2 skipped, 2 warnings** in 330.83s.
Q12. Configgen: **76 passed**; `configgen check` passed; `uv.lock` restored.
Q13. `test_runserver_term.py`: verifier’s load flake noted; passed here, unchanged.
Q14. Open questions: none. No commit; `docs/handoff.md` untouched.