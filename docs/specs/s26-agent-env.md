# S26 — agent environment: host fingerprint guard (C360) + tg2 positives and Gradle home (C361) — SPEC v1, 2026-11-17 (four-eyes STRICT)

## Goal

An agentic benchmark leg must run in a specified, unchanging host environment and must not change it under itself or under the
other arm of a pair: (C360) record the environment the agent can see and change as a fingerprint, check it around every Wave 2 leg
and around the tg2 positives, and fail closed on a change; (C361 (1)) the tg2 positives prove the harness, not the model's
willingness to run planted commands: stall must pass, loop / alloc pass or are recorded as declined by the model; (C361 (2)) every
tg2 Java item finds the same pre-filled Gradle home in one bench-owned folder, with no daemon, instead of the operator's real
`~/.gradle` (the JVM ignores `$HOME`) and a first-item network download. Light: no sandbox, no command denylist, no auto-revert.

## Inputs

- Rulings: C360, C361 (`docs/open-questions.md`); findings S26-P5, S26-P6, S26-P11, S26-P12, S26-P13; C152 (alloc waiver precedent).
- Starting code (designer WIP, unreviewed; treat as a draft, not a constraint): `bench/host_env.py`, the `host_env` hunks of
  `bench/p426_wave2.py`, `bench/tests/test_s26_host_env.py`, `scripts/bootstrap_machine.sh` step 5b. Its cold read:
  `docs/reviews/s26-p9/cold-read-sol-r1.md` (adopted below: P1 partly, P2, P3, P4, P5, P8).

## Scope (files)

`benchmark/bench/host_env.py` (new), `benchmark/bench/p426_wave2.py`, `benchmark/bench/p426_freeze.py` (`positives_problems`),
`benchmark/bench/arm_opencode.py` (tg2 env + identity), `benchmark/bench/tg2_gradle_home.py` (new), tests under
`benchmark/bench/tests/`, `scripts/bootstrap_machine.sh`. Nothing else.

## Settled constraints

- (C360, operator) Light: detect and fail closed; never revert, never deny commands; network stays open.
- (C361, operator) Loop / alloc may be declined by the model (C152 precedent); one bench-owned Gradle home for all tg2 items.
- (designer) tg1 behaviour, argv, records and identity are byte-unchanged: B4b-1's tg1 golden
  (`bench/tests/test_m76_b4b1_impl_golden_tg1.py`) passes unmodified. tg2 identity may change (no tg2 leg has run).
- (designer) No new third-party dependency. Lazy-import heavy modules. Tests are mocked or use temp trees; no GPU, no network,
  no real Homebrew mutation, no docker except where existing tests already use it.
- (AGENTS.md) Guards check recorded facts, not declarations; a refusal names what changed; no PII in records or messages.

## Interfaces

### 1. `bench/host_env.py`

- `fingerprint(*, path=AGENT_PATH, cellar=…, bin_dirs=…, npm_global=…, home=None, files=()) -> dict`, deterministic for an
  unchanged host, JSON-serialisable, no subprocess calls:
  - `tools`: for each name in `TOOLS` (`cargo rustc java javac gradle node npm g++ clang++ cmake make python3 go docker`):
    `"absent"`, or `{"path": realpath, "sha256": sha256 of the resolved file}` (no `--version` call; S26-P9 r1 P3).
  - `cellar`: sorted `<formula>/<version>` under the Homebrew Cellar (`/opt/homebrew/Cellar`).
  - `bin_dirs`: for `/opt/homebrew/bin` and `/usr/local/bin`: sorted entries, each `name` or `name -> readlink target`.
  - `npm_global`: `{package: version}` from each `package.json` directly under `/opt/homebrew/lib/node_modules` (scoped packages
    one level deeper); `null` when the directory is absent.
  - `home_toolchains`: for `.cargo .rustup .sdkman .gradle .m2 .npm-global Library/Python` under the real HOME: present or absent.
  - `files`: `{label: sha256 | "absent"}` for the given `(label, path)` pairs (callers pass the tg2 Gradle home's
    `gradle.properties`, §3).
  - An unreadable entry records `"error: <ExceptionName>"`, never raises.
- `diff(before, after) -> list[str]`: every changed key, human-readable (`tool cargo: absent -> /opt/…`, `Homebrew Cellar: added x/1`,
  `~/.cargo: absent -> present`, `npm -g jest: absent -> 29.7.0`); `[]` iff equal.
- `fingerprint_for_run()`: the box call: defaults + `files=(("tg2 gradle.properties", <tg2 Gradle home>/gradle.properties),)`.

### 2. Wave 2 sequencer (`bench/p426_wave2.py`)

- `BoxSeqOps.host_env()` → `host_env.fingerprint_for_run()`. Fakes may omit the seam; the real ops always have it (tested).
- Baseline: the first check of a run writes `<out-base>/host_env.json` (exclusive, `{kind: "host_env", fingerprint, created}`);
  later checks compare to it; an unreadable baseline stops (rc 1).
- Before every launch (after the power check): a difference → `Stop(1)`, message `STOP: the host environment differs from the run's
  baseline before <leg> (nothing launched): <diff>`; nothing launched.
- After every launched leg, on every path that reaches the end of supervision (normal end, overrun, and any exception raised between
  the launch and `leg.json`; S26-P9 r1 P2): compare; a difference sets the leg `state: INVALID`, `reason: "host environment changed
  during the leg: <diff>"`, and the `class` an INVALID infrastructure leg gets from `classify_leg` today (r1 P5; the implementer names
  the value it uses); `leg.json` and `sequence.json` carry it; the leg is harvested as INVALID legs are; the run stops as for any
  INVALID leg. When an exception path is taken, the check runs and is logged, then the exception propagates.
- End of run: after the last leg of the command (the `DONE` path), one more check; a difference → `Stop(1)` with `STOP: the host
  environment changed after the last leg: <diff>` and `sequence.json` records `host_env_after_last_leg` = the diff.
- `run` publishes `host_env.json` with the other run files (`publish_run_files`; r1 P4). A rehearsal keeps it in its out-base.
- `cmd_positives`: fingerprint before the serving session and after it (in a `finally`, also when an inject raises); a difference adds
  `host environment changed during the leg: <change>` per change to `problems`; the record carries `host_env` (the before
  fingerprint) and the verdict FAILs.

### 3. tg2 Gradle home (`bench/tg2_gradle_home.py`, `bench/arm_opencode.py`)

- `GRADLE_HOME_REL = "tg2-gradle-home"`: the folder is `$STACK_WORKDIR/tg2-gradle-home/`; `PROPERTIES = "org.gradle.daemon=false\n"`
  written as `gradle.properties` in it.
- `python -m bench.tg2_gradle_home prefill [--force]`: creates the folder and `gradle.properties`; for every VALID Java item of the
  committed tg2 universe, prepares the item (`Tg2Corpus.prepare`), applies its reference (`tg2_materialize.apply_reference`), runs
  `./gradlew test --console=plain` with `env = {PATH: host_env.AGENT_PATH, HOME: <scratch home>, GRADLE_USER_HOME: <folder>, TMPDIR}`
  (nothing else inherited), then `./gradlew --stop`; then a second pass per item with `--offline` (proves the folder serves every
  item without network). Writes `<folder>/PREFILL.json` (`items` with rc of both passes, `gradle_version`, `java` realpath,
  `created`, `universe_sha256`). rc 0 only when every offline pass succeeds; a non-empty folder without `--force` refuses.
  Work trees live under `$STACK_WORKDIR/scratch/` and are removed after.
- `python -m bench.tg2_gradle_home check` → rc 0 iff the folder exists, `gradle.properties` equals `PROPERTIES`, `PREFILL.json`
  exists with every offline pass rc 0 for the committed universe's sha.
- `OpencodeArm.build_env` (tg2 only): `env["GRADLE_USER_HOME"] = <folder>` after `check` succeeds; else `ArmContractError` naming the
  missing piece (the item never starts). tg1 / M64 unchanged.
- tg2 identity (`OpencodeArm.identity`, tg2 only): `policy["gradle_user_home"] = {"path": "$STACK_WORKDIR/tg2-gradle-home",
  "properties_sha256": …, "prefill_sha256": sha256 of PREFILL.json}`.

### 4. tg2 positives pass rule (`cmd_positives`, `p426_freeze.positives_problems`)

- Per (language, kind): `stall` → `PASS` required. `loop` / `alloc` → `PASS`; else `DECLINED` when the run's events (the row's
  `events_path`) hold NO tool call whose input contains the kind's marker (`loop`: `sleep 600`; `alloc`: `bytearray(`); else the
  inject_verify verdict (a FAIL). A `TRANSPORT_ABORT` stays a FAIL.
- Each inject entry records `verdict` (`PASS` | `DECLINED` | the failure), `declined_evidence` (the events file sha256 and the
  marker) when DECLINED.
- `positives_problems` (v8) accepts `DECLINED` for loop / alloc only; anything else unchanged.

### 5. Bootstrap

`scripts/bootstrap_machine.sh` step 5b: `brew install rust openjdk@21 cmake`, `brew link --force openjdk@21`, `java` resolves on the
agent PATH or die; prints the versions; names `python -m bench.tg2_gradle_home prefill` as the tg2 prerequisite (not run by default).

## Success and failure paths (traced)

- Clean Wave 2 run: first pre-launch check writes the baseline; every leg's pre / post checks are `[]`; the end check is `[]`;
  `host_env.json` is published with the run files.
- A leg runs `brew install openjdk@17`: post-leg diff `Homebrew Cellar: added openjdk@17/…` → leg INVALID with that reason, harvested,
  run stops; a rerun first refuses before launch until the host equals the baseline again.
- A tg2 Java item on an arm whose Gradle folder was never prefilled: `build_env` raises `ArmContractError: tg2 Gradle home …`; no item runs.
- Positives where the model declines loop (no `sleep 600` tool call in the events): verdict DECLINED, record PASS if all else passes,
  v8 accepts. The model runs `sleep 600 …` but inject_verify fails: FAIL, v8 refuses.

## Supported conditions

This box (macOS, Homebrew under `/opt/homebrew`, the agent PATH of `opencode_v2_core`), the pinned opencode 2.0.20, the committed tg2
universe / draw, JDK 21 from Homebrew, Gradle 8.7 via the exercises' wrapper.

## Acceptance criteria

1. Tests (mocked / temp trees): fingerprint determinism and each `diff` kind (tools via a temp PATH with a changed file; Cellar;
   bin_dirs incl. a symlink retarget; npm_global version change; home toolchains incl. `Library/Python`; files); an unreadable entry;
   the sequencer: baseline written once, pre-launch refusal, post-leg INVALID with reason and class, exception-path check, end-of-run
   check, `host_env.json` published (run) / kept (rehearsal), fakes without the seam unchanged, `BoxSeqOps.host_env` exists; positives:
   host change → FAIL, DECLINED vs FAIL vs PASS per kind from real-shaped events, stall never DECLINED, v8 accepts DECLINED only for
   loop / alloc; `build_env` tg2 refuses without a prefilled folder and sets `GRADLE_USER_HOME` with one; tg2 identity carries the
   Gradle policy; tg1 identity, argv and env unchanged (the B4b-1 tg1 golden passes unmodified); `tg2_gradle_home` prefill / check with a
   fake runner (both passes, refusal on a non-empty folder, offline failure → rc ≠ 0).
2. The stack suite passes or fails only as on the baseline.
3. (Designer, real box, after Wave 2) `prefill` rc 0 on the real universe; `check` rc 0; a tg2 positives run PASSES under the new rule.

## Non-goals

Sandboxing or network control; hashing contents of existing directories (residual: a change inside an already-present `~/.gradle` /
`~/.cargo` is not seen); npm / crate caches (downloads per item accepted, C361); the inject addenda (S26-P13: unchanged); tg1 changes.

## Open questions

None for the operator; implementation deviations follow the deviation rule: satisfy the behaviour, report any interface deviation
with its reason.
