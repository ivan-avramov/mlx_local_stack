**P4 — BLOCKING at `424551c`.** Two remaining defects affect scaffold attribution and drift-history preservation.

**VERIFIED** below means source/test inspection, including the pinned executable’s embedded code. Tests were **not executed**; no fresh request capture or Docker validation was performed. No prior review files were read, and port 8000 was untouched.

**P5 — Closure table.** References: `probe` = `benchmark/run_opencode_probe.py`; `tests` = `benchmark/bench/tests/test_opencode_probe_seeding.py`; `provenance` = `benchmark/bench/provenance.py`.

| Round-5 claim | Code + test evidence | Closure |
|---|---|---|
| Scrub complete stderr before tail at all three sites | `provenance:1186,1519,1528`; `probe:627`; `tests:1278,1293,1308` exercises second-item refusal | VERIFIED |
| Tick snapshots use run TMPDIR | `probe:289,349`; `tests:1334,1349` | VERIFIED |
| Rehash cache after each item; flag row/stamp manifest | `probe:1235,1282`; both mutation/control arms at `tests:1370` | VERIFIED; resume gap E2 |
| Pre-write refusal preserves previous manifest bytes | `probe:1185`; `tests:750` | VERIFIED |
| Bench HOME guard and per-item carrier-copy SHA | `probe:491,1037,1162`; `tests:1397,1405,1424` | VERIFIED narrowly; E1 |
| Overlay includes seed, disabled title, disabled snapshots | `probe:414,656`; `tests:165,314,320,468` | VERIFIED by inspection |
| Probe/progress-gate source hash in resume identity | `probe:524,1315`; field-mutation test at `tests:584` | VERIFIED |
| Positive-control monkeypatch scoped | `tests:1109,1164` | VERIFIED |

**P6 — New findings.**

**E1 — HIGH / blocking — Additional config-home files bypass scaffold checks.**  
`benchmark/run_opencode_probe.py:1163` and `:663`.

Failure scenario: item 1 leaves `$XDG_CONFIG_HOME/opencode/AGENTS.md`, while preserving `opencode.json`. Item 2 passes the HOME guard, carrier SHA, destination, sampling, limit and empty-`instructions` checks. The pinned executable loads global config-directory `AGENTS.md` independently of the JSON `instructions` field. Item 2 therefore receives extra system instructions under the unchanged scaffold hash. An added `opencode.jsonc` containing an agent prompt is another unchecked surface.

**VERIFIED:** incomplete guard and global instruction-loading path. **Not runtime-reproduced:** the two-item scenario. Existing tests check initial directory contents and modification of the original carrier, not added files.

Minimal fix: enforce the permitted config-directory contents before each item; reject additional loadable configuration/instruction sources. Add second-item injection tests for global `AGENTS.md` and an agent override.

**E2 — MEDIUM / blocking — Cache-drift history can disappear on resume.**  
`benchmark/run_opencode_probe.py:1363`, `:1120`, `:1131`.

Failure scenario: an item changes the cache, producing `cache_bin_inventory_drift`. Before resuming, the cache returns to its original inventory. Identity comparison now passes because only `served_config_drift` is explicitly refused. The fresh manifest drops the cache-drift stamp; `continuation_history` also omits it. The recorded observed hash and affected-item attribution are lost.

**VERIFIED:** complete control-flow path. `tests:1370` covers stamping; `tests:1245` covers only served-config drift refusal.

Minimal fix: refuse `cache_bin_inventory_drift` before identity comparison, including zero-row manifests. Test a restored-inventory resume and require byte-identical prior files.

**P7 — Challenge results and residuals.**

| Challenge | Result |
|---|---|
| **1. M50 ordering** | `probe:1026–1048`: stat → config copy/HOME/state/TMPDIR creation → redirected `--version` → redirected `debug config --pure` → router check. Writes are narrowly scoped under the workdir, apart from the ratified shared-cache initialization. Refusal removes config/tmp/discovery directories; persistent HOME/state and empty parents can remain. Discovery receives `boot_env` from `_opencode_env(disc_data, cfg_home, state_home, tmp_dir, bench_home)`. |
| **2. Personal/default sources and cache** | Normal harness spawns use the absolute pinned executable and redirected HOME/config/data/state. Parent `OPENCODE_*` variables are removed. Shared cache is **not catalogue-only**: embedded code uses cached ripgrep/LSP executables and package installations; these can affect tool feedback. `bin`/`packages` are inventoried. PATH tools, inherited non-`OPENCODE_*` environment and toolchain caches remain outside that inventory. |
| **3. Seed/sampling** | CLI `--model` overrides the carrier’s default `model`. Overlay preserves sampling; checks enforce exact options-plus-seed and matching `limit`. Capture-test assertions include `max_tokens` and every carrier option. Disabled title generation removes the ordinary `small_model` request. **Residual:** the sampling capture uses a temporary HOME stand-in; the separate bench-HOME sentinel capture does not assert sampling. No single capture test establishes both together. |
| **4. Resume** | Required identity fields, serving hash, router SHA, prior attribution, recorded-key skipping and duplicate-request suppression are present. All-skipped manifests remain unchanged. E2 remains. Not compared: dirty corpus/serving files beyond recorded commits, general toolchain/PATH state, cache catalogue, and other helper-module changes outside the two-file probe hash. |
| **5. Per-item checks** | Two `debug config --pure` spawns. Nonzero exit, timeout and malformed output refuse. Parser takes everything from the first `{`; brace-containing banners/trailing output can cause false refusal. Exact dictionary comparison can reject benign normalization. These fail closed. |
| **6. Git effects/grading** | Git boundary remains visible as “git repo: yes”; snapshots are explicitly disabled. `probe:886` bind-mounts the entire exercise, including `.git`, into `/work`; no stripping occurs. Graders call language tools directly. `run_aider_docker.sh:55` uses a different mounting arrangement and does not validate this path. Docker positives remain **UNVERIFIED**. |
| **7. Consumers** | `generate` skips cleanup/restamping for opencode. Scoreboard reads score sidecars; `rescore.py` is retired. **Residual:** generic `compare` still reaches `grade.grade("opencode")`, which lacks an opencode benchmark entry. New comparison tests use `math500` with opencode metadata—they prove the policy gate, not actual opencode comparison support. |
| **8. Receipt** | Opt-in stamping follows capture assertions; receipt binds executable, carrier and test-file hashes. Missing/mismatched receipt yields manifest-level `unverified`, not refusal. It is test evidence, not per-run wire verification. No receipt was stamped here. |
| **9. Test quality/isolation** | Field mutations, byte comparisons, second-item refusals and positive controls are useful. Some fixtures derive expected identity from production helpers, so omitted inputs can escape detection. Integration opencode environments redirect HOME and core XDG locations to temp directories. They still inherit other environment variables; `_real_dirs_listing` reads real directory names and detects no same-name content mutation. Receipt opt-in intentionally writes outside temp unless overridden. |
| **10. Docs** | Residual drift: `docs/open-questions.md:18` still calls C125 OPEN; `:28` leaves the HOME amendment awaiting confirmation and contains contradictory historical wording. Proposal AC1 (`:40`) omits `snapshot:false`; `:33` incorrectly describes CI/row stamping. Lab entry `:4462` says snapshots are enabled, later corrected at `:4495`. Qualification guidance accurately retains the Docker-validation debt. |

The inherited transport-abort gap remains separately recorded as C124; it is not a new closure finding.
