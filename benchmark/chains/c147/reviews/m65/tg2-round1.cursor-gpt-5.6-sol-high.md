Review of `a44b4b18`. The proposal is not launchable as written.

T1 — blocker — `docs/specs/m65-tg2-corpus.md:27`  
Failure: C++ configure never sets `EXERCISM_RUN_ALL_TESTS`; 25/26 exercises guard most cases behind that macro. Universes would contain roughly one test per exercise. Default `cmake --build build` also executes the custom test target before the JUnit run.  
Fix: configure with `-DEXERCISM_RUN_ALL_TESTS=ON`, build only the exercise-slug target, then run it with `-r junit -o <private-report>`.

T2 — blocker — `docs/specs/m65-tg2-corpus.md:25`  
Failure: the corpus supplies Gradle 8.7 wrappers, while the parent image does not install global `gradle`. `gradle --offline test` therefore fails or uses an unpinned installation; the pre-seeded wrapper distribution is unused.  
Fix: use `bash ./gradlew --offline --no-daemon --rerun-tasks test`, with the exact wrapper distribution and Maven artifacts baked into the pinned image.

T3 — high — `docs/specs/m65-tg2-corpus.md:26,33`  
Failure: there are no JavaScript lockfiles, so “one `node_modules` per lockfile” produces none and `npx` may attempt a network install under `--network none`. Enabling only `xtest` is also incomplete: the corpus has 832 `xtest`, 23 `xit`, and 2 `test.skip` cases.  
Fix: build one digest-pinned dependency bundle—all 49 package dependency signatures match—invoke its Jest binary directly, and freeze-time rewrite every supported skip form into the protected prepared tree.

T4 — high — `docs/specs/m65-tg2-corpus.md:38-40`; `benchmark/m62/universe_preflight.py:39-48,69`  
Failure: V1b assumes exactly one solution and one example and copies one pair. Actual metadata includes two solution paths for every Rust/C++ item, multiple Java solutions/examples, Rust `forth` with two tests, and Java `ledger` with a test helper. Reusing V1b yields no valid universe or partial references.  
Fix: add language-specific multi-file reference materialization; freeze arrays of editable solutions/tests and define `file_changed` over all editable paths.

T5 — high — `docs/specs/m65-tg2-corpus.md:38-40`  
Failure: recording the stub baseline is insufficient. A deterministic reference plus a vacuously passing stub recreates C145 under another shape. Three reference runs also do not prove stable stub results or leaf identity.  
Fix: require `baseline_failing > 0`, identical collected leaves and verdicts across fresh reference runs, no skipped leaves, and repeated stable stub collection. List every exclusion and reason.

T6 — high — `docs/specs/m65-tg2-corpus.md:23-28`  
Failure: parser identities are underspecified. Rust bare test names collide across binaries; Jest titles collide without file plus `fullName`; duplicate pass/fail events can become passes unless failure wins. Compile failures and missing reports also need different treatment from infrastructure failures.  
Fix: define canonical language-specific leaf IDs, failure-precedence, expected-leaf matching, skipped-as-failed semantics, and fail-closed report classification. Retain all raw reports and build output by hash.

T7 — high — `docs/specs/m65-tg2-corpus.md:35-37`  
Failure: the protected list is not complete. Test data fixtures, all original non-solution files, model-created `build/`, `target/`, `node_modules/`, alternate Babel/Gradle/CMake configs, extra test files, and framework-namespace shadowing can alter or spoof grading.  
Fix: protect every prepared non-editable file; add per-language allowlists for legitimate new implementation helpers and deny everything affecting tests/builds. Explicitly state the threat model for malicious code inside declared solution files.

T8 — medium — `docs/specs/m65-tg2-corpus.md:24,35`  
Failure: all 30 Rust configs classify `Cargo.toml` as a solution, yet the proposal says it is protected; no exercise has `Cargo.lock`. Offline resolution is image-dependent and current protection logic would exempt `Cargo.toml`.  
Fix: explicitly override metadata so `Cargo.toml` is protected, generate and protect lockfiles during preparation, and run Cargo with `--frozen`.

T9 — high — `docs/specs/m65-tg2-corpus.md:51-53,65-66`  
Failure: “M64 pooled claim” conflicts with the rule against cross-language ranking and with approved M64, whose estimand is three scaffold arms and is an estimation screen. A tg2 opencode headroom chain is not an M64 baseline because M64 has a different epoch, compaction policy, schedule and treatment.  
Fix: report only language × session cells; any aggregate is descriptive. Moving M64 to tg2 requires a formal M64 amendment before running it, and earlier tg2 rows must remain non-poolable.

T10 — high — `docs/specs/m65-tg2-corpus.md:48-53`  
Failure: the Python/Go pilot does not estimate Rust/Java/JavaScript/C++ discordance. The tg1 stability value 0.041 is especially optimistic for the harder corpus; M55 per-language reload discordance ranges from 1/22 to 9/22. At N=25, paired MDE is roughly ±25 pp, nowhere near ±5 pp.  
Fix: size each language from language-specific conservative discordance scenarios and label N=25 an estimation screen, not an equivalence or confirmatory design.

T11 — medium — `docs/specs/m65-tg2-corpus.md:42-46`  
Failure: the draw rule is conceptually model-independent, but seed and N alone do not freeze a mutable valid set. Behavior when fewer than N items survive is undefined.  
Fix: commit a hashed draw artifact containing corpus/universe hashes, sorted valid IDs, exclusions, N, seed and explicit selected IDs. Define a minimum-valid threshold and halt/drop-language rule. M55 overlap itself is acceptable.

T12 — medium — `docs/specs/m65-tg2-corpus.md:50-53`  
Failure: 45 hours is plausible only as a point estimate. P223’s current harness averaged 6.06 minutes but had a 19.3-minute p95 and 61-minute maximum; compiled grading now occurs after completed requests and adds unmeasured overhead.  
Fix: budget 45 hours as a lower-bound estimate, publish a heavy-tail range after four-language smoke data, and include model loads, A4, auditing, grading and recovery.

T13 — medium — `docs/specs/m65-tg2-corpus.md:29-32`  
Failure: `--network none` correctly isolates container execution, but the full boundary is unspecified. Docker may pull a missing image, writable shared caches can poison later grades, and the agent itself remains network-enabled under the tg1 policy.  
Fix: verify the full image digest locally, use `--pull=never`, avoid writable cross-item caches, mount only work plus private reports, and explicitly inherit P201 auditing for agent-phase web/shell traffic.

VERDICT: AGREE WITH CHANGES T1,T2,T3,T4,T5,T6,T7,T8,T9,T10,T11,T12,T13
