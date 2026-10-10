VERDICT: FAIL

The normal single-router incident is caught before generation, but M50 does not satisfy the registered criteria. It can validate the wrong HTTP destination, leaks home paths into provenance, and misses the first request on one CLI path.

**P3 — A1: FAIL — major. Guard placement is incomplete.**

| Entry point | Finding |
|---|---|
| `generate.run` | **PASS directly:** guard at [generate.py:420]($STACK_REPO/benchmark/bench/generate.py:420) precedes precheck, cleanup, manifests and preload. **FAIL through `run.py generate`:** [run.py:123]($STACK_REPO/benchmark/run.py:123) calls `_resolve`; without `--models`, [run.py:96]($STACK_REPO/benchmark/run.py:96) calls `client.roster()`, issuing `/v1/models` before the guard. |
| `session_cache_probe.main` | **FAIL:** [session_cache_probe.py:349]($STACK_REPO/benchmark/bench/session_cache_probe.py:349) creates the work directory before the guard at line 353. `LogTail` only reads metadata; preload follows the guard. |
| `stack_smoke.main` | **FAIL:** [stack_smoke.py:175]($STACK_REPO/benchmark/bench/stack_smoke.py:175) creates the output directory before the guard at line 178. |
| `parity_replay.run` | **FAIL:** [parity_replay.py:66]($STACK_REPO/benchmark/bench/parity_replay.py:66) creates the output directory before the guard at line 74. Earlier frozen/resume reads are read-only. |
| `vision_gate.main` | **PASS:** [vision_gate.py:278]($STACK_REPO/benchmark/vision_gate.py:278) checks after applying `--url`, before output-directory creation, corpus loading and requests. |
| `run_opencode_probe.main` | **PASS for ordering of model requests/result writes:** [run_opencode_probe.py:546]($STACK_REPO/benchmark/run_opencode_probe.py:546) precedes manifest/result creation and agent execution. Docker/version subprocess checks precede it. Destination correctness fails separately under A3. |

**Fix:** guard `cmd_generate` before `_resolve`, retain protection for direct `generate.run` callers, and move the other three guards above their `mkdir` calls. Refusal currently exits nonzero, but the directory side effects violate the explicitly requested ordering.

**P4 — A2: FAIL — major. Router path resolution uses the driver’s home and accepts missing files.**

At [provenance.py:613]($STACK_REPO/benchmark/bench/provenance.py:613), `os.path.expanduser(raw)` uses the **reviewing/driver process’s HOME**, ignoring `owner["env"]["HOME"]`. A router with a different HOME and `MLX_SERVE_CONFIG=~/…` can therefore produce either a false match or false mismatch. I reproduced a false match.

At [provenance.py:616]($STACK_REPO/benchmark/bench/provenance.py:616), non-strict `realpath` accepts nonexistent paths. In contrast, the actual [_find_config:24]($HOME/ws/mlx-serve/src/mlx_serve/config.py:24) checks existence and raises; an explicit missing config **does not fall back**. I reproduced acceptance when both sides named the same nonexistent file. This can affect a running router whose original config was deleted.

Ordinary existing symlinks, `..`, trailing separators and relative paths against a different router cwd are handled by the realpath comparison. The driver correctly retains its separate repo-root convention in [paths.py:53]($STACK_REPO/benchmark/bench/paths.py:53).

**Fix:** expand `~` using the router’s environment/user identity, require a known router cwd for relative paths, and verify the resolved paths exist before comparing. Remove the fallback to the driver’s `os.getcwd()` at line 615. Keep refusing absent `MLX_SERVE_CONFIG` as required by A3, but correct the diagnostic’s claim that fallback can “never” select the driver’s registry.

**P5 — A3: FAIL — blocker. Port ownership is not endpoint ownership.**

The four required refusal branches exist at [provenance.py:630]($STACK_REPO/benchmark/bench/provenance.py:630): no owner, unreadable environment, absent config and mismatch. There is no environment/CLI bypass. Explicit ports and HTTP/HTTPS default ports are parsed.

However:

- **Blocker:** [provenance.py:562]($STACK_REPO/benchmark/bench/provenance.py:562) selects the first listener with the port, ignoring destination host, bound address and address family. The [lsof fallback:576]($STACK_REPO/benchmark/bench/provenance.py:576) likewise selects the first PID. I exercised the production lookup with mocked psutil processes: an IPv4 target was approved using an unrelated IPv6 listener’s matching config. A remote URL also passes using a local listener.
- **Blocker:** [run_opencode_probe.py:546]($STACK_REPO/benchmark/run_opencode_probe.py:546) checks `MLX_SERVE_BASE`, while [_opencode_env:271]($STACK_REPO/benchmark/run_opencode_probe.py:271) merely inherits the environment and does not bind OpenCode’s provider URL to it. The shipped [opencode.json:8]($STACK_REPO/opencode_config/opencode.json:8) uses `localhost:8000/v1`. An overlay on `:8123` can pass the check while OpenCode benchmarks the daily driver on `:8000`. Session-cache leg B has the same independently configured OpenCode destination.
- **Major:** an inherited `MLX_SERVE_CONFIG` is sufficient for any listener to pass; command line is recorded but never validated. A proxy or worker can be mistaken for the router. A proxy without that variable safely refuses, but its environment is not proof of its backend.

Established client sockets are correctly excluded by the LISTEN filters.

**Fix:** verify the actual destination host/address/family and refuse ambiguous or unsupported remote/proxy ownership. Resolve and explicitly bind OpenCode’s provider configuration to the checked endpoint. Verify router identity, rather than accepting any process carrying the variable.

**P6 — A4: FAIL — blocker for privacy; major for incomplete records.**

[provenance.py:647]($STACK_REPO/benchmark/bench/provenance.py:647) normalizes only `config`; `config_raw` and `cmdline` remain verbatim. I reproduced absolute home paths in **both** fields. [provenance.write:878]($STACK_REPO/benchmark/bench/provenance.py:878) serializes them directly into result manifests. Stack-smoke, parity and vision outputs also serialize the block without scrubbing. The [router_block error:656]($STACK_REPO/benchmark/bench/provenance.py:656) can persist absolute paths from exception text. Session-cache’s final whole-document scrub does cover its output.

Recording is also incomplete:

- Generate’s [result rows:480]($STACK_REPO/benchmark/bench/generate.py:480) and OpenCode’s [result rows:608]($STACK_REPO/benchmark/run_opencode_probe.py:608) lack `router`.
- Vision records it only in the final summary, after [JSONL writes:319]($STACK_REPO/benchmark/vision_gate.py:319); an interrupted run lacks that summary.
- Aborted [parity output:89]($STACK_REPO/benchmark/bench/parity_replay.py:89) and [smoke output:191]($STACK_REPO/benchmark/bench/stack_smoke.py:191) omit it.
- [generate.py:263]($STACK_REPO/benchmark/bench/generate.py:263) preserves compatible existing manifests, so resumed results can retain no router block—or a previous router PID.

**PASS subcriterion:** the router block is outside [config_fingerprint:325]($STACK_REPO/benchmark/bench/provenance.py:325). A PID-only change does not cause staleness or deletion; my in-memory comparison confirmed this.

**Fix:** sanitize every persisted router string centrally, including errors, or omit raw command lines. Attach the verified router block/run reference to all result and abort records. Preserve historical run identities when resuming instead of silently retaining or replacing a single PID.

**P7 — A5: FAIL — major. Tests cover comparison logic but bypass process discovery.**

The tests execute real `assert_served_config` and entry-point control flow. They do **not** establish production process-table correctness:

- The purported lsof parsing test [test_provenance_fingerprint.py:584]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:584) replaces `_psutil_listener`, `_lsof_listener_pid` and `_process_facts`. It tests fallback dispatch, not parsing or process inspection.
- The [autouse fixture:215]($STACK_REPO/benchmark/bench/tests/conftest.py:215) makes every ordinary lookup match the current registry regardless of port. It masks discovery failures, wrong-port selection and missing dependencies.
- The home-path test at [line 508]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:508) checks only `config`, using a temporary path that need not be under HOME. The “symlink” test at line 516 creates no symlink.
- [Entry-point tests:33]($STACK_REPO/benchmark/bench/tests/test_m50_entrypoints.py:33) invoke `generate.run`, missing the CLI roster request. Directory-refusal tests use already-existing `tmp_path` parents. OpenCode has no successful-recording test.

**Fix:** add tests mocking psutil/subprocess primitives while retaining all production discovery functions. Cover dual-stack/multiple listeners, remote hosts, inherited worker environments, AccessDenied, disappearing processes, actual lsof field output, missing files, differing router HOME, real symlinks, nonexistent output parents, CLI generation without `--models`, OpenCode endpoint disagreement, abort records and whole-document privacy.

**P8 — A6: FAIL — major. The first-request guarantee is false.**

With one stable local listener and literal overlay-versus-main config paths, all six guards reject the incident before preload/completion. But `run.py generate` without `--models` already sends its roster GET, and the endpoint-selection failures in P5 can still allow contaminated benchmark requests.

There is also a check/use window: [generate.py:420]($STACK_REPO/benchmark/bench/generate.py:420) validates before corpus loading and manifest work; preload occurs at line 453. A router replacement during that interval is not checked. A later `gather()` mismatch becomes a best-effort error block rather than stopping the run.

**Fix:** apply P3/P5, verify process identity again immediately before first model traffic and after restarts, and abort if identity changes. For stronger guarantees, capture the loaded config identity/hash in the router itself: reconstructing a path cannot detect an in-place config replacement or a symlink retargeted after startup.

**P9 — A7: FAIL — minor operational gaps.**

The per-process approach avoids the stated macOS system-wide-table restriction, and the fallback correctly requests LISTEN records. Missing psutil still refuses: lsof may find a PID, but `_process_facts` cannot obtain its environment.

Concrete remaining fixes:

- [requirements.txt:20]($STACK_REPO/benchmark/requirements.txt:20) permits psutil 5.9, but [provenance.py:561]($STACK_REPO/benchmark/bench/provenance.py:561) uses `Process.net_connections`, renamed in 6.0. On 5.9, exceptions are swallowed and every lookup falls through to lsof. Require ≥6.0 or support the older method. [Official migration reference](https://psutil.io/migration/#migrating-to-6-0).
- [Process inspection:589]($STACK_REPO/benchmark/bench/provenance.py:589) groups cmdline, cwd and environment in one try; a cmdline failure prevents otherwise usable facts from being read. Separate required facts from optional diagnostics and retain specific failure reasons.
- Every fresh [gather:864]($STACK_REPO/benchmark/bench/provenance.py:864) repeats the process walk, potentially followed by a 20-second lsof timeout, once per newly written manifest. Pass the verified observation into manifest creation; keep deliberate revalidation at request/restart boundaries.

Validation: read the requested diff/status and untracked M50 tests; `git diff --check` passed. In-memory production-code checks reproduced the ordering, missing-path, HOME, destination-selection and privacy failures. I did not run the filesystem-writing pytest fixtures. No files were modified or live model requests sent.

