I have traced v2 against the source. Here is the review.

---

## Round-1 findings: resolved status

| id | sev | status | why |
|---|---|---|---|
| D1 | blocker | **resolved** | C346 ruled no tg2 make-up legs; v2 settled constraints say so; `_check_makeup` (p426_signals.py:554) refuses any make-up — consistent. |
| D2 | blocker | **resolved** | C346 + v2 fix α at 0.001 and make the re-check a stop/label gate; `m76_sim.recheck` (m76_sim.py:689) already supports `operator_review` without changing α. |
| D3 | — | **resolved** | C346 dropped the screen leg; v2 makes the screen = s1's first 10/language (descriptive). |
| D4 | scope | **resolved in principle** | v2 puts A8 panel packets in scope (members `A8-s1`, `A8-s2`); see F4 for the wiring gap. |
| D5 | blocker | **resolved** | v2 lists every `Corpus` method (corpus.py:87) and the full `grade_outcome` mapping with `seq/boundary/final`, `failing = result.failing(set(entry["leaves"]))`, `resources`, `phases`, `reports`. |
| D6 | blocker | **resolved in principle** | v2 gives the per-leg table and `schedules.tg2_p426(draw, leg, model, predictor)`; see F2 for the builder/`verify_schedule` gap. |
| D7 | blocker | **resolved in principle** | v2 says `P426_CONFIG_IDS = ("tg1-p426","tg2-p426")` and `chain_core` treats every one as P426; see F1 for the `ChainConfig`/`freezes_schedule`/`verify_schedule` gap. |
| D8 | blocker | **resolved in principle** | v2 threads the scaffold from `ArmBinding.label` into `validate_leg`/`a4_gate`, `session_pinning_gate`, `structured_grade.validate_reports`, and a configgen target; see F3/F5. |
| D9 | blocker | **resolved in principle** | v2 gives the order, R2/R3-only rehearsals, the wall formula (`max(max pilot wall, 382)`), and the deadline formula; see F6 for the `cmd_v8`/`write_amendment` gap. |
| D10 | blocker | **resolved in principle** | v2 uses `wave2.tg2` (accepted by `NAMESPACE_RE`, p426_harvest.py:204), `KV_TG2_ATTEMPT_RE`, `verify_a8_kv`, `verify_all_kv` adds A8; see F7 for the wave-directory gap. |
| D11 | blocker | **resolved** | v2 says `_leg_reasons` accepts `VALID_WITH_DNF` for A8 ≤ `MAX_DNF`; the existing `_leg_reasons` (p426_verify.py:394) only accepts `VALID` — the spec says to extend it. |
| D12 | major | **resolved in principle** | v2 says `kv_axis_verdict(..., languages=None)` forwards `languages`, `kv_flags`/`render_kv` cover A8, noise floor; see F8. |
| D13 | major | **resolved** | v2 sets `grader_timeout_s[lang] = 2 × max_entries(timeout_s) + 300` and keeps the core join bound (`2 × max + 60`, run_config.py:21); the default universe is `m65/tg2_universe.json`. |
| D14 | major | **resolved in principle** | v2 pre-registers 12 injected positives + grader known-positives, `m62/inject_verify.py` taking the scaffold; see F9. |
| D15 | major | **resolved** | v2 pins `TG2_DRAW_SHA256`/`TG2_UNIVERSE_SHA256` in `schedules`; a consistent redraw refuses. |
| D16 | major | **resolved** | v2 defines the byte-identity boundary: tg1 plan/argv/schedules/B8/signals golden; tg1 rows equal except closure-derived identity fields, asserted to change. |
| D17 | major | **resolved** | v2 names `run_tg2_chain.py`, the argv, `--tg2-draw`, `source_root`. |
| D18 | minor | **resolved in principle** | v2 lists the exact files and the near-match refusal; see F10 for the missing patterns. |
| D19 | major | **resolved** | v2 says `source_root` is the corpus-root seam (no private helper). |
| D20 | minor | **resolved in principle** | v2 says the refusal text comes from the policy/corpus; see F11. |
| D21 | minor | **resolved in principle** | v2's acceptance criterion 1 is much expanded; see F12 for residual gaps. |

---

## New findings v2 breaks or leaves ambiguous/untestable

### F1 — Major — `ChainConfig` and `freezes_schedule`/`verify_schedule` for `tg2-p426` are inconsistent
**Location:** Spec §2 (lines 64–67); `run_config.py:293–298`; `chain_core.py:815`, `:1227–1233`.
**Evidence:** confirmed. `ChainConfig.__post_init__` allows `p426_continue` only when `config_id == P426_CONFIG_ID` ("tg1-p426") and forces `builder == "tg1"`. `freezes_schedule` is `self.builder in ("blocks","tg2_tier") or self.config.config_id == run_config.P426_CONFIG_ID` (single id). `verify_schedule` runs `check_tg2_membership` only when `self.builder == "tg2_tier"`. v2 says `tg2-p426` uses builder `tg2_p426` and "chain_core treats every `P426_CONFIG_IDS` config as P426 (`freezes_schedule`, no `ensure_overlay`, the tg1 prediction defaults, never M64's `PRED_S`)".
**Problem:** With builder `tg2_p426`, `freezes_schedule` is False (not in `("blocks","tg2_tier")` and config_id != "tg1-p426") unless the implementer also changes the check to `config_id in P426_CONFIG_IDS`. And `verify_schedule` skips the draw-membership check for builder `tg2_p426`. v2 says `tg2_p426` "verifies the draw against the pins and each invocation's items against the draw prefix" — but the only existing verifier (`check_tg2_membership`) is gated on `builder == "tg2_tier"`. The spec doesn't say whether to (a) relax `ChainConfig` to accept `builder == "tg2_tier"` for `tg2-p426`, or (b) keep builder `tg2_p426` and extend `freezes_schedule`/`verify_schedule` to cover it.
**Failure scenario:** Implementer picks builder `tg2_p426` and only relaxes `ChainConfig` → `freezes_schedule` is False → `schedule.json` is not frozen/re-verified per leg → a redrawn draw passes (D15 defeated). Or implementer picks `builder == "tg2_tier"` → `ChainConfig` refuses (`p426_continue` needs `builder == "tg1"`).
**Proposed change:** State that `ChainConfig.__post_init__` is relaxed so any `config_id in P426_CONFIG_IDS` may use `p426_continue` with builder `tg1` OR `tg2_tier` (one model, `params.p426` True), and that `freezes_schedule`/`verify_schedule` key on `config_id in P426_CONFIG_IDS` (so the draw-membership check runs for `tg2-p426`). Pick `builder == "tg2_tier"` to reuse `plan_tg2`/`check_tg2_membership`, or state that `tg2_p426` is a new builder with its own `plan_*`/membership path.

### F2 — Major — `schedules.tg2_p426` is a new builder with no `plan_*` or membership path
**Location:** Spec §2 (line 68–77); `schedules.py:315` (`tg2_tier`), `:343` (`check_tg2_membership`); `chain_core.py:1240` (`plan` dispatch), `:1290` (`plan_tg2`).
**Evidence:** confirmed. `chain_core.plan` dispatches on `self.builder` to `plan_tg1`/`plan_blocks`/`plan_tg2`; there is no `plan_tg2_p426`. `tg2_tier` emits `sessions[].cells[]`, but v2 says `tg2_p426` "emits tg1's P426 shape (`blocks[].legs[].invocations[]`, one session)" so `planned_slots`/`schedule_plan_sha`/`p426_not_run` read it unchanged. So `tg2_p426` is a new shape, not `tg2_tier`. The spec gives the per-leg table but no `plan_*` reader and no membership verifier for the new shape.
**Problem:** An implementer must invent both the schedule emitter and the `chain_core.plan_*` reader for `tg2_p426`, and a membership check. The spec says the shape is "tg1's P426 shape" — but `plan_tg1` reads `blocks[].legs[].invocations[]` and assumes one language per leg (tg1 is single-language). tg2 has four languages per session. The spec doesn't say whether `tg2_p426` emits one leg per (session, language) or one leg per session with four invocations.
**Failure scenario:** Implementer emits one leg per session with four language invocations → `plan_tg1` reads one `lang` per leg (the first) → the other three languages are never run. Or implementer emits one leg per (session, language) → `planned_slots` counts 20 per language but `plan_tg1`'s `arm.arm`/`label` keying breaks.
**Proposed change:** State the exact `blocks/legs/invocations` shape `tg2_p426` emits (one leg per (session, language), each with one invocation of that language's items, or one leg per session with four invocations), and name the `chain_core.plan_*` reader and the membership verifier. Alternatively, reuse `tg2_tier` for the schedule and add a per-leg projection (one session) — but then `planned_slots` must read `sessions[].cells[]`, which v2 says it doesn't.

### F3 — Major — `validate_leg` takes `spec` (an `ArmSpec`), not a scaffold string from `ArmBinding.label`
**Location:** Spec §2 (line 67); `chain_ops.py:1157` (`validate_leg(..., spec=None)`), `:1164` (`scaffold = SCAFFOLD if spec is None else spec.label`).
**Evidence:** confirmed. `validate_leg`'s `spec` is an `arm_specs.ArmSpec` with a `.label` field; `ArmBinding.label` (run_config.py:242) is the scaffold label string. v2 says "take the scaffold from the leg's `ArmBinding.label`" — but `validate_leg` doesn't receive an `ArmBinding`, it receives `spec`. The existing `a4_gate(self, model, tag, scaffold=SCAFFOLD)` does take a scaffold string.
**Problem:** An implementer must either construct an `ArmSpec` with `.label = "opencode-v2-web-tg2"` for tg2 legs, or change `validate_leg`'s signature to take a scaffold string. The spec's wording ("from the leg's `ArmBinding.label`") implies the latter, but the existing call sites pass `spec`. The spec doesn't say which.
**Failure scenario:** Implementer passes `spec=None` for tg2 → `scaffold = SCAFFOLD = "opencode-v2-web-tg1"` → every tg2 row rejected for `runtime_scaffold: opencode-v2-web-tg2`.
**Proposed change:** State that `validate_leg` takes the scaffold from `spec.label` (an `ArmSpec` constructed for tg2 with `.label = "opencode-v2-web-tg2"`), or change the signature to accept a scaffold string and update call sites.

### F4 — Major — `p426_panel` A8 members are not wired into `kv_members`/`kv_export`/`kv_expected_members`
**Location:** Spec §6 (line 161); `p426_panel.py:1235` (`kv_members`), `:1847` (`if member.startswith("A7-")`), `:1946` (`kv_expected_members`).
**Evidence:** confirmed. `kv_members` returns `KV_WAVE1_MEMBERS + tuple(f"A7-{s}" ...)`. `kv_export` special-cases `member.startswith("A7-")` for the packet shape. `kv_expected_members` adds `A7-<s>` for planned sessions. v2 says members `A8-s1`, `A8-s2` "as `A7-<s>`" — but the code has no `A8-` branch. An implementer must extend `kv_members`, `kv_export`, `kv_expected_members`, `kv_rubric`, and the leak patterns (`KV_LEAK_PATTERNS + (..., "tg2")`).
**Problem:** v2 says "as `A7-<s>`" but doesn't say the implementer must add `A8-` branches to five functions. The packet content (task, final tree diff, transcript summary; rubric `code`; the kv leak patterns + `tg2`) is described, but the selection rule (one blind packet per B8-accepted, both-pass, non-identical item) must mirror A7's `kv_select`-equivalent. The spec doesn't name the A8 selection function or how it reads A8 rows (which are tg2 rows, not tg1 rows).
**Failure scenario:** Implementer adds `A8-s1` to `kv_members` but not to `kv_export` → `kv_export` falls through the `A7-` branch → no packet is built → the panel is incomplete → `panel_incomplete` blocks forever. Or the A8 selection reads tg1-style rows and finds none.
**Proposed change:** Name the A8 packet builder (e.g. `kv_export_a8`), the selection rule (mirror `kv_select` over A8 B8-accepted both-pass non-identical items), the rubric (`code`), the leak patterns (`KV_LEAK_PATTERNS + (..., r"\btg2\b")`), and state that `kv_members`/`kv_expected_members`/`kv_export`/`kv_rubric` all gain `A8-` branches.

### F5 — Major — `structured_grade.validate_reports` rejects every tg2 outcome and language
**Location:** Spec §1 (line 84); `structured_grade.py:429` (`REPORT_OUTCOMES`), `:436` (`REQUIRED_ARTIFACTS = {"python": ..., "go": ...}`), `:438` (`PARSED_EXTRA_ARTIFACTS`).
**Evidence:** confirmed. `REPORT_OUTCOMES = ("parsed","timeout","oom","mem_kill","missing_report","collection_error","tampered")`. tg2 outcomes include `compile_failure`, `crash`, `storage_cap` — none are in `REPORT_OUTCOMES` → `validate_reports` appends `outcome {outcome!r} not permitted`. `REQUIRED_ARTIFACTS` has only `python`/`go`; rust/javascript/java/cpp have no required artifacts → every non-tampered receipt is rejected for `has no artifacts` (the `else` branch requires `need = REQUIRED_ARTIFACTS.get(lang, ())` — empty is fine, but `if not artifacts: reasons.append("has no artifacts")` still fires for a receipt with no artifacts). v2 says `validate_reports` "accepts tg2 languages with `tg2_grade`'s outcome set and its per-language `parsed` artifacts".
**Problem:** v2 says to accept tg2 but doesn't list the new outcome set or the per-language required/parsed artifacts. An implementer must add `compile_failure`, `crash`, `storage_cap` to `REPORT_OUTCOMES`/`FINAL_OUTCOMES`, and add `rust`/`javascript`/`java`/`cpp` to `REQUIRED_ARTIFACTS`/`PARSED_EXTRA_ARTIFACTS`. The spec lists the parsed artifacts in §1 ("Java/C++ `junit-NNN.xml`/`report.xml`, JavaScript `report.json`, Rust the execute step stdout") but doesn't say these are the `PARSED_EXTRA_ARTIFACTS` for `validate_reports`.
**Failure scenario:** A tg2 row with a `compile_failure` receipt → `validate_reports` returns `outcome 'compile_failure' not permitted` → the leg is INVALID → A8 incomplete.
**Proposed change:** State that `REPORT_OUTCOMES`/`FINAL_OUTCOMES` add `compile_failure`, `crash`, `storage_cap`; `REQUIRED_ARTIFACTS` adds the four tg2 languages (with their launch-output artifacts — at minimum the step `stdout`/`stderr`); `PARSED_EXTRA_ARTIFACTS` adds the parsed artifacts per §1.

### F6 — Blocker — `p426_freeze.cmd_v8`/`write_amendment` cannot produce the tg2 v8 base or amendment
**Location:** Spec §3 (lines 119–129); `p426_freeze.py:649` (`cmd_v8`), `:801` (`write_amendment`), `:82` (`deadline_formula`), `:36` (`PILOT_N`), `:41` (`REHEARSAL_R1_ITEMS`).
**Evidence:** confirmed. `cmd_v8` requires `--rehearsal-manifest`, `--r1-off`, `--r1-on`, `--r2`, `--r3` (parser at :870), reads `ops.historical_walls()` for `w_python_s`/`w_go_s`/`max_request_elapsed_s` (:678), and writes `pilot_deadline_s = deadline_formula({"python": PILOT_N}, ...)` (:698). `deadline_formula` raises `ValueError` for any lang not in `("python","go")` (::84). `write_amendment` reads `ops.historical_walls()` for `w_python_s`/`w_go_s` (:826) and writes only those two walls (:832). v2 says `p426_freeze v8 --corpus tg2` writes a `p426_v8_base` with `corpus: "tg2"`, `tg2_draw_sha256`, R2/R3 receipts (no R1), and `write_amendment --corpus tg2` writes `w_<lang>_s = max(max pilot wall of <lang> over both arms, 382)` and `leg_deadline_s[leg] = 1.5 × Σ_lang n_lang × w_<lang>_s + 1800 + 3660`.
**Problem:** The spec gives the formulas and the record fields but does not say whether `cmd_v8`/`write_amendment` are extended with a `--corpus tg2` branch or new `cmd_v8_tg2`/`write_amendment_tg2` functions are added. The existing `cmd_v8` requires R1 and `w_python_s`/`w_go_s`; it cannot run for tg2. The existing `write_amendment` calls `pilot_gate_problems` (which hardcodes `kv_pilot_leg(arm) = "tg1-m76-<arm>-pilot"` and `PILOT_N=5`) — see F13. The `--corpus` flag is not in the parser. The spec says `p426_freeze v8 --lever kv --corpus tg2` and `write_amendment --corpus tg2` but the parser (`parse_args`, :854) has no `--corpus` argument.
**Failure scenario:** Implementer runs `python -m bench.p426_freeze v8 --corpus tg2 ...` → argparse refuses: `unrecognized arguments: --corpus tg2`. Or implementer extends `cmd_v8` but leaves `need_walls(ops.historical_walls(), "w_python_s", ...)` → `Refusal: ops.historical_walls() lacks w_python_s, w_go_s, max_request_elapsed_s`. The tg2 freeze never writes; every decider leg refuses at `check_frozen_record`.
**Proposed change:** Specify the tg2 freeze as either (a) a `--corpus tg2` branch in `cmd_v8`/`write_amendment`/`parse_args` that skips R1, reads the pilot walls from the pilot pair's item records (not `historical_walls`), generalises `deadline_formula` to accept any language whose wall is present, and writes `w_rust_s`/`w_javascript_s`/`w_java_s`/`w_cpp_s` + `leg_deadline_s` over the per-leg table; or (b) new `cmd_v8_tg2`/`write_amendment_tg2` functions. State the parser changes (`--corpus`, `--r2`, `--r3` required for tg2; `--r1-off`/`--r1-on` not required).

### F7 — Major — `verify_a8_kv` must read `wave2.tg2/`, but v2 doesn't state the wave directory constant
**Location:** Spec §5 (lines 145–148); `p426_verify.py:42` (`WAVE = "wave2"`), `:1364` (`KV_W2 = "wave2"`), `:2007` (`reader.root / WAVE / name`), `:2050` (`_kv_load_attempt` uses `WAVE`).
**Evidence:** confirmed. `verify_a7_kv` reads attempts under `reader.root / "wave2"`. v2 says the namespace is `wave2.tg2` and `verify_a8_kv` "mirrors `verify_a7_kv`". `NAMESPACE_RE` (p426_harvest.py:204) accepts `wave2.tg2` (dot), so harvest works. But `verify_a7_kv`'s `WAVE = "wave2"` is a module constant; an implementer mirroring `verify_a7_kv` literally reads `reader.root / "wave2" / "tg2-m76-..."` — which does not exist (tg2 is under `wave2.tg2/`). v2 says "`p426_verify` reads the wave directory per corpus (`wave2` tg1, `wave2.tg2` tg2)" — this is the intent, but the constant is unnamed and the existing `WAVE` is hardcoded.
**Problem:** v2 states the per-corpus wave directory but doesn't name a `KV_W2_TG2 = "wave2.tg2"` constant or say `verify_a8_kv` uses it. `verify_all_kv` (p426_verify.py:2125) adds A7 when `m76/wave2/run/` exists; v2 says it adds A8 when `m76/wave2.tg2/run/` exists — but the existing `if (Path(rows_root) / KV_ROOT / WAVE / "run").is_dir()` uses `WAVE`. The implementer must add a parallel check.
**Failure scenario:** The decider harvests to `wave2.tg2/`; `verify_a8_kv` reads `wave2/` → "attempt wave2/tg2-m76-n16-s1.a1 is missing" → every session rejected → A8 incomplete → no verdict.
**Proposed change:** Name `KV_W2_TG2 = "wave2.tg2"` and state that `verify_a8_kv` reads `reader.root / KV_W2_TG2 / name`, and `verify_all_kv` adds A8 when `(Path(rows_root) / KV_ROOT / "wave2.tg2" / "run").is_dir()`.

### F8 — Major — `kv_axis_verdict` must be extended to forward `languages`; v2 says "passes through" but the existing helper drops it
**Location:** Spec §6 (line 156); `p426_signals.py:1341` (`kv_axis_verdict(axis, look, a, b)`), `:1346` (`m76_rule.axis_verdict(axis, look, a, b)` — no `languages`).
**Evidence:** confirmed. `kv_axis_verdict` calls `m76_rule.axis_verdict(axis, look, a, b)` with no `languages` kwarg. `m76_rule.axis_verdict` (m76_rule.py:620) sets `hold = None` unless `axis == "A8" and languages is not None` (:686). v2 says "`kv_axis_verdict(axis, look, a, b, languages=None)` passes `languages` through."
**Problem:** v2 states the new signature but the existing function has it not. An implementer "mirroring `_kv_a7_section`" (which uses `kv_axis_verdict("A7", ...)`) and calling `kv_axis_verdict("A8", ...)` without `languages` produces `hold = None` always — the per-language HOLD (C339, blocking) is dead code. This is exactly D12, and v2's wording resolves it *if* the implementer extends the helper — but v2 doesn't say "extend `kv_axis_verdict`"; it says the signature is `kv_axis_verdict(axis, look, a, b, languages=None)`, which an implementer could read as "the helper already has this" (it doesn't).
**Failure scenario:** A language scores −25 pp; `axis_verdict("A8", 1, test, ref)` returns `hold = None` (no `languages`); `kv_flags` never adds the HOLD flag; the operator ships a regressed language.
**Proposed change:** State explicitly: "Extend `kv_axis_verdict` to accept `languages=None` and forward it to `m76_rule.axis_verdict`; `_kv_a8_section` MUST call `kv_axis_verdict("A8", lk["look"], test, ref, languages=langs)` (not `m76_rule.axis_verdict` directly)."

### F9 — Major — Run-time injected positives cannot use the existing `--tg1-inject` path; `m62/inject_verify.py` hardcodes the tg1 label
**Location:** Spec §1 (line 60), §3 (line 119); `arm_runner.py:1029–1038` (`if a.tg1_inject: ... --out under $STACK_WORKDIR/m62/inject/`), `:1037` (refusal); `m62/inject_verify.py:179` (`label = "opencode-v2-web-tg1-inject:" + kind`).
**Evidence:** confirmed. `arm_runner.main` forces `--tg1-inject` runs to `--out` under `$STACK_WORKDIR/m62/inject/` (:1037). `m62/inject_verify.verify_row` hardcodes the label `"opencode-v2-web-tg1-inject:" + kind`. v2 says the inject flag is `--tg2-inject stall|loop|alloc` (in place of `--tg1-inject`), the out root is `$STACK_WORKDIR/m65/inject/`, and `m62/inject_verify.py` takes the scaffold as a parameter.
**Problem:** v2 renames the flag to `--tg2-inject` but `arm_runner.main` only inspects `a.tg1_inject` (:1028, :1063). The implementer must add `a.tg2_inject` handling (or generalise to `a.inject`/`a.inject_corpus`). The out-root check (:1037) is hardcoded to `m62/inject/`. The inject addenda (`INJECT_ADDENDA`) live in `corpus_tg1.py`; v2 says `corpus_tg2` provides `INJECT_ADDENDA`/`inject_addendum_sha256` but doesn't give the text. `m62/inject_verify.verify_row`'s label is hardcoded; v2 says "taking the scaffold as a parameter" — the implementer must parameterise the label construction (`f"{scaffold}-inject:{kind}"`).
**Failure scenario:** A tg2 probe run with `--tg2-inject stall` → `arm_runner.main` doesn't read `a.tg2_inject` → no inject addendum is appended → the run is a normal (non-injected) run → `inject_verify` reports `not_observed`. Or the run is forced to `m62/inject/` → refusal.
**Proposed change:** State that `arm_runner.main` gains a corpus-parameterised inject path (flag name, out root, addenda source from the corpus), and `m62/inject_verify.verify_row`/`main` take a `--scaffold` parameter and build the label as `f"{scaffold}-inject:{kind}"`. State whether `corpus_tg2.INJECT_ADDENDA` reuses tg1's three addenda byte-identically (they are shell commands, language-agnostic) or gives new text.

### F10 — Major — Harvest `classify` rejects most tg2 per-grade files; v2 lists files but gives no patterns
**Location:** Spec §4 (lines 137–140); `p426_harvest.py:261` (`classify`), `:309–321` (evidence branch), `:223` (`EVIDENCE_SUFFIXES = (".jsonl",".json",".txt",".log",".html")`).
**Evidence:** confirmed. The evidence-kind `classify` returns evidence only for names ending in `EVIDENCE_SUFFIXES + (".xml",)` (with the `go.stderr` special case at :319). tg2 writes `<item>.grades/seq-NNNN/<step>.stdout`/`.stderr`/`.inspect`/`.inspect.err` and `<tag>.out`/`.err` — none end in those suffixes → `classify` returns `None` → harvest fails. v2 lists the exact files and says "a near-match (another step / tag name) stays unclassified (the harvest fails)" and "`grading-private/.tg2-registry/*.json` → evidence (bookkeeping, never cited), placed before the generic `.json` → main rule".
**Problem:** v2 lists the files but gives no regex patterns. The docker bookkeeping tags (from `tg2_grade._plain`/`_exists`/`_remove_container`) include `plan-*`, `volume-*`, `own-*`, `holder`, `own-holder`, `<step>-pre`, `-rm`, `-v`, `-n`, `-x`, `cl-holder`, `cl-*`, `rm-*`, `ls-*` — the spec doesn't enumerate them, so an implementer must read `tg2_grade` to discover them. A missed tag → harvest fails. The spec says `.tg2-registry/*.json` goes to evidence "placed before the generic `.json` → main rule" — but the existing `grading-private` branch (p426_harvest.py:309) sends `.json` to `main` and `.log`/`.txt`/`.out`/`.err` to `evidence`. The implementer must add a `.tg2-registry/*.json` → evidence rule BEFORE the generic `.json` → main. v2 says this but doesn't give the pattern.
**Failure scenario:** Implementer adds `seq-\d+/(setup-image|...|collect)\.(stdout|stderr|inspect|inspect\.err)` but misses `<step>-pre.out` (the `_exists` pre-check) → a real tg2 grade writes `compile-pre.out` → `classify` returns `None` → harvest rc 4 → the decider leg is never harvested → A8 incomplete.
**Proposed change:** Give the exact regex patterns (or pin them to a recorded fixture the test freezes), including the docker bookkeeping tag glob (e.g. `^[A-Za-z0-9][A-Za-z0-9._-]*\.(out|err)$` over the listed tags, or an explicit alternation), and the `.tg2-registry/*.json` → evidence rule with its precedence.

### F11 — Minor — `arm_runner` refusal text is tg1-specific
**Location:** `arm_runner.py:1009` (`"REFUSED: tg1 supports eligible Python/Go single-pass items only"`).
**Evidence:** confirmed. v2 says the refusal text comes from the policy/corpus but doesn't call out this line. With `TG2_POLICY.langs=(rust,...)`, a rust refusal prints "tg1 supports eligible Python/Go".
**Problem:** Cosmetic; no material consequence (the refusal is correct), but an operator chasing a tg2 failure sees the wrong corpus name.
**Failure scenario:** A rust item is refused; the operator reads "tg1 supports eligible Python/Go" and looks in the wrong place.
**Proposed change:** Parameterise the refusal text by `template` (e.g. `f"REFUSED: {template.config_id} supports {tuple(template.langs)} single-pass items only"`), keeping tg1's exact string when `config_id=="tg1"`.

### F12 — Minor — `kv_a8_sessions()` is not stated; `axis_plan("A8")["sessions"]` is a count, not names
**Location:** Spec §5 (line 146), §6 (line 156); `m76_rule.py:442` (`"A8": ... sessions=2`), `p426_plan.py:434` (`kv_a7_sessions`).
**Evidence:** confirmed. `axis_plan("A8")` returns `sessions=2` (a count). `kv_a7_sessions()` (p426_plan.py:434) turns A7's count into `("s1","s2"[,"s3"])`. v2 says `verify_a8_kv` uses `kv_a8_sessions() = ("s1","s2") (from axis_plan("A8")["sessions"])` and `_kv_a8_section` uses planned sessions. There is no `kv_a8_sessions()` in the code.
**Problem:** v2 names `kv_a8_sessions()` but doesn't say the implementer must add it (mirroring `kv_a7_sessions`). An implementer could read `axis_plan("A8")["sessions"]` = 2 and build session keys `"1","2"` or `["s1","s2"]` by guess.
**Failure scenario:** Implementer builds session keys `"1","2"` → the B8 pair lookup (keyed by session name) misses every pair → A8 incomplete.
**Proposed change:** State that `kv_a8_sessions()` is added to `p426_plan` (mirroring `kv_a7_sessions`), returning `("s1","s2")`, and that `verify_a8_kv`/`_kv_a8_section` use it.

### F13 — Major — The "strict pilot gate" for tg2 is undefined (function, location, relation to `pilot_gate_problems`)
**Location:** Spec §3 (line 127); `p426_freeze.py:723` (`pilot_gate_problems`), `:728` (`want_leg = kv_pilot_leg(arm)` → `"tg1-m76-<arm>-pilot"`), `:749` (`planned != PILOT_N` where `PILOT_N=5`).
**Evidence:** confirmed. `pilot_gate_problems` hardcodes `want_leg = kv_pilot_leg(arm) = "tg1-m76-<arm>-pilot"` and `planned != PILOT_N` (5). v2 says the pilot gate conditions: "both arms VALID (not VALID_WITH_DNF), 4 reconciled rows each, 0 DNF, speed-valid, engaged, pair-gated". The leg name is `tg2-m76-<arm>-pilot`, 4 rows. v2 doesn't name the gate function or where it lives (freeze or wave2).
**Problem:** The spec names the gate ("strict pilot gate") and its conditions but gives no function name. The existing `pilot_gate_problems` is unparameterised (constant leg-name function, constant `PILOT_N`). `write_amendment` calls `pilot_gate_problems` (:814) — so if the implementer reuses it for tg2, it reports "the leg is `tg2-m76-<arm>-pilot`, not `tg1-m76-<arm>-pilot`" and "5/4 items realized". The candidate punts the amendment to the operator (F6), so the gate is never run.
**Failure scenario:** Implementer reuses `pilot_gate_problems` → it reports the wrong leg name and `5/4 items` → the gate never passes → no amendment → no decider.
**Proposed change:** Name a `tg2_pilot_gate_problems(off_root, on_root, arms)` (in `p426_freeze` or `p426_wave2`) that checks: leg name `tg2-m76-<arm>-pilot`, state VALID (not `VALID_WITH_DNF`), 4 reconciled rows (1/language), 0 DNF, speed-valid, engagement proven, KV pair gate. State that `write_amendment --corpus tg2` calls this (not `pilot_gate_problems`), and parameterise `kv_pilot_leg`/`PILOT_N` or add a tg2 pair.

### F14 — Major — The sequencer's tg2 leg table and `after_leg` hooks are undefined
**Location:** Spec §3 (lines 119–131); `p426_wave2.py:118` (`kv_legs` builds `tg1-m76-<arm>-<s>`), `:860` (`after_leg` calls `ensure_amendment` when `spec["name"] == self.pilots[1]`).
**Evidence:** confirmed. `kv_legs` returns `run = [pilot, pilot, s1, s1, s2, s2, reload, reload]` + makeup + rehearsal, all named `tg1-m76-...`. v2's tg2 order is: (a) grader known-positives, (b) injected positives, (c) R2/R3 rehearsals, (d) freeze v8, (e) pilot pair, (f) pilot gate, (g) amendment, (h) s1, (i) re-check 1, (j) s2, (k) reload, (l) re-check 2. This is a new sequence with re-check stops between s1/s2/reload — the existing `after_leg` only calls `ensure_amendment` after the pilot pair. v2 says "`p426_wave2 --corpus tg2` sequences per arm pair" but doesn't name the leg-table builder or the `after_leg` hooks for re-check 1/2.
**Problem:** An implementer must build a `kv_tg2_legs` (or parameterise `kv_legs`) with the new names `tg2-m76-<arm>-{pilot,s1,s2,reload}` and `tg2-m76-<arm>-rehearsal-{r2,r3}`, and add `after_leg` hooks that run `m76_sim.recheck("A8", ...)` after s1 (both arms) and after s2 (both arms), with the stop/resume-on-ack protocol. The spec says the re-check "stops (rc 5, record `recheck-s1.json`) and resumes only with `--recheck-ack <sha256>`" — but the existing `Stop` mechanism (p426_wave2.py:860) is for the pilot gate, not a re-check; the `--recheck-ack` flag is not in the parser. v2 doesn't name the parser changes or the `Stop`-on-recheck hook.
**Failure scenario:** Implementer reuses `kv_legs` → leg names are `tg1-m76-...` → B8's `KV_TG2_ATTEMPT_RE = ^tg2-m76-...` rejects every attempt → A8 incomplete. Or implementer builds the leg table but no re-check hook → the re-check never runs → C346's stop-for-operator gate is dead code.
**Proposed change:** Name the tg2 leg-table builder (e.g. `kv_tg2_legs(ref, test)`), the `after_leg` hooks for re-check 1 (after both s1 legs harvested) and re-check 2 (after both s2 legs harvested), the `Stop(5, ...)` on outside/`operator_review`, the `--recheck-ack <sha256>` parser flag and its resume semantics, and where the recheck records live (`<wave2.tg2>/recheck-s1.json`, `recheck-s2.json`).

### F15 — Major — `p426_receipt.PAIRS`/`KV_DOSSIER_PAIRS` must add `pilot` for tg2 but the spec's list omits the tg2-specific changes
**Location:** Spec §3 (line 130); `p426_receipt.py:323` (`PAIRS = ("r1","pilot","s1","s2","reload","makeup")`), `:324` (`KV_DOSSIER_PAIRS = PAIRS + ("s3",)`).
**Evidence:** confirmed. v2 says "`p426_receipt` pairs for tg2: `pilot`, `s1`, `s2`, `reload`." The existing `KV_DOSSIER_PAIRS` already includes `pilot`/`s1`/`s2`/`reload` (via `PAIRS`), so tg2 needs no addition for those — but it must NOT include `r1`/`makeup`/`s3` for tg2 (no R1, no make-up, no s3). v2 doesn't say whether `KV_DOSSIER_PAIRS` is parameterised by corpus or whether a separate `KV_TG2_DOSSIER_PAIRS = ("pilot","s1","s2","reload")` is added.
**Problem:** If `write_kv_dossier` (p426_receipt.py:488) checks `pair not in KV_DOSSIER_PAIRS` and `KV_DOSSIER_PAIRS` includes `r1`/`makeup`/`s3`, a tg2 dossier for `pilot` is accepted (it's in the set) — but a tg2 sequence that accidentally produces an `r1`/`makeup`/`s3` dossier would also be accepted. The spec says tg2 pairs are exactly `pilot`/`s1`/`s2`/`reload`; the implementer must enforce that tg2 rejects the others.
**Failure scenario:** A tg2 sequence accidentally writes an `s3` dossier (a bug) → `KV_DOSSIER_PAIRS` accepts it → B8 reads a phantom s3 pair → A8 has 3 sessions instead of 2 → `axis_verdict` size-warning or refusal.
**Proposed change:** State that `KV_DOSSIER_PAIRS` is parameterised by corpus (or a `KV_TG2_DOSSIER_PAIRS = ("pilot","s1","s2","reload")` is added) and `write_kv_dossier` rejects `r1`/`makeup`/`s3` for tg2.

### F16 — Minor — `corpus_tg2.INJECT_ADDENDA` text is not specified
**Location:** Spec §1 (line 60); `corpus_tg1.py:22` (`INJECT_ADDENDA`).
**Evidence:** confirmed. v2 says `corpus_tg2` provides `INJECT_ADDENDA`/`inject_addendum_sha256` but gives no text. `inject_addendum_sha256` is part of the generation identity, so the text must be frozen. tg1's addenda are shell commands (`ls` four times, `sleep 600 ...` three times, `python3 -c "import time; b = bytearray(...)"`) — language-agnostic.
**Problem:** An implementer must either reuse tg1's addenda byte-identically or write tg2-specific text. The spec doesn't say which. If they write new text, `inject_addendum_sha256` changes and must be re-frozen; if they reuse tg1's, the addenda reference shell commands that work for all tg2 languages (they're shell, not language-specific).
**Failure scenario:** Implementer writes tg2-specific addenda with different text → the `inject_addendum_sha256` in the policy differs from what `corpus_tg2.inject_addendum_sha256(kind)` computes → identity mismatch → B8 rejects the pair.
**Proposed change:** State that `corpus_tg2.INJECT_ADDENDA` reuses tg1's three addenda byte-identically (they are shell commands, language-agnostic), or give the tg2 addenda text explicitly.

### F17 — Minor — A8 noise floor is not explicitly stated
**Location:** Spec §6 (line 159); `p426_signals.py:1496` (`kv_a7` noise floor, N16 within-arm s1-vs-s2).
**Evidence:** confirmed. v2 says "the N16 s1 vs s2 noise floor (as A7)" — this implies A8 carries a noise floor mirroring A7. A7 builds it only when `ref_arm == "n16"` (p426_signals.py:1493). A8's reference is also n16, so the same pattern applies. v2 says "as A7" — so this is resolved in principle, but the spec doesn't say `_kv_a8_section` builds it.
**Problem:** Minor; an implementer mirroring `kv_a7` would add it. But v2's wording "the N16 s1 vs s2 noise floor (as A7)" is in the list of section contents, so it's stated. Resolved.
**Failure scenario:** Implementer omits it → the operator loses the within-arm discordance diagnostic for A8.
**Proposed change:** None needed beyond v2's wording; optionally state `_kv_a8_section` builds `noise_floor` when `ref == "n16"` mirroring `kv_a7`.

### F18 — Minor — `compute_kv`/`verify_all_kv` A8 wiring is stated but not pinned to the aggregator branches
**Location:** Spec §5 (line 148), §6 (line 160); `p426_verify.py:2125` (`verify_all_kv`), `p426_signals.py:1695` (`if "A7" in b8["axes"]`).
**Evidence:** confirmed. v2 says `verify_all_kv` adds A8 when `m76/wave2.tg2/run/` exists and `compute_kv` calls `_kv_a8_section` when `b8["axes"]["A8"]` exists. The existing `compute_kv` only branches on `"A7"`; `verify_all_kv` only branches on `m76/wave2/run/`.
**Problem:** v2 states the wiring but an implementer could add `verify_a8_kv`/`_kv_a8_section` and forget the aggregator branches. The spec says "the public B8 CLI emits it" and "`compute_kv` calls `_kv_a8_section` when `b8["axes"]["A8"]` exists" — so this is stated. Resolved in principle.
**Failure scenario:** Implementer forgets `verify_all_kv` A8 branch → `b8["axes"]` has no `"A8"` → `compute_kv` skips `_kv_a8_section` → no A8 verdict.
**Proposed change:** None beyond v2; the spec already states both branches.

### F19 — Minor — `kv_flags` A8 entries are listed but not pinned to the flag schema
**Location:** Spec §6 (line 160); `p426_signals.py:1721` (`kv_flags` iterates `("A1","A5","A7")`).
**Evidence:** confirmed. v2 says `kv_flags` adds "A8 LOSS, UNDECIDED, interaction, HOLD, `operator_review`, `a8_dnf_sensitivity`, size warnings". The existing `kv_flags` loop is `for axis in ("A1","A5","A7")` — A8 is not in the tuple. The `a8_dnf_sensitivity` and `operator_review` flags are new and have no existing pattern.
**Problem:** v2 lists the flags but doesn't say the implementer must add `"A8"` to the `kv_flags` loop and add new flag branches for `a8_dnf_sensitivity`/`operator_review`. The `a8_dnf_sensitivity` flag (paired-exclusion sensitivity) is computed in `_kv_a8_section` — but `kv_flags` must read it and emit a blocking flag. v2 says this but the flag's `blocking`/`items`/`text` shape isn't given.
**Failure scenario:** Implementer adds `_kv_a8_section` but forgets `"A8"` in the `kv_flags` loop → the A8 verdict is computed but no LOSS/HOLD flag is emitted → the operator sees no blocking flag.
**Proposed change:** State that `kv_flags`'s axis loop adds `"A8"`, and give the `a8_dnf_sensitivity`/`operator_review` flag shapes (e.g. `dict(flag="a8_dnf_sensitivity", member="A8", value=..., items=[...], blocking=True, text=...)`).

### F20 — Minor — `GradeOutcome.outcome = "model"` invariant is stated but the `outcome="parsed"` wording could mislead
**Location:** Spec §1 (lines 56–58); `corpus.py:62` (`if self.outcome not in OUTCOMES: raise ValueError`), `:20` (`OUTCOMES = ("model","infrastructure")`).
**Evidence:** confirmed. v2 says "`GradeOutcome.outcome = "model"` for EVERY graded tg2 outcome" — this is explicit and correct. The earlier line "`parsed` → `failing = ...`" uses `parsed` to mean the `tg2_grade` outcome, not the `GradeOutcome.outcome`. An implementer reading carefully sees the "EVERY graded tg2 outcome" line. Resolved.
**Problem:** The two uses of `outcome=` (tg2_grade outcome vs GradeOutcome outcome) could still confuse a literal implementer who reads the `parsed →` line first. But v2's explicit "GradeOutcome.outcome = 'model' for EVERY graded tg2 outcome" resolves it.
**Failure scenario:** None if the implementer reads the full section.
**Proposed change:** None beyond v2; optionally reword "`parsed` →" to "tg2 outcome `parsed` →" for clarity.

### F21 — Minor — `storage_cap` resource flags are still ambiguous
**Location:** Spec §1 (line 57); `tg2_grade.py:1189` (`storage_cap` = tree exceeds byte cap).
**Evidence:** confirmed. v2 says "compile_failure, timeout, oom, mem_kill, crash, storage_cap → every leaf failing, outcome='model', resources.grader_oom ⇔ oom, resources.grader_mem_kill ⇔ mem_kill". This ties oom→grader_oom and mem_kill→grader_mem_kill but doesn't explicitly say the other four set both False. The B4 ledger L9 flagged `storage_cap → grader_oom=True` as wrong; v2's wording fixes it in principle but leaves `storage_cap`'s flags unstated.
**Problem:** An implementer could read "resources.grader_oom ⇔ oom" as the only constraint and leave `storage_cap → grader_oom=True` (the candidate's mapping). `grader_oom` feeds the arm identity; a wrong value drifts the identity.
**Failure scenario:** A model writes a 1.6 GB tree (storage_cap) → recorded as `grader_oom=True` → the arm identity's `grader_oom` flag is wrong → `generation_identity_sha256` differs → B8 rejects the pair.
**Proposed change:** State: "For compile_failure, timeout, crash, storage_cap: `resources.grader_oom = False`, `resources.grader_mem_kill = False`. Only `oom` sets `grader_oom = True`; only `mem_kill` sets `grader_mem_kill = True`."

### F22 — Minor — `kv_axis_verdict`'s `languages` is a `{item_id: language}` mapping; v2 doesn't say where it comes from
**Location:** Spec §6 (line 156); `m76_rule.py:686` (`if axis == "A8" and languages is not None: hold = a8_hold(...)`), `:688` (`_groups_of("axis_verdict", "language", languages, ids)`).
**Evidence:** confirmed. `axis_verdict`'s `languages` is `{item_id: language}`. v2 says `_kv_a8_section` calls `axis_verdict("A8", 1, test, ref, languages=…)` but doesn't say where the mapping comes from. The tg2 universe entry has the item's language (the item id is `<lang>/<name>`), so the mapping is `{i: i.split("/")[0] for i in common}`. The spec doesn't state this.
**Problem:** Minor; an implementer can derive it from the item ids. But the spec should pin it.
**Failure scenario:** Implementer passes `languages=None` (no mapping) → `hold = None` (F8 again). Or passes the wrong shape.
**Proposed change:** State that `languages = {item_id: item_id.split("/")[0] for item_id in common}` (the item id's language prefix), built in `_kv_a8_section`.

### F23 — Scope request — The tg2 freeze / amendment / sequencer is a substantial new surface
v2 specifies the formulas and the order but leaves the `p426_freeze`/`p426_wave2` implementation to the implementer (F6, F13, F14). This is a new surface comparable to the tg1 freeze. Request: scope the tg2 freeze + sequencer as a named build step with its own interfaces (function names, parser flags, record shapes), or confirm the operator writes the freeze and the sequencer only reads it.

### F24 — Scope request — The C331 (3) re-check gates with stop/resume
v2 defines the re-check semantics (inside → continue; outside/`operator_review` → stop rc 5, resume on `--recheck-ack`) but not the parser flag, the `Stop` hook, or the resume semantics (F14). Request: scope the `--recheck-ack` flag and the sequencer's stop/resume protocol as a named build step.

### F25 — Acceptance gap — The tg2 freeze round-trip and the re-check gates are not in acceptance criterion 1's explicit list
v2's acceptance criterion 1 lists "the freeze round-trip (rehearsals → v8 → pilot → gate → amendment → s1); the re-check gates (inside / outside / unrealisable; the ack)" — so this IS listed. Resolved. (Self-correction: F12's residual gaps are F6/F13/F14, not the acceptance list.)

---

## Summary

Round-1 findings D1–D21 are all resolved in principle by v2 + C346. The material new gaps are:

- **F6 (blocker)** — `p426_freeze.cmd_v8`/`write_amendment` cannot produce the tg2 v8 base or amendment; the `--corpus` flag is absent,`deadline_formula` refuses tg2 languages, and R1 is required.
- **F1 (major)** — `ChainConfig`/`freezes_schedule`/`verify_schedule` are inconsistent with builder `tg2_p426`.
- **F2 (major)** — `schedules.tg2_p426` has no `plan_*` reader or membership verifier.
- **F4 (major)** — `p426_panel` A8 members are not wired into `kv_members`/`kv_export`/`kv_expected_members`.
- **F5 (major)** — `structured_grade.validate_reports` rejects every tg2 outcome and language.
- **F7 (major)** — `verify_a8_kv` must read `wave2.tg2/`; the wave-directory constant is unnamed.
- **F8 (major)** — `kv_axis_verdict` must be extended to forward `languages` (D12's resolution depends on this).
- **F9 (major)** — run-time injected positives cannot use the existing `--tg1-inject` path; `inject_verify` hardcodes the tg1 label.
- **F10 (major)** — harvest `classify` rejects most tg2 per-grade files; no patterns given.
- **F13 (major)** — the "strict pilot gate" for tg2 is undefined.
- **F14 (major)** — the sequencer's tg2 leg table and `after_leg` re-check hooks are undefined.
- **F15 (major)** — `KV_DOSSIER_PAIRS` must be parameterised to reject `r1`/`makeup`/`s3` for tg2.
- **F19 (minor)** — `kv_flags` A8 loop entry and the `a8_dnf_sensitivity`/`operator_review` flag shapes are not pinned.
- **F21 (minor)** — `storage_cap` resource flags are still ambiguous.
- **F3, F11, F12, F16, F17, F18, F20, F22 (minor)** — signature/wording ambiguities a literal implementer could get wrong.

The blocker (F6) and the sequencer/pilot-gate gaps (F13, F14) are the ones that defeat the goal outright: without them the tg2 freeze never writes and the decider never runs. The rest are major seams a literal implementer would either invent (diverging from the test-writer) or get wrong, silently defeating a guarantee (F8 kills the HOLD; F5 kills every tg2 row; F7 kills A8 verification; F10 kills harvest).

NOTHING ELSE OF SUBSTANCE.The background `find` for `spec-v1-to-v2.diff` completed successfully — the file was already located and read earlier at `~/ws/mlx_local_stack_workdir/fe-m76b4b/design-panel/snap/spec-v1-to-v2.diff`. No follow-up needed; the review above is complete.
