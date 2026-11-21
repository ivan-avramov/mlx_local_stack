Verdict: one major finding (P1), five minors, and one acceptance item not shown. I traced everything by reading source. I had no shell, so I ran no tests and rely on the implementer's reported results.

## Prior findings (design ledgers r1–r3)

| Finding | Status |
|---|---|
| L1 (separate record, base-sha binding) | Resolved. `B8.json` is only read, and `check_b8_a8` binds `base_b8_sha256`. |
| L2 (`B8.json` never depends on A8) | **Not resolved.** See P1. |
| L3, L4 (prompt, polyglot root, final-tree split) | Resolved in source. The prompt check has not run on a real tg2 export (P7). |
| L5 (per-row final-tree rule) | Resolved. The orphan exemption is looser than the spec (P3). |
| L6, L7, L9–L18, S1, S2 | Resolved. I checked L7 against `Sequencer.check_recheck_doc` and the ack shape at `p426_wave2.py:1582-1586`. L6 has a time-zone defect (P2). |
| L8 (goldens) | Resolved per the implementer's report; not re-run. |
| M1–M6, N1–N6 (§3.7 regrade) | Moot. §9.1 removes §3.7, and the candidate has no regrade code. |
| M7–M12 | Resolved. M9 is subject to P3. |

Your questions, answered from source:
- **A8 verdict source:** every A8 verdict, including the sensitivity line, comes from `m76_rule.axis_verdict` through `kv_axis_verdict`. The per-language lines come from `loss_bound` with the verdict dropped.
- **Duplicate and DNF handling:** two accepted attempts of a slot refuse (`_a8_slots`). A harness DNF has no row, so `_strict(None)` scores it 0. Its sidecar check matches the harvest's check.
- **No-A8 sheet and the panel:** with no A8 record, `kv_flags` and `render_kv` skip A8. An `A8-*` panel directory is ignored. The A7 byte-identity relies on the implementer's golden tests.
- **Panel leak and binding:** the leak report covers task, off and on texts. The prompt is bound to both arms' exports, the start tree to the pinned universe, and final trees via `_a7_final_tree`.

## Findings

**P1 — `B8.json` is not written when A8 verification refuses** (major, confirmed)
- **Location:** `p426_verify.py` `main`, the new block after `verify_all_kv` (patch ~2983–2991).
- **Problem:** `write_atomic(texts)` runs only after `verify_a8_kv` succeeds. Any `RefusalError` from A8 ends in `return 2` and nothing is written. That contradicts L2 ("`B8.json` never depends on it") and §3.5.
- **Scenario:**
  - The decider is mid-run and a harvested attempt lacks `schedule.json`.
  - Or `recheck-s1.json` no longer matches the selected attempts after a rerun.
  - Or `exec_latency.json` is unsealed.
  - Each of these blocks regenerating `B8.json` for A1–A7. The A8 inputs are already on `main` (`wave2.tg2/`), so this is live now.
- **Fix:** write `B8.json` first in its own `write_atomic`. Then try B8-A8 and return 2 on refusal, leaving `B8.json` on disk. A stale `B8-A8.json` already fails the base-sha check in `check_b8_a8`.

**P2 — latency windows are parsed as local time** (minor, confirmed in source)
- **Location:** `p426_signals.py` `_a8_time`.
- **Problem:** it uses `datetime.strptime(...Z).timestamp()`, which treats a naive datetime as local time. Leg `started` and `ended` are ISO-Z strings (checked in `leg.json`). `exec_latency` `t` may be epoch seconds, which the code accepts.
- **Scenario:** on a box not set to UTC, epoch-`t` rows are shifted by the UTC offset against ISO-Z leg windows. Latency is then assigned to the wrong leg or to none.
- **Fix:** parse the ISO-Z string as UTC (`calendar.timegm(time.strptime(...))`), and pin the `t` format in the spec.

**P3 — orphan exemption is not bound to a run id** (minor, confirmed)
- **Location:** `final_tree_reasons` and `_discarded_run_ids`.
- **Problem:** `slot_attempts` carry no `run_id`. The exemption is `other in seen_run_ids and rid in discarded`, and `seen_run_ids` covers every run in the leg.
- **Scenario:** an item with a harness-fault rerun also has a stray published manifest under another item's accepted run id. That manifest passes as "discarded".
- **Fix:** also refuse an orphan whose run id is the accepted run of any row in the attempt.

**P4 — the slot table is hand-rolled** (minor, mechanism heavier than needed)
- **Location:** `_a8_slots`, `_a8_harness_dnf`, `_a8_session_rows`.
- **Problem:** `chain_rows.load_slots` already enforces these rules. The candidate diverges in two places:
  - `_a8_harness_dnf` does not require a non-empty `reason`, which `chain_rows._harness_dnf_rows` does.
  - `_a8_session_rows` globs every `*.jsonl` in the session directory. `load_slots` refuses an unregistered rows file.
- **Scenario (hypothesis):** a stray rows file holding a row for a transport-DNF slot turns that DNF into a scored row. `load_dnf` drops the DNF record when a row exists, and `check_planned` still passes.
- **Fix:** reuse `chain_rows.validate_progress` and `_harness_dnf_rows` at least. Or add the registered-file check.

**P5 — accounting-fault legs are not marked speed-invalid** (minor, hypothesis)
- **Location:** `_a8_speed_invalid`.
- **Problem:** §9.6 lists an accounting fault among the tiers that mark "that leg's speed figures descriptive-invalid". The candidate excludes only the faulted item and keeps the leg labelled `descriptive`.
- **Fix:** if `leg.speed_valid` does not already reflect accounting faults, add them to the invalid reasons.

**P6 — scope request: row seeds are not bound to the plan**
- **Problem:** only off-versus-on seed equality is checked (`pair_keys`). Nothing compares a row's `sampler_seed` to `rowschema.sample_seed(id, 0, TG2_P426_LEGS[session].seed)`. The schedule check covers items and order, not seeds.
- **Scenario:** both arms run s2 with s1's base and the session still passes.
- **Proposal:** add the check, as a cheap REASON.

**P7 — §7.3 prompt check on a real export is not shown** (acceptance, disclosed by the implementer)
- **Problem:** the real-export test skips in this clone, so `_a8_first_user_text` and the `"<prompt>"` quote wrapper are checked only against fixtures modelled on tg1 exports. A wrong guess fails closed (refuses every member) rather than corrupting, but it is unproven.
- **Proposal:** run it on the pilot export before the freeze, as §7.3 requires.

## What the tests miss
- P1's CLI path, where an A8 refusal must not suppress `B8.json`.
- P2's mixed epoch and ISO formats.
- P3's orphan exemption on a foreign run id.
- P4's stray rows file and a harness DNF with no reason.
- P6's seed binding.
- A real tg2 export for the prompt check.

## Beyond the spec
These are harmless. They are `repo_inputs`, `version`, the extra per-session keys (`status`, `legs`, `faults`, `tampered`), `_a8_counts`, per-language walls with a ratio, and the `_sequence_pair_and_superseded(namespace=…)` parameter, which changes message text only. The `b4b2` lambda in the golden-tg1 allow-list is broad: it tolerates any `.b8.inputs.*.jsonl` sha change.