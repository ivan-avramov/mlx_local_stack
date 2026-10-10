**P4 — Verdict: BLOCKING at `f3c0887`.** Three in-scope gaps remain.

**VERIFIED** below means source and test assertions inspected, including embedded code in the pinned executable. Tests and mock captures were **not executed** in this pass. No port-8000 requests, opencode execution, personal-config access, repository edits, or prior-review-file reads.

**P5 — Round-4 closure**

Paths abbreviated: `probe` = `benchmark/run_opencode_probe.py`; `tests` = `benchmark/bench/tests/test_opencode_probe_seeding.py`.

| Claimed fix | Closure evidence | Result |
|---|---|---|
| Receipt override and real opt-in branch | `probe:448,462`; `tests:1155` exercises `_maybe_stamp_receipt`, including opt-out | CLOSED, static |
| Cache `bin`/`packages` inventory in manifest/resume | `probe:510,1084,1264`; content-mutation test at `tests:1169` | PARTIAL: E3 |
| Always `--pure`; remove `--no-pure` | `probe:1015,1153,1159,1181`; three-debug-spawn assertions at `tests:975`, CLI rejection at `1186` | CLOSED, static |
| `poll_s` identity | `probe:538,1264`; field-mutation case at `tests:577` | CLOSED, static |
| Scrub persisted errors before truncation | Helper at `probe:178`; tests at `1026,1193` | **NOT CLOSED: E1** |
| Check existing manifest even without rows; reject drift | `probe:1085,1311`; `tests:1205` | CLOSED, static |
| Reject malformed/unterminated rows, identify line | `probe:1268`; `tests:1213` | CLOSED, static |
| Register cleanup before creation; partial cleanup | `probe:491,928,1003`; `tests:1038,1224` | CLOSED, static |
| HOME-sentinel positive control | `tests:1075,1116` | PARTIAL: negative arm retains disabled switches |
| Reconciled documentation | See residuals below | NOT fully reconciled |

**P6 — Findings**

- **E1 — HIGH, PII leakage remains possible.** `benchmark/run_opencode_probe.py:599`; `benchmark/bench/provenance.py:1504,1511`.  
  Debug-config stderr is sliced to 200/300 characters **before** the exception reaches `_scrub_error` at `probe:1150`. A slice through a home path/login name leaves a fragment that neither full-path replacement nor whole-login matching removes; that fragment can enter `served_config_drift.error`.  
  **Minimal fix:** scrub complete stderr before taking its tail, at the exception-construction sites. Add a test through the real nonzero-debug-config → manifest-stamp path, sweeping cuts through a synthetic identity. Current tests scrub complete helper inputs or inject already-constructed exceptions, bypassing this defect. **VERIFIED code path; no actual leak induced.**

- **E2 — HIGH, progress snapshots can write outside the workdir.** `benchmark/run_opencode_probe.py:288,348,384`.  
  Per-run `TMPDIR` is supplied only to opencode’s child environment. `_tick_snapshot_fn` executes in the parent and calls `TemporaryDirectory()` without `dir=`. A fresh-shell launch with the normal system temp directory therefore copies the exercise—and its `.git`—outside `$STACK_WORKDIR` at the first progress tick. This is inherited code, but the new per-run redirection does not cover it.  
  **Minimal fix:** pass the run’s temp directory explicitly into the snapshot helper and its `TemporaryDirectory`. Assert containment in a tick test. Existing snapshot tests check separation from the live workspace, not containment; mock-request tests use a ceiling shorter than their first tick. **VERIFIED.**

- **E3 — MEDIUM, tool-cache attribution is only an entry snapshot.** `benchmark/run_opencode_probe.py:1084,1178,1245`.  
  The shared cache is hashed once before items. The pinned executable contains lazy ripgrep/LSP download paths into that cache; tools can consequently be installed during an item, while its manifest retains the earlier inventory. Exit validation checks the router only. Thus clean rows can claim an inventory different from the tools used.  
  **Minimal fix:** qualify/populate the tool cache before recording identity, then recheck it before items and at exit; refuse or drift-stamp changes rather than silently retaining the entry hash. Add a main-path test that mutates cache content during the mocked run. **VERIFIED missing guard and download implementation; occurrence during a particular campaign is unmeasured.**

**P7 — Requested challenges**

| Area | Assessment |
|---|---|
| **1. M50 ordering** | Before the router check: resolve workdir, stat pinned binary, create/copy config, create persistent HOME/state and per-run temp, run `--version`, then discovery (`probe:978–1016`). The config write is minimal and inside the workdir. Refusal removes config/temp/discovery-data directories; persistent HOME/state, parent directories, and permitted shared-cache initialization can remain. Discovery receives `boot_env`: bench HOME/config/state/temp, isolated discovery data, shared cache, and exactly the two `OPENCODE_*` switches. |
| **2. Isolation/cache** | Normal production spawns use the absolute pinned executable and redirected HOME/config/data/state. Brew is not selected through PATH. The shared cache **can influence tool feedback**: embedded code uses `bin` for ripgrep/LSP executables and `packages` for installed packages; it also contains skill-cache machinery, whose activation under this carrier was not measured. It is not catalogue-only. Other PATH tools remain inherited. |
| **3. Seed/sampling** | Overlay contains seed plus title-disable; resolved options and `limit` are checked exactly (`probe:412,619`). AC3 asserts every deployed option, including `max_tokens`, in captured bodies. However, its HOME is a temporary stand-in, not the production persistent bench HOME (`tests:834,847`). No fresh capture here. Explicit CLI `--model` overrides the carrier default; title-disable removes the demonstrated `small_model` title path. Broader auxiliary-call behavior remains unmeasured. |
| **4. Resume** | Drift refusal, named identity fields, model/serving/router hashes, prior attribution/history, recorded-key skipping, and duplicate requested-item suppression are present. All-skipped manifest preservation has a byte-equality test. Not compared: dirty corpus content, probe/progress-gate source identity, inherited tool environment, persistent HOME contents, and within-run cache changes. |
| **5. Per-item checks** | Two debug spawns, both pure. Nonzero exits, timeouts and malformed JSON refuse; existing manifests receive drift stamps. Parser uses the first `{` through EOF: brace-containing prefixes or trailing diagnostics cause safe false refusals. Exact option/limit equality can also reject benign normalization. |
| **6. Git/docker** | Git initialization changes prompt context and enables snapshot tracking under isolated data storage. `_docker_grade` binds the entire exercise to `/work`, including `.git` (`probe:854`); no stripping occurs. `run_aider_docker.sh:55` is a separate execution path and establishes no additional protection here. Known-positive grades for all four Docker languages remain **UNVERIFIED**. |
| **7. Consumers** | `generate` skips opencode cleanup/restamping; opencode has no generation loader. No new deletion path found. Compare rejects differing/legacy scaffold hashes, but does not enforce the complete resume identity. Scoreboard presents stored scores without a scaffold-compatibility gate. `benchmark/rescore.py` is retired. |
| **8. Receipt** | Opt-in stamps only after AC3 assertions. Receipt binds executable, carrier and test-file hashes; stale/missing receipts yield `unverified`, which does **not** prohibit generation. It certifies that test configuration—not every model, multi-turn behavior, or subsequent cache state. |
| **9. Tests** | Main-path resume mutations, cleanup, duplicate and history tests are useful. Cache testing covers the helper plus a synthetic identity mismatch, not runtime cache mutation. Error tests miss E1. HOME positive-control monkeypatching persists into the negative arm (`tests:1099,1125`); that arm does not restore production switches. Standard child HOME/XDG/temp destinations are redirected, but top-level directory-name comparisons cannot prove absence of outside writes. |

**P8 — Short residuals**

- **Docs:** `docs/lab-notebook.md:4459` still says the receipt binds instruction inventory; proposal design at `docs/proposal-opencode-seeding.md:22` still says seed-only overlay, while amended AC1 correctly includes title-disable. AC7 at `:54` still labels M54 unseeded.
- **Decision record:** `docs/open-questions.md:28` names the client carrier and says the HOME amendment awaits confirmation; `:18` still leaves C125 ratification open. Both conflict with the supplied governing rulings. `docs/qualify-a-model.md:700` is substantially aligned.
- **Operational debt:** retain the documented Docker positives and receipt-stamp run. C124 transport-abort behavior remains explicitly inherited and outside this closure’s new findings.
