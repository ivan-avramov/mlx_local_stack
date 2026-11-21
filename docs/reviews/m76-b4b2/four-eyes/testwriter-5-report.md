# Test-writer report, delivery 5 (last) — M76 B4b-2, fix round 3 (candidate 4 = candidate 3 + `fix-3.patch`), new-identity records

Commands: `../fe_test.sh stack …` (candidate 4), `../../twb/fe_test.sh stack …` (baseline copy; my changed / new files copied there). Nothing committed, pushed or reset.
Outputs: `../scratch/tw5_cand4_final.txt`, `../scratch/tw5_base.txt`, `../scratch/tw5_impl_cand4.txt`.

## 1. Verdict: **fix then merge** — two blockers, both found on the real new-identity records, both small

* **T1 (blocker): the new-identity pilot pair is REJECTED by provenance.** The new manifests carry a per-invocation `probe_session` block (`run_dir`, `sid`, `started`) that differs between the arms by construction;
  `kv_normalise` does not drop it, so `kv_provenance_reasons` reports 12 "differs" reasons and `pilot.accepted` is False. Every A8 session of the decider (s1, s2, reload) would be rejected the same way.
* **T2 (blocker): the prompt check refuses a real pilot export.** opencode records the run argument double-quoted with each embedded `"` backslash-escaped. The candidate accepts the prompt exactly or in one pair of quotes only, so
  `rust/say` (whose spec says `stop at "trillion"`) is refused: `tg2-m76-n16-pilot.a1 rust/say: the rebuilt tg2 prompt != the first user message of the evidence export`. cpp / java / javascript pass.
  Verified on the real bytes: the exported text with the outer quotes removed and `\"` → `"` equals the rebuilt prompt exactly.

Neither is in E1–E3; both are real-record facts the old-identity data (and every synthetic fixture, mine included) could not show. E1, E2, E3 themselves are implemented as ruled (§4).

## 2. Results

| set | baseline | candidate 4 |
|---|---|---|
| my whole set, 9 files (216 tests incl. an emptied scratch file) | 34 passed · 169 failed · 13 errors | **210 passed · 6 failed** |
| `test_m76_b4b2_impl_*` (8 files, 171 tests) | – | **168 passed · 3 failed** |

**My 6 failures on candidate 4 (all (D), listed verbatim by name; causes T1 / T2):**
```
FAILED test_m76_b4b2_fe_real.py::test_the_real_pilot_pair_builds_with_the_pilot_accepted            (T1)
FAILED test_m76_b4b2_fe_real.py::test_the_real_pilot_identities_are_matched_and_provenance_passes   (T1)
FAILED test_m76_b4b2_fe_real.py::test_the_real_pilot_pair_is_accepted_without_any_reason            (T1)
FAILED test_m76_b4b2_fe_real.py::test_the_real_pilot_exports_pass_the_prompt_check                   (T2: RefusalError "…rebuilt tg2 prompt != the first user message of the evidence export")
FAILED test_m76_b4b2_fe_packet.py::test_the_exports_escaped_embedded_quotes_are_the_runners_prompt   (T2, synthetic form of the same fact)
FAILED test_m76_b4b2_fe_r3.py::test_the_new_identity_probe_session_block_is_per_invocation_not_provenance (T1, synthetic form)
```
First T1 reason (real): `rule 2d: pilot manifest provenance (cpp: …L3.full.a1.jsonl / …): probe_session.run_dir differs (n16 '$STACK_WORKDIR/opencode-probe-v2/run-20261121T020858-2050a8cb75d7', x '$STACK_WORKDIR/opencode-probe-v2/run-20261121T023532-601920ff9acf')`; the differing keys are exactly `probe_session.run_dir`, `probe_session.sid`, `probe_session.started` (per language, 12 reasons); s1 / s2 / reload give only their `incomplete` reasons.

**The implementer's three failures** (`FAILED test_m76_b4b2_impl_golden.py::test_pilot_pair_b8_a8_shape`, `::test_provenance_passes_on_the_real_tg2_pilot_manifests`, `::test_pilot_export_prompt_check`) are the same two facts: the first two are T1 (their pilot-accepted / provenance asserts on the new pair); the third is T2's family but fails earlier on their own bug — it passes `"origin/evidence"` to `V.resolve_commit` (`RefusalError: --evidence-ref: 'origin/evidence' is not a commit sha`; it needs `git rev-parse` first), so it never reached the prompt comparison.

Baseline: the 34 passes are the same invariants (goldens, A7 controls, leak rule, world sanity, the committed B8 / SIGNALS regenerations — which still hold on the new data: B8.json and SIGNALS(-partial) regenerate byte-identically). Every other test fails on the missing A8 interfaces.

## 3. Real-record tests re-pointed (`test_m76_b4b2_fe_real.py`) and new

* Re-pointed to the new-identity records: pilot accepted with no reason (T1: red), final-tree identities matched, provenance passes (T1: red); the record binds `B8.json` and every input; no regrade machinery; latency incomplete; the §7.2 projection (A1–A7 sections, decode, coverage, raw panel statistics identical to the committed `SIGNALS(-partial).json`, only the A8 section / header / flags / Holm column differ) — **passes** on the new data; the premises (pinned-draw schedules, rows ↔ published manifests, v8 is the tg2 kv pair) pass.
* New: `test_the_real_s1_is_incomplete_with_x_s1_unaccepted` — s1 `incomplete` (no pair record: X s1 a1 / a2 INVALID before any item), not a refusal, no keys; s2 / reload `incomplete`; document `incomplete` — **passes**.
* New: `test_the_real_pilot_exports_pass_the_prompt_check` (B11) — the evidence objects are present (probe via `git ls-tree` of the evidence ref; the evidence ref holds evidence files, **not** `HARVEST.json`, which is on `main`); polyglot checkout found; all 8 pilot rows × both arms: **red on T2**.
* New regression: `test_the_old_identity_pilot_pair_still_verifies_from_its_archive` — `wave2.tg2-old-identity/` copied as `wave2.tg2/` into a scratch rows tree (its records name `…/wave2.tg2/…` paths) still verifies (pilot accepted, no reason): **passes** — the archived pair keeps its meaning.
* New: `test_the_real_n16_s1_attempt_satisfies_every_per_attempt_binding` (in `_r3`) — the real N16 s1 attempt (VALID, 80 items) loads through the A8 inventory (`load_slots`, E1 ledger, E2 accounting), passes the v8-identity, plan-seed and final-tree checks and `check_tg2_p426`: **passes**. So E1 / E2 / B2 / B4 / B10 hold on 80 real runner rows, not only on the pilot.

## 4. E1–E3 and the new scenario tests (`test_m76_b4b2_fe_r3.py`, 19 tests)

All E1 / E2 scenarios pass on candidate 4 and fail on the baseline (no interfaces):
* **E2, the runner's own branch shape**: an accounting fault recorded by the abort route on an accepted slot (unmarked attempt, ledger entry and row + list entry + sealed sidecar) is accepted as an accounting fault — on a plain slot, on an accepted **rerun** (index 1, sidecar `.r1`), and with **no item record** (`item_record_sha256` None, as the real abort route writes it); the slot table and the listing carry the fact; a marker True on the **row alone** without the record refuses; an explicit False marker beside no record stands.
* **E1**: transport and harness DNF slots with their one `dnf` entry are accepted (control); a second entry, a `row`-kind entry, or no entry for a DNF slot refuses; a DNF entry carrying a foreign rerun index refuses; two `row` entries at different rerun indices refuse (one per slot, not per index); a ledger that is not a list refuses.
* **E3**: the implementer's explanation holds — `World.edit_row` (v3 support) re-hashes the invocation record, so the old test needed to write the file directly; the new r3 / r2 tests do that.

## 5. Review of fix 3 (`fix-3.patch`, 376 lines: `p426_verify.py`, the r1fix test, the r3fix test)

E1 (`_a8_ledger`): every ledger entry shape-checked before any filtering; exactly one entry per scored slot over all kinds; kind matches the scored source; a row entry's rerun index (absent → 0) equals the accepted attempt's; a DNF entry's index checked only when present (the runner writes none) — right, and consistent with `check_p426_ledger`. E2 (`_a8_accounting`): when the chain carries `p426_accounting_faults` the chain's record (list entry + sealed sidecar) decides; a half record refuses; markers, where present, must agree; the decision is written back to the slot table before `_a8_load_items`; without the list key the old exact-agreement rule stays. E3: test-only. No defect found in the diff; the two blockers above are outside it.

| id | sev | where | note |
|---|---|---|---|
| T1 | **blocker** | `p426_verify.py` `KV_A7_INVOCATION_KEYS` / `kv_normalise` | add the `probe_session` block (or its `run_dir` / `sid` / `started`) to the per-invocation identity the normaliser drops; then the real pilot pair is accepted and every decider session can be. Red tests: the three real-pilot tests and `test_the_new_identity_probe_session_block_is_per_invocation_not_provenance`; the paired control `test_a_real_provenance_difference_beside_probe_session_still_rejects` (passes) pins that nothing else is loosened |
| T2 | **blocker** | `p426_panel.py` `a8_prompt_check` (`text not in (prompt, f'"{prompt}"')`) | accept the runner's real argument form: wrapped in one pair of quotes with `"` escaped as `\"` (check: strip the pair, unescape `\"`, compare exactly; keep the exact and the plain-quoted forms). Red: `test_the_real_pilot_exports_pass_the_prompt_check`, `test_the_exports_escaped_embedded_quotes_are_the_runners_prompt`; control `test_an_escaped_export_that_differs_still_refuses` (passes) |
| T3 | minor | `test_m76_b4b2_impl_golden.py::test_pilot_export_prompt_check` | resolves `"origin/evidence"` through `resolve_commit` (needs a sha); resolve with `git rev-parse` first, as my test does. Its two other failures go away with T1 |
| T4 | note | carried | delivery-3 minors f1–f4 and delivery-4 g1–g3 unchanged and not adopted |

## 6. Not run / caveats

* I did not rerun the existing test families (`test_m76_b3_*`, `b4b1`, `p426`, `p613*`, `m76_b8`, `s26`, `t3`) on candidate 4; the implementer reports `589 passed, 3 failed` (b3), `480 passed, 1 failed` (b4b1), `207 passed` (p426), the four failures naming the absent commit `f2b61127…`. I have not verified them, and I never completed `p613*` / the `m76_b8` + `s26` + `t3` families.
* After T1 and T2 the real-record tests should be rerun: the prompt-check test only proves the 8 pilot rows; the decider's s1 / s2 exports (many prompts with quotes, backslashes, tabs) are the designer's real-record acceptance (B11) — the escaping rule should be checked against every item, not only `rust/say`.
* `test_m76_b4b2_fe_tmpdump.py` is an emptied scratch file (no tests); delete it.
