I found 14 findings: 4 major, 8 minor and 2 scope requests. Two of the majors (F1, F2) break existing consumers. I could only read files, so none of this was run. Evidence is "confirmed" where I traced it in the source or the committed records, and "hypothesis" otherwise.

## Findings

**F1. §6.1 / §7.1 — a B8 record that carries `axes.A8` breaks every frozen A1–A7 panel member. Major, confirmed.**
- **Problem:** `kv_panel_members` refuses any member whose `FROZEN.json` `b8_sha256` differs from the sha of the B8 record being read (`p426_panel.py:1937-1938`). `kv_panel_section` passes the current B8 sha (`p426_signals.py:1598`). All eight frozen members (A1–A5, A7-s1/s2/s3) are bound to `4651db7e…`, the sha of today's `B8.json`.
- **Scenario:** `verify_all_kv` adds `axes.A8` and `m76/wave2.tg2/*` inputs, so the B8 sha changes. Regenerating `SIGNALS` with the existing panel then raises "bound to another B8 record". Freezing A8 members "separately" does not help, because the binding is against the whole B8.
- **Change:** Bind each member to the sha of a named B8 projection, and give A8 members the sha of the full record that carries A8. Alternatively, keep A8 in its own record (`B8-A8.json`) with a `base_b8_sha256` field. Do not leave the binding rule undefined.

**F2. §3.5 / §3.2 — a trigger of "`wave2.tg2/run` exists" makes the whole B8 build refuse in states that exist now or will recur. Major, confirmed.**
- **Problem:** `wave2.tg2/run` is already on `main`, with only the pilot harvested. `verify_a8_kv` mirrors `verify_a7_kv` and loops over s1, s2, pilot and reload. `_sequence_pair_and_superseded` raises `RefusalError` when it finds no pair record (`p426_verify.py:507-509`).
- **Scenario (partial decider):** If the decider is mid-run, stopped (the sequencer's rc 5 waits for an operator ack) or aborted, every B8 build refuses. That blocks A1–A7 as well as A8, and also blocks §7.1's "goldens on main's inputs".
- **Scenario (other pairs):** `check_kv_pair` also allows `--pair x,v` and `--pair n16,v`. §3.2 hard-codes `(n16, x)` and says nothing for other pairs. With `wave2.tg2` present, those B8 builds refuse or emit an A8 axis under the wrong pair.
- **Change:** Emit `axes.A8` only when `pair == TG2_PAIR`. Record incomplete or partial decider state as `status: incomplete` with per-session reasons, as signals already does. Refuse only on corruption, not on absence.

**F3. §6.2 / Q4 — the protected-file rule is dead code, and its Cargo.toml exception is narrower than the grader. Major, confirmed.**
- **Problem:** The final tree is `accepted_files` (`corpus_tg2.py:370-393, 395-422`). Tests and build files the grader rejected are tampered and never enter it. The only protected file that can appear is a Rust `Cargo.toml` that `tg2_grade.cargo_manifest_reasons` accepted (`tg2_grade.py:262-300`). That check allows any structural `[dependencies]` edit, including version changes and removals. The spec instead allows "additions naming crates in `OFFLINE_CRATES.md`", a second, stricter rule built from a different source than `RUST_ALLOWLIST`.
- **Scenario:** A both-pass tree whose `Cargo.toml` the grader accepted but the spec rule rejects refuses the whole member export. There is no exclusion path.
- **Change (Q4):** Allow any edit the grader accepted. Membership in the final tree already proves it. Diff `Cargo.toml` and judge it as content. Keep a refusal only as an assertion that no test or build path other than `Cargo.toml` is present.

**F4. §4.2 / Q2 — the reload control is only meaningful against s1. Major, confirmed.**
- **Problem:** Seeds are `blake2b(base, item, sample)` (`rowschema.sample_seed`, via `arm_runner.py:1117`). Reload and s1 both use base 1001. s2 uses base 2002 and reversed language order (`schedules.py:57-61`). So "X reload vs X s2" is a reseed, not a repeat. Reload also covers only the first 5 items per language, so it compares on 20 of the 80 items.
- **Scenario:** The sheet shows X-reload-vs-X-s2 discordance beside the noise floor. That figure includes seed effects and will be misread as reload nuisance.
- **Change:** Compare reload to s1 only, per arm (X reload vs X s1, N16 reload vs N16 s1), on the 20 shared items. Assert per-item equal `sampler_seed` between reload and s1 and refuse the control if any differ. Drop the s2 comparison, or label it "different seed, not a control".

**F5. §6.2 / §3.1 — panel code hard-wires the A7/tg1 shape, and the spec parameterises only B8. Minor, confirmed.**
- **Problem:** `_a7_final_tree` builds its stem from `V.WAVE` (`p426_panel.py:552`). `_StartTree` reads raw polyglot bytes. `_a7_packet` requires string `entry["solution"]` and `entry["test"]` (`p426_panel.py:673`), whereas tg2 entries carry lists `solutions` and `tests`. `kv_export` branches on `member.startswith("A7-")` and uses `KV_INPUT_SOURCE["A7"]`.
- **Scenario:** An implementer who follows §3.1 literally builds A8 packets that look under `wave2/` and refuse every item.
- **Change:** List the panel call sites in §6, including a `kv_a8_context` analogue of `kv_a7_context`, and state that `_a8_packet` must not reuse `_StartTree`.

**F6. §4.2 — "the B7 per-language helper" does not exist. Minor, confirmed.**
- **Problem:** `m76_rule` has only `a8_hold` and `_groups_of`. The only α in B7 for A8 is 0.001 one-sided, which gives a vacuous interval on 20 items.
- **Scenario:** The implementer invents the interval, and the sheet shows an interval whose α the spec never fixed.
- **Change:** Specify `loss_bound` on each language's sub-maps at `PER_SESSION_ALPHA` (0.025), labelled descriptive, with no verdict.

**F7. §5 — the re-check rules are narrower than the sequencer's. Minor, confirmed.**
- **Problem:** The sequencer requires an ack when `not inside or operator_review` for s1 (`p426_wave2.py:1530-1541`). The spec says only "not `inside`". The spec also does not require `doc.gate`, `axis`, `sessions`, `ref`, `test` and `attempts` to equal B8's accepted attempts, which `check_recheck_doc` enforces. And "a missing record for a harvested session refuses" would reject pilot and reload as written. Only s1 and s2 have re-checks, and re-check 2 is sealed after the reload leg.
- **Scenario:** A rerun after the seal leaves a re-check that is sealed and valid but computed over a superseded attempt. The sheet labels it as the interim re-check.
- **Change:** Copy the `check_recheck_doc` binding and the full ack rule into B8. State exactly which sessions require a record.

**F8. §3.4 — the foreign-worktree guard is vacuous for tg2. Minor, confirmed pattern mismatch; consequence is a hypothesis.**
- **Problem:** `_kv_path_re` matches only `m76-f45|m76-q-<arm>` (`p426_verify.py:1446-1453`). tg2 worktrees are `m76-g2-n16` and `m76-g2-x`; the manifests show `.../worktrees/m76-g2-x/...`. The router block is excluded, so the pilot is unaffected today.
- **Scenario:** A manifest leaf naming the other arm's worktree passes unflagged.
- **Change:** Add the `m76-g2` prefix, parameterised by axis, and test it with a planted foreign-worktree leaf.

**F9. §6.1 / §6.4 — member selection and Holm statements are under-specified or inconsistent. Minor, confirmed.**
- **Problem:** `kv_members()` takes no B8, yet is called from `kv_panel_family` (`p426_signals.py:1514`) and `kv_export` (`p426_panel.py:1853-1854`), so "gains them when `axes.A8` exists" needs a signature change that preserves the default. "Prints A1…A7 unchanged and the family re-adjusted" is contradictory, because Holm-adjusted p for A1–A7 change when the family grows.
- **Scenario:** The existing members' adjusted p silently shift, or the A8 members never enter the family.
- **Change:** Add `kv_members(b8=None)` and state that raw p are unchanged while adjusted p are recomputed.

**F10. §7.1 — the golden claim "only `axes.A8` / the A8 sections are added" is false. Minor, confirmed.**
- **Problem:** B8 `inputs` gains every `m76/wave2.tg2/*` file. The SIGNALS header changes `b8_sha256`, `inputs_sha256` and `n_inputs`. The flags gain `panel_incomplete`, since A8 members are expected but not exported. `compute_kv` writes `axes.A7 = pending` when A7 is absent (`p426_signals.py:1705`), so absent A8 must be omitted, not "pending".
- **Scenario:** The acceptance test as worded cannot pass, or is weakened ad hoc.
- **Change:** Define the golden as an exact projection: remove `axes.A8`, the `wave2.tg2` inputs and the header derivatives, and expect byte equality. Specify omission rather than "pending".

**F11. §4.4 — "twin" renderers need explicit entries. Minor, confirmed.**
- **Problem:** `render_kv`'s decode loop treats only `k == "A7"` specially, and any other key reads `d["both"]` (`p426_signals.py:1917-1925`). `kv_flags` loops over `("A1","A5","A7")` and raises `session_interaction` for A7 only (`:1767, :1785`). `KV_BLOCKING` is never read; flags carry `blocking=True` themselves.
- **Scenario:** `decode["A8"]` raises `KeyError`, or the A8 interaction and `hold` flags are dropped.
- **Change:** List these sites. Add a `hold` flag with `blocking=True` built from `final["hold"]`.

**F12. §3.3 / Q1 — the trigger is worded per attempt; it should be per row. Minor, confirmed.**
- **Q1 answer:** Yes for A7 too. `B8.json` has zero null manifest shas, so the A7 golden holds.
- **Problem:** An attempt whose rows are all DNF lists main files (items, rows) but no manifests, so the attempt-level wording would reject it wrongly. The wording also lacks the row-level case of a `passed` row with no `final_tree` at all.
- **Change:** Trigger per row, and require exactly one matching manifest for every row with a `final_tree`. Test the all-DNF case and the one-evidence-run-per-item layout (tg2 has one per item, tg1 one per invocation).

**F13. §6.2 / assumptions 3 and 4 — task rebuild and start tree are right in principle, but not "from harvested records alone". Minor, confirmed, with a hypothesis on the scrubbed transcript.**
- **Problem:** `Tg2Corpus.prompt` calls `spec_text`, which calls `verify_source`, which needs the polyglot checkout at `7e0611e7…` and the item's `inputs_sha256` (`corpus_tg2.py:239-287`). `prepare_tree` needs the same checkout. The transcript on `evidence` is the scrubbed export, so the first-user-message sha check may fail systematically if scrubbing touches that text. That is a hypothesis, since I could not read the evidence branch.
- **Scenario:** Every item refuses, with no remedy named.
- **Change:** State the polyglot-root requirement, as A7 does. Compare against the HARVEST-bound scrubbed export, and run the check on the pilot export before freezing the spec.

**F14. §4.2 — the "launch-latency log" is not named. Minor, confirmed.**
- **Problem:** No file is named. Candidates are `watch.jsonl` and `log_bounds.json`. B8 reads neither today, so signals would read bytes B8 never hashed.
- **Change:** Name the file or files and add them to B8's inputs.

**Scope request S1 — bind each tg2 leg to the pinned plan.** B8 trusts each attempt's own `schedule.json`. It checks that both arms' plans are equal and that rows equal planned slots. It does not check that the plan is the pinned draw's prefix for that session, which `schedules.check_tg2_p426` can do. The other checks I would add are `chain.tg2_leg == session` and `chain.frozen_record.sha256 == v8.sha256`. Today a short or mis-composed s1 reaches the verdict with only a count-based `size_warning`. Per-language composition is not asserted, and the HOLD runs only over the languages present.

**Scope request S2 — one more reload check.** Add a reload-key-set check (the 20 keys equal the first 5 per language of s1). F4 covers the seeds.

## Answers to §9 and to your assumptions

- **Q1:** Yes, apply §3.3 to A7 too, but trigger per row (F12).
- **Q2:** No, not as specified. Compare reload to s1 only, per arm, with a seed-equality assert (F4).
- **Q3:** Include H. It is what the model saw. It names no arm or box. It tells the judge that helper files and `Cargo.toml` additions were permitted, so they are not scored as scope creep.
- **Q4:** Allow any edit the grader accepted (F3).
- **Q5:** Yes, keep 0.5. An identical manifest means an identical file set and identical bytes, so there is nothing to judge for multi-file trees as well.
- **Assumption 1:** Holds for the pilot shape. The tg2 differences are one evidence run per item and a manifest path with dotted stems. Both are handled by the existing `rid` and `run_id` filtering. DNF and multi-item shapes are unobserved, because acceptance §7.2 tests only the pilot.
- **Assumption 2:** Holds for existing A7 inputs, but see F12 on the trigger wording.
- **Assumption 3:** Reproducible only with the polyglot checkout (F13).
- **Assumption 4:** The materialised tree is the right start tree. `_StartTree`'s raw polyglot bytes are wrong for tg2 and cannot be reused (F5).
- **Assumption 5:** False as specified (F1).
