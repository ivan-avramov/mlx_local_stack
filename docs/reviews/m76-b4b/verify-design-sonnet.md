## Round-1 findings: status in v2

| Round-1 finding | Status | Reason |
|---|---|---|
| F1 chain config | Resolved in intent | `tg2-p426`, builder `tg2_p426`, no overlay, `needs_docker` from the corpus, tg1 prediction defaults. The builder dispatch is not named (see N2). |
| F2 schedule shape | Resolved | `tg2_p426` emits the `blocks/legs/invocations` shape, one session per leg. |
| F3 labels / order / reload | Resolved | The per-leg table fixes session dir, seed, language order and item order; reload is 5 per language. |
| F4 scaffold hard-codes | Mostly resolved | `chain_ops`, `session_pinning_gate`, `validate_reports` and the configgen target are now in scope. `p426_hooks.py` is missing (N1). |
| F5 B8 / harvest constants | Mostly resolved | `wave2.tg2` matches `NAMESPACE_RE`, the smoke deny pattern no longer applies, readers are parameterised. `_sequence_leg_reasons` is missed (N3). |
| F6 freeze / amendment | Partly resolved | The wall formula is numeric and sourced. The rehearsal, settle-bound and positives-gate parts are not (N1, N2, N4). |
| F7 grader mapping | Resolved | `failing = result.failing(set(entry["leaves"]))`, entry `timeout_s`, flags, and tampered shape are all stated. |
| F8 join bound / universe default | Resolved | `grader_timeout_s = 2 × max timeout_s + 300` gives a join bound of 1380 s. The default universe comes from the policy. |
| F9 HOLD surfaced | Resolved | `kv_flags`, `render_kv`, `kv_axis_verdict(languages)`, the noise floor and a CLI-level test are specified. |
| F10 stricter α | Resolved by C346, with a residual literal defect | Gates replace the stricter α. The `recheck(out=…)` path does not match the code (N6). |
| F11 make-up | Resolved | Make-up is removed, with the paired-exclusion sensitivity. |
| F12 names | Mostly resolved | Entry, draw seam, corpus-root seam and pins are named. `--rehearsal` / `--inject` and the `--leg`-to-record-mode mapping are missing (N2). |
| F13 harvest | Resolved | A closed table of exact unmatched names. |
| F14 byte-identical | Resolved | The boundary is defined; closure identities are asserted to change. |
| F15 acceptance | Resolved | Chain start, validation, schedule readers, join bound, HOLD in flags and render, and the public CLIs are covered. N1–N5 add gaps. |
| Scope request (panel) | Resolved in scope, defective in design | See N5. |

The draw and universe pins in v2 equal the committed sidecar values.

## New findings

### N1 — R2 and R3 cannot work on tg2: the injection hooks are python/go-specific and `p426_hooks.py` is not in scope
- **Location:** spec §3 (c), Scope; `p426_hooks.py:24-30,275-279`; `chain_core.py:1176-1183`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - R2's injected mismatch fires only when `_is_go(slot, done)` is true, on the first Go item.
  - R3's `--inject-stall-item` selection is `p426_inject_stall`, which requires `lang == "python"`.
  - A tg2 R2 leg is therefore VALID, not INVALID with `R2_REASON`. The rehearsal gate fails and the v8 record is never written.
  - `p426_hooks.py` is not in the Changed list, and `chain_core` is listed without this change.
- **Scenario:** the implementer runs R2 on a Rust item. Reconciliation is never perturbed and the leg ends VALID.
- **Change:** add `p426_hooks.py` to scope. State the R2/R3 injection target as the first item of the leg's first language (rust). Test R2 giving INVALID `R2_REASON` and R3 giving a scored kill on a tg2 leg.

### N2 — The rehearsal and freeze path for tg2 is underspecified, and the chain argv omits flags
- **Location:** spec §2 argv and §3 (c)(d); `p426_freeze.py:246-253,256-280,649-702`; `p426_wave2.py:89-97,174-205`; `run_tg1_chain.py:230-236,284`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:**
  - **Manifest step.** The §3 order has no step that writes the rehearsal manifest (`p426_freeze rehearsal`). Rehearsal legs accept only that manifest and need its identity. `cmd_v8` requires `--rehearsal-manifest`.
  - **R1 removed.** v2 drops R1, but `cmd_v8` still requires `--r1-off`/`--r1-on`. It derives `settle_bound_s` from R1's `request_elapsed_max` and `max_request_elapsed_s` from `historical_walls`, and records `r1_env_difference`. None of these has a tg2 source in v2.
  - **Rehearsal binding.** `binding_problems` and `kv_rehearsal_legs` expect the names `tg1-m76-rehearsal-*`.
  - **Argv.** The new chain argv has `--leg pilot|s1|s2|reload` but not `--rehearsal` / `--inject`. It does not say how `--leg` selects the record kind (pilot → v8 base, others → amendment, rehearsal → manifest). `check_p426` constraints (one session, no smoke) are not restated.
  - **Gate parameters.** `kv_pilot_leg` and `pilot_gate_problems` (name `tg1-m76-…-pilot`, `PILOT_N` 5) are not stated as parameterised by corpus.
- **Scenario:** a literal implementer cannot produce the R2/R3 receipts or the v8 record. The test-writer cannot write the freeze round-trip.
- **Change:** list each `p426_freeze` command with its tg2 inputs. State the settle-bound source, the R1 replacement, the rehearsal leg names and directory, and the chain's `--leg` / `--rehearsal` / `--inject` and record-mode mapping.

### N3 — B8 still rejects `VALID_WITH_DNF` through `_sequence_leg_reasons`
- **Location:** spec §5; `p426_verify.py:502-508`.
- **Severity:** major. **Evidence:** confirmed.
- **Problem:** v2 changes `_leg_reasons` only. `_sequence_leg_reasons` reports `rule 1: sequence.json leg state != 'VALID'` for every pair. The pair becomes unaccepted, `_kv_a8_section` returns "incomplete", and a decider with one DNF produces no verdict. Acceptance 1's `VALID_WITH_DNF` CLI test would catch it, but the spec does not name the function.
- **Change:** name both functions. State that `VALID` or `VALID_WITH_DNF` with at most `MAX_DNF` DNF slots is accepted in both (A8 only).

### N4 — The pre-launch positives (a)(b) are not enforced by any record or gate
- **Location:** spec §3 order (a)(b), Goal, AC3.
- **Severity:** major. **Evidence:** confirmed (no consumer in the v2 text).
- **Problem:**
  - The grader known-positives and the 12 injected positives are in the order list, but nothing records them.
  - The v8 base records only the R2/R3 receipts. `sequence.json` has no positives entry. B8 and the pilot gate do not check them.
  - The Goal says the decider runs "after injected positives…". The B4 candidate had a recorded positives gate (L10, L13). v2 dropped it.
  - "(b) on N16" does not say whether X is exercised.
- **Scenario:** the sequencer starts the pilot and decider with no positives run, and nothing refuses.
- **Change:** a sealed positives record (the grader results and the `inject_verify` verdicts per language and kind). The v8 base binds its sha256. The sequencer and `verify_a8_kv` re-verify it. State whether X is required.

### N5 — The A8 panel packet "as A7" cannot be built from the A7 code
- **Location:** spec §6 `p426_panel`; `p426_panel.py:663-690`, `:1798-1815`, `:1905-1907`.
- **Severity:** major. **Evidence:** confirmed for the start tree and diff; the rest is hypothesis.
- **Problem:**
  - `_a7_packet` needs a universe entry with string `solution` and `test` fields; tg2 entries have `solutions` / `tests` lists.
  - It builds the start tree from raw `polyglot_root`. The tg2 model-visible tree is `tg2_materialize.prepare_tree` output (JS and Java skip rewrites, a Rust `OFFLINE_CRATES.md`). A raw diff would show the grader rewrites as model edits.
  - `_a7_diff` handles a single solution file; Java and C++ items have several editable files.
  - `kv_a7_context`, `kv_members`, `kv_expected_members`, `kv_check_frozen` and `KV_INPUT_SOURCE` are keyed to A7 / tg1.
- **Scenario:** `kv-export` refuses every A8 item ("universe has no entry (solution / test)"), or exports leaky or noisy diffs.
- **Change:** specify the tg2 start tree (prepared via `prepare_tree`), the multi-file diff, the universe reader, and the member / context functions. Add a packet test over one real item per language.

### N6 — `m76_sim.recheck(out=…)` writes a directory, and the record location is ambiguous
- **Location:** spec §3 re-checks and §4; `m76_sim.py:763-765`.
- **Severity:** minor. **Evidence:** confirmed.
- **Problem:**
  - `recheck` treats `out` as a directory and writes `recheck-A8.json` inside it. Passing `<wave2.tg2>/recheck-s1.json` creates a directory of that name containing `recheck-A8.json`; re-check 2 does the same.
  - m76_sim is read-only, so v2 cannot change this.
  - `--recheck-ack <sha256 of that record>` is undefined for a directory.
  - "Recheck records → main" has no harvest rule: it is not under a leg root or `run/`.
  - It is also unclear which directory `<wave2.tg2>` is, B8's `m76/wave2.tg2/run/` or the sequencer out-base. B8 can only read files covered by its `inputs`.
- **Change:** call `recheck(..., out=<dir>)`, then move or copy `recheck-A8.json` to `recheck-s1.json` (or name the file as written). State the exact path, how it is published, and what the ack hashes.

### N7 — `t_coop` still uses the tg1 grader timeout table
- **Location:** `chain_ops.py:27,996-999`; spec §2 and §1 `grader_timeout_s`.
- **Severity:** minor. **Evidence:** hypothesis. I did not trace what uses `t_coop`.
- **Problem:** `t_coop(prompt, lang)` uses `GRADER_TIMEOUT_S.get(lang, 300)`, a python/go table that defaults to 300 s for tg2 languages. tg2's whole-grade bound is longer (the join bound is 1380 s). `chain_ops` is in scope but this value is not named.
- **Change:** take the grader bound from the corpus identity in `t_coop`, or state that 300 s is deliberate.

## What v2 resolves cleanly
The schedule table, pins, grader mapping, join bound, harvest table, B8 reader parameterisation, HOLD and flags, make-up removal and the closure-identity boundary all trace against the code. Remaining defects are N1–N5 (major) and N6–N7 (minor).