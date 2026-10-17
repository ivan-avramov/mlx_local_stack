G29 — blocker — `tg2_grade.py:898-1028`  
Deletion still lacks proven ownership. Registries are written before creation; normal cleanup deletes names unconditionally. Explicit cleanup accepts any registry path, ignores `base`, does not require exact `<base>-{w,r}` names, and never validates volume labels. A pre-existing same-name object or crafted registry can therefore delete foreign storage. Random names/static labels are not ownership proof.

G30 — high — `tg2_grade.py:1005-1028`  
`remove_registered()` ignores return codes from initial container/volume listings. If Docker listing fails with empty stdout, it treats objects as absent, unlinks the registry, and exits successfully without verification.

G31 — high — `tg2_grade.py:882-897`  
`grade()` checks `TREE_CAP` before `list_leftovers()`. An oversized tree returns `storage_cap` while labelled leftovers exist, bypassing the required `TransportAbort` refusal.

G32 — medium, non-blocking verification — `test_tg2_grade.py:1532-1538`  
G28’s polling loop falls through after 600 failed parses rather than requiring readiness. The old replacement race can therefore recur after 120 seconds. Require successful synchronization or fail the test.

G25–G27 are moot under P363’s no-automatic-sweep decision. G28 is improved but not fully deterministic. The chain-runner isolation fix does not mask failures: timeout still fails unconditionally, while normal runner exceptions still propagate.

VERDICT: NOT CLEARED
