# S26 — agent environment: host fingerprint guard (C360) + tg2 positives and Gradle home (C361) — SPEC v1.1d, 2026-11-18 (four-eyes STRICT; v1.1 applies design review round 1, v1.1a the change review round 1 errata; `docs/reviews/s26-agent-env/`)

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
  `docs/reviews/s26-p9/cold-read-sol-r1.md` (adopted below: P1 partly, P2, P3, P4, P5, P8). The draft diverges from this spec in
  places (it runs `--version`, lacks `files` / `npm_global` / `Library/Python`, has no exception paths): the spec governs.
- Verified facts: the JVM's `user.home` ignores `$HOME` on this box (`HOME=/tmp/fakehome java -XshowSettings:properties` → the
  real home); the agent's shell inherits the opencode spawn env built by `OpencodeArm.build_env` (`arm_runner.py:1123`, `:1207`; a
  recorded transcript's shell prints `PATH=/opt/homebrew/bin:/usr/bin:/bin`); the chain and the positives both spawn through it.

## Scope (files)

`benchmark/bench/host_env.py` (new), `benchmark/bench/p426_wave2.py`, `benchmark/bench/p426_freeze.py` (`positives_problems`),
`benchmark/bench/arm_opencode.py` (tg2 env + identity), `benchmark/bench/arm_runner.py` + `benchmark/bench/run_config.py` (the identity policy, §3), `benchmark/bench/tg2_gradle_home.py` (new), tests under
`benchmark/bench/tests/`, `scripts/bootstrap_machine.sh`. Nothing else.

## Settled constraints

- (C360, operator) Light: detect and fail closed; never revert, never deny commands; network stays open.
- (C361, operator) Loop / alloc may be declined by the model (C152 precedent); one bench-owned Gradle home for all tg2 items.
- (designer; v1.1a wording, change r1 Sol P22) tg1's agent env, argv and `scaffold_policy_sha256` are unchanged; its closure-derived
  `probe_code_sha256` rotates (C178); the Wave 2 sequencer gains the guard for tg1 too. B4b-1's tg1 golden
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
- Baseline: at `Sequencer.run()` entry, before the first leg (design r1 GLM F14): the first run of an out-base writes
  `<out-base>/host_env.json` (exclusive, `{kind: "host_env", fingerprint, created}`); a resumed run compares the live fingerprint to
  it first and stops on a difference (message as the pre-launch refusal, `<leg>` = the next leg); an unreadable baseline stops (rc 1).
- Before every launch (after the power check): a difference → `Stop(1)`, message `STOP: the host environment differs from the run's
  baseline before <leg> (nothing launched): ` + `"; ".join(diff)`; nothing launched.
- After every launched leg: a `try/finally` spans from `ops.launch` to the `leg.json` write (design r1 GLM F1); the `finally` compares.
  On the normal path a difference sets `state: "INVALID"`, `class: "systemic"` (the class `classify_leg`'s `invalid()` gives), and
  `reason: "host environment changed during the leg: " + "; ".join(diff)`, followed by ` (prior: <reason>)` when the leg already had a
  reason (GLM F2, F13); `leg.json` and `sequence.json` carry it; the leg is harvested as INVALID legs are; the run stops as for any
  INVALID leg. When an exception left the region, the `finally` logs the diff (or "unchanged") to `sequence.log` and the exception
  propagates unchanged.
- Finalization (both exits of `run()`: the `DONE` path and the `--through` return; Sol P3, GLM F4): one more check BEFORE publishing
  the run files; a difference → `sequence.json` records `host_env_after_last_leg` = the diff (saved), then `Stop(1)` with
  `STOP: the host environment changed after the last leg: ` + `"; ".join(diff)`; no difference → publish, log, return as today.
- `run` publishes `host_env.json` with the other run files (`publish_run_files`; r1 P4). A rehearsal keeps it in its out-base.
- `cmd_positives`: `env0` = the fingerprint before the first grade. The grades, the serving session and the injects run inside one
  `try`; any exception there (Sol P5, GLM F3) is caught, recorded in `problems` as `exception: <ExceptionName>: <message[:300]>`, and
  the run continues to the record; a `finally` takes `env1` (also when no session opened). Each change in `diff(env0, env1)` adds
  `host environment changed during the leg: <change>` to `problems`. The sealed record carries `host_env` (= `env0`), `host_env_after`
  (= `env1`) and the verdict (FAIL on any problem); rc 0 only when every check passes.

### 3. tg2 Gradle home (`bench/tg2_gradle_home.py`, `bench/arm_opencode.py`)

- `GRADLE_HOME_REL = "tg2-gradle-home"`: the folder is `$STACK_WORKDIR/tg2-gradle-home/`; `PROPERTIES = "org.gradle.daemon=false\n"`
  written as `gradle.properties` in it.
- `python -m bench.tg2_gradle_home prefill [--force]`: `--force` removes the folder first; without it a non-empty folder refuses.
  Creates the folder and `gradle.properties`; for every VALID Java item of the committed tg2 universe (exactly that set), prepares the
  item (`Tg2Corpus.prepare`), applies its reference (`tg2_materialize.apply_reference`), runs `./gradlew test --console=plain` with the
  agent's spawn env fields (design r1 GLM F12): `SCAFFOLD_ENV_POLICY_V2` (PATH, TERM, NO_COLOR, …), `HOME` = a scratch home,
  `TMPDIR` = a scratch dir, plus `GRADLE_USER_HOME` = the folder, nothing else; then `./gradlew --stop`; then a second pass per item
  with `--offline` (proves the folder serves every item without network). Writes `<folder>/PREFILL.json`: `items` (id, rc of both
  passes), `gradle_version`, `java` realpath, `universe_sha256`, `cache_manifest` (Sol P4: sorted `[relative path, size]` of every
  file under `wrapper/dists/` and `caches/modules-2/files-2.1/`), `created`. rc 0 only when every offline pass succeeds. Work trees
  live under `$STACK_WORKDIR/scratch/` and are removed after.
- `python -m bench.tg2_gradle_home check` → rc 0 iff the folder exists, `gradle.properties` equals `PROPERTIES`, `PREFILL.json`
  exists for the committed universe's sha with exactly its VALID Java items, every offline pass rc 0, and the live `cache_manifest`
  contains every recorded entry with its size (Sol P4); else rc ≠ 0 naming the first problem. The same check as a function,
  `check_problems() -> list[str]`.
- `OpencodeArm.build_env` (tg2 only, `self.tg2`): `check_problems()` empty → `env["GRADLE_USER_HOME"] = <folder>`; else
  `ArmContractError("tg2 Gradle home: <problem>")` (the item never starts). tg1 / M64 unchanged.
- tg2 identity (Sol P2): `GenerationPolicy` (`run_config.py`) gains `gradle_user_home: dict | None = None`, OMITTED from `as_dict()`
  and the hash when None (tg1's `scaffold_policy_sha256` byte-unchanged); `OpencodeArm.identity` (tg2) puts
  `{"path": "$STACK_WORKDIR/tg2-gradle-home", "properties_sha256": …, "prefill_sha256": sha256 of PREFILL.json}` in its policy and
  `arm_runner._identity_inputs` passes it to `template.build`. The real tg2 `--print-identity` carries it (tested).

### 4. tg2 positives pass rule (`cmd_positives`, `p426_freeze.positives_problems`)

- Per (language, kind): `stall` → `PASS` required. `loop` / `alloc` → `PASS`; else `DECLINED` iff ALL hold (Sol P1, adapted): the
  inject_verify verdict is `not_observed*` or `FAIL:no_shell_part` (= no shell call carrying the alloc command); the run's recorded
  artifacts verify against the row's `evidence_sha256` (inject_verify's V3 check); and the row's events file holds NO tool call whose
  input contains the kind's marker (`loop`: `sleep 600`; `alloc`: `bytearray(`). Otherwise the inject_verify verdict (a FAIL); a
  `TRANSPORT_ABORT` stays a FAIL. inject_verify's stdout result line is recorded per run (`verify_result`).
- Each inject entry records `verdict` (`PASS` | `DECLINED` | the failure), and when DECLINED `declined_evidence` = {events sha256,
  marker, the verify verdict}.
- `positives_problems` (v8) accepts `DECLINED` for loop / alloc only, and only with `declined_evidence` whose verify verdict is in
  the allowed set; anything else unchanged.

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
   check on both exits before publishing, a resumed run with a changed host, an exception inside the leg region (logged, re-raised),
   `host_env.json` published (run) / kept (rehearsal), fakes without the seam unchanged, `BoxSeqOps.host_env` exists; positives:
   host change → FAIL, an inject exception → sealed FAIL record, DECLINED vs FAIL vs PASS per kind from real-shaped events (incl.
   `FAIL:rss` with no marker stays FAIL), stall never DECLINED, v8 accepts DECLINED only for loop / alloc with valid evidence; `build_env` tg2 refuses without a prefilled folder (and with a deleted cache file) and sets `GRADLE_USER_HOME` with one; the
   real tg2 `--print-identity` carries the Gradle policy; tg1 identity, argv and env unchanged (the B4b-1 tg1 golden passes unmodified); `tg2_gradle_home` prefill / check with a
   fake runner (both passes, refusal on a non-empty folder, offline failure → rc ≠ 0).
2. The stack suite passes or fails only as on the baseline.
3. (Designer, real box, after Wave 2) `prefill` rc 0 on the real universe; `check` rc 0; a tg2 positives run PASSES under the new rule.

## Non-goals

Sandboxing or network control; hashing contents of existing directories (residual: a change inside an already-present `~/.gradle` /
`~/.cargo` is not seen); npm / crate caches (downloads per item accepted, C361); the inject addenda (S26-P13: unchanged); tg1 changes.

## Open questions

None for the operator; implementation deviations follow the deviation rule: satisfy the behaviour, report any interface deviation
with its reason.

## Erratum v1.1a (change review round 1; ledger `docs/reviews/s26-agent-env/change-ledger-r1.md`)

1. §4 DECLINED (S26-P14, Sol P1 in full): DECLINED iff the inject_verify verdict is `not_observed*` AND the events hold no tool call
   carrying the marker AND the row records no kill AND the probe exited rc 0 AND `row_sha256` verifies (Sol P17). `FAIL:no_shell_part`
   and every other `FAIL:*` / `competing_trigger:*` stay failures. v8 `positives_problems` checks the same allowed set.
2. Scope extension (S26-P14): `benchmark/m62/inject_verify.py` alloc rule counts only EXECUTED shell calls carrying `bytearray(` — a call
   whose `state.status` is `"error"` and whose `state.metadata.providerCall.executed` is false (the tool-bounds plugin rejected it) is
   excluded — and requires exactly one, whose part id equals the kill's `tool_call_id`. Every other rule unchanged. Red test: the recorded
   java alloc row shape (a rejected `background: true` call, then the executed retry, one kill linked to the retry) → PASS; with the
   retry's id not equal to the kill's → `FAIL:tool_call_id`; two executed marker calls → `FAIL:no_shell_part`.
3. `BoxSeqOps.inject_verify(run, kind)` returns the retained attempt's verdict string (`PASS`, `not_observed:kill`, `FAIL:…`);
   `inject_verify_result` may keep the richer record.
4. `BoxSeqOps.host_env()` calls `host_env.fingerprint_for_run()` with no argument.
5. `tg2_gradle_home.py`'s bytes enter tg2's generation identity (Sol P18); tg1's closure does not include it.
6. `check` does not require a self-seal on `PREFILL.json` (Sol P21); its facts are checked as listed, and `prefill_sha256` binds it.
7. Documented extensions (kept): the fingerprint's `path` section; `PREFILL.json` `kind`, `path`, `properties`, `stop_rc`, per-item `error`;
   `OpencodeArm(gradle_home=…)` for tests.
8. A host-changed leg stops the run even where INVALID is expected (rehearsal R2): a host change always fails closed. After the final
   check's Stop, `main`'s existing `finally` still publishes the run files, as for every Stop; the diff is in `sequence.json`.

## Erratum v1.1b (fix round 1, implementer judgement adopted)

9. "The row records no kill" (erratum 1) means BOTH `mem_kills` and `termination.killed` are present and empty. A genuine decline
   completes normally (all six recorded declines: `stop_reason: completed`, no kill); any kill — a memory kill or a client kill —
   means the run is not a clean decline (fail closed).

## Erratum v1.1c (test-writer second delivery, T3 / D1; designer judgement)

10. The run baseline `<out-base>/host_env.json` is SEALED (self-hashed, as every sequencer record); a baseline that is unreadable or
    whose seal does not verify stops (rc 1). A nonzero probe exit makes a PASS a failure too (`FAIL:probe_rc:<n>`; stricter than §4).

## Erratum v1.1d (change verify round 2)

11. v8 `positives_problems` accepts DECLINED only when `declined_evidence.row_sha256` is 64-hex and equals the entry's `row_sha256`.
12. tg2's campaign-core closure (`benchmark/chains/c147/run_tg2_chain.py` `CORE_SPECS["probe_data"]`) includes
    `benchmark/bench/tg2_gradle_home.py` (scope extension); tg1's is unchanged.
13. Documented extension: each positives inject entry may carry `not_declined` (why a non-PASS was not declined; diagnostic only).
14. Stop messages of the guard are flat fail-closed statements (no "the operator decides" on an automatic stop).

