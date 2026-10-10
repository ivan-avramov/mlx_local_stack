**BLOCKING — HEAD `77ddc98a7f7a`.** C1–C3 remain material correctness gaps; C4 is a demonstrated cleanup regression.

**VERIFIED:** 151 tests passed; one environment-sensitive test failed. Follow-up: that test passed with `STACK_WORKDIR` unset, and all 20 scoreboard tests passed. Pinned 1.18.30 mock captures succeeded with isolated HOME/XDG. No repository changes or port-8000 traffic.

Locations: `probe` = `benchmark/run_opencode_probe.py`; `tests/` = `benchmark/bench/tests/`.

| Prior finding | Status | Code / test evidence |
|---|---|---|
| Fail-closed path resolution; same executable throughout | **Partial:** path handling closed; version ordering C1 | `probe:92,329,487,602,865`; `tests/test_opencode_probe_seeding.py:56,75,89,101,114,131` |
| Resume four fields; skip recorded keys | **Closed narrowly; C2 remains** | `probe:935,967,1103`; seeding tests `:456,468,476,483,492` |
| Scaffold hash consumed by compatibility/compare | **Closed directly; consumer regression C4** | `benchmark/bench/provenance.py:421,576`; `compare.py:321`; `tests/test_scaffold_policy_compare.py:32–71` |
| Receipt bound to executable/config/test/global-config hashes | **Closed for listed bytes; incomplete coverage C3** | `probe:432,449,468`; seeding tests `:201,221,232` |
| Overlay rejects nonzero/timeout/malformed JSON | **Closed** | `probe:486–503`; seeding tests `:306,317` |
| Per-item overlay hash in manifest | **Closed** | `probe:1006`; seeding test `:500` |
| Resolved options minus seed equal shipped block | **Closed** | `probe:517–532`; seeding tests `:258–303`; normalization reproduction passed |
| Scratch git boundary | **Closed for ancestor isolation** | `probe:976–984`; seeding tests `:518,559,604`; real mock positive/negative passed |
| Ancestor inventory and portable paths | **Partial: C3, C5** | `probe:549–576`; seeding tests `:532,546` |
| Rehash/restore before export | **Closed for normal completion** | `probe:1023–1030`; seeding test `:625` |
| Item refusal stamps drift | **Closed** | `probe:988–1001`; seeding test `:613` |
| Documentation corrections | **Seed annotations correct; historical exposure overclaimed, C6** | `docs/specs/m54-agentbench-os.md:23`, `m55-polyglot-gap.md:10,13`; notebook `:4432,4447` |

**C1 — HIGH · VERIFIED: discovery executes an unvalidated version.**  
`benchmark/run_opencode_probe.py:863–868,892`: `_require_opencode_bin()` checks absolute path, existence and executability—not version. `debug config` runs before `--version`. A replaced pinned install or absolute override pointing to v2 therefore executes v2 discovery before rejection. Mocked ordering reproduced only `debug config` before router refusal.

**Minimal fix:** validate the same absolute executable’s version before discovery; reject unsupported versions there. Update `test_m50_entrypoints.py:195`, which currently explicitly forbids that version preflight.

**C2 — HIGH · VERIFIED: resume accepts changed scaffold configuration and overwrites attribution.**  
`benchmark/run_opencode_probe.py:936–939,947–963,1110`: resume ignores the recorded global-config hash, shipped-config hash and instruction inventory. Changing global permissions or instructions while preserving model options passes the overlay check; continuation then replaces the manifest with current provenance for both old and new rows. Direct reproduction accepted changed global/shipped/instruction hashes.

**Minimal fix:** compare the complete output-determining run identity before continuation and preserve original attribution. Include global/shipped configuration and effective instructions. Excluded ancestors need not match merely because they exist; **loaded** instructions must match.

**C3 — HIGH · VERIFIED: a loaded global instruction source escapes every new hash.**  
`benchmark/run_opencode_probe.py:461–463,549–575,588–595`: `$XDG_CONFIG_HOME/opencode/AGENTS.md` is absent from both global-config hashing and the ancestor inventory. In an initialized scratch repository, its sentinel **reached the captured system prompt**. Editing it left the global hash unchanged and the receipt marked `verified-by-test`.

**Minimal fix:** inventory/hash effective instruction sources, including global `AGENTS.md`, and consume that identity in resume/comparison. The receipt’s existing hashes establish the listed-file binding, not complete scaffold identity.

**C4 — MEDIUM · VERIFIED: legacy rows can be deleted before an unsupported regeneration.**  
`benchmark/bench/provenance.py:421`; `benchmark/bench/generate.py:338–343,459–461`: generic `current_manifest_lite()` has no opencode scaffold, so legacy `"pre-C121"` now mismatches `"n/a"`. On synthetic results, `--clean-stale` deleted the JSONL/manifest; `benchmarks.load("opencode")` then refused because this generator cannot regenerate opencode. The identical manifest pair passed without the new gate.

**Minimal fix:** validate supported benches before cleanup; do not use a scaffold-less generic manifest to classify opencode freshness. Preserve strict legacy-versus-seeded refusal.

**C5 — LOW · VERIFIED: portability test depends on the caller’s environment.**  
`benchmark/bench/tests/test_opencode_probe_seeding.py:532–543`: with temp files beneath exported `STACK_WORKDIR`, `_portable()` correctly chooses `$STACK_WORKDIR/...`; the test requires `~/AGENTS.md`. This caused the sole suite failure.

**Minimal fix:** explicitly isolate `STACK_WORKDIR` in this test or assert the intended workdir-first representation.

**C6 — LOW · VERIFIED wording defect; historical exposure remains ASSUMPTION.**  
`docs/lab-notebook.md:4447–4449` asserts instruction exposure for every earlier row. Current file existence and a current mock capture cannot establish historical exposure; `docs/open-questions.md:24` itself calls that unobservable.

**Minimal fix:** qualify historical exposure and limit definitive claims to captured evidence.

Remaining checks:

- **VERIFIED:** key order and integer/float normalization do not cause false refusal. The shipped options block is an appropriate carrier check, but does not independently audit agreement across all four carriers.
- **VERIFIED:** preparation precedes git initialization; overlay follows initialization. `file_changed`/tamper checks inspect solution/test contents. Pinned runs and session export worked without Git identity configuration.
- **VERIFIED:** the M50 autouse fixture preserves its zero-write assertions by placing the stub outside each test’s `tmp_path`; no additional fixture regression found.
- **ASSUMPTION / untested:** Docker toolchain execution with `.git` present. Restore-before-export ordering is correct after the parent exits, but concurrent surviving descendants were not tested.
