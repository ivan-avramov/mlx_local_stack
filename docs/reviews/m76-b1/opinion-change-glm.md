I have enough to report. Here are my findings.

---

## Findings

### F1 — Blocker: the mode-proof delta rule marks every real `f45` TQ4 leg INVALID
- **Location:** `benchmark/bench/p475_kv.py:1109-1185` (`ROUTE_RULES`, `route_proof`); spec "Mode proof"; errata v1.1 item 1.
- **Severity:** blocker.
- **Evidence:** confirmed. `route_proof` computes `deltas = exit − creation` (line 1170) and requires `deltas[k] > 0` for the "positive" counters (line 1178). `run_capacity.py:191-236` (read-only) runs the whole ladder, then `provenance.gather` records `tq4_route_counts_at_creation`, then `guard.verify()` records the exit snapshot — both after every measured request, so `exit − creation ≈ 0` on a real leg. The implementer (point 1) and the test-writer (finding 1) both confirm this by tracing `run_capacity.py`. The frozen `test_m76_b1_fe_f45_modeproof.py` tests encode delta semantics (line 70-71: *"the creation snapshot is non-zero in every counter, also in the ones that must stay put: an absolute check would refuse"*) and pass only because the fakes move counters between the two snapshots.
- **Problem:** On a real stage-1 run, `p2s`, `d2_verify`, `native:prefill`, `native:verify` (X) etc. all have delta 0, so `route_proof` emits "route counter 'p2s' delta 0 (need > 0)" and the leg is INVALID. Every X / V / XO leg fails the mode proof; no `f45` matrix can ever be complete. The instrument fails its purpose.
- **Failure scenario:** `bench.p475_kv run --campaign f45` → prepare → preflight (PASS) → legs: N16 VALID, X INVALID ("mode proof: route counter 'p2s' delta 0 (need > 0)"), V INVALID, XO INVALID → harvest → matrix writes `MATRIX.…PARTIAL.md` with rc 1 forever; stage 1 never produces a trigger verdict.
- **Proposed change:** Apply `ROUTE_RULES[arm]` to the **exit** block's absolute counters (each leg is a fresh worker, so exit counts are that leg's own counts, preload + calibration included). Keep the creation block recorded and mode-checked, keep both blocks in the receipt/dossier, keep the `fallback:*`-at-exit and mode-mismatch checks. Then revise the frozen modeproof tests to absolute semantics (they currently *reject* an absolute check by construction).

### F2 — Major (defect): the XO worker environment is not stripped/checked for `MLX_VLM_DRAFT_KIND` / `MLX_VLM_DRAFT_MODEL`
- **Location:** `benchmark/bench/p475_kv.py:1276-1299` (worker env check), `:1308` (driver env), `:355-359` (`kv_env_names`/`strip_kv`); errata v1.1 item 4.
- **Severity:** major.
- **Evidence:** confirmed. `kv_env_names` returns only `KV_*` / `TQ_*` / `STACK_DEFINED_KV_TQ_NAMES`; `MLX_VLM_DRAFT_KIND` / `MLX_VLM_DRAFT_MODEL` match none of those (`p426_secrets.py:22-26`), so `strip_kv` leaves them in the router env and the worker-env leak check at line 1280 ignores them. The candidate predates errata v1.1, which adds: on XO the worker env must not carry either name (fail before load as INVALID with the reason); the router env is stripped of both on **every** `f45` leg.
- **Problem:** On XO (predictor OFF), an inherited `MLX_VLM_DRAFT_KIND`/`MLX_VLM_DRAFT_MODEL` from the operator's environment reaches the worker. `predictor_argv_problems` only inspects argv flags, so it does not catch this. The errata notes the M77 worker refuses it — so the leg ends up INVALID via a load-time exception (`except BaseException` → INVALID) rather than a clean "before load" refusal with the named reason, and on a non-M77 worker a drafter could load under an OFF arm. The predictor-OFF boundary the request asks for is not enforced at the environment level.
- **Failure scenario:** Operator exports `MLX_VLM_DRAFT_KIND=mtp` / `MLX_VLM_DRAFT_MODEL=…` for an unrelated run; `run --campaign f45` XO leg loads, the worker refuses (M77) or silently loads a drafter (non-M77); the receipt's INVALID reason is a generic `Exception: …` from `handle.load`, not "worker environment carries MLX_VLM_DRAFT_KIND on a predictor-OFF arm".
- **Proposed change:** On `f45` legs, strip `MLX_VLM_DRAFT_KIND` and `MLX_VLM_DRAFT_MODEL` from the router env (extend the strip used for `env_base`/`spawn`), and on XO add a pre-driver check (alongside `predictor_argv_problems`) that the worker env carries neither name, raising `_Abort` with the named reason.

### F3 — Minor: trigger-line format bolds the whole phrase, not the verdict
- **Location:** `benchmark/bench/p475_kv.py:1995-1998`; errata v1.1 item 3.
- **Severity:** minor.
- **Evidence:** confirmed. The candidate emits `**stage-4 trigger: met** (…)` / `**stage-4 trigger: not met** — …`. Errata v1.1 fixes the format to `stage-4 trigger: **met**` / `stage-4 trigger: **not met** — <cells>` (bold verdict only). The verdict and the named failing cells are correct in every exercised case (test-writer finding 3); only the bold span differs.
- **Failure scenario:** A consumer grepping the matrix for `**met**` / `**not met**` (the form the errata and the frozen tests specify) misses the line; the 10 frozen `test_the_stage_4_trigger_line*` cases fail on this literal.
- **Proposed change:** `lines += ["", "stage-4 trigger: **met** (V / X decode ≥ 1.05 …)" if met else f"stage-4 trigger: **not met** — {'; '.join(failing)}", ""]`.

### F4 — Minor (scope request, not a defect): preflight records are campaign-checked beyond spec v1
- **Location:** `benchmark/bench/p475_kv.py:849-857`, `:1241-1244`; test-writer finding 2.
- **Severity:** minor (literal/extra check; errata v1.1 item 2 later requires it).
- **Evidence:** confirmed. Under `f45`, an unstamped preflight record reads as `u4` and the leg is NOT_STARTED ("preflight of X belongs to campaign 'u4', not 'f45'"). Spec v1 names only dossiers, receipts and state files as campaign-checked; errata v1.1 adds preflight records. The candidate predates the errata, so this is a self-added check. It is defensible and now spec-aligned, but it is the cause of 153 frozen-test failures (cause A) because the test fixtures pre-write preflight records without a `campaign` field.
- **Problem:** None functionally; the check is stricter and correct per errata. The only fallout is that the frozen tests' fixtures must stamp `campaign: "f45"` on pre-written preflight records (the test-writer's stamping wrapper proves this).
- **Proposed change:** Keep the check; update the frozen fixtures to stamp preflight records with `campaign` (or have the candidate's own preflight writer be the only writer). No code change to the candidate.

### F5 — Minor (behaviour change for `u4`): editing a missing key now refuses for every arm
- **Location:** `benchmark/bench/p475_kv.py:485-540` (`arm_registry_text`); implementer point 5 / judgement 5; test-writer finding 6.
- **Severity:** minor.
- **Evidence:** confirmed. The `missing` check at the end of `arm_registry_text` now refuses for any edit whose key is absent from the base entry. Before, the `u4` TQ4-OFF edit only checked `draft_kind`. The `u4` golden (bytes, argv, paths, receipt keys) is unchanged — the path is only reachable with a malformed registry.
- **Problem:** A behaviour change to `u4` beyond the request's "u4 stays byte-identical" (in outputs it does; in edit-model strictness it does not). Material consequence is nil because the committed `u4` entry has all the edited keys.
- **Proposed change:** None needed; record it in the commit message / spec note.

### F6 — Minor: `f45` per-leg wall estimates are placeholders
- **Location:** `benchmark/bench/p475_kv.py:108` (`leg_estimate_min={"N16": 25, "X": 40, "V": 40, "XO": 40}`); errata v1.1 item 5.
- **Severity:** minor.
- **Evidence:** confirmed. The spec gives no estimates; the implementer chose N16 25 min, X/V/XO 40 min. These set `driver_timeout = 3 × sum + 900 s`. Errata v1.1 says they are placeholders until the stage-1 smoke (`--expected-rung-seconds` from the smoke).
- **Problem:** A 40-min estimate for an X leg that actually runs ~76 min (the `u4` TQ4 wall) would time out a real leg. The override exists, but the defaults are unsafe for a real run.
- **Proposed change:** Pass `--expected-rung-seconds` from the smoke before any GPU leg, or raise the defaults toward the `u4` TQ4 wall (76 min) for headroom.

---

## Answers to the specific questions

- **Can an `f45` leg read/write/regenerate anything of the `u4` campaign or vice versa?** No. Isolation is solid: scratch (`m76/p475` vs `p475`), results (`benchmark/results/m76/matrix` vs `benchmark/results/p475`), leg-name regexes (`f45-…` vs `u4-…`), and campaign stamps on receipts/state/preflight are all checked on read (`load_dossier`, `load_dossiers`, `harvest`, `load_state`, `preflight`, `config_from_args`). The only shared surface is `LAST_LEG_END` over the shared idle sources (`p475`, `p426`, `m76/p475`) — intended by the spec, a timestamp only, not campaign data. A `u4` dossier under `f45` refuses (and vice versa) via `foreign_campaign` + `recorded_campaign`.

- **Can a leg be VALID with the wrong arm / mode / KV / predictor?** Not for arm/KV/predictor-argv/mode-mismatch: `run_leg` binds arm to the leg name, `arm_identity` checks the commit, `kv_line_problems` checks the KV line per arm, `predictor_argv_problems` checks argv flags, and `route_proof`/`selftest_problems` check the mode. **Except** F2: on XO a draft env var (`MLX_VLM_DRAFT_KIND`/`MLX_VLM_DRAFT_MODEL`) is not checked, so without the M77 backstop a drafter could load under an OFF arm and the leg still pass the argv/predictor check. And F1 inverts the failure: real TQ4 legs are never wrongly VALID — they are wrongly INVALID (delta ≈ 0).

- **Does the arm edit model produce exactly the specified registry text from the real committed entry?** Yes. Against the real `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` entry (`main_models.yaml:350-413`, `kv_bits: 0` at :358, `mtp_verify_scan` at :380, `draft_kind`/`draft_model` at :412-413), the candidate's diff is exactly: the `# PROVISIONAL M76 arm <ARM>` comment after the `- name:` line, `kv_bits: 0 …` → `kv_bits: 4`, `tq4_attention: <mode>` added directly below, and for XO `mtp_verify_scan` / `draft_kind` / `draft_model` commented out with value kept. The test-writer's "X/V differ by exactly the listed lines" failures (cause B) are fixture bugs — `check_arm` matches the first `kv_bits: 4` line in the file, which is the `u4` entry's (`main_models.yaml:298`), not the `f45` entry's. Adding an existing key / editing a missing key refuses as specified.

## What the tests miss

- The frozen `test_m76_b1_fe_f45_modeproof.py` tests encode **delta** semantics and explicitly reject an absolute check (line 70-71). They pass against the candidate's delta implementation and would fail against the errata-correct absolute implementation — so they cannot catch F1; they *institutionalise* the bug. A real-run integration test (or a test that takes `creation == exit`, as `run_capacity` produces) would catch it, and none exists.
- No test exercises an XO leg with `MLX_VLM_DRAFT_KIND`/`MLX_VLM_DRAFT_MODEL` in the worker env (F2) — the worker-env leak check is only exercised for `KV_*`/`TQ_*` names.
- No test asserts the trigger-line bold span against the errata form (F3); the frozen tests' regex wants `**met**`/`**not met**` and so fail, but no test pins the *correct* form positively.
- The `u4` golden covers bytes/argv/paths/receipt keys but not the edit-model's refusal strictness for a malformed `u4` registry (F5).

## What the candidate does beyond the specification

- Preflight-record campaign isolation (F4) — not in spec v1, added by the candidate, later required by errata v1.1.
- Stricter `u4` edit-model refusal (F5) — beyond "u4 byte-identical" in behaviour, though not in outputs.
- `--campaign` accepted both before and after every subcommand (compatible with "on every subcommand").
- Matrix path follows B1 (`benchmark/results/m76/matrix/MATRIX.<pick>.md`) over M76 §7's `benchmark/results/m76/MATRIX.md` (implementer point 2; correct per the B1 spec).

The only blocker is F1; F2 is the one material protection gap the request asks about (predictor-OFF boundary). F3–F6 are minor / scope.
