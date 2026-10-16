# M65 step 2 — "tg2" harder agentic corpus (DRAFT proposal, 2026-10-16; sizing pending the step-1 pilot)

Status: DRAFT → Cursor `gpt-5.6-sol-high` cold review → operator. PLAN M65; C167 (P349).

## Why

tg1 (43 Python + Go items) is saturated for both B picks (83–86/86 strict across P223, M63, c144-base; M64 power
simulation 0.000). Prior evidence of headroom elsewhere: M55 (opencode 1.18, C37 22-item draws, k=2) scored the picks
at 61–86 % on Rust / Java / JavaScript, with per-session first-vs-second-pick deltas up to +23 pp
(`benchmark/results/m55_polyglot_gap_report.md`). M55 ran an older harness (stall kills, sandbox rejections), so its
levels are indicative only; tg2 re-measures under the tg1 harness.

## Scope

- Languages: Rust (30), Java (47), JavaScript (49), C++ (26) from the pinned polyglot corpus (`polyglot_sha` as tg1).
- Harness: the tg1 probe (`opencode-v2-web-tg1` policy family, same token-turn gate, guard, web audit) with a new
  scaffold label `opencode-v2-web-tg2` (its own `scaffold_policy_sha256`; tg1 identity untouched).
- Python + Go stay tg1; tg2 is reported per language, never blended with tg1.

## Grader (`structured_grade`, new grader version `m65-structured-v3`; Python/Go behaviour byte-identical)

| Lang | Command (in the grading container) | Structured result |
|---|---|---|
| Rust | `cargo test --offline --no-fail-fast -- --include-ignored` | libtest lines `test <name> ... ok/FAILED/ignored` (stable toolchain; no `-Z` JSON) |
| Java | `gradle --offline test` (pre-seeded wrapper distribution + dependency cache) | JUnit XML `build/test-results/test/*.xml` |
| JavaScript | `npx jest --ci --json --outputFile=<private>` with pre-installed `node_modules` (no network) | jest JSON `testResults[].assertionResults[]` |
| C++ | `cmake -S . -B build && cmake --build build && ./build/<target> -r junit` (Catch2) | JUnit XML |

- **Container:** derived image `tg2-grader` FROM the current `aider-benchmark` (digest
  `sha256:6ed3b12a…`), adding the gradle distribution + Java deps, one `node_modules` per JS lockfile and the Rust crate
  cache, then pinned by digest in the policy. Grading runs with `--network none`, 4 GB memory/swap, the guard's
  container registration, per-language timeouts set from the reference build times (measured at universe freeze ×3).
- **Skipped tests:** Exercism ships skipped tests (`#[ignore]`, `xtest`, `@Disabled`); the grader runs all of them
  (Rust `--include-ignored`; JS/Java un-skipped in the prepared tree, recorded in the universe manifest, protected).
- **Protected files** (tamper check, like `PY_FORBIDDEN`): every test file, `Cargo.toml`/`Cargo.lock`, `build.gradle`,
  `gradle/`, `gradlew*`, `package.json`, lockfiles, `babel.config.js`, `.eslintrc`, `CMakeLists.txt`, test helpers;
  a new file that changes build/test configuration (e.g. `jest.config.*`, `build.rs`, `.cargo/config*`) fails the item.
- **Universe freeze:** the V1b builder per language (reference passes every collected test; stub baseline recorded);
  deprecated/inverted items scanned first (C145 lesson); an item whose reference fails, or whose grade is not
  deterministic across 3 reference runs, is excluded and listed. Never excluded by model outcome.

## Draw rule (pre-registered, model-independent)

All valid items per language after the freeze, or — if sizing needs fewer — `random.Random(6501).sample(sorted(valid),
n_lang)` per language, seed and `n_lang` committed before any tg2 model run. M55 per-item outcomes are never used
(no selection on noise). M55's earlier draws may overlap; that is allowed (not outcome-based).

## Sizing (to be filled from the pilot)

Inputs: step-1 pilot (per-pick strict, discordance between picks), M55 per-language rates and between-session
discordance, the M64 `power_sim.py` (same-model run-to-run discordance 0.041). Candidate: 25 items per language
(100 items; ≈ 6–7 min/item from M55 → ≈ 45 h for 2 picks × k = 2 + reload control). Report the power of the M64
pooled claim and of a per-language pick-vs-pick screen at that N before the operator chooses N.

## Build steps (each test-first, worktree, Cursor review)

1. Grader per language + fixtures (real reference/stub trees, injected tamper cases), image build script + digest pin.
2. tg2 universe freeze + determinism report.
3. Probe: `--lang` rust/java/javascript/cpp under the tg1 policy family (`opencode-v2-web-tg2`), gate per-language
   timeouts; chain runner LEGS for tg2 (no tg1 change).
4. Injected positives (stall/loop/alloc) on one item per language; `--smoke`; then the operator's chain go.

## Operator decisions (after the pilot)

D1 languages (C++ in or out — 26 items, Catch2 adds a fourth parser); D2 N per language; D3 whether M64 moves to tg2
(spec amendment) or runs tg1 + a tg2 subset.
