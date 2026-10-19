S1 — RESOLVED — `.approaches/.articles` are excluded. Pinned-corpus audit found no dropped legitimate stub directory and no actual solution leak among the 18 `STUB_SCAFFOLDING` pairs.

S2 — PARTIALLY — Stable caret (`0.x`/`0.0.x` included), tilde, wildcard, and comma-intersection math is correct; S5–S6 remain.

S3 — PARTIALLY — Cache mismatches now fail closed, but S6–S8 leave the fingerprint incomplete.

S4 — RESOLVED — Configured examples must be beneath excluded roots and are post-copy checked absent (`benchmark/bench/tg2_materialize.py:123-129,186-191`).

S5 — MEDIUM — `benchmark/bench/tg2_grade.py:107-155` — The custom parser accepts Cargo-invalid leading-zero requirements such as `"01"` and rejects Cargo-valid prerelease/build syntax. This misclassifies invalid manifests as compile failures or valid ones as tampering. Fix: use Cargo-compatible semver parsing and parity tests.

S6 — HIGH — `benchmark/bench/tg2_grade.py:92-103`; `benchmark/m65/tg2_universe.py:29-46` — Vendored versions come from mutable, shallow `*/Cargo.lock` globbing, not the verified union of committed locks; their hash is absent from the fingerprint. Lock drift can approve a version absent from the image while nested locks are omitted. Fix: canonical tracked `rglob` manifest, verify against `IMAGE_ID`’s lock hash, and fingerprint it.

S7 — HIGH — `benchmark/m65/tg2_universe.py:303-309` — Corpus identity is only `git HEAD`; dirty target-language files or a clean wrong commit can be frozen under misleading provenance against an image built from another corpus. Fix: require the pinned/image-recorded commit and clean relevant subtrees, or fingerprint their bytes.

S8 — HIGH — `benchmark/m65/tg2_universe.py:29-46,186-199` — No freezer implementation identity is fingerprinted; the hard-coded 4 GiB memory limit is omitted, and `load()` does not validate the embedded policy fingerprint. Freeze-logic or policy changes can reuse/accept stale evidence. Fix: hash/version the freeze closure, include memory limits, and validate policy on load.

S9 — MEDIUM — `benchmark/bench/tg2_materialize.py:17-21,171-184` — The claimed allow-list keeps every top-level file and every file inside an allowed top-level directory. An undisclosed `answer.*` can survive outside configured example roots. Fix: explicit audited per-language/per-item scaffold paths; fail on unknown files.

S10 — MEDIUM — `benchmark/bench/tests/test_tg2_materialize.py:267-349` — References shorter than 200 characters are invisible, while an allowed pair passes any overlap below 50%. Eleven current short exact overlaps are benign scaffolding, but a short or partial solution leak would pass. Fix: adaptive/exact matching and content-addressed exceptions keyed by reference path.

VERDICT: CLEARED AFTER FIXES S5 S6 S7 S8 S9 S10

[exited with code 0]
