**P1 — BLOCKING**, reviewed HEAD `77ddc98`.

Focused tests: **151 passed, 1 failed**. The failure assumes `~/…` takes precedence over `$STACK_WORKDIR/…`; it passed when rerun with `STACK_WORKDIR` unset. Real pinned-1.18.30 mock checks verified git-directory execution, seed/sampling forwarding, and session export. No repository edits, port-8000 requests, or real opencode configuration access.

**P2 — Prior-findings closure**

Abbreviations: `R` = `benchmark/run_opencode_probe.py`; `T` = `benchmark/bench/tests/test_opencode_probe_seeding.py`; `S` = `benchmark/bench/tests/test_scaffold_policy_compare.py`. All statuses below are **VERIFIED** by code inspection and cited tests unless stated otherwise.

| Prior finding | Status | Code and test evidence |
|---|---|---|
| Codex B1 / Claude B4: executable fallback | **Partial** | `R:92,329,487,602,607,864`; `T:62,75,89,101,114,131` verify exact executable and missing-pin refusal. Version validation remains too late: C4. |
| Codex B2 / Claude B1: resume identity, duplicate rows | **Specified keys closed; identity incomplete** | `R:934,966,1103`; `test_resume_*`, `T:456–492`. Seed/scaffold/bin/version mismatches refuse; recorded keys skip. C1 remains. |
| Codex B3 / Claude B1: comparison ignores policy | **Core fix closed; regression introduced** | `provenance.py:421,576`, `compare.py:321`; `S:32,38,44,50,55,60`. Legacy/new refuses; equal hashes pass. C5. |
| Codex B4: lost main-branch records | **Closed** | Three-dot diff preserves C123, PLAN M59 and handoff; verified by inspection, no automated test. |
| Codex B5 / Claude B5: unbound receipt | **Partial** | `R:432–478`; `T:189,201,221,232` cover hash invalidation and legacy markers. Effective configuration remains incompletely bound: C3. |
| Codex B6 / Claude B6: overlay failure handling | **Closed for reported cases** | `R:489–503,988–1001`; `T:306,317,613`. Nonzero, timeout, malformed JSON refuse; earlier manifest receives drift stamp. Two discovery calls remain explicitly accepted. |
| Codex B7 / Claude B9: documentation | **Partial** | README/campaign seed notes and M54/M55 annotations corrected; contradictions remain: C8. Inspection only. |
| Codex B8: failed transport becomes scored row | **OPEN — HIGH, inherited** | `R:1016,1030,1043,1068`: nonzero exit still proceeds through export, grading and append. No closing regression test. Abort transport/session failures before grading; distinguish intentional gate termination. |
| Codex B9: manifest overlay hash | **Closed** | `R:1006`; `test_manifest_records_the_overlay_sha_per_item_before_any_traffic`, `T:500`. |
| Claude B2: overlay-only model loses sampling | **Closed for options** | `R:517–532`; `T:275,282,288,298`. Missing/drifted options refuse. Limit contents remain unchecked: C7. |
| Claude B3: ancestor instructions | **Ancestor boundary closed; global exposure remains** | `R:544,977`; `T:559,604` includes positive/negative real-binary capture. C2. |
| Claude B7: overlay mutation/export | **Partial** | `R:1023–1030`; `T:625` verifies restoration ordering with mocks. Real binary produces false attribution: C6. |
| Claude B8: weak tests | **Improved, incomplete** | Meaningful executable, resume, comparison and real ancestor-boundary tests added. Missing cases are exposed below; portability test has environment-dependent expectations. |
| Claude B10: informational residuals | **Mixed** | Merge issue closed. AgentBench base-0 schedule remains (`run_agentbench_os.py:1077`); separate cache probe still spawns bare opencode (`session_cache_probe.py:97`). Neither was fixed here. |
| Claude B11: pre-M50 ordering | **Verified with qualification** | Configuration resolution, executable stat/access and C114 discovery precede router verification. The M50 ordering test still forbids an early version check (`test_m50_entrypoints.py:195`); C4 explains the consequence. |

**P3 — New findings**

- **C1 — HIGH · VERIFIED — Resume still mixes effective scaffolds.**  
  `benchmark/run_opencode_probe.py:936,954,1109`. Changing global configuration passes `_check_resume`; the next new item replaces the manifest with current configuration metadata while retaining earlier rows. Shipped-config hash, model/sampling identity, limits and gate settings are also absent from this check. I directly reproduced acceptance of differing global hashes. **Minimal fix:** compare the effective run identity before continuation and preserve original attribution. Excluded ancestors need not invalidate resume; instruction sources actually loaded do.

- **C2 — HIGH · VERIFIED — Git initialization does not isolate global instructions.**  
  `benchmark/run_opencode_probe.py:549,570,588`. A temporary `$XDG_CONFIG_HOME/opencode/AGENTS.md` sentinel entered the system prompt **inside a git-initialized item**, but appeared in neither `ancestor_instruction_files` nor its policy hash. Editing it left the global-config hash unchanged. Binary source also identifies `CONTEXT.md` as an instruction candidate; the inventory omits it. **Minimal fix:** inventory and fingerprint actual loaded instruction sources, including global AGENTS, or explicitly isolate them. The requested ancestor names are walked portably, but that list is not the actual complete loading set.

- **C3 — MEDIUM · VERIFIED — Receipt can remain valid across an effective configuration change.**  
  `benchmark/run_opencode_probe.py:461`; `benchmark/bench/tests/test_opencode_probe_seeding.py:422`. Pinned v1 loads global **`config.json`**, while hashing includes only `opencode.json` and `opencode.jsonc`. I changed an agent prompt in `config.json`: resolved configuration changed, hash did not. Additionally, the test exercises temporary shipped configuration, then stamps the ambient configuration’s hash—without testing that configuration. **Minimal fix:** include all loaded sources and bind the receipt to the configuration actually exercised. Current executable/shipped-file/test-file changes correctly invalidate it; `None` correctly remains unverified.

- **C4 — HIGH · VERIFIED ordering; v2 side effects not re-executed — Version rejection occurs after discovery.**  
  `benchmark/run_opencode_probe.py:864,866,892`. `_require_opencode_bin` validates file existence/executability, not version. An absolute override—or replacement at the pinned path—pointing to v2 executes `debug config` before version rejection, even without `--allow-version-drift`. Exact-path propagation fixes PATH fallback but does not enforce C123 before execution. **Minimal fix:** validate that same executable with `--version` before discovery; explicitly exclude v2. Update the M50 test that currently forbids this permitted preflight.

- **C5 — HIGH · VERIFIED — Generic cleanup newly deletes otherwise-compatible legacy opencode results.**  
  `benchmark/bench/provenance.py:421,576`; `benchmark/bench/generate.py:338–343`. Generic `current_manifest_lite` lacks `client=opencode`, producing `"n/a"` against legacy `"pre-C121"`. With otherwise-identical manifests, compatibility changed from true to false; a temporary `provenance_precheck(..., clean_stale=True)` deleted both rows and manifest. **Minimal fix:** reject externally generated opencode axes before generic cleanup/resume, or supply an appropriate scaffold-aware current identity. Do not weaken legacy-versus-seeded refusal.

- **C6 — MEDIUM · VERIFIED — Every normal overlay normalization is attributed to the model.**  
  `benchmark/run_opencode_probe.py:984,1024–1029`. Real v1’s **pre-run `debug config` adds `$schema`** to `opencode.json`. With zero mock tool calls, its hash already differed before execution, so `overlay_rewritten_by_model` becomes true. Restoration is normalized again during export. **Minimal fix:** establish the baseline after successful resolution, validate the permitted normalization, and compare post-run state against that baseline. Keep authored and resolved hashes distinct if both are needed.

- **C7 — MEDIUM · VERIFIED — Limits are presence-checked, not matched.**  
  `benchmark/run_opencode_probe.py:530`. Any nonempty `limit` dictionary passes, including a different context/output budget. Equal sampling options therefore do not establish the shipped model entry; changed context limits can change compaction behavior. **Minimal fix:** compare relevant resolved limits with the shipped entry and include them in resume identity.

- **C8 — LOW · VERIFIED inconsistencies; historical exposure is inference.**  
  `docs/proposal-opencode-seeding.md:10,14,16,47`, `docs/open-questions.md:24`, `docs/lab-notebook.md:4447`. The proposal retains M54/unseeded, absent-CLAUDE and version-migration claims contradicted by its annotations; open questions retains “reload control proved nothing.” The notebook upgrades present-day reproduction into certainty about **every historical row**, which the available transcripts cannot establish. **Minimal fix:** annotate superseded claims consistently; distinguish demonstrated loading behavior from inferred historical exposure.

**P4 — Remaining requested checks**

- **Options equality:** shipped opencode configuration is the appropriate carrier to check under the four-carrier rule; it does not independently establish registry/carrier agreement. Dictionary key order and `1` versus `1.0` do **not** cause false refusal. Real resolved configuration passed.
- **`.git`:** initialization follows `_prepare` and precedes overlay creation. Solution/test comparisons target specific files, so `.git` does not directly alter those checks. A real git-directory mock run and export succeeded without configured Git identity. **ASSUMPTION/unverified:** Docker grading across all four languages; Docker was not run.
- **Export ordering:** restoration precedes export and the main child is waited for. Descendant-process quiescence is not guaranteed; a surviving writer race was **not reproduced**.
- **Other consumers:** scoreboard does not consume the new compatibility guard and remains scaffold-unaware. Ordinary non-opencode manifests without the new field remain unaffected. M50 stub creation is outside each test’s `tmp_path`; its no-output assertions remain meaningful, but its version-order expectation needs C4’s correction.
