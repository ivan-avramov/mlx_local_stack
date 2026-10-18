S1 — HIGH — `benchmark/bench/tg2_materialize.py:163`  
Failure: `prepare_tree()` excludes only `.docs` and `.meta`; five valid items retain `.approaches/**`, including solution snippets. Those files are recorded in `tg2_universe.json` and are model-visible.  
Fix: exclude `.approaches`, add corpus-backed leakage tests, then regenerate universe/draw artifacts and sidecars.

S2 — HIGH — `benchmark/bench/tg2_grade.py:109-128`  
Failure: the P367 structural check validates crate names and TOML forms but never checks whether version requirements are satisfiable by vendored versions. Tests explicitly classify `regex = "99"` as compile failure (`test_tg2_grade.py:1952-1963`), contrary to P367’s tamper requirement.  
Fix: validate Cargo semver requirements against exact vendored versions during tamper checking; update unit and Docker tests.

S3 — HIGH — `benchmark/m65/tg2_universe.py:220-228`  
Failure: resumable records are reused without validating corpus SHA, image ID, grader/materializer version, or policy fingerprint. `assemble()` then stamps cached results with current metadata, allowing stale runs to masquerade as fresh final-image evidence.  
Fix: fingerprint cache entries and reject mismatches; regenerate artifacts from a clean or validated cache.

S4 — MEDIUM — `benchmark/bench/tg2_materialize.py:113-149,163`  
Failure: Rust, C++, and JavaScript example paths are not required to reside under excluded `.meta`; a future pinned corpus could place a configured example elsewhere and copy the exact reference into the prepared tree. Current frozen mappings happen to be under `.meta`.  
Fix: require reference sources under an excluded root or explicitly exclude every configured example and assert its absence.

Verified otherwise:
- Frozen universe/draw are canonical; sidecars match.
- Draw recomputes byte-equivalently with seed 6501 and nested 10/20 prefixes.
- Artifact invariants show 149 valid, three justified baseline exclusions, 3 reference/2 stub runs, stable leaves, positive baselines, and exactly two declared JS optional leaves.
- Offline lock generation uses `--network none`, `--offline`, image-vendored sources, and no shared mutable Cargo cache.
- Cleanup rechecks the registered 128-bit nonce and leaves missing/different-nonce objects untouched.
- Non-blocking: leg-start expected-SHA pinning belongs to build step 3; no leg runner exists yet.

VERDICT: CLEARED AFTER FIXES S1 S2 S3 S4
