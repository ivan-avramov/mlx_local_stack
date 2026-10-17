G33 — blocker — `tg2_grade.py:809-833`, `proc_guard.py:765-785,1014-1017`  
Transient grading containers are unconditionally removed by name without nonce labels or inspection. A name collision makes `docker run` fail, then `_step()` deletes the pre-existing container. `ProcGuard.cleanup()` can likewise delete a holder intentionally left after nonce mismatch. G29 is unresolved.

G34 — high — `tg2_grade.py:203-208,1073-1083`, `proc_guard.py:765-785`  
Container removers and `remove_registered()` discard `docker rm` return codes. If removal fails but a subsequent listing reports absence, cleanup succeeds and the registry is unlinked. Removal uncertainty is lost.

G35 — high — `tg2_grade.py:1016-1021`  
Registry creation uses overwriting `write_text()`. A pre-existing `<base>.json` is touched without refusal, potentially destroying prior ownership evidence. Creation must be exclusive.

G30’s listing checks, G31’s reported ordering defect, and G32’s synchronization defect are resolved. No non-correctness findings.

VERDICT: NOT CLEARED
