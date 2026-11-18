Cold read, round 1 of 3. Read-only. A one-line widening of a commit-hook exemption in benchmark/bench/modelnames.py (the model-name
check that blocks commits naming a model by shorthand). Existing rule P601: harvested Wave-2 records under
benchmark/results/p426/wave2(.<label>)?/{tg1-p426-*.aN,run,pairs}/ are verbatim data and are exempt. The first real M76 KV-lever
Wave 2 harvest (benchmark/results/m76/wave2/{tg1-m76-*.aN,run,pairs}/, and the tg2 namespace wave2.tg2/ with tg2-m76-*.aN) was
blocked because receipts list the model directory's files (`optiq/metadata.json`). The fix adds _M76_WAVE2 for those paths. <!-- allow-shorthand -->
Diff: fix.diff in this directory. Question: can the new pattern exempt prose or code that should stay checked (READMEs, scripts,
docs beside the data), or miss a real harvest path the KV sequencer writes (read benchmark/bench/p426_harvest.py namespace_root and
the KV leg names in benchmark/bench/p426_wave2.py kv_legs / kv_tg2_legs)? Numbered findings with severity (blocker / major / minor),
file:line and a concrete scenario; "no findings" if none. Do not modify any file.
