# P369 phase-2 harness — Cursor gpt-5.6-sol-high CODE review round 3 (fork `p369-mtp` `dec95d95..a004a922`, incl. the P387 code review, 2026-10-19)

Prompt: `code-round3.prompt-head.md` + the round-2 output + P394 + the P387 build note v2 + `git diff dec95d95..a004a922` + plan v7; workspace `../mlx-vlm` at `24551869`. Output verbatim:

P1 — Verification

Read-only review of `dec95d95..a004a922`. Tests were not run.

- `4e6d0e03..a004a922` has no production diff under `mlx_vlm` excluding tests.
- The fixture payload is byte-identical to `7021bdbb:main_models.yaml`, SHA-256 `1d07c9dd0ebf5058b526e1d78fee2a88f8e92976323ddf0e8d5503dcaa18253d`.
- The generated interim matches the live five-line C177 change.

P2 — Round-2 findings

H2 — RESOLVED  
`telemetry.py:147-182,272-295,414-426` reproduces the production tuple predicate at `quantized_verifier.py:1790-1807` and rejects eligible groups that do not use `quantized_linears_optimized`. The tuple-decline regression test exercises the intended case.

H6 — RESOLVED  
`orchestrate.py:384-418,422-456` excludes digest-invalid E7a requests and censors digest-invalid E7b sessions. Under P394, one valid digest-bound observation is sufficient; invalid, unengaged, and censored observations remain disclosed. This supersedes round 2’s stricter “any mismatch prevents PASS” recommendation.

H8 — PARTIALLY RESOLVED — MEDIUM  
Timeout decisions are written before signalling at `orchestrate.py:786-793`, and cleanup now follows the persisted request and `after` heartbeat at `worker.py:92-101`. H20 remains: those two writes are not atomic together, permitting a completed request to be censored.

H9 — PARTIALLY RESOLVED — HIGH  
The binding was substantially extended at `orchestrate.py:210-258,1043-1095`, and the fork tree is checked before launches. Four material gaps remain:

- `reviewed_head_problems()` accepts any matching prefix, including one character, at `orchestrate.py:261-272`; it does not establish that the supplied value names the reviewed commit.
- `hf_hub_cache()` ignores `XDG_CACHE_HOME` at `orchestrate.py:281-289`, although it is passed to workers at line 53 and Hugging Face uses it when `HF_HOME` is absent.
- The worker checks only a re-resolved revision-directory basename after model loading at `worker.py:56-78,850-858`. Same-revision file mutation is undetected despite the manifest’s file hashes.
- `stack_bench.tree` hashes `HEAD:benchmark/bench` at `orchestrate.py:1063-1070`, while reconstruction imports the mutable worktree at lines 947-985. Dirty or transient benchmark changes are therefore not bound.

Scenario: `--reviewed-head a` authorizes an unreviewed HEAD beginning with `a`; or the orchestrator hashes the default cache while the worker loads the XDG cache; or a safetensors blob/bench builder changes without changing the recorded revision/tree. The campaign can PASS with evidence different from its binding.

Fix: resolve `--reviewed-head^{commit}` and compare its full object ID; implement Hugging Face’s XDG precedence; capture production-resolved snapshot paths and recheck complete hashes; require a clean stack benchmark tree or hash the actual files used.

H10 — RESOLVED  
`overall_status()` at `orchestrate.py:473-488` requires every pick to have E1c PASS, E2 PASS, E7a OBSERVED, and E7b OBSERVED. Missing coverage now yields `NOT_PASS`.

H12 — PARTIALLY RESOLVED — MEDIUM  
The intentional deferral remains. `.github/workflows/tests.yml:49` runs pytest without `MLX_REQUIRE_P369_ORACLE=1`, and checkout remains shallow by default. This matches P394’s decision to land CI enablement with the fork-main merge, but CI does not yet gate the oracle.

H14 — RESOLVED  
`orchestrate.py:1541-1568` holds `fcntl.flock` on a stable descriptor through campaign execution, releases it in `finally`, and never unlinks the pathname. Descriptor lifetime is correct. H21 is a separate lock-location defect.

H15 — RESOLVED  
`orchestrate.py:342-361,492-535` implements ABORT > FAIL > INCOMPLETE > PASS and cleanly separates neutrality failures from invalid evidence.

H16 — PARTIALLY RESOLVED — MEDIUM  
E7a and E7b are persisted separately at `orchestrate.py:1455-1461`, and ordinary errors inside the monitor block record `HARNESS_ERROR`. H23 remains for errors outside that block and termination.

H17 — PARTIALLY RESOLVED — MEDIUM  
Workers start as process-group leaders and same-group descendants receive TERM/KILL at `orchestrate.py:700-744,831-854`. H22 identifies launch and escaped-descendant gaps; H24 identifies orphan-unsafe test cleanup.

H18 — RESOLVED  
`orchestrate.py:422-456` requires every E7b turn to have positive MTP rounds or the documented first-token-terminal exception, plus a passing kernel verdict and continuity.

P3 — P387

K1 — PASS  
Ordinary consumers use `certified_registry()` at `test_mtp_verify_scan.py:1764-1770`; `deployed_sampling()` uses it at `test_mtp_exactness.py:52-57`. Repository-wide search found live registry access only in the two opt-in tests.

K2 — NOT FULLY MET  
Direct classifier equality is strict at `test_mtp_verify_scan.py:1789-1796`, and the exact current interim passes. H19 nevertheless allows newline-normalized variants through live file resolution.

K3 — PASS  
The fixture payload is byte-exact to `7021bdbb:main_models.yaml` and its recorded SHA is correct. H25 concerns only inaccurate ancestry wording.

K4 — PASS  
P387 changes only tests and the fixture. Production diff against `4e6d0e03` is empty.

P4 — New findings

H19 — MEDIUM — `mlx_vlm/tests/test_mtp_verify_scan.py:1760-1761,1817,1826-1831`  
Problem: `Path.read_text()` performs universal-newline translation before hashing and classification. A CRLF or lone-CR registry is therefore normalized to LF and can pass as byte-exact, despite the CRLF rejection test at line 1893.

Scenario: the C177 interim is rewritten with CRLF. `live_registry()` reads normalized text and accepts it although its bytes differ.

Fix: read and compare raw bytes, then decode only after classification. Exercise CRLF through `live_registry()` using an actual file.

H20 — MEDIUM — `dev/p369_phase2/worker.py:92-101`; `dev/p369_phase2/orchestrate.py:777-793,810-817`  
Problem: `req-N.json` is written before progress changes to `phase="after"`. The supervisor can poll between the writes, classify an expired completed request as `request_timeout`, and then discard its durable entry.

Scenario: generation completes exactly at its deadline; the request artifact lands, but supervision intervenes before the heartbeat update. Valid E7 evidence is censored.

Fix: when stopping request N, check for and validate `req-N.json`; if present, retain it and classify the stop as `hang_after`. Add a barrier-controlled interleaving test.

H21 — HIGH — `dev/p369_phase2/orchestrate.py:1617-1618`  
Problem: the exclusive lock is located under user-selected `out.parent`, not the canonical campaign location required by the plan.

Scenario: two campaigns use different output parents and complete preflight concurrently. They acquire different locks and launch GPU workers simultaneously, invalidating timing, memory, and allocator evidence.

Fix: place the lock at one canonical `$STACK_WORKDIR/p369/phase2/.lock` independent of `--out`; test concurrent differing output paths.

H22 — MEDIUM — `dev/p369_phase2/orchestrate.py:700-744,831-854`  
Problem: cleanup ownership begins only after `launch_worker()` returns, and termination reaches only the original process group. A signal between spawn and entry into the `try`, or a descendant calling `setsid()`, can leave a worker/helper alive. The non-leader fallback signals only the direct PID and then attempts `killpg(proc.pid)`, which is not that process’s group.

Scenario: SIGTERM arrives immediately after the detached worker is created, or a helper starts a new session. The orchestrator exits while the process retains GPU memory.

Fix: block termination signals across spawn and process-handle publication; retain the actual PGID; track and terminate escaped descendants by PID/create-time; wait for group extinction before the next launch.

H23 — MEDIUM — `dev/p369_phase2/orchestrate.py:1464-1497,1621-1630`  
Problem: `prepare()`, smoke-binding checks, final `tree_guard()`, and `SystemExit` from SIGTERM sit outside the persistence handler.

Scenario: the final tree guard discovers a mid-campaign edit after all GPU work. Execution raises without replacing the partial summary with `HARNESS_ERROR`, leaving stale status.

Fix: wrap the complete campaign lifecycle in one persistence boundary and record final-tree failures and interruptions before propagation.

H24 — LOW — `mlx_vlm/tests/test_p369_phase2_orchestrate.py:931-959`  
Problem: the process-group test’s `finally` kills only known PIDs. If the child starts but its PID file is not readable, cleanup kills only the leader and can orphan the stubborn child. The normal-exit leftover-descendant path is also untested.

Scenario: the worker fails between spawning its child and writing `child.pid`; the suite leaves a 60-second process behind.

Fix: always kill the test PGID in `finally`, and add a normal-worker-exit descendant case.

H25 — LOW — `mlx_vlm/tests/test_mtp_verify_scan.py:1727-1729`; `mlx_vlm/tests/fixtures/stack_registry_golden.yaml:1-2`  
Problem: comments call `7021bdbb` C177’s parent. C177 `78a730fe` actually has parent `98a14f2e`. The registry blobs are identical, so fixture content is correct but provenance wording is false.

Scenario: a later audit follows the stated parent relationship and reaches the wrong commit history.

Fix: describe `7021bdbb` as the last commit changing the pre-C177 registry, byte-identical to `78a730fe^`.

H26 — LOW — `mlx_vlm/tests/test_mtp_verify_scan.py:1805-1811`  
Problem: `MLX_STACK_REGISTRY=""` is treated as unset because resolution tests truthiness rather than presence, contrary to “set-but-absent FAILS.”

Scenario: require mode receives an accidentally empty variable and silently falls back to a sibling registry instead of exposing the configuration error.

Fix: distinguish absence with `if "MLX_STACK_REGISTRY" in os.environ`; reject an empty value explicitly and add coverage.

VERDICT: NOT CLEARED H9 H21
