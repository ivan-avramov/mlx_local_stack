# Test-writer report, delivery 2 — M76 B4b-2 (candidate applied), spec v1.5

Tests frozen as v1 at 2026-11-21T04:51:37Z; candidate = `../scratch/candidate-1.patch`. Commands: `../fe_test.sh stack …` (candidate),
`../../twb/fe_test.sh stack …` (baseline copy; my 5 test files + `fixtures/m76_b4b2_fe/` copied there, nothing else).

## 1. Result

| run | baseline | candidate |
|---|---|---|
| my 140 tests (5 files), **amended** | 34 passed · 95 failed · 11 errors (every failure is a missing A8 symbol/argument except the 5 A7 per-row reds) | **140 passed** (`test_m76_b4b2_fe_b8.py` re-run after the last tightening: 67 passed) |
| v1 tests, **un-amended**, on the candidate | – | 51 passed · 78 failed · 11 errors (all 89 non-passes were interface shape — see §2; **no (D) among them**) |

**No test I wrote found a candidate defect.** Every v1 failure on the candidate was my interface assumption (I). The findings in §5 come from reading the
candidate, not from a red test.

## 2. Classification of the v1 failures on the candidate (all (I))

| cause | cite | tests | amendment |
|---|---|---|---|
| `verify_a8_kv(results_root, base_b8_sha256, draw_path=None)` — the base sha is an argument (B8.json is not read), I had `verify_a8_kv(results_root)` | `p426_verify.py:2864` | every A8 call in `_b8`, `_signals` (Scenario), `_real` (~85 tests incl. the 11 fixture errors) | `A8(w)` helper → `V.verify_a8_kv(w.root, w.base_b8_sha())`; real: `sha(M76/"B8.json")` |
| a language whose only slot is a DNF leaves no rows file / manifest, and the candidate (like A7) requires a provenance manifest per language (`kv_provenance_reasons`) — my pilot world has one item per language | `p426_verify.py:2758` | `test_a_dnf_slot_is_exempt[A8]`, `test_harness_dnf_slot_is_accepted_and_counted[2]` | moved to the `reload` session (5 items / language); the three harness-DNF tests likewise |
| the A8 world must be laid out `<x>/benchmark/{results,m65}` because `check_b8_a8` re-hashes `repo_inputs` (the pinned draw) at `rows_root.parents[1]` | `p426_verify.py:2929` | signals `Scenario` | builds the B3 world under `<tmp>/benchmark/`, copies the draw to `<tmp>/benchmark/m65/` |
| the candidate adds a top-level `inputs_a8` (and header `b8_a8_sha256` / `a8_inputs_sha256` / `n_a8_inputs`) | `p426_signals.py:1733` | `test_a8_record_changes_only_the_a8_parts_of_the_sheet`, `…_real_sheet[2]` | `projection` drops `inputs_a8` |
| A8 sits mid-sheet (before "A2 / A3 / A4 / M1"), heading is `## A8 tg2 (X − N16; …)`; my text test cut at the heading and read the rest as A8 | `p426_signals.py:2197` | `test_a8_record_leaves_the_a1_to_a7_text_alone` | strips the A8 section by heading prefix; remaining extra lines must mention A8 / hold |

Also amended (not a candidate-driven failure): `test_fixtures_carry_no_home_path_user_or_host` read this box's username from a literal regex; it now takes
`getpass.getuser()` / `socket.gethostname()` at run time (the file holds no username, home path or hostname — checked by grep). And I tightened the five
§3.6 plan-binding tests to require the **record** form ("rejects the session": `accepted False`, matching reason, not a refusal); all five hold on the candidate.
`test_v8_arms_must_be_n16_x` stays "rejected or refused": §3.2 builds B8-A8 only for the (n16, x) v8, so a v8 with other arms is *not applicable* (refusal) and the
§3.6 arms check is unreachable through `verify_a8_kv` (finding m3).

## 3. Per test (class · item · baseline → candidate · disposition)

Dispositions: **kept** = passes unchanged; **A** = amended (I). All final outcomes on the candidate: PASS. Baseline: P = PASS, R-sym = RED, symbol absent, R-beh = RED, behaviour.

* **support** (8 tests; b): pinned fixtures, draw, no-PII (A), world sessions ×4, chain-reader validity — P → P.
* **b8, per-row final-tree rule** (§3.3, §7.4), `[A7]/[A8]`: clean (b/c) P/R-sym → P/P (A); no block (a), unpublished (a), two matches (a), row sha ≠ published (a), orphan (a): **R-beh**/R-sym → P/P (A for A8); discarded-rerun not an orphan (c, A8 only) R-sym → P (A); all-DNF (b/c) P/R-sym → P/P; one DNF exempt (b/c) P/R-sym → P/P (A: reload); committed B8 has no null sha (b) P → P.
* **b8, axis table / names / guards** (§3.1, §3.2): `KV_AXES` (c), 4 foreign-name refusals (c), A7 refuses tg2 name (b, P → P), own-`m76-g2`-worktree normalised (c), other arm's worktree rejected (c) — R-sym → P (the pair isolates A8's `m76-g2` prefix from A7's `m76-f45|m76-q`).
* **b8, provenance** (§3.4): real manifests pass (c), 6 tg2-only keys reject (c), missing manifest rejects (c), `kv_normalise` + A7 alias (c) — R-sym → P (A).
* **b8, record / partial / refusals** (§3.2): document fields + inputs (c), partial decider incomplete (c), session without pair record incomplete (c), not built for a tg1 world (c), missing schedule / chain refuse (b ×2), unreadable chain refuses (b) — R-sym → P (A).
* **b8, plan binding** (§3.6): off-draw schedule, other leg, `chain.tg2_leg`, `frozen_record.sha256` (c, tightened to the record form), v8 arms (c) — R-sym → P (A).
* **b8, re-check labels** (§5; 6 tests, fixture ERROR on baseline): complete decider, missing re-check-s2 only labels, superseded attempt, s1 outside without ack, unsealed, sha ≠ sequence.json (c) — → P (A).
* **b8, latency** (c) → P (A). **S27** (§9, c): harness DNF ×2, sidecar mismatch / missing, rerun reads accepted attempt, two accepted attempts, rerun without reason, accounting fault listed / sidecar naming another row / sidecar missing, PAUSED ×2, speed-invalid keeps quality — R-sym → P (A; harness DNF on reload).
* **signals** (29; c except where stated): verdict = `axis_verdict`, heading after A7, outcome incl. DNF = 0, HOLD −25 pp blocks, −20 pp exactly does not, LOSS / UNDECIDED flags, per-language descriptive, noise floor, reload control (equal seeds; `refused: seeds differ`), partial → incomplete, PAUSED → incomplete, unknown language refuses, sensitivity (one faulted item, 3 fault kinds, none → "no faulted items"), verdict keeps faulted items, accounting fault keeps outcome and leaves decode, speed-invalid keeps quality, latency, no-B8-A8 ⇒ no A8 (b; **P on baseline**), explicit `None` = default, A8 changes only A8 parts (b/c, A), A1–A7 text alone (b/c, A), other-B8 refuses, changed input refuses — R-sym (1 P) → P.
* **panel** (18): members ×2, rubric / input source, expected members, Holm family join, <5 judged not tested, flag favouring reference, not flagged favouring treatment — R-sym → P (no amendment needed: `kv_members(sessions, a8_sessions)`, `kv_panel_family(…, a8_sessions)`, `kv_expected_members(b8, b8_a8=…)` carry an `a8` parameter and the tests pass `a8_sessions` only where it exists; `kv_expected_members`' parameter is `b8_a8`, so its output assertion is skipped — it asserts only that an A8 parameter exists); leak / box / family-token / protected_manifest (b, 10) P → P; family without A8 unchanged (b) P → P.
* **real** (18): B8 regenerates (b, P → P), `B8-A8.json` beside it (c, R-beh → P), B8 has no A8 (b), SIGNALS regenerate (b, P → P), SIGNALS-partial (b, P → P), frozen panel has no A8 (b), §7.2 projection ×2 (c, A), §7.3 five tests on the real pilot pair (c, R-sym → P, A), pilot schedule / rows / v8 premises (b, P → P).

## 4. Existing tests of the touched families, on the candidate (verbatim)

* `test_m76_b3_*` (all): **3 failed, 589 passed** — `FAILED …test_m76_b3_impl_golden_mtp.py::test_mtp_golden_is_meaningful`, `::test_mtp_golden_component[leg_checks]`, `::test_mtp_golden_committed_b8_and_signals_regenerate`
  (`REFUSED: frozen stack_head_on f2b61127c55f0436b6c6c777bec5384ce004d62d does not resolve: git rev-parse failed`; `git … show f2b61127…:main_models.yaml` exit 128) — this clone's own.
* `test_m76_b4b1_*` (all): **1 failed, 480 passed** — `FAILED …test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical` (`REFUSED: frozen stack_head_on f2b61127…`) — this clone's own.
* `test_p426_*`: **207 passed**.
* `p613 p613s2 p613s3 p613s4` (one invocation): **NOT COMPLETE: the run was stopped by the background time limit** (these tests are slow here; my own suite competed for the CPU). 493 tests had run — 476 passed, 17 skipped, **0 failed** — of roughly 900 (the implementer reports 883 passed, 22 skipped). Output: `../scratch/tw2_fam_p613.txt` (one character per test, no `F`). I do not report the family as passed.
* `test_m76_b8_*`, `test_s26_p1*`, `test_t3_*` (one invocation; the first attempt was killed at the 10-minute background limit, this is the rerun with a longer limit): **NOT COMPLETE: the run was stopped by the background time limit.** 168 tests had run — 167 passed, 1 skipped, **0 failed**. Output: `../scratch/tw2_fam_misc.txt`. Not reported as passed.

I did not run these families on the baseline; the `f2b61127…` failures name the absent commit and do not touch the candidate's code.

## 5. Review of the candidate against spec v1.5

**Verdict: fix then merge** — fix list: M1 (narrow / re-record the tg1 golden allowance; operator accepts the three edited existing tests), m1 (write `B8.json` before attempting A8), m2–m5 (small); and confirm the two unfinished existing-test families (§4: p613*, m76_b8/s26_p1*/t3_*) complete green. No blocker; the candidate passed every one of my 140 tests and the 207 `test_p426_*`, 589 `test_m76_b3_*` (3 absent-commit failures) and 480 `test_m76_b4b1_*` (1 absent-commit failure) existing tests.

What holds (checked in code and by test): the A8 verdict is only `m76_rule.axis_verdict("A8", look, …, languages=…)` via `kv_axis_verdict` (`p426_signals.py:2029`); descriptive figures use `m76_rule.loss_bound` /
`stats.paired_session_delta` and no other verdict code; incomplete vs refusal follows §3.2 (no pair record, unharvested leg, PAUSED, missing re-check / latency → incomplete; unreadable / contradictory / unsealed → refuse);
B8-A8 binds `base_b8_sha256` and re-hashes every input plus the pinned draw on every consumer (`check_b8_a8`, called by `compute_kv` and `kv_a8_context`); with no `B8-A8.json`
`B8.json`, `SIGNALS.md/.json`, `SIGNALS-partial.md/.json` regenerate byte-identically on the committed records (my `real` goldens, run on the candidate); the S27 facts (harness DNF sidecars, rerun-keyed records, accounting sidecars through `p426_hooks.accounting_problems`, PAUSED) behave as §9 says; the leak refusal reports pattern names only.

| id | sev | where | evidence | failure scenario |
|---|---|---|---|---|
| M1 | **major (process)** | patch: `test_m76_b3_impl_a7.py`, `test_s26_p15_rerun_pairs.py`, `test_m76_b4b1_impl_golden_tg1.py` | the implementer edited three existing tests, incl. a golden: `b4b2 = lambda p: key == "b8" and p.startswith(".b8.inputs.") and p.endswith(".jsonl")` lets *any* `.b8.inputs.*.jsonl` sha differ from the recorded baseline golden, and the baseline fixture was not re-recorded | a later change that corrupts a KVWorld rows file passes the tg1 golden unnoticed. The fixture edits themselves follow from §3.3 (rows must carry `final_tree.manifest`), so keep them, but narrow the golden allowance to the KVWorld rows-file keys (or re-record the golden) and have the operator accept it — the brief makes the test directory read-only to the implementer |
| m1 | minor | `p426_verify.py:2906-2909` (`main`) | B8.json and B8-A8.json are computed together and written by one `write_atomic`; an A8 refusal (`RefusalError` from `verify_a8_kv`, e.g. a corrupt tg2 chain) returns rc 2 and **writes no `B8.json`** | spec §1/§7: "`B8.json` is byte-identical in every state". A damaged A8 record during the decider blocks regenerating B8 for A1–A7. Compute B8 first, write it, then try A8 (a refusal then leaves B8 written and exits 2 naming A8) |
| m2 | minor | `p426_verify.py:2929` `check_b8_a8` | `repo_inputs` are re-hashed at `Path(rows_root).parents[1]`, i.e. rows_root must be `<repo>/benchmark/results` | any other layout (a copied rows tree, my first test world) refuses with "input … is missing" though the files are intact; the failure names the file, not the layout assumption. Pass the repo root explicitly or record the draw sha only |
| m3 | minor | `p426_verify.py:2884-2885` | `v8.arms != [ref, test]` appends a reason, but `a8_applies` (2413) already refuses unless `arms == TG2_PAIR`, so the §3.6 branch is unreachable via `verify_a8_kv` | dead code that reads as a guard; a v8 with swapped arms yields a refusal "no A8 to verify", not a rejected record. Either drop the check or let `a8_applies` ignore arms and keep the reason |
| m4 | minor | `p426_verify.py:2908` | the document `status` is `complete` when no confirmatory session is `incomplete`, even if one is `rejected` | a consumer reading only `status` (not `accepted`) treats a rejected decider as complete; `compute_kv` / `kv_a8_member_sessions` do check `accepted`, so nothing wrong today. Set `complete` only when every confirmatory session is accepted (as §4.1 words it) |
| m5 | minor | `p426_signals.py:1630` | `b8_a8_sha256 or _sha_doc(b8_a8)` falls back to a canonical-JSON sha, not the file's bytes; the panel freeze binds the **file** sha (`_kv_b8_a8`) | a library caller that omits `b8_a8_sha256` gets header / panel bindings that never equal the exported A8 members' `b8_sha256`. The CLI always passes the file sha, so only direct callers are exposed |
| n1 | note (heavier than the intent) | `p426_verify.py:2427-2660` | `_a8_session_rows`, `_a8_load_items`, `_a8_load_attempt`, `_a8_slots` duplicate `session_rows` / `load_items` / `_kv_load_attempt` to add rerun / sidecar handling; `a8_leak_report` re-runs the leak check `_kv_write_packets` already does; B8-A8 carries extra `legs`, `faults`, `tampered`, `repo_inputs`, `inputs_a8` | correct and tested, but two loaders drift apart; folding the rerun-keyed names into `load_items` (namespace-aware) would remove ~150 lines. Not a merge condition |
| n2 | note | `p426_panel.py:1954-1960` | the prompt check accepts the export text equal to the prompt **or the prompt wrapped in one pair of double quotes** (taken from tg1 exports on the evidence ref) | defensible, but the tg2 pilot export was not on the evidence ref in this clone, so the quoting rule was never exercised on a real tg2 export: if the real shape differs the first A8 export refuses (fail-closed, not silent) |
| n3 | note | spec | §7.3 prompt check on the pilot export did not run (implementer's skip; my suite does not cover `_a8_packet`) | the A8 packet path — start tree, protected-path refusal, `Cargo.toml` diff, prompt check, leak refusal at export — is covered **only by the implementer's own fixtures** (`test_m76_b4b2_impl_panel.py`), never by an independent test. I did not write them in v1 (no signature) and did not add them now; the brief's amendment scope was (I) tests only |

Mechanism vs intent: one verdict path, one descriptive path, B8-A8 as a separate record — right-sized. The per-row rule (`final_tree_reasons`) is small and shared by both axes. The extra record keys and the second loader are the only heavy parts (n1).

## 6. Files touched (this delivery)

`test_m76_b4b2_fe_support.py` (PII check reads username / hostname at run time), `test_m76_b4b2_fe_b8.py`, `test_m76_b4b2_fe_signals.py`, `test_m76_b4b2_fe_real.py` (candidate interface); `test_m76_b4b2_fe_panel.py` unchanged. Scratch outputs in `../scratch/tw2_*.txt`.
