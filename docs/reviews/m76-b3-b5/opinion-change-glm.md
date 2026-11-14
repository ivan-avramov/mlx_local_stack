I've traced the candidate (`benchmark/bench/p426_*.py`, `m76_ids.py`, `run_retrieval.py`, `retrieval.py`, `chains/c147/run_tg1_chain.py`) against spec v1.1 and the frozen FE tests. Findings below.

---

## F1 — MAJOR (confirmed): the `lever` Python surface the spec states ("generalised") was not implemented; the frozen red-first FE tests fail with `TypeError`

**Location.** `benchmark/bench/p426_leg.py:119` (`registry_delta_problems`), `:296` (`model_argv_problems`); `benchmark/bench/p426_plan.py:57` (`leg_name`), `:61` (`frozen_path`); `benchmark/bench/p426_wave1.py:46` (`schedule`), `:64` (`leg_argv`).

**Evidence.** The spec Interfaces section says the registry delta is "`p426_leg.py:110-150` **generalised**" and the worker argv delta is "`p426_leg.py:285-305`" — i.e. the existing functions are generalised with a `lever` keyword. The frozen FE tests were written to that surface:
- `test_m76_b3_fe_kv_lever.py:27` `p426_leg.registry_delta_problems(..., lever="kv", **kw)`
- `:143` `p426_leg.model_argv_problems(..., lever="kv", **kw)`
- `:257` `p426_plan.leg_name(axis, arm, 1, "s3", lever="kv")`
- `:279` `p426_plan.frozen_path(tmp_path, "s3", lever="kv")`
- `test_m76_b3_fe_golden_cli.py:53-57` `leg_name/leg_argv/registry_delta_problems(..., lever="mtp")`
- `:132` `p426_wave1.schedule(axes=..., lever="kv", arms=("n16","x"))`

The candidate instead added **separate** `kv_*` functions (`p426_plan.kv_registry_delta_problems`, `kv_argv_problems`, `kv_leg_name`, `kv_frozen_path`, `p426_wave1.schedule_kv`, `leg_argv_kv`) and only added the `lever` kwarg to `plan_leg`, `qualify_problems`, `wave1_dir`. The six functions above take no `lever`/`arms` parameter and no `**kwargs`, so every call above raises `TypeError: ... got an unexpected keyword argument 'lever'`. `test_unknown_lever_is_refused` (`:166`) passes `lever="bogus"` and asserts `(ValueError, KeyError, SystemExit)` — `TypeError` is not in that tuple, so it fails too.

**Problem.** Acceptance criterion 1 ("Red-first tests … the `kv` delta accepted for N16/X, X/V, N16/V; refused when an MTP key differs, a non-KV key differs, or the argv differs beyond the two flags …") is not met: the red-first tests cannot run. The functional checks the criterion asks for *do* exist (in the `kv_*` functions, covered by the implementer tests), so the protection is in place — but the frozen four-eyes tests stay red.

**Failure scenario.** `pytest benchmark/bench/tests/test_m76_b3_fe_kv_lever.py test_m76_b3_fe_golden_cli.py` → a large fraction of cases error at collection/call time with `TypeError`, so the operator's four-eyes gate (red-first tests green) cannot close.

**Proposed change.** Add `lever="mtp"` (and `arms=None` for `schedule`) to the six functions, dispatching to the `kv_*` helpers when `lever=="kv"`; keep the `kv_*` names as the implementation. This satisfies both the spec's "generalised" wording and the frozen FE tests without changing behaviour.

---

## F2 — MAJOR (confirmed): `--lever` CLI placement breaks two frozen FE CLI tests

**Location.** `benchmark/bench/p426_verify.py:1975` (`--lever` on the `all` subparser only); `benchmark/bench/p426_panel.py:1418-1419` (`--lever` on a new `kv-eligibility` subparser, `required=True, choices=["kv"]`).

**Evidence.** `test_m76_b3_fe_golden_cli.py:104-108` `test_lever_flag_exists_with_mtp_and_kv` asserts `"--lever"`, `"mtp"`, and `"kv"` all appear in the joined `--help` of `p426_panel` and its subcommands `("all","a7","export","a7-export","freeze","pack","verify")`. `p426_panel`'s real subcommands are `a7-export/a7-cursor/a7-seal/kv-eligibility`; `--lever` lives only on `kv-eligibility` (not in the list) and never offers `mtp`, so the assert fails for `bench.p426_panel`. Separately, `test_unknown_lever_value_is_refused` (`:112`) runs `p426_verify --lever bogus` with no subcommand; since `--lever` is on the `all` subparser, argparse reports `argument axis: invalid choice: 'bogus' (choose from 'all')` — has `"invalid choice"` but no `"'kv'"/"'mtp'"`, so the assert fails for `bench.p426_verify`. I reproduced this parse behaviour directly.

**Problem.** The spec lists `--lever mtp|kv (default mtp)` on `p426_verify` and `p426_panel`. `p426_panel` has no `mtp` spelling of `--lever` at all (the mtp panel path `a7-export` takes no `--lever`); `p426_verify`'s `--lever` is unreachable at top level.

**Failure scenario.** `pytest test_m76_b3_fe_golden_cli.py::test_lever_flag_exists_with_mtp_and_kv[bench.p426_panel]` and `::test_unknown_lever_value_is_refused[bench.p426_verify]` fail.

**Proposed change.** Add a top-level `--lever` (default `mtp`, choices `mtp|kv`) to `p426_verify` and `p426_panel` (propagated to the `all`/`a7-export` paths as a no-op for `mtp`), or widen the FE subcommand probe list to include `kv-eligibility` and accept `kv`-only — but the cleaner fix is the top-level flag the spec names.

---

## F3 — MINOR (confirmed): the `lever=mtp` golden over-captures `EXPECTED_BUILDS`

**Location.** `benchmark/bench/p426_plan.py:27-31` (adds `s3` to `EXPECTED_BUILDS`); fixture `benchmark/bench/tests/fixtures/m76_b3_fe/golden_mtp_surface.json` (`expected_builds` = `{"s2": …}`).

**Evidence.** `test_m76_b3_fe_golden_cli.py:38-42` `test_mtp_surface_is_byte_identical_to_the_baseline[key=expected_builds]` compares the whole `EXPECTED_BUILDS` dict to the baseline golden, which holds only `s2`. The candidate legitimately adds `s3`, so the dict differs. The material invariant — `s2` byte-identical, `s` absent — is preserved (`test_s2_pins_unchanged_and_s_has_none` passes; `EXPECTED_BUILDS["s2"]` is unchanged at `p426_plan.py:24-26`).

**Problem.** One golden parametrization fails though no `mtp`/`s`/`s2` behaviour changed.

**Proposed change.** Regenerate the golden with `s3` present (it is a baseline-of-the-candidate fixture), or scope the golden's `expected_builds` check to `{"s2"}` only.

---

## F4 — MINOR (confirmed): A5 196,608 rung resolves to 65,024, not the spec's "65,536"

**Location.** `benchmark/bench/m76_ids.py:131-139` (`budget`), `:37-39` (`PROMPT_OVERHEAD=512`, `CONTEXT_CAP=262144`).

**Evidence.** `budget(196608)` gives `resolved = CONTEXT_CAP - (rung + PROMPT_OVERHEAD) = 262144 - 196608 - 512 = 65024`. The spec (§A5) says "the 196,608 rung resolves `max_tokens` to 65,536" (262144 − 196608, ignoring the 512-token prompt overhead). The implementer test `test_m76_b3_impl_lever.py:293` codifies 65024 (`b["196608"]["resolved_max_tokens"] == 262144 - 196608 - 512`).

**Problem.** Literal spec/impl mismatch. No material consequence: the resolved budget is equal in both arms and `prompt + resolved = 262144 ≤ cap` holds; 65024 is stricter than 65536.

**Proposed change.** Either correct the spec text to 65,024 (or "≈65 k") or drop `PROMPT_OVERHEAD` from the 196,608 cell if 65,536 is intended — but the conservative value is safer; I'd fix the spec wording.

---

## F5 — scope request (hypothesis): A5 panel export reuses the `math500` rubric for `longctx`

**Location.** `benchmark/bench/p426_panel.py:1289` (`axis = {… "A5": "math500" …}`), `:57` (`AXIS_RUBRIC` has no `"longctx"`).

**Evidence.** `kv_export` maps member `A5` to axis `"math500"` because `AXIS_RUBRIC` has no `"longctx"` entry; packets would be built under the `reasoning` rubric. `kv_export` is not called internally and is not exercised by any test. Functionally this is mostly benign: A5 retrieval items that are both-correct yield identical code strings (excluded from judging), and the chain-4 reasoning items that reach judging are well-served by the `reasoning` rubric. But there is no `longctx`/retrieval rubric, so a non-identical retrieval answer (one arm recovers 4/5 codes, the other 5/5 — excluded as not-both-correct anyway) would never be judged; and the prompt template is math500's.

**Problem.** The spec says "panel adapters as the other Wave 1 axes" for A5; A5 has no dedicated rubric, so the adapter silently reuses math500's. No test covers `kv_export` for A5.

**Proposed change.** Add a `"longctx"` rubric (or explicitly document A5 panel = reasoning-only, retrieval excluded), and add a test for `kv_export("A5", …)`.

---

## What does **not## What does **not** fail (confirmed by tracing)

- **Pair differing beyond KV keys accepted?** No. `p426_verify._kv_registry_reasons` → `kv_registry_delta_problems` (registry delta exactly `{kv_bits,tq4_attention}`+note), `_kv_argv_reasons` → `kv_argv_problems` (argv delta exactly `--kv-bits`/`--tq4-attention`, every other token equal in order), `_kv_equal_reasons` (sampling, `kv` except KV fields, `thinking_budget==81920` equal). A non-KV registry key, a stray argv flag, or a sampling difference is refused at B8; the receipt-level `kv_pair_problems` (`p426_receipt.py:422`) adds `_equal_problems` (router/env/snapshots/drafter). Triple coverage.
- **Valid pair refused?** No false positive found: argv normalisation (`_kv_path_re`) only masks the leg's own worktree component; `kv_argv_problems` compares the remainder in order, and the real M76 argvs differ only in the two KV flags.
- **MTP-OFF or wrong build slipping through?** No. `kv_registry_problems` pins the three MTP keys ON; `kv_worker_problems` requires the MTP flags exactly once; `_kv_equal_reasons` runs `_draft_problem("on", d)` on every row (a null draft → "no draft object"). Wrong build: `kv_record_problems` checks against `EXPECTED_BUILDS["s3"]`; `pin_problems` checks `registry_{arm}_sha`/`registry_n16_sha` and `build_pins` (mlx_vlm/mlx_serve).
- **`lever=mtp` outputs change?** No, apart from F3. `plan_leg`/`qualify_problems` dispatch only when `lever=="kv"`; the `mtp` code path is line-for-line unchanged, `EXPECTED_BUILDS["s2"]` is byte-identical, `"s"` is absent, `p426_wave1.AXES` has no `longctx`.
- **A5 items/budgets/convergence equal between arms?** Yes. Items and `sampler_seeds` live in the shared `ids.json`; `budget()` is per-rung and derived from the one deployed profile (`deployed_budget()`), so identical for both arms; the offline `budget_problems` check runs in the planner before any leg; seed derivation matches across `m76_ids.row_sampler_seed`, `run_retrieval` (`sample_seed("retrieval:{task_seed}",0,request_seed)`), `run_reasoning` (`sample_seed("reasoning:{task_seed}",0,request_seed)`), and the verifier's `_kv_keys`.
- **Signals verdicts/looks/flags for B7?** Yes. `compute_kv` refuses without `bench.m76_rule`/`stats.paired_session_delta`; A1 reads `axis_plan("A1")` looks and calls `paired_delta` at each look's α; A5 calls `verdict_a5(b,c,n)` (b=ref-pass/test-fail, c=ref-fail/test-pass) and applies the ≥0.85 / ≥−5 pp per-task gates; A7 uses `paired_session_delta` at the final look's α* and `session_interaction` (blocking flag); the N16 s1-vs-s2 noise floor is emitted only when `ref_arm=="n16"` (so V−X gets none — consistent with the evidence available to that pair).

## What the candidate does beyond the spec (not defects)

- Adds `--lever` to `p426_harvest` (`:1214`) and `p426_freeze` (`:860`) CLIs — not named in the spec's `--lever` list but required for the kv harvest/freeze paths to be reachable; reasonable.
- New `p426_panel kv-eligibility` subcommand and `kv_wave1_eligibility`/`kv_panel_family` helpers (panel-over-both-correct-pairs, Holm) — matches the spec's "panel adapters as the other Wave 1 axes".

## Summary

The in-use machinery (leg, sequencer, verifier, signals, panel, chain) is functionally correct and the protections the request asks about hold. The material failures are contractual: **F1** and **F2** leave the frozen four-eyes red-first tests red (a `lever`-keyword surface mismatch plus two `--lever` CLI placements), so acceptance criterion 1 cannot close; **F3** is a golden over-capture; **F4** is a harmless literal budget mismatch; **F5** is an untested A5 panel-rubric gap worth a scope decision.
