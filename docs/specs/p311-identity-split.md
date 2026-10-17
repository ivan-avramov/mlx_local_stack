# P311-lite — generation-only probe identity for tg1 (C164 approved; C170 chose "lite" over v2)

v4 2026-10-17 applies Cursor round 3 P21–P30 (`reviews/p311/round3…`, AGREE WITH CHANGES). v3 2026-10-17 (P311-lite, P352 option a). Supersedes v2 `2b161f64` (Cursor round 2 AGREE WITH CHANGES P10–P20 →
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

1. **Scoring out of the tg1 probe (P28, P29).** tg1 rows no longer carry the `_web_audit` fields (`web_fetches`, `net_shell`,
   `web_denied`, `subagent_calls`, `web_audit_incomplete`, `answer_key_contact`, `answer_key_evidence`). A scoring tool
   `benchmark/bench/tg1_score.py` derives them post hoc from each row's stored transcript (sha256-verified against the
   row's `evidence_sha256`) and the pinned corpus, writing `<rows>.score.jsonl` (one record per row key, with
   `scoring_code_sha256` and the transcript sha). Report scripts and `web_audit.needs_web_audit` read the sidecar
   (legacy rows: the in-row fields, labelled legacy). ONE fail-closed join `bench/row_scores.py` (row + sidecar by row
   key + transcript sha + `scoring_code_sha256`) is the only reader, used by `web_audit.audit_rows`,
   `answer_key.audit_states` / `report_rows` and every report counter; a missing, stale (transcript sha mismatch) or
   duplicate record → the row is unscored and excluded from strict scoring until rescored, never silently "no
   contact". Contact inputs (`.meta/example*`, `exemplar*`, `proof*`) are read from the recorded corpus git tree
   (`git show <polyglot_sha>:<path>`), never the live checkout; the score record carries the digest of those files.
2. **Separate tg1 entry (P21).** The generation code of `run_opencode_probe_v2.py` (carrier selection, spawn, export,
   provenance glue) moves to `bench/opencode_v2_core.py`; a new entry `benchmark/run_tg1_probe.py` imports only
   core + `tg1_runner`; the standard v2 entry `run_opencode_probe_v2.py` keeps its scoring paths (`_rerun_resume`, the
   web scan) and imports core. `_web_audit` / `_collect_web_audit` move to `bench/web_scan.py` (scoring);
   `shell_deny_patterns` moves to `bench/deny_rules.py` (generation; `answer_key` re-exports it). The chain runner's
   default `--probe` becomes `run_tg1_probe.py`.
   **Provenance trimming (P22):** `provenance.py`'s imports that tg1 never executes (`generate` and its transitive
   modules) become function-local in the non-tg1 paths, so the tg1 closure stays tight.
3. **Identity = generation import closure.** `probe_code_sha256` (field and relpath + NUL + bytes recipe kept) is
   computed over the repo-local static import closure of `run_tg1_probe.py`, found by an AST walk of every `import` /
   `from` (module- and function-level), plus a fixed list of non-Python inputs (plugins `toolbounds.js` /
   `noretry.js`, carrier source, prompt files) — no hand-kept module list. Tests both directions (P22): (a) the closure
   excludes `answer_key`, `web_audit*`, `web_scan`, `tg1_score`, `generate`; (b) every repo-local module in
   `sys.modules` after a fake end-to-end tg1 item is inside the closure; (c) every Python module in the closure is
   reachable on a tg1 path (call-graph reachability check from the entry, allow-list for deliberate data/plugin
   inputs); (d) golden value on a fixed temp tree.
   **Runtime toolchain (P23):** `scaffold_policy_sha256` gains the `.venv-bench` lock identity
   (`benchmark/requirements-bench.lock` sha + interpreter version) and the local grader image digest
   (`aider-benchmark` image id); the probe refuses a missing or changed image / lock.
   **Chain lifecycle (P24):** the chain runner freezes the sha256 of `run_tg1_chain.py`, `chain_ops.py`, the A4 gate
   and the launcher at chain creation in `chain.json` and verifies them before every launch, barrier, validation,
   resume and at exit; drift aborts (rc 2), never silently rewritten.
4. **Pairing composite** (P16, P25, P26): `generation_identity_sha256` (shared across arms) = sha256 of canonical JSON
   of `probe_code_sha256`, `scaffold_policy_sha256`, `opencode_version`, `opencode_exe_sha256`,
   `opencode_bench_config_sha256`, `carrier_source_sha256`, `agent_system_sha256`, `polyglot_sha`, `sampling_profile`.
   Model-specific identity is SEPARATE: `arm_identity_sha256` per (model, predictor) = sha256 of the effective worker
   fingerprint — the verified worker argv plus the served registry entry, covering the target AND draft artifacts
   (repo + revision / local hash) and every output-determining flag (`draft_kind`, `draft_model`, `draft_block_size`,
   `suffix_min_match`, KV scheme / cap, prefill step, session retention, APC state); unknown flags fail closed. The
   chain freezes a map {(model, predictor): arm_identity} at each arm's first manifest and the shared composite at the
   first manifest; resume and validation check both, plus today's separate model / language / seed checks (P18).
5. **`prompt_date` (P17, P27; C170 requires it in the pairing identity):** captured immediately before spawn (today it
   is read after generation — a midnight-crossing item can record the wrong date) and part of the ROW-level pairing
   key: `pair_identity = (generation_identity_sha256, arm_identity_sha256 for each side, prompt_date)`. Reports pair
   only rows with equal prompt dates; date-mismatched pairs are reported separately as descriptive. Consequence: a
   reference arm can be reused across days (C168 P356b) only if the date shown to the model is frozen per epoch —
   owed: an investigation whether opencode's date line can be fixed (plugin system-prompt transform, carrier system
   overlay or the client's clock environment), recorded and verified per row. Until then, reference reuse is
   same-day only.
6. **Forward-only.** No historical migration (C165 E1: cross-epoch comparisons are descriptive). The identity value
   changes once at this build (a new epoch for tg1). The standard v2 identity (`run_opencode_probe_v2.py:603-613`,
   basename recipe over six modules) also changes once, because `run_opencode_probe_v2.py` and `answer_key.py` are
   edited; no chain currently runs `opencode-v2-web` — recorded, not preserved.
7. **CLI:** `--probe-code-sha` keeps its meaning (now the generation closure); `--print-identity` adds
   `generation_identity_sha256` and `scoring_code_sha256` (of the scoring tool's closure, informational).

## Tests (red first)

1. Closure tests 3(a)–(d); standard v2 entry still imports its scoring paths and its rerun tests stay green.
2. `bench/web_scan` output == the old in-row `_web_audit` fields on recorded tg1 / v2 transcript fixtures (byte-equal
   JSON); `deny_rules.shell_deny_patterns` == old; carrier bytes unchanged.
3. Scoring-only edit (temp copy of `answer_key.py` / `web_audit_prompt.md`) → `probe_code_sha256` and the composite
   unchanged; generation edit → changed; the composite changes for each listed field; `arm_identity` changes for
   each output-determining worker flag and for a changed draft artifact; unknown flag → refused.
4. Toolchain drift (lock sha, interpreter, grader image id) → `scaffold_policy_sha256` changes; missing image → refused.
5. Chain lifecycle drift between legs and between pilot and full (edit a temp copy of `chain_ops.py`) → abort rc 2.
6. Multi-model chain: two picks freeze two arm identities; a changed draft model on the second arm aborts.
7. `prompt_date` captured at spawn: an item spawned before midnight and finished after records the spawn date;
   reports refuse to pair date-mismatched rows and list them.
8. `tg1_score` / `row_scores`: sidecar per row; stale transcript sha, duplicate record, missing record and a newer
   `scoring_code_sha256` replacing an older record are each handled fail-closed; dirty corpus reference file does not
   change the label (git-tree read); end to end transcript → `tg1_score` → P201 audit → strict exclusion.
9. Report scripts on P223 / M63 / c144-base rows (legacy in-row fields) give byte-identical outputs.
10. Chain runner: scoring drift between pilot and full (and between legs) → accepted; generation drift → abort; fake
    probe emits the composite + arm identity; malformed values fail closed in `validate_leg`.

## Out of scope

M64 arm identities (reuse the closure + composite per arm adapter); the standard v2 rerun policy; re-deriving labels of
legacy rows.
