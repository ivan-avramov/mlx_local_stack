## Round-1 and round-2 findings still in B4b-1 scope

Round-1 findings F1–F15 trace as resolved or mostly resolved except where noted. I did not see the E-ledger text. I took round 2 as my own N-series (N3 and N5 moved to B4b-2).

| Finding | Status in v3 |
|---|---|
| F1 chain config | Resolved. `P426_CONFIG_IDS`, builder `tg2_p426`, overlay and PRED_S keyed on config id, `needs_docker` from the corpus. |
| F2 shape / leg=session | Resolved. One block, one schedule leg per (session, language), `check_tg2_p426`. |
| F3 labels, order, reload | Resolved. The per-leg table covers them. |
| F4 scaffold hard-codes | Resolved. `p426_hooks`, `chain_ops`, `session_pinning_gate`, `validate_reports`, configgen are in scope. |
| F5 namespace / readers | The harvest namespace is resolved. The B8 side moved to B4b-2. |
| F6 freeze / amendment | Mostly resolved. The wall and deadline formulas are numeric. The settle-bound, rehearsal CLI and positives launch parts are not resolved (G4, G5). |
| F7 mapping / grade call | The mapping is resolved. The grade call fails on `private` and the snapshot location (G1). |
| F8 join bound / default universe | Resolved. |
| F9–F11 | F9 moved to B4b-2. F10 is partly resolved: the gates are defined, but publication of the re-check record fails (G3). F11 is resolved (no make-up). |
| F12 names / seams | Mostly resolved. |
| F13 harvest | Not resolved. The pinned regex does not match real files (G2). |
| F14, F15 | Resolved. |
| N1 hooks | Partly resolved. The `p426_hooks` language target is named. R3's selector in `chain_core` is not (G5). |
| N2 argv / rehearsal / freeze | Mostly resolved: the `--leg` mapping, record kinds and `--rehearsal` are specified. The rehearsal CLI is still wrong (G5). |
| N4 positives gate | The record and its sha binding are resolved. The launch seam is not (G4). |
| N6 re-check record | The path is resolved. It is not publishable (G3). |
| N7 `t_coop` | Resolved. |

## G1 — Every tg2 grade is refused: the snapshot lies inside `private`
- **Location:** spec §1 (Grade call, `snapshot`); `tg2_grade.py:952-958,990-992`; `structured_grade.py:65-88`; `arm_runner.py:231,1095`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - The core snapshots into `<grading-private>/snapshot-*/tree`. `Corpus.snapshot` documents that captures live under `private`.
  - `tg2_grade.grade` first calls `_disjoint(work, private, keep)`. That raises `TransportAbort` when `other in work.parents`, i.e. when the private dir is a parent of the mounted work tree.
  - Passing the core's `private` with `work=snap.path`, as the spec's call implies, therefore raises on every grade.
  - The harvest rule and `_registry` need `private` to be `grading-private` (`.tg2-registry`). The snapshot must live elsewhere.
- **Scenario:** the first intermediate grade of the first item raises. The leg is INVALID (systemic).
- **Change:** specify that `Tg2Corpus.snapshot` places captures outside `grading-private` (for example a sibling `grading-snap/` in the run dir, not under TMPDIR) and passes `private=grading-private` to `grade_item`. Add a test through the real `grade_item` path, not a mock.

## G2 — The pinned `TG2_BOOKKEEPING_RE` misses real tag names
- **Location:** spec §4; `tg2_grade.py:1056-1063,1096,1173,1201,1270`; `proc_guard.py:411-414`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:** the regex fails on three kinds of real file.
  - **`ls-<volume>`.** `_exists(..., "ls-" + name)` writes `ls-mlxbench-tg2-<hex>-w.out`. The regex allows only `ls-ps` and `ls-vol`.
  - **`<step>-n-x`.** `_remove_container(…, step)` calls `_nonce_of(…, step + "-n")`, which probes `tag + "-x"`. That writes `execute-n-x.out`. The regex allows only `-pre|-n|-rm|-v|-x` after a step.
  - **`plan-<container>`.** The holder is `ops.container_name()` = `mlxbench-<run_id>-<item>-<n>`. `run_id` is `YYYYMMDDTHHMMSS-hex`, with an uppercase `T`. The `[a-z0-9_.-]*` class rejects `plan-mlxbench-…T…`.
- **Scenario:** the pilot leg finishes, the harvest refuses the first real grade directory, and the sequencer stops with rc 4 after the leg ran. The hedge ("the implementer checks it") puts the failure on the implementer's AC run, not on the literal spec.
- **Change:** replace the regex with the tag grammar derived from the call sites (`plan-*`, `volume-*`, `own-*`, `cl-*`, `rm-*`, `ls-*`, `<tag>-(n|rm|v|n-x|x)`, `<step>-pre`, `holder`, `ls-ps`, `ls-vol`), with `[A-Za-z0-9_.-]` in names. Test it against every recorded real directory.

## G3 — The re-check record is not publishable, and the ack is ambiguous
- **Location:** spec §3 (Re-checks), §4; `p426_harvest.py:1040-1084,1140-1157`; `m76_sim.py:761-766`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - `publish_run_files` goes through `_publish_records(require_self_hash=True)`, which rejects any run record without a valid `sha256` self-hash. Only `sequence.json` is exempt.
  - `recheck-A8.json` has no `sha256` field.
  - The harvest's `classify` kinds are leg, run (the opencode run directory) and evidence. A harvest rule "`run/positives.json` → main" has no such kind; those files go through `publish_run_files`.
  - The ack hashes "that sha256" of the file. If the sequencer seals the record, the file sha and the self-hash field are two different values.
- **Scenario:** after s1 the sequencer writes `run/recheck-s1.json`, the end-of-sequence publication refuses it ("an immutable record without its sha256"), and the run files are never published.
- **Change:** have the sequencer seal the record (`ph.seal`) before writing it. Define the ack as the sealed record's `sha256` field. Replace the harvest line with the `publish_run_files` rule. Test publishing the re-check records and `positives.json`.

## G4 — The positives launch seam and its inputs are unspecified
- **Location:** spec §3 (Positives record), order; `arm_runner.py:1022-1038,1090-1092`; `run_tg1_probe.py:73`.
- **Severity:** major. **Evidence:** hypothesis.
- **Problem:**
  - `p426_wave2 positives` runs 12 `run_tg2_probe.py --tg2-inject` probes on N16.
  - A probe needs a live router and a worker loaded with N16, `--a4-v2-receipt`, `--frozen-prompt-date` (required, never defaulted), `--cancel-file`/`--manifest-ack`, and an out path under `m65/inject/`.
  - The positives run before the rehearsal manifest and v8, which are the only sources of the frozen prompt date and identity. The spec names none of these inputs or who starts the router.
  - The positives record says "probe identity", with no source.
- **Scenario:** the implementer invents a launch path. The test-writer cannot write a test beyond the record's shape.
- **Change:** specify the sequencer's launch (router start, A4 gate, worker load), where the frozen prompt date comes from, and the CLI inputs for the positives. If the date is operator-supplied, it must be checked against the later rehearsal manifest and v8.

## G5 — The rehearsal CLI and the R3 selector do not match the code
- **Location:** spec §3 (Rehearsals), v8; `p426_freeze.py:599-626,649-684,880-911`; `chain_core.py:1176-1183`; `p426_freeze.py:578-590`.
- **Severity:** major. **Evidence:** confirmed (CLI, selector); hypothesis (settle bound).
- **Problem:**
  - **CLI.** `p426_freeze rehearsal --lever kv` requires `--pair <ref>,<test>`, an `--arm-worktree` for each arm of the pair, and `--frozen-prompt-date`. v3's command passes only `n16=<W>`.
  - **Manifest check.** `cmd_v8` refuses a manifest unless `manifest["arms"]` equals the pair. A manifest for N16 alone is refused.
  - **R3 selector.** `chain_core.p426_inject_stall` applies only when `lang == "python"` and picks the first python item. The v3 text names `p426_hooks` for the language target but not this selector, so the R3 kill never fires on Rust.
  - **Settle bound.** The v8 settle bound uses `request_elapsed_max` over R2 and R3. A killed R3 item may have no item record. The function returns None, and `cmd_v8` currently refuses on that.
- **Scenario:** R3 ends as a normal VALID leg without the kill. The rehearsal gate cannot pass, or the v8 command refuses.
- **Change:** state the rehearsal CLI with the pair, both worktrees and the date. Make the stall-kill selector corpus-driven (first item of the first language). State how `settle_bound_s` handles a leg with no request records.

## G6 — The prompt is not specified to the byte
- **Location:** spec §1 (Prompt); `m65-tg2-corpus.md:73-80`.
- **Severity:** minor. **Evidence:** confirmed.
- **Problem:** `{H}` is given as quoted fragments ("Rust: helper modules under src/", …) attributed to M65 v5. M65 v5 has no such phrases; it states only the allowlist. It is unclear whether the "Rust:" label belongs inside `H`, whether a terminating period follows, and whether the output ends at `{H}`. The prompt bytes enter the policy hash and results, so the golden test cannot be written.
- **Change:** give the four `H` strings as exact literals, including punctuation and the ending.

## G7 — The final-tree membership has no named enumerator
- **Location:** spec §1 (Final tree); `tg2_grade.py:889-908`.
- **Severity:** minor. **Evidence:** confirmed.
- **Problem:** "every path the grader accepts as a model edit" depends on `_new_file_reason`, which is private and takes `solution_dirs` and `existing`. `tg2_grade` is read-only. The implementer must copy the logic or call private functions, which then drift from the grader.
- **Change:** define it as the complement of what `tamper_reasons` rejects: the files that are new or changed in a tree that `tamper_reasons` approves. Name the call. Test with a helper file, a Java package helper and a changed `Cargo.toml`.

Everything else I traced is consistent with the code: the pins equal the sidecar values, the grader mapping fits `GradeOutcome`, the guard API satisfies `tg2_grade`'s `ops`, and the per-leg table fits the readers.