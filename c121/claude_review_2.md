# C121 cold review, round 2 (Claude): branch `c121-seeded-opencode` @ 77ddc98

**Verdict: BLOCKING (small fixes).** C1 and C4 must close before the next seeded rows are produced. C3 blocks every `role: candidate` model, but it fails closed, so it cannot produce bad data. The rest are residuals.

Method: I ran the five changed test files on a `git archive 77ddc98` export (seeding 49, m50 51, scaffold-compare 6, probe 38, progress-gate 8; all passed, 0 skipped). I wrote one adversarial pytest outside the repo. I ran the pinned 1.18.30 binary against my own mock, with HOME and XDG_CONFIG/CACHE/STATE/DATA redirected to `/tmp`. I did not contact :8000, did not touch `~/.config/opencode/`, and did not read any prior review.
**Note:** uncommitted edits appeared in the worktree while I was reviewing (`run_opencode_probe.py`, three test files, `generate.py`). Every finding below is against the HEAD export, not the dirty tree.

## Prior findings

| # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | Fail-closed binary, same exe on every spawn incl. discovery | CLOSED | `run_opencode_probe.py:92-107,862-867`. `opencode_bin` is threaded to run/session/export/debug config/`--version`/`debug paths`. Tests: `test_require_opencode_bin_refuses_relative_missing_and_non_executable`, `test_missing_pin_refuses_..._never_spawns_a_path_opencode`, `test_router_discovery_spawns_the_given_binary`, `test_export_and_overlay_check_spawn_the_given_binary`, `test_run_opencode_spawns_the_given_binary`. Only a stat runs before the check; `--version` runs after it (`test_run_opencode_probe_does_only_the_discovery_call_before_the_check` makes every subprocess call fail the test). No bare `opencode` spawn is left in the probe. `session_cache_probe.py:97` is still bare, which is the separate C125 issue. VERIFIED |
| 2 | Resume identity + skip recorded keys | CLOSED as specified, but incomplete (C1, C2) | `:1103-1117`, `:930-937`, `:960-962`; resume tests at seeding `:456-498`. VERIFIED |
| 3 | `scaffold_policy_sha256` consumed by `is_compatible`/compare, legacy "pre-C121" | CLOSED | `provenance.py:421,576-584`, `compare.py:319-325`, `test_scaffold_policy_compare.py`. Non-opencode manifests read "n/a" on both sides. Only `run_opencode_probe` writes `client: opencode`, and `generate`/`run_reasoning` never see opencode manifests, so `--clean-stale`/generate resume are unaffected. VERIFIED |
| 4 | Receipt bound to exe/shipped-config/test/global-config | CLOSED mechanically; residual C5 | `:432-446,468-478`, `test_receipt_is_bound_...`. `.bin/opencode` is a symlink to the real Mach-O, so the exe sha is a real binding. VERIFIED |
| 5 | Overlay check rejects nonzero exit, timeout, malformed JSON | CLOSED | `:487-503`; tests at seeding `:306,:317`. VERIFIED |
| 6 | Per-item overlay sha in manifest | CLOSED | `:1004-1005` (stamped after `_write_manifest`, before traffic); `test_manifest_records_the_overlay_sha_per_item_before_any_traffic`. VERIFIED |
| 7 | Resolved options minus seed equal the shipped block | CLOSED as specified, but against the wrong carrier (C3) | `:518-529`. With the real binary it PASSES on the shipped config: `min_p 0` and `0.0` compare equal, key order is irrelevant, nested dicts are fine. VERIFIED |
| 8 | git init per scratch dir + ancestor instruction files hashed | git init CLOSED; ancestor set wrong and incomplete (C4) | `:541-546,974-975`. Real-binary known-positive/negative test at seeding `:604-609`; I reproduced it: `~/AGENTS.md` is blocked with git init and leaks without it. VERIFIED |
| 9 | Overlay re-hash/restore after run, before export | CLOSED | `:1021-1029`; seeding `:625`. VERIFIED |
| 10 | Drift stamp on item refusal | CLOSED for the stamp; erasable by resume (C1) | `:988-1000`; seeding `:613`. VERIFIED |
| 11 | Docs corrections | Mostly CLOSED; residual C8 | AgentBench claim checked: `run_agentbench_os.py:1077` uses `sample_seed(task["id"], 0)`. VERIFIED |

## New findings

**C1: HIGH. Resume silently erases a prior session's `served_config_drift` stamp.** `run_opencode_probe.py:942-958` (`_write_manifest` rebuilds the manifest from `provenance.gather`), `:925-930` (only `router_history` and the overlay map are carried forward), `:1103` (`_check_resume` never looks at drift).
- Scenario: session 1 refuses at item k, and rows 1..k-1 are stamped as drifted. The operator reruns the same `--out` with the same `--seed-base`. The identity check passes, item k reaches `_write_manifest()`, and the stamp (and `router_exit`) is gone. The drifted rows now look clean and pool, which AGENTS.md forbids ("never grade/pool them").
- VERIFIED: adversarial test; the manifest after resume has no `served_config_drift`.
- Fix: `_check_resume` refuses when `prev_doc` has `served_config_drift`. Alternatively, carry it forward in `_write_manifest`.

**C2: MEDIUM. Resume identity covers 4 keys; the rest of the run identity is unchecked and then overwritten.** `:1110` compares only `seed_base`, `scaffold_policy_sha256`, `opencode_bin` and `opencode_version`. `:926` compares the router config path but not its `config_sha256`.
- Not compared: `opencode_global_config_sha256`, `opencode_config_sha256`, `ancestor_instruction_files`, `seed_propagation`, exe sha, `claude_md_present`, `polyglot_sha`, and the gate params. On resume, all of them are overwritten with session 2's values, so session-1 rows are attributed to a global config, instruction set and registry sha they did not run under.
- VERIFIED: the adversarial test resumed over `OLD-GLOBAL`/`OLD-SHIPPED`, and the manifest was rewritten with the new values.
- Fix: compare the whole `_scaffold_runtime()` + `_seed_runtime()` dict, the ancestors and the router `config_sha256`, and refuse on any difference.

**C3: MEDIUM. The overlay check uses the client carrier, not the bench carrier the probe documents.** `:520,535`; the same source is used for the receipt `config_sha256` (`:434`) and for `_scaffold_runtime.opencode_config_sha256`, which predates this branch.
- `docs/qualify-a-model.md` §8 and `docs/box-notes.md` name `benchmark/opencode_bench.json` as the carrier for probe runs. The lab-notebook entry for 2026-08-29 records it being deployed as the global config.
- `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` and `Qwen3.8-27B-OptiQ-4.5bpw-mixed` exist only in the bench carrier. Every item for them refuses with "shipped opencode config has no deployed options", so candidates cannot be probed.
- For the 7 shared models the options and limits are identical today (VERIFIED), so the picks are unaffected.
- ASSUMPTION: the live global config is still the bench carrier (not inspected, per the rules).
- Fix: compare against `benchmark/opencode_bench.json` (or registry `params_for(..., "deployed")` through the configgen transform), and record that file's sha.

**C4: MEDIUM-HIGH. Global instruction and config surface is not covered: the operator's global rules reach every prompt and are recorded nowhere.**
- What opencode 1.18.30 actually loads:
  - `<config>/AGENTS.md`, the global rules file (the first that exists of `[config/AGENTS.md, ~/.claude/CLAUDE.md]`). It reached the system prompt even in a git-init'd item dir (VERIFIED mock capture; source list VERIFIED from binary strings).
  - `<config>/config.json` (VERIFIED in opencode's own load log).
  - A `CONTEXT.md` project fallback (binary).
  - Files named in the `instructions` key (VERIFIED: they reach the prompt, and the overlay check still passes).
- What the probe hashes and lists:
  - `_global_config_sha256` (`:462`) hashes only `opencode.json`/`.jsonc`.
  - `_ancestor_instruction_files` (`:570-571`) omits `<config>/AGENTS.md` and `CONTEXT.md`. It includes `.cursor/rules`, which 1.18.30 never reads. It also lists ancestors that git init now blocks, so the list is neither the loaded set nor complete.
- None of this feeds `scaffold_policy_sha256`, compare or resume.
- ASSUMPTION: whether `~/.config/opencode/AGENTS.md` exists on this box (not inspected).
- Fix:
  - Hash the whole config dir (config.json, opencode.json(c), AGENTS.md, agent/, command/, mode/).
  - Refuse the item if the resolved `debug config` has a non-empty `instructions`, or if `<config>/AGENTS.md` exists.
  - Correct the instruction-file list to AGENTS.md/CONTEXT.md plus the global AGENTS.md.

**C5: LOW-MEDIUM. `verified-by-test` certifies a configuration the probe does not run.**
- The AC3 test (seeding `:404`) runs in a NON-git dir, against a temp config derived from the client carrier. It then binds the receipt to the real global config hash (`:422`), a config it never loaded.
- The git-mode test (`:609`) checks only the sentinel, not the seed.
- Production does propagate the seed in a git-init'd dir with the deployed options (VERIFIED in my run), so today's data is correct; the label is just weaker than it claims.
- Fix: call `_git_init_scratch(proj)` in AC3, assert `body["seed"]` in `_run_with_mock(git_init=True)`, and fix the stale comment. Optionally bind the sha of `run_opencode_probe.py`.

**C6: LOW. git init turns on opencode's snapshot tracking (undocumented scaffold side-effect).**
- `xdg-data/opencode/snapshot/global` appears only in git mode (VERIFIED). The project id is "global" because the repo has no commit. The system prompt now says "Is directory a git repo: yes".
- ASSUMPTION: per-step snapshots of the tree, including any model-run `npm install`/`cargo` output, add a wall-clock/latency tax.
- It is hashed via `scratch_git_init`, so there is no pooling hazard, but latency comparisons against pre-C121 rows are confounded.
- ASSUMPTION: `.git` in the docker mount does not affect `go test`, cargo, gradle or jest.
- Fix: document it, and run one known-positive (`.meta` example) grade per docker language on a git-init'd dir before the next chain.

**C7: LOW. `limit` is only checked as non-empty (`:530`).** context/output drive compaction and the output cap. Fix: require equality with the carrier's `limit`.

**C8: LOW. Docs.**
- Lab-notebook `:4450` "seed still merges" has no repo test behind it (C5).
- `:4451` "so exposure is observable" is overstated (C4), and global AGENTS.md exposure is not mentioned.
- `.cursor/rules` is not a 1.18.30 source.
- Spec annotations (m54/m55) and the open-questions entry match the code.

**C9: LOW. Integration tests spawn the pinned binary with the real HOME and the default XDG cache/state.** They write `~/.cache/opencode` and `~/.local/state/opencode`, neither of which is on the AGENTS.md exception list. The probe does the same by design (cache), which predates this branch. Fix: redirect HOME and XDG_STATE_HOME in the tests.

**C10: LOW.**
- `overlay_rewritten_by_model` is recorded, but nothing excludes such rows.
- `progress_gate.py:151,158` kills only the opencode PID, so a surviving tool child could rewrite the overlay after the restore. That kill behaviour predates this branch.
- ASSUMPTION: opencode reads its config once per instance, so a mid-session rewrite does not change later turns' seed.

**Item 9 (autouse stub in `test_m50_entrypoints.py`): no regression.** The stub lives outside `tmp_path`, so the `list(tmp_path.iterdir()) == []` assertions stay valid. Tests that get past the check now really spawn the stub (`debug paths` returns None) and a real `git init` in tmp, which is harmless. VERIFIED: 51 passed on the HEAD export.
