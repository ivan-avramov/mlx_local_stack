I have traced the spec against the code and harvested records. Findings below.

---

## Findings

**F1 — Blocker — §7.1 vs §6.4: the panel Holm re-adjustment breaks the "only A8 added" golden.**
- Location: §6.4 ("the family re-adjusted with A8") vs §7.1 part 2 ("with `wave2.tg2` present only `axes.A8` / the A8 sections are added") and §1 ("Every existing output … is byte-identical").
- Evidence: confirmed. `kv_panel_section` → `kv_panel_family(members)` (`p426_signals.py:1591,1507`) calls `stats.holm([p for m in tested])` over the whole tested family, then `kv_members()` lists every member. Holm‑adjustment is rank‑dependent: inserting A8‑s1/A8‑s2 p‑values shifts the ranks of A1…A7‑s* members and changes their `holm_p` whenever an A8 p‑value lands below an existing one. `render_kv` prints one shared `## Panel` block (`p426_signals.py:192I'll deliver findings in numbered chunks.

## Findings (1/3)

**F1 — Blocker — §7.1 vs §6.4: the panel Holm re-adjustment breaks the "only A8 added" golden.**
- Location: §6.4 ("the family re-adjusted with A8") vs §7.1.2 ("with `wave2.tg2` present only `axes.A8` / the A8 sections are added") and §1.
- Evidence: confirmed. `kv_panel_section` → `kv_panel_family` (`p426_signals.py:1591,1507`) runs `stats.holm(...)` over the whole tested family, and `render_kv` emits one shared `## Panel` block listing every member with its `holm_p` (`p426_signals.py:1928‑1933`). Holm is rank‑dependent, so inserting A8‑s1/A8‑s2 changes A1…A7 members' `holm_p` whenever an A8 p‑value ranks below an existing one.
- Problem: §6.4 mandates a re‑adjustment that mutates A1…A7 panel lines; §7.1.2 mandates that with `wave2.tg2` present *only* A8 sections are added (A1…A7 byte‑identical). Both cannot hold.
- Failure scenario: A8 members are added; an A8 p‑value is smaller than some A7‑s* p‑value; the A7 member's `holm_p` line in `SIGNALS.md` changes; the §7.1.2 golden diff fails (or, if the implementer satisfies §7.1.2 by *not* re‑adjusting, §6.4 is violated and the family p‑values are wrong).
- Proposed change: rewrite §7.1.2 to state that with `wave2.tg2` present the A1…A7 per‑axis sections and the A1…A7 members' raw fields (`judged/identical/vector/mean`) are byte‑identical, but the shared `## Panel` block is re‑rendered with the A8 members and the Holm family re‑adjusted across all members. Add a golden that captures the re‑adjusted A1…A7 `holm_p` (not the old ones).

## Findings (2/3)

**F2 — Major — §6.2: the protected set for tg2 is underspecified and the current code silently accepts forbidden build‑file edits.**
- Location: §6.2 ("protected = the entry's `tests` ∪ the build files the prompt forbids editing").
- Evidence: confirmed. The tg2 universe entries have `protected: None` (`benchmark/m65/tg2_universe.json`, `rust/say`, `javascript/word-search`, `java/zipper`, `cpp/spiral-matrix`). The existing `_a7_diff` (`p426_panel.py:598`) does `protected = set(entry.get("protected") or {}) | {entry["test"]}`, so for tg2 it reduces to `{tests}` only — `Cargo.toml`, `build.gradle`, `gradlew`, `package.json`, `babel.config.js`, `CMakeLists.txt`, `test/catch.hpp`, `test/tests-main.cpp` are *not* protected. The prompt (`corpus_tg2.prompt`) forbids editing "the build files"; the grader's protected set is `structured_grade.protected_manifest(prepared, solutions)` (`structured_grade.py:90`), which is `{p: h for p,h in prepared if p not in solutions and not p.startswith(".docs/")}` — i.e. tests + all build/scaffold files.
- Problem: the spec names "the build files the prompt forbids editing" without a derivation, and the tg2 universe carries no `protected` field. An implementer following the spec literally (or reusing `_a7_diff` unchanged) would silently accept a model edit to `build.gradle`/`CMakeLists.txt`/`package.json` into the packet diff — exactly the silent‑acceptance of wrong data the request names.
- Failure scenario: a both‑pass item where the model edited `CMakeLists.txt`; the A8 packet ships the diff; the panel judges a tree the grader would have called tampered.
- Proposed change: specify `protected = protected_manifest(entry["prepared"], entry["solutions"])` (which already includes tests + build/scaffold files), and the Cargo.toml exception via `tg2_grade.cargo_manifest_reasons(entry["prepared_cargo_toml"], current_text)` (see F4). Add a red test: a changed `build.gradle`/`CMakeLists.txt` refuses the export.

**F3 — Major — §4.2: the reload control "X reload vs X s1/s2" is not a same‑seed control for s2.**
- Location: §4.2 ("the reload control (same‑seed X reload vs X s1/s2 and N16 reload, discordance only)").
- Evidence: confirmed. `schedules.TG2_LEG_TABLE` (`schedules.py:58‑61`): `pilot`/`reload`/`s1` use `seed_base=1001`; `s2` uses `seed_base=2002` with reversed language order. `reload` is 5 items/language in the rust→cpp order; `s2` is 20 items/language in cpp→rust order. So reload shares seed and item order with s1 only, not s2.
- Problem: "X reload vs X s2" pairs different items under different seeds; the discordance is meaningless as a same‑seed reload control. The spec's wording invites the implementer to compute a discordance against s2 that has no diagnostic value and could mask a real reload reproduction failure.
- Failure scenario: the signals sheet reports "X reload vs X s2 discordance = 0/5" as a clean reload control, while X reload actually diverged from X s1 on 2/5 items — the operator is misled.
- Proposed change: §4.2 should read "same‑seed X reload vs X s1 (first 5 items) and N16 reload vs N16 s1, discordance only". Drop "/s2". (Answers Q2.)

**F4 — Major — §6.2 Cargo.toml exception: re‑implementing it diverges from the grader.**
- Location: §6.2 ("a changed protected file refuses EXCEPT Rust `Cargo.toml` `[dependencies]` additions naming crates in `OFFLINE_CRATES.md`").
- Evidence: confirmed. `tg2_grade.cargo_manifest_reasons` (`tg2_grade.py:262`) already enforces exactly this: only `[dependencies]` may differ, every new/changed entry must name a crate in `RUST_ALLOWLIST` (= the `OFFLINE_CRATES.md` disclosure line, `rust_disclosure_line`), with a string version. The grader's `accepted_files` (`corpus_tg2.py:386`) uses it to decide whether a changed `Cargo.toml` is in the final tree.
- Problem: the spec describes the rule in prose rather than naming the function. An implementer who re‑implements it (e.g., "additions only", or matching against the `OFFLINE_CRATES.md` *file text* instead of `RUST_ALLOWLIST`) will diverge from the grader: a `Cargo.toml` the grader accepted (row `passed=True`, tree in evidence) would be refused by the panel, or vice‑versa.
- Failure scenario: model changes a version spec of an allowlisted crate (grader accepts; `cargo_manifest_reasons` passes); the panel's re‑implementation rejects "additions only" → the A8 member export refuses on a both‑pass item, dropping a packet the readout needs.
- Proposed change: §6.2 should state the exception is `tg2_grade.cargo_manifest_reasons(entry["prepared_cargo_toml"], current_text) == []` (reuse, do not re‑implement). (Answers Q4.)

## Findings (3/3)

**F5 — Minor — §3.1: `_harvest_reasons_kv` and `_sequence_*` do not use `WAVE`; the parameterisation list is wrong.**
- Evidence: confirmed. `_harvest_reasons_kv` (`p426_verify.py:2201`) uses only `prefix = f"benchmark/results/{KV_ROOT}/"` — namespace‑agnostic; A8 HARVEST `main` paths are `benchmark/results/m76/wave2.tg2/...` and `pub[len(prefix):]` resolves under `rows_root/m76` for both axes. `_sequence_pair_and_superseded` / `_sequence_leg_reasons` (`p426_verify.py:500,565`) operate on the `seq` dict, not paths.
- Problem: the spec lists them as needing the axis namespace; an implementer who threads a `wave` arg through them adds dead parameters and risks touching the mtp path (the `_sequence_*` helpers are shared with `verify_a7`).
- Proposed change: drop `_harvest_reasons_kv` and `_sequence_*` from the §3.1 list; keep `_kv_load_attempt`, `harvest_manifests`, `pair_keys`, `_supersede_reasons`, `_kv_dossier_reasons`, and the `verify_all_kv` existence check.

**F6 — Minor — §3.2/§4.1: A8 confirmatory sessions are hardcoded, not derived from the plan.**
- Evidence: confirmed. A7 derives its sessions via `kv_a7_sessions()` → `m76_rule.axis_plan("A7")["looks"][-1]["size"]` (`p426_plan.py:434`). The A8 plan carries `sessions=2` (`m76_rule._AXES["A8"]`), but §3.2 hardcodes `("s1","s2")` "never `kv_a7_sessions`" without a `kv_a8_sessions()` helper.
- Problem: if the A8 plan's `sessions` ever changes (e.g., a reload‑as‑third‑session variant), the spec's hardcoded list silently diverges from the plan; `axis_verdict("A8",...)` would still expect `expected_sessions=2` and the signals would refuse on a session count the spec told B8 to accept.
- Proposed change: add `kv_a8_sessions()` reading `m76_rule.axis_plan("A8")["sessions"]` and use it in both §3.2 and §4.1 (with the same `2 <= k <= 2` guard A7 has).

**F7 — Minor — §5: "a missing re‑check record for a harvested session refuses" is ambiguous for pilot/reload.**
- Evidence: confirmed. Re‑checks are `recheck‑s1` (after s1) and `recheck‑s2` (after reload, over s1+s2) per the runner spec; pilot and reload have no re‑check. The harvested `wave2.tg2/run/sequence.json` has `"rechecks": {}`.
- Problem: "for a harvested session" can be read as "for every harvested session including pilot/reload", which would make B8 refuse the currently‑harvested pilot pair (no `recheck‑pilot.json` exists).
- Proposed change: §5 should say "a missing re‑check record for a harvested *confirmatory* session (s1, s2) refuses; pilot and reload have no re‑check."

**F8 — Minor — §6.1: `kv_members()` has no access to `axes.A8`; the signature change is unspecified.**
- Evidence: confirmed. `kv_members(sessions=None)` (`p426_panel.py:1238`) only knows A7 sessions; it has no `b8`/`a8_sessions` parameter. `kv_export`, `kv_panel_members`, `kv_expected_members`, `kv_panel_completeness`, `kv_panel_family` all call it. §6.1 says "kv_members() gains them when axes.A8 exists" without specifying how.
- Problem: the implementer must invent the seam (an `a8_sessions=` kwarg threaded from `b8["axes"]["A8"]["sessions"]` through five call sites); the spec gives no contract, so the test‑writer and the implementer may diverge.
- Proposed change: specify `kv_members(sessions=None, a8_sessions=None)` and require every caller to pass `a8_sessions=b8["axes"]["A8"]["sessions"]` when `axes.A8` exists (None otherwise → byte‑identical).

**F9 — Scope request — §3.4: "legitimately differs" is undefined for tg2 provenance keys.**
- Evidence: confirmed. The tg2 manifest's `runtime` carries many tg2‑only keys (`scaffold`, `carrier_source_sha256`, `opencode_bench_config_sha256`, `opencode_exe_sha256`, `scaffold_policy_sha256`, `probe_code_sha256`, `generation_identity_sha256`, `epoch_id`, `polyglot_sha`, `frozen_prompt_date`, …). §3.4 says "any tg2‑only runtime key that legitimately differs between arms is added to the allowed list with a cited reason, nothing else" but does not define "legitimately".
- Problem: an implementer could whitelist a key that *should* match between arms (e.g., `scaffold` or `carrier_source_sha256` differ because one arm ran a different carrier) and silently accept a config mismatch the session pair should reject.
- Proposed change: §3.4 should state the criterion: a key may be whitelisted only if it is per‑invocation (already removed by `kv_a7_normalise`) or a documented KV‑mode key already in `KV_PROVENANCE_WHITELIST`; any other difference rejects. Require the test to assert that no tg2‑only key is whitelisted beyond per‑invocation identity.

---

## §9 questions — recommendations

- **Q1 (is §3.3 right for A7 too):** Yes. A7's HARVEST publishes every `final_tree/manifest.json` as a `main` file (verified in `wave2/.../HARVEST.json`); a row whose `final_tree.manifest_sha256` matches no published manifest is a harvest gap or tampering, and should reject the session rather than pass silently as `identical:false` with null shas. The spec's "A7's existing inputs all match" is a hypothesis the §7.1.1 golden verifies; the rule fires only on a real mismatch, so it cannot break a legitimate A7 row.
- **Q2 (reload control meaningful):** No — see F3. Drop "/s2"; the meaningful control is X reload vs X s1 (and N16 reload vs N16 s1), first 5 items, same seed 1001.
- **Q3 (include H in task text):** Include H. H is part of the exact prompt bytes the model saw (E1); the §6.2 prompt‑sha check requires the rebuilt prompt to equal the transcript's first user message, which carries H. H leaks nothing — its tokens (`src/`, `OFFLINE_CRATES.md`, `Cargo.toml`, "Helper .js files…") match no `KV_LEAK_PATTERNS` (`p426`, `caslca/`, `m76`, `tq4`, `kv_bits`, `m72_`, `n16`), no registry name, no box identity, no template tag.
- **Q4 (Cargo.toml exception):** Reuse the grader — see F4. Accept any `Cargo.toml` edit for which `tg2_grade.cargo_manifest_reasons(entry["prepared_cargo_toml"], current_text)` is empty; do not re‑implement.
- **Q5 (identical multi‑file tree at 0.5):** Yes, keep 0.5. `identical` comes from B8's `pair_keys` (`p426_verify.py:387`): `mo is not None and mo == mn`, where `mo`/`mn` are the manifest *file* shas. The manifest covers the whole file set (`files: {rel: sha}` + `missing`), so equal manifest shas ⇒ identical multi‑file trees. No change.

---

## Driver's assumptions

1. **tg2 rows carry every field in tg1's shape** — confirmed (same key set: `id`, `passed`, `converged`, `final_tree.{manifest,manifest_sha256,files,missing}`, `sampler_seed`, `evidence_sha256`, `runtime.arm_identity`, …).
2. **§3.3 does not change any existing A7 output** — hypothesis (spec asserts; the rule fires only on a manifest mismatch; §7.1.1 golden verifies). The risk is a false positive on an A7 row whose run_id in `final_tree.manifest` doesn't match the HARVEST‑published run_id — verifiable, not provable from the spec alone.
3. **Rebuilding the task text reproduces the bytes the model saw** — hypothesis, enforced fail‑closed by the §6.2 prompt‑sha check against the transcript's first user message (transcript is on the `evidence` branch at `<prefix>wave2.tg2/<att>/evidence/<run>/<lang>__<item>.json`; the row's `transcript_path` is a `$STACK_WORKDIR` path and not directly usable). The spec should name that path reconstruction and the message format.
4. **Materialised tree is the right start tree** — confirmed. `tg2_materialize.prepare_tree` rewrites JS `xtest`/Java `@Disabled` and emits `OFFLINE_CRATES.md`; raw polyglot bytes would fail the `prepared` hash for those items, so the materialised tree is required.
5. **A8 freeze separate without breaking bindings** — confirmed. `kv_check_frozen` (`p426_panel.py:1600`) binds each member's FROZEN to `b8_sha256`; A8 members are separate directories; the stage‑3 FROZEN files are not touched. The only seam gap is F8 (`kv_members` signature).
