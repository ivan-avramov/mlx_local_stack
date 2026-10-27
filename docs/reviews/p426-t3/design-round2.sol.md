P1 — Location: §4 “Expected build per label”; severity: blocker; evidence: confirmed.  
Problem: `production_ref = mlx_vlm` makes both equal `c688e722…`. The fork’s `resolve_production_ref()` requires the production ref to be a strict ancestor of the reviewed head, so every M1 leg refuses before execution.  
Failure scenario: any S′ M1 smoke receives `--reviewed-head c688e722… --production-ref c688e722…` and returns NOT_STARTED.  
Proposed change: pin `production_ref` to `b26fa7c9faf23bc3167db3419504ef0b2b82a8e6`, the strict parent whose non-test `mlx_vlm` tree is identical to `c688e722…`, and test this real preflight.

P2 — Location: Settled C218/P472 and §4 “Arms as commits”; severity: blocker; evidence: confirmed; settled-constraint conflict.  
Problem: the pinned fork cannot run M1 ON without creating an overlay file. `qualify.py` calls `overlay_registry()`, writes `overlay-<entry>.yaml`, and launches against that path even when the committed ON registry is already ON. This contradicts “no overlay files” and “reads the ON registry from the ON commit,” while T3 forbids changing the fork.  
Failure scenario: an ON M1 leg either uses the generated overlay and violates C218, or refuses to use it and cannot run.  
Proposed change: obtain an explicit operator exemption for this byte-identical M1 materialization, or expand scope to change and repin the fork so already-ON registries are used directly from committed `main_models.yaml`.

P3 — Location: §4 “Arms as commits” and “The frozen record”; severity: major; evidence: confirmed.  
Problem: “tree clean” does not define whether untracked files count. Every non-M1 leg writes new files under deliberately tracked `benchmark/results/`; plain `git status --porcelain` therefore marks the arm dirty at exit. Existing K2 intentionally uses `--untracked-files=no`.  
Failure scenario: a correct first S′ leg creates its rows, then the exit K2 check invalidates it for build drift; later resume validation also refuses.  
Proposed change: define cleanliness explicitly as no tracked changes (`git status --porcelain --untracked-files=no`), with generated-output freshness enforced separately.

P4 — Location: §4 “Arms as commits”; severity: major; evidence: confirmed.  
Problem: “diff is exactly the restore paths” constrains the path set, but only specifies exact content for `main_models.yaml`; arbitrary additional changes inside `test_opencode_probe_seeding.py` can pass a literal path-based assertion. That fails C218’s exact-restore protection.  
Failure scenario: ON also deletes or weakens another seeding test in that file; the two changed paths remain exactly the listed paths, so the arm is accepted.  
Proposed change: require an exact patch-level assertion: only the three registry keys and note, plus precisely §11’s `per_query`→`joint_v1` and source-`registry` test changes, with no other hunks or metadata changes.
