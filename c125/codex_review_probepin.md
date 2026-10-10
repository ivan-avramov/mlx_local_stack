Verdict: **BLOCKING**

**F1 — blocking — `benchmark/bench/session_cache_probe.py:262`: pre-M50 writes use the operator environment.**  
Running the actual pinned binary with only `--version` created config, data, state, cache, log, repository-cache and temporary directories. Its embedded initialization code unconditionally calls `mkdir` before argument handling. With `dict(os.environ)`, these target operator directories. This exceeds the stated exception for execution under the **bench-owned environment**.

Minimal fix: supply a bench-owned preflight environment, redirecting HOME/XDG/TMP locations outside the requested work directory, and strip operator `OPENCODE_*` overrides. Reuse the existing environment builder/policy where applicable. `_opencode_version` also omits `--pure`; adding that alone cannot prevent initialization writes.

**VERIFIED-BY-RUNNING / VERIFIED-BY-READING.** Network was denied during my run; success establishes no required network access, **not** zero attempted connections. Whether arbitrary operator configuration is read during `--version` remains **ASSUMPTION**, not established.

**F2 — should-fix — `scripts/session_pinning_gate.py:64`: executable-path validation is not version validation.**  
An absolute executable override pointing to another compatible version passes `_require_opencode_bin()` and runs. A4 can consequently print a passing result for an unrecorded scaffold.

Minimal fix: check the version under the corrected preflight environment before gate activity; record binary/version and label A4 as **pinned v1 session-header propagation**. It now measures v1 with operator configuration/skills, not the installed v2 daily driver. Its pass criterion measures session pinning; cross-process cache reuse remains diagnostic. `[A4] True` does not certify v2.

The import resolves: lines 28–29 put `benchmark` on `sys.path`. The gate’s lack of M50/destination guards predates this diff; pinning does not repair it.

**VERIFIED-BY-READING.**

**F3 — should-fix — `benchmark/bench/session_cache_probe.py:409,432`: the new path field is not universally publication-safe.**  
An accepted override under `$STACK_WORKDIR/<login>/opencode` retains `<login>`. An executable under another user’s home retains its absolute home path. `_portable` and the final replacement loop only cover configured roots/current HOME. The version field is safe because successful execution requires exact equality with `1.18.30`.

Minimal fix: scrub login names and other home-directory prefixes before persistence, or reject paths that cannot be represented safely. Add both cases to the persistence test.

**VERIFIED-BY-RUNNING / VERIFIED-BY-READING.**

**F4 — should-fix — `benchmark/bench/session_cache_probe.py:379`: filesystem exceptions can escape `main`.**  
A `PermissionError` during `_require_opencode_bin()`’s `is_file()` escapes because this block catches only `SystemExit`. The process still fails before router/HTTP/workdir activity, but without the intended controlled refusal.

Minimal fix: handle expected resolution/stat `OSError`s as refusals.

For the requested ordinary cases, ordering is correct: missing, relative, non-executable and wrong-version refusals are covered by passing tests; mocked nonzero exit, timeout and launch failure each returned 2 with zero router/HTTP calls and no workdir.

**VERIFIED-BY-RUNNING.**

**F5 — note — `benchmark/bench/session_cache_probe.py:99,283,393`: no direct PATH fallback remains; executable identity remains conditional.**  
Both turns use the supplied binary. Both destination checks pass it with `pure=True`; `provenance.py:1612` directly executes that argv, without `shell=True` or `shutil.which`. The installed `.bin/opencode` symlink targets a native ARM64 Mach-O executable, not a shell/Node launcher. Package `postinstall.mjs` is an installation step, not its launch path.

However, an absolute `OPENCODE_PROBE_BIN` may itself be a wrapper that executes bare `opencode` through PATH. The resolver permits that. A replaced executable/symlink between version checking and execution can also invalidate the recorded version.

Minimal fix if stronger identity is required: constrain overrides to approved native executables and record/recheck executable hashes. Current assurance assumes a trusted, unchanged override.

**VERIFIED-BY-READING; unchanged executable identity is ASSUMPTION.**

**F6 — note — `benchmark/bench/session_cache_probe.py:269`: operator configuration compatibility is unproven, not a demonstrated new blocker.**  
A v2-only configuration key rejected by v1 would make `debug config` fail; the first destination check converts that into refusal before model loading. A successfully parsed config with different sampling/tool semantics can pass M50: that check verifies the provider destination, not the complete scaffold.

I established no concrete incompatibility in the operator’s current configuration. No larger isolation redesign is justified as a blocking finding from this evidence. Minimal follow-up: document the v1/operator-config scope; fingerprint resolved configuration if results must identify the complete scaffold.

**VERIFIED-BY-READING; actual configuration incompatibility is ASSUMPTION.**

**F7 — note — `benchmark/bench/tests/test_session_cache_probe.py:147–215`: useful coverage, with specific blind spots.**

| New test | What it establishes; what can still pass |
|---|---|
| Missing binary | Early refusal; does not exercise successful default-location resolution. |
| Relative override | Bare-name rejection; absolute PATH-delegating wrappers remain untested. |
| Non-executable | Mode-based refusal; stat exceptions remain untested. |
| Wrong version | Catches skipped comparison **and** skipped version execution—both mutations failed. |
| Proceeds/records | Checks portable path/version; operator-env side effects and login-name suffixes still pass. |
| PATH decoy | Catches continuation PATH fallback and `pure=False` at **either** destination call—each mutation failed. Destination subprocess internals are mocked. |
| A/C independence | Checks no resolver/version calls; does not prove lazy import because the test itself imports the module. |

The updated command-shape test also caught continuation PATH fallback. Test binaries/output are confined to temporary directories; real opencode and real STACK_WORKDIR are not required. The decoy test assumes `PATH` exists, but not a particular ordering. My runs disabled bytecode and pytest-cache writes.

Minimal additions: environment assertions, stat/version-failure cases, default-location success, wrapper handling and broader scrub cases.

**VERIFIED-BY-RUNNING / VERIFIED-BY-READING.**

Checks actually run:

```text
Original mocked suite:
14 passed in 0.52s

Scratch-copy baseline:
14 passed in 0.24s

continue_uses_PATH:
2 failed, 12 passed
inner_destination_not_pure:
1 failed, 13 passed
outer_destination_not_pure:
1 failed, 13 passed
version_check_skipped:
1 failed, 13 passed
version_spawn_skipped:
1 failed, 13 passed

Isolated real --version:
rc=0 stdout='1.18.30\n' stderr=''
Created: tmp/opencode, config/opencode, state/opencode,
         cache/opencode/bin, data/opencode/{log,repos}

Mocked refusal checks:
nonzero       rc=2 router=0 http=0 wd_exists=False
timeout       rc=2 router=0 http=0 wd_exists=False
launch_oserror rc=2 router=0 http=0 wd_exists=False
stat_error escaped=PermissionError router=0 http=0 wd_exists=False
```

The initial sandboxed pytest attempt failed because no temporary directory was writable; the successful rerun used a fresh directory under STACK_WORKDIR. Repository files were unchanged; no model-server requests were made.