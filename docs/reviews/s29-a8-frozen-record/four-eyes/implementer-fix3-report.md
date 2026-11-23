# Implementer report, fix round 3 (Sol P1): S29 B8-A8 rule 3.6, spec v1.2

- **Baseline:** `a073d594e`. I started from candidate 3, already staged.
- **Scope:** this round fixes Sol P1 only.
- **Export:** `out/candidate-4.diff`, covering `benchmark/bench` and excluding `s29b_frozen/`.
- **Untouched:** nothing was committed. I did not edit the frozen suite `s29b_frozen/` or the spec. The spec shows as modified in
  the working tree because of the lead's v1.2 edit.

## Production change (`benchmark/bench/p426_verify.py`, `a8_frozen_record_reasons` only)
- **Early return removed:** candidate 3 returned early (`got == v8 sha → []`) for every session. That return is gone.
- **Pilot:** accepts only the v8 base's sha256. The amendment's sha, or any other sha, is still a reason.
- **s1, s2 and reload:**
  - They accept only the amendment's sha256, and only when `a8_amendment_problems` finds no problem.
  - Naming the v8 base gives a rule-3.6 reason: "… is the v8 base's: a <session> leg runs on the amendment
    (wave2.tg2/run/amendment.json), never on the v8 base". This holds whatever the state of the amendment.
  - The other decider reasons are reworded so they no longer mention the v8 base as an acceptable alternative: amendment absent,
    amendment not an object, sha not the amendment's.
- **Comparison hardening:** both sha comparisons now require string operands, so a missing `sha256` never matches a missing one.
- **Nothing else changed:** no other function, rule, runner or sequencer code was touched.

## Fixture worlds (they now model the real records)
- **`test_m76_b4b2_fe_support.py`:**
  - New helper `publish_tg2_amendment(ns_dir, v8, pilot_dossier, previous)`. It writes a sealed `p426_timeout_amendment` with the
    fields `p426_freeze.write_amendment_tg2` writes:
    - `kind`, `v8_base_sha256`, `corpus="tg2"`, `w_<lang>_s` (synthetic, at the 382 s floor), `leg_deadline_s` (via
      `fz.tg2_deadline_s`), `settle_bound_s`, `pilot_dossier_sha256` (the byte sha of the pilot dossier) and `created`.
    - It re-points every decider chain that names the v8 base, or a previous amendment, at the new amendment
      (`frozen_record.path = $STACK_WORKDIR/run/amendment.json`).
    - Pilot chains stay on the v8 base.
  - `World` publishes the amendment at the end of `__init__` (tg2 only; tg1/A7 is untouched). It republishes whenever
    `write_dossier("pilot")` rewrites the pilot dossier, for example after `edit_harvest` on the pilot.
  - **Decider-only tg2 worlds** (no `pilot` in `sessions`): 41 tests use these. In the real campaign the pilot always ran, so these
    worlds now write the sequencer's pilot leg records, a pilot pair record and a sealed PASS pilot dossier. The amendment binds
    that dossier.
    - The pilot attempt directories are not in the tree. B8-A8 therefore reports the pilot as `incomplete` ("not harvested"),
      where before it said "no pair record". It is never accepted.
    - The new helpers are `recorded_pilot_legs`, `recorded_pilot_pair` and `recorded_pilot_dossier`.
- **`test_m76_b4b2_impl_world.py` (`A8World`):** the same scheme, reusing those helpers. It publishes after `save_seq` and
  republishes when the pilot dossier is rewritten.
- **`test_m76_b4b2_impl_r1fix.py` `_write_v8`:** it re-seals the v8 base and points every chain at it. It now calls
  `w.publish_amendment()` afterwards, so the amendment binds the new v8 base and the decider chains name the amendment again.
  This is one added line.
- **No rule weakened:** no test assertion was relaxed. The earlier failures all came from worlds whose decider chains named the
  v8 base, which is exactly what P1 now rejects.

## New negative tests (`test_s29_impl_a8_frozen_record.py`)
- **`test_r2_decider_naming_the_v8_base_is_a_reason[session × amendment]`:**
  - Runs for s1, s2 and reload, both arms, with the real amendment, with no amendment and with a tampered amendment.
  - Each case gives a non-empty list of reasons, all rule-3.6, at least one mentioning "v8 base".
- **`test_e2e_decider_naming_the_v8_base_is_rejected[s1|s2|reload]`:**
  - Works on a copy of the real records. One n16 decider chain is re-pointed at the v8 base.
  - That pair is `rejected` with a rule-3.6 reason that names the attempt and "v8 base".
  - The other three pairs stay `accepted` with no reasons.
  - The document is `incomplete` for s1 and s2, and `complete` for reload, because reload is diagnostic.
- **Not confirmed by a run on candidate 3:** I did not run these tests against candidate 3. That they would fail there is my
  reading of the code: candidate 3 returned `[]` whenever the chain named the v8 sha, for any session.
- **Docstring:** the module docstring now cites v1.2.

No A8 result value was read or reported. The tests check only status, reasons and input shas.

## Commands and results (all `../fe_test.sh stack …`, run from the copy)
1. **All 17 `bench/tests/test_m76_b4b2_*.py` modules** (before the new s29 tests were added): **398 passed**, exit 0.
2. **Full required set:**
   - Scope: `bench/tests/s29b_frozen`, `bench/tests/test_s29_impl_a8_frozen_record.py`, all 50 modules in `.realrec_tests`, and
     the 7 `test_m76_b4b2_*` modules not already in `.realrec_tests` (fe_packet, fe_r2, impl_panel, impl_r2fix, impl_r3fix,
     impl_r4fix, impl_signals). The run used `-rfEs`.
   - Result: **1747 passed, 0 failed, 0 skipped** (`1747 passed in 738.54s`), exit 0.
   - Log: `impl/scratch/fix3-full.log`.
   - Not comparable to round 2's 1601: round 2's set did not include those 7 extra b4b2 modules.

## Judgement calls
- **J6.** A decider-only fixture world gets a *recorded* pilot (sequence leg and pair records plus a sealed dossier) without
  pilot attempt directories.
  - Why: this models "the pilot ran and the sequencer recorded it" without changing which sessions those tests evaluate.
  - Side effect: the pilot's B8-A8 reason changes from "no pair record" to "not harvested". No test asserted the old text.
  - Alternative: build full pilot attempts in every decider-only world. That changes those tests' session set and roughly doubles
    their cost.
- **J7.** The fixture amendment's walls are synthetic (all at `TG2_WALL_FLOOR_S`). B8-A8 checks only the seal, `kind`, `corpus`,
  `v8_base_sha256` and `pilot_dossier_sha256`, not the walls.
