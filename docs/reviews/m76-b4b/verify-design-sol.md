## Round-1 verification

- D1 — Resolved. No make-up legs; DNFs score 0 and paired-exclusion sensitivity is specified.
- D2 — Not resolved. Fixed α and the two stop/label decisions are stated, but the recheck output paths and durable acknowledgement contract are invalid or absent (P5).
- D3 — Resolved. There is no separate screen leg; the diagnostic uses s1’s first 10 items per language.
- D4 — Not resolved. A8 members are named, but the existing A7 packet machinery cannot represent tg2 inputs (P6).
- D5 — Not resolved. The abstract-method inventory and outcome mapping are substantially improved, but the prompt, grade invocation, and final-tree evidence remain incomplete (P1, P4, P7).
- D6 — Resolved. `tg2_p426` has the required P426 shape, exact leg table, ordering, seeds, prefixes, and five-per-language reload.
- D7 — Resolved. `tg2-p426`, P426 treatment, overlay behavior, prediction defaults, and Docker selection are specified.
- D8 — Resolved. Scaffold-dependent validation, A4, report validation, and config generation are all in scope.
- D9 — Not resolved. Pilot and wall formulas are now defined, but R2/R3 cannot run through the existing rehearsal interfaces (P3).
- D10 — Resolved. `wave2.tg2` is legal; corpus-specific readers, discovery, and `kv_a8_sessions()` are specified.
- D11 — Resolved. A8 explicitly permits bounded `VALID_WITH_DNF`.
- D12 — Resolved as raised. `languages` reaches `axis_verdict`, and HOLD, noise, flags, and rendering are named. P9 and P10 are additional defects.
- D13 — Resolved. The default universe and per-language grade-join bounds are specified.
- D14 — Not resolved. Item/seed/root/retry are present, but the verifier and durable positive-gate contract remain underdefined (P8).
- D15 — Resolved. Universe and draw have independent constants and consistent redraws refuse.
- D16 — Resolved. The closure-derived identity exceptions are explicit.
- D17 — Not resolved. Entry, draw, and corpus root are named, but the new `--leg` interface is not mapped to shared-core mode/session semantics, and rehearsal argv remains undefined (P2, P3).
- D18 — Not resolved. Step names are closed, but Docker bookkeeping `<tag>` remains an open grammar (P11).
- D19 — Resolved. `source_root` is a public corpus seam.
- D20 — Resolved. Refusal text is policy/corpus-derived.
- D21 — Not resolved. Acceptance names most missing tests, but several asserted behaviors still lack implementable contracts; it also does not require incomplete A8 to produce a blocking flag.

## Additional findings

### P1 — Tg2’s first prompt points at material absent from the model tree
- Location: `m76-b4b-tg2-runner.md` §1 lines 62–65; `corpus_tg1.py:120–130`; `tg2_materialize.py` excluded roots.
- Severity: blocker
- Evidence: confirmed
- Problem: “tg1’s prompt contract with tg2 language wording” inherits the instruction to read `.docs/instructions.md`, while tg2 materialization excludes `.docs`. The specification does not provide another exact task-text source.
- Concrete failure scenario: the literal adapter tells the model to read `.docs/instructions.md`; the file does not exist, so the first request lacks the exercise specification.
- Proposed change: freeze the complete tg2 prompt template and inline the pinned source exercise’s `.docs/instructions.md` bytes. Define solution/test wording and new-file policy explicitly, and test exact prompt bytes for every language.

### P2 — `--leg` has no mapping to the shared-core mode contract
- Location: spec §2 lines 92–112; `chain_core.py:635–637,1115–1118`; `p426_record.py:11–40`.
- Severity: blocker
- Evidence: confirmed
- Problem: the new entry exposes only `--leg pilot|s1|s2|reload`, but shared code requires `a.mode`, and frozen-record validation accepts only `pilot`, `chain`, `makeup`, or rehearsal semantics.
- Concrete failure scenario: leaving `mode` absent crashes; setting it to `s1` causes `p426_record` to reject or key-fail before launch.
- Proposed change: specify the adapter exactly: pilot → `mode=pilot, sessions=[]`; s1/s2/reload → `mode=chain, sessions=[leg]`; define the corresponding rehearsal mapping and ensure `chain.json` records both normalized mode and tg2 leg.

### P3 — Tg2 R2/R3 rehearsals are not runnable
- Location: spec §3 lines 120–124; `chain_core.py:1176–1183`; `p426_freeze.py:246–350,675–700`.
- Severity: blocker
- Evidence: confirmed
- Problem: no tg2 rehearsal schedule or argv exists. R3 injects only into Python; R2 validation requires a Go slot; existing v8 expects R1 off/on plus two arm worktrees and derives `settle_bound_s` from R1. Tg2 has neither Python/Go nor R1.
- Concrete failure scenario: R3 receives no kill injection, while an otherwise correct Rust/JavaScript/Java/C++ R2 is rejected for not invalidating Go; v8 cannot be produced.
- Proposed change: define an exact rehearsal table, target language/item, chain argv, one-arm manifest semantics, and `settle_bound_s` source. Parameterize injection and freeze validation by corpus instead of Python/Go.

### P4 — The grade call omits required runtime and policy arguments
- Location: spec §1 lines 68–70; `tg2_grade.py:961–968`; `arm_runner.py` grade call.
- Severity: major
- Evidence: confirmed
- Problem: `prepared` and `extra_crates` remain ellipses, and `guard=guard` is absent. Omitting the guard bypasses the run’s process accounting; passing `reference_extra_crates` would incorrectly grant model runs item-specific reference dependencies.
- Concrete failure scenario: a grader memory kill is not attributed through the item guard, or a candidate is allowed a dependency intended only for freezing the reference.
- Proposed change: state the complete call with `prepared=prepared.prepared`, `solutions=entry["solutions"]`, `prepared_cargo_toml=entry.get(...)`, `extra_crates=()`, `guard=guard`, `timeout=entry["timeout_s"]`, and the existing keep/sequence/boundary/final arguments.

### P5 — Recheck output paths and acknowledgement cannot work as specified
- Location: spec §3 lines 130–134; `m76_sim.py:689–766`; spec §5 lines 148–151.
- Severity: blocker
- Evidence: confirmed
- Problem: `m76_sim.recheck(out=...)` treats `out` as a directory and always writes `recheck-A8.json` beneath it. Passing `recheck-s1.json` therefore creates `recheck-s1.json/recheck-A8.json`. No sealed record binds `--recheck-ack` to the resumed sequence.
- Concrete failure scenario: B8 looks for `recheck-s1.json` as a file and fails; alternatively a transient acknowledgement resumes s2 with no durable evidence of what was acknowledged.
- Proposed change: define canonical immutable s1/s2 file paths and either extend `recheck` to accept an exact output file or publish from separate temporary directories. Record the recheck hash and acknowledgement in `sequence.json` or another sealed artifact, and require B8 to verify both.

### P6 — “As A7” cannot generate A8 panel packets
- Location: spec §6 lines 163–166; `p426_panel.py` A7 context/packet/export/ingest functions; tg2 universe.
- Severity: blocker
- Evidence: confirmed
- Problem: A7 packet code requires singular `solution` and `test`, reads `.docs/instructions.md` through the prepared tree, and exposes only A7 CLI/context seams. Tg2 uses `solutions`/`tests` arrays, excludes `.docs`, and allows multiple changed files.
- Concrete failure scenario: adding `A8-s1` to the member list reaches `_a7_packet` and fails on missing `solution`, `test`, or prepared `.docs/instructions.md`; no valid packet can be exported or ingested.
- Proposed change: define `kv_a8_context` and `_kv_a8_packet`, A8 CLI inputs, pinned task-text derivation, multi-file diff/protection rules, expected-member expansion, and exact export/ingest/completeness behavior.

### P7 — Final-tree evidence omits files that tg2 actually grades
- Location: spec §1 lines 64–66 and §6 packet definition; `corpus.py:78–83,140–141`; `corpus_tg1.py:164–188`; `tg2_grade.py:875–907`.
- Severity: major
- Evidence: confirmed
- Problem: tg1’s final tree copies only declared editable files. Tg2 permits new helper files and constrained `Cargo.toml` edits, neither of which is in `entry["solutions"]`.
- Concrete failure scenario: a passing Rust answer adds a dependency or a C++ answer adds a helper file; grading uses it, but final evidence and the panel diff omit it.
- Proposed change: define tg2 final-tree membership as every grader-permitted mutable implementation file, including changed `Cargo.toml` and allowed helpers, while retaining the content-addressed layout and missing-solution reporting.

### P8 — Positive gates have no exact, resumable artifact contract
- Location: spec §3 lines 115–124 and acceptance 3; `m62/inject_verify.py:176–182,286–291`.
- Severity: major
- Evidence: confirmed
- Problem: the current verifier hard-codes the tg1 scaffold and has no scaffold argument. The spec also does not assign ownership or define a sealed record for known/injected positives; v8 binds only rehearsals.
- Concrete failure scenario: a resumed campaign proceeds using stale positive results or a verifier changed with an incompatible parameter interpretation, while v8 still validates.
- Proposed change: freeze the addendum source and verifier CLI/label semantics; write one sealed positives record containing probe identity, item/seed/kind, attempts, result hashes, and verifier outcomes; bind its hash into v8 or the sequence.

### P9 — Incomplete A8 evidence is not a blocking signal
- Location: spec §6 lines 155–162 and acceptance 1; `p426_signals.py:1721–1764`.
- Severity: major
- Evidence: confirmed
- Problem: `_kv_a8_section` returns “incomplete” without a verdict, but the enumerated A8 flags contain no incomplete flag. `kv_flags` skips axes without a final verdict.
- Concrete failure scenario: one s2 pair is rejected; the rendered axis says incomplete, but machine consumers see no A8 blocking flag.
- Proposed change: add a blocking `a8_incomplete` flag and require it in the public JSON/render acceptance test.

### P10 — Sensitivity compares only verdict class, not the safety disposition
- Location: spec §6 lines 157–161; C346(1).
- Severity: major
- Evidence: confirmed
- Problem: C346 requires disagreement to reach the operator, but v2 flags only a different PASS/LOSS/UNDECIDED class. HOLD languages and session-interaction blocking can change while the class remains unchanged.
- Concrete failure scenario: both runs are UNDECIDED, but only the full DNF=0 analysis triggers a Rust HOLD; no sensitivity flag is emitted.
- Proposed change: compare the complete blocking decision state: verdict class, HOLD status/languages, and interaction blocking. Keep expected reduced-size warnings separate from this comparison.

### P11 — Harvest’s bookkeeping-tag language is still open-ended
- Location: spec §4 lines 137–142; `tg2_grade.py:1058–1350`; `p426_harvest.py` classifier.
- Severity: minor
- Evidence: confirmed
- Problem: `<tag>` is not an enumerable grammar. Actual names include nonce-bearing `plan-*`, `volume-*`, `rm-*`, `own-*`, `cl-*`, and derived verification suffixes.
- Concrete failure scenario: an implementation accepts arbitrary `*.out`/`*.err`, defeating near-match refusal, or rejects a real nonce-bearing volume artifact.
- Proposed change: publish the exact regex/allowlist or a shared `tg2_grade` bookkeeping-tag classifier, with fixtures for every emitted form and near-match rejection.
