I've read all the material. Here is the verification.

## Disposition of the opinion's findings

**1. Registry TOCTOU — RESOLVED.** `drive` reads the registry once right after the lock (`qualify.py.txt:1051-1052`), stores it in `snapshot["text"]/["sha256"]`, and `_drive_locked` uses only `snapshot` (`:1178-1179`). A later change is caught two ways: `binding_problems` re-reads `main_models.yaml` via `sha256_file` and compares to `registry_sha` (`:951`), and `guard_problems` compares the stack HEAD to `snapshot["start"]` (`:1179`, `:688-701`). Both add problems that block the job (`if not problems:` at `:1262`). Tests `test_r1_a_registry_flipped_on_after_the_gate_refuses` (three hooks) and `test_r1_a_registry_changed_between_the_gate_and_execution_refuses` confirm.

**2. `served_on` MTP-ON not bound to the certified configuration — RESOLVED.** `certified_argv` reads `manifest.json`'s `picks[name].argv_on` (`:199-207`); `entry_problems` refuses when it is None (`:308-310`); `_drive_locked` runs `argv_binding_problems(name, snapshot["certified"][name], cmd[1:])` for every MTP-ON arm (`:1260-1262`), and `argv_binding_problems` names the first differing flag (`:212-223`). `snapshot["certified"]` is captured once in `drive` (`:1133-1137`), so the run binds against one read. Tests cover equal-argv pass, four differing-flag refusals (incl. a restored drafter), and a missing-`argv_on` refusal.

**3. Production comparison direction / short vs full shas — RESOLVED.** `_production_matches` resolves the summary's ref via `_full_sha` and compares to the run's resolved full sha (`:189-196`); `drive` resolves the run's production (default included) via `orchestrate.resolve_production_ref` (`:1063-1066`). Tests `test_r1_a_short_summary_matches_a_full_run_ref`, `test_r1_a_full_summary_matches_a_short_run_ref`, `test_r1_a_summary_on_another_commit_refuses`, and the unresolvable-default/summary cases pin both directions.

**4. Registry names used as filesystem paths — RESOLVED.** `safe_id` (`:968-972`) sanitizes to `[A-Za-z0-9._-]` and appends sha8; `out_path` (`:974-979`) verifies the resolved path stays under `--out`. All three path sites go through `out_path` with `safe_id` (`:1242`, `:1248`, `:1470`). `test_r1_per_entry_paths_use_a_safe_id_under_out` covers `org/Model`, `/abs/Model`, `../Model` for both `served_off` and `mtp_off`.

**5. `mtp_off` removal regex too narrow / misleading refusal — RESOLVED.** `mtp_off_registry` now uses YAML node marks (`:113-138`), refuses flow-style blocks (`:128`), names the key and its 1-based line (`:121`, `:149-152`), and guards against shared-line content (`:135-138`). Tests cover quoted keys, indented blocks, and a flow-style refusal naming `draft_kind`.

**6. "Served ON" by key presence — RESOLVED.** `serves_mtp` returns `expected_config(entry)["drafter"]` and raises on a partial / non-MTP block (`:62-72`). Tests `test_r1_a_partial_or_non_mtp_draft_block_refuses` covers no-draft-model, scan-only, and non-mtp-kind.

**7. `arm_for` restore without `name in registry_state` — RESOLVED.** `arm_for` checks `name not in registry_state` and raises (`:91-95`). `test_r1_arm_for_refuses_a_restore_when_the_name_is_not_off_in_registry_state` covers it.

**8. `rates` on a FAILED entry untested — RESOLVED.** `test_r1_a_failed_entry_with_a_record_carries_rates_and_arm` pins it; the code path (`:1316-1317`) records `arm`/`rates` whenever `rec` exists.

**9. Style slip — RESOLVED.** `repair.diff` fixes `pre =orchestrate.preflight` → `pre = orchestrate.preflight` (`:380` of the diff).

## Anything else the diff breaks or leaves failing

**F1 — `argv_binding_problems` raises an uncaught `TypeError` when `certified` is `None` (minor; hypothesis).**
`qualify.py.txt:214` does `if list(argv) == list(certified):` with no None-guard. `certified` comes from `snapshot["certified"][name]` (`:1133-1137`), which is `certified_argv(...)` — documented to return `None` when the manifest is absent/malformed (`:199-207`). `entry_problems` refuses a `None` certified argv before the run (`:308-310`), and `snapshot["certified"]` is built right after, so in the normal flow the value is a list. But the manifest is read twice (once in `entry_problems`, once for the snapshot) with no snapshotting; if the manifest is removed/corrupted between those two reads, `snapshot["certified"][name]` becomes `None` and `_drive_locked`'s `argv_binding_problems(name, None, cmd[1:])` raises `TypeError: 'NoneType' object is not iterable`. The outer `except Exception` (`:1297-1299`) catches it, so the entry is FAILED (not COMPLETED) — no wrong measurement — but the error message is opaque and the gate's specific message is lost.
*Scenario:* between `entry_problems` and the `snapshot` build, an external process truncates `manifest.json`; the run reports `TypeError: 'NoneType' object is not iterable` instead of `<name>: its P369 manifest.json has no picks[<name>].argv_on`.
*Proposed change:* guard in `argv_binding_problems`: `if certified is None: return [f"{name}: {CERTIFIED_DIFFERS} (no certified argv)"]` (or read the certified argv once into the snapshot and reuse it in `entry_problems`).

**F2 — `summary_artifact_problems` runs before `argv_binding_problems`, so a stale manifest can mask a configuration drift (minor; hypothesis).**
In `entry_problems`, `artifact(path, summary)` (the campaign-artifact check, `:307`) and the `certified_argv` check (`:308-310`) both run before the run; the actual argv binding (`argv_binding_problems` in `_drive_locked`) reads `snapshot["certified"]`, captured once. The artifact check reads `manifest.json` a third time (`:325-328`). The manifest is thus read at least three times with no snapshot; the binding uses the second read. This is consistent for an immutable artifact, but the design repeats the spec's TOCTOU concern (finding 1) for the manifest without applying the same one-snapshot discipline. The binding is still trustworthy because `snapshot["certified"]` is the single value used during the run; only the pre-run gate's `is None` check is on a separate read.
*Scenario:* (contrived) the manifest is valid at the gate, replaced with a different valid `argv_on` before the snapshot build, then restored before the artifact check — the gate passes, the snapshot binds to the middle value, the artifact check passes. No wrong measurement results (the binding still enforces equality to whatever the snapshot captured), so this is a robustness nit, not a protection gap.
*Proposed change:* capture `certified_argv` once into the snapshot before `entry_problems` and pass that value to both the gate and the binding check.

NOTHING OF SUBSTANCE.
