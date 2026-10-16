Review of `ed9a4030` (proposal-only commit; no implementation yet).

P1 — Blocker — “Scoring” controls subsequent generation  
`docs/specs/p311-identity-split.md:15-23`; `benchmark/run_opencode_probe_v2.py:690-721`; `benchmark/bench/answer_key.py:322-403`

`audit_states`, `require_audits`, and `rerun_plan` decide whether an item is done, blocked, or regenerated and which deny rules shape that regeneration. They depend on `answer_key.py`, `web_audit.py`, `web_audit_cursor.py`, the audit prompt, and `legacy_audit_records.json`. Leaving these exclusively in an unpinned scoring hash permits scoring drift to change the number or conditions of model attempts while preserving generation pairing.

Fix: split pure post-hoc scoring from rerun policy. Hash contact/audit interpretation, rerun eligibility, and deny planning into generation/decision identity, or persist an immutable rerun decision plus policy hash before launching another attempt.

P2 — High — Incorrect module partition  
`docs/specs/p311-identity-split.md:10-16`; `benchmark/run_opencode_probe_v2.py:603-610`; `benchmark/bench/provenance.py:1847-1869`

- `progress_gate.py` is omitted despite directly controlling v2 termination and already being hashed at `run_opencode_probe_v2.py:608`. C164 also explicitly included it.
- `model_params.py` and `quant_info.py` are observational on this tg1 path: the carrier controls actual sampling; `provenance.gather` merely records `params_for`, while quant inspection is best-effort and never blocks. Putting them in generation recreates unnecessary row orphaning.
- `rowschema.py`, `convergence.py`, and `structured_grade.py` are correctly generation-classified: they control seeds, gate budget resolution, and in-run grade boundaries respectively.
- `paths.py` should remain generation-relevant because it affects registry/router resolution and refusal.

Fix: add `progress_gate.py`; move purely observational provenance dependencies out of the pairing hash.

P3 — Blocker — Legacy `probe_code_sha256` continuity is internally impossible  
`docs/specs/p311-identity-split.md:14-18,33-39`; `benchmark/bench/tg1_runner.py:319-342`

The proposal simultaneously:
- adds `deny_rules.py` and `legacy_audit_records.json`,
- changes `answer_key.py` by extracting a function,
- requires `probe` to cover “all of the above,” and
- requires the legacy digest to remain byte-identical.

Those conditions cannot all hold. There also is no single current recipe: tg1 hashes relpath+NUL+bytes over its larger list, while `run_opencode_probe_v2.py:603-613` hashes basenames+bytes over six modules.

Fix: define exact per-scaffold legacy recipes and golden vectors. Preserve the field and algorithm for historical interpretation, but permit its value to change after the refactor. Explicitly scope whether standard v2 also receives the split.

P4 — High — Pilot/full resume still defeats scoring-drift tolerance  
`benchmark/bench/tg1_runner.py:1085-1097`; `benchmark/chains/c147/run_tg1_chain.py:113-121,538-540`

Pilot and full use the same rows file. The probe compares every `identity()` field on resume, and the barrier pins `probe_code_sha256`. A scoring-only change between pilot and full therefore aborts before chain-level generation pairing can help.

Fix: make resume and the first-manifest barrier pin generation identity while retaining row-specific scoring identity. Test scoring drift between pilot and full, not only between separate legs.

P5 — High — `generation_code_sha256` is insufficient as the pairing key  
`docs/specs/p311-identity-split.md:24-29`; `docs/specs/m64-scaffold-arms.md:81-89`

Equal repository code does not establish equal carrier, system prompt, client binary/snapshot, universe, sampling, predictor, seed schedule, or arm adapter. M64 correctly names a broader `generation_identity_sha256`, but P311 never defines its relationship to `generation_code_sha256`.

Fix: define a canonical composite such as `generation_identity_sha256 = H({generation_code_sha256, scaffold policy, carrier, universe, client/snapshot, served controls, sampling, arm adapter})`. Reports pair on this composite; code hash remains one component.

P6 — High — Legacy report fallback cannot solve old-to-new pairing  
`docs/specs/p311-identity-split.md:28-29`; `benchmark/results/p223_tg1/tg1_report.py:30-31,57-59`

Existing rows contain none of the three hashes; only adjacent manifests contain `probe_code_sha256`. Current reports load rows alone and pair by item ID. Falling back to the old probe hash only supports old-to-old comparisons—it cannot prove old-to-new generation equality when scoring changed, which is P311’s motivating case.

Fix: reports must load a leg envelope plus manifest and refuse mismatched composite identities. Add a reviewed migration map/sidecar assigning generation identity to approved historical manifests; otherwise declare old-to-new pairing unavailable.

P7 — Medium — Claimed CLI compatibility is not compatibility  
`docs/specs/p311-identity-split.md:24-27`; `benchmark/chains/c147/run_tg1_chain.py:721-743`; `benchmark/chains/c147/drive_chain.sh:4`

Requiring new `--generation-code-sha` rejects every existing caller that supplies only `--probe-code-sha`, despite saying the old option remains accepted for one release.

Fix: for the transition, accept either: generation pin selects new mode; probe-only selects legacy strict mode with a warning; both verify both. Alternatively declare a deliberate breaking migration and update every caller/document.

P8 — High — P311 and M64 disagree about contact ownership  
`docs/specs/p311-identity-split.md:20-23`; `docs/specs/m64-scaffold-arms.md:85-89`; `benchmark/run_opencode_probe_v2.py:519-583`

P311 keeps `answer_key.contact()` in-probe; M64 moves it to chain level. Moving it does not automatically make it scoring-only because M64 §9 uses the result synchronously to launch a same-slot rerun.

Fix: choose one owner and specify when the decision is frozen. Record both row-time scoring hash and report-time scoring hash when reports rederive labels.

P9 — Medium — Missing acceptance coverage  
`docs/specs/p311-identity-split.md:32-41`

Add tests for:
- pilot→full scoring drift;
- old/new report migration and generation mismatch refusal;
- full composite identity, not code hash alone;
- row-level stamping for every writer and mixed resume segments;
- exact legacy probe golden vectors;
- standard-v2 versus tg1 identity scope;
- CLI transition matrix;
- malformed/missing hashes in `RUNTIME_PINNED`, `SHA_FIELDS`, `validate_leg`, and `fake_probe`;
- rerun/contact-policy drift changing eligibility or deny plans.

AGREE WITH CHANGES: P1, P2, P3, P4, P5, P6, P7, P8, P9
