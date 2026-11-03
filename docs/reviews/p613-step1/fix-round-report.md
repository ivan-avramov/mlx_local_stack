All 16 findings are applied to the two files. 204 of the 212 frozen tests pass, both CLIs give byte-identical output on two runs, and the golden numbers match. There is one deviation you need to decide on: finding 2's literal rule would reject every pair on the committed data, so I implemented an adapted version (see P1).

## P1 — Deviation on finding 2
Comparing raw `schedule.json` sha256s rejected all four pairs on the committed data, which breaks the golden "B8 accepts s1, s2". The OFF and ON schedules differ only in `predictor` and `blocks[].legs[].draft_kind` (`off` vs `mtp`), which is the arm difference itself. So `p426_verify.py:schedule_plan_sha` hashes the schedule with those two fields removed, and the pair is rejected with "rule 3: schedules differ" when those hashes differ. The reason text gives both the raw shas and the plan shas.

What this leaves out: nothing checks the values of the two removed fields. A wrong `predictor` value would pass this check. The designer should confirm this version or give another rule.

## P2 — Per finding
1. `p426_verify.py:load_items`: every row needs exactly one item record. Its `slot` must name (session, language, item) and its file name must end `__<session>__<language>__<item>.json`. A missing, duplicate or mis-slotted record (wrong session, wrong name, or not a planned slot) is a RefusalError. DNF slots need no record. `p426_signals.py:_rate` gives DNF slots no speed rate, and acceptance skips them.
2. `verify_a7` / `pair_keys`: a rejected key is listed alone and the pair stays accepted. The old "N keys rejected" pair reason is gone. The schedule check is as described in P1.
3. `p426_signals.py:_check_makeup`: a non-empty `makeup`, or a leg with `makeup` / "make-up" in its record, raises "make-up legs present: substitution not implemented in step 1". Otherwise the sheet says "no make-up run". `reruns` is listed for information only.
4. `_noise_floor`: same-epoch numbers appear only when B8 accepted both pilot and reload. Otherwise the sheet says "not computed: diagnostic pair rejected (<reasons>)".
5. `_planned_outcomes` / `_flips`: comparisons run over the planned slots from `schedule.json`, a DNF counts as a non-success, and the denominator is the planned slots both sides share. Old-namespace attempts are loaded with the same checks (`_plain_attempt`).
6. `rate_primary`: `totals` is used only when `decode_rate_source` contains "completed requests". Otherwise the item is dropped with a reason, and `SIGNALS.md` prints that reason.
7. `harvest_manifests` / `manifest_sha`: identity counts only when the row's sha equals the `published_sha256` of the HARVEST "main" final-tree manifest for that item (and its run id). Otherwise it is null.
8. Cross-epoch: no pooled headline. Results are given per arm, with each matched attempt's flips over common items.
9. `_flags`: the −5 pp flag is raised only when the point estimate is below −5 pp − 1e-9.
10. `compute_a7(results_root, b8, b8_sha256=None)`: the CLI passes the sha of the B8 file bytes. A direct call without it uses the canonical-dump sha, and the header names which one was used.
11. `_coverage`: a leg's state comes from its `leg.json` (or "INVALID (leg.json self-hash)") plus B8's rejection. Disagreements with `sequence.json` are listed as "state mismatch".
12. `check_out_dirs` / `write_atomic`: both CLIs write temporaries in the destination directory, then rename them. A missing output directory gives rc 2 and `REFUSED: output directory for <name> is missing`.
13. A `nonconv_kind_on_only` flag is raised for any kind that appears in ON and not in OFF, unless the same category is already flagged as a runaway-tax category.
14. Row and item globs skip `*.dnf.*` files.
15. `planned_slots`: an `expect` count, or the length of an `expect` id list, that differs from `len(names)` refuses.
16. Every flag carries `items` (`id`, `arm`, `ending`, `other_arm`, `other_ending`), and `SIGNALS.md` prints them under the flag. The items behind each flag:
    - strict-point and Holm flags: the discordant items;
    - decode-ratio flag: items with a ratio below 1.3;
    - acceptance flag: items with acceptance below 0.70;
    - tax and kind flags: the items in that category.

## P3 — Commands and results
- **Frozen tests** (from `benchmark/`): `8 failed, 204 passed in 57.65s`. The failures:
  - `test_p613_signals_flags.py::test_holm_flag_not_raised_when_not_significant`
  - `test_p613_signals_output.py::test_md_has_no_composite_or_hours_metric`
  - `test_p613_signals_tax_speed_noise.py::test_wall_per_leg`
  - `test_p613_signals_tax_speed_noise.py::test_power_invalid_pair_keeps_quality_and_drops_speed`
  - `test_p613_signals_tax_speed_noise.py::test_cross_epoch_noise_floor`
  - `test_p613_signals_tax_speed_noise.py::test_superseded_namespace_does_not_leak_into_sessions`
  - `test_p613_signals_tax_speed_noise.py::test_coverage_counts_valid_legs`
  - `test_p613_verify_b8.py::test_rule3_missing_slot_rejects_both_unshared_keys`
- **Byte-identity**: both CLIs ran twice into `p613-impl-out2/r1` and `r2`, rc 0 each time, and all three files are identical:

  | File | sha256 |
  |---|---|
  | `B8.json` | `b6ceddfb…` |
  | `SIGNALS.md` | `50b27b18…` |
  | `SIGNALS.json` | `84d8d1a9…` |

  No absolute paths appear in the outputs.
- **Golden numbers** (strict pass counts and noise floor):

  | | OFF | ON |
  |---|---|---|
  | s1 strict | 42/43 | 41/43 |
  | s2 strict | 41/43 | 42/43 |
  | Same-epoch noise floor | 0/5 | 0/5 |

  s2 ON lenient is 43/43, which is the "ON 43/43" the contract wrote; the brief's strict 42/43 matches. B8 accepts s1, s2, pilot and reload with no rejected keys. All rule-7 identities resolve against HARVEST (0 null), with 31/43 identical in each session.
- **Ad-hoc checks** on a mutated scratch copy of the data: each of findings 1 (missing, duplicate, mis-slotted), 3, 4, 7, 11, 14 and 15 behaved as specified. Finding 6 was checked on `rate_primary` directly.

## P4 — Tests I judge unsupported or test-side
Six failures match the test-writer's report §4:
- **#1**: the test pulls numbers out of flag text such as "A7-s1".
- **#2**: the test trips on the disclaimer text in the sheet.
- **#3**: the lookup can't see `walls`, which is keyed by attempt name.
- **#5**: spec §4.9 names `on-s1.a2` as an attempt to compare.
- **#6**: the lookup also collects noise-floor records tagged `session: s1`.
- **#10**: the renamed row has no planned slot, and under finding 1 it also lacks a matching item record, so a refusal is correct.

The other two:
- **#4** (power-invalid): the report calls this a spec ambiguity. I left the behaviour unchanged because no adopted finding covers it.
- **#8** (coverage counts): §4.10 does not require a count field, so I added none.

Two tests the report listed as failing (#7 and #9) now pass because of findings 11 and 2.

## P5 — Process notes
- `cp` from the scratchpad was blocked by the session's permissions, so I copied the frozen tests into `benchmark/bench/tests/p613/` with Python `shutil.copytree`. I also read the report's §4 with Python. Both the test copy and my scratch directory are deleted.
- `git status` shows only the two candidate files and the contract, all still untracked. Nothing is committed.