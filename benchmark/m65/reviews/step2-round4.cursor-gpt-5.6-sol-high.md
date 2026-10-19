S2 — RESOLVED — satisfiability and Cargo-compatible wildcard handling are correct.

S3 — RESOLVED — cache identity covers current pins, closure, policy, locks, and item bytes.

S5 — RESOLVED — malformed wildcard, prerelease, build, and leading-zero forms are rejected correctly.

S6 — RESOLVED — tracked recursive locks and crates.io registry versions, including build metadata, are verified.

S8 — RESOLVED — current pins and the dynamically loaded verifier now participate in validation.

S9 — RESOLVED — non-reference files reach the allow-list audit; declared files are post-checked.

S11 — RESOLVED — invalid repeated-major wildcards and wildcard metadata are rejected; `1.*.*` and `1.x.x` remain accepted.

S12 — RESOLVED — full lock versions are retained and build metadata is ignored only for precedence.

S13 — RESOLVED — undeclared directories fail visibly instead of being silently dropped.

S14 — RESOLVED — `load()` compares embedded image, corpus, and lock identity against current pins.

S15 — RESOLVED — the executed corpus verifier is the verifier hashed into freezer identity.

S16 — RESOLVED — per-item before/after hashes and final corpus/hash verification prevent mixed persistent mutations from being published.

New findings — none.

VERDICT: CLEARED

[exited with code 0]
