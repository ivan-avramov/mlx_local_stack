Verdict: **SHIP-WITH-RESIDUALS**

**F1 — should-fix — `benchmark/bench/agentbench_compare.py:138`**  
The gate trusts manifests without checking rows. Rows carrying bases 0/1000 with manifests both declaring 0 produce `comparable=True`. A mistaken `--manifest` override or concatenated session file therefore bypasses the seed gate. Direct `pairwise_stats()` also accepts different bases; duplicate item IDs collapse to the last row. Minimal fix: validate row bases and derived `sampler_seed` against the effective manifest base, reject duplicate IDs, and guard direct pairing. **VERIFIED-BY-RUNNING**; duplicate-ID behavior **VERIFIED-BY-READING**.

**F2 — should-fix — `benchmark/bench/agentbench_compare.py:83`**  
Explicit `seed_base: null` becomes zero. Only an *absent* key establishes legacy base zero. `"0"` versus integer `0` refuses conservatively, but two `"0"` values pass without type validation. Minimal fix: distinguish absence from null; require present values to be nonnegative integers, excluding booleans. **VERIFIED-BY-RUNNING**.

**F3 — note — `benchmark/bench/run_agentbench_os.py:850`**  
Validation exists only in `main()`. Directly calling `run_generate()` with parser-produced arguments lacking the flag reaches M50; if prerequisites pass, it hashes `base=None` and records null. That is a different schedule from zero. No production repository caller bypassing `main()` was found. Minimal fix: validate at the generation boundary too. Router-check bypass **VERIFIED-BY-RUNNING**; subsequent generation **VERIFIED-BY-READING**.

**F4 — should-fix — `benchmark/bench/tests/test_run_agentbench_os.py:2206`**  
The seed tests replace `AB.run_task`. Dropping or resetting seeds inside the adapter, loop, or HTTP client would leave every C125 test passing. Minimal fix: add a mocked-transport test through the real adapter/loop/driver, capturing request bodies across ordinary turns and reprompts. **VERIFIED-BY-READING**; the independent positive check described below **VERIFIED-BY-RUNNING**.

**F5 — note — `benchmark/README.md:333`**  
“Distinct base per session,” repeated in the module docstring and specification, omits the same-seed reload-control exception. Minimal fix: explicitly require distinct bases for the two independent sessions and reuse the relevant base for its reload control. Otherwise the changed documentation matches the CLI. **VERIFIED-BY-READING**.

**F6 — note — `benchmark/bench/provenance.py:1301`**  
The full suite is not green with temporary files under `STACK_WORKDIR`: four transcript-path tests fail. Encoding uses `resolve_stack_workdir`; decoding uses the separately monkeypatched `stack_workdir`, duplicating path components. Minimal fix: make the test fixture’s two resolvers consistent. Failures **VERIFIED-BY-RUNNING**; mechanism **VERIFIED-BY-READING**. No pre-change baseline was run.

Requested checks:

| Check | Result |
|---|---|
| **1. Every-turn propagation** | `run_agentbench_os:1082` → `AB.run_task:2728` → `agent_loop:183` → `DualSubmitDriver:2353` → `driver:22` → `client:114`. Three-turn mocked requests retained the base-derived seed, including a no-tool-call reprompt. **VERIFIED-BY-RUNNING**. Transport errors terminate; there is no model retry. Gold preparation/evaluation executes shell scripts, without model requests. Container randomness is not controlled by this sampler seed. **VERIFIED-BY-READING**. Actual server consumption remains an **ASSUMPTION**; no server contacted. |
| **2. Generation routes** | CLI resume, limit and pilot paths all pass the flag check and common seeded loop. `--pilot-seed` changes selection/order only. Existing valid rows without `--resume` refuse. Rate helpers read evidence; live smoke tests shells; watch monitors rows. No AgentBench pilot-twice generator or additional production `run_generate` caller found. **VERIFIED-BY-READING**. Internal API exception: F3. |
| **3. Resume identity** | Missing/unreadable manifests, absent/null base and changed base refuse; matching base passes. **VERIFIED-BY-RUNNING**. Requiring structural presence matches other identity keys. Empty `done_ids` skips identity checking, but implies no parsed ID-bearing rows: only blank, ID-less or torn content can remain. It cannot mix two valid generated schedules through that case. Existing row seed fields themselves are not validated. **VERIFIED-BY-READING**. |
| **4. Comparison/pooling** | Legacy absence → zero is sound: the old call used the function’s default `base=0`. Report generation gates both descriptive and paired statistics. Direct pairing bypasses it; see F1/F2. **VERIFIED-BY-RUNNING/READING**. Generic `bench.compare` has no seed gate, but its grader does not support `agentbench_os`, so it cannot currently produce this comparison. Scoreboard selects the largest variant; it neither pairs sessions nor pools their accuracy. **VERIFIED-BY-READING**. |
| **5. Ordering** | Missing/negative generate bases refuse before operational reads, writes, Docker or M50. Literal “before any disk read/write” is too strong: Python imports precede validation and ordinary execution can write bytecode. `--prepare --seed-base -1` dispatches successfully; preparation ignores the supplied integer. **VERIFIED-BY-RUNNING/READING**. |
| **6. Tests** | All 14 C125 cases pass; limitations and mutations below. |
| **7. Docs** | F5 is the changed-text qualification needed. |
| **8. Misattribution** | F1–F3 are the identified routes. No wrong-seed request found through validated CLI generation. |

Each new test’s sensitivity, **VERIFIED-BY-READING**. Names below omit `test_` and `_C125`:

| Test | Detects / can miss |
|---|---|
| `generate_without_seed_base_refuses_before_anything` | Detects missing refusal or early mocked router/Docker/task call; misses disk reads and writes outside `tmp_path`. |
| `negative_seed_base_refused` | Detects accepting `-1` or early router call; does not directly trap HTTP/Docker. |
| `prepare_works_without_seed_base` | Detects requiring the flag for preparation; does not test supplied values. |
| `migrate_exclusions_works_without_seed_base` | Checks dispatch only; migration is mocked. |
| `item_seed_follows_seed_base` | Detects ignoring base before `AB.run_task`; misses downstream loss. |
| `seed_base_zero_reproduces_the_legacy_seed` | Checks adapter input against the current default hash; has no fixed historical numeric oracle. |
| `manifest_and_rows_record_seed_base_and_sampler_seed` | Detects incorrect row seed/base or missing manifest base; misses downstream request changes. |
| `resume_same_seed_base_continues` | Checks successful continuation and observed IDs; does not assert each task ran exactly once. |
| `resume_refuses_different_seed_base` | Detects removing seed from identity enforcement; verifies no task runs. |
| `resume_refuses_legacy_manifest_without_seed_base` | Detects treating missing resume base as zero; does not cover null/unreadable manifests. |
| `check_comparability_refuses_differing_seed_bases` | Detects dropping the manifest comparison; misses contradictory rows. |
| `check_comparability_equal_seed_bases_is_clean` | Detects unconditional refusal; alone also passes with no seed gate. |
| `check_comparability_legacy_missing_seed_base_counts_as_zero` | Checks missing/zero and missing/nonzero in both arm orders; omits explicit null/string cases. |

Concrete mutation outcomes, reasoned from those assertions:

- Reset seed inside `client.probe()` → **all C125 tests still pass**.
- Record `sampler_seed = item_seed + 1` → **recording test fails**.
- Keep the resume identity key but omit manifest `runtime.seed_base` → **recording and same-base continuation tests fail**.

Checks actually run:

- Scoped six-file diff; repository Python/shell caller searches; adapter, loop, client, resume, helper and comparison tracing.
- Full requested pytest pair, with bytecode/cache writes disabled and `TMPDIR="$STACK_WORKDIR"`:
  ```text
  4 failed, 180 passed, 2 warnings in 19.86s
  ```
  Failures: `test_resume_reuses_the_same_run_id_transcripts_dir_P29`, `test_resume_does_not_rewrite_an_existing_transcript`, `test_manifest_records_transcripts_dir`, `test_transcripts_dir_defaults_to_stack_workdir_m54_transcripts_model`.
- Same pair with `-k C125`:
  ```text
  14 passed, 170 deselected, 2 warnings in 4.19s
  ```
- Mocked real adapter → loop → driver → HTTP-body capture:
  ```text
  base=0:    [1067807066, 1067807066, 1067807066]
  base=1000: [2147425001, 2147425001, 2147425001]
  base=2000: [1561840445, 1561840445, 1561840445]
  ```
  Each completed three turns and passed.
- In-memory adversarial probes:
  ```text
  COMPARE None vs 0: []
  COMPARE '0' vs '0': []
  MISMATCHED ROW BASES 0/1000 WITH MANIFESTS 0/0: comparable=True
  DIRECT pairwise_stats BASES 0/1000: comparable=True
  RESUME missing/null/different: REFUSED
  RESUME same: ACCEPTED
  RESUME manifest absent/unreadable: REFUSED
  DIRECT run_generate without seed_base: router check reached
  ```