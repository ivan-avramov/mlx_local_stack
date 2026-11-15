P1 — Resolution ledger
- Location: v3 overall.
- Severity: blocker.
- Evidence: confirmed.
- Problem:
  - Resolved: D1, D3, D6, D8, D13, D15, D16, D18, D20; E7, E8, E12–E14.
  - Resolved for B4b-1, consumer remainder moved by C347: D10.
  - Not resolved: D2 (P7), D5 (P2, P5), D7 (P3), D9 (P4), D14 (P6), D17 (P2, P4), D19 (P2), D21 (P3, P6, P7); E1 (P2), E2 (P4), E3 (P3, P4), E4 (P7), E6 (P6).
  - Moved wholly to B4b-2: D4, D11, D12; E5, E9–E11.
- Concrete failure scenario: the prompt source, reconciliation path, or re-check publication fails before B4b-1 produces complete harvested evidence.
- Proposed change: address P2–P7 before dispatch.

P2 — The task-text path contradicts the `Corpus.source_root` contract
- Location: `docs/specs/m76-b4b-tg2-runner.md:57-66`; `benchmark/bench/corpus.py:103-107`; `benchmark/bench/corpus_tg1.py:102-111`; `benchmark/bench/tg2_materialize.py:116-117`.
- Severity: blocker.
- Evidence: confirmed.
- Problem: `source_root(lang)` is defined by the shared contract as the language’s exercises directory, while `tg2_materialize.exercise_dir` expects the polyglot checkout root. v3 composes `exercise_dir(source_root(lang), lang, slug)`, duplicating `lang/exercises/practice`. Returning the checkout root instead violates the shared contract.
- Concrete failure scenario: Rust prompt construction looks under `<root>/rust/exercises/practice/rust/exercises/practice/<slug>/.docs/`; the first request has no specification.
- Proposed change: retain `source_root(lang) = <root>/<lang>/exercises/practice` and read task text from `source_root(lang)/slug/.docs`; pass the checkout root separately to `prepare_tree`. Freeze the UTF-8 decoding and exact separator bytes.

P3 — Tg2 P426 invocations can silently lose the item barrier and reconciliation
- Location: v3 §2; `benchmark/bench/chain_core.py:1992-1996`; `benchmark/bench/tg1_runner.py:42-46,75-78`.
- Severity: blocker.
- Evidence: confirmed.
- Problem: v3 names four `P426_CONFIG_IDS` conversions but misses the probe-argv predicate. The core currently sends `--evidence p426` only when `config_id == "tg1-p426"`. A `tg2-p426` run therefore selects the ordinary evidence policy with `item_barrier="off"`.
- Concrete failure scenario: a tg2 s1 or rehearsal leg emits no ready/done barriers; P426 hooks cannot produce reconciled item records, defeating engagement, R2 and harvested row guarantees.
- Proposed change: derive `evidence="p426"` from `self.p426` or membership in `P426_CONFIG_IDS`. Test the exact argv for pilot, s1 and both rehearsals, while retaining the tg1 golden.

P4 — `--rehearsal r2|r3` does not define the required injection mapping
- Location: v3 §2 lines 92-99 and §3 lines 126-131; `benchmark/bench/p426_record.py:19-40`; `benchmark/bench/chain_core.py:498-505,1176-1183`; `benchmark/bench/p426_hooks.py:274-288`.
- Severity: blocker.
- Evidence: confirmed.
- Problem: v3 maps rehearsals to `mode="chain"`, `sessions=["s1"]`, `rehearsal=True`, but never maps R2 to `inject="reconcile-mismatch"` or R3 to `inject="stall-kill"`. Those values are what the hooks and frozen rehearsal validation consume.
- Concrete failure scenario: both rehearsal schedules run normally; R2 ends VALID and R3 contains no scored kill, so v8 refuses.
- Proposed change: specify the complete normalization, including both injection values, target Rust item, `chain.json.inject`, and exact generated argv.

P5 — The “exact” grade call does not bind grading to the snapshot
- Location: v3 §1 lines 70-73; `benchmark/bench/corpus.py:121-132`; `benchmark/bench/arm_runner.py:464-470`; `benchmark/bench/tg2_grade.py:961-975`.
- Severity: major.
- Evidence: confirmed.
- Problem: the call uses an undefined `work`; the corpus interface supplies `snap`, and the existing core creates content-stable snapshots specifically for grading. Passing `prepared.work` permits intermediate grading to race model edits. A missing snapshot also cannot be passed to `grade_item`.
- Concrete failure scenario: the model changes a helper while an intermediate grade runs; hashes and outcome describe different trees.
- Proposed change: state `grade_item(prepared.lang, snap.path, prepared.name, ...)` explicitly, with a pre-call tampered branch for `snap is None` and protected-tree violations.

P6 — A valid but stale positives record can be rebound into a new v8
- Location: v3 §3 lines 120-140.
- Severity: major.
- Evidence: confirmed.
- Problem: the record contains “probe identity”, but v8 is only required to bind `positives_sha256`; no required comparison ties its N16 commit, generation/scaffold identity, universe, draw, grader image, or corpus identity to the live v8 inputs.
- Concrete failure scenario: shared-core code changes after positives, rotating identities under C178; v8 binds the old record’s hash and proceeds without positives for the harness being run.
- Proposed change: require v8 to compare all recorded identity fields and the N16 worktree commit against its live inputs. Add a test where an intact, self-hashed record from another identity refuses.

P7 — Re-check records cannot be published by the existing run-record path
- Location: v3 §3 lines 145-149 and §4; `benchmark/bench/m76_sim.py:689-766`; `benchmark/bench/p426_harvest.py:1040-1090,1140-1157`; `benchmark/bench/p426_wave2.py:945-951`.
- Severity: blocker.
- Evidence: confirmed.
- Problem: `m76_sim.recheck` writes ordinary JSON without a self-hash. `publish_run_files_kv` requires self-hashes for every run file except `sequence.json`, and the existing run-file list does not include the re-check files.
- Concrete failure scenario: re-check 1 stops with rc 5, but final publication rejects `recheck-s1.json`; publication failure supersedes the stop with rc 4, or the file is omitted and B4b-2 cannot verify the gate.
- Proposed change: explicitly add both files to run publication under namespace `wave2.tg2`; either seal wrappers or exempt exactly these immutable names while binding their hashes in `sequence.json`. Reverify the current bytes on resume and test the real publisher plus ack path.

P8 — The prompt forbids an edit that the grader and final-tree contract support
- Location: v3 §1 lines 62-80; `benchmark/bench/tg2_grade.py:888-896`.
- Severity: minor.
- Evidence: confirmed.
- Problem: the exact prompt says never modify build files, while controlled Rust `Cargo.toml` changes are graded and explicitly required in final-tree tests.
- Concrete failure scenario: a valid vendored dependency edit is allowed by grading but discouraged by the model-facing policy.
- Proposed change: state the constrained `Cargo.toml` exception in the Rust helper rule, or remove changed `Cargo.toml` from the supported model-edit contract.
