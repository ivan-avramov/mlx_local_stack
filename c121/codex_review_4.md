**P1 — BLOCKING at `cc3c04d`.** The receipt-stamping path is broken, and several isolation/resume guarantees remain incomplete.

**VERIFIED** below means source or embedded executable-code inspection. No tests, opencode processes, Docker, or router requests were run. No prior review files or personal opencode configuration were read.

**P2 — Closure against the supplied design**

Paths abbreviated: **probe** = `benchmark/run_opencode_probe.py`; **tests** = `benchmark/bench/tests/test_opencode_probe_seeding.py`.

| Concern | Closure and evidence |
|---|---|
| Pinned executable; version before discovery | **Closed by inspection.** Absolute executable validation, no PATH fallback; version precedes discovery (`probe:91`, `probe:956`). Explicit drift override remains available. |
| Bench config/HOME/state/data/TMPDIR; parent switches | **Closed on the default path.** `boot_env` contains bench HOME, copied config home, persistent bench state, per-run TMPDIR/discovery data, shared cache, and exactly two `OPENCODE_*` switches (`probe:359`, `probe:963`). Items reuse that policy with item-specific data (`probe:1096`). |
| M50 ordering and cleanup | **Partial.** Before M50: workdir/config resolution, binary stat, config copy, persistent HOME/state and per-run TMPDIR creation, version, discovery. These harness writes are inside the workdir. Ordinary refusal removes config/TMPDIR/discovery data; persistent HOME/state and parent directories remain (`probe:473`, `probe:888`). Partial initialization leaks remain: E7. |
| All three discovery/check spawns use `--pure` | **Default path closed; bypass remains.** Discovery plus destination and overlay checks receive it (`probe:974`, `probe:1111`, `probe:1117`). See E3. |
| Seed, sampling, title, limits | **Implementation closed; exact-path capture coverage partial.** Overlay adds seed and disables title (`probe:404`); check enforces options equality, unchanged baseURL, title disabled, empty instructions and equal limits (`probe:543`). Propagation test asserts every configured option, including `max_tokens` (`tests:455`), but uses a different HOME construction from production; bench-HOME test checks only sentinels (`tests:1068`). |
| Effective policy hash | **Closed as specified.** Inventory excluded; carrier/schema/switches/git/HOME/version/executable included (`probe:659`). Inventory stays observational. Shared executable cache remains outside identity: E2. |
| Resume identity/history/skipping | **Mostly closed.** Model, language, seed/scaffold, gate settings, corpus commit, executable, environment policy, serving hashes and router SHA checked; attribution/history retained; requested duplicates suppressed; ordinary all-skipped resume does not rewrite manifest (`probe:1037`, `probe:1083`, `probe:1240`). E4/E6 remain. |
| Failed debug checks | **Fail closed for expected failures.** Nonzero exit, timeout and malformed JSON refuse. Parser starts at the first `{`; braces in a preamble or trailing logging cause false refusal. Exact dict equality can reject added/default-normalized fields; no observed pinned-version normalization failure established. |
| Overlay rewritten by model | **Closed at row level.** Rehash, restore before export, flag and emit `passed:null`/exclusion reason (`probe:1143`, `probe:1165`). |
| `generate` ownership | **Closed.** Both cleaning and manifest stamping skip opencode (`benchmark/bench/generate.py:260`, `:334`). |
| Receipt, persisted errors, docs | **Not fully closed.** E1, E5 and E8. |

**P3 — Findings**

- **E1 — HIGH, VERIFIED: receipt stamping always fails when requested.**  
  `tests:476` calls `_record_seed_propagation_verified(binary, inventory_hash)`; `probe:451` accepts only one argument. `OPENCODE_PROBE_RECORD_VERIFIED=1` therefore reaches a `TypeError` after successful assertions.  
  **Minimal fix:** remove the obsolete inventory argument and test the actual opt-in branch with a temporary receipt destination.

- **E2 — HIGH, VERIFIED mechanism: shared cache is output-determining beyond the catalogue.**  
  `probe:366`, `probe:379`, `probe:468` share the entire cache while describing it as catalogue storage. Embedded code in the pinned executable defines `Global.Path.bin = join(cache, "bin")`; ripgrep and LSP implementations resolve/install executables there. It also implements `cache/packages`, remote-skill caching, and GitLab model/config caches. Thus cached tool/LSP versions can change diagnostics and subsequent model requests without changing resume identity. **Actual contamination was not measured.** Remote skills/GitLab caches are conditional; their presence alone does not prove activation for this carrier.  
  **Minimal fix:** pin/hash relevant cached executables and prevent uncontrolled replacement, or isolate non-catalogue cache contents through an approved amendment. Correct the catalogue-only claim.

- **E3 — HIGH, VERIFIED: `--no-pure` reopens pre-M50 plugin execution.**  
  `probe:924` permits it; `probe:974` passes `pure=False` to discovery. This recreates the plugin initialization/fetch path the amendment explicitly closed, before router verification.  
  **Minimal fix:** reject/remove this flag for the benchmark entrypoint, or explicitly scope a separately authorized workflow.

- **E4 — MEDIUM, VERIFIED: resume omits an effective gate parameter.**  
  `poll_s` is accepted at `probe:915` and used at `probe:1138`, but absent from `_run_identity` and `RESUME_IDENTITY_KEYS` (`probe:490`, `probe:1218`). `benchmark/bench/progress_gate.py:143` checks process completion before deadlines and sleeps for `poll_s` at line 162. Increasing it can delay termination or accept completion beyond the intended ceiling.  
  **Minimal fix:** record/compare `poll_s`; add a resume mutation test.

- **E5 — MEDIUM, VERIFIED: persisted error scrubbing can leak truncated home-path fragments.**  
  `probe:559` and `benchmark/bench/provenance.py:1504` truncate stderr before `probe:1108` applies `portable_path`. Truncation inside a home prefix leaves a fragment that root substitution cannot recognize; bare usernames are also not scrubbed by that function.  
  **Minimal fix:** scrub complete error text before truncation, using the existing PII scrubber; test cuts through the home prefix and username.

- **E6 — MEDIUM, VERIFIED: damaged/empty row files bypass resume safeguards.**  
  `probe:1225` ignores malformed lines; `_check_resume` runs only when `done` is nonempty (`probe:1043`). A drift-stamped manifest with no recognized rows can be overwritten. A crash leaving an unterminated partial JSON line causes the next append (`probe:1192`) to concatenate a valid row onto corrupt text, losing that row on subsequent reads.  
  **Minimal fix:** reject drift stamps whenever a manifest exists; validate row-file integrity before continuation and refuse malformed tails pending explicit recovery.

- **E7 — LOW, VERIFIED: cleanup registration happens too late.**  
  `_make_run_dirs()` executes before `ctx["dirs"]` is assigned (`probe:963`). Missing/unreadable carrier, failed copy verification or mkdir failure leaves partially created per-run directories unregistered for cleanup.  
  **Minimal fix:** register intended paths before creation, or clean partial initialization inside the helper.

- **E8 — LOW, VERIFIED: design documentation contradicts the amendment.**  
  `docs/proposal-opencode-seeding.md:40` still says seed-only overlay; line 50 still hashes instruction inventory. `docs/lab-notebook.md:4459` still binds inventory into the receipt. `docs/open-questions.md:28` names the client carrier and says HOME amendment awaits confirmation; C125 at line 18 still requests ratification. `docs/qualify-a-model.md:701` says only catalogue storage is shared.  
  **Minimal fix:** reconcile these statements with the current ruling and implementation; retain historical wording explicitly as superseded.

**P4 — Remaining challenge results**

- **Personal/default directories:** configured child HOME/config/data/state paths exclude ordinary personal locations. This is environment redirection, not filesystem access control. Brew opencode is not selected on the default path. Shared cache, inherited PATH/tool environment and mutable persistent bench HOME/state still prevent a blanket “cannot influence output” conclusion.

- **Sampling:** CLI `--model` overrides the carrier’s default `model`; `small_model` matters for auxiliary requests, with title generation disabled here. Configured `limit` equality and forwarded `max_tokens` are distinct checks; neither proves the server’s eventual context-dependent budget. No fresh captured bodies were obtained in this review.

- **Still not compared on resume:** harness/prompt implementation changes, dirty corpus contents beyond its commit SHA, external tool/container versions, cache contents and persistent bench-state contents. Serving hashes describe committed submodule trees, not arbitrary dirty serving changes (`benchmark/bench/provenance.py:1620`).

- **Git/Docker:** `.git` is included in the whole-directory `/work` bind mount (`probe:814`); tick snapshots copy it too (`probe:283`). Graders invoke Go/Cargo/Gradle/npm recipes directly. `benchmark/run_aider_docker.sh:55` is a separate Aider launch path, not the probe’s grader. Static reading establishes exposure, not successful grades; four known-positive Docker checks remain **UNVERIFIED**.

- **Consumers:** no new deletion/restamping regression found. `compare` enforces policy mismatch, but its tests use `math500` fixtures; actual same-policy opencode comparison eventually encounters the missing opencode grader registration (`benchmark/bench/benchmarks.py:15`, `benchmark/bench/grade.py:1046`). This is an inherited limitation. Scoreboard neither checks scaffold epochs nor excludes `passed:null` from coverage counts (`benchmark/m1/scoreboard.py:122`); `rescore.py` is retired.

- **Tests:** per-field resume mutations and known-positive config/ancestor tests provide useful sensitivity. Receipt helper tests miss E1; HOME sentinel test explicitly lacks a positive control. Directory-name snapshots cannot detect overwrites of existing files. Integration helpers redirect HOME and four XDG homes, but retain other inherited `XDG_*` variables (`tests:404`); blanket hermeticity is therefore **not established**. Ordinary integration assertions do not validate all sampling fields under the exact production HOME construction.

The inherited transport-abort gap remains explicitly open as C124; this review does not close it.
