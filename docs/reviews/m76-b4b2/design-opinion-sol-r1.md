P1

- Location: §6.1/§6.4, `p426_panel.kv_freeze`, `kv_panel_members`, `p426_signals.kv_panel_section`.
- Severity: blocker.
- Evidence: confirmed.
- Problem: Separately freezing A8 does not preserve the existing panel bindings. Every current A1–A7 `FROZEN.json` is bound to the current B8 SHA. Adding `axes.A8` changes that SHA, while `compute_kv → kv_panel_section → kv_panel_members` rejects every member bound to another B8.
- Concrete failure scenario: A8-s1/s2 are successfully frozen against the new B8; signals ingestion encounters A1 first, sees its old B8 SHA, and refuses before constructing the required joint Holm family.
- Proposed change: Define mixed immutable bindings: A1–A7 remain bound to the old B8, accepted only when removing `axes.A8` and its inputs from the new B8 reproduces the exact old B8 bytes/SHA; A8 members bind to the full new B8. Pass B8-derived expected members explicitly through `kv_export`, `kv_panel_members`, `kv_expected_members`, and `kv_panel_family`; preserve `kv_members()`’s no-argument behavior.

P2

- Location: §1 and §6.2 (`_a8_packet`, task/start-tree construction); parent B4b-1 Goal.
- Severity: blocker.
- Evidence: confirmed.
- Problem: The panel cannot be built from harvested records alone. `Tg2Corpus.prompt` reads `.docs` from an external polyglot checkout, and `tg2_materialize.prepare_tree` requires that checkout’s source bytes. The committed universe contains hashes, not those bytes; harvested final trees contain accepted final files, not the complete materialised start tree.
- Concrete failure scenario: On a clean evidence-processing checkout without the pinned polyglot working tree, B8 and signals succeed, but every A8 packet fails before producing its task or start-tree diff.
- Proposed change: Harvest a content-addressed materialised start-tree bundle for selected items, or explicitly make the pinned polyglot Git object database a recorded input and bind every consumed blob into B8. Use the transcript’s first user message as the authoritative task bytes and reconstruction only as a validation. Q3 recommendation: include H because it was part of the model-visible task and defines permitted helper edits; it leaks neither arm nor box.

P3

- Location: §6.2, “Final tree = the evidence ref”.
- Severity: major.
- Evidence: confirmed.
- Problem: The described source contradicts the actual harvest layout and existing A7 call chain. `_a7_final_tree` reads the manifest from main and objects/events from the evidence ref. Real tg2 HARVEST records likewise publish `*.final_tree/manifest.json` to main and objects to evidence.
- Concrete failure scenario: A literal `_a8_final_tree` implementation performs `git show <evidence-ref>:.../manifest.json` and refuses despite a complete valid harvest.
- Proposed change: Specify the split explicitly: manifest from the B8-verified main checkout; objects and scrubbed events from the evidence ref, each bound through HARVEST and row hashes.

P4

- Location: §3.3, `harvest_manifests`, `manifest_sha`, `pair_keys`.
- Severity: major.
- Evidence: confirmed.
- Problem: The proposed rule still misses an individual non-DNF row with no `final_tree` or no manifest path. If other rows in the attempt publish manifests, the attempt-level condition passes; because the row names no unpublished path, the second condition also passes. Current `pair_keys` then accepts the key with null hashes as merely non-identical.
- Concrete failure scenario: One of 80 s1 rows loses its `final_tree` block while the other 79 are intact. B8 accepts the session and signals score the row; the panel can silently omit identity information.
- Proposed change: For every non-DNF row require a valid manifest path and SHA, exactly one matching destination-main HARVEST record, matching item/run identity, and matching published SHA. Reject duplicate/orphan final-tree manifests; exempt DNF slots. Q1 recommendation: apply this to A7 too—committed A7 B8 has no null manifest mappings, so successful output remains unchanged. Q5 recommendation: retain the 0.5 treatment for both-pass identical manifests; the manifest covers the complete multi-file accepted tree and `missing` set.

P5

- Location: §2 walls/latency and §4.2 latency-log summary.
- Severity: major.
- Evidence: confirmed.
- Problem: No consumable, B8-bound latency-log input is defined. C367’s log is outside the attempt trees; B4b-1’s harvest contract does not publish it into main, the pilot HARVEST does not contain it, and `compute_kv` has no evidence-ref input.
- Concrete failure scenario: All A8 legs are harvested correctly, but signals cannot produce the required per-leg-window launch-latency summaries from `rows_root`; an implementer either omits them or reads mutable scratch data outside B8.
- Proposed change: Publish a sealed latency record or summary under `wave2.tg2/run/`, bind its SHA in `sequence.json` and B8 inputs, and define timestamp-window matching and required fields.

P6

- Location: §5 re-check labels.
- Severity: major.
- Evidence: confirmed.
- Problem: Seal, sequence SHA, and acknowledgement checks do not establish that a re-check belongs to the attempts B8 selected. The runner’s real resume path additionally calls `check_recheck_doc`, checking gate, axis, sessions, arms, and exact selected attempts.
- Concrete failure scenario: s1 is rerun after an earlier re-check. `sequence.json` points to the old but validly sealed re-check; B8 labels it as the selected session’s interim re-check.
- Proposed change: Require the same current-selection checks as `check_recheck_doc`, consistency of `inside`/`operator_review` with the embedded record, and the committed simulation report SHA. Require rechecks only for s1/s2, not pilot.

P7

- Location: §6.4 versus §7.1 and the goal’s byte-identity claim.
- Severity: major.
- Evidence: confirmed.
- Problem: The acceptance criterion says that with tg2 present only A8 sections are added, but the parent spec requires A8 to join the existing Holm family. Adding A8 can change every A1–A7 Holm-adjusted p-value; adding `axes.A8` also necessarily changes the B8 SHA printed in signals.
- Concrete failure scenario: A8 contributes a new small p-value, changing an existing A7 Holm value. Correct output fails the proposed golden; preserving the golden violates the pre-registered panel plan.
- Proposed change: Require byte identity only when A8 is absent. For A8-present output, permit the B8/header binding, A8 sections, panel completeness, flags, and Holm-adjusted values to change; require all raw A1–A7 member statistics and frozen artifacts to remain identical.

P8

- Location: §4.2 and §9 Q2.
- Severity: minor.
- Evidence: confirmed.
- Problem: “Same-seed X reload vs X s1/s2” is false for s2. B4b-1 fixes s1/reload seed base 1001 and s2 seed base 2002.
- Concrete failure scenario: X reload disagrees with X s2 and the sheet presents that as reload instability despite the changed seed/session schedule.
- Proposed change: Report same-arm, same-seed reload comparisons as X reload–X s1 and N16 reload–N16 s1; report X–N16 within reload as the same-seed arm control. If X reload–X s2 is retained, label it different-seed and descriptive.

P9

- Location: §4.2, “the B7 per-language helper”.
- Severity: minor.
- Evidence: confirmed.
- Problem: No such helper exists. `m76_rule` computes only per-language point estimates for HOLD; `stats` exposes generic paired estimators. The spec therefore leaves the interval method and alpha unspecified.
- Concrete failure scenario: One implementation reports 95% descriptive intervals while another uses A8’s α*=0.001, producing materially different-looking uncertainty.
- Proposed change: Specify the exact function and alpha. Recommendation: run `m76_rule.loss_bound` on each language subset at `PER_SESSION_ALPHA=0.025`, label the 95% intervals descriptive and unadjusted, and keep HOLD based only on the exact point estimate.

P10

- Location: §6.2 Cargo exception and §9 Q4.
- Severity: minor.
- Evidence: confirmed.
- Problem: “Any edit the grader accepted” would be broader than the model-visible permission. `tg2_grade.cargo_manifest_reasons` can accept changes beyond adding a dependency, including removal or alteration of an existing allowlisted dependency.
- Concrete failure scenario: A passing model removes an unused dependency. A broad panel exception silently treats that prompt-violating build-file edit as permitted.
- Proposed change: Allow only structural additions to `[dependencies]` whose names are in the pinned offline allowlist; preserve every existing dependency and every other TOML table exactly. Reuse the grader parser, then apply this stricter additions-only delta.
