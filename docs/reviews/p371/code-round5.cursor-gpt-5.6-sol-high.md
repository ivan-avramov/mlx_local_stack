F14 — partially resolved — F23 still breaks crash-resume hydration (`benchmark/bench/chain_core.py:1661-1703`).

F15 — partially resolved — repointing works, but F23 can strand abort evidence (`benchmark/bench/chain_core.py:1661-1703`).

F16 — resolved.

F17 — partially resolved — completion flag and move ordering work; F23 prevents fully idempotent recovery (`benchmark/bench/chain_core.py:1661-1703`).

F18 — partially resolved — F24 permits unproven attribution (`benchmark/bench/chain_core.py:1604-1610`).

F20 — partially resolved — `manifest_hydrated` is correct, but extraction publication is not crash-atomic (`benchmark/bench/web_evidence.py:99-106`).

F21 — partially resolved — expected-prefix comparison normalizes away the row language (`benchmark/bench/chain_core.py:1604-1610`).

F22 — resolved.

F23 — medium — `benchmark/bench/chain_core.py:1661-1703`; `benchmark/bench/web_evidence.py:99-106` — process death after exclusive destination creation but before complete write leaves a partial file; resume re-extracts to `.verify`, detects inequality, and permanently aborts hydration. Fix: write/fsync a temporary file and atomically publish it; test interruption after creation and partial write.

F24 — medium — `benchmark/bench/chain_core.py:1604-1610`; `benchmark/bench/chain_rows.py:97-100` — `slot_for` maps `go/a` onto a Python slot when the bare item matches, falsely proving a foreign/wrong-language prefix and attributing unavailable evidence to the next slot. Fix: compare exact expected row IDs, including language, before deriving the slot.

F25 — low — `benchmark/bench/chain_core.py:1604-1606`; `benchmark/bench/chain_rows.py:119-121` — a valid JSON row with a non-string `id` raises unexpectedly instead of producing `slot:null, attribution unproven`. Fix: require string IDs or catch the schema failure. Residual hardening.

Merge blockers: F23, F24. F25 and open P383 can be tracked; green full-suite and §8 lead verification remain procedural gates.

VERDICT: NOT CLEARED F23 F24

[exited with code 0]
