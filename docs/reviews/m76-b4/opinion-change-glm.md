Based on my read of the candidate (`run_tg2_chain.py`, the `run_tg1_chain.py` hooks, `p426_wave2.py`, `p426_signals.py`, `p426_harvest.py`), the spec v1.1, the B7 rule, and both test suites, here are my findings.

---

## Findings

### F1 — A8 refuses on any transport DNF; the spec says "DNF included" and tg1's A7 scores a DNF as a strict fail
- **Location:** `benchmark/bench/p426_signals.py:1982-1983` (`a8_decider_inputs`); `run_tg2_chain.py:213-216` (`item_record` DNF branch).
- **Severity:** major.
- **Evidence:** confirmed. `a8_decider_inputs` raises `RefusalError` when `r.get("passed") is None or r.get("dnf_class") is not None`. `item_record` sets `passed=None` for a DNF. So a single transport DNF in s1/s2 of either arm aborts the whole A8 verdict.
- **Problem:** P426 tolerates up to `MAX_DNF = 2` DNFs per leg as `VALID_WITH_DNF` (`p426_wave2.py:49`), and the certification spec §8 says the mechanical-axis statistic is "DNF included" — tg1's A7 implements that as `_strict(None) == 0` (`p426_signals.py:105-106`, "a DNF slot is a strict fail", line 1769). The candidate instead refuses the verdict on the first DNF. A tg2 decider leg that is `VALID_WITH_DNF` (the discipline's accepted state) cannot produce an A8 verdict. The request's parenthetical "(a DNF never scored as a pass or a fail)" matches the candidate, but conflicts with the spec and with A7.
- **Failure scenario:** On the real arms, one of the 80 decider items transport-DNFs (the P426 discipline accepts this). `a8_decider_verdict` raises `RefusalError`; stage 3 has no A8 verdict and the operator gets a refusal instead of the pre-registered "DNF included" statistic.
- **Proposed change:** Decide one rule. Either (a) score a DNF as 0 in `a8_decider_inputs` (match A7 and §8 "DNF included"), or (b) keep refusal but then amend the spec's §8 A8 line and the `MAX_DNF` interaction so a `VALID_WITH_DNF` decider leg is not a verdict-blocking state. I recommend (a); push-back on the request's parenthetical.

### F2 — `a8_decider_verdict` requires both arms to cover identical item/session sets; a `VALID_WITH_DNF` arm with a DNF is refused before the set-equality check can even matter
- **Location:** `p426_signals.py:1996-2000`.
- **Severity:** minor (subsumed by F1 if F1 is resolved as "score DNF as 0"; standalone if not).
- **Evidence:** confirmed. The set-equality guard `a.keys() != b.keys() or any(a[i].keys() != b[i].keys() ...)` runs after `a8_decider_inputs`, which already refused on any DNF.
- **Problem:** If F1 is kept as-refusal, the "same items/sessions" guard is partly dead code for the DNF case. If F1 is changed to score DNF as 0, the guard still usefully catches arms whose legs ran different items.
- **Proposed change:** resolve via F1; keep the set-equality guard regardless.

### F3 — `item_record.acc` is `0` for a DNF while `passed` is `None`
- **Location:** `run_tg2_chain.py:216, 226`.
- **Severity:** minor.
- **Evidence:** confirmed. `rec["acc"] = 1 if rec["passed"] else 0` — `None` is falsy, so a DNF records `acc=0` while `passed=None`. A consumer reading `acc` sees "fail"; one reading `passed` sees "DNF".
- **Problem:** Inconsistent signal for the same item. The B6-style signals and the panel read these records; a DNF should read consistently across fields.
- **Failure scenario:** A downstream consumer sums `acc` and silently scores the DNF as a fail, contradicting the `passed=None` contract.
- **Proposed change:** `rec["acc"] = None` when `dnf is not None` (mirror `passed`).

### F4 — The tg2 amendment is never written by the sequencer; `ensure_amendment` raises `Stop` for tg2 even after a PASS smoke pair, with no path forward except an operator hand-write
- **Location:** `p426_wave2.py:893-895` (the `if self.corpus == "tg2": raise Stop(...)` branch).
- **Severity:** major (it is the intended placeholder, but it is the interface B4b must change, and the candidate fixes the shape of that interface here without a spec basis).
- **Evidence:** confirmed. After the smoke pair passes, `ensure_amendment` refuses to write `amendment.json` for tg2 and stops. `tg2_deadline_s` then requires `w_rust_s / w_javascript_s / w_java_s / w_cpp_s` from the amendment. tg1's `fz.write_amendment` writes only `w_python_s / w_go_s` and `leg_deadline_s` (`p426_freeze.py:832`), so it cannot produce a tg2 amendment.
- **Problem:** The candidate hard-codes that the operator/designer writes the tg2 amendment by hand from the smoke. The spec v1.1 says nothing about who writes the tg2 amendment or its wall derivation; the spec's "Interfaces" only names `--corpus`, `--tier`, the leg names and the results path. This is the largest unbuilt surface B4b plugs into, and B4 has fixed its shape (a hand-written `p426_timeout_amendment` with four `w_<lang>_s` keys and the smoke dossier sha) without a spec to anchor it. `verify_amendment` does not check the walls are present, so an amendment with a valid dossier link but no walls passes verification and only fails later at `tg2_deadline_s`.
- **Failure scenario:** B4b lands a smoke-driven wall writer; the candidate's `raise Stop` and the `verify_amendment` that ignores walls both have to be rewritten, and any operator who hand-wrote an amendment against the candidate's shape finds it silently re-verified with wrong walls.
- **Proposed change:** Add a spec note (or a B4b prerequisite) naming the tg2 amendment's writer and its wall keys; have `verify_amendment` assert the four `w_<lang>_s` keys are present and numeric for tg2, so a malformed amendment fails at verify, not at the first screen launch.

### F5 — `BoxSeqOps.tg2_positives` reaches into `opencode_v2_core._polyglot_root()` (a private `_`-prefixed function) for the corpus root
- **Location:** `p426_wave2.py:1101`.
- **Severity:** major.
- **Evidence:** confirmed. `root = oc._polyglot_root(); results = t2.run_positives(doc, sha, universe=universe, corpus_root=root, scratch=self.positives_scratch)`.
- **Problem:** The positives' corpus root is an assumption with no spec basis. `run_tg2_chain.run_positives` passes `corpus_root` to `tg2_materialize.prepare_tree(corpus_root, lang, slug, base)` and `mat.read_plan` / `mat.apply_reference`. If B4b's tg2 corpus is not the opencode polyglot root (it is a separate M65 corpus built in B4b per C342), every positive is materialized from the wrong tree and the C169 verdict is meaningless. Calling a `_`-prefixed function also couples the sequencer to a private implementation detail.
- **Failure scenario:** B4b ships a tg2 corpus at a different path; the candidate's positives grade against the opencode polyglot tree, the stub/reference verdict passes vacuously or fails, and the gate blocks or, worse, passes a broken grader.
- **Proposed change:** Take the corpus root from a B4b seam (e.g. an ops method or a `--corpus-root` flag), not from `oc._polyglot_root()`. Until B4b lands, refuse the positives with a named "no tg2 corpus" message rather than guessing.

### F6 — Two copies of the C169 positives verdict exist (`tg2_positives_problems` in `p426_wave2.py` and `positives_problems` in `run_tg2_chain.py`)
- **Location:** `p426_wave2.py:191-224`; `run_tg2_chain.py:249-262`.
- **Severity:** minor.
- **Evidence:** confirmed. Both implement the same verdict (one stub FAIL + one reference PASS per language, no duplicates, parsed report). `ensure_tg2_positives` calls the wave2 copy; `run_positives`'s tests call the chain copy. They can drift.
- **Problem:** A future change to one copy (e.g. accepting a tampered stub as a valid FAIL) won't propagate; the gate and the runner disagree silently.
- **Proposed change:** Keep one verdict (in `run_tg2_chain.py`, the pure module) and have `p426_wave2.py` import it.

### F7 — `record_problems` accepts a `tg2_tiers` *list* containing the leg's tier; the spec says the record names "the tier" (singular)
- **Location:** `run_tg2_chain.py:159-167`; used at `run_tg1_chain.py:341`.
- **Severity:** minor.
- **Evidence:** confirmed. `if not isinstance(tiers, list) or tier not in tiers` — a record with `tg2_tiers=["screen","decider"]` passes for any tg2 leg. The spec's Interfaces says "the frozen record names the draw sha256 and the tier."
- **Problem:** A single record can cover both a screen and a decider leg, so the record no longer pins which tier this leg belongs to. The draw sha is still pinned, so this is a relaxation, not a hole, but it is wider than the spec.
- **Failure scenario:** A screen leg runs under a record the operator intended for the decider only; the tier assertion the spec promised is absent.
- **Proposed change:** Either pin `tier == tiers` (a single string), or amend the spec to say the record names a list of tiers it covers.

### F8 — `ensure_tg2_positives` runs before `wait_boundary` / `check_power`; it launches docker grading outside the leg's supervision and idle discipline
- **Location:** `p426_wave2.py:1001-1003` (the call site is at the top of the loop, before `process` → `run_leg` → `wait_boundary`).
- **Severity:** minor.
- **Evidence:** confirmed. `for spec in self.legs(): if spec.get("corpus") == "tg2" and spec["kind"] != "pilot": self.ensure_tg2_positives(); self.process(spec)`. `ensure_tg2_positives` calls `ops.tg2_positives()` which runs `run_positives` (docker `grade_item` per language) with no power check, no idle gap, no deadline.
- **Problem:** The positives are a real docker grading run on the box. The P426 discipline checks power and the idle gap before every launch; the positives bypass that. On a battery/idle boundary this could start grading against the contract.
- **Proposed change:** Move the positives call inside `run_leg`'s pre-launch discipline (after `check_power` / `wait_boundary`), or give `ensure_tg2_positives` its own power/idle guard.

### F9 — The harvest's handling of real tg2 grader output is untested and the implementer flags it as an open question (Q4)
- **Location:** `p426_harvest.py` `classify` / the wave2 harvest path; `BoxSeqOps.harvest` at `p426_wave2.py:1162-1170`.
- **Severity:** major (hypothesis — needs real output to confirm; the candidate cannot run yet, so this is not reproducible today, but it is the most likely place stage 3b fails first).
- **Evidence:** hypothesis. The harvest's `classify` and `LEG_MAIN` / `ROW_REFS` tables are tg1-shaped (`p426_harvest.py:228-232`). `run_tg2_chain.grade_outcome` produces a `GradeOutcome` with `phases=(..., outcome="parsed"|"tampered"|...)` and `reports=dict(result.artifacts)`. Whether the harvest accepts the tg2 grade-receipt files (`seq-NNNN/phases.json`, image-id artifacts, the `final_tree` layout for polyglot trees) is unverified. The implementer's Q4 says the same.
- **Problem:** A tg2 leg that runs VALID on the box can still fail at harvest because the harvest's classifier does not recognize tg2-specific artifacts, which would stop the sequence with rc 4 and no pair dossier.
- **Failure scenario:** First real tg2 screen leg completes; `ops.harvest` returns non-zero; `Sequencer.harvest` raises `Stop(4)`; the leg is never recorded as harvested; the pair gate never runs.
- **Proposed change:** Before stage 3b, run one tg2 leg's output through `bench.p426_harvest` on a copy and extend `classify` / `LEG_MAIN` for tg2 artifacts. Add a red test with a synthetic tg2 leg root.

### F10 — The tests do not exercise the sequencer's smoke → amendment-Stop → resume → positives → screen flow end-to-end
- **Location:** `test_m76_b4_impl_tg2.py` (the `ensure_tg2_positives` tests use a hand-built `Sequencer` with `__new__`, bypassing `run`); `test_m76_b4_fe_plan.py` notes "Not covered: the wiring of the sequencer's screen-to-decider flow."
- **Severity:** minor (test gap; the behavior is fail-closed, so a bug here stops rather than silently passes).
- **Evidence:** confirmed. `test_sequencer_positives_gate` calls `ensure_tg2_positives` directly. No test drives `Sequencer.run` with fake ops through the smoke pair, the amendment Stop, the resume, the positives gate and the first screen launch.
- **Problem:** The ordering invariants the request asks about (smoke → positives → screen → decider; safe stop where data are missing) are asserted only from the leg table, not from a run.
- **Proposed change:** Add a fake-ops `Sequencer.run` test that drives the tg2 table through the amendment Stop and a resume, asserting the positives run exactly once and only after the amendment verifies.

### F11 — `--corpus tg2` is refused under `mtp`, but the chain's `parse_args` allows `--corpus tg2` without `--p426` reaching `check_tg2` only via the `a.corpus == "tg2"` branch; the gate is correct but the error path is split
- **Location:** `run_tg1_chain.py:460-476` (`check_tg2`); `p426_wave2.py:1281-1283` (sequencer-side refusal).
- **Severity:** minor (no hole; a clarity/diagnostic note).
- **Evidence:** confirmed. The chain refuses `--corpus tg2` without `--p426 --lever kv` inside `check_tg2`; the sequencer refuses `--corpus tg2` without `run --lever kv`. Both gates close the path. The request's assumption "tg2 runs only under `--lever kv`" holds.
- **Problem:** None material; the two gates emit different messages for the same condition.
- **Proposed change:** none needed; optionally unify the message.

---

## Scope requests (beyond the request, no severity)

- **S1:** The request's assumption "tg2 runs only under `--lever kv`" is enforced (F11). The assumption "language order rust, javascript, java, cpp; s2 reversed; reload = first 5 of s1's first language at 1001" is implemented and tested (`run_tg2_chain.LANGS`, `leg_langs`, `leg_items`; `test_m76_b4_impl_tg2.py::test_tier_prefixes_and_language_order`, `test_reload_items_are_s1_first_language_first_five_at_seed_1001`). The assumption "s2 reversed" matches tg1's P426 s2 language reversal. No finding.
- **S2:** The first-arm alternation (screen ref, s1 test, s2 ref, reload test) is the implementer's own call (Q3); the spec does not fix it. I would suggest the spec state it, since the pair-gate order can matter for drift detection. This is a spec amendment request, not a code defect.

## What the candidate does beyond the specification

- `a8_decider_inputs` / `a8_decider_verdict` in `p426_signals.py` — the spec names no function; the candidate added the seam. Reasonable, but the DNF-as-refusal choice (F1) is beyond the spec.
- `tg2_positives_problems` in `p426_wave2.py` (F6) — a second copy of the chain's verdict.
- `ensure_amendment`'s tg2 `raise Stop` branch (F4) — a placeholder shape for B4b with no spec basis.
- `BoxSeqOps.tg2_positives`'s `oc._polyglot_root()` corpus-root guess (F5).
- `needs_docker = lambda lang: True` for tg2 — matches "Docker graders" in the spec; not beyond.

## Summary

The tg1 surface is byte-identical (golden tests pass; the `corpus`/`tier` keys are the only namespace additions). The draw integrity, tier-prefix nesting, s2 reversal, reload, leg names, paths, and the `--corpus tg2` refusal under `mtp` are all correct. The two material risks for stage 3b are **F1** (A8 refuseson the first transport DNF, contradicting the spec's "DNF included" and tg1's A7) and **F5** (the positives' corpus root is guessed from a private opencode helper). **F4** (the hand-written tg2 amendment) and **F9** (untested harvest of real tg2 output) are the interfaces B4b most likely has to change because B4 fixed them without a spec basis. The rest are minor or test gaps.
