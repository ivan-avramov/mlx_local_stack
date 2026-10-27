P1  
Location: `docs/specs/p426-t3-serving-build.md:17,80–87,119`  
Severity: blocker  
Evidence: confirmed  
Problem: The specification declares C218 settled, then requires an ON overlay while leaving `main_models.yaml` unchanged. C218 and `AGENTS.md` require each arm to be a stack commit served from its committed registry.  
Concrete failure scenario: Wave 1 reruns on S′ using `registry-on.s2.yaml`; the resulting ON evidence measures an overlay, not the configuration that may ship.  
Proposed change: Define committed OFF and ON arm commits/worktrees and make the sequencer select the appropriate worktree and its committed `main_models.yaml`. Remove the overlay path from T3.

P2  
Location: `docs/specs/p426-t3-serving-build.md:74–77,85–91,103–106`  
Severity: major  
Evidence: confirmed  
Problem: `build: "s2"` is checked only against `--build s2`; it is not bound to S′’s required pins. Current K2 checks merely prove the running tree equals whatever pins the record contains.  
Concrete failure scenario: A stack commit containing the new label tooling but retaining old serving gitlinks writes a self-consistent `frozen.s2.json`. Every check passes and old build S produces evidence labelled S′.  
Proposed change: Bind `s2` to `mlx_vlm=c688e722`, `mlx_serve=e6a7a5a`, mlx 0.32.4, and the accepted T3 stack commit through a checked freeze tool or immutable expected-build record. Add a wrong-but-self-consistent-build refusal test.

P3  
Location: `docs/specs/p426-t3-serving-build.md:68–88,103–107`; `benchmark/bench/p426_wave1.py:148–179`  
Severity: major  
Evidence: confirmed  
Problem: The namespace design omits the caller-controlled sequencer `--out` directory, including `receipts/`, stdout files, and `sequence.log`.  
Concrete failure scenario: Running `--build s2` with S’s existing `--out` appends to S’s `sequence.log`; S2’s harvested run log then contains both campaigns, and S’s scratch evidence is modified.  
Proposed change: Derive or validate a build-specific out root, such as `<workdir>/p426/wave1.<build>`, while preserving the legacy path for `s`. Test S and S2 sequentially with the same parent tree and assert every S byte is unchanged.

P4  
Location: `docs/specs/p426-t3-serving-build.md:54–58,110–119`; `benchmark/bench/local_gate.py:32–34,226–245`; `review_material/fork-main-c688e722/.upstream-sync-ref`  
Severity: major  
Evidence: confirmed  
Problem: The specification does not account for the stack’s local gate being incompatible with S′’s fork. The gate reads the removed `.github/workflows/upstream-parity.yml`, while S′ stores the ref in `.upstream-sync-ref`; it also runs eight audits while S′’s gate has nine, adding `check_upstream_test_copies.py`. The stack suite does not exercise this real integration.  
Concrete failure scenario: `bench.local_gate run --repo mlx-vlm --sha c688e722` fails before creating a receipt because the workflow file does not exist, so the new stack cannot pass its release gate.  
Proposed change: Specify and test the local-gate adaptation, including `.upstream-sync-ref`, all nine audits, and a real PASS gate receipt for each S′ pin.

P5  
Location: `docs/specs/p426-t3-serving-build.md:22–28,54–58,110–118`; C236 in `docs/open-questions.md:20`  
Severity: major  
Evidence: confirmed  
Problem: C236 requires a smoke, but the acceptance criteria require only imports and test suites. A2’s running provisional rehearsal is an assumption, not acceptance evidence for the accepted T3 commit.  
Concrete failure scenario: All unit tests and imports pass, but the accepted committed registry cannot start a router, load the P426 target, or complete a request on S′. T3 is accepted without demonstrating its serving goal.  
Proposed change: Add a smoke on the accepted committed S′ build that starts the shipped path, loads the P426 entry in both required predictor states, completes requests, verifies identity/engagement, and tears down cleanly.

P6  
Location: `docs/specs/p426-t3-serving-build.md:110–117`; `pyproject.toml:1–18`; `review_material/uv.lock.relocked:999–1055`  
Severity: major  
Evidence: confirmed  
Problem: Acceptance criterion 3 requires the fork suites in the stack’s `.venv`, but the root project does not install the fork’s `test` extra or pytest. The relocked serving environment records those requirements only behind `extra == "test"`.  
Concrete failure scenario: After the required `uv sync --frozen`, `.venv/bin/python -m pytest` fails because pytest and other fork gate dependencies are absent.  
Proposed change: Define a reproducible test-environment command and dependencies, or require the real fork local gate instead. Keep the serving `.venv` acceptance separate from the test environment.

P7  
Location: `docs/specs/p426-t3-serving-build.md:1–4`; C236 in `docs/open-questions.md:20`  
Scope request  
Evidence: confirmed  
Problem: The specification upgrades T3 from the operator-set “four-eyes light” process to “four-eyes STRICT” without a new ruling.  
Concrete failure scenario: Implementation incurs the stricter workflow despite the settled scope.  
Proposed change: Restore “four-eyes light,” or obtain an explicit operator ruling for STRICT.
