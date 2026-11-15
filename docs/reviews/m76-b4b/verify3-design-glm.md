Now I have enough to write the review. Let me compile findings.

---

# Round 3 design review — M76 B4b-1 spec v3

## Round-1 findings (D1–D21)

**D1 (blocker, make-up)** — Resolved. C346 ruled no tg2 make-up legs; v3 settled constraints repeat it; `p426_signals._check_makeup` (p426_signals.py:554) refuses any make-up. Out of B4b-1 scope anyway (signals → B4b-2).

**D# Round 3 design review — M76 B4b-1 spec v3

## Round-1 findings (D1–D21)

**D1** (blocker, make-up) — Resolved. C346 no make-up; out of B4b-1 scope (signals).
**D2** (blocker, stricter α) — Resolved. C346 re-check is stop/label gate, α fixed 0.001; v3 §3 re-checks match.
**D3** (screen leg) — Resolved. C346 no screen leg.
**D4** (scope, panel) — Out of scope (B4b-2).
**D5** (blocker, Tg2Corpus) — Resolved. v3 §1 lists every `Corpus` method, prompt bytes, grade call, grader mapping, final tree.
**D6** (blocker, schedule) — Resolved. v3 §2 gives per-leg table, builder shape, seeds, language order, reload=5/lang.
**D7** (blocker, ChainConfig) — Resolved in principle (see R1 below).
**D8** (blocker, scaffold hard-codes) — Resolved. v3 scope lists `validate_leg`, `a4_gate`, `session_pinning_gate`, `structured_grade`, configgen.
**D9** (blocker, freeze/amendment) — Resolved in principle (see R2, R3 below).
**D10** (blocker, wave2-tg2) — Resolved. `wave2.tg2` matches `NAMESPACE_RE`; harvest/run files in scope.
**D11** (blocker, VALID_WITH_DNF) — Out of scope (B4b-2 B8).
**D12** (major, HOLD) — Out of scope (B4b-2 signals).
**D13** (major, join bound) — Resolved. v3 `grader_timeout_s[lang] = 2 × max_entries(timeout_s) + 300`.
**D14** (major, injected positives) — Resolved. v3 §3 positives record sealed, bound to v8.
**D15** (major, pins) — Resolved. v3 `TG2_DRAW_SHA256`/`TG2_UNIVERSE_SHA256` match committed files (verified: `8eb9d8ef…` / `ff76573b…`).
**D16** (major, byte-identical) — Resolved. v3 defines closure-identity boundary.
**D17** (major, chain entry) — Resolved. v3 §2 names entry, argv, `--leg`/`--rehearsal`, `--tg2-draw`.
**D18** (minor, harvest) — Resolved. v3 gives `TG2_BOOKKEEPING_RE` (see R4).
**D19** (major, corpus root) — Resolved. `source_root` public seam.
**D20** (minor, refusal text) — Resolved in principle (see R5).
**D21** (minor, acceptance) — Resolved. v3 acceptance 1 expanded.

## Round-2 findings (E1–E14)

**E1** (blocker, prompt .docs) — Resolved. v3 inlines `.docs/instructions.md` + `.append.md` from pinned source via `tg2_materialize.exercise_dir`. Confirmed `EXCLUDED_ROOTS` excludes `.docs` from prepared tree (tg2_materialize.py:19).
**E2** (blocker, --leg mapping) — Resolved. v3 §2 gives `--leg`/`--rehearsal` → mode/sessions/record-kind; `KINDS` in p426_record.py:11 matches.
**E3** (blocker, R2/R3) — **Not fully resolved.** R2 and freeze path resolved; R3 injection is not (see R1).
**E4** (blocker, recheck out=) — Resolved. v3 says `out=<tmp dir>`, publish `recheck-A8.json` as `recheck-s1.json`. Confirmed `recheck` writes `recheck-A8.json` under `out` dir (m76_sim.py:763).
**E5** (blocker, panel) — Out of scope (B4b-2).
**E6** (major, positives) — Resolved. v3 §3 sealed positives record, `positives_sha256` in v8, re-verified on resume.
**E7** (major, grade call) — Resolved. v3 gives full call with `prepared=prepared.prepared`, `extra_crates=()`, `guard=guard`, `timeout=entry["timeout_s"]`.
**E8** (major, final tree) — Resolved. v3 says helpers + changed `Cargo.toml` included.
**E9–E11** — Out of scope (B4b-2).
**E12** (major, builder) — Resolved in principle (see R2).
**E13** (minor, harvest regex) — Resolved. v3 gives `TG2_BOOKKEEPING_RE` (see R4).
**E14** (minor, t_coop) — Resolved. v3 says `t_coop` takes grader bound from corpus identity.

## New findings v3 breaks or leaves failing

### R1 — Blocker — R3 rehearsal injection (`p426_inject_stall`) is not parameterized for tg2
- **Location:** spec §3 (E3 rehearsals); `chain_core.py:1176–1180` (`p426_inject_stall`).
- **Evidence:** confirmed. `p426_inject_stall` checks `leg.get("lang") == "python"` and `l["lang"] == "python"`, returns `(f"python/{first}", INJECT_STALL_S)`. The rehearsal schedule for tg2 R3 is `s1`, seed 1001, **rust**, first 1 item (v3 §2 table). `leg["lang"]` is `"rust"`, so `p426_inject_stall` returns `None` — no `--inject-stall-item` is passed; R3 never fires.
- **Problem:** v3 says "`p426_hooks` takes the target language from the corpus" (R2, in `p426_hooks.py`), but R3's injection target is selected by `chain_core.p426_inject_stall`, **not** `p426_hooks`. v3's `chain_core` description (§2) lists `freezes_schedule`, overlay skip, prediction defaults, `verify_schedule`, `plan`, `needs_docker` — it does **not** mention `p426_inject_stall`. A literal implementer who reads v3's directive ("p426_hooks takes the target language") would parameterize `_is_go` in `p426_hooks` (R2) but leave `p426_inject_stall` hardcoded to `"python"` (R3).
- **Failure scenario:** R3 rehearsal runs on a Rust item; `p426_inject_stall` returns `None`; the probe gets no `--inject-stall-item`; the leg ends VALID with no kill scored; the rehearsal gate expects "VALID with the kill scored" and fails; v8 never writes; the decider never runs.
- **Proposed change:** state that `chain_core.p426_inject_stall` is parameterized by the corpus's first language (the rehearsal's target language), replacing the hardcoded `"python"` checks with the corpus's first `LANGS` entry, and that the inject-stall item id is `f"{target_lang}/{first}"`.

### R2 — Blocker — `p426_freeze` parser refuses the spec's tg2 command lines
- **Location:** spec §3 (v8 base, amendment); `p426_freeze.py:854–878` (`parse_args`).
- **Evidence:** confirmed. The `v8` subparser requires `--r1-off` and `--r1-on` (line 870: `for flag in ("--rehearsal-manifest", "--r1-off", "--r1-on", "--r2", "--r3")`). The `amend` subparser has `--v8`, `--pilot-off`, `--pilot-on`, `--out` only. Neither subparser has `--corpus` or `--positives`. v3's command lines: `p426_freeze v8 --lever kv --corpus tg2 … --r2 L --r3 L --positives P --out v8_base.json` (no `--r1-off`/`--r1-on`) and `write_amendment --corpus tg2`.
- **Problem:** `argparse` refuses `unrecognized arguments: --corpus tg2` (and `--positives`), and `the following arguments are required: --r1-off, --r1-on`. v3 says `p426_freeze.py` is in scope and gives the command lines + output fields, but does not state the parser changes. `cmd_v8` (line 649–700) also calls `need_walls(ops.historical_walls(), "w_python_s", "w_go_s", ...)` and `deadline_formula({"python": PILOT_N}, ...)` — both refuse tg2. `rehearsal_problems` (line 311) calls `r1_shape_problems` which checks `REHEARSAL_R1_ITEMS = {"python": 3, "go": 2}` — refuses a tg2 rehearsal.
- **Failure scenario:** implementer runs the spec's `p426_freeze v8 --corpus tg2 …` → argparse refuses → exit 2 → no v8 → no decider.
- **Proposed change:** state the parser changes: add `--corpus` and `--positives` to the `v8` and `amend` subparsers; make `--r1-off`/`--r1-on` optional when `--corpus tg2`; add a `cmd_v8` tg2 branch that skips R1, reads `positives_sha256`, derives `settle_bound_s` from R2/R3, and writes `pilot_deadline_s = REHEARSAL_DEADLINE_S`; generalize `deadline_formula` to accept any language whose wall is present; add a `write_amendment` tg2 branch that writes `w_<lang>_s` and `leg_deadline_s[leg]` per the v3 formula; parameterize `rehearsal_problems`/`r1_shape_problems` to skip R1 for tg2.

### R3 — Major — `pilot_gate_problems` hardcodes the tg1 leg name and `PILOT_N = 5`
- **Location:** spec §3 (strict pilot gate); `p426_freeze.py:723–755` (`pilot_gate_problems`), `:39` (`PILOT_N = 5`), `:100` (`kv_pilot_leg` → `"tg1-m76-{arm}-pilot"`).
- **Evidence:** confirmed. `pilot_gate_problems` checks `want_leg = kv_pilot_leg(arm) = "tg1-m76-<arm>-pilot"` and `planned != PILOT_N` (5). v3 says the gate is "parameterised by leg name and n = 4" and the pilot leg is `tg2-m76-<arm>-pilot`. `write_amendment` (line 814) calls `pilot_gate_problems`.
- **Problem:** v3 says "parameterised by leg name and n = 4" but gives no function name or signature. A literal implementer reusing `pilot_gate_problems` gets "the leg is `tg2-m76-n16-pilot`, not `tg1-m76-n16-pilot`" and "5/4 items realized". The gate never passes; no amendment; no decider.
- **Failure scenario:** `write_amendment --corpus tg2` calls `pilot_gate_problems` → reports wrong leg name + 5/4 items → `Refusal` → no amendment → no s1.
- **Proposed change:** name a `tg2_pilot_gate_problems(off_root, on_root, arms)` (or parameterize `pilot_gate_problems` by corpus) that checks `tg2-m76-<arm>-pilot`, `n = 4`, VALID (not VALID_WITH_DNF), 0 DNF, speed-valid, engaged, pair-gated; state that `write_amendment --corpus tg2` calls this.

### R4 — Minor — `TG2_BOOKKEEPING_RE` misses `<step>-n-x` (and `-rm-x`, `-v-x`) edge-case files
- **Location:** spec §4 (harvest regex); `tg2_grade.py:1164–1173` (`_nonce_of`), `:1053–1063` (`_remove_container`).
- **Evidence:** confirmed. `_nonce_of` on rc≠0 calls `_exists` with `tag + "-x"`, producing e.g. `compile-n-x.out` (when `_remove_container` calls `_nonce_of` with tag `compile-n` and docker inspect fails). The regex alternative `(setup-image|…|collect)-(pre|n|rm|v|x)` matches single suffixes only; `compile-n-x` does not match. `cl-holder-n-x` is saved by the `cl-` prefix alternative, but `<step>-n-x`/`<step>-rm-x`/`<step>-v-x` have no matching prefix.
- **Problem:** an edge-case docker-inspect failure during cleanup writes `<step>-n-x.out`; harvest classifies it as None → harvest fails. v3 says "the implementer checks it against every `_plain` / step call site" — but the regex as written doesn't match this call site's output.
- **Failure scenario:** a grade aborts with a TransportAbort during container cleanup (docker inspect rc≠0); `<step>-n-x.out` is left in `<keep>/seq-NNNN/`; harvest fails with "no harvest rule matches".
- **Proposed change:** extend the step alternative to `(setup-image|…|collect)-(pre|n|rm|v|x)(-[a-z0-9][a-z0-9_.-]*)?` or add `-(pre|n|rm|v|x)(-[a-z0-9].*)?` to allow nested `-x` suffixes; or state that these edge-case files are excluded.

### R5 — Major — `validate_reports` `PARSED_EXTRA_ARTIFACTS` for Java uses a pattern (`junit-NNN.xml`) that exact-name matching cannot enforce
- **Location:** spec §1 (validate_reports); `structured_grade.py:436–438` (`REQUIRED_ARTIFACTS`, `PARSED_EXTRA_ARTIFACTS`), `:493` (`if a not in artifacts`).
- **Evidence:** confirmed. v3 says "per-language `parsed` artifacts (Java / C++ `junit-NNN.xml` / `report.xml`, JavaScript `report.json`, Rust the execute step's stdout)". `validate_reports` checks `need = REQUIRED_ARTIFACTS.get(lang, ()) + (PARSED_EXTRA_ARTIFACTS.get(lang, ()) …)` then `if a not in artifacts` — exact name match. Java's junit files are `junit-000.xml`, `junit-001.xml`, … (tg2_grade.py:1429: `(outputs / ("junit-%03d.xml" % n)).write_bytes(...)`). `"junit-NNN.xml"` is not a literal artifact name. Also `REPORT_OUTCOMES` (line 429) lacks `compile_failure`, `crash`, `storage_cap`.
- **Problem:** v3 says "accepts tg2 languages with `tg2_grade`'s outcome set and per-language `parsed` artifacts" but (a) doesn't list the outcomes to add to `REPORT_OUTCOMES`/`FINAL_OUTCOMES` (the implementer must infer `compile_failure`, `crash`, `storage_cap` from the grader mapping), and (b) gives `junit-NNN.xml` as a pattern but `validate_reports` uses exact matching. An implementer putting `"junit-NNN.xml"` in `PARSED_EXTRA_ARTIFACTS` makes every parsed Java row fail `lacks ['junit-NNN.xml']`.
- **Failure scenario:** a parsed Java row has artifacts `{"junit-000.xml": …, "report.xml": …}`; `validate_reports` checks `"junit-NNN.xml" not in artifacts` → "parsed receipt lacks ['junit-NNN.xml']" → row rejected → leg INVALID → A8 incomplete.
- **Proposed change:** state the exact `REPORT_OUTCOMES`/`FINAL_OUTCOMES` additions (`compile_failure`, `crash`, `storage_cap`); state that Java's parsed check is "at least one `junit-*.xml`" (glob), not an exact name, or rename the junit artifact to a fixed name; state `REQUIRED_ARTIFACTS` for tg2 languages (or that it is empty, with only `PARSED_EXTRA_ARTIFACTS` checked for parsed).

### R6 — Major — `ChainConfig.__post_init__` refuses `tg2-p426` with builder `tg2_p426`
- **Location:** spec §2 (run_config); `run_config.py:293–298` (`__post_init__`).
- **Evidence:** confirmed. `__post_init__` checks `if self.config_id == P426_CONFIG_ID: … builder != "tg1" → ValueError` and `p426_continue … config_id != P426_CONFIG_ID → ValueError`. v3 says `P426_CONFIG_IDS = ("tg1-p426", "tg2-p426")` and `tg2-p426 = builder tg2_p426, p426=True, transport p426_continue`. The existing check forces `builder == "tg1"` for the P426 config and refuses `p426_continue` for any other config_id.
- **Problem:** v3 says `chain_core` keys on `config_id in P426_CONFIG_IDS` but does not say `ChainConfig.__post_init__` is relaxed. A literal implementer who adds `tg2-p426` to `P426_CONFIG_IDS` but leaves `__post_init__` checking `config_id == P426_CONFIG_ID` (singular) gets `ValueError: tg2-p426 is the tg1 builder in P426 mode` or `p426_continue is the transport policy of tg1-p426 only`.
- **Failure scenario:** the chain constructs a `ChainConfig(config_id="tg2-p426",…builder="tg2_p426", transport_policy="p426_continue")` → `__post_init__` raises `ValueError` → the chain refuses to start.
- **Proposed change:** state that `__post_init__` is relaxed: any `config_id in P426_CONFIG_IDS` may use `p426_continue` with its builder (`tg1` for `tg1-p426`, `tg2_p426` for `tg2-p426`), one model, `params.p426 True`.

### R7 — Major — Sequencer re-check hooks, `Stop(5, …)`, and `--recheck-ack` parser flag are not wired
- **Location:** spec §3 (re-checks); `p426_wave2.py:859–869` (`after_leg`), `:1077–1104` (`parse_args`).
- **Evidence:** confirmed. `after_leg` only calls `ensure_amendment` after `self.pilots[1]`. There is no hook after "both s1 legs harvested", no `Stop(5, …)` (existing `Stop` uses rc 1, 3, 4), no `--recheck-ack` in the parser, no `rechecks.s1`/`rechecks.s1.ack`/`rechecks.s2` in `sequence.json`. `tg2_strict_rows` does not exist.
- **Problem:** v3 gives the re-check semantics (when, what, output path, stop rc 5, resume on `--recheck-ack`) but not the mechanism: the `after_leg` hook that fires after both s1 legs (not after each leg), the parser flag, the `Stop(5, …)`, or the `sequence.json` schema. A literal implementer must invent all of these; a test-writer cannot know the resume protocol's exact shape.
- **Failure scenario:** implementer adds `tg2_strict_rows` and a `m76_sim.recheck` call but hooks it after each s1 leg (not after both) → re-check runs on one arm's rows only → wrong verdict; or adds `Stop(5, …)` but no `--recheck-ack` parser flag → the sequencer cannot resume.
- **Proposed change:** name the hook (e.g. an `after_pair(spec, entry)` that fires when both arms of a session pair are harvested), the `--recheck-ack <sha256>` parser flag, the `Stop(5, …)` on outside/`operator_review`, and the `sequence.json` fields (`rechecks.s1`, `rechecks.s1.ack` with time, `rechecks.s2`).

### R8 — Major — `chain_core.plan` has no `tg2_p426` dispatch; `verify_schedule` skips it
- **Location:** spec §2 (chain_core); `chain_core.py:1227–1245` (`verify_schedule`, `plan`).
- **Evidence:** confirmed. `plan` dispatches `tg1`/`blocks`/`tg2_tier` only; `verify_schedule` returns early unless `builder == "tg2_tier"`. v3 says `plan` dispatches `tg2_p426` to the tg1 P426 planner and `verify_schedule` calls `check_tg2_p426`. Neither function exists.
- **Problem:** v3 names the intent but not the code. `plan_tg1` reads `blocks[].legs[].invocations[]` and assumes one language per leg — workable for tg2's one-leg-per-(session,language) shape, but the implementer must add the `tg2_p426` branch and write `schedules.tg2_p426` + `check_tg2_p426`. The spec gives the shape and table but not the function bodies.
- **Failure scenario:** implementer adds `tg2_p426` to `plan` but reuses `plan_tg1` without parameterizing by corpus `LANGS` → the schedule emits tg1's languages (python/go) → wrong items launched.
- **Proposed change:** state that `plan` gains `if self.builder == "tg2_p426": return self.plan_tg1()` (the shape is compatible), and that `verify_schedule` gains `if self.builder == "tg2_p426": schedules.check_tg2_p426(...)`; name `schedules.tg2_p426(draw, leg, model, predictor)` and `check_tg2_p426(schedule, draw, leg)` as new functions emitting/verifying the documented shape.

### R9 — Minor — `arm_runner` refusal text and inject out-root not parameterized
- **Location:** spec §1 (arm_runner); `arm_runner.py:1009` ("tg1 supports eligible Python/Go"), `:1029` (`kind = a.tg1_inject`), `:1037` (`m62/inject`).
- **Evidence:** confirmed. v3 says "the inject flag / out root … and the language-refusal text come from the policy / corpus" but the code hardcodes `tg1`, `Python/Go`, `a.tg1_inject`, `m62/inject`. No `--tg2-inject` flag exists.
- **Problem:** a literal implementer must add a `--tg2-inject` flag (or generalize `--tg1-inject`), change the out-root check to `m65/inject` for tg2, and parameterize the refusal text. v3 gives the directive but not the exact text or flag name.
- **Failure scenario:** a tg2 probe run with `--tg2-inject stall` → `arm_runner.main` reads `a.tg1_inject` (None) → no inject addendum → `inject_verify` reports `not_observed`; or the run is forced to `m62/inject/` → refusal.
- **Proposed change:** state that `arm_runner.main` gains a corpus-parameterized inject path (flag name from the policy, out root from the corpus, addenda from `corpus_tg2.INJECT_ADDENDA`), and the refusal text is `f"REFUSED: {template.config_id} supports {template.langs} single-pass items only"` (keeping tg1's exact string when `config_id=="tg1"`).

### R10 — Minor — `KV_DOSSIER_PAIRS` not parameterized to refuse `r1`/`makeup`/`s3` for tg2
- **Location:** spec §3 (p426_receipt); `p426_receipt.py:323–324` (`PAIRS`, `KV_DOSSIER_PAIRS`), `:488` (`if pair not in KV_DOSSIER_PAIRS`).
- **Evidence:** confirmed. `KV_DOSSIER_PAIRS = ("r1","pilot","s1","s2","reload","makeup","s3")`. v3 says tg2 pairs are exactly `pilot`/`s1`/`s2`/`reload` and `r1`/`makeup`/`s3` are "refused". The existing set accepts all.
- **Problem:** v3 says "refused for tg2" but not how. A literal implementer could leave `KV_DOSSIER_PAIRS` as-is → a buggy tg2 sequence that writes an `s3` dossier is accepted → B4b-2 sees a phantom s3.
- **Failure scenario:** a tg2 sequence accidentally writes an `r1` dossier → accepted → B4b-2's `kv_a8_sessions()` sees 3 sessions → size warning or refusal.
- **Proposed change:** state that `KV_DOSSIER_PAIRS` is parameterized by corpus (or `KV_TG2_DOSSIER_PAIRS = ("pilot","s1","s2","reload")` is added) and `write_kv_dossier` rejects `r1`/`makeup`/`s3` for tg2.

## Summary

Round-1 D1–D21 and round-2 E1, E2, E4, E6, E7, E8, E12, E13, E14 are resolved by v3 (D11/D12/E5/E9–E11 are B4b-2). The remaining blockers are:

- **R1** (R3 `p426_inject_stall` not parameterized — the spec says "p426_hooks" but R3 lives in `chain_core`).
- **R2** (`p426_freeze` parser refuses `--corpus`/`--positives` and requires `--r1-off`/`--r1-on`; `cmd_v8`/`write_amendment`/`deadline_formula`/`rehearsal_problems` need tg2 branches).

The majors (R3 pilot gate, R5 validate_reports Java junit pattern + outcome set, R6 ChainConfig, R7 sequencer re-check hooks, R8 plan/verify_schedule dispatch) are seams a literal implementer would either invent (diverging from the test-writer) or get wrong silently. R4 (harvest regex edge case) and R9/R10 are minor.
