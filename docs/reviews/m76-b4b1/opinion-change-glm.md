## Findings

### F1 — `tg2_strict_rows` silently ignores stray rows (planned-slot boundary hole)
**Location:** `benchmark/bench/p426_wave2.py:405-438` (`tg2_strict_rows`).
**Severity:** major.
**Evidence:** confirmed. The loop iterates `for item in planned` and pulls `rows[item]`; a row whose `id` is not in `planned` is loaded into the `rows` dict but never examined. The duplicate check (`if r.get("id") in rows`) only catches a second occurrence of an already-seen id.
**Problem:** A stray row (an extra harvested row outside the frozen schedule) is silently accepted. The spec (§3 "Strict rows") and the delivery-1 test `test_strict_rows_refuses_a_stray_row` require a refusal. On the box, a stray row would mean extra evidence that the frozen schedule does not account for — exactly the kind of tampering/leakage the strict-rows gate exists to catch — yet the gate passes.
**Failure scenario:** A leg harvest accidentally publishes an extra `rust/extra.jsonl` row (e.g., from a prior attempt's leftover file, or a bug that double-writes). `tg2_strict_rows` reads it into `rows`, never checks it, and returns the planned 80 entries as if nothing happened. The re-check then runs over an incomplete/contaminated view.
**Proposed change:** After building `rows`, refuse if `set(rows) != set(planned)` (minus the dnf set): `raise fz.Refusal(f"{root.name}: {len(rows)} rows, {len(planned)} planned; stray: {set(rows)-set(planned)-dnf}")`.

---

### F2 — `t_coop` for tg2 double-counts the 2× factor in the grade join
**Location:** `benchmark/bench/chain_ops.py:1000-1005` (`t_coop`).
**Severity:** major.
**Evidence:** confirmed. `join = 660 if grader_timeout_s is None else 2 * max(table.values()) + 60`. For tg2 the caller passes `grader_timeout_s = corpus.grader_timeouts()`, whose values are already `2 × max_entries(timeout_s) + 300` (spec §1). So `join = 2 × (2×max+300) + 60 = 4×max + 660` instead of the intended `2×max + 60`. The implementer's own test (`test_m76_b4b1_impl_chain.py:218`) asserts `5 + (2*worst+60) + …` with `worst = max(timeouts.values()) = 660`, giving join = 1380 and t_coop = 2545; the delivery-1 test (`test_m76_b4b1_fe_grade.py:304`) expects join = 660 and t_coop = 1825.
**Problem:** The cooperative-cancel bound for tg2 is 720 s (12 min) too long. This is the time the chain waits before cancelling a stuck probe/grade. On the box, a genuinely stuck tg2 grade holds the leg (and the single router/worker) an extra 12 min per incident before the cancel fires — enough to push a leg past its supervision deadline (`leg_deadline_s`), turning a recoverable incident into an OVERRUN/INVALID. The spec says t_coop "takes the grader bound from the corpus identity"; the grade-join term and the per-language term are different quantities and the 2× must not be applied twice.
**Failure scenario:** A tg2 Rust item's grade hangs (docker daemon stall). The chain waits 2545 s instead of 1825 s before cancelling; with a tight `leg_deadline_s` (e.g. ~2 h for s1) two such incidents in one leg overrun it, producing OVERRUN_PAUSED instead of a clean INVALID/retry.
**Proposed change:** Pass the per-item timeout table (the raw `timeout_s` values) as `grader_timeout_s`, not the corpus identity's already-doubled bound; or compute the join from the corpus bound as `join = max(bound.values()) + 60 - 300` (i.e. recover `2×max_item+60` from `2×max_item+300`). Make the implementer test and the delivery-1 test agree on 1825.

---

### F3 — `--r1-off`/`--r1-on` not refused for `--corpus tg2` v8; `--positives` not required at parse time
**Location:** `benchmark/bench/p426_freeze.py:1119-1131` (argparse), `750-790` (`cmd_v8_tg2`).
**Severity:** major.
**Evidence:** confirmed. `parse_args` makes `--r1-off`/`--r1-on` optional for both corpora (deviation 6). `cmd_v8_tg2` checks `--positives` is present but never checks `--r1-off`/`--r1-on` are *absent*. Delivery-1 tests `test_freeze_v8_for_tg2_needs_positives_and_no_r1` and `test_freeze_v8_tg1_unchanged` both fail with "DID NOT RAISE Refusal".
**Problem:** (a) An operator who copies a tg1 v8 invocation and leaves `--r1-off/--r1-on` on the line with `--corpus tg2` gets a silently-accepted run: `cmd_v8` dispatches to `cmd_v8_tg2` which ignores `a.r1_off`/`a.r1_on`. The spec says tg2 v8 has "no R1"; stray R1 flags should be refused (fail-closed), not silently dropped. (b) `--positives` being required only inside `cmd_v8_tg2` (not at parse) means a direct `parse_args` caller (any future tooling) misses the gate.
**Failure scenario:** Operator runs `p426_freeze v8 --corpus tg2 --rehearsal-manifest M --r1-off R1off --r1-on R1on --r2 L2 --r3 L3 --positives P --out v.json`. The code accepts it, writes a tg2 v8 base, and the R1 leg roots are never read — the v8 base is created without verifying the pilot pair takes R1's role, exactly the precondition the spec removes R1 for.
**Proposed change:** In `parse_args` (or at the top of `cmd_v8_tg2`), refuse when `a.corpus == "tg2"` and (`a.r1_off` or `a.r1_on`); and refuse when `a.corpus == "tg2"` and not `a.positives`. Symmetrically, keep the tg1 `--r1-off`/`--r1-on` required check in `parse_args` (or at least in `cmd_v8` before dispatch) so a direct parse surfaces it.

---

### F4 — `validate_reports` tg2 rules are opt-in; the spec says "accepts the tg2 languages"
**Location:** `benchmark/bench/structured_grade.py:470-520` (`validate_reports`), called by `chain_ops.validate_leg:1284` and `m62/inject_verify.py:103`.
**Severity:** minor (box-side correct; spec-wording deviation).
**Evidence:** confirmed. `validate_reports` only applies the tg2 outcome set / artifact patterns when `grader="tg2"` is passed. Both tg2 call sites (`validate_leg` via `scaffold == TG2_SCAFFOLD`, and `inject_verify` via `scaffold == "opencode-v2-web-tg2"`) do pass it, so on-box evidence is validated correctly. The delivery-1 tests call `validate_reports(reports, lang, test_modified)` directly without `grader="tg2"` and fail (10 of the 26 delivery-1 failures). The spec §1 says "`validate_reports` accepts the tg2 languages with `tg2_grade`'s outcome set" — implying language-based selection, not an opt-in flag.
**Problem:** The deviation is documented (deviation 4, to protect the M64 four-language fake corpus). It does not break the box. But any future caller that validates a tg2 receipt without passing `grader="tg2"` (e.g., a harvest-side check, a review tool) will silently apply tg1's outcome set and accept `compile_failure`/`output_cap` receipts as invalid or miss the parsed-artifact pattern requirement.
**Failure scenario:** A future harvest-time validator calls `sg.validate_reports(reports, "rust", test_modified)` to cross-check a published receipt. It uses tg1's `REPORT_OUTCOMES`, finds `compile_failure` is "not permitted", and flags a valid tg2 receipt as corrupt — or, conversely, never checks for the `execute.stdout` parsed artifact and accepts a tampered receipt.
**Proposed change:** Either (a) auto-select tg2 rules when `lang in TG2_LANGS` and add an opt-out (`grader="tg1"`) for the M64 fake corpus, or (b) keep opt-in but make `TG2_LANGS`-without-`grader="tg2"` a refusal (not silent tg1), so a missed flag fails loud rather than misvalidating.

---

### F5 — Slot_base uses `oc` (ArmBinding.arm) instead of the KV arm (`n16`/`x`)
**Location:** `benchmark/bench/chain_core.py:1301` (`slot_base=f"{self.config.config_id}|{self.arm.arm}|…"`), `benchmark/bench/tests/test_m76_b4b1_fe_chain.py:370`.
**Severity:** minor.
**Evidence:** confirmed. Delivery-1 `test_plan_of_a_frozen_tg2_schedule[pilot/s2]` fails: expected `tg2-p426|n16|…`, got `tg2-p426|oc|…`. The tg2 `ArmBinding(arm="oc", …)` is hardcoded `oc` in `run_tg2_chain.tg2_config`; the kv-arm (`n16`/`x`) lives only in the leg name (`tg2-m76-<arm>-<leg>`).
**Problem:** The ledger slot key and the leg name use different arm identifiers. The spec (§2) names legs `tg2-m76-<arm>-<leg>` with the KV arm, and says "slot prefix `tg2-p426`" without specifying the arm field. For tg1 the slot uses `oc` consistently and the leg name uses `off`/`on` — a similar mismatch, so this is not a regression. But for tg2 the pair gate (`kv_pair_problems`) identifies arms by `--kv-bits`/`--tq4-attention` in the worker argv, not by the slot's arm field, so the slot's `oc` doesn't break the gate. The mismatch is a labeling inconsistency that makes the harvested ledger harder to audit (the slot says `oc`, the leg dir says `n16`).
**Failure scenario:** An auditor reading `chain.json`'s `p426_ledger` sees `tg2-p426|oc|…|s1|rust` and must cross-reference the leg root name to learn which KV arm ran it. Not wrong evidence, but unverifiable-by-inspection.
**Proposed change:** Use `self.a.kv_arm` (or the leg's KV label) in the tg2 slot_base arm field, so the slot and the leg name agree. (If tg1's `oc` is pinned by a golden, keep tg1 as-is and only change the tg2 path.)

---

### F6 — Probe `--print-identity` does not surface `universe_sha256` / `draw_sha256`
**Location:** `benchmark/bench/arm_runner.py:960-998` (`print_identity`).
**Severity:** minor.
**Evidence:** confirmed. `out` contains `arm, config_id, scaffold, scaffold_policy_sha256, probe_code_sha256, toolchain, opencode_version, opencode_exe_sha256, polyglot_sha, snapshot_*, generation_identity_sha256` — no `universe_sha256`, no `draw_sha256`, no `corpus_identity`. Delivery-1 `test_probe_without_universe_defaults_to_the_tg2_universe` and `test_probe_identity_with_an_inject_kind` fail: the pinned universe sha `ff76573…` and the inject-addendum sha are not in the JSON. (The universe sha *is* present inside `ident["policy"]`, but `out` only pulls `toolchain` from it.)
**Problem:** The spec §1 says the corpus identity carries "universe and draw sha256" and the acceptance criteria test "a probe without `--universe`". The probe identity is the artifact the operator/chain uses to confirm which universe was loaded; without the universe sha visible, `--print-identity` alone cannot prove the probe defaulted to the tg2 universe. The chain still pins `universe_sha256` via the manifest's `runtime.policy.universe_sha256`, so on-box evidence is verifiable — but the `--print-identity` contract is incomplete. (tg1 has the same gap, so this is not a regression.)
**Failure scenario:** An operator runs `run_tg2_probe.py --print-identity` to confirm the box is wired to the committed universe before a leg. The output shows no universe sha; they cannot confirm from this output alone and must run a separate check.
**Proposed change:** Add `universe_sha256=universe_sha` (and `draw_sha256` for tg2) to `out` in `print_identity`, or include the `corpus_identity` dict.

---

### F7 — `--rehearsal` parser refuses a valid r2 invocation when `--kv-arm` defaults to `n16`
**Location:** `benchmark/chains/c147/run_tg2_chain.py:150-152`.
**Severity:** minor.
**Evidence:** confirmed. Delivery-1 `test_rehearsal_mapping[r2]`, `test_record_kinds[argv4-p426_rehearsal]`, `test_r2_invalidates_the_first_rust_item`, `test_r2_does_not_fire_on_a_non_rust_first_item` all fail with `REFUSED: --rehearsal r2 runs on x, not n16`. The test helper `_argv` defaults `--kv-arm n16`; r2 is on `x`.
**Problem:** The parser validates `a.kv_arm == REHEARSALS[a.rehearsal]["arm"]` at parse time. This is a reasonable fail-closed check, but it couples the rehearsal choice to the arm flag in a way the spec does not require: the spec (§2) says `--rehearsal r2|r3` is exclusive with `--leg` and the table fixes r2→x, r3→n16. The parser could derive the arm from the rehearsal instead of requiring the operator to pass the matching `--kv-arm`. On-box the operator passes the right arm, so this doesn't block; but it means `--rehearsal r2 --kv-arm n16` refuses where it could simply override `kv_arm` to `x`.
**Failure scenario:** Operator runs `run_tg2_chain.py --rehearsal r2 --kv-arm n16 …` (copying the n16 default from a non-rehearsal leg). Refused. They must know to pass `--kv-arm x` for r2. Not a box blocker; a usability/foot-gun issue.
**Proposed change:** When `--rehearsal` is given, set `a.kv_arm = REHEARSALS[a.rehearsal]["arm"]` and ignore a conflicting `--kv-arm` (or refuse only when the operator *explicitly* passes a conflicting arm, not when they pass the default).

---

### F8 — `--tg2-inject` dest is `tg1_inject` (naming deviation)
**Location:** `benchmark/run_tg2_probe.py:72` (`ap.add_argument("--tg2-inject", dest="tg1_inject", …)`).
**Severity:** minor.
**Evidence:** confirmed. Delivery-1 `test_probe_parser_scaffold_and_languages` fails: `assert ns.tg2_inject == "alloc"` → `AttributeError: no attribute 'tg2_inject'`. The shared core reads `a.tg1_inject` (deviation 7).
**Problem:** Pure naming mismatch. On-box the core reads `getattr(a, "tg1_inject", None)` so the value reaches the runner correctly. But the namespace attribute name is a leak of the tg1 implementation detail into the tg2 CLI surface; any tooling that introspects `Namespace.tg2_inject` breaks.
**Failure scenario:** A future probe wrapper reads `ns.tg2_inject` to log the inject kind before delegating to the core. `AttributeError`.
**Proposed change:** Add `tg2_inject` as an alias (or rename the dest to `inject_kind` and update the core's `getattr`), so both `ns.tg1_inject` (tg1) and `ns.tg2_inject` (tg2) work.

---

### F9 — Re-check 2 position: after reload, not after s2 (spec text vs. order line)
**Location:** `benchmark/bench/p426_wave2.py:1043-1044` (`after_leg`).
**Severity:** minor.
**Evidence:** confirmed. `if spec["role"] == "second" and spec["kind"] in ("s1", "reload"): self.ensure_recheck("s1" if spec["kind"] == "s1" else "s2")` — re-check 2 fires after the reload pair's second leg. Spec §3 text: "After s2: the same over s1 + s2 → run/recheck-s2.json"; spec §3 order line: "s1 → re-check 1 → s2 → reload → re-check 2". Deviation 10 acknowledges the contradiction and picks the order line.
**Problem:** The two spec statements disagree. The implementer chose the order line (after reload). Since re-check 2 pools `s1+s2` rows (not reload rows), the verdict is identical either way; only the timing differs (later, after reload). If the operator expects the verdict after s2 (per the text) to decide whether to proceed to reload, they instead get it after reload — reload has already run by the time an "outside" re-check 2 could stop. But re-check 2 "never stops" (B4b-2 labels it), so no stop is expected anyway.
**Failure**Failure scenario:** An outside re-check 2 verdict is computed later than the spec text suggests; if B4b-2's panel expects the recheck-s2.json timestamp to fall between s2 and reload, it will be wrong.
**Proposed change:** Resolve the spec contradiction explicitly (ask the designer); if "after s2" is intended, move the `ensure_recheck("s2")` call to the s2 second-leg branch; if "after reload" is intended, update the spec text.

---

### F10 — `run_tg2_chain` rehearsal path does not set `a.kv_arm` before the arm-match check when `--kv-arm` is omitted
**Location:** `benchmark/chains/c147/run_tg2_chain.py:148-155`.
**Severity:** minor (same root as F7, listed separately because the test-writer's `_argv` default is the realistic operator default).
**Evidence:** confirmed. `a = ap.parse_args(argv)` runs before the rehearsal block; `--kv-arm` is `required=True`, so the parser itself enforces a value — the test passes `n16` via `_argv`. The rehearsal block then refuses on mismatch.
**Problem:** Functionally subsumed by F7. Noting it as a separate seam because the delivery-1 failures split across both the parser and the hook tests.
**Proposed change:** Same as F7.

---

## What both test sets miss (box-side positives seams)

The implementer's report flags these explicitly; the delivery-1 report confirms none are tested. They are the untested box-side positives seams, and they are where a real run would most likely produce wrong/unverifiable evidence:

- **`BoxSeqOps.positives_session`** (`p426_wave2.py:1330-1349`): starts a real lean router on N16's worktree, runs the A4 gate under the tg2 scaffold, loads the worker. Never exercised on a box. If the lean-router startup or A4-gate path has a tg2-specific bug (e.g., the `--scaffold opencode-v2-web-tg2` argument to `session_pinning_gate.py` not being plumbed through `scripts/session_pinning_gate.py`), the positives record would fail to start or fail the A4 gate, blocking v8.
- **`BoxSeqOps.positive_inject`** (`p426_wave2.py:1376-1395`): spawns `run_tg2_probe.py --tg2-inject` with `--a4-v2-receipt` pointing at the positives-session receipt. The argv construction is hand-rolled and not tested against the real probe parser; a missing/extra flag (e.g., `--expect-items` vs the probe's expectation) would make every inject verdict `FAIL` and refuse v8.
- **`BoxSeqOps.inject_verify`** (`p426_wave2.py:1399-1405`): shells out to `m62/inject_verify.py --scaffold opencode-v2-web-tg2`. The `inject_verify.py` tg2 path (`check_files` with `grader="tg2"`) is tested via delivery-1 only on recorded fixtures, never on a real inject run's row. A mismatch between the row's `grade_reports` shape (written by `arm_runner` for a tg2 grade) and `validate_reports(..., grader="tg2")` would refuse every inject.
- **The re-check stop/resume (rc 5, `--recheck-ack`)**: the test-writer report states sequencer behaviour is not tested. `ensure_recheck` (`p426_wave2.py:1067-1106`) seals `recheck-A8.json`, records `rechecks.<gate>` in `sequence.json`, and stops with rc 5. None of this is exercised end-to-end. A bug in the seal/record/ack path would either never stop (running an outside re-check silently) or never resume.
- **The freeze round-trip (positives → rehearsals → v8 → pilot → gate → amendment → s1)**: not tested end-to-end; only the individual `p426_freeze` parse-time checks and `write_amendment_tg2`'s pilot-gate call are tested. A bug in `cmd_v8_tg2`'s ordering of checks (e.g., `positives_problems` before `tg2_rehearsal_problems`, or the `run_checks` call's `corpus="tg2"` argument) would only surface on a real freeze.
- **`row_scores.py:43`** (implementer report, "not in scope"): still matches only the tg1 label prefix. If this file feeds B8/signals/panel for tg2, tg2 rows would be silently dropped. Out of scope per the implementer, but a real consumer risk.

## Summary

The candidate's tg2 path is largely faithful to the spec and the tg1 mirror. The box-blocking issues are **F1** (stray rows silently accepted by the strict-rows gate — a direct fail-closed violation), **F2** (t_coop double-counts the 2× factor — 12 min extra cancel latency per stuck grade, enough to overrun legs), and **F3** (tg2 v8 doesn't refuse stray `--r1-off`/`--r1-on` — fail-open where the spec says fail-closed). F4–F10 are real but minor (labeling/naming/parse-time-vs-cmd-time validation gaps that don't break the box but break the delivery-1 tests and future callers). The largest untested risk is the box-side positives seam (F-seam group above), which neither test set exercises and which is the most likely place for a real run to produce wrong evidence.
