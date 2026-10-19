S2 — PARTIALLY — core caret/tilde/intersection math is correct; S11–S12 remain.

S3 — PARTIALLY — code, policy, lock and item-byte fingerprints exist; S14–S16 remain.

S5 — PARTIALLY — leading-zero and prerelease/build handling fixed; invalid wildcard forms remain (`benchmark/bench/tg2_grade.py:203-223`).

S6 — PARTIALLY — recursive tracked lock-set and image-pin verification fixed; the extracted union is incomplete (`benchmark/bench/tg2_grade.py:153`).

S7 — RESOLVED — pinned commit, clean target subtrees and per-item bytes are checked.

S8 — PARTIALLY — freezer closure, resource policy and embedded-policy validation fixed; current pins and dynamic verifier identity remain unchecked (`benchmark/m65/tg2_universe.py:66-69,238-240`).

S9 — PARTIALLY — copied files are allow-listed, but unknown top-level directories are silently removed before auditing (`benchmark/bench/tg2_materialize.py:205-209`).

S10 — RESOLVED — all 26 content-addressed exceptions are benign scaffolding, not solution leaks. The only references below the 40-character floor are three identical Java editor enums.

S11 — MEDIUM — `benchmark/bench/tg2_grade.py:203-223` — Cargo-invalid `*.*` is accepted as “any”; wildcard prerelease forms such as `1.2.*-rc` also pass parsing. They become compile failures rather than tampering. Reject unsupported major-wildcard repetition and prerelease/build metadata on wildcard components; add Cargo-parity cases.

S12 — LOW — `benchmark/bench/tg2_grade.py:153` — vendored versions exclude valid lock versions containing build metadata; committed `wasi 0.11.1+wasi-snapshot-preview1` is already omitted. Parse lock versions with `_VERSION`, ignore build metadata for matching, and require registry sources.

S13 — MEDIUM — `benchmark/bench/tg2_materialize.py:205-209,234-240` — an undeclared top-level directory is dropped silently, so a legitimate future fixture can disappear instead of producing the required allow-list failure. Copy every non-reference root, audit unknown files, and post-check every declared file remains present.

S14 — HIGH — `benchmark/m65/tg2_universe.py:238-240` — `load()` validates embedded image/corpus IDs against themselves. After `IMAGE_ID` or its corpus pin changes, an old universe can still load. Compare against current `pinned_image_id()` and `image_record()["polyglot_sha"]`.

S15 — MEDIUM — `benchmark/m65/tg2_universe.py:42-45,66-69` — dynamically loaded `verify_corpus.py` is absent from `freezer_sha256`; changed corpus-admission semantics can reuse old cache identity. Hash it as a data dependency or import it statically.

S16 — HIGH — `benchmark/m65/tg2_universe.py:301-322,348-359` — the 71-minute freeze verifies corpus cleanliness only at start and records each item hash after grading. Concurrent mutation can produce mixed evidence under pinned provenance. Hash each item before and after freezing, revalidate all hashes and corpus cleanliness before assembly.

VERDICT: CLEARED AFTER FIXES S11 S12 S13 S14 S15 S16

[exited with code 0]
