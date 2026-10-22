Round 1 of 3.

F1 — HIGH — `dev/p400_perf_probe.py:485,574`; `benchmark/bench/p426_overlay.py:56`  
Problem: These consumers use `Path.read_text()`, which performs universal-newline conversion. This removes `\r` before `registry_states.parse()` can enforce C203’s raw no-CR rule.  
Failure scenario: A CRLF `main_models.yaml` is normalized to LF, classified as valid, and used to build an overlay; P400/P426 proceeds despite the mandatory raw refusal.  
Fix: Read bytes and decode UTF-8 explicitly, as `orchestrate.read_registry()` does. Add consumer-level CRLF refusal tests.

F2 — MEDIUM — `dev/p369_phase2/registry_states.py:179-193`  
Problem: Configuration equality uses ordinary Python equality, which is not type-sensitive: `False == 0`, `True == 1`, and `0 == 0.0`. Thus YAML type changes can classify as an accepted state.  
Failure scenario: `kv_bits: 0` → `kv_bits: false`, or `lazy_prompt_embeddings: true` → `1`, passes classification although the YAML setting type changed; type-strict downstream validation may then behave differently or refuse later.  
Fix: Use recursive type-aware equality, preserving lexical numeric equivalence such as `0.40` versus `0.4`. Test bool/int/float/string and explicit-tag variants.

F3 — HIGH — `dev/p369_phase2/registry_states.py:101-107,217-227`  
Problem: `classify()` accepts settings-equivalent formatting and comments, but `overlay_on()` relies on exact raw shapes. `_span()` requires an unquoted, comment-free `  - name: <entry>` line, and commented MTP matching validates the expected value only when multiple candidates exist.  
Failure scenario: Adding a trailing comment to an entry’s `name` line—or quoting/reordering that key—keeps identical settings but makes the overlay refuse, violating C203’s “comments must never block” ruling. Separately, if the real commented MTP marker is removed and a historical `# draft_kind: suffix` is the sole candidate, the overlay overwrites that unrelated note and succeeds.  
Fix: Locate spans using YAML token/source marks or a syntax-tolerant mapping, always match candidate values, and deterministically insert missing fixture MTP lines. Test name-line comments, quoting/key order, missing markers, and a sole historical suffix note.

F4 — MEDIUM — `dev/p369_phase2/registry_states.py:141-146`  
Problem: The duplicate-key constructor inspects merge-tag keys before PyYAML flattens them, so valid YAML merge keys fail with “could not determine a constructor for … merge.” This rejects a settings-preserving YAML feature that `SafeLoader` normally supports.  
Failure scenario: Identical generation defaults expressed through an anchor and `<<: *defaults` refuse the campaign despite resolving to the pinned settings. Existing tests cover duplicate literal keys but not merges or semantic aliases.  
Fix: Check duplicate explicit keys while handling merge tags according to YAML semantics, then flatten/construct normally. Add equivalent anchor/alias/merge classification tests.

No B7 or P429 correctness finding: OFF is checked against the committed MTP-OFF state and runtime evidence, while `_exit(0)` occurs only after the closed result write and successful leg return.

VERDICT: DISAGREE F1 F2 F3 F4