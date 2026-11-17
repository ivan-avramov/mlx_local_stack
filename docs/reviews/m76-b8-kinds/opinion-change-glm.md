Findings below. I could not execute B8 on the real harvested tree — the snapshot is not a git repo (`_kv_frozen` → `resolve_commit` needs the harvest commits in the object store), so the real-data run is traced in source, not reproduced. The synthetic-tree tests use the real `ids.json` but synthetic legs.

---

**F1 — major, confirmed** — `benchmark/bench/tests/test_m76_b3_impl_wave1.py:145` (existing baseline test, not in the candidate patch) regresses.

- Location: `test_m76_b3_impl_wave1.py:151-153` (second half of `test_main_kv_refuses_v_before_anything_runs`), driven by `p426_wave1.py:301-302` (new default) + `p426_wave1.py:263-281` (`preflight_kv`) + `p426_wave1.py:329` (`claim_out`) + `p426_wave1.py:379` (`label_problems_kv`).
- Evidence: confirmed by tracing. On the baseline the kv default `--axes` was `KV_AXES` = `AXES + ("longctx",)` = all six kinds incl. `m1` (`p426_wave1.py:198`, old line 417). For pair `n16,x`, `preflight_kv` saw an `m1` leg for arm `x` (not the reference) with no `--certified-by x=…` and refused with `"the x m1 leg needs its stage-2 record (--certified-by …)"` → rc 2, `out` never created. The candidate moves the kv default to `kv_w1_kinds(build)` = the five planned kinds (no `m1`), so `preflight_kv` no longer refuses; the sequencer proceeds, `claim_out(out, …)` creates `out` (writes `.build`), then `label_problems_kv` refuses at the frozen-record check with rc 1. The test asserts `rc == 2`, `"stage-2 record" in stderr`, and `not out.exists()` — all three now fail.
- Problem: acceptance 3 ("the stack suite passes or fails only as on the baseline") is violated. The implementer report flags this exactly (`IMPLEMENTER-REPORT.md` deviation 1) but did not edit the test (test dir is read-only for the implementer).
- Failure scenario: run `pytest benchmark/bench/tests/test_m76_b3_impl_wave1.py::test_main_kv_refuses_v_before_anything_runs` on the candidate — the `n16,x` half fails (rc 1, no "stage-2 record", `out` exists).
- Proposed change: the test's *intent* is the m1 certified-by refusal, not the default axes — pass `--axes m1` (or `--axes m1,cjudge`) on line 152 so the refusal is still exercised. Either the designer amends the spec scope to include this test, or the candidate/test-writer adds that flag. This is the only baseline parity break found.

---

**F2 — minor, confirmed** — the signals consumer `compute_kv` does not read the new `wave1.dropped` field, and reports the dropped M1 as `missing`.

- Location: `benchmark/bench/p426_signals.py:1622-1693` (`compute_kv`); M1 section at `p426_signals.py:1685-1692`; `dropped` is never referenced anywhere in `p426_signals.py` (grep: 0 hits).
- Evidence: confirmed. `recs = {(p["kind"], p["block"]): p for p in w1.get("pairs") or []}`; for the dropped `m1` there are no pairs, so `recs.get(("m1", label))` is `None` and `m1[label]["status"] = "missing"`. Meanwhile `coverage["not_run"]` does include `"m1/b1","m1/b2"` (`p426_signals.py:1637`). So the same signals record says M1 is `missing` (axis) and `not_run` (coverage), and the C352 ruling in `dropped` is discarded.
- Problem: the question asks whether `compute_kv` reads the new record correctly — for `dropped` it does not; for the M1 section it reports `missing` for a deliberately *dropped* kind. M1 is `role: "memory (descriptive)"` and non-blocking, so no flag is affected, but the descriptive report is wrong and internally inconsistent.
- Failure scenario: run `compute_kv` on the candidate's B8 over the real harvested s3 — `SIGNALS.json` `axes.M1.blocks.{b1,b2}.status == "missing"` while `coverage.not_run` lists `m1/b1,m1/b2`.
- Proposed change (scope request — `p426_signals.py` is listed read-only in the spec): have `compute_kv` read `w1.get("dropped")` and emit `status="not_run"` (with the ruling) for a dropped kind's blocks, distinguishing dropped from genuinely missing. If the spec intends the consumer unchanged, document that `dropped` is record-only and M1 `missing` is the accepted descriptive label.

---

**F3 — minor, confirmed** — acceptance 2 ("the signals run on it") is not tested by either test file.

- Location: `test_m76_b8_kinds_impl_planned.py` (whole file) and `test_m76_b8_kinds_fe_wave1.py` (whole file) — neither imports `p426_signals` nor calls `compute_kv`.
- Evidence: confirmed by grep (no `compute_kv` / `p426_signals` reference in either file).
- Problem: the consumer path (F2) is unexercised; a regression in `compute_kv`'s handling of the new record would not be caught.
- Proposed change: add a test that builds the B8 record (default kinds) and runs `compute_kv` on it, asserting the signals run and asserting M1's status (per F2).

---

**F4 — minor, confirmed** — the `dropped`/`not_run` behavior is tied to `kinds=None`; an explicit `kinds=PLANNED` yields `dropped={}` and no `m1/*` in `not_run`, and no test locks that difference.

- Location: `p426_verify.py:1908-1910` (dropped populated only when `kinds is None`) and `p426_verify.py:1964-1966` (dropped loop); test `test_m76_b8_kinds_fe_wave1.py:267-269` (`test_kinds_none_equals_default_equals_planned`) compares only `by_key(...).keys()` between default and explicit `PLANNED`, not full dumps.
- Evidence: confirmed. `verify_wave1_kv` sets `dropped = {}` unless `kinds is None`; the trailing `for kind in KV_W1_KINDS: if kind in dropped and kind not in kinds` is a no-op when `dropped == {}`. So `all_kv()` and `all_kv(kinds=PLANNED)` differ in `not_run` and `dropped`, but the FE test only asserts the pair keys match.
- Problem: the intended semantics of "explicit kinds equal to the plan" vs "default kinds" is under-specified (implementer deviation 2) and un-locked. A future change that populates `dropped` for explicit-equal-to-plan kinds would pass all current tests.
- Failure scenario: a maintainer makes `all_kv(kinds=PLANNED)` also emit `dropped.m1` for consistency; no test fails, but consumers reading `dropped` change behavior.
- Proposed change: assert the intended relation explicitly — either `all_kv()["axes"]["wave1"]["dropped"] == all_kv(kinds=PLANNED)["axes"]["wave1"]["dropped"]` (if equality is intended) or the opposite (if the current divergence is intended), so the choice is locked.

---

**F5 — confirmation (no defect), hypothesis** — on the real harvested stage-3a Wave 1 the candidate accepts/refuses correctly.

- Location: `benchmark/results/m76/wave1/` (real harvest) — all five planned kinds × {b1,b2} × {n16,x}; no `m1-m76-*-b1/b2` (only `m1-m76-n16-smoke`); `ids.json` has no `m1` axis (`benchmark/results/m76/ids.json`).
- Evidence: traced in source (could not execute — no git repo). With default kinds, `verify_wave1_kv` iterates the five planned kinds × {b1,b2}; `if kind in KV_ITEM_KINDS and label not in ids[kind]` skips `m1` (not in `KV_ITEM_KINDS`); the dropped loop appends `m1/b1,m1/b2` to `not_run` and sets `dropped.m1`. Smoke legs (incl. `m1-m76-n16-smoke`) are never accessed — only `b1`/`b2`/`t2-*` labels are iterated, so the `smoke` deny-pattern in `KV_DENY_PATTERNS` is not triggered. A missing planned leg still refuses via `_kv_member` (`p426_verify.py:1414-1421`). No planned kind is silently skipped: every kind in `kinds` is iterated, and each label either not_runs (tier-2 absent), refuses (tier-2 present / no ids / missing leg), or verdicts.
- Conclusion: no wrong acceptance, no wrong refusal, no silent skip of a planned kind from the candidate logic. (Confirmed at the source level; the real-data execution is hypothesis pending a git checkout with the harvest commits.)

---

**mtp lever** — unchanged, confirmed. `verify_all` (the mtp path) is untouched; `p426_wave1.py:419-420` keeps the mtp default at `AXES`; `KV_AXES` is still used for `schedule_kv` validation/ordering (`p426_wave1.py:51,208,215`); the mtp golden test passes per the implementer report, and `test_mtp_b8_golden_unchanged` asserts `has_dropped is False` (the mtp record never gets `dropped`, since `verify_wave1` — not `verify_wave1_kv` — produces it).

**Beyond spec** — nothing material. `KV_ITEM_KINDS`, `build=` on `verify_all_kv`, the `dropped` field, and the kv default-axes change are all within the spec. One slight overshoot: the kv `wave1` record always carries a `dropped` key (even `dropped={}` for explicit kinds) — the spec phrases it as "a new `wave1.dropped = {kind: reason}`", implying it's populated on a drop; the always-present empty dict is a benign shape choice and the consumer ignores it. The implementer's deviation #2 (dropped only when `kinds=None`) is a reasonable reading of an under-specified point, not beyond spec.

**Summary:** one major (F1 — baseline test `test_main_kv_refuses_v_before_anything_runs` regresses, acceptance 3 fails as delivered; one-line test fix by adding `--axes m1` to the `n16,x` half); three minor (F2 consumer ignores `dropped` and reports M1 `missing`; F3 no `compute_kv` test; F4 explicit-vs-default `dropped` divergence un-locked); F5 confirms the core B8 logic is correct on the real harvest shape; mtp unchanged; nothing beyond spec.
