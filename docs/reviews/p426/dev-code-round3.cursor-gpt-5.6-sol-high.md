F3 — CLOSED — `_span` now handles explicit `name` keys in any order and quoted/commented values. Duplicate marker comments remain inert, missing markers are inserted safely, and the resulting settings are verified against the fixture.

H1 — CLOSED — `benchmark/bench/p426_overlay.py:20-35` loads the frozen file directly under a path-derived module name and verifies `__file__`; a cached foreign package module cannot be reused.

H2 — CLOSED — `benchmark/bench/p426_leg.py:60-141` strictly parses both registries, rejects duplicate keys and type changes, pins all three ON values, preserves every other setting, and limits textual additions/removals as claimed.

I1 — MEDIUM — `dev/p369_phase2/registry_states.py:120-131`  
Problem: `_span()` finds an entry only through an explicit raw `name` key. C203 permits YAML merges, and `classify()` accepts a models item expressed solely through `<<:` whose merged mapping contains `name`, but `_span()` sees only the merge key.  
Failure scenario: A settings-identical item written as `- <<:` followed by the original mapping classifies as a valid OFF state, then `overlay_on()` raises `<entry>: 0 registry blocks`, blocking overlay generation.  
Fix: Match names from the constructed/flattened models sequence and use the corresponding composed item’s source marks. Add a merge-only model-item overlay test.

VERDICT: DISAGREE I1