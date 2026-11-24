# Test-writer report, delivery 2 — S29 tg2 testable, candidate 1

**Verdict: fix then merge.** The candidate meets the spec's core (T1, T2, T3, K1, I1, tamper rule) and regresses nothing I could observe. The fixes are small and are about the anti-lookup denies (F-A, F-B, F-C below). Nothing needs rejecting.

Setup: both diffs applied cleanly from the copy root (`git apply --check` then `git apply`; candidate-1.diff, then candidate-1.configgen.diff). Frozen hashes verified before the run (`shasum -a 256 -c .fe-material/FROZEN.sha256`: 9 of 9 OK). The test directory was not edited. The implementer's `test_s29c_impl_*` files are in the working tree as untracked files from the diff.

## 1. Frozen tests: baseline vs candidate (`../fe_test.sh stack bench/tests/s29c_frozen`, docker included)

| | tests | passed | failed | skipped | errors |
|---|---|---|---|---|---|
| baseline (delivery 1, final run) | 655 | 251 | 404 | 0 | 0 |
| candidate (`out/frozen-cand.xml`, `out/run-cand-frozen.txt`) | 655 | 644 | 11 | 0 | 0 |

Nothing that passed on the baseline fails on the candidate (the 11 failures are among the 404 baseline failures).

Per area on the candidate: T2 (149 prompts) pass; T3 stated-command-allowed (149) pass; T1 static rust 27/30, cpp 25/26 (the rest below); T1 docker 23/24; K1 9/9; I1 9/9; tamper rule 20/20; T4 all pass. Docker ran for real (the tg2-grader image and the corpus were present): rust, java, cpp run the full graded suite locally, the real grader passes exactly the graded leaves, tamper is clean after the stated command and its variants, known negatives fail locally and in the grader. <!-- allow-shorthand -->

### The 11 failures: is the test over-specific or the candidate wrong?

| # | frozen test | cause | verdict |
|---|---|---|---|
| 1 | `t1_docker::…locally[javascript]` | The candidate's JS command is `npm install && npm test`; my docker harness runs `--network none`, so `npm install` fails (`EAI_AGAIN registry.npmjs.org`), and it also replaced my pre-linked `node_modules`. | **Test/harness limitation, not a candidate error.** The spec leaves the mechanism free and an agent has the network. Consequence: I have **not observed** the JS full-suite run on the candidate; only the implementer's own `test_s29c_impl_local_run` (javascript/word-search, host + grader image, run in my related-modules run: passed) covers it. See F-D. |
| 2–4 | `t1_static::rust[doubly-linked-list, wordy, xorcism]` (`cargo test` runs 21 of 19, 25 of 23, 12 of 8) | The extra tests are `#[cfg(feature = "…")]`-gated (e.g. wordy `exponentials`, xorcism `io`; confirmed by reading the prepared trees in a temporary debug test, since removed). My static parser counts them as enabled; cargo does not compile them without the feature, and the grader's leaf set excludes them. | **Test over-specific (my parser bug).** Candidate is right. | <!-- allow-shorthand -->
| 5 | `t1_static::cpp[crypto-square]` | The candidate removed the macro guard completely (confirmed: no `#if` left in the prepared test file). My parser misses two TEST_CASE names that are split across adjacent string literals. | **Test bug.** Candidate is right. |
| 6–11 | `t3 … local flag/file/path … [./gradlew test -Dexercism.local=true; ls problem-specifications-notes; cat ~/problem-specifications/README.md]` and the same three chained with a build (`…chained…`) | (a) `-Dexercism.local=true` is denied: the case-form trick uses `?` for the first letter of each word, so `exercism.io` is emitted as `*?xercism.?o*` and matches `exercism.lo…` (any local file/flag `exercism.lo*`, `exercism.?o*`). (b) The shell deny `*problem-specifications*` stayed broad, so a local path with that word is denied (the implementer documents it as F4). | (a) **Candidate wrong** (spec: "a local build flag, file or path that merely contains the word is not a lookup and is allowed"). (b) **Mostly over-specific**: my P4 reading (a local `problem-specifications` directory); the candidate's trade (no build/test command contains the word) is defensible, but it contradicts the sentence as written — the designer decides. |

## 2. Existing modules (exact counts, `out/related-cand.xml`)

Selection: every test file that mentions `tg2_materialize`, `corpus_tg2`, `p426_reconcile`, `p426_wave2`, `p426_hooks`, `p426_panel`, `tg2_testable`, `configgen` or the tg2 carrier (135 files by search; run as 91 explicit files + the `configgen/tests` dir + the `s26_frozen`, `s29_frozen`, `s29b_frozen`, `p586_frozen`, `p613s3`, `p613s4` dirs; the list is `out/related-args.txt`; the implementer's `test_s29c_impl_*` files are in it).

**4389 tests: 4387 passed, 1 failed, 1 skipped, 0 errors** (2446 s).
* The 1 failure: `s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path` — the pytest temp dir sits under the home directory (the host fingerprint's fake bin dirs carry it). It passes (all 66 tests of the module) with `--basetemp=/private/tmp/tw2-bt`, as the implementer reported. I did **not** run it on the baseline; the cause is the path of the temp dir, not code the candidate changed. Not counted as a regression.
* The 1 skip: the bench opencode 2.0.20 binary is not installed (schema capture).
* Not run: the other ~170 test files that do not mention the changed modules (the implementer reports 5630 passed over 175 files incl. these); the `GATE_PUSHED_BASE` test `test_m64_arm_closure.py::…tg1_carrier…` the implementer could not run (it was not in my file selection either). The tg1 carrier byte-identity is covered by the implementer's `test_the_tg1_carrier_is_unchanged_from_the_baseline` (passed in my run).
* Baseline pass → candidate fail: **none observed.**

## 3. Review against the spec and the threats

**T1 / workspace (good).** `enable_full_suite` removes only exact `#[ignore]` lines (rust) and the macro `#if` + matching `#endif` (cpp) in non-solution files; JS/Java unchanged (already enabled at freeze — consistent with my P1 in delivery 1). It runs after the frozen-manifest check; `_make_testable` verifies the file set, that only reported test-side files changed, no solution/build file, and no skip form left (`corpus_tg2.py` `_make_testable`), so it fails closed (`TransportAbort`) on `#[ignore = "…"]`, `#else` in a guard, a missing `#endif`. Real runs: the stated commands run exactly the graded leaves (rust accumulate 12, cpp all-your-base 17 — frozen docker tests).

**Tamper rule with the rewritten tests (good).** The item's `prepared`/`protected` are the testable manifest; frozen `test_s29c_tamper_rule` passes (editing a test file, adding a test file, editing a build file are tampering; editing the solution is not), and the docker tests show no reasons after the stated command and its variants. Re-adding `#[ignore]` or the guard is tampering (the rewritten file is protected). No weakening found. `test_m76_b4b1_*` pins were changed to compare against the testable manifest with the assertion that only test-side files differ (rust/cpp only) — a faithful update, not a weakening.

**I1 (acceptable).** The label stays `opencode-v2-web-tg2` (F6); identity values move: the corpus identity gains `workspace` (`TESTABLE_VERSION`, hash of the exact helper sentences, the four commands), the carrier sha changes, the probe closure includes the changed modules. Frozen I1 tests pass, including old vs new policy hash, `provenance.is_compatible` refusing to pool, and "binds the helper sentences" (hash computed at call time). Not tested by me: the other ~20 sites that key on the label (pairing: the implementer shows `tg1_pairing.pair_rows` → `generation_mismatch`).

**K1 (good, class boundary tight).** `_trailing_failed_at_kill` (`p426_reconcile.py`) requires: kill case, `in_flight_at_kill == 0` and `worker_summary_before.in_flight == 0`, summaries' started +1 / failed +1 / completed +0, exactly one failed line which is the window's last, `stream_closed_before_completion`, directly after its own `Request started`, `|S| = |C|+1`, failure time ≥ `signal_at`; tried only when X2 did not anchor. It adds a failing check `kill_trailing_failed`, in `ACCOUNTING_CHECKS`, so the class is `accounting` (frozen K1 tests: the recorded shape → accounting; started-0, completed+1, failure-before-signal, two failures, in-flight-at-pre-signal, no-kill-markers keep today's classes — all pass). I did not run the hook-level `accounting_fault` disposition myself (the implementer's `test_s29c_impl_k1` does, and passed in my related run).

**Anti-lookup denies — what a cooperative agent could still get through** (the tg2 carrier shell rules; evaluated by the frozen evaluator under all four readings; probes in a temporary debug test, removed):

* **F-A (medium) — GitHub org / user API not denied.** `curl -s https://api.github.com/orgs/exercism/repos`, `curl -s https://api.github.com/users/exercism`, `gh api orgs/exercism/repos` are **allowed** (forms cover `github.com/exercism`, `github.com/repos/exercism` and `gh api *repos/…` only). Org-listing is a path to repository names, then the clone forms are denied, but `curl https://api.github.com/repos/…` is denied — so the practical hole is the org listing; the contents of a solution still cannot be fetched by the covered forms. Also `npx degit exercism/rust` and `npm i exercism` (known, F4). Webfetch is unaffected (the broad `*xercism*` rule stays).
* **F-B (medium, depends on the engine) — the anchored CLI patterns have no leading `*`:** `gh repo * ?xercism/*`, `gh api *repos/?xercism/*`, `gh search *`, `exercism *` (`configgen/emitters/opencode.py`, `TG2_SHELL_ONLY`). Under a node-by-node engine they deny; under a whole-command engine `cargo test && gh repo clone exercism/rust` or `cd /tmp && gh repo clone exercism/rust` is **allowed** (frozen-evaluator readings `whole/*` = allow; `nodes/*` = deny). The implementer decides on whole line + parts (F5), and no real opencode binary was available to either of us, so which engine opencode uses is **unverified**. Cheap fix: also emit a `*`-prefixed variant of each.
* **F-C (low–medium) — over-match false positives.** The `?`-for-first-letter trick makes the host forms match local names (`exercism.lo…`, `exercism.?o…`, e.g. `-Dexercism.local=true`, `cat exercism.log`, `ls exercism.local`, `cat exercism.org.txt`, `grep -r exercism.io .`) — spec says a local file/flag containing the word is allowed. `cat exercism.json`, `.exercism/config.json`, `~/exercism/rust`, `-DEXERCISM_RUN_ALL_TESTS=ON` are allowed, which is the case that mattered (cpp). Fix: anchor the host forms (`*://?xercism.org*` / `*//?xercism.org*` and the `.io` pair) instead of a bare substring. <!-- allow-shorthand allow-pii-pattern -->
* Covered and checked: curl / wget / git clone / git fetch / submodule / `gh repo` / python urlopen of `exercism.org`, `.io`, any subdomain, the GitHub org (https, ssh, `codeload`, `raw.githubusercontent`, jsdelivr), `problem-specifications` (any host), the code-search sites, `gh search`, `pip install exercism-cli`, in lower / Title / UPPER / per-word case, chained and piped; a web.archive.org wrapper of an Exercism URL is denied (substring). Not covered by design: obfuscated case (`ExErCiSm`), a mirror under another host/org not named problem-specifications (F3/F4).
* The code-search deny now has case forms (it was lowercase-only): my "UPPER host" frozen tests pass.

**Identity / prompt side effects.** F9 (the A8 panel rebuilds prompts with current code, so pre-S29 A8 rows' prompt checks refuse) is real by construction and consistent with "never pool"; the two recorded-export tests were changed to rebuild with the verbatim pre-S29 helper sentences. Flag for the designer: any later reader of old A8 rows needs that identity-aware rebuild (the implementer says the panel is unchanged).

## 4. Deviations and notes

* JS T1 depends on the network (`npm install`) (F8): a JS session on an offline box fails before testing. Java likewise needs Gradle/JUnit from the bench's prefilled home. Not a spec violation (the spec fixes no mechanism) but it makes T1-JS un-provable in my network-less container; the implementer's host run is the only observation.
* Acceptance 6 is recorded not enforced (F7): consistent with "gain a record"; the designer's call.
* My frozen tests that fail for test-side reasons are listed in §1; I did not change them (frozen). If the designer wants them corrected: the rust parser should honour `#[cfg(feature = …)]`, the cpp parser should join adjacent literals, and the HTTP-less JS docker test should run with the network or be skipped.
* No real opencode session was run by either of us (no binary); every T3/T4 statement above is about the rule set under a Python port, not the engine.

## 5. Fixes required before merge

1. **F-C**: anchor the host deny forms so local `exercism.*` names are allowed (turns frozen tests 6, 9 green).
2. **F-B**: add `*`-prefixed variants of the anchored CLI patterns (`gh repo`, `gh api`, `gh search`, `exercism`) so a chained command is denied under either engine reading.
3. **F-A**: add the `orgs/exercism` and `users/exercism` API forms (`github.com/orgs/exercism`, `github.com/users/exercism`, `gh api *orgs/?xercism*`, `*users/?xercism*`); optionally `degit`, `npm i`.
4. Designer decision (no code unless chosen): keep or narrow the broad shell `*problem-specifications*` (frozen tests 7, 8, 10, 11); and whether a real-opencode check of T3/T4 is a merge gate or phase 2 (the implementer proposes phase 2).

Optional follow-ups, not blocking: a JS network note in the helper sentence or prefill; the A8 identity-aware prompt rebuild (F9).

Raw outputs: `out/run-cand-frozen.txt`, `out/frozen-cand.xml`, `out/run-related-cand.txt`, `out/related-cand.xml`, `out/related-args.txt`.
