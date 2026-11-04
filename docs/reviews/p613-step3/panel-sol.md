P1 — Location: `benchmark/bench/p426_panel.py:692-738`, `benchmark/bench/p426_signals.py:959-1058`  
Severity: major  
Evidence: confirmed, traced in source.  
Problem: `FROZEN.json` is not itself sealed. `check_frozen()` trusts its current `files`, judges and lengths; the sheet merely reports its current hash.  
Failure scenario: alter `items[*].len_on/len_off` after verdicts. Packet checks still pass, but the length-adjusted headline changes.  
Proposed change: bind every verdict to the current `FROZEN.json` SHA and validate it at ingestion; independently cross-check frozen judges/items/slots against `manifest.jsonl`. Add FROZEN-tampering tests.

P2 — Location: `benchmark/bench/p426_panel.py:160-218`  
Severity: major  
Evidence: confirmed, traced in source.  
Problem: ingestion validates only packet/attachment hashes. It trusts verdict-supplied `judge`, `family`, `model`, `client`, `client_version`, and `prompt_sha`. `seal_verdicts()` also skips any verdict already containing `packet_sha`.  
Failure scenario: copy or pre-seal a verdict with the correct packet hash but a different judge/model provenance; it can satisfy `admit()` and support a false two-family claim.  
Proposed change: derive identity and prompt metadata from FROZEN/manifest, reject mismatches, always normalize bare verdicts, and require the frozen-set SHA. Tests currently cover only a wrong packet hash.

P3 — Location: `benchmark/bench/p426_panel.py:221-255`  
Severity: major  
Evidence: confirmed, traced in source.  
Problem: retries are zero only within one invocation. A failed packet receives `.failed.txt`, but the next `a7-cursor` invocation calls the judge again because only existing verdicts are skipped.  
Failure scenario: repeatedly resume failed calls until enough verdicts exist to cross the `<5` threshold or change Holm membership.  
Proposed change: write an attempt marker before each call and permanently skip attempted failures. Add a second-run test after failures.

P4 — Location: `benchmark/bench/p426_panel.py:133-147, 657-659`; `benchmark/bench/judge_pairwise.py:76-115`; `benchmark/bench/p426_signals.py:1013-1019`  
Severity: major  
Evidence: confirmed, reproduced read-only on all 21 committed packet items.  
Problem: `len_off/len_on` measure raw diffs, while judges see `strip_model_names()` output. All 42 real arm responses changed, shortening by 1–10 characters. The helper also silently redacts model names instead of making `leak_problems` refuse. Thus the length adjustment uses text different from the judged packet.  
Failure scenario: short or whitespace-heavy diffs materially change the length ratio and adjusted result; model-identifying source is silently rewritten.  
Proposed change: preflight raw packets for leaks, refuse on any hit, and export the exact unmodified diff; otherwise calculate lengths from the exact rendered packet. Frozen tests miss real blank-context-line normalization, although their model-leak case should catch the silent redaction.

P5 — Location: `benchmark/bench/p426_signals.py:1199-1222`; `.p613-material/frozen-tests/test_p613s3_signals.py:280-283`  
Severity: major  
Evidence: confirmed; the implementer reproduced 12 committed step-2 failures.  
Problem: `all` refuses without `--panel`, violating E1 and changing step-2 CLI behavior. The frozen step-3 test incorrectly requires this regression.  
Failure scenario: ordinary step-2 regeneration now exits 2 and writes no outputs.  
Proposed change: make `--panel` optional and preserve byte-identical step-2 output when absent; replace the contradictory frozen test.

P6 — Location: `benchmark/bench/p426_panel.py:663-681`; `benchmark/bench/p426_signals.py:991-1001`; `.p613-material/frozen-tests/test_p613s3_golden.py:84-99`  
Severity: minor  
Evidence: confirmed against E3.  
Problem: A1 counts all 100 keys as panel-eligible, producing Wave-1 identity 166. E3 requires 96 both-correct A1 keys, four “not both correct” exclusions, and total 162. A non-identical both-wrong A1 key would incorrectly refuse the panel.  
Failure scenario: the sheet misreports eligibility and frozen counts, though current statistical membership remains unchanged.  
Proposed change: apply A1’s both-correct selection before identity checking and report the four exclusions. Update golden tests from 166 to 162.

P7 — Location: `benchmark/bench/p426_panel.py:743-805`  
Severity: major  
Evidence: confirmed, traced in source.  
Problem: `--b8` and `--universe` may name arbitrary local files. Their hashes are recorded but never verified against committed authoritative bytes. A modified B8 can retain the valid input-hash map while changing accepted/identical decisions.  
Failure scenario: supply a modified universe plus matching local start tree to alter task text or baseline diffs, or a modified B8 to alter packet membership; export and later ingestion succeed.  
Proposed change: in the production CLI, require and verify the committed repository paths against an immutable git ref or registered expected SHA. Keep injectable low-level interfaces for hermetic tests.

P8 — Location: `benchmark/bench/p426_panel.py:160-177`  
Severity: major  
Evidence: confirmed, traced in source.  
Problem: malformed Claude verdict JSON raises from `json.loads()` and aborts sealing instead of becoming one missing verdict. Valid JSON with an invalid choice is sealed as `choice: null` but not counted as unparseable.  
Failure scenario: one malformed judge response prevents later valid verdicts from being sealed and repeatedly crashes `a7-seal`.  
Proposed change: handle each file independently; invalid output gets a permanent failed marker and counts as missing/unparseable. Add malformed and invalid-choice Claude tests.

P9 — Location: `benchmark/bench/p426_panel.py:626-659`; `.p613-material/frozen-tests/test_p613s3_export.py:168-174`  
Severity: minor  
Evidence: confirmed.  
Problem: the public `a7_packet` signature adds `_ctx` and `_top_ref`, contrary to the specified interface and frozen signature test.  
Failure scenario: interface-introspection consumers and the frozen test fail despite normal seven-argument calls working.  
Proposed change: retain the exact public wrapper and move cached context parameters into a private helper.
