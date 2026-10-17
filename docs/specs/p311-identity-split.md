# P311-lite — generation-only probe identity for tg1 (C164 approved; C170 chose "lite" over v2)

v3 2026-10-17 (P311-lite, P352 option a). Supersedes v2 `2b161f64` (Cursor round 2 AGREE WITH CHANGES P10–P20 →
P352). v1 `ed9a4030`. Reviews: `benchmark/chains/c147/reviews/p311/round{1,2}.cursor-gpt-5.6-sol-high.md`.

Problem: `tg1_runner.identity()` hashes generation and scoring code into one `probe_code_sha256`
(`benchmark/bench/tg1_runner.py:319-342`), so every scoring fix (P299, C163, P309) orphaned every row for pairing and
forced an ≈ 18 h re-baseline (C164).

Approach: instead of partitioning one hash, take scoring OUT of the tg1 probe process. The probe identity then is the
generation identity, by construction.

## Facts this rests on (verify in review)

- tg1 makes no in-probe rerun decision: `--rerun-of` is refused for every scaffold but `opencode-v2-web`
  (`run_opencode_probe_v2.py:910-913`); `_rerun_resume` / `audit_states` / `rerun_plan` are standard-v2 only.
- On tg1, scoring code runs in-probe only through `_web_audit` (`run_opencode_probe_v2.py:519-583`, called at
  `tg1_runner.py:1227`): web-fetch / net-shell extraction and `answer_key.contact()` labels — a pure function of the
  exported transcript (stored, sha256 in `evidence_sha256`) and the pinned corpus item dir. No tg1 control-flow
  decision reads its result.
- The LLM web audit (`web_audit.py`) already runs post hoc over rows.
- `answer_key.shell_deny_patterns` builds carrier deny rules (`run_opencode_probe_v2.py:246`): generation.

## Change

1. **Scoring out of the tg1 probe.** tg1 rows no longer carry the `_web_audit` fields (`web_fetches`, `net_shell`,
   `web_denied`, `subagent_calls`, `web_audit_incomplete`, `answer_key_contact`, `answer_key_evidence`). A scoring tool
   `benchmark/bench/tg1_score.py` derives them post hoc from each row's stored transcript (sha256-verified against the
   row's `evidence_sha256`) and the pinned corpus, writing `<rows>.score.jsonl` (one record per row key, with
   `scoring_code_sha256` and the transcript sha). Report scripts and `web_audit.needs_web_audit` read the sidecar
   (legacy rows: the in-row fields, labelled legacy). A missing / stale sidecar record → the row is unscored (never
   silently "no contact").
2. **Module moves** so the tg1 import closure excludes scoring: `_web_audit` / `_collect_web_audit` and their
   regexes move from `run_opencode_probe_v2.py` to `bench/web_scan.py` (scoring; the standard v2 probe imports it);
   `shell_deny_patterns` moves to `bench/deny_rules.py` (generation; `answer_key` re-exports it); every remaining
   `answer_key` import in `run_opencode_probe_v2.py` becomes function-local inside standard-v2-only paths.
3. **Identity = generation import closure.** `probe_code_sha256` (field and relpath + NUL + bytes recipe kept) is
   computed over the repo-local static import closure of the tg1 entry (`run_opencode_probe_v2.py` +
   `bench/tg1_runner.py`), found by an AST walk of every `import` / `from` (module- and function-level), plus a fixed
   list of non-Python inputs (plugins `toolbounds.js` / `noretry.js`, carrier source, prompt files) — no hand-kept
   module list. Tests: (a) the closure excludes `answer_key`, `web_audit*`, `web_scan`, `tg1_score`; (b) every
   repo-local module in `sys.modules` after a fake end-to-end tg1 item is inside the closure; (c) golden value on a
   fixed temp tree. Chain lifecycle code (`run_tg1_chain.py`, `chain_ops.py`) stays recorded by sha in `chain.json`
   (unchanged), not in the probe identity.
4. **Pairing composite** (P16): `generation_identity_sha256` = sha256 of canonical JSON of `probe_code_sha256`,
   `scaffold_policy_sha256`, `opencode_version`, `opencode_exe_sha256`, `opencode_bench_config_sha256`,
   `carrier_source_sha256`, `agent_system_sha256`, `polyglot_sha`, `sampling_profile`, `draft_kind`, and the served
   worker fingerprint (`provenance.config_fingerprint` + resolved model artifact). Recorded in the manifest; the chain
   runner pins it at the first manifest alongside the fields it pins today.
5. **`prompt_date` (P17):** opencode prints its own local date into the system prompt; it cannot be pinned. It stays a
   recorded per-row covariate (as today, C135), NOT part of the composite: putting it in would make every multi-day
   chain unpairable with every other. Reports disclose prompt-date differences per pair; C168's reference reuse
   already requires contemporaneous sentinels to detect drift.
6. **Forward-only.** No historical migration (C165 E1: cross-epoch comparisons are descriptive). The identity value
   changes once at this build (a new epoch for tg1). The standard v2 identity (`run_opencode_probe_v2.py:603-613`,
   basename recipe over six modules) also changes once, because `run_opencode_probe_v2.py` and `answer_key.py` are
   edited; no chain currently runs `opencode-v2-web` — recorded, not preserved.
7. **CLI:** `--probe-code-sha` keeps its meaning (now the generation closure); `--print-identity` adds
   `generation_identity_sha256` and `scoring_code_sha256` (of the scoring tool's closure, informational).

## Tests (red first)

1. Closure tests 3(a)–(c).
2. `bench/web_scan` output == the old in-row `_web_audit` fields on recorded tg1 / v2 transcript fixtures (byte-equal
   JSON); `deny_rules.shell_deny_patterns` == old; carrier bytes unchanged.
3. Scoring-only edit (temp copy of `answer_key.py` / `web_audit_prompt.md`) → `probe_code_sha256` and
   `generation_identity_sha256` unchanged; generation edit → changed; composite changes for each listed field.
4. `tg1_score`: sidecar per row; transcript sha mismatch → refused; missing record → row unscored in reports.
5. Report scripts on P223 / M63 / c144-base rows (legacy in-row fields) give byte-identical outputs.
6. Chain runner: scoring drift between pilot and full (and between legs) → accepted; generation drift → abort; fake
   probe emits the composite; malformed composite fails closed in `validate_leg`.
7. Standard v2: its rerun path still works (`_rerun_resume` tests unchanged and green).

## Out of scope

M64 arm identities (reuse the closure + composite per arm adapter); the standard v2 rerun policy; re-deriving labels of
legacy rows.
