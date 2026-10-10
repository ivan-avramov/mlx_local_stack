VERDICT: FAIL

The original stable overlay-versus-daily-driver incident is caught at all seven entry paths. Remaining configuration bypasses and false-provenance paths prevent acceptance.

| Finding | Round-3 assessment |
|---|---|
| **P5** | **NOT-FIXED completely — hardening.** Addresses are retained, but [provenance.py:575]($STACK_REPO/benchmark/bench/provenance.py:575) treats every wildcard as covering both families. Reproduced `_covers("::1", ["0.0.0.0"]) == True`. An IPv4 socket cannot answer IPv6. **Fix:** preserve socket family and qualify wildcard coverage. This reproduction causes connection failure, not demonstrated wrong-router traffic. |
| **P6** | **NOT-FIXED — blocker.** [provenance.py:791]($STACK_REPO/benchmark/bench/provenance.py:791) rejects the two named environment overrides, but still does not identify opencode’s effective destination. See P20. |
| **P7** | **NOT-FIXED — major.** [provenance.py:561]($STACK_REPO/benchmark/bench/provenance.py:561) searches **every** argument. Reproduced acceptance of `python -m http.server 8000 --directory /opt/mlx-serve`, returning verified router provenance. **Fix:** validate the executable/script or Python module position; never interpret application arguments as process identity. |
| **P8** | **CONFIRMED-FIXED** for the stated successful-block fields. [provenance.py:718]($STACK_REPO/benchmark/bench/provenance.py:718) scrubs both homes; [line 768]($STACK_REPO/benchmark/bench/provenance.py:768) applies it to config, raw config and cmdline. Distinct-router-HOME regression passes. |
| **P14** | **NOT-FIXED — blocker.** The immediate scratch-directory check exists at [provenance.py:809]($STACK_REPO/benchmark/bench/provenance.py:809), but misses inherited configuration sources and ancestors. See P20. |
| **P15** | **CONFIRMED-FIXED.** [run_opencode_probe.py:571]($STACK_REPO/benchmark/run_opencode_probe.py:571) passes the verified block; [provenance.py:1022]($STACK_REPO/benchmark/bench/provenance.py:1022) uses it. Port-8123/PID manifest regression passes. |
| **P16** | **CONFIRMED-FIXED.** [generate.py:561]($STACK_REPO/benchmark/bench/generate.py:561) re-raises `ServedConfigError`; restart refusal aborts without subsequent probes or an error row. |
| **P17** | **NOT-FIXED completely — blocker.** Normal 1→2→3 history passes, but [generate.py:477]($STACK_REPO/benchmark/bench/generate.py:477) swallows refresh failures and continues producing rows with stale provenance. See P22. |

**P20 — NEW: additional local opencode configuration sources bypass verification — blocker.**

[provenance.py:791]($STACK_REPO/benchmark/bench/provenance.py:791) omits `OPENCODE_CONFIG_DIR`; [line 797]($STACK_REPO/benchmark/bench/provenance.py:797) reads only global `opencode.json`; [line 809]($STACK_REPO/benchmark/bench/provenance.py:809) checks only the immediate project directory.

Reproduced: the guard selects `localhost:8123` while `_opencode_env` preserves `OPENCODE_CONFIG_DIR`. The pinned OpenCode version loads that directory’s configuration and merges global `opencode.jsonc` after JSON. It also searches ancestor project directories. These are local sources, outside neither the stated policy nor this review. [Pinned configuration loader](https://github.com/anomalyco/opencode/blob/v1.18.15/packages/opencode/src/config/config.ts), [Pinned configuration paths](https://github.com/anomalyco/opencode/blob/v1.18.15/packages/opencode/src/config/paths.ts)

Thus an override targeting daily-driver `:8000` can recreate the incident while verification and manifests name the overlay router.

**Fix:** reject unsupported local sources—including config-directory overrides, global JSONC and discovered ancestor/home configurations—or resolve and bind the effective child configuration. Explicitly configure the child to load the shipped fallback if using it.

**P21 — NEW: parity resume rewrites historical attribution — blocker.**

[parity_replay.py:74]($STACK_REPO/benchmark/bench/parity_replay.py:74) retains only prior `rows`; [line 109]($STACK_REPO/benchmark/bench/parity_replay.py:109) writes them under today’s router.

Reproduced with **zero new requests**: rows previously attributed to PID 1/config A become attributed solely to PID 2/config B, with no history.

**Fix:** preserve prior router provenance; reject incompatible-config resumes and retain router history for compatible restarts. This requires no per-row stamping.

**P22 — NEW: failed restart-manifest refresh permits false provenance — blocker.**

At [generate.py:474]($STACK_REPO/benchmark/bench/generate.py:474), missing manifests are skipped and refresh exceptions are logged without stopping.

Injected a manifest `PermissionError` while row files remained writable:

```text
verified router: 1 → 2 → 3
persisted router: 1
probes: 4; rows: 2; run: COMPLETE
```

**Fix:** make required router-manifest refresh failure fatal before further traffic. Preserve the original manifest with an atomic replacement; apply the same requirement to compatible-resume refreshes.

**P23 — NEW: strict “before first read/write/request” ordering remains unmet — nonblocking contract gap.**

[stack_smoke.py:172]($STACK_REPO/benchmark/bench/stack_smoke.py:172) reads deployed parameters before verification. For leg B, [session_cache_probe.py:368]($STACK_REPO/benchmark/bench/session_cache_probe.py:368) preloads before the project-override refusal at [line 257]($STACK_REPO/benchmark/bench/session_cache_probe.py:257); scratch files have already been overwritten.

**Fix:** move parameter reads after verification and inspect existing scratch/source configuration before preload or staging writes.

**P24 — A1–A7 retest**

| Criterion | Result and evidence |
|---|---|
| **A1** | **FAIL** under the requested first-read/write/request contract: P23. Initial router mismatch nevertheless refuses before HTTP/result writes across all seven paths. |
| **A2** | **PASS:** router HOME/cwd expansion, realpath and existing-file checks at [provenance.py:679]($STACK_REPO/benchmark/bench/provenance.py:679). |
| **A3** | **FAIL:** P5/P7/P20. Named missing-owner, unreadable-env, absent-config and mismatch cases pass. |
| **A4** | **FAIL:** false attribution on parity resume and failed restart refresh, P21/P22. |
| **A5** | **FAIL—coverage gaps:** 102 tests pass, but omit the reproduced cases. Discovery tests exercise production functions; the [autouse fake owner]($STACK_REPO/benchmark/bench/tests/conftest.py:206) means entry tests alone cannot establish discovery correctness. |
| **A6** | **FAIL overall:** exact stable incident passes all seven mocked entry paths; P20 permits a local-config variant. |
| **A7** | **FAIL:** required provenance refresh exceptions remain swallowed, P22. |

**P25 — Validation:** 102 focused tests passed; additional adversarial reproductions produced the failures above. `git diff --check` passed. No repository files were modified; test scratch stayed under `STACK_WORKDIR`. No live model requests or router restarts were performed.