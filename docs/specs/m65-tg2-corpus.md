# M65 step 2 — "tg2" harder agentic corpus (DRAFT v2, 2026-10-16; sizing pending smoke data)

Status: DRAFT → Cursor `gpt-5.6-sol-high` review → operator. PLAN M65; C167 (P349). v2 applies Cursor round 1
T1–T13 (`benchmark/chains/c147/reviews/m65/tg2-round1.cursor-gpt-5.6-sol-high.md`); v1 = `a44b4b18`.

## Why

tg1 (43 Python + Go items) is saturated for both B picks (83–86/86 strict across P223, M63, c144-base; M64 power
simulation 0.000). Prior evidence of headroom: M55 (opencode 1.18, C37 22-item draws, k=2) scored the picks at
61–86 % on Rust / Java / JavaScript with per-session pick deltas up to +23 pp
(`benchmark/results/m55_polyglot_gap_report.md`). M55's harness differed (stall kills, sandbox rejections), so its
levels are indicative only.

## Scope and estimand

- Languages: Rust (30), Java (47), JavaScript (49), C++ (26), pinned polyglot corpus (`polyglot_sha` as tg1).
- Harness: the tg1 probe policy family under a new scaffold label `opencode-v2-web-tg2` (own
  `scaffold_policy_sha256`; tg1 identity untouched). Agent-phase web and shell networking stay as tg1 and are audited
  by P201 (T13).
- **Estimand (T9):** per language × session cells only (strict, conv, nonconv kinds, tokens/task); never blended
  across languages or with tg1; any aggregate is descriptive. tg2 is an **estimation screen**, not an equivalence or
  confirmatory design (T10). A tg2 opencode chain is not an M64 baseline: moving M64 to tg2 needs a formal M64 spec
  amendment before M64 runs, and tg2 rows from other epochs stay non-poolable with M64.

## Grader (`structured_grade`, grader version `m65-structured-v3`; Python/Go behaviour byte-identical)

| Lang | Command (in the grading container) | Leaf report |
|---|---|---|
| Rust | `cargo test --frozen --offline --no-fail-fast -- --include-ignored` | libtest lines; leaf id = `<test binary>::<path::name>` |
| Java | `bash ./gradlew --offline --no-daemon --rerun-tasks test` (corpus wrapper 8.7; distribution + Maven artifacts baked into the image) | JUnit XML `build/test-results/test/*.xml`; leaf id = `<classname>#<name>` |
| JavaScript | `<bundle>/node_modules/.bin/jest --ci --json --outputFile=<private>` (one digest-pinned dependency bundle: all 49 `package.json` dependency signatures match; no `npx`) | jest JSON; leaf id = `<test file>::<fullName>` |
| C++ | `cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON`, `cmake --build build --target <slug>`, `./build/<slug> -r junit -o <private>` (Catch2) | JUnit XML; leaf id = `<classname>#<name>` |

- **Parsing (T6):** canonical leaf ids as above; a leaf with any failure event is failed (failure wins over pass);
  a skipped / ignored / missing expected leaf counts as failed; a compile failure fails every leaf of the item (model
  outcome, graded); an absent or unparsable report with a clean build, an image pull, an OOM or a docker daemon error
  is an infrastructure failure → transport abort (never graded). Raw reports and build output retained by sha256.
- **Skipped tests (T3):** Rust via `--include-ignored`; JS freeze-time rewrite of every supported skip form (`xtest`,
  `xit`, `test.skip`, `it.skip`, `describe.skip`, `xdescribe`; 832 + 23 + 2 found) and Java `@Disabled` removal, both in
  the protected prepared tree, recorded in the universe manifest; the grader refuses a tree whose test files still
  contain a skip form.
- **Multi-file items (T4):** a per-language reference materializer reads `.meta/config.json` arrays (Rust/C++ have two
  solution paths each; Java items have several solutions/examples; Rust `forth` has two tests; Java `ledger` a helper);
  the universe freezes arrays of editable solution paths and test paths; `file_changed` and the tamper check range
  over all editable paths. V1b (Python/Go) is unchanged.
- **Protection (T7, T8):** every prepared file not in the editable solution array is protected (tests, fixtures, build
  configs, wrappers, helpers). Overrides: Rust `Cargo.toml` is protected although the metadata lists it as a solution;
  a `Cargo.lock` is generated at preparation (offline, from the image's crate cache) and protected; Cargo runs
  `--frozen`. New files: per-language allowlist for implementation helpers (Rust `src/*.rs`, Java
  `src/main/java/**/*.java`, JS non-test `*.js` beside the solution, C++ `*.h`/`*.cpp` named in no CMake test glob);
  anything else that can affect build or tests (`build/`, `target/`, `node_modules/`, `jest.config.*`, `babel.config.*`,
  `.babelrc`, `build.rs`, `.cargo/`, `settings.gradle*`, `gradle.properties`, `CMakeLists.txt`, `*.cmake`, extra test
  files, framework-namespace shadows such as a local `catch.hpp` or `jest/` dir) fails the item. Threat model: code
  inside declared solution files is trusted to run (it is the answer) but runs in the network-less, memory-capped
  container with only the work tree and a private report dir mounted.
- **Container (T13):** derived image `tg2-grader` FROM `aider-benchmark` (`sha256:6ed3b12a…`), adding the gradle
  distribution + Maven deps, the JS bundle and the Rust crate cache; full image digest pinned in the policy and verified
  locally before each leg; `docker run --pull=never --network none --memory 4g --memory-swap 4g`; mounts: the item work
  tree and a private report dir only; no writable cache shared across items (caches are read-only image layers).
- **Universe freeze (T5):** per item: ≥ 3 fresh reference runs with identical collected leaf sets and all-pass
  verdicts; ≥ 2 fresh stub runs with identical collected leaves; `baseline_failing > 0`; no skipped leaves; deprecated /
  inverted items scanned first (C145). Every exclusion listed with its reason. Never excluded by model outcome.
- Timeouts per language from the reference build+test time (max over freeze runs × 3, floor 180 s).

## Draw rule (T11)

A committed, hashed draw artifact `benchmark/m65/tg2_draw.json`: corpus `polyglot_sha`, universe sha256, sorted valid
ids per language, exclusions with reasons, `n_lang`, seed 6501, and the explicit selected ids
(`random.Random(6501).sample(sorted(valid), n_lang)`, or all valid ids when `n_lang ≥ |valid|`). Written before any
tg2 model run. A language with fewer than 20 valid items after the freeze is dropped (reported) rather than
under-sampled. M55 outcomes are never used; overlap with M55's draws is allowed.

## Sizing (T10, T12)

Per language, from conservative discordance scenarios: M55 same-model reload discordance per language (1/22–9/22) and
the four-language tg2 smoke, NOT the tg1 value (0.041). Report, per candidate `n_lang` ∈ {20, 25, all}, the paired
MDE per language × session cell (≈ ±25 pp at 25) and the interval width for strict accuracy. Cost: point estimate
from M55 means (≈ 6–7 min/item → ≈ 45 h for 100 items × 2 picks × k = 2 + reload) is a LOWER bound; P223's current
harness had p95 19.3 min and max 61 min per item; a heavy-tail range (+ model loads, A4, auditing, grading, recovery)
is published after the smoke.

## Build steps (each test-first, worktree, Cursor review)

1. Grader per language + parser fixtures (real reference / stub trees, colliding leaf names, duplicate events,
   compile failure, missing report, every tamper vector above); image build script + digest pin.
2. Multi-file materializer + tg2 universe freeze + determinism report + draw artifact.
3. Probe `--lang` rust / java / javascript / cpp under `opencode-v2-web-tg2`; chain runner tg2 LEGS (tg1 unchanged).
4. Injected positives (stall / loop / alloc) on one item per language; four-language `--smoke`; sizing report; then
   the operator's chain go.

## Operator decisions (after the smoke + sizing report)

D1 languages (C++ in or out); D2 `n_lang`; D3 whether M64 moves to tg2 (spec amendment) or stays on tg1.
