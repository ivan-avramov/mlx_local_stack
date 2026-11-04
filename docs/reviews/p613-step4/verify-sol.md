- Sol P1 — resolved (major, confirmed): `_tool_state` now refuses malformed retained events. Across the 86 real items, all 12 error events had string `state.error`, no `output`; comparing error text would change zero classifications.
- Sol P2 — resolved (major, confirmed): `_final_ready` requires exactly `b1` and `b2`, both accepted, for every Wave-1 axis.
- Sol P3 / GLM F1 — resolved (minor, confirmed): the canonical SHA is recorded in `evidence_ref`; the supplied value is preserved in `evidence_ref_given`.
- GLM F2 — resolved (major, confirmed): a rejected A7 session makes both A7 and divergence incomplete and blocks FINAL; the test exercises this end-to-end.
- GLM F3 — resolved (minor, confirmed): `--evidence-ref` without `--panel` refuses before writing.
- GLM F4 — resolved (scope request, confirmed): generated committed-data output is tested to place the section exactly once between §4.5 and Flags.
- Steps 1–3 remain unchanged on the no-reference path; no vacuous acceptance test or alternative path to premature FINAL was found.

NOTHING OF SUBSTANCE
