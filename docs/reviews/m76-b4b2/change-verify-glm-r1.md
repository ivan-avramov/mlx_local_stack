I now have enough to report. Here are my findings.

---

# Change review round 1 of 3 — M76 B4b-2 A8 consumers

## Findings

### F1 — `verify_a8_kv` requires `base_b8_sha256`, but every frozen acceptance test calls it with one argument
- **Location:** `benchmark/bench/p426_verify.py` `verify_a8_kv(results_root, base_b8_sha256, draw_path=None)`; frozen tests `test_m76_b4b2_fe_b8.py:28,228,252,...`, `test_m76_b4b2_fe_signals.py:48,235,346`, `test_m76_b4b2_fe_real.py:123,137`.
- **Severity:** blocker.
- **Evidence:** confirmed. The candidate signature has `base_b8_sha256` as a required positional (no default). All 30+ frozen-test call sites are `V.verify_a8_kv(w.root)` / `V.verify_a8_kv(M76)` — one argument. The test-writer's stated assumption (report §"Interface assumptions", and `test_m76_b4b2_fe_support.py:13`) is: "`verify_a8_kv(results_root)` … it finds `B8.json` in `results_root` (the world writes a stand-in) and records its sha as `base_b8_sha256`". The implementer's own tests pass `base` explicitly (`verify_a8_kv(w.root, base)`), so this masked the mismatch.
- **Problem:** every frozen A8 test errors with `TypeError: verify_a8_kv() missing 1 required positional argument: 'base_b8_sha256'` — the acceptance suite cannot run against the candidate. The request's "test-writer's frozen acceptance tests" are the verification contract; a signature the frozen tests cannot call fails it.
- **Failure scenario:** `pytest bench/tests/test_m76_b4b2_fe_b8.py` → every test that calls `verify_a8_kv` errors at the call (module fixtures and per-test), exactly as the baseline errored with `AttributeError` for the missing symbol — the candidate replaces one error class with another. §7.1/§7.2/§7.3 goldens in `fe_real.py` (`test_b8_regenerates_byte_identical`, `test_the_real_pilot_pair_builds_with_the_pilot_accepted`, …) never execute.
- **Proposed change:** make `base_b8_sha256=None` optional; when `None`, read `results_root/B8.json`, hash it, and use that (the frozen worlds write a stand-in `B8.json`); keep the explicit-arg path for the CLI. One line: `def verify_a8_kv(results_root, base_b8_sha256=None, draw_path=None):` and `if base_b8_sha256 is None: base_b8_sha256 = hashlib.sha256((Path(results_root)/"B8.json").read_bytes()).hexdigest()`.

### F2 — `_sequence_pair_and_superseded` / `_supersede_reasons` gained a `namespace` parameter, against §3.1's "_sequence_* stay unchanged"
- **Location:** `p426_verify.py` `_sequence_pair_and_superseded(seq, session, namespace=WAVE)`, `_supersede_reasons(..., namespace=WAVE)`.
- **Severity:** minor.
- **Evidence:** confirmed. The implementer flags this in the report ("Not satisfied"). The parameter is used only in refusal-message text (`{namespace}/run/sequence.json …`); the logic is unchanged and A7 output is unchanged (default `WAVE`).
- **Problem:** literal deviation from §3.1 ("`_sequence_*` stay unchanged (namespace-free)"). No material consequence: A7 refusals still say `wave2/run/...`; A8 says `wave2.tg2/run/...`.
- **Failure scenario:** none material — a reviewer grep for namespace-free helpers finds a new parameter, but no row, verdict or byte differs.
- **Proposed change:** drop the parameter; keep the A8 refusal text via a `where` prefix the callers already pass, or accept the deviation and note it in the spec. Either is fine; the current code is correct, just off-spec.

### F3 — B8-A8 carries extra top-level/per-session keys beyond §3.2's "Output keys = A7's plus …"
- **Location:** `verify_a8_kv` returns `version`, `repo_inputs` (top level); per-session `status`, `legs`, `faults`, `tampered`.
- **Severity:** minor (scope request, not a defect).
- **Evidence:** confirmed. §3.2 names `corpus`, `status`, `recheck`, `latency`, `base_b8_sha256`, `inputs` plus A7's keys. `repo_inputs` is needed because the pinned draw is outside the rows root and §4.4 says "re-hash every `b8_a8.inputs` file" — the draw must be bound somewhere; `check_b8_a8` re-hashes `repo_inputs` too, so the binding holds. `legs`/`faults`/`tampered` are descriptive and consumed by the sheet.
- **Problem:** none functional; the extras are descriptive and the binding is enforced. A consumer that strictly checks the documented key set would see new keys.
- **Failure scenario:** none — `check_b8_a8`, signals and panel all read these by name; nothing rejects on extra keys.
- **Proposed change:** none needed; if the operator wants the spec to match, add `repo_inputs` (and the descriptive per-session keys) to §3.2's list.

### F4 — The frozen tests do not cover the A8 packet (prompt check, protected-path assertion, export-level leak refusal, member freeze/ingest)
- **Location:** `test_m76_b4b2_fe_panel.py` header "NOT covered here (no call signature in the spec)".
- **Severity:** minor (test gap, not a code defect).
- **Evidence:** confirmed. The frozen `fe_panel.py` covers members, rubric, Holm family, and the baseline leak rule on `_kv_write_packets`, but never calls `_a8_packet`, `a8_prompt_check`, `_a8_diff`, `a8_leak_report`, or `kv_export` with `b8_a8_path`. The implementer's own `impl_panel.py` does cover these (prompt check incl. quoted/unquoted, protected paths incl. grader-accepted `Cargo.toml`, leak refusal per item, member freeze against B8-A8's sha).
- **Problem:** the acceptance (frozen) suite does not verify the panel's strongest protections: that an item whose prompt/start/final tree is not the bound one refuses, or that the export refuses a leak per item. The candidate's code does implement them.
- **Failure scenario:** a future change that drops the `a8_prompt_check` call or weakens `a8_leak_report` would pass the frozen suite.
- **Proposed change:** lift the `_a8_packet` / `kv_export` tests from `impl_panel.py` into the frozen suite (the signatures now exist), or accept the implementer's tests as the acceptance for the packet.

### F5 — The real-pilot prompt check (`§7.3`) is unverified on real data (skipped in this clone)
- **Location:** `test_m76_b4b2_impl_golden.py::test_pilot_export_prompt_check` (skips); `test_m76_b4b2_fe_real.py` has no equivalent.
- **Severity:** minor (environment, not a code defect).
- **Evidence:** confirmed. The implementer's report: "SKIPPED, because `origin/evidence` has no `benchmark/results/m76/wave2.tg2/` in this clone." I verified the real HARVEST *does* publish a `{lang}__{item}.json` evidence record (destination `evidence`) with raw `sha256` and scrubbed `published_sha256`, and that the opencode export shape (`messages[].type=="user"`, `.text`) matches `_a8_first_user_text`. So the candidate's binding is correct in shape; it is just unexercised on real bytes here.
- **Problem:** the §7.3 "checked on the pilot export before the freeze" guarantee is not demonstrated on real data in this clone.
- **Failure scenario:** none in this clone; on a clone with the evidence objects the test would run.
- **Proposed change:** run `test_pilot_export_prompt_check` on a clone that has `origin/evidence` tg2 objects before promoting.

## The request's specific questions, resolved/not

- **Can an A8 verdict come from anywhere but `axis_verdict`?** Resolved. `_kv_a8_section` returns `dict(v, **head, …)` where `v = kv_axis_verdict("A8", …)` (the only call to `m76_rule.axis_verdict` for A8 besides the sensitivity line, which is also `axis_verdict`); `head` has no `verdict` key. Incomplete → no `verdict` key at all. Per-language `loss_bound` drops its verdict. The `hold` field comes from `axis_verdict`'s `a8_hold`. No other path produces a verdict.
- **Can a contradictory/corrupted record pass as `incomplete` or accepted?** Resolved. Missing pair record / un-harvested attempt dir / PAUSED leg → `incomplete`. Missing `schedule.json`/`chain.json`/`HARVEST.json` of a harvested attempt → `RefusalError`. Unreadable chain → refuse. Two accepted attempts → refuse. Harness-DNF sidecar mismatch / missing → refuse. Accounting sidecar failing `accounting_problems` → refuse. `accepted = not reasons`; reasons come from leg/harvest/commit/plan/final-tree/dossier/provenance/slot checks. One labeling quirk: a *rejected* confirmatory session leaves the document `status == "complete"` (the candidate checks `!= "incomplete"`), but the signals section independently requires `accepted` and suppresses the verdict, so no verdict leaks. This is by design (implementer's `test_a_rejected_confirmatory_session_is_incomplete` asserts it) and matches §3.2 ("has its record") vs §4.1 ("accepted").
- **Can a session be accepted with a missing/duplicated/foreign final tree, plan/v8/seed mismatch, harness DNF not scored 0, two accepted attempts, or an accounting-fault row inside an aggregate?** Resolved — no. `final_tree_reasons` (fail-closed) rejects on missing block, 0/2 HARVEST matches, sha mismatch, and orphan (unless the run id is in `seen_run_ids` for a discarded slot). `_a8_plan_reasons` checks `check_tg2_p426`, `chain.tg2_leg`, `frozen_record.sha256`; `v8.arms` checked. `pair_keys` rejects on `sampler_seed` mismatch. Harness DNF scores 0 via `_strict(None)` (no row). Two accepted → `_a8_slots` raises. Accounting-fault items are excluded from decode `keys` and from `_a8_walls`; their tokens leave the speed aggregate (the `keys` filter). The outcome stays (strict map uses the row).
- **Is `B8.json` or the no-A8 sheet changed in any byte?** Resolved. `verify_all_kv` never adds A8; the A7 path now also runs `final_tree_reasons`, but the committed A7 rows all pass it (golden `test_b8_regenerates_byte_identical` passes). `compute_kv(b8_a8=None)` adds no A8 section, no `inputs_a8`, no A8 header, no A8 flags (the `A8` iteration in `kv_flags` is a no-op when `sig["axes"]` has no `A8`). Goldens `test_signals_without_b8_a8_are_byte_identical` / `test_partial_signals_regenerate_byte_identically` pass.
- **Can the panel export leak the arm or the box, or judge an item whose start/final tree or prompt is not the bound one?** Resolved. `a8_leak_report` runs `_kv_leaks` (C362 KV list + registry names + box identity + template tags) over task/off/on and refuses the member per item on any hit (never echoes the matched text). `a8_prompt_check` rebuilds the prompt from the pinned polyglot root and requires it equal to the first user message of the HARVEST-bound evidence export (I confirmed the real HARVEST publishes `{lang}__{item}.json` as evidence and the opencode export has `messages[].type=="user"` with `.text`). `_a8_start_tree` hashes `prepare_tree` against `entry["prepared"]`. `_a7_final_tree` checks manifest sha == row == B8-A8 key, and every object hashes to its name. `_a8_diff` refuses any new/changed protected path except a grader-accepted Rust `Cargo.toml`.
- **What do the tests miss?** F4 and F5 above. Plus: no frozen test exercises a `pair_keys` seed-mismatch for A8 (covered by shared A7 logic, but not asserted for the A8 axis); no test exercises the `repo_inputs` re-hash in `check_b8_a8` with a mutated draw (the `inputs` re-hash is tested).
- **What does the candidate do beyond the specification?** F3 (extra B8-A8 keys), F2 (namespace param), the prompt quote-wrapping allowance (`text in (prompt, f'"{prompt}"')`, justified by opencode 2.0.20 exports), and listing final-tampered rows for all languages (§9.1 names javascript; the candidate lists every language — harmless and more complete).
- **Where is the mechanism heavier than the intent needs?** (a) `_a8_slots` / `_a8_load_items` / `_a8_accounting` re-implement slot tracking that `chain_rows.load_slots` already validates (the world self-test confirms the world is valid for `load_slots`); the candidate does not reuse it, only `load_dnf`/`check_planned`. Partially justified by the spec's extra checks (two-accepted refuse, reason checks) that `load_slots` does not do. (b) `_a8_session` reads `leg.json` once for the PAUSED check and `_a8_load_attempt` reads it again (idempotent via `Reader.inputs`, just redundant). (c) `_a8_accounting` re-reads the item record via `ph.read_item_record` after `_a8_load_items` already read and validated it. (d) `kv_a8_context` loads attempts only for confirmatory sessions (good), but `_kv_a8_section` loads attempts for all accepted sessions including diagnostic (pilot/reload) for decode — descriptive, but more than the verdict needs.

## Anything else the diff breaks or leaves failing

The implementer's report notes two pre-existing failures (`test_m76_b3_impl_golden_mtp.py`, `test_m76_b4b1_fe_golden_tg1.py`) from a missing commit `f2b61127…` in the clone; these are unrelated to the candidate (the paths don't import the touched modules' A8 surface) and are environment artifacts, not defects of this change.

The one blocker is F1: the frozen acceptance tests cannot run against the candidate as shipped. Everything else is minor or a scope request.
