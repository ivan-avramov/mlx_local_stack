1. **P1 — Major — `benchmark/bench/modelnames.py:47`**  
   `(.+/)?`, `batch\d+`, and `p\d+` accept malformed/non-panel paths such as `benchmark/results/m76/panel/A2/notes/batch0/p0.md`. Prose there bypasses checking despite not matching the writer’s `<member>/<judge>/batchNN/pNNNN.md` layout (`p426_panel.py:1390`). The tests cover positives but no malformed lookalikes.

No real packet, verdict, or failure-marker path written by the panel appears to be missed.
