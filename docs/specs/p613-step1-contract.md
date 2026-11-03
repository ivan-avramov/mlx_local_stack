# P613 step 1 — the A7 contract (shared by implementer and test-writer)

## Goal (verbatim in every brief)

P426 decides whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships with MTP ON. Its primary workload, the tg1 opencode
benchmark (axis A7), ran as Wave 2c: 8 legs and 4 pair dossiers committed under `benchmark/results/p426/wave2/`. The operator's
decision needs a generated, deterministic signals sheet computed only from ON / OFF pairs a verifier accepted, with the
pre-registered statistics. Solving it means: `bench/p426_verify.py` decides which A7 pairs are comparable (fail closed, every
rejection with its reason) and `bench/p426_signals.py` computes the A7 signals of spec v2 and writes `SIGNALS.md` +
`SIGNALS.json`, byte-identical from the same inputs. Step 1 is A7 only; the Wave 1 axes come later.

The specification is `docs/specs/p613-b8-b6-signals.md` v2 (in the copy). Step 1 implements its A7 parts: §2 (allow / deny, the
A7 row), §3 rules 1–5 and 7 (rule 6 and the Wave 1 rules are later steps), §4.1–4.4 and 4.7–4.12 as they apply to A7 (§4.5 / §4.6
are later steps: the sheet lists them as "pending"), §6 for what step 1 covers. This file pins the interfaces and the A7 field
mapping; where it and the spec differ, this file wins for step 1.

## Data (real, committed; use it as the format reference — read-only)

`results_root` = a directory laid out like `benchmark/results/p426/` (tests use a `tmp_path` copy or synthetic fixtures).

- `wave2/run/v8_base.json`: `off_commit`, `on_commit`, `gitlinks`, `sha256` (self-hash).
- `wave2/run/sequence.json`: `legs` [{leg, attempt, state}], `pairs` [{pair, off, on, dossier, verdict, published}].
- `wave2/pairs/<pair>__off-a1__on-a1.json` (pair ∈ pilot, s1, s2, reload): `pair`, `verdict` ("PASS"), `arms` {off, on: {attempt,
  harvest_sha256, receipt_sha256, …}}, `differences` [{field, off, on, …}], `sha256`.
- `wave2/tg1-p426-{off,on}-{pilot,s1,s2,reload}.a1/` (an attempt):
  - `leg.json`: `state` ("VALID"), `speed_valid` (bool), `started`, `ended` (ISO-8601 Z), `sha256`.
  - `chain.json`: `artifacts.campaign_core.commit` (the arm's commit), `p426_dnf` (list; DNF records), `rc`, `status`.
  - `HARVEST.json`: `files` [{destination "main" | "evidence", published (repo-relative path), published_sha256, …}], `sha256`.
    Only `destination == "main"` files are verifiable from `main`; re-verify each against `results_root`'s repo-relative path.
  - `schedule.json`: planned slots = Σ over `blocks[].legs[].invocations[]` of `len(names)` (43 for s1 / s2, 5 for pilot / reload).
  - `<session>/*.jsonl` (session = pilot | s1 | s2 | reload): one row per slot. Row fields used: `id` (`<language>/<item>`),
    `sampler_seed` (int), `passed` (bool), `converged` (bool), `nonconv_kind` (str | null), `nonconv_flags` (list of str),
    `file_changed` (bool), `test_modified` (bool), `tool_bounds_rejections` (int), `wall_s` (float), `final_tree` {`manifest_sha256`, …}.
  - `items/<…>__<session>__<language>__<item>.json` (NOT `*.ready.json`): `slot`, `totals` {`requests`, `generated_tokens`,
    `decode_s`, `accepted`, `proposed`, `prompt_tokens`, `decode_rate_source`}, `requests` [{`generated_tokens`, `decode_tok_s`,
    `draft_n`, `draft_n_accepted`, `error`, …}].
- Self-hashes: reuse the repository's own canonical-hash helper used by these records (`bench.p426_harvest._canon_sha`); never
  reimplement hashing differently.
- The superseded namespace `wave2.v8-4104c7fc/` (same layout) is read ONLY for the cross-epoch noise floor (§4.9).

## Definitions

- strict success (`acc_strict@budget`) = `passed is True and converged is True`; `acc` (lenient) = `passed is True`. A slot in
  `p426_dnf` without a row = non-success for that arm (both measures), labelled `transport_dnf`. Denominator = planned slots.
- Pair = (session, `id`) present in both arms with equal `sampler_seed`; a seed mismatch or a missing slot is a rejected pair key.
- Paired ON − OFF: `bench.stats.paired_delta(on_per_item, off_per_item, iters=10000, seed=426)` with per-item lists of one 0/1
  value; read only `delta`, `lo`, `hi`, `degenerate`, `discordance_upper95`.
- Permutation p: d_i = on_i − off_i; T = mean(d); `numpy.random.default_rng(426)` draws a (10000, n) matrix of ±1;
  p = (1 + #{|mean(s·d)| ≥ |T| − 1e-12}) / 10001. n = 0 → p = 1.0.
- Holm: `bench.stats.holm` over the mechanical family members present ({A7-s1, A7-s2} in step 1), labelled
  "PROVISIONAL: family incomplete (A1 pending)".
- MDE: `bench.stats.mde(n, p_d)` with p_d = discordant pairs / n; when that is 0 report `mde(n)` (default 0.20) and say so.
- Label: lo > 0 or hi < 0 → "shown difference"; else "WASH — directional (not a shown difference)". Loss bound =
  `bench.compare_predictor._loss_bound(paired_delta_result)` in pp; > 10 pp → "loss not ruled out above X pp".
- Runaway tax per arm and session: counts of items whose `nonconv_flags` or `nonconv_kind` contains budget_hit, turn_cap,
  exec_timeout, client_inactivity, looping, stalled (each its own category) + the union (items with any). C269 sensitivity: the
  paired delta without pairs where either arm's `nonconv_kind == "client_inactivity"`.
- Speed per item (both arms): primary = (`totals.generated_tokens` − `totals.requests`) / `totals.decode_s`; sensitivity = Σ
  (gen − 1) / Σ ((gen − 1) / `decode_tok_s`) over request records with `decode_tok_s` > 0 and gen ≥ 1. Paired ratio ON / OFF per
  item; statistic = geometric mean of ratios; 95 % interval = percentile bootstrap over items (10,000, `default_rng(426)`). Items
  with no usable rate in either arm are dropped and listed. Acceptance (ON) = Σ `totals.accepted` / Σ `totals.proposed` per session.
- Wall: per leg `ended − started` (seconds) from `leg.json`, descriptive.
- Noise floor: same-epoch = per arm, items of `-reload.a1` vs `-pilot.a1` whose (`passed`, `converged`) differ / 5. Cross-epoch =
  per arm and attempt with an equal `schedule.json` sha256 in both namespaces and `leg.json` VALID in both: flips / common items;
  both v8 `sha256` values printed.
- Flags (A7): session point < −5 pp; Holm-adjusted p < .05 with OFF better; decode ratio point < 1.3; acceptance < 0.70; a
  runaway-tax category present in ON and absent in OFF (per session). Each flag carries the number that raised it.

## Interfaces

`bench/p426_verify.py`
- `verify_a7(results_root: Path) -> dict` → `{"axis": "A7", "inputs": {relpath: sha256}, "pairs": [{"pair": session, "off":
  attempt, "on": attempt, "accepted": bool, "reasons": [str], "keys_accepted": int, "keys_rejected": [{"key": [session, id],
  "reason": str}], "speed_valid": bool}]}` for sessions s1 and s2 (pilot / reload appear with `"role": "diagnostic"`).
- Rules: rule 1 (`leg.json` state VALID; else rejected with reason; a deny-listed or missing attempt → refusal), rule 2 (the dossier
  `differences` fields ⊆ {"snapshots.drafter", "argv.worker"}; `chain.json` commits equal `v8_base` off / on commits), rule 3 (keys),
  rule 4 (`speed_valid` both), rule 5 (dossier present, self-hash OK, verdict PASS, names both attempts; every HARVEST "main"
  file re-verifies), rule 7 (identity key = the row's `final_tree.manifest_sha256`, null when absent; ON == OFF → the pair key is marked
  `identical: true`, recorded for step 3).
- `RefusalError(Exception)` for structural problems: missing / unreadable required file, duplicate row key, row count ≠ planned
  slots, a deny-listed path. A rejected pair is NOT a refusal.
- CLI: `python -m bench.p426_verify a7 --results-root <dir> --out <B8.json>` → rc 0 (written, `json.dumps(sort_keys=True,
  indent=1)` + "\n"); rc 2 + one stderr line `REFUSED: <reason>` and nothing written.

`bench/p426_signals.py`
- `compute_a7(results_root: Path, b8: dict) -> dict` (refuses with `RefusalError` from p426_verify when any `b8["inputs"]` sha
  differs from the file now, or a required input is missing).
- `render_md(signals: dict) -> str`; `permutation_p(diffs: list[float], iters=10000, seed=426) -> float`;
  `geomean_ratio_ci(ratios: list[float], iters=10000, seed=426) -> dict(point, lo, hi, n)`.
- CLI: `python -m bench.p426_signals a7 --results-root <dir> --b8 <B8.json> --out-md <SIGNALS.md> --out-json <SIGNALS.json>` →
  rc 0; rc 2 + `REFUSED: <reason>`.
- Outputs contain no wall-clock time of generation and no absolute path (relative to `results_root`); header: generator name,
  `PROVISIONAL — A7 only`, numpy and scipy versions, B8.json sha256, inputs sha set.
- Golden on the committed data (`benchmark/results/p426`): strict-input pass counts s1 OFF 42/43, ON 41/43; s2 OFF 41/43, ON 43/43;
  same-epoch noise floor 0 / 5 both arms; B8 accepts s1 and s2.

Test command (from `benchmark/` in the copy): `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider <paths>`
(`bench` imports resolve from the copy's `benchmark/`).
