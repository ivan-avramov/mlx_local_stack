## Per-finding verdicts

**Sol P1 — malformed/truncated `tool_use.state` read as `{}` → RESOLVED.**
`_tool_state` (`benchmark/bench/p426_signals_divergence.py:33-49`) validates `part.state` is a dict, `status` is in `("completed","error")`, `state.input` is a dict, `completed` carries a non-`None` `output`, `error` carries a string `error`; any failure raises `RefusalError` naming the attempt/item/line. The old `{}` fallback is gone (`_input_json` now reads `state["input"]` directly, line 52). The three `C:no_input|no_output|no_state` worlds and the three `parse_messages` cases in `test_p613s4_fixes.py` reproduce the failure on the unfixed candidate and pass on this one; the refusal message contains `python/alpha` (the `where` passed by `a7_divergence` is `f"{att['name']} {rid}"`).

**Sol P2 — `_final_ready` accepts an axis missing `b1`/`b2` → RESOLVED.**
`benchmark/bench/p426_signals.py:899` now requires `set(blocks) == set(V.W1_BLOCKS)` (with `V.W1_BLOCKS = ("b1","b2")`, `p426_verify.py:573`) in addition to every block accepted. Extra keys are also rejected (inequality is bidirectional). `test_axis_missing_a_block_is_not_final` parametrizes 5 axes × `b1`/`b2` and reproduces the failure on the candidate; `test_axis_unaccepted_block_is_not_final` keeps the pre-fix protection.

**Sol P3 / GLM F1 — resolved vs passed ref → RESOLVED (per the operator's disposition).**
Fix 3 keeps `header.evidence_ref` and the `evidence:<full sha>:` input prefix as the resolved full SHA and adds `evidence_ref_given` (the string as passed) to both the divergence record (`p426_signals_divergence.py:184`) and the header (`p426_signals.py:879`); the rendered line shows both (`p426_signals.py:1251-1252`). The frozen golden was amended (`tests-amend.diff`) to expect the full SHA in `evidence_ref`/input prefixes and `b6ec7819` in `evidence_ref_given`. This matches the disposition (contract ambiguity, adapted). `test_evidence_ref_given_is_as_passed` and `test_golden_evidence_ref_given` cover short and full forms.

**GLM F2 — no test of a B8-rejected A7 session blocking FINAL → RESOLVED.**
`test_b8_rejected_a7_session_blocks_final` (`test_p613s4_fixes.py:188-196`) builds a hermetic world whose `s1` ON HARVEST is edited so B8 rule 5 rejects the pair, re-verifies and commits B8, exports and judges a fresh panel, then runs `all`. It asserts `status != FINAL`, `A7-s1` in `header.final.missing`, `ready is False`, `divergence.complete is False`, and `sessions.s1.status != accepted`. The test-writer confirms it passes on the candidate.

**GLM F3 — `--evidence-ref` without `--panel` → RESOLVED.**
`p426_signals.py:859-860` raises `RefusalError("--evidence-ref requires --panel …")` before any work, so the CLI exits rc 2 and writes nothing. `test_ref_without_panel_refuses_rc2` asserts rc 2, `REFUSED` + `--panel` on stderr, and no output files. The help text was updated (line 1322).

**GLM F4 — section position on the real sheet → RESOLVED.**
`test_golden_section_between_subjective_and_flags` pins `## Subjective panel (§4.5; …) < HEADING < ## Flags` on the generated committed-data sheet, and `test_golden_committed_sheet_section_position` pins the same on the committed `SIGNALS.md` (skips until step 4 commits). The hermetic `test_section_heading_and_position` already covered the world.

**A1 — does it let a real difference go uncounted contrary to the contract? No.**
The contract defines `env` as the sorted multiset of `(tool, input JSON, str(state.output))` — error text is not in the multiset. A1's choice to compare `str(state.get("output"))` (=`"None"` for error events) and not the error text is exactly the contract's rule, so no contract-counted difference is dropped. The case that matters — a `completed` event on one arm vs an `error` event on the other at the same `gen` position — IS counted: `(tool, input, "X")` ≠ `(tool, input, "None")` → `environment`. The golden counts (s1 18/24/1/0, s2 17/25/1/0) reproduce, confirming the 154 real error events parse under the new check.

## Step 1–3 output

Confirmed unchanged. The `--evidence-ref`-without-`--panel` refusal and all step-4 logic sit behind `if evidence_ref is None: return rec` (`p426_signals.py:871`); the no-ref path returns the step-3 record untouched. `render_md`'s dispatch only adds `STEP4_VERSION`, which never matches a step-1–3 header. The implementer's byte-identity check against the committed step-3 sheet (`noref == committed`) and `test_golden_no_ref_path_reproduces_step3_sheet` back this.

## Anything else the diff breaks or leaves failing

**M1 — minor (hazard, confirmed).** `benchmark/bench/p426_signals_divergence.py:43` requires `isinstance(state.get("input"), dict)`. The contract's `env`/`gen` rule is `JSON of state.input with sorted keys`, which `json.dumps` accepts for any JSON value, not only objects. A future tool event with `state.input: null` or a list (no-args or array-arg tool) would refuse the whole sheet rather than parse. No current evidence triggers this (golden counts reproduce; the implementer reports all 15,865 completed events carry object `input`), so it does not break the present sheet. The safe direction (refuse > misclassify) is consistent with the disposition, but it is stricter than the contract's literal rule. *Proposed change:* accept any JSON value for `state.input` (drop the `isinstance(..., dict)` check, keep the "key present" requirement), or record the tightening as a contract amendment.

**M2 — minor (hazard, confirmed).** `benchmark/bench/p426_signals_divergence.py:39-41` requires `status in TERMINAL` ("completed","error"). The contract says "keep `type` `text` and `tool_use`" — it does not filter `tool_use` by terminal status. A future evidence stream containing non-terminal (streaming/partial) `tool_use` events would refuse. The current evidence has only terminal events (implementer's count: 15,865 completed + 154 error), so nothing breaks now. Same safe-direction reasoning as M1. *Proposed change:* either keep non-terminal events out of the multiset explicitly (skip, not refuse) with a contract note, or record the terminal-only restriction as a contract amendment.

**M3 — minor (test weakness, hypothesis).** `test_p613s4_fixes.py:196`'s final assertion `assert "A7-s1" in text[: text.index("## ")] or "A7-s1" in text` is satisfied by any occurrence of the substring `A7-s1` anywhere in the sheet (the `or` clause is a superset of the first), so it does not pin that the missing-section is named in the header/status area. The three specific assertions above it (`missing`, `ready`, `divergence.complete`) carry the check, so the finding is still verified; only this trailing line is vacuous. *Proposed change:* drop the `or` clause and assert `"A7-s1" in text[: text.index("## ")]` (the header block), or remove the line as redundant.

No blocker or major found. The four repairs resolve all six findings without weakening another protection; the no-ref path is byte-identical; and A1 does not let a contract-counted difference escape.
