Round-1 disposition: T1, T2, T5, T9, T12 and most of T13 are resolved. T3, T4, T6–T8, T10 and T11 retain gaps identified below.

T14 — blocker — `docs/specs/m65-tg2-corpus.md:16-17,25`; `benchmark/bench/tg1_runner.py:310,320-349`; `benchmark/m62/universe_preflight.py:109-116`  
Failure: “tg1 identity untouched” is impossible if `structured_grade.py` is extended or `VERSION` becomes `m65-structured-v3`. tg1 hashes that file into `probe_code_sha256`, includes `sg.VERSION` in policy identity, and rejects its existing m62 universe when versions differ.  
Fix: put tg2 grading in a separately versioned module imported only by the tg2 runner, or explicitly accept a tg1 epoch/identity change and regenerate/review its artifacts.

T15 — blocker — `docs/specs/m65-tg2-corpus.md:34-37,56-62`; `benchmark/bench/structured_grade.py:380-421`; `rust/exercises/practice/forth/tests/alloc-attack.rs`  
Failure: the spec calls grader OOM infrastructure, but `rust/forth` deliberately detects bad implementations through explosive allocation. A model-caused OOM would abort rather than score a strict failure, selectively removing the hardest outcome. Existing tg1 correctly records `oom`/`mem_kill` as final scored outcomes.  
Fix: score container resource-cap exhaustion after successful launch as all-leaf model failure. Reserve transport abort for daemon, image, mount, runtime-launch, or externally attributed host failures.

T16 — high — `docs/specs/m65-tg2-corpus.md:28-37`  
Failure: “compile failure” versus “absent report with a clean build” is not operationally identifiable from the listed combined Rust, Java and Jest commands. A model syntax error can look exactly like a missing-report infrastructure failure; a missing runtime can be misgraded as model failure.  
Fix: require phase-typed launchers—setup, compile, execute, parse—with explicit evidence and fixtures for each terminal shape. Only setup failures and missing/malformed output after a clean execution abort.

T17 — high — `docs/specs/m65-tg2-corpus.md:42-45`  
Failure: reading metadata arrays does not define reference materialization. Real metadata is not generally pairwise: Java `connect` has one solution and four reference files; Rust has `Cargo.toml` listed as a solution but only one example; C++ has paired source/header examples. Copy-by-index or “copy every example over solutions” produces invalid reference trees.  
Fix: define path mapping per language and build a separate reference overlay. Validate every destination, keep Rust `Cargo.toml` protected, and specify that `file_changed` means any declared editable implementation path changed.

T18 — high — `docs/specs/m65-tg2-corpus.md:46-55`  
Failure: the Java helper allowlist permits arbitrary `src/main/java/**/*.java`. A model can add classes under `org.assertj.core.api` or JUnit namespaces and shadow assertion/framework dependencies, yielding expected passing leaves with no-op assertions.  
Fix: restrict new helpers to the package roots of the declared solution files and explicitly deny dependency/framework namespaces and duplicate test-visible classes.

T19 — high — `docs/specs/m65-tg2-corpus.md:65-71,81-93`  
Failure: build step 2 commits selected IDs and `n_lang` before the smoke and operator D1/D2 decisions. The artifact must then be rewritten post-decision or may encode the wrong language set/N, defeating pre-registration. “Hashed” also lacks canonical serialization and a runtime refusal check.  
Fix: freeze the valid universe first; after smoke and D1/D2, commit a canonical draw artifact and make every leg verify its SHA. Alternatively precompute immutable `{20,25,all}` candidate draws and select one by hash.

T20 — high — `docs/specs/m65-tg2-corpus.md:14-23,73-89`  
Failure: the estimand omits pick, matched budget, deployed sampling, seed schedules and the actual `s1/s2/reload` protocol, while cost assumes “2 picks × k=2 + reload.” Pairing and the meaning of each language × session cell are therefore undefined.  
Fix: pre-register two independent loaded sessions with distinct paired seeds, same-seed reload control, deployed sampling/thinking, and `acc_strict@budget` per pick × language × session, with sessions never pooled.

T21 — high — `docs/specs/m65-tg2-corpus.md:73-80`; `docs/PLAN.md:179`  
Failure: sizing cites discordance up to `9/22` but quotes ±25 pp at N=25, which assumes `p_d=0.20`; `p_d=9/22` gives approximately ±35.8 pp. It also drops the approved Python/Go pilot from the sizing inputs.  
Fix: report an explicit MDE table by language, N and assumed discordance; include the pilot for current-harness headroom/latency and use M55 plus tg2 smoke only as disclosed sensitivity bounds.

T22 — high — `docs/specs/m65-tg2-corpus.md:14-23,81-89`  
Failure: the design omits the required subjective-quality measure. Execution results cannot substitute for the mandated two-provider blind pairwise panel, and the panel cannot be reconstructed unless exact final code is retained.  
Fix: retain hashed final solution trees and add the two-judge, both-orders, length-adjusted panel over execution-passing outputs, including its cost and provenance.

T23 — medium (build) — `docs/specs/m65-tg2-corpus.md:46-49`; `rust/exercises/practice/macros/tests/macros.rs:177-213`  
Failure: root `Cargo.lock` generation does not cover `rust/macros/tests/invalid/Cargo.toml`; ignored tests run a nested `cargo build --offline`, unconstrained by the root `--frozen`.  
Fix: discover all protected manifests invoked by tests, generate and protect a lockfile beside each, and validate them offline in the pinned image.

T24 — medium (build) — `docs/specs/m65-tg2-corpus.md:38-41`  
Failure: Java has one bare `@Disabled` in `forth`; the other hundreds use `@Disabled(...)`. A quoted-form rewrite leaves a skipped leaf. JavaScript’s two `test.skip` cases are explicitly optional, expensive tests, unlike normal `xtest`/`xit` cases.  
Fix: test both Java annotation forms and make inclusion of optional JS tests an explicit policy, verified by stable reference runs rather than a blind textual substitution.

T25 — medium (build) — `docs/specs/m65-tg2-corpus.md:30,56-59`  
Failure: Java has three dependency closures: the common JUnit/AssertJ graph, `hangman` with RxJava, and `rest-api` with `org.json`. Seeding only the common graph makes those two items fail offline.  
Fix: image acceptance must execute all three dependency variants with an empty writable Gradle cache under `--offline`.

T26 — medium — `docs/specs/m65-tg2-corpus.md:70-71,91-93`  
Failure: the unexplained `<20` rule silently drops a language before the operator’s D1 choice and defines no minimum surviving language set. This can materially change approved scope without a decision.  
Fix: record `N_actual`; require explicit operator acknowledgement for any language below 20 and define whether the campaign proceeds if one or more languages are lost.

VERDICT: AGREE WITH CHANGES T14,T15,T16,T17,T18,T19,T20,T21,T22,T23,T24,T25,T26
