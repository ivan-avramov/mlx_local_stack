# Implementer report — S29 tg2 testable (spec `docs/specs/s29-tg2-testable.md` v1.1)

Baseline `cd334f773e6bc6d1e2f9f1344755e4df787b4fef`. Nothing committed, staged only by the export command.
Candidate diff: `out/candidate-1.diff` (the brief's export, `-- benchmark`) **plus** `out/candidate-1.configgen.diff`
(one file outside `benchmark/`, see F1 below — the brief's export cannot see it).

## Findings first (things the designer must look at)

- **F1 — one change lives outside `benchmark/`.** The tg2 carrier is a configgen output (`configgen/targets.py` →
  `emit_opencode_bench_v2_web_tg2`). Hand-editing the JSON would drift `configgen check`. I changed the emitter
  (`configgen/emitters/opencode.py`) and regenerated only the tg2 target; `configgen check` reports no drift on any target. The
  brief's `git diff -- benchmark` export does not include that file, so it is exported separately as
  `out/candidate-1.configgen.diff`. Apply both.
- **F2 — the goal's premise is half true.** JavaScript (`xtest`/`xit`/`xdescribe` → `test`/`it`/`describe`) and Java
  (`@Disabled` removed) were ALREADY rewritten at freeze time by `tg2_materialize.prepare_tree` (the universe records it,
  `rewrites`). Only Rust (`#[ignore]`) and C++ (the `EXERCISM_RUN_ALL_TESTS` guard) shipped partly disabled. For JS / Java, T1
  needed no workspace change; they got T2 (the command in the prompt), T3 and the proofs.
- **F3 — "any letter case" is implemented as "every per-word case form", not arbitrary mixed case.** opencode's matcher is
  case-sensitive with no character classes. Each deny form is emitted with the first letter of every word as `?` and the rest
  lower or UPPER per word, all combinations, plus brand spellings (`GitHub`, `SourceGraph`, `SearchCode`,
  `GitHubUserContent`, `JsDelivr`). So `exercism.org`, `Exercism.org`, `EXERCISM.ORG`, `eXERCISM.Org`, `GitHub.com/Exercism`
  are denied; an obfuscated `ExErCiSm.org` is not. Consistent with the spec's threat model sentence; the designer should
  confirm it reads that way.
- **F4 — the shell deny moved from "the word" to "lookup forms".** webfetch keeps the broad `*xercism*` / `*XERCISM*`
  (a fetched URL is never local). Shell now denies: the Exercism hosts (`exercism.org`, `exercism.io`, any subdomain), the
  org on GitHub (`github.com/exercism`, `github.com:exercism`, `githubusercontent.com/exercism`, `github.com/repos/exercism`,
  `jsdelivr.net/gh/exercism`), `problem-specifications` (still broad: no build/test command contains it), the code-search
  sites (now with case forms; before they were lowercase only), and anchored forms `gh repo * exercism/*`,
  `gh api *repos/exercism/*`, `gh search *`, `*install exercism*`, `exercism *` (the Exercism CLI). **Added** beyond the old
  carrier: `gh search *` (CLI code search) and the CLI / install forms. **Not covered** (a lookup without a host or the org
  path): e.g. `npx degit exercism/rust`, a mirror under another host/org that is not named `problem-specifications`.
- **F5 — no real opencode binary on this box** (`$STACK_WORKDIR/opencode-2.0.20` absent), so T3 / T4 are proven with the
  carrier's own matcher ported to Python (`bench.tg2_testable.wildcard_match`, checked equal to the repo's existing faithful
  port `tests/test_m61_round7.match`; last match wins; each parsed command and the whole line decided, any deny denies). The
  per-command split is my approximation of opencode's tree-sitter split (a superset: whole line + `&&`/`||`/`;`/`|`/`&`/newline
  parts + `$(...)`/backtick bodies). A real-session check of T3/T4 should run in phase 2 (the positives now record it).
- **F6 — I1 keeps the scaffold label.** The label stays `opencode-v2-web-tg2` (it is hard-coded in ~20 refusal/selection sites,
  as in the S27 rotation). The identity VALUES move: `scaffold_policy_sha256` (new carrier sha + a new
  `corpus_identity.workspace` block: `testable` version, `hints_sha256`, the four full-suite commands), `probe_code_sha256`
  (closure holds `corpus_tg2.py`, `tg2_materialize.py`, and the carrier as identity data) and the pairing composite
  `generation_identity_sha256`. Shown to refuse pooling (`tg1_pairing.pair_rows` → `generation_mismatch`; the positives record
  of the old identity → "scaffold_policy_sha256 differs from the probe's live identity"). If the designer wants a new label
  too, that is a mechanical but wide change.
- **F7 — acceptance 6 is recorded, not enforced.** The positives record gains `testable` (lookup record on the worktree's
  carrier + per-language full-suite record from that language's positives sessions). It never adds a problem and
  `positives_problems` (v8) does not require it: making it a freeze requirement would break the frozen positives tests (not in
  the "may change" list) and the inject sessions are not guaranteed to run a test. Whether phase 2 should enforce `ran` /
  `all_denied` is the designer's call.
- **F8 — JS T1 needs network.** `npm install` fetches jest/babel from the npm registry (the prompt says
  `npm install && npm test`). On this box it worked (the real run passed). An offline box would make the JS command fail
  before testing; the Java run likewise downloaded Gradle + JUnit into a test-local `GRADLE_USER_HOME` (no prefilled bench
  Gradle home exists here; the agent gets the S26 prefilled one).

- **F9 — the A8 panel rebuilds prompts with current code.** `p426_panel.a8_prompt` calls `corpus_tg2.prompt`, so under
  the new code every pre-S29 A8 row's prompt check REFUSES (rebuilt ≠ recorded). That is consistent with "never pool"
  (A8 is SUPERSEDED, rerun under M85), but if anything still needs to panel-check old-identity rows, the panel needs an
  identity-aware prompt rebuild. I did not change the panel; I changed the two tests that check recorded old exports.

## Mechanisms chosen

**T1 (prepare-time enabling, not a test-command configuration).** `tg2_materialize.enable_full_suite(tree, lang, solutions)`
(new; `prepare_tree` and `VERSION` untouched, so the frozen universe, its freeze, the panel's A8 start tree and the Gradle
prefill are byte-identical):
- Rust: every line that is exactly `#[ignore]` is removed from every non-solution `.rs` file (620 attributes across the
  universe; all of the one form).
- C++: in non-solution `.cpp/.cc/.h/.hpp` files that mention the macro, the `#if defined(EXERCISM_RUN_ALL_TESTS)` /
  `#ifdef EXERCISM_RUN_ALL_TESTS` line and its MATCHING `#endif` are removed (directive nesting tracked; an `#else`/`#elif`
  branch or a missing `#endif` is a FreezeError, never guessed; `test/catch.hpp` is never parsed).
- JS / Java: nothing (already enabled at freeze).
- `full_suite_violations` (new): any remaining Rust `ignore` attribute (any form, incl. inline), any remaining
  `EXERCISM_RUN_ALL_TESTS` reference in C++ test-side files, JS/Java skip forms (`tg2_grade.skip_form_violations`).

`Tg2Corpus.prepare` now: materialise → **verify against the universe's frozen `prepared` first (unchanged guard)** →
`_make_testable` → git init / freeze mtimes → verify the tree still equals the testable manifest. `_make_testable` checks the
recorded facts: same file set; the changed files are exactly the files the rewrite reports; none is a solution, a build file
(`Cargo.toml`, `CMakeLists.txt`, `build.gradle`, `package.json`) or outside the protected manifest; no violation left. Any miss
→ `TransportAbort`. The item's `PreparedItem.prepared` / `.protected` are the testable tree's (so the tamper rule protects the
rewritten tests; the agent's `git checkout`/`git diff` see no pending change because the rewrite precedes `git init`). The
grader's commands are unchanged: `--include-ignored` / `-DEXERCISM_RUN_ALL_TESTS=ON` are now no-ops on these trees.

**T2.** `corpus_tg2.FULL_SUITE_COMMANDS` = rust `cargo test`, java `./gradlew test`, javascript `npm install && npm test`,
cpp `cmake -S . -B build && cmake --build build` (the CMakeLists' `test_<slug>` ALL target runs the binary on every build).
Each `HINTS[lang]` = the old sentence + "`<cmd>` runs the full test suite your solution is graded on." (cpp: "builds and runs").
The prompt still ends with `HINTS[lang]` (the panel's `a8_prompt` contract holds).

**T3 / T4.** configgen `tg2_permissions` (see F4). The tg1 carrier is byte-identical to baseline (tested).

**K1.** `p426_reconcile._trailing_failed_at_kill`, tried in the kill `inflight_failed` branch only when the in-flight evidence is
absent and the S27 X2 anchor did not match (X2 keeps its clean class). Facts required: `in_flight_at_kill == 0` and
`worker_summary_before.in_flight == 0`; from `termination.worker_summary_before` to `worker_summary_after`:
`requests_started` +1, `requests_failed` +1, `requests_completed` +0; the window's one failed line is its last,
`stream_closed_before_completion`, directly after its own `Request started`, `|S| = |C| + 1`; the worker's `last_error`
(STREAM_CLOSED) time ≥ `signal_at`. Then `inflight_evidence` holds and a new check `kill_trailing_failed` FAILS with the facts in
`late_record` (shape `trailing_failed_at_kill`); `kill_trailing_failed` is added to `ACCOUNTING_CHECKS`, so `fault_class` =
`accounting` and the done hook returns `accounting_fault` with the sealed sidecar (existing machinery; `p426_hooks.py` needed no
change). Anything else keeps today's class.

**Acceptance 6.** `bench/tg2_testable.py` (new): matcher, `split_commands`, `shell_decision`, `FULL_SUITE_VARIANTS`,
`LOCAL_WORD_COMMANDS`, `LOOKUP_SHELL` / `LOOKUP_WEB` per deny class, `lookup_record`, `full_suite_record`.
`p426_wave2.cmd_positives` collects the retained run of every inject positive (`positive_entry(..., runs=)`) and records
`testable = {version, lookup, full_suite[lang] = {ran, calls[command (home → ~, workdir → $STACK_WORKDIR), status, decision,
kind], sources, denied}}`; an exception there is recorded, never raised.

## Files

Production: `benchmark/bench/tg2_materialize.py`, `benchmark/bench/corpus_tg2.py`, `benchmark/bench/p426_reconcile.py`,
`benchmark/bench/p426_wave2.py`, `benchmark/bench/tg2_testable.py` (new), `benchmark/opencode_bench_v2_web_tg2.json`
(regenerated), `configgen/emitters/opencode.py` (outside the export, F1).
New tests: `benchmark/bench/tests/test_s29c_impl_{workspace,carrier,k1,identity,positives,local_run}.py`.

## Existing tests changed (each pins the old carrier / prompt / workspace-identity)

| test | why |
|---|---|
| `test_m76_b4b1_impl_probe.py::test_the_tg2_carrier_is_generated_and_equals_tg1s` | pinned tg2 carrier == tg1 bytes; now: equal except `permissions` (the difference is pinned in `test_s29c_impl_carrier`) |
| `test_m76_b4b1_fe_chain.py::test_carrier_is_tg1s_with_the_tg2_label` | same pin (flattened diff); `permissions` excluded |
| `test_m76_b4b1_impl_corpus.py` `HINTS` (→ `test_the_prompt_is_the_specs_exact_bytes[*]`) | pinned the old helper sentences |
| `test_m76_b4b1_impl_corpus.py::test_prepare_is_the_frozen_universe_item` | pinned prepared == frozen manifest; now: same file set, only `tests/say.rs` rewritten, protected from the testable manifest |
| `test_m76_b4b1_impl_corpus.py::test_the_grade_call_and_its_arguments` | pinned `prepared=entry["prepared"]`; now the testable manifest |
| `test_m76_b4b1_fe_corpus.py::test_prepare_pilot_item_matches_the_frozen_universe[*]` | same frozen-manifest pin; now: same files, rewritten ⊆ tests, rewritten iff rust/cpp |
| `test_m76_b4b1_fe_support.py` `HELPER_TEXT` (used by `test_m76_b4b1_fe_corpus` prompt tests) | pinned the old helper sentences |

## Commands and results

All via `../fe_test.sh stack <args>` (cwd = the copy).

| run | result |
|---|---|
| `test_s29c_impl_workspace.py`: T1 static proof on all 149 valid items + refusal / C++ rewrite units + T2 | all pass (161) | <!-- allow-shorthand -->
| `test_s29c_impl_carrier.py`: T3 for every item × variant, T4 per deny class, local words, known positive (the 3 recorded denied cpp commands: denied by the old carrier, allowed now), no configgen drift, tg1 carrier byte-identical to baseline | 222 passed |
| `test_s29c_impl_k1.py`: P16 shape → `accounting` (reconcile and done hook → `accounting_fault` + sidecar), 10 out-of-K1 shapes → `integrity`, X2 still clean | 15 passed |
| `test_s29c_impl_identity.py`: workspace binding, old ≠ new (`scaffold_policy_sha256`, carrier sha, composite), no pairing, old positives record refuses, each bound part moves the hash, closure holds the modules | 9 passed |
| `test_s29c_impl_positives.py`: acceptance 6 record | 4 passed |
| `test_s29c_impl_local_run.py`: rust/say, javascript/word-search, java/zipper, cpp/spiral-matrix, reference + known negative, host toolchain + the real `tg2-grader:m65-v1` in docker | 4 passed (none skipped; Java downloaded Gradle, JS ran `npm install`) |
| Final run: the 175 existing test files that touch a changed module, plus all of the above, `--basetemp=/private/tmp/s29c-bt2` | **5630 passed, 1 failed, 58 skipped** |
| Red-first, scratch (not in the diff): the key assertions against the BASELINE sources via `git show` | 7/7 hold on baseline: P16 → `integrity` (only `inflight_evidence` fails); the three cpp commands denied; HINTS name no command; prepare = frozen tree (Rust `#[ignore]` / C++ guard present); no `workspace` identity; tg2 carrier == tg1 bytes; no `testable` record |

The 1 failure: `test_m64_arm_closure.py::test_the_tg1_carrier_and_plugins_the_arm_wraps_are_unedited_by_this_build` fails with
`GateError: no pushed base: GATE_PUSHED_BASE is unset and the origin … is not the canonical stack remote`. That is the clone's
environment, and the test stops there, before it compares any content. Setting `GATE_PUSHED_BASE` here needed approval, so I
could not rerun it. What it guards (the tg1 carrier is unedited) is shown directly by
`test_s29c_impl_carrier::test_the_tg1_carrier_is_unchanged_from_the_baseline` (byte-identical to `cd334f773`). I did not run it
on the baseline.
Skips: 57 need the bench opencode 2.0.20 binary (absent here), 1 needs branch `tg2-step2`. They are the same environment skips
as on baseline (not caused by this change).
In the first related run (default basetemp, under the home directory),
`s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path` also failed. The cause
is the wrapper's temp dir under `$HOME` (the host fingerprint's fake bin dirs carry it). It passes with a basetemp outside home;
my `testable` record is not the leak.

Additional existing tests changed after the first related run (also pins of the old workspace / prompt):

| test | why |
|---|---|
| `test_m76_b4b1_fe_grade.py::test_grade_call_arguments[rust, cpp]` | pinned `prepared == entry["prepared"]` (frozen); now the testable manifest, same file set |
| `test_m76_b4b2_impl_golden.py::test_pilot_export_prompt_check`, `test_m76_b4b2_fe_real.py::test_the_real_pilot_exports_pass_the_prompt_check` | they check RECORDED pre-S29 A8 exports against a prompt rebuilt by current code; now they rebuild with the pre-S29 helper sentences (`test_s29c_impl_identity.PRE_S29_HINTS`, verbatim baseline), i.e. the identity those exports were generated under — see F9 |

## What I could not satisfy / not done

- No real opencode session for T3/T4 (no binary; F5). Matcher-based only.
- Arbitrary mixed-case obfuscation of lookups is not denied (F3).
- Acceptance 6 is recorded, not enforced (F7); the "agent ran the full suite" record is only as good as the positives sessions
  (an inject session may never reach a test run).
- The real-universe docker T1 run (every item) is the designer's; I ran the real grader on one item per language and the
  static proof on all 149 valid items. <!-- allow-shorthand -->
- Red-first: I could not create a baseline worktree / archive without approval, so the red evidence is an in-process run of
  the key assertions against the baseline sources read with `git show` (scratch, not in the diff): see results.
