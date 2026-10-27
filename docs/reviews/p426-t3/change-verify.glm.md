I have everything needed. Here is the review.

---

# P426 T3 candidate — strict verify (round 1 of 3)

## A. Findings adopted/adapted by the two design rounds — resolved in the candidate?

**R1-1 (ON from overlay → arms as commits).** Resolved. `p426_wave1.main` requires `--stack-root-off`/`--stack-root-on` under a label, refuses `--registry-on` (`p426_wave1.py:881–895`, `p426_leg.py:729–735`), each leg's `cwd` and `--stack-root` are its arm's worktree (`p426_wave1.py:925–931`), and the restore diff is asserted (`p426_plan.restore_diff_problems`). Confirmed in source.

**R1-2 (expected build per label in code).** Resolved. `EXPECTED_BUILDS["s2"]` is in code (`p426_plan.py:464–467`); `record_problems` refuses a record whose `mlx_vlm`/`mlx_serve`/`production_ref` differ from the label's expected, even when self-consistent with the trees (`p426_plan.py:559–572`). `test_a_self_consistent_record_of_another_build_refuses` covers it.

**R1-3 (labelled leg names, `.build` marker).** Resolved. `leg_name`, `tune_prefix`, `frozen_path`, `m1_out_dir`, `wave1_dir` all carry the label; `claim_out` writes/reads `.build` and refuses a mismatch or an unmarked directory holding receipts/`sequence.log` (`p426_wave1.py:73–89`).

**R1-4 (local gate on S′).** Resolved. `current_parity` reads `.upstream-sync-ref` at the sha when present, else the workflow; `audits_at` parses the fork's `dev/ci.py` `AUDITS` with `ast` (never executed); the audit list is threaded through `audit_argvs`, `steps_for`, `policy_digest`, `digest_for`, `run` (`local_gate.py:60–89, 240–289`). `test_t3_local_gate.py` covers both layouts.

**R1-5 (smoke in acceptance).** Not yet run (acceptance 6); the spec lists it as outstanding. The candidate code does not block it. Not a candidate defect.

**R1-6 (fork-suite environment).** Resolved in spec §2; not code. The candidate does not block it. Acceptance 3 was run by the designer (1124 passed, 1 skipped, 1 xfailed).

**R1-8 (frozen worktrees' venvs specified/checked).** Resolved. `arm_state` reads both venvs' versions; `record_problems` requires every `VENV_PACKAGES` per arm/venv and `mlx`/`mlx-metal` == the expected build's mlx; `pin_problems` (under a label) compares the live venvs at leg entry/exit (`p426_leg.py:300–306, 380–388`).

**R1-9 (box-notes: keep S note verbatim, add separate note).** Resolved. The 2026-10-17 note is kept verbatim with a scope line; a new 2026-10-27 note is added (`docs/box-notes.md` diff).

**R1-10 (A1 superseded by acceptance 3).** Resolved in spec; A1 is marked superseded. Not a candidate defect.

**R1-11 (read path for `frozen.<b>.json`).** Resolved. `frozen_path` returns `frozen.json` for `s`, `frozen.<label>.json` otherwise; the leg refuses a missing file for the missing file (`p426_leg.py:745–748`); `test_a_missing_label_record_refuses_for_the_missing_file` covers it.

**R1-12 (consumers hard-code S names).** Resolved. `modelnames._P426_WAVE1` matches `wave1(\.[a-z][a-z0-9]{0,7})?/`; `p426_panel.tunes(build)` returns `p426<label>-off`/`-on`; `pairs`, `make_pairs`, `item_scores` take `build`.

**R1-13 (validate before harvest).** Resolved. `label_problems` runs before `harvest_run_files` (`p426_wave1.py:292–298`).

**R1-14 (sequencer requires `--build`; leg keeps default).** Resolved. `p426_wave1.main` refuses a missing `--build` with rc 2 (`p426_wave1.py:874–878`); `p426_leg` keeps `--build` defaulted to `s`. Note: the existing test `test_main_refuses_a_workdir_that_is_not_stack_workdir` was **not** given `--build s` (the implementer's report §4 acknowledges this; the test directory was read-only). The spec v2.1 [r2] required that test to gain `--build s`. **This is a residual of R1-14 / R2-7 not fully landed in the candidate** — see B6 below.

**R1-15 (#2545 default temperature may reach M1).** Outstanding (acceptance 6). Not a candidate defect.

**R1-SR (glm S1/S2).** Resolved: S1 (worktree-venv acceptance) is acceptance 1; S2 (a test that `wave1/run/` is untouched) is `test_a_copied_s_record_is_refused_before_any_harvest_or_launch` and the `_tree_snapshot` checks.

**R2-1 (`production_ref = b26fa7c9`).** Resolved. `EXPECTED_BUILDS["s2"]["production_ref"] = "b26fa7c9faf23bc3167db3419504ef0b2b82a8e6"` (`p426_plan.py:467`); `test_the_real_expected_build_of_s2_is_in_code` asserts it.

**R2-2 (qualify's overlay byte-identical to ON registry; P504).** Resolved. `run_qualify_leg` asserts `overlay-<entry>.yaml` sha256 == the ON worktree's `main_models.yaml` and records both (`p426_leg.py:587–593`); `test_m1_asserts_qualifys_overlay_is_the_on_worktrees_registry` and `test_m1_refuses_an_overlay_that_is_not_the_committed_on_registry` cover it.

**R2-3 (tree clean = tracked only).** Resolved. `arm_state` uses `git status --porcelain --untracked-files=no` (`p426_plan.py:543`); `test_live_drift_is_found_per_arm` confirms an untracked output does not dirty the tree.

**R2-4 (patch-level restore diff).** Resolved in structure (the diff is parsed at hunk level, file set and mode checked), but the seeding-test half is not patch-exact — see B1.

**R2-5 (directed local-gate change).** Resolved (see R1-4).

**R2-6 (naming exemption regex).** Resolved. `_P426_WAVE1` is anchored and matches labelled dirs; `test_the_naming_exemption_covers_every_labelled_wave1_dossier` checks accepts and rejects.

**R2-7 (existing test gains `--build s`).** Not landed — see B6.

**R2-8 (per-arm head selection; no `None == None`).** Resolved. `build_pins(record, arm)` reads `stack_head_<arm>`; `pin_problems` under a label compares against the arm's own head; `test_a_label_leg_whose_head_is_the_other_arms_refuses` covers it.

**R2-SR (list stack files T3 changes).** Resolved in the implementer's report §1.

## B. What fails in use / what the tests miss / what the candidate does beyond the spec

### B1 — major — the seeding-test half of the restore check is not patch-exact
- Location: `benchmark/bench/p426_plan.py:240–249` (`restore_diff_problems`, seeding-test branch).
- Severity: major (confirmed spec violation of C218's "exactly the restore" / R2-4 "patch-level"; practical impact on the served build is nil, but the protection the request asks for is materially failed under conditions it supports).
- Evidence: confirmed in source. The seeding branch filters out every comment line on both sides before comparing: `seed_removed += [t for _, t in h["removed"] if not t.lstrip().startswith("#")]` and the same for `added`. Added code lines are accepted iff `len(seed_added) <= 2` and each contains `joint_v1` or `registry`.
- Problem: any comment hunk in the seeding test (added or removed) is invisible to the check, and up to two added code lines anywhere in the file pass as long as each mentions `joint_v1` or `registry`. The spec v2.1 §4 requires "no other hunk"; R2-4 adopted "patch-level".
- Failure scenario: an ON commit that, beyond the §11 restore, also deletes the C177-interim comment line elsewhere in the test, or appends a comment hunk, or adds `assert "joint_v1" in m["x"]` (contains `joint_v1`, not the restore's assertion) — all are accepted. The candidate's own `test_any_other_change_in_the_restore_commit_refuses` parametrizes only added **code** lines (`assert True`, `== 'other'`); it never tests a comment-only extra hunk in the seeding test, so the gap is untested. (The test-writer's `seeding-extra-hunk` case would have caught it but only "passed" because of the field-name refusal.)
- Proposed change: compare the seeding test's `-U0` patch against the pinned §11 patch exactly — one removed code line (the `per_query` assertion) plus its preceding comment removed, two added code lines (`joint_v1`, source `registry`) in order, no other hunk. Add a test that appends a comment line to the seeding test and asserts refusal.

### B2 — minor — the `main_models.yaml` half of the restore check is looser than "exactly"
- Location: `benchmark/bench/p426_plan.py:218–236` (`_key_value`, sorted comparison, `notes` count).
- Severity: minor (literal mismatch without material consequence on the served registry; YAML parse is identical).
- Evidence: confirmed in source. `_key_value` strips trailing ` # …` comments, so `draft_kind: mtp  # anything` parses as `draft_kind: mtp`. Removed/added active lines are compared as sorted lists, not positionally. `notes` is only required to be non-zero, so any number of `PROVISIONAL P426` comment lines anywhere in the entry pass.
- Problem: a restore commit that adds a trailing comment to a restored line, moves the restored lines within the entry, or adds multiple `PROVISIONAL P426` notes (or one outside `generation_defaults` but inside the entry) is accepted. R2-4 adopted "patch-level"; the spec says "exactly the entry's three C177 lines and the `PROVISIONAL P426` note".
- Failure scenario: ON commit adds `draft_kind: mtp  # re-cert` and a second `# PROVISIONAL P426` note in the entry; parsed YAML is unchanged, but the patch is not the §11 patch. The check passes.
- Proposed change: compare the registry's `-U0` patch against the pinned §11 patch positionally (one note inside `generation_defaults`, the three lines uncommented in place, no trailing-comment drift), or assert the registry patch equals a stored golden patch.

### B3 — major — the `new_side.py` exception is vacuous and silently disables a p371 check
- Location: `benchmark/bench/tests/p371_baseline/new_side.py:383–392` (`rederive` hook).
- Severity: major (breaks what a real consumer — the p371 differential — relies on, beyond the requested change; the documented behaviour of `rederive` is "policy VALUE changes are never accepted").
- Evidence: confirmed in source. The hook returns `new == _sha((REPO / "benchmark/requirements-bench.lock").read_bytes())` for the `lock_sha256` pointer. The "new" value is itself `sha256(benchmark/requirements-bench.lock)` computed by the new side from the same file, so the comparison is `sha256(file) == sha256(file)` — always true. The goldens still hold `ecd97da3…`; the helper's own docstring still says policy value changes are never accepted.
- Problem: any future lock change — reviewed or not — passes the p371 differential silently for `lock_sha256`. The spec §3 says fixes must be "the smallest that restores the documented behaviour" with "no behaviour change beyond that"; the vacuous-accept is a behaviour change that contradicts the documented behaviour, and is not the smallest fix (regenerating the goldens by their own procedure would be).
- Failure scenario: a later, unreviewed lock bump (e.g., an mlx point release) changes `lock_sha256`; p371's differential no longer flags it; the change ships unreviewed.
- Proposed change: either pin the accepted pair (`ecd97da3…` → the committed S′ bench-lock sha) so only that one transition is accepted, or regenerate the p371 goldens by their own procedure so there is no diff to accept. The operator should rule (the test-writer flagged this for a ruling).

### B4 — minor — `venv_versions` is non-deterministic on a stale second dist-info
- Location: `benchmark/bench/p426_plan.py:524–531` (`venv_versions`).
- Severity: minor (hazard the material introduces; a fresh `uv pip sync` does not leave stale dist-info, but the K2 check reads the live venv at leg entry/exit and a manual install could).
- Evidence: confirmed in source. The loop sets `found[name] = version` for every matching dist-info; the last in glob order wins. Glob order is lexicographic on the directory name, not the active version.
- Failure scenario: a venv that had mlx 0.32.4 then is downgraded to 0.32.3 by a manual `pip install` (leaving both `mlx-0.32.4.dist-info` and `mlx-0.32.3.dist-info`) reports `mlx=0.32.4` (the stale one wins lexicographically) and passes the K2 check, masking the downgrade. The reverse (stale 0.32.3 beside 0.32.4) happens to report correctly only by accident of sort order.
- Proposed change: resolve the active version from the `RECORD`/`INSTALLER` of the dist-info that pip considers active, or fail if two dist-info for the same `VENV_PACKAGES` name exist. At minimum, sort so the highest version does not silently win.

### B5 — minor — `claim_out` writes `.build` before the record is validated
- Location: `benchmark/bench/p426_wave1.py:239` (claim_out) vs `:292–295` (label_problems).
- Severity: minor (cosmetic; no byte of S's files is involved and a rerun under the same label is still allowed).
- Evidence: confirmed in source. `claim_out(out, build)` runs before `label_problems`; on a first start it creates `.build` and `sequence.log` even if the record is then refused.
- Failure scenario: a refused first start (e.g., a copied S record) leaves a `.build` marker and a `sequence.log` in `--out`. The rerun proceeds (marker matches). No S file is touched, but the operator's `--out` directory is not pristine after a refusal.
- Proposed change: validate the record before writing `.build`, or clean the marker on a refusal. Low priority. <!-- allow-shorthand: "Low" is a priority word -->

### B6 — minor — R1-14 / R2-7 not fully landed: the existing sequencer test was not given `--build s`
- Location: `benchmark/bench/tests/test_p426_wave1.py::test_main_refuses_a_workdir_that_is_not_stack_workdir` (unchanged in the candidate).
- Severity: minor (the spec v2.1 [r2] said that test "gains `--build s` and keeps its assertion"; the implementer's report §4 says the test directory was read-only for edits to existing tests, so it was left unchanged and `--build` is enforced in code via rc 2 rather than argparse `required=True`).
- Evidence: confirmed by the implementer's report §4. The candidate enforces `--build` in code (`p426_wave1.py:874–878`), so the existing test still passes, but the spec's literal wording is not met.
- Problem: the spec v2.1 [r2] disposition R2-7 is "adopted: that test gains `--build s`". The candidate does not make that edit. The protection (the test's guard) is preserved in code, so the outcome is intact, but the literal disposition is not landed.
- Failure scenario: an operator reviewing against the spec sees the test unchanged and flags drift; the test-writer's frozen set's 4 support-check defects (c) call the sequencer without `--build` and are correctly refused, but those are the writer's own fixtures, not the existing test.
- Proposed change: edit `test_main_refuses_a_workdir_that_is_not_stack_workdir` to pass `--build s` and keep its assertion, as R2-7 directed (requires unfreezing that test file).

## C. What the candidate does beyond the spec

- `bench.modelnames._P426_WAVE1` is a module-level compiled regex (not a string `startswith`); the spec said "a code change to `bench.modelnames`: its exemption … matches `benchmark/results/p426/wave1(\.[a-z][a-z0-9]{0,7})?/`Continuing the "beyond the spec" section, briefly.

## C. What the candidate does beyond the spec (continued)

- `bench.modelnames._P426_WAVE1` is a compiled anchored regex rather than the spec's literal `startswith` form; behaviour matches the spec's regex. In scope.
- `p426_leg.registry_delta_problems` gains `allow_added_comments` so the committed ON registry (with its `PROVISIONAL P426` note) passes only under a label; under `s` an added note still refuses. The spec v2.1 implies this (the ON arm carries the note) but did not name the flag. In scope; consistent with R2-2.
- `p426_leg.pin_problems` under a label switches from `PIN_KEYS` to `build_pins(record, arm)` and adds `uv_lock_sha256`/`bench_lock_sha256`/`venvs` to the live state. The spec listed these in the record and the K2 comparison; the candidate's `arm_state`/`repo_state` wiring is the implementation. In scope.
- `p426_wave1.label_problems` validates the record, both worktrees and the restore diff in one function before any harvest — the spec's "order of checks" [o1] made this a single sequencer-level gate; the candidate folds it into `label_problems`. In scope.
- The frozen-record field names (`uv_lock_sha256`, `bench_lock_sha256`, `stack_head_off/on`, `stack_clean_off/on`, `registry_off_sha`/`registry_on_sha`, `venvs.{off,on}.{.venv,.venv-bench}.{...}`) are the implementer's choice; the spec listed contents not keys. The test-writer's frozen set used `uv_lock_sha`/`bench_lock_sha` and so the two sets disagree on 43 cases — this is the open naming mismatch the test-writer is amending, not a defect in the candidate.

## D. Summary

- All R1/R2 dispositions are resolved in the candidate **except R1-14/R2-7** (the existing sequencer test was not given `--build s` — B6, minor, code-enforced instead).
- The S′ path (restore-diff, dirty tree, head mismatch, lock sha, venv checks, isolation, order of checks, naming exemption, P504 overlay, local gate) is implemented and, per the test-writer's delivery2, mostly exercised once the field-name mismatch is reconciled; the only confirmed spec violation in that path is **B1** (seeding-test restore check not patch-exact). **B2** is a looser-than-exact registry half.
- Two defects the candidate introduces beyond the requested change: **B3** (vacuous `new_side.py` exception silently disables a p371 check — needs an operator ruling) and **B4** (non-deterministic `venv_versions` on stale dist-info). **B5** is cosmetic.
- Nothing in the diff breaks evidence isolation between `s` and `s2`: per-label record path, per-label `wave1.<b>/` dossiers, per-label stems, the `.build` marker, and the resume rule reading only `wave1_dir(build)` are all confirmed in source and covered by `test_resume_reads_only_its_own_labels_receipts`, `test_a_valid_label_run_serves_each_leg_from_its_arms_worktree` (asserts S's `wave1/` is byte-unchanged), and `test_harvest_dossiers_and_run_files_per_label`.

The one finding I would block merge on is **B1** (confirmed C218/R2-4 violation, untested). **B3** should be ruled on by the operator before merge because it changes documented p371 behaviour. The rest are minor and can land with follow-ups.
