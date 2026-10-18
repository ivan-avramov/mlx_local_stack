# M65 step 2 — "tg2" harder agentic corpus (DRAFT v5, 2026-10-17; tiers per C168)

Status: DRAFT → Cursor `gpt-5.6-sol-high` review → operator. PLAN M65; C167 (P349). v2 applies Cursor round 1
T1–T13 (`benchmark/chains/c147/reviews/m65/tg2-round1.cursor-gpt-5.6-sol-high.md`); v3 applies round 2 T14–T26
(`tg2-round2…`) and round 3 T27–T28 (`tg2-round3…`, AGREE WITH CHANGES T27 T28). v1 = `a44b4b18`, v2 = `ae4aeb9d`,
v3 = `5e98a509`, v4 = `e97d34ee`. v5 folds in C168 (P356 as revised by its Cursor review): screen / decider tiers.

## Why

tg1 (43 Python + Go items) is saturated for both B picks (83–86/86 strict across P223, M63, c144-base; M64 power
simulation 0.000). Prior evidence of headroom: M55 (opencode 1.18, C37 22-item draws, k=2) scored the picks at
61–86 % on Rust / Java / JavaScript with per-session pick deltas up to +23 pp
(`benchmark/results/m55_polyglot_gap_report.md`). M55's harness differed (stall kills, sandbox rejections), so its
levels are indicative only.

## Scope and estimand

- Languages: Rust (30), Java (47), JavaScript (49), C++ (26), pinned polyglot corpus (`polyglot_sha` as tg1).
- Harness: the tg1 probe policy family under a new scaffold label `opencode-v2-web-tg2` (own
  `scaffold_policy_sha256`). **tg2 is a configuration of the shared core (T14, amended 2026-10-17 by C178 / P371):** tg2 has its own probe entry (`run_tg2_probe.py`), corpus (`bench/corpus_tg2.py` over `bench/tg2_grade.py` + `bench/tg2_materialize.py`, version `m65-tg2-v1`), label and chain configuration on the ONE item core (`bench/arm_runner.py`) and chain core (`bench/chain_core.py`; schedule `schedules.tg2_tier` over the frozen draw); the core is in every probe closure, so a core change moves the tg1, tg2 and M64 identities together (accepted, C178; campaign freeze P377 / C179). tg2 transport semantics = tg1's (P373). Agent-phase web and shell networking stay as tg1 and are
  audited by P201 (T13).
- **Protocol (T20):** per pick, two independent loaded sessions s1 / s2 with distinct paired seeds
  (`rowschema.sample_seed`, seed bases as tg1) plus a same-seed reload control (5 items per language), deployed
  sampling via `params_for(model, profile="deployed")`, thinking ON with the tg1 budget, predictor OFF, the tg1 gate
  ceilings; the ranking key is `acc_strict@budget` per pick × language × session; sessions never pooled.
- **Subjective quality (T22, T28, AGENTS.md / C166):** content-addressed snapshots of the exact final graded
  implementation tree (bytes, not only hashes) retained per row; no final tg2 comparison or recommendation is complete
  until the panel has run — until then every tg2 report is labelled "pending subjective review"; the two-provider blind
  pairwise panel (both orders, length-adjusted) runs over execution-PASSING outputs once the M64 panel build exists;
  judge model ids, client versions and prompt sha recorded per verdict; cost reported with the sizing.
- **Estimand (T9):** per language × session cells only (strict, conv, nonconv kinds, tokens/task); never blended
  across languages or with tg1; any aggregate is descriptive. tg2 is an **estimation screen**, not an equivalence or
  confirmatory design (T10). A tg2 opencode chain is not an M64 baseline: moving M64 to tg2 needs a formal M64 spec
  amendment before M64 runs, and tg2 rows from other epochs stay non-poolable with M64.

## Grader (`bench/tg2_grade.py`, version `m65-tg2-v1`; `structured_grade` unchanged)

| Lang | Command (in the grading container) | Leaf report |
|---|---|---|
| Rust | `cargo test --frozen --offline --no-fail-fast -- --include-ignored` | libtest lines; leaf id = `<test binary>::<path::name>` |
| Java | `bash ./gradlew --offline --no-daemon --rerun-tasks test` (corpus wrapper 8.7; distribution + Maven artifacts baked into the image) | JUnit XML `build/test-results/test/*.xml`; leaf id = `<classname>#<name>` |
| JavaScript | `<bundle>/node_modules/.bin/jest --ci --json --outputFile=<private>` (one digest-pinned dependency bundle: all 49 `package.json` dependency signatures match; no `npx`) | jest JSON; leaf id = `<test file>::<fullName>` |
| C++ | `cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON`, `cmake --build build --target <slug>`, `./build/<slug> -r junit -o <private>` (Catch2) | JUnit XML; leaf id = `<classname>#<name>` |

- **Phase-typed launch (T16):** each grade runs as separate container steps — setup (image present by digest, mounts,
  runtime launch), compile (`cargo test --no-run`, `gradlew compileTestJava`, jest `--listTests` + babel transform,
  `cmake --build`), execute, parse — each with its own exit code, stdout/stderr and timing retained by sha256.
- **Outcome classes (T6, T15):** a leaf with any failure event is failed (failure wins over pass); a skipped / ignored /
  missing expected leaf counts as failed; a compile-phase failure fails every leaf (model outcome); a resource-cap
  exhaustion after a successful launch (container OOM, memory kill, timeout) fails every leaf (model outcome — e.g. Rust
  `forth`'s `alloc-attack` tests detect bad implementations through explosive allocation; tg1 also scores `oom` /
  `mem_kill` as outcomes); only a setup-phase failure, or a missing / malformed report after a clean execute phase, is
  an infrastructure failure → transport abort (never graded). Fixtures cover every terminal shape.
- **Skipped tests (T3, T24):** Rust via `--include-ignored`; JS freeze-time rewrite of `xtest` / `xit` / `xdescribe`
  (832 + 23 found) and Java `@Disabled` removal in both forms (bare and `@Disabled(...)`), in the protected prepared
  tree, recorded in the universe manifest; the grader refuses a tree whose test files still contain a rewritten skip
  form. JS `test.skip` (2 cases) are Exercism's optional expensive tests: policy = excluded from the universe, listed
  by id. Every rewrite is validated by the stable reference runs.
- **Multi-file items (T4, T17):** a per-language path mapping from `.meta/config.json` builds a separate reference
  overlay (never copy-by-index): Rust — the single example maps to `src/lib.rs`, `Cargo.toml` stays protected; C++ —
  map by file type to the unique solution destination (`.meta/example.cpp` → the solution `.cpp`, `.meta/example.h` →
  the solution `.h`); header-only references (three items, e.g. `binary-search-tree`) keep the unmatched prepared stub;
  an ambiguous or missing destination is a freeze error (T27); Java — each example maps by class path under
  `src/main/java` (e.g. `connect`: one solution, four reference files); every destination validated (inside the tree,
  declared or allowlisted). The universe freezes arrays of editable implementation paths and test paths; `file_changed`
  = any declared editable implementation path changed. V1b (Python/Go) unchanged.
- **Protection (T7, T8):** every prepared file not in the editable solution array is protected (tests, fixtures, build
  configs, wrappers, helpers). Overrides: Rust `Cargo.toml` is protected although the metadata lists it as a solution;
  a `Cargo.lock` is generated at preparation (offline, from the image's crate cache) and protected; Cargo runs
  `--frozen`; every nested manifest a test invokes (e.g. `rust/macros/tests/invalid/Cargo.toml`, run by ignored tests via
  a nested `cargo build --offline`) gets its own generated, protected lockfile, validated offline in the image (T23).
  New files: per-language allowlist for implementation helpers (Rust `src/*.rs`; Java only under the package roots of
  the declared solution files, with dependency / framework namespaces — `org.junit`, `org.assertj`, `org.json`,
  `io.reactivex`, `java.`, `javax.` — and duplicates of test-visible classes denied (T18); JS non-test `*.js` beside
  the solution; C++ `*.h`/`*.cpp` named in no CMake test glob);
  anything else that can affect build or tests (`build/`, `target/`, `node_modules/`, `jest.config.*`, `babel.config.*`,
  `.babelrc`, `build.rs`, `.cargo/`, `settings.gradle*`, `gradle.properties`, `CMakeLists.txt`, `*.cmake`, extra test
  files, framework-namespace shadows such as a local `catch.hpp` or `jest/` dir) fails the item. Threat model: code
  inside declared solution files is trusted to run (it is the answer) but runs in the network-less, memory-capped
  container with only the work tree and a private report dir mounted.
- **Container (T13):** derived image `tg2-grader` FROM `aider-benchmark` (`sha256:6ed3b12a…`), adding the gradle
  distribution + the three Java dependency closures (common JUnit/AssertJ, `hangman` + RxJava, `rest-api` +
  `org.json`; image acceptance runs all three offline from an empty writable Gradle cache — T25), the JS bundle and the
  Rust crate cache; full image digest pinned in the policy and verified
  locally before each leg; `docker run --pull=never --network none --memory 4g --memory-swap 4g`; mounts: the item work
  tree and a private report dir only; no writable cache shared across items (caches are read-only image layers).
- **Universe freeze (T5):** per item: ≥ 3 fresh reference runs with identical collected leaf sets and all-pass
  verdicts; ≥ 2 fresh stub runs with identical collected leaves; `baseline_failing > 0`; no skipped leaves; deprecated /
  inverted items scanned first (C145). Every exclusion listed with its reason. Never excluded by model outcome.
- Timeouts per language from the reference build+test time (max over freeze runs × 3, floor 180 s).

## Draw rule (T11, T19, T26)

1. Freeze the valid universe first (`benchmark/m65/tg2_universe.json` + sha256 sidecar): corpus `polyglot_sha`, sorted
   valid ids per language, exclusions with reasons, `N_actual` per language.
2. One seeded permutation per language, `random.Random(6501).sample(sorted(valid), N_actual)`, frozen as a canonical
   JSON (sorted keys) with its sha256 before any tg2 model run (smoke included). Tier draws are NESTED prefixes of it:
   screen = first 10 per language, decider = first 20 per language (the screen items are the decider's first half);
   a later resolution increase (C168) extends the same prefix (25, …, all) — never a redraw.
3. Every leg names its tier and verifies the permutation's sha256 and the prefix length at start; refuses on mismatch.
A language with `N_actual` < 20 (decider prefix not fillable) needs explicit operator acknowledgement (keep at `N_actual`, or drop); the campaign
proceeds only if at least two languages remain unless the operator rules otherwise. M55 outcomes are never used;
overlap with M55's draws is allowed.

## Tiers and sizing (C168; T10, T12; P356 review `benchmark/chains/c147/reviews/m65/p356-round1.cursor-gpt-5.6-sol-high.md`)

| Tier | When | Items | Sessions | GPU per new arm | Claims allowed |
|---|---|---|---|---|---|
| SCREEN | every model / harness / config tuple | 40 (10 / language) | k = 1 (exception to the agentic k = 2 rule, screens only) | ≈ 4 h | diagnostic only: per-language estimates, nonconv kinds, tokens/task, failure modes, headroom; no PASS / ADOPT / REJECT; a clean screen is not safety evidence; a material finding triggers the decider |
| DECIDER | only when a pick or ladder order would change | 80 (20 / language) | k = 2 + same-seed reload | ≈ 18–19 h | per-session inference (sessions never pooled); equal-language macro-average + every language reported, pre-registered large-harm HOLD; exact 80 %-power MDE ≈ 14 pp same-model/config, ≈ 18 pp between picks |

- Planning discordance (P356 S3): p_d = .182 for same-model / config comparisons (M55 s1 vs s2, 24/132) and .303 between
  picks (40/132); .409 stress. Never the saturated tg1 value (.041). Sized by exact paired-binary simulation (P357 fixed
  sim), pooled and per-language power reported separately.
- Early stopping: futility only, at the screen → decider boundary (40 of 80 items, nested); a futility stop yields
  HOLD, never equivalence; no efficacy looks, no sequential TOST.
- Reference arm: run once per decision epoch and reused only with identical epoch, model, items, seeds, fingerprint,
  wall policy, frozen opencode `prompt_date`, box class and scoring, plus contemporaneous sentinel items each run; any
  sentinel drift → HOLD / re-baseline. Cross-epoch rows descriptive.
- Single-turn axes keep their own ≤ 5 pp estimands but never certify agentic behaviour (S9; M63): any lever that changes
  trajectories, timeouts, scaffold, tools or serving needs at least the screen.
- ±5 pp agentic equivalence is out of reach (≈ 514–1,300 items); resolution is revisited once results exist (C168).
- Cost: the per-arm figures are lower bounds from M55 means (≈ 351–382 s / item); loads, A4, audits, recovery and the
  subjective panel come on top; P223 tail p95 19.3 min / max 61 min. A heavy-tail range is published after the smoke.

## Build steps (each test-first, worktree, Cursor review)

1. Grader per language + parser fixtures (real reference / stub trees, colliding leaf names, duplicate events,
   compile failure, missing report, every tamper vector above); image build script + digest pin.
2. Multi-file materializer + tg2 universe freeze + determinism report + the three candidate draw artifacts.
3. `bench/tg2_runner.py` (`--lang` rust / java / javascript / cpp under `opencode-v2-web-tg2`) and chain runner tg2
   LEGS as a configuration of the shared core (T14 amended, P371); final solution trees retained for the panel (T22).
4. Injected positives (stall / loop / alloc) on one item per language; four-language `--smoke`; sizing report; then
   the operator's chain go.

## Operator decisions (after the smoke + sizing report)

D1 languages (C++ in or out; it has 26 candidates before exclusions); D3 whether M64 moves to tg2 (spec amendment) or
stays on tg1. (D2 settled by C168: screen 10 / language, decider 20 / language.)
