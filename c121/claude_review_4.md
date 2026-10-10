# C121 round-4 cold review (Claude) — branch `c121-seeded-opencode` @ cc3c04d

Reviewed `git diff main...cc3c04d`. Read-only; CPU only; port 8000 untouched. Only the pinned 1.18.30 binary was run, against my own two temp mocks (main and task provider), with HOME, every XDG_* dir and TMPDIR under a fresh temp dir. The temp dirs are deleted. Tests were run at cc3c04d: seeding 92 passed; m50_entrypoints 51; run_opencode_probe 38; progress_gate 8; scaffold_policy_compare 7; workdir 3; dsh 32 passed + 2 skipped (no dsh installed); c106 7. The real `~/.cache/opencode` and `$STACK_WORKDIR` were unchanged afterwards (checked: mtimes, and no `opencode-probe/` dir).

**Concurrent change.** f3c0887 ("round 5") was committed to this worktree during the review, at 22:01. Every finding below is against cc3c04d. I read f3c0887's diff only to tag each finding [f3c0887: fixed / open]. I did not review f3c0887 itself.

## Verdict

- **cc3c04d: BLOCKING**, on E1 (the receipt stamping path crashes).
- **With f3c0887's E1 fix: SHIP-WITH-RESIDUALS.** Fix E2 and E3 before the first chain. Each is small.

## Closure of prior rounds (from the commit messages and fix report; prior reviews not read)

| Item | Status @cc3c04d | Evidence |
|---|---|---|
| R1 B1: fail-closed pinned binary on every spawn | CLOSED | `_require_opencode_bin` (absolute path, is a file, is executable). The exe path is passed to run, list, export, discovery, destination and overlay spawns. Tests: `test_*_spawns_the_given_binary`, `test_missing_pin_refuses...` |
| R1/R3 B2/C1/C2: resume identity, skip recorded keys, drift refusal, history | CLOSED, with gaps (E2, E9) | `_check_resume` checks RESUME_IDENTITY_KEYS, model, `git.serving_path` and `router.config_sha256`. `continuation_history` holds the full prior attribution. The byte-identical all-skipped resume is tested. |
| R1 B3: scaffold policy in `is_compatible` / compare | CLOSED (E4: `pure` is not in the hash) | provenance.py:421, compare.py:319 |
| R1/R2 B5: receipt bound to exe/config/test | NOT CLOSED (E1) | Binding logic is correct. The stamping call raises TypeError. |
| R1 B6: overlay check rejects nonzero exit / timeout / malformed output | CLOSED | `_assert_overlay_resolved`, `test_overlay_check_rejects_*` |
| R1/R2 B9: per-item overlay sha | CLOSED | `overlay_sha256_by_item` is stamped before traffic |
| R2 B2/C7: resolved options == carrier ∪ seed; `limit`; `instructions` | CLOSED | Mock run: the real 1.18.30 `debug config --pure` model block equals the carrier block plus the seed exactly, and `limit` is equal. This is not exercised by any test (E10). |
| R2 B3: git init per item | CLOSED | The upward search is blocked (`test_ancestor_agents_md_...` has a known positive). Side effects: E7. |
| R2 B6: item refusal stamps drift | CLOSED, but over-broad (E2) | |
| R2 B7/C10: overlay rewrite is flagged, restored and grade-excluded | CLOSED | `test_overlay_after_run_is_restored...` |
| R3: bench-owned config home (bench carrier, 9 models) | CLOSED | `_make_bench_config_home` copies `benchmark/opencode_bench.json` verbatim and checks the sha |
| R3 C1: `--version` before discovery | CLOSED | `test_override_pointing_at_v2_is_refused_before_any_debug_config_spawn` |
| R3 C4: `generate` never cleans or restamps opencode rows | CLOSED (vacuous, E12) | |
| R4 E1: bootstrap env on every spawn | CLOSED | `boot_env` (run_opencode_probe.py:965) feeds `--version` and discovery (:974). Per-item `oc_env` feeds both checks, run, list and export. `test_every_spawn_runs_under_the_bench_owned_env` asserts config, data, state, TMPDIR and HOME on all 4+ spawns. |
| R4: title switch | CLOSED | Mock with a live task-provider mock: 0 requests to the task provider in a 1-turn session and in a 2-turn session with a `write` tool call. Every main request carried `seed`. |
| R4: scrubbed stamps | CLOSED | `portable_path` |
| R4: per-run dir cleanup | PARTIAL | A `sys.exit` inside `_make_run_dirs` (the sha-mismatch branch) leaves `config-<id>` behind, because `ctx["dirs"]` is set after the call (:963–964). [f3c0887: fixed] |
| R4b: `--pure` on every `debug config` | CLOSED for the default path; OPEN under `--no-pure` (E4) | |
| R4b: bench HOME | CLOSED as specified; new hazard E3 | |
| R4b: OPENCODE_* strip | CLOSED | `test_child_env_drops_every_parent_opencode_variable...` |
| R4b: effective-inputs-only policy hash | CLOSED, but `pure` is missing (E4) | `_scaffold_runtime` :668 |

## Findings

**E1 — HIGH — receipt can never be stamped.** VERIFIED.
- Where: `benchmark/bench/tests/test_opencode_probe_seeding.py:476` calls `P._record_seed_propagation_verified(_pinned_bin(), P._instruction_sources_sha256(...))`. The signature is `_record_seed_propagation_verified(binary=None)` (run_opencode_probe.py:451).
- Reproduced: `TypeError: takes from 0 to 1 positional arguments but 2 were given`. No receipt exists at `$STACK_WORKDIR/opencode-1.18.30/seed_propagation_verified`.
- Failure: the qualify-a-model step `OPENCODE_PROBE_RECORD_VERIFIED=1` fails after the mock assertions pass. Every manifest reads `seed_propagation: unverified`.
- Fix: pass only the binary.
- [f3c0887: fixed. It adds an `OPENCODE_PROBE_RECEIPT` override and a test of the opt-in branch.]

**E2 — MEDIUM — a refusal in a continuation stamps `served_config_drift` on the PREVIOUS session's clean manifest.** VERIFIED by reading.
- Where: run_opencode_probe.py:1105–1121.
- `_drift_stamp` runs whether or not this session has written the manifest (`manifest_written`). On a resume, the first new item's destination check or overlay check fails, for example a 120 s `debug config` timeout on a loaded box, or a model missing from the carrier. That writes `served_config_drift` into a manifest whose rows passed their own `router_exit`.
- Every later resume then refuses, and M50 requires archiving and regenerating those rows. Hours of clean rows are lost to a transient fault.
- Overlay or carrier mismatches are also not "served config drift" at all.
- `test_item_refusal_stamps_served_config_drift_on_an_existing_manifest` codifies this behaviour.
- Fix: stamp only if `manifest_written`. Otherwise refuse without stamping, or append to a separate `refusal_history`. Use a distinct key for overlay refusals.
- [f3c0887: open]

**E3 — MEDIUM — the persistent bench HOME and the per-run config copy are config sources the model can write, and they are never re-verified.** VERIFIED (mock).
- 1.18.30 with `--pure` merges `$HOME/.opencode/opencode.json` and `$HOME/.opencode/agent/*.md`:
  - A sentinel `agent.build.prompt` in `<HOME>/.opencode/opencode.json` REPLACED the system prompt (system length 9917 → 1302, sentinel present).
  - `<HOME>/.opencode/agent/build.md` content entered the system prompt.
- `opencode-probe/home` persists across runs and sessions. The model's bash tool has HOME pointing at it. 1.18.30 even ships a built-in `customize-opencode` skill in the prompt.
- The same applies within a run to `$XDG_CONFIG_HOME/opencode/opencode.json`, the copy. It is hashed once, at the first item (`opencode_config_copy_sha256`).
- The per-item check compares only baseURL, the model's options and limit, `agent.title`, and `instructions`. It does not compare `agent.*.prompt`, `mode`, `command` or `permission`. Neither location is in the identity.
- Failure: one item writes `~/.opencode/...`. Every later item, run and session runs a different system prompt with an identical scaffold hash.
- Also VERIFIED: the test docstring at :1070 and the notebook ("a manual run showed none of them reaching the prompt … belt-and-braces") are wrong for `~/.opencode/agent/build.md`. The bench HOME is load-bearing. The real `~/.opencode` is absent on the box, so past rows are unaffected.
- Fix, per item:
  - refuse if `<bench home>/{.opencode,AGENTS.md,.claude}` exists;
  - re-hash the config copy and refuse on change;
  - or make HOME per-run.
- Better still: compare the whole resolved `debug config` minus `seed` against the carrier ∪ overlay. Normalise opencode's defaults (`options: {}`, `permission: {}` on agent entries, `username`, `plugin_origins`).
- [f3c0887: open]

**E4 — MEDIUM — `--no-pure`.** VERIFIED by reading.
- `pure` is in the resume identity (:497) but not in `scaffold_policy_sha256` (:668). compare.py and `is_compatible` would therefore treat plugin-ON rows as the same scaffold as plugin-OFF rows.
- With `--no-pure`, discovery (:974) runs without `--pure`. That npm-installs and fetches the GitHub plugin BEFORE the router check, which is the exact defect round 4b fixed.
- Fix: remove the flag, or fold `pure` into the hash.
- [f3c0887: fixed, flag removed]

**E5 — LOW — doc inaccuracies.** VERIFIED.
- `docs/lab-notebook.md:4458`: "receipt binds … instruction-source inventory". The code binds version, exe, bench config and test only.
- Notebook "Fix" bullet: the overlay is described as seed-only, but it is now seed + title. It also says the config copy is "the only file there", but opencode writes `config-<id>/opencode/.gitignore` (VERIFIED).
- Notebook :4479 and the test :1070: the false negative claim from E3.
- `docs/proposal-opencode-seeding.md:50` (AC5): says the inventory goes "into the scaffold-policy hash". This contradicts the effective-inputs design.
- `docs/open-questions.md` C121:
  - first amendment: "copy of the shipped `opencode_config/opencode.json`". The code uses `benchmark/opencode_bench.json`.
  - "Every opencode row so far (M53/M54/M55) ran on one seed": M54 is AgentBench, seeded base 0.
  - The second amendment still reads "operator to confirm", while the brief treats it as in force.
- `docs/qualify-a-model.md:701`: "only the models.dev cache dir is shared". The shared cache also holds `bin/` (rg/LSP) and `packages/`; the real one contains the superpowers plugin.
- Code comment :999: "One extra spawn (`debug paths`)". No such spawn exists any more.
- Fix: edit the text.

**E6 — LOW/process — the pre-M50 write set exceeds what was ruled.** VERIFIED.
- What runs before the router check:
  - read config.sh;
  - stat the binary;
  - mkdir `config-<id>/opencode` and write the carrier copy, then re-read its sha;
  - mkdir `home/.local/state` (persistent) and `tmp-<id>`;
  - `--version`, which creates `$XDG_{DATA,STATE,CONFIG}_HOME/opencode`, `$TMPDIR/opencode`, and the REAL `~/.cache/opencode/bin` (mkdir; it already exists);
  - discovery `debug config --pure` (cwd `$STACK_WORKDIR`), which writes a DB and log under the discovery data dir, lock files under the persistent bench state, and `.gitignore` into the config home.
- Everything is inside the workdir except the real cache mkdir.
- After a refusal, `config-<id>`, `tmp-<id>` and the discovery data dir are removed. `opencode-probe/home/.local/state/opencode/locks/*` remains, because it is persistent.
- C125(3) is still OPEN in open-questions, and it proposed "no write". C114 covers only the discovery data-home write. `~/.cache/opencode` is not in the AGENTS.md artifact exception list.
- Fix: get an operator ruling. Then extend the M50 exception and the artifact exceptions in AGENTS.md to name exactly this set.

**E7 — LOW — side effects of git init.** VERIFIED in part.
- The system prompt now says "Is directory a git repo: yes".
- opencode creates `data/opencode/snapshot` and tracks the item tree on each step. JS and rust exercises ship no `.gitignore`, so a model's `node_modules`/`target` would be snapshotted on every step. The wall-time cost and progress-gate effect are an ASSUMPTION, not measured.
- `snapshot: false` is a valid 1.18.30 key (it is resolved by `debug config`).
- Docker: `_docker_grade` mounts the whole item dir as `/work`, including `.git` and `opencode.json`, as root. The image is `buildpack-deps:jammy`, so git is present, and `safe.directory` is set only for `/aider`. The commands (`go test ./...` on non-main packages, `cargo test`, gradlew, and `npm-test.sh`, which only symlinks, seds and runs `npm run test`) do not invoke git. ASSUMPTION: go test on library packages does no VCS stamping. The known-positive grade per language is still owed.
- Fix: add `"snapshot": false` to the overlay (it is part of the overlay schema, so it is hashed). Run the known-positive grades.

**E8 — LOW — the receipt certifies a different environment from production.** VERIFIED.
- `_hermetic_env` (test :412) points XDG_CACHE_HOME at an empty temp dir. Production uses the real shared cache, which is written by the daily-driver and brew v2 opencode.
- The receipt binds the test file and the carrier, but not `scaffold_policy_sha256` or the probe module. Changing the overlay or env in `run_opencode_probe.py` keeps "verified-by-test".
- Fix: bind the receipt to `scaffold_policy_sha256` plus the test sha. Run the receipt test with the production cache home (it is read-only for the test except `models.json`), or record that it is out of scope.

**E9 — LOW — resume gaps.** VERIFIED.
- Not compared on resume:
  - probe and grader code identity (`run_opencode_probe.py`, `progress_gate.py`, the prompt text);
  - the docker image digest;
  - `poll_s`;
  - cache `bin` content;
  - bench HOME content (E3).
- A manifest without rows skips `_check_resume` entirely (:1043), and the next `_write_manifest` drops any drift stamp it carried.
- Malformed row lines are silently ignored (`_recorded_keys`).
- Fix: add a sha of the probe module and progress_gate to the identity. Run the check whenever a manifest exists. Refuse on corrupt lines.
- [f3c0887: the manifest-exists check, corrupt-line refusal, `poll_s` and the cache-bin inventory are fixed. Code identity is still open.]

**E10 — LOW — test gaps.**
- `_assert_overlay_resolved` is never run against real 1.18.30 output (only `_fake_debug` and the recording stub), so false refusals from opencode's normalisation are untested. My mock run shows it would pass today for the Fable mixed model.
- `_real_dirs_listing` compares only top-level names (it is moot because the env is fully redirected).
- `test_m55_report_counts_grade_excluded_rows_separately` executes an untracked script from `$STACK_WORKDIR` (via `eval`/`exec`). Whether it passes or skips depends on the box.
- `test_real_home_instruction_sentinels...` has no positive control. With E3, a positive control is now known to exist.
- Fix: add one real-binary test calling `_assert_overlay_resolved` in a git-init'd dir. Add a positive control: HOME left at the stand-in leaks `~/.opencode/agent/build.md`.

**E11 — LOW — the HOME redirect also moves the model's tool caches.** ASSUMPTION, apart from the toolchain locations.
- The toolchains are Homebrew-installed, so they are not HOME-relative (VERIFIED).
- Their caches do move: `~/.cargo/registry`, `~/go`, `~/Library/Caches/go-build`, `~/.gradle` and `~/.npm` now live in the bench HOME. The first session after the change runs cold and may need network access, which skews wall time between paired sessions.
- Fix: warm the bench HOME once before a chain, or note this in the latency caveats.

**E12 — INFO.** `_SCAFFOLD_BENCHES={"opencode"}` (generate.py:289) can never match: the real stems are `opencode_<lang>[.<tag>]`, and none is in `benchmarks.SPECS`. scoreboard (`stem.split(".")[0]`), compare and clean-stale are unaffected by the new or legacy manifests: legacy reads "pre-C121", non-opencode reads "n/a" (VERIFIED).

**E13 — INFO.** On failure, the destination check re-raises the ServedConfigError: a traceback, exit 1. The overlay check instead calls `sys.exit("REFUSED: …")`. Both are nonzero, but the outputs are inconsistent.

## Answers to the brief's questions (short)

1. **Pre-M50 sequence:** listed in E6. Discovery env: `boot_env` (:965) has XDG_CONFIG_HOME=`config-<id>`, HOME=bench HOME, XDG_CACHE_HOME=real cache, OPENCODE_* stripped plus the two switches. VERIFIED by `test_every_spawn...` and the code.
2. **What can influence the request or system prompt:**
   - Personal config: no (XDG redirected, VERIFIED by the isolation test).
   - brew v2: no, as long as the exe is pinned and `--version` passes. `session_cache_probe.py:97` still spawns a bare `opencode` from PATH (C125(2), open).
   - Cache: `models.json` (fetched on `run`), `bin/` (rg/LSP), `packages/` (plugins; only loaded without `--pure`).
   - State: bench state holds only locks.
   - Persistent bench HOME: YES (E3).
   - Data: per item.
3. **Seed:**
   - Every main request (1-turn, and 2-turn with a tool call) carried `seed` and all the carrier options.
   - `max_tokens` = 102400 = `limit.output`. Both are equal for all 9 models, so precedence is moot.
   - `model` is overridden by `--model`.
   - `small_model` is reached only by title generation, which is disabled. 0 task-provider requests were observed. Compaction and long sessions are not covered (ASSUMPTION).
4. **Resume:** see the table, E2 and E9.
5. **Per-item check:** fails closed on exit, timeout or parse failure. The parser takes from the first `{`, so leading log text containing `{` refuses, which is safe. No normalisation false refusals today (VERIFIED for one model). Scope gap: E3.
6. **git init:** E7.
7. **Other consumers:** E12.
8. **Receipt:** E1 and E8.
9. **Tests:** E10. Integration isolation is correct (temp HOME/XDG/cache; nothing real changed).
10. **Docs:** E5.
