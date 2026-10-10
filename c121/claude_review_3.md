# C121 cold review, round 3 (Claude). Branch `c121-seeded-opencode` @ 499e479

**HEAD moved during the review.** 7af61ea ("round 4") landed in the worktree while I was working. Everything below is for 499e479, as the brief asks, and every line reference is to 499e479. I grepped 7af61ea but did not review it. Results of that grep:
- Still open at 7af61ea: E1 (both `debug config` spawns still lack `--pure`, run_opencode_probe.py:542 and provenance.py:1497), E2 and E3.
- Touched at 7af61ea: E5 (model, lang, pure and gate parameters added to the identity), E9 (state home redirected) and E8 (rmtree cleanup).

**Method.** I read the code and the tests, and ran the 5 C121 test files (174 passed). I ran 8 experiments with the pinned 1.18.30 binary against my own mock on a random localhost port. In each one, HOME and every XDG_* directory pointed to temp dirs under `$STACK_WORKDIR/c121/tmp/`. The config was the real `benchmark/opencode_bench.json`, verbatim except for the baseURLs; the `plugin`, `mlx-task` and `small_model` entries were kept.

**One deviation.** I ran `opencode debug config --help` once with the real environment. Afterwards no mtimes had changed under `~/.local/share/opencode`, `~/.cache/opencode` or `~/.local/state/opencode`. I did not look inside `~/.config/opencode/`.

## Verdict: BLOCKING (E1; the fix is small). E2, E3, E4 and E5 should be fixed or ruled on before the next chain.

## Closure table

| Prior finding | Status | Evidence |
|---|---|---|
| R1 B1: pinned binary on every spawn | CLOSED in the probe | `run` :334/:248, export, discovery provenance.py:1497, overlay check :499, `--version` :893 all take `oc_bin`. Residual: `session_cache_probe.py:97` still spawns bare `opencode` (C125(2), outside this branch). |
| R1/R2/R3 B2: resume identity, key skip | PARTIAL | Drift refusal, router sha, the keys in `RESUME_IDENTITY_KEYS`, the skip and no-duplicate behaviour are all tested. Gaps are in E5 and E6. |
| B3: scaffold policy in `is_compatible` and `compare` | CLOSED | provenance.py:421, compare.py:321. Legacy manifests on disk have `client=opencode` and no hash, so they read `pre-C121` and refuse. |
| B5/C3: receipt bound to exe, carrier, test and instruction hashes | CLOSED (mechanism) | No receipt exists on disk, so every run is `unverified` until the operator stamps one. |
| B6: overlay check rejects nonzero exit, timeout, malformed output | CLOSED for the overlay check | The destination check still parses stdout whatever the exit code (provenance.py:1503). |
| B9: overlay sha per item | CLOSED | — |
| R2 B2/C7: resolved options and `limit` equal the bench carrier | CLOSED | VERIFIED: resolved options and `limit` equal the carrier for all 9 models. No float or int normalisation problems (`0.0` resolves to `0`, which Python treats as equal). |
| R2 B3: `git init` blocks the upward AGENTS.md search | CLOSED | VERIFIED: the prompt shows "Is directory a git repo: yes" and snapshot repos appear in the per-item data home. |
| R2 B6: item refusal stamps drift | CLOSED, but see E6 | — |
| B7/C10: overlay rewritten by the model | CLOSED at row level | Consumers: see E10. |
| C1/C125(3): `--version` before discovery | CLOSED | Test `test_override_pointing_at_v2...` logs the calls. Wording problem: see E7. |
| C2: continuation history | PARTIAL | History keeps only the identity keys. `seed_propagation` and the gate parameters are lost. |
| C4: `generate` never cleans or restamps opencode rows | CLOSED | generate.py:260/:334. `scoreboard` reads score files only, `--clean-stale` skips opencode, `compare` refuses pre-C121 vs new. |
| C6: docker grading with `.git` present | UNVERIFIED (unchanged) | See point 6 below. |
| R8: CLAUDE.md switch | CLOSED | VERIFIED known positive: a sentinel `~/.claude/CLAUDE.md` reaches the prompt without `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` and is absent with it. No repo test does this; see E11. |
| C123: never use v2 | CLOSED | A non-pinned version refuses before any `debug config` runs. |
| C124: transport abort | OPEN, not in scope | — |

## Findings

**E1 — HIGH — run_opencode_probe.py:499, provenance.py:1497.** Both `debug config` spawns run without `--pure`, while `run` adds `--pure` (:334).
- What happens (VERIFIED, real carrier, fresh temp home):
  - Discovery runs before the M50 check. It npm-installs `@opencode-ai/plugin@1.18.30` into the new `config-<run-id>/opencode/`: `.gitignore`, `package.json`, `package-lock.json` and 61 MB of `node_modules`.
  - That install writes about 96 MB into `$HOME/.npm/_cacache`. In the probe HOME is not redirected, so these are writes outside the workdir before the router check.
  - It fetches the `superpowers` plugin from GitHub HEAD into the cache home and **runs that plugin's code**. This is unpinned third-party code, executed before the router check and again in both per-item spawns.
  - The plugin changes the resolved config (it adds `skills.paths`). So the per-item check validates a config that `run --pure` never uses.
- Why it matters: this breaks the M50 rule ("before any read/write/request") beyond the C114 and C125 exceptions, and makes the docstring's "the only file there" false. It is new with C121: the fresh per-run config home forces a fresh install every run, and the second per-item spawn is new.
- Comparison: `debug config --pure` writes only `.gitignore`, makes no network fetch, takes 0.5 s instead of 6.5 s, and resolves the same provider options (VERIFIED).
- Fix: pass `--pure` to both `debug config` spawns whenever `pure` is set (thread it through `opencode_router_base` and `_assert_overlay_resolved`). Add a test that checks the argv. Add a pinned-binary assertion that after discovery the config home holds only `opencode.json` and `.gitignore`. Optionally merge the two per-item spawns into one.

**E2 — MED — :363, :538–551.** opencode loads `~/.opencode/` (under HOME) regardless of `XDG_CONFIG_HOME`.
- VERIFIED with a temp HOME:
  - `~/.opencode/opencode.json` changed the request's temperature to 0.111. The per-item check would catch that.
  - `~/.opencode/agent/build.md` **replaced the system prompt**, and the per-item check passed. The check compares only provider options, `limit` and `instructions`.
- The binary also has system-level config sources: `/Library/Application Support/opencode` and `/Library/Managed Preferences/<user>/ai.opencode.managed.plist`.
- None of these are in the instruction inventory or the identity. `~/.opencode` and `/Library/Application Support/opencode` are absent on the box today, so this is latent.
- Fix: refuse if `~/.opencode` or a managed config exists, or give the opencode child a bench-owned HOME. Make the check require that resolved `mode` and `command` are `{}`, that `agent` equals what the overlay sets, and that the whole resolved model block minus `seed` equals the carrier block.

**E3 — MED — :361–377.** The child environment is `dict(os.environ)`, and only the three `OPENCODE_CONFIG*` overrides are refused.
- The 1.18.30 binary reads about 80 `OPENCODE_*` variables (from `strings`). Several change behaviour: `OPENCODE_PERMISSION`, `OPENCODE_EXPERIMENTAL*`, `OPENCODE_ENABLE_EXA`, `OPENCODE_ENABLE_QUESTION_TOOL`, `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX`, `OPENCODE_DISABLE_AUTOCOMPACT`, `OPENCODE_PURE`, `OPENCODE_MODELS_URL`.
- The operator's shell exports `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` today (VERIFIED: it is in the current environment and set in `.zshrc`). It ends up in the probe's environment and is not recorded. It is probably redundant with `EXTERNAL_SKILLS` (ASSUMPTION).
- Fix: strip every `OPENCODE_*` variable, then apply `SCAFFOLD_ENV_POLICY`. Record the stripped names in the manifest.

**E4 — MED (design challenge) — :614, :1141.** `instruction_sources_sha256` covers `~/.claude/CLAUDE.md`, `~/AGENTS.md` and other ancestor files. It feeds `scaffold_policy_sha256` and the resume identity, yet both files are VERIFIED not to reach the prompt (the switch, and `git init`).
- Scenario: any edit to the operator's personal CLAUDE.md or `~/AGENTS.md` between sessions flips the policy hash. `compare` then refuses cross-model pairs (compare.py:321), resume refuses, and the receipt flips to `unverified`. This is the same kind of fragility the operator rejected for the personal-config equality check.
- Fix (needs a ruling): keep the inventory as an observation in the manifest. Key the policy hash on the blocking mechanisms (the switch values and `scratch_git_init`) plus any source that is not blocked.

**E5 — MED — :1141–1184, :972.** The resume path does not compare:
- the manifest `model`;
- `--lang` or `pure` (neither is recorded at all);
- the gate parameters (`tick_s`, `hard_ceiling_s`, `stall_ticks`, `loop_repeats`) or `polyglot_sha`, which are recorded but not compared;
- the `gather()` blocks: serving-path git, sampling, kv and registry. There is no `provenance.is_compatible`.

`seed_propagation` is neither compared nor kept in `continuation_history`.

Scenario: the default `--out` is per model, not per language. `--lang rust --seed-base 1` after `--lang python --seed-base 1` appends to the same file and overwrites the manifest. A fork bump between sessions also pools silently.

Fix: add these keys to the identity, call `is_compatible(prev_doc, gather_now)`, and snapshot the full previous runtime into history. (7af61ea appears to add model, lang, pure and the gate parameters; not reviewed.)

**E6 — LOW-MED — :1035–1048, :1127–1134.** A session that never reached `_write_manifest` can stamp `served_config_drift` or `router_exit` onto the **previous** session's manifest.
- Scenarios:
  - A resume whose first new item fails the destination check marks the previous session's clean rows as drifted, and AGENTS.md says drifted rows are archived.
  - A resume where every item is already recorded overwrites the previous `router_exit` with this session's (router from pid A, exit from pid B).
- The test `test_item_refusal_stamps_served_config_drift_on_an_existing_manifest` locks this behaviour in.
- Fix: stamp only if `manifest_written` is true this session. Otherwise record the event in `continuation_history` or a sidecar file.

**E7 — LOW — :893.** The pre-M50 `--version` runs with the operator's real environment.
- VERIFIED in a temp environment: `--version` creates `<data>/opencode/{log,repos}`, `<cache>/opencode/bin` and `<state>/opencode`. On this box those directories already exist, so it is a no-op, but the C125 claim of "no write" is inaccurate on a fresh box.
- Fix: run it under the discovery environment, or correct the C125 and AGENTS.md wording.

**E8 — LOW — :452–465, :902.** One config home per invocation, refusals included, and none is ever deleted. Each is 61 MB with E1 present, about 16 KB without. Fix: E1, plus pruning at exit. (7af61ea appears to add rmtree.)

**E9 — LOW — :361–377.** `XDG_STATE_HOME` keeps its default, so every spawn writes `locks/<hash>.lock/{heartbeat,meta.json}` into the personal `~/.local/state/opencode`. The brew v2 daily driver shares that directory.
- The lock writes are VERIFIED in a temp environment. Possible contention with v2 is an ASSUMPTION.
- These are writes outside `$STACK_WORKDIR` that are not on the AGENTS.md exception list.
- Fix: redirect the state home per item, as the data home already is. (7af61ea appears to do this.)

**E10 — LOW.** No consumer honours `grade_excluded_reason` or `passed: null`.
- `$STACK_WORKDIR/m55/m55_report.py:15` (`1.0 if passed else 0.0`) counts an excluded row as a failure.
- Its `sum(x["passed"])` (line 27) raises a TypeError on `None`.
- `scoreboard` counts excluded rows in `n`.
- `run_m55.py` does not pass `--seed-base`, so it will fail closed (good).
- Fix: drop excluded items from both arms of a pair, and test that in the next chain's report.

**E11 — LOW — tests.**
- `_isolation_run` and `_run_with_mock` pop `plugin` and `mcp` and drop the `mlx-task` provider. They never exercise the real carrier, which is exactly why E1 went unseen.
- `_run_with_mock` does not redirect HOME, so it reads the real `~/.claude` and `~/.opencode`. No writes, by inspection (ASSUMPTION).
- No real-binary known-positive test exists for the CLAUDE.md switch.
- The C114 test patches `os.makedirs`, but `_make_bench_config_home` uses `Path.mkdir`. Its docstring still says "no directory creation".
- Mutation sensitivity of the overlay and resume tests is adequate: pointing the check at the client config is caught by `..._absent_from_the_bench_config`.

**E12 — LOW — docs and comments.**
- run_opencode_probe.py:876–886 says `--version` runs after the check and "we create no directory". Both are stale.
- :898 and :454 say "verbatim copy of the shipped config" (it is the bench carrier) and "the only file there" (false after discovery).
- :931 mentions "One extra spawn (`debug paths`)", which no longer exists.
- :608 says "global ~/.config/opencode expected to be the shipped file", which is stale.
- The lab notebook says "the only file there".
- `docs/open-questions.md`: the branch's C121 entry conflicts with main's. Main says "verbatim copy of the shipped `opencode_config/opencode.json`" and "M53/M54/M55"; the branch excludes M54. The branch also lacks C124 and C125, so the merge will conflict. Reconcile to the bench carrier.
- C125(3) ratifies only stat plus `--version`. Creating the config home before the router check, and opencode's own writes during discovery, need an exception recorded like C114's, in AGENTS.md M50 as well.

**E13 — LOW — :1143.** `opencode_config_sha256` (the client config, which the probe never uses) is in the resume identity. A change to the daily-driver config therefore refuses a resume for no reason. Fix: keep it recorded, drop it from the identity.

**E14 — INFO.** The title request goes to `small_model` (`mlx-task` at `localhost:8092`): Qwen2.5-1.5B, `max_tokens` 2048, no seed, outside M50 (VERIFIED). With the task server down there is no fallback to the main model (VERIFIED). The `model` key does not matter because `--model` is passed.

## Brief points not covered above

1. **Discovery environment:** cwd is the workdir, which is not a git repo. The env is `os.environ` plus `XDG_DATA_HOME=<workdir>/scratch/m50-discovery-xdg-data`, `XDG_CONFIG_HOME=cfg_home` and the policy switches. HOME, cache and state are inherited. It does resolve the bench home (VERIFIED by the test, and by my capture showing the carrier values).
2. **What survives a refusal:**
   - Router refusal: the config home (`opencode.json`, plus 61 MB from E1), the discovery data home, `~/.npm` entries, the plugin in `~/.cache/opencode/packages`, and `~/.local/state/opencode/locks`.
   - Version refusal: only `--version`'s mkdirs.
3. **What 1.18.30 reads from the cache home:** besides `models.json`, it reads `packages/<plugin>` (loaded only without `--pure`) and `bin/` (tool and LSP downloads; ASSUMPTION that it is used when the tool is not on PATH). The provider SDK is bundled: requests worked with no provider package installed (VERIFIED). The personal config is never read (the test plus my capture). Brew v2 is not run.
4. **Seed and sampling (VERIFIED):** the captured body under the bench home, with the real carrier, has `seed=4242` and every deployed field, and `max_tokens` = `limit.output` = 102400. `run --pure` does not load superpowers skills. The only skill in the prompt is the built-in `customize-opencode`.
5. **Per-item check (`debug config`):**
   - Parser: `out.index("{")` fails closed. A `{` in a preamble would cause a false refusal, which is safe.
   - The destination failure path uses `raise` and the overlay failure path uses `sys.exit`. Both exit nonzero and both stamp drift (see E6).
6. **Docker grading with `.git` present** (`_docker_grade` :757 mounts the whole work dir, including `.git` and `opencode.json`): `go test ./...`, `cargo test`, `npm-test.sh` and `gradlew` do not call git by default. Go stamps VCS information only when building main packages; exercism Go exercises are libraries. Container root with host-owned `.git` matters only if git is invoked. Everything here is an ASSUMPTION; the one known-positive grade per language is still owed.
