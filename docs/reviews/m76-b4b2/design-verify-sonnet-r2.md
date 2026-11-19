Round 1: 14 of 16 items are resolved, 2 are partly resolved (F5, F14), and 0 are unresolved. In v1.2 the new C368 rulings add 1 major defect (G1), 1 major defect (G2) and 5 minor ones. I could only read files, so none of this was run. Evidence is "confirmed" where I traced the source, and "hypothesis" otherwise.

## Round-1 status

| Round-1 finding | Status | Why |
|---|---|---|
| F1 B8 sha binding | Resolved | `B8.json` never changes. A8 lives in `B8-A8.json` with `base_b8_sha256`. A1–A7 stay bound to `B8.json`, and A8 members bind to `B8-A8.json` (§3.5, §6.1). The two verification steps are not stated (see G7). |
| F2 refusal on a partial decider or another pair | Resolved | Built only for `TG2_PAIR`. Missing sessions are `status: incomplete`, and only corruption refuses (§3.2). |
| F3 protected-file rule and `Cargo.toml` | Resolved | §6.2 asserts that no protected path other than a grader-accepted Rust `Cargo.toml` is new or changed, and diffs `Cargo.toml` as content. This matches `accepted_files` and `cargo_manifest_reasons`. |
| F4 reload control | Resolved | §4.2 compares reload to s1 only, per arm, with a per-item `sampler_seed` assert and no s2 comparison. §3.6 adds the key-set rule. |
| F5 panel call sites | Partly resolved | `kv_a8_context`, `_a8_packet` without `_StartTree`, `KV_INPUT_SOURCE["A8"]` and the A8 branch in `kv_export` are listed. The final-tree stem for `wave2.tg2` is still not stated (`_a7_final_tree` uses `V.WAVE`, `p426_panel.py:552`). I fold this into G7. |
| F6 per-language interval | Resolved | `loss_bound` at `PER_SESSION_ALPHA`, descriptive, no verdict. |
| F7 re-check binding | Partly resolved | The fields and ack rule are now right. The mechanism is wrong (see G5). |
| F8 worktree guard | Resolved | The axis table carries `m76-g2`, with a planted-leaf test. |
| F9 `kv_members` and Holm | Resolved | `kv_members(sessions=None, a8_sessions=None)`, and raw statistics unchanged with adjusted p recomputed (§6.1, §6.4). |
| F10 golden definition | Resolved | §7.1 and §7.2 define the projection, and absent A8 is omitted rather than "pending". |
| F11 renderer and flag sites | Resolved | §4.3 lists the decode loop, `kv_flags`, `session_interaction` and the `hold` flag. |
| F12 per-row final-tree rule | Resolved, with one residual | The rule is now per row and DNF-exempt. The residual is the orphan clause (see G4). |
| F13 polyglot checkout and prompt | Resolved | §1 and §6.2 name the pinned polyglot root as an input, with sha and blob checks and the pilot-export check. |
| F14 latency log | Partly resolved | It is now a named sealed file with its sha in `B8-A8.inputs`. The seal and the absent-file behaviour are undefined (see G7). |
| S1 plan binding | Resolved, with one residual | §3.6 adds the `check_tg2_p426`, `tg2_leg` and `frozen_record` checks. Residual: the draw input (see G6). The pilot chain shows `tg2_leg: "pilot"` and `frozen_record.sha256 == v8.sha256`, so the checks hold on the real record. |
| S2 reload key set | Resolved | §3.6, third item. |

## New findings

**G1. §3.7 — the eligibility test cannot tell a lock-file tamper from a real tamper. Major, confirmed.**
- **Problem:** The final tampered grade records no reasons. `write_receipt` writes an index-only report (`structured_grade.py:264-272`), and `grade_outcome` sets `reports={}`. So the cause must be inferred from events. Conditions (a)–(c) do not establish it, for three reasons:
  - Check (b) matches only `protected_manifest(prepared, solutions)`, which is prepared-only. Tamper also fires on new files with denied names (`jest.config.*`, `babel.config.*`, `.babelrc*`) and new non-helper files (`tg2_grade.py:785, 946-949, 986-988`). A model that writes `babel.config.js` after `npm install` passes (a), (b) and (c), because that path is not in the protected manifest.
  - (a) accepts any `npm install` form. `npm install <pkg>` edits the protected `package.json` without naming it.
  - (c) treats `npx jest` and `npm test` as read-only, but `jest -u` and package scripts write files.
- **Scenario:** A genuinely tampered javascript row, one that created a denied config file, is regraded to pass on a tree that omits that file. The JS point estimate and the HOLD move in an arm-dependent direction, because the regrade can only turn zeros into ones.
- **Change:** Require every path written or created in the events (write, edit and patch tools, plus a conservative parse of shell commands) to be either `package-lock.json` or `node_modules`, or accepted by the grader's own `_denied`/`_new_file_reason` rules, or a declared solution. Require bare `npm install`, `npm i` and `npm ci` with no package arguments. Reject `-u`/`--updateSnapshot` and `npm test` as read-only. Normalise event paths to work-relative before comparing. Where the events cannot prove it, the row stays tampered and is listed.

**G2. §3.7 / §1 / §7.5 — the regrade is not re-derivable by B8-A8 or signals, and a missing record fails silently. Major, confirmed.**
- **Problem:**
  - Eligibility needs the events on the evidence ref, and the regrade needs the grader image, the polyglot root and the final-tree objects. §1 names only two recorded inputs.
  - B8-A8 "binds every regrade record's sha" but never says how it learns which rows should have one. If an eligible row has no record, the row silently stays tampered and scores 0.
  - The `converged` handling is unstated for rows whose in-run gate may have been affected by tampered boundary grades.
  - §7.5 omits the regrade step from the sequence.
- **Scenario:** The designer's tool skips or mis-judges one javascript item. The sealed records are internally valid, B8-A8 binds what exists, and the verdict is computed over an incomplete regrade set.
- **Change:**
  - B8-A8 enumerates every final-tampered javascript row from the rows (name the row field, for example the last `grade_reports` outcome).
  - For each, it requires either a regrade record or a listed `stays tampered` reason, else the session is `incomplete`.
  - Specify an evidence-ref input to B8-A8 and re-verify (a)–(c) there, or state explicitly that only seal and sha are checked and name the command that re-verifies the facts.
  - Add the regrade step before B8-A8 in §7.5, and define a regrade outcome that is not a scored outcome (timeout, transport) as an abort, never a grade.

**G3. §3.7 / §6.2 — panel selection and "both-pass" do not say which `passed` applies. Minor, confirmed.**
- **Problem:** `_passed(att, rid)` reads the row's `passed` (`p426_panel.py:393`), while signals read the regraded value.
- **Scenario:** A regraded item scores 1 in the mechanical axis but is listed as "one-arm-pass" or "neither-pass" for the panel. The panel's item set then differs from the verdict's.
- **Change:** Define one effective-`passed` accessor, used by signals, B8-A8 counts, the panel selection and the packets.

**G4. §3.3 — the orphan-manifest clause may reject legitimate sessions. Minor, hypothesis.**
- **Problem:** "An orphan published manifest no row names" is a REASON, but DNF slots are exempt only in general terms. The chain has `rerun_index` / `slot_attempts` dispositions, and a discarded earlier run's evidence could also publish a manifest. I could not confirm whether the harvest includes runs the chain discarded. The A7 committed chains show none (all `p426_dnf` are empty and there is no `rerun_index` above 0), so the A7 golden is unaffected.
- **Scenario:** An A8 session with one rerun or one DNF item that left a manifest is rejected, although the row's own run id has exactly one match.
- **Change:** Scope the orphan check to manifests whose item has a row, or exempt run ids listed in the chain's `seen_run_ids` for DNF or rerun slots.

**G5. §5 — `check_recheck_doc` cannot be reused. Minor, confirmed.**
- **Problem:** It is an instance method of the sequencer class and uses `self.arms` and `self.recheck_attempts`/`self.selected` (`p426_wave2.py:1555-1565`). B8-A8 must re-implement the comparison. Extracting it would be a runner edit, which §8 puts out of scope. Also, recheck-s2 is sealed only after the reload leg. The spec does not say whether a missing recheck-s2 makes s2 incomplete or only the control incomplete.
- **Scenario:** An implementer imports the method or edits the sequencer, or an s2-accepted state with no reload yet is reported inconsistently.
- **Change:** State "re-implemented over the same fields", with a test against the sequencer's own sealed document shape. State that a missing recheck-s2 makes only the re-check label incomplete.

**G6. §3.6 — the pinned draw is an unnamed input. Minor, confirmed.**
- **Problem:** `check_tg2_p426(schedule, draw_doc, leg)` needs the draw document (`benchmark/m65/tg2_draw.json`, sha pinned in `schedules.py`). It is outside `results_root`, and it raises `TransportAbort`, not `RefusalError` or `ValueError`. `v8` carries `arms`, not a "pair" (§3.2).
- **Scenario:** B8-A8 reads an unhashed file, or the raised `TransportAbort` propagates as a crash rather than a session rejection.
- **Change:** Name the draw file as an input recorded with its sha. Catch `TransportAbort` and reject the session. Read `v8.arms == ["n16","x"]`.

**G7. §3.5 / §4 / §6.1 — plumbing the new record leaves unstated. Minor, confirmed.**
- **Problem:** The spec does not say that signals and the panel verify `B8-A8.base_b8_sha256 == sha(B8.json)` and re-hash B8-A8's `inputs`; `_kv_check_b8_inputs` does this only for `B8.json`. It gives no CLI or signature for passing B8-A8 to `compute_kv` or `kv_panel_section` (both take one record and one sha). It does not say how the exec-latency file is "sealed", or what happens when it is absent, as in the pilot-only build of §7.3. It does not state the final-tree namespace for `_a8_packet`.
- **Scenario:** A stale B8-A8 pairs with a regenerated `B8.json`. Or the pilot build refuses on the missing latency file, so §7.3 cannot pass.
- **Change:** State the base-sha and inputs verification explicitly. Define `latency` as `incomplete`, not a refusal, when the file is absent. Define the seal as a self-hash. State the `wave2.tg2` stem for final-tree reads.
