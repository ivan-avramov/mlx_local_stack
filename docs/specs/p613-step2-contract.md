# P613 step 2 — the Wave 1 contract (shared by implementer and test-writer)

## Goal (verbatim in every brief)

Decide, with evidence the operator can act on, whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships with MTP ON (P426; C204:
the operator makes the call from per-axis signals, no automatic pass / fail). The evidence is ONE generated, deterministic
`benchmark/results/p426/SIGNALS.md` built only from B8-accepted ON / OFF pairs: A7 tg1 (done, provisional), A1 math500, M1 256K memory,
A2 cjudge, A3 vision, A4 reasoning (step 2), the subjective panel (step 3), then the final sheet + a recommendation (step 4).

Step 2 means: `bench/p426_verify.py` gains the Wave 1 adapters (A1, A2, A3, A4, M1) and the rule-6 cross-wave code check, and one
`all` command writes ONE `B8.json` covering A7 + Wave 1; `bench/p426_signals.py` gains the Wave 1 sections and one `all` command
writes ONE `SIGNALS.md` + `SIGNALS.json` (A7 as in step 1, plus A1, M1, A2, A3, A4, the complete mechanical family, the Wave 1 flags),
byte-identical from the same inputs. The subjective panel (spec §4.5 / §5) stays "pending (step 3)".

Specification: `docs/specs/p613-b8-b6-signals.md` v2 (spec). Step-1 contract: `docs/specs/p613-step1-contract.md` (its A7 rules,
interfaces and outputs are unchanged and stay green). Step 2 implements spec §2 (Wave 1 rows), §3 rules 1–4, 6, 7 for Wave 1, §4.1–4.3,
4.6, 4.7, 4.10, 4.11, 4.12 for Wave 1, §6 for what step 2 covers. Where this file and the spec differ, this file wins for step 2.

## Roots

- `results_root` = a directory laid out like `benchmark/results/p426/` (as step 1).
- `rows_root` = a directory laid out like `benchmark/results/` (holds `<entry>/` and `p426/`). Must resolve equal to
  `bench.generate.results_root()`, else `RefusalError` (A1 regrades through `bench.grade`, which reads `generate.results_root()`; tests
  set `generate.RESULTS` by monkeypatch, the repo convention). `results_root` must resolve equal to `rows_root / "p426"`, else refusal.
- `repo` = a git work tree whose objects contain both Wave 1 heads and the Wave 2 OFF commit (rule 2 registry check, rule 6).
- `ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"`. Blocks `b1`, `b2`. Arms `off`, `on`. Tune `p426s2-<arm>-<block>`;
  leg `<kind>-p426s2-<arm>-<block>`, kind ∈ {math500, cjudge, vision, reasoning, m1}.

## Data (real, committed; format reference — read-only)

- `p426/wave1.s2/run/frozen.s2.json`: `stack_head_off`, `stack_head_on`, `registry_off_sha`, `registry_on_sha`, `mlx_vlm`,
  `mlx_serve`, `production_ref`, `uv_lock_sha256`, `bench_lock_sha256` (no self-hash field).
- `p426/wave1.s2/<leg>/<leg>.receipt.json` (no self-hash): `name`, `arm`, `kind` (`qualify` for m1), `verdict` ("VALID"),
  `speed_valid` (bool), `problems` [], `speed_problems` [], `pins` (frozen copy + `frozen_sha`), `state.stack_head`, `started` /
  `ended` (`YYYY-MM-DD HH:MM:SS`, naive local). Router legs: `worker.cmdline` (one string: PID, interpreter, script, args; the
  `--generation-defaults` value is JSON with spaces), `log` {`started`, `completed`, `failed`, `overlapping`}. M1 legs: no `worker` /
  `log`; `report` / `overlay` key lists.
- `p426/wave1.s2/<leg>/SCRUB_MANIFEST.json`: `files` {repo-relative path `benchmark/results/…`: {`published_sha256`, …}}.
- `<entry>/math500.<tune>.jsonl` (50 rows / block), `<entry>/cjudge.<tune>.jsonl` (20): fields `id`, `sample`, `sampler_seed`, `content`,
  `content_sha256`, `answer_gold`, `finish_reason`, `converged`, `nonconv_kind`, `decode_tps`, `completion_tokens`, `thinking_budget`,
  `draft` {`draft_kind`, `draft_n`, `draft_n_accepted`, `draft_rounds`} (OFF: all four null), optional `error`.
- `<entry>/math500.<tune>.score.json`: `n`, `errors`, `correct`, `acc`, `acc_strict`, `conv_rate`, `nonconv_kinds`.
  `<entry>/<bench>.<tune>.manifest.json`: `sampling`, `kv`, `runtime`, `registry.sha256`, `tune` (grading reads `kv.max_kv_cache_size`,
  `sampling.max_tokens`).
- `<entry>/vision_gate.<tune>.jsonl` (10): `id`, `seed`, `image_sha256`, `description`, `verdict` (model self-check), `converged`,
  `finish_reason`, `decode_tps`, `draft`, `turn2` {…, `seed`, `draft`}.
- `<entry>/reasoning.<tune>.json`: `records[0]` {`accuracy`, `samples`, `budget_hits`, `errors`, `acceptance_pooled`, `rows` [3]};
  row: `seed` (task seed), `sampler_seed`, `trial`, `score`, `budget_hit`, `finish_reason`, `content`, `decode_tps`, `draft`.
- `p426/wave1.s2/<m1 leg>/m1/<entry>/result.json`: `status` ("ok"), `served` {`draft_kind`, `drafter_loaded`, `verify_policy`, `kv`,
  `session_max`, …}, `snapshots` {`--model`, ON also `--draft-model`}, `requests[0].qualify` {`peaks` {`prefill`, `decode`, `retire`}
  (bytes), `rates` {`prefill_tps`, `decode_tps`}, `generate_seed`, `generation_tokens`, `prompt.sized.{sha256,tokens}`,
  `finish_reason`, `backend`}. `…/m1/<entry>/job.json`: `argv` (list), `expect`. `…/m1/report.json`: `predictor`, `reviewed_head`,
  `registry_sha256`, `production`, `versions`, `end_problems`.
- `p426/ids.json`: `axes.{math500,cjudge,vision}.{block1,block2}` (id lists), `axes.reasoning.{block1,block2}` (task seeds) and
  `axes.reasoning.request_seeds` {task seed (str): request seed} (erratum 2026-11-04: the location made explicit).
- Excluded: `p426/wave1/` (S build), tunes `p426-*`, every `*-smoke` leg / tune (listed in coverage, never scored),
  `p426/wave1.s2/archive/` (listed as superseded). A pair member resolving to any of them → `RefusalError`.

## B8 — Wave 1 rules (each rejection names the pair, the rule and both values)

Pair = (kind, block). Key: A1 / A2 (block, `id`, `sampler_seed`); A3 (block, `id`, `seed`); A4 (block, task `seed`, `sampler_seed`);
M1 (block). Inputs: every file read, `{repo-relative-to-rows_root path: sha256}` in `inputs`.

1. **Validity.** Both receipts `verdict == "VALID"`, `problems == []`, `name` / `arm` / `kind` match the path; else the pair is rejected.
   `speed_valid` false → pair stays, labelled "power-invalid" (rule 4). Every SCRUB_MANIFEST path under `benchmark/results/` re-verifies
   against `rows_root` (`published_sha256`); a mismatch or missing file rejects the pair.
2. **Arm identity.** (a) Receipts: `pins` without `frozen_sha` equal across the pair and equal to `frozen.s2.json`; `pins.frozen_sha`
   == `state.frozen_sha` == sha256 of the `frozen.s2.json` bytes (golden `3c155062…`); `state.stack_head` == `stack_head_<arm>`.
   (b) Registry: sha256 of `git show <stack_head_<arm>>:main_models.yaml` == `registry_<arm>_sha` (opened, not trusted; a head that does
   not resolve → refusal); M1 `report.registry_sha256` == `registry_<arm>_sha`; row manifests `registry.sha256` ==
   `registry_<arm>_sha`. (c) Worker argv: split on `" --"` after dropping the PID token; normalise the arm worktree path component
   `stack-p426-s2-<arm>` → `stack-p426-s2-ARM`; multiset ON − OFF == exactly {`--draft-kind mtp`, `--draft-model
   caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter`, `--mtp-verify-scan joint_v1`}, OFF − ON == ∅. M1: the same on
   `job.json` `argv` (flag + value pairs). (d) Everything else equal: manifests `sampling`, `kv`; rows `thinking_budget`; M1 `served`
   except {`draft_kind`, `drafter_loaded`, `verify_policy`}, `snapshots` except `--draft-model`, `report` `reviewed_head` / `production`
   / `versions`, `qualify` `generate_seed` / `prompt.sized`. OFF rows: every `draft` value null; ON rows: `draft_kind == "mtp"`,
   `draft_n > 0`, `0 ≤ draft_n_accepted ≤ draft_n`.
3. **Keys.** Row ids per arm == the `ids.json` block list (as sets; duplicate key → `RefusalError`; count ≠ block size → refusal); A4
   task seeds == the block list and each `sampler_seed` == `request_seeds[str(seed)]`; keys equal across arms (a key in one arm only, or a
   seed mismatch → that key rejected; pair stays). Blocks of one kind are disjoint (asserted; overlap → refusal).
4. **Speed.** Per block: both `speed_valid` → speed inference; else the block leaves it; one valid block → "descriptive, not
   order-balanced".
6. **Cross-wave code check** `cross_wave(repo, wave1_off, wave2_off)` with wave1_off = `frozen.s2.json` `stack_head_off`, wave2_off =
   `wave2/run/v8_base.json` `off_commit`. Paths = `main_models.yaml`, `src/mlx-vlm`, `src/mlx-serve`, and the union over both commits of
   `bench.identity_closure.python_closure` of `benchmark/run.py`, `benchmark/vision_gate.py`, `benchmark/bench/run_reasoning.py`, each
   computed on that commit's `*.py` tree (`git archive <sha> -- ':(glob)**/*.py'` into a temporary directory). `files` = `git diff
   --name-only <wave1_off> <wave2_off> -- <paths>` run at the repo top (pathspecs are cwd-relative). The M1 `qualify` entry is
   `src/mlx-vlm/dev/p369_phase2/qualify.py`: covered by the `src/mlx-vlm` gitlink (recorded as such). Also recorded (evidence, never a
   gate): `entry_equal` = the parsed `models` entry named ENTRY equal at both commits; `globals_equal` = parsed top-level keys other than
   `models` equal; `closure_files` (sorted). `files` non-empty → `flag: true` (not a refusal). Either commit unresolvable → refusal.
7. **C217 identity.** A1 / A2: `content_sha256`, recomputed as sha256(`content` UTF-8) and required equal to the field (mismatch →
   refusal); A3: sha256 of `description`; A4: sha256 of `content`; M1: none. ON == OFF → key `identical: true`.

## B6 — Wave 1 definitions

- **A1 per item.** `bench.grade.grade("math500", ENTRY, tune=<tune>)`: lenient = `items[].score`, strict = `strict_items[].score`.
  Regraded `n`, `errors`, `correct`, `acc_strict` must equal `math500.<tune>.score.json`, else `RefusalError` ("regrade drift").
  Convergence = `convergence.is_converged` as `grade` applies it. Per block and both blocks: per arm `acc`, `acc_strict@81920` over
  the block's planned items (denominator = block size), conv %, `nonconv_kinds`; paired ON − OFF (`stats.paired_delta`, dict
  per-item inputs `{id: [score]}`, iters 10000, seed 426; read `delta`, `lo`, `hi`, `degenerate`, `discordance_upper95` only); MDE /
  label / loss bound as step 1; exclusive solves (ON-only, OFF-only strict ids). Permutation (step-1 `permutation_p`) on the both-block
  strict differences, sorted by (block, id).
- **Mechanical family** {A1 (both blocks), A7-s1, A7-s2}, `stats.holm`, m = 3, label "complete"; A7 raw p from the step-1 computation.
- **A2.** Mechanical quality N/A (grader `acc: null`; labelled "panel only (step 3)"); per arm conv %, `nonconv_kinds`, errors.
- **A3.** Self-pass (`verdict == "PASS"`) counts per arm, labelled "self-check, lenient, descriptive"; conv % (turn 1).
- **A4.** Descriptive, never tested: per arm and block the draws (task seed, `score`, `budget_hit`, `finish_reason`); strict draw =
  `score == 1.0` and `budget_hit is False` and `finish_reason == "stop"`; counts.
- **Speed** (A1, A2, A3 turn 1, A4 per draw): ratio ON / OFF of `decode_tps` per key; geomean + item-bootstrap CI via step-1
  `geomean_ratio_ci`, per block and both blocks (keys sorted (block, key)); a key with a missing / non-positive rate in either arm is
  dropped and listed. **Acceptance** = Σ `draft_n_accepted` ÷ Σ `draft_n` over ON rows (A3: turn 1 only), per block and both blocks.
  **Leg wall** = `ended − started` seconds (naive local, descriptive, labelled so).
- **M1.** Per leg the three peaks (bytes and GB = bytes / 1e9, 3 dp), `rates`; ON − OFF per block and mean of both blocks; decode
  ratio ON / OFF per block (descriptive). Acceptance: "not recorded" (no counters in `result.json`).
- **Identity** (for step 3): per axis and block the count of `identical` keys over keys; printed.
- **Coverage.** Per kind: full legs VALID / invalid; smokes listed; `archive/` attempts listed superseded.
- **Flags (Wave 1), each with its number and items:** A1 point < −5 pp (per block, both); A1 Holm p < .05 with OFF better; A1 decode
  ratio point < 1.3; acceptance < 0.70 per axis × (block, both) for A1, A2, A3, A4; M1 ON prefill peak > OFF + 2e9 bytes or > 48e9
  bytes (per block); a `nonconv_kind` present in ON and absent in OFF (per axis, block); B8 cross-wave `flag` (with `files`,
  `entry_equal`, `globals_equal`).

## Interfaces

`bench/p426_verify.py` (step-1 functions and the `a7` command unchanged)
- `verify_wave1(results_root, rows_root, repo) -> dict` → `{"axis": "wave1", "inputs": {path: sha}, "pairs": [{"kind", "block",
  "off": leg, "on": leg, "accepted": bool, "reasons": [str], "speed_valid": bool, "keys_accepted": int, "keys_rejected": [{"key",
  "reason"}], "identical": {"n": int, "of": int}, "keys": [{"key": [...], "identical": bool}]}]}` for kinds × blocks (10 pairs).
- `cross_wave(repo, wave1_off, wave2_off) -> {"wave1_off", "wave2_off", "paths": [...], "closure_files": [...], "files": [...],
  "flag": bool, "entry_equal": bool, "globals_equal": bool, "qualify": "covered by gitlink src/mlx-vlm"}`.
- `verify_all(results_root, rows_root, repo) -> {"axes": {"A7": verify_a7(...), "wave1": verify_wave1(...)}, "cross_wave": {...},
  "inputs": union}`.
- CLI `python -m bench.p426_verify all --results-root <p426 dir> --rows-root <results dir> --repo <git top> --out <B8.json>`; rc 0 /
  rc 2 + `REFUSED: <reason>`, nothing written (as step 1).

`bench/p426_signals.py` (`a7` command unchanged)
- `compute_all(results_root, rows_root, b8, b8_sha256=None) -> dict` (refuses on any input sha drift vs `b8["inputs"]`, as step 1;
  A7 part = `compute_a7` on `b8["axes"]["A7"]`).
- CLI `python -m bench.p426_signals all --results-root … --rows-root … --b8 … --out-md … --out-json …`.
- Header: generator, version `p613-step2`, status `PROVISIONAL — subjective panel pending (step 3)`, numpy / scipy versions, B8 sha,
  inputs sha set. Sections in order: A7-s1, A7-s2, A1, M1, A2, A3, A4, mechanical family, flags, noise floor, coverage, pending
  (4.5 subjective). Every number has a JSON path. No absolute path, no generation time; byte-identical on rerun.
- Committed outputs become the `all` outputs: `benchmark/results/p426/{B8.json,SIGNALS.md,SIGNALS.json}`.

## Golden (counted from the committed data with the definitions above, 2026-11-03)

- B8: 10 / 10 Wave 1 pairs accepted, all `speed_valid`; keys A1 50 + 50, A2 20 + 20, A3 10 + 10, A4 3 + 3, M1 1 + 1; identical A1 50/50
  + 50/50, A2 20/20 + 20/20, A3 10/10 + 10/10, A4 3/3 + 3/3 (166 / 166); SCRUB files 249 / 249 re-verify; `content_sha256` 280 / 280.
- Rule 6: `files == ["main_models.yaml"]`, `flag: true`, `entry_equal: true`, `globals_equal: true`, `closure_files` 34, gitlinks equal.
- A1 strict = lenient: b1 OFF 49/50, ON 49/50; b2 OFF 47/50, ON 47/50; conv 100 % all; `nonconv_kinds` {} all; exclusive solves none;
  paired delta 0, lo 0, hi 0, degenerate per block and both; loss bound = exact bound 5.82 pp (n 50), 2.95 pp (n 100); MDE `mde(50)`
  0.1772, `mde(100)` 0.1253 (zero discordance → default row); permutation p 1.0; Holm m 3, all adjusted p 1.0.
- Decode geomean ratio points: A1 b1 1.736, b2 1.729; A2 1.606, 1.543; A3 1.775, 1.727; A4 per draw b1 1.615, 1.623, 1.584; b2 1.656, 1.634, 1.528 (erratum 2026-11-04: was "1.584–1.656", b2's 1.528 omitted).
- Acceptance: A1 0.7490 / 0.8038 / both 0.7666 (106153 / 138464); A2 0.5869 / 0.6128 / both 0.6015; A3 0.6343 / 0.5996 / both 0.6168;
  A4 634/708 = 0.8955, 604/680 = 0.8882 (equals `acceptance_pooled`).
- A2 conv 20/20 each arm and block; A3 self-PASS 10/10 each; A4 strict draws 3/3 each arm and block, budget hits 0.
- M1 peaks (bytes): OFF b1 = b2 prefill 37658578482, decode 37557075522, retire 37935199774; ON b1 prefill 37972876142, decode
  37926799772, retire 38251713408; ON b2 the same except retire 38251715456; ON − OFF prefill +314297660 (0.314 GB) both blocks; decode
  ON / OFF b1 16.019 / 13.361, b2 16.041 / 13.412 tok/s.
- Flags expected from Wave 1: acceptance < 0.70 for A2 (b1, b2, both) and A3 (b1, b2, both); cross-wave. No other Wave 1 flag.

## Tests

Hermetic fixtures under `tmp_path` (a synthetic `rows_root` with `p426/` + `<entry>/`, a tiny git repo for rules 2b / 6, `generate.RESULTS`
monkeypatched): one per rule (accept + each rejection / refusal), regrade-drift refusal, deny-listed members, argv normalisation, the
rule-6 flag both ways (a closure file change, a non-generation file change outside the paths → no flag), the identity recomputation,
each Wave 1 flag raised and not raised, A4 never tested, byte-identical `all` regeneration, `a7` outputs unchanged. Golden (marker
`p613s2_golden`, reads committed data): the numbers above. Test dir: `benchmark/bench/tests/p613s2/`. Command (from `benchmark/`):
`../.venv-bench/bin/python -m pytest -q -p no:cacheprovider <paths>`. Accept also needs the full local gate on the commit.
