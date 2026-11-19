Round 2 of 3.

P1 — blocker — resolved — `benchmark/bench/p426_verify.py:542-547`  
Unreadable, missing, non-object, and unsealed earlier records now add a rejection reason. They no longer count as merely “not clean.”

P2 — blocker — resolved — `benchmark/bench/p426_verify.py:537-540`  
Validation is anchored on each chosen attempt and enumerates every preceding attempt, independent of surviving pair records.

P3 — major — resolved — `benchmark/bench/p426_verify.py:539-553`  
Each transition `aK → a(K+1)` independently requires the corresponding rerun reason, so a labelled final hop cannot conceal an unlabelled middle hop.

P4 — major — not fully resolved — `benchmark/bench/p426_verify.py:541-543`  
Building the name from a validated chosen member prevents the original `../outside.a1` attack, but the resulting earlier-attempt directory is not resolution-confined. Scenario: `wave2/tg1-…-s1.a1` is a symlink to an outside directory containing a sealed speed-invalid `leg.json`; B8 reads and accepts it. The chosen attempts receive resolved-parent checks, but earlier attempts do not.

P5 — blocker — `benchmark/bench/p426_verify.py:546-550`  
The earlier `leg.json` is not identity-bound to `old`. Scenario: replace a clean `x-s1.a1/leg.json` with a self-hash-valid INVALID record copied from another arm/session; a labelled `x-s1.a2` is accepted because only seal and cleanliness are checked. Require `doc["leg"] == leg` and `doc["attempt"] == k`, as `_leg_reasons` does for chosen attempts.

P6 — minor — `benchmark/bench/p426_verify.py:551-552`  
A non-string reason can satisfy the check because it is stringified. Scenario: `reason={"note":"x"}` is accepted as non-empty despite `--rerun-reason` being textual. Require a non-empty string.

Requested compatibility checks:
- Both MTP and KV call the shared helper and have the same behavior.
- A legitimate single rerun of a sealed speed-invalid attempt with an `attempt: 2` reason remains accepted.
- A sealed, identity-correct `state: "INVALID"` attempt can be rerun: it is not classified as clean.
- The real X pilot has the required sealed speed-invalid a1 and textual a2 reason.

Read-only/static verification; no files modified.
