F1 — CLOSED — `dev/p400_perf_probe.py:346-349`; `benchmark/bench/p426_overlay.py:54-57`. Both consumers now read bytes and decode UTF-8 explicitly, preserving CR for the strict parser.

F2 — CLOSED — `dev/p369_phase2/registry_states.py:181-189`. `_same` recursively requires identical types while preserving numeric equivalence within the same type.

F3 — OPEN — HIGH — `dev/p369_phase2/registry_states.py:101-110,241-249`. `_span` now handles quoted/commented name values, but still requires `name` as the first mapping key. It also rejects multiple matching commented markers, although comments must never block. Reordering `name` after `hf_path`, or duplicating a matching marker comment, remains settings-equivalent under `classify()` but makes `overlay_on()` fail. Locate sequence-item spans from YAML source marks and treat comments as inert, inserting the canonical active lines without consuming ambiguous comments. Add reordered-key and duplicate-comment tests.

F4 — CLOSED — `dev/p369_phase2/registry_states.py:141-155`. Merge-tag keys are excluded from explicit duplicate detection and resolved by `SafeLoader`; literal duplicate keys still refuse.

H1 — MEDIUM — `benchmark/bench/p426_overlay.py:21-31`. `sys.path` insertion does not override an existing `p369_phase2.registry_states` entry in `sys.modules`. A process that previously imported the module from another checkout can therefore generate an overlay using stale rules while attributing it to the frozen build. Load the exact file under a unique module name, verify its resolved path, and test with a pre-populated module cache.

H2 — MEDIUM — `benchmark/bench/p426_leg.py:51-85`. The purported independent delta check uses type-blind Python equality, does not validate the three added values, and verifies only the number—not the identity—of changed lines. An alternate cached rule could restore `draft_kind`, `draft_model`, or `mtp_verify_scan` with wrong values yet still produce the expected six changed lines and pass. Use strict, type-aware parsing and compare both arms against pinned expected key/value mappings and the exact permitted textual delta.

No new B7 or P429 finding.

VERDICT: DISAGREE F3 H1 H2