# P542 — `qualify.py` for any registry entry (C254) — spec v1

## Goal
`dev/p369_phase2/qualify.py` (the R7 256K operational qualification: the largest accepted prompt, the 256K prefill / decode / retire
peaks via `mx.get_peak_memory`, prefill and decode tok/s) qualifies ANY entry of the stack root's committed `main_models.yaml`, in
either predictor state, so it serves the current picks and new candidate models. The production tree (`mlx_vlm/` excluding
`mlx_vlm/tests/`) does not change.

## Changes
1. **Entries**: `--entry <name>` accepts any `models[].name` of the stack root's committed registry (`<stack-root>/main_models.yaml`,
   strict parse). A name not in it refuses, listing the registry's names. `default_entries()` (no `--entry`) = every registry entry
   that carries, or can restore, an MTP block — i.e. the entries of `orchestrate.PICKS` that are in the registry (today the four MTP
   entries); `ENTRIES` (the fixed table) is removed.
2. **Arm per entry** (`arm_for(name, predictor, *, registry_entry, registry_state)` — replaces the table lookup):
   - no `--predictor`: **served** — the entry exactly as the committed registry serves it (MTP-ON if its committed block carries the
     MTP keys, else OFF).
   - `--predictor off`: an entry served MTP-ON gets a derived registry with that entry's MTP keys (`draft_kind`, `draft_model`,
     `mtp_verify_scan`, the `bench.p426_leg.MTP_KEYS` / C177 set) removed and nothing else changed (written under `--out`; its sha256
     recorded); an entry served OFF is served as committed.
   - `--predictor on`: an entry served MTP-ON is served as committed; an entry served OFF whose block is restorable by the 16-state
     generator (`orchestrate.overlay_registry`) is served with that overlay; otherwise refuse `<name>: no MTP drafter to restore`.
   - Arm names recorded in the report: `served_on`, `served_off`, `mtp_off` (derived), `mtp_on_restored`.
3. **MTP-ON gate (generalized C199)**: every arm that serves MTP-ON (`served_on`, `mtp_on_restored`) requires (a) the entry in
   `orchestrate.PICKS` (drafter shape for the draft-kernel check) and (b) a `--p369-summary` that is a P369 FULL-run PASS for exactly
   that entry (today's checks), whose `binding.production` / `manifest.production` equal THIS run's attested production
   (`--production-ref`, resolved as today; default `orchestrate.PRODUCTION`), not the old constant `7207179b`. `--p369-summary` may be
   given once per entry: `--p369-summary <name>=<path>` (repeatable); a bare path keeps working for a single `--entry`.
4. **Registry check**: the 16-state byte classifier (`registry_states.classify`) runs only when a `mtp_on_restored` overlay is built
   (it needs the pinned fixture); `served_*` and `mtp_off` arms need only the strict parse, so a registry with extra (new) entries is
   accepted for them. The existing guard that `--predictor off` "means the committed registry's OFF block" is replaced by rule 2.
5. **References**: `load_references` no longer refuses a name outside a fixed table; an entry without a reference reports its measured
   peak and `vs_guidance_gb` only (as today for `None`).
6. **Speed**: each entry's final report state carries `rates: {prefill_tps, decode_tps}` copied from the record (already measured), and
   `arm`, so one report gives capacity and speed per arm.
7. Everything else unchanged: reviewed-head / production-ref / tree guards, interference census, idle gaps, power events, the job and
   worker, the exact-command checks, `expected_config` (it already derives from the registry entry; an unknown registry key still
   refuses), the P452 ancestor rules.

## Acceptance
- Tests (hermetic; synthetic registries and summaries under `tmp_path`; no GPU, model or server) for: any registry name accepted, a
  non-registry name refused with the list; `default_entries`; each arm derivation (`served_on`, `served_off`, `mtp_off` with only the
  three keys removed and its sha recorded, `mtp_on_restored`, `no MTP drafter` refusal); the MTP-ON gate (missing summary, wrong
  entry, wrong production, a summary matching `--production-ref`, per-entry `name=path`); the classifier runs only for
  `mtp_on_restored` (a registry with an extra entry is accepted for served / off arms and refused for a restore); references optional;
  `rates` and `arm` in the report. Existing qualify tests (`test_p415_qualify.py`, `test_p426_qualify_predictor.py`,
  `test_p452_qualify_in_wrapper.py`) pass, amended only where they assert the removed fixed table (each amendment named).
- The fork's P369 harness tests pass; the fork gate passes; production diff empty.

## v1.1 — designer rulings after the independent tests
- `arm_for(name, predictor, *, registry_entry, registry_state)`: `registry_state` is the classifier result (`registry_states.classify`: the frozenset of MTP-OFF entries, or None); it is used only to decide a restore. A refusal raises `ValueError` with the message `<name>: no MTP drafter to restore` (or the classifier's reason, below).
- `default_entries(registry_entries) -> list[str]`: the registry's names that are in `orchestrate.PICKS`, in registry order.
- The MTP keys are a fork-local constant `MTP_KEYS = ("draft_kind", "draft_model", "mtp_verify_scan")` (the fork cannot import the stack).
- The derived `mtp_off` registry removes exactly that entry's lines of those keys textually (the entry block's span via `registry_states`), every other byte unchanged; its sha256 is recorded per entry as `overlay_sha256` (as `orchestrate`'s manifest does).
- Refusals of entries / arms / gates happen before the run (`SystemExit("refused: [...]")`), as `entry_problems` does today.
- The summary's `binding.production` / `manifest.production` must be a prefix (≥ 7 hex) of this run's resolved production sha.
- `--p369-summary`: a bare path with more than one `--entry` refuses; `name=path` splits on the first `=`; a name that is not an `--entry` refuses.
- The MTP-ON gate includes `summary_artifact_problems` (today's checks) for every MTP-ON arm.
- `rates` (and `arm`) are recorded whenever a record exists, not only on COMPLETED.
- Restorable = the name is in `registry_states.ENTRY_OFF` and the registry classifies (one of the 16 states); a registry that does not classify refuses a restore with `<name>: the registry is not one of the 16 accepted states (a restore needs the pinned fixture)`.
- Existing tests that assert the removed fixed table, the old arm names / signatures, the `7207179b` summaries or the removed `--predictor off` guard are amended by the implementer to the new behaviour; each amendment named in the report.

## v1.2 — after the cold review round 1 (sol / glm / Claude Sonnet)
- **One registry snapshot**: the registry bytes are read once under the run lock; arm selection, the MTP-ON gate, the derived / restored registries, hashing and execution all use exactly those bytes. Any later read that differs (or a stack HEAD that moved) refuses.
- **The MTP-ON arm is bound to the certified configuration**: for every MTP-ON arm, the worker argv qualify derives for the entry must equal the P369 run's `manifest.json` `picks[<name>].argv_on` (the run directory the summary names; the overlay file path is not part of the argv); any difference refuses `<name>: the served configuration differs from the one its P369 run certified (<first differing flag>)`.
- **Production**: both the summary's production and this run's production are resolved to full shas in the fork (`git rev-parse <ref>^{commit}`; the default `orchestrate.PRODUCTION` too) and must be equal; an unresolvable value refuses.
- **"Served MTP-ON"** means `expected_config(entry)["drafter"]` is set (`draft_kind: mtp` with a non-empty `draft_model`); an entry with only some of the MTP keys, or a non-MTP `draft_kind`, refuses `<name>: a partial or non-MTP draft block`.
- **`mtp_off` removal** locates the entry's top-level MTP keys through the YAML node marks of the strict parse (any quoting / indentation the strict parser accepts) and removes their complete source lines; the semantic-equality guard stays; a failure names the key and its line.
- **Filesystem names**: per-entry files and directories use a safe id (`[A-Za-z0-9._-]` kept, everything else `_`, plus the first 8 hex of sha256(name)); every resolved output path must lie under `--out`, else refuse.
- `arm_for` refuses a restore when `name` is not in `registry_state`.
