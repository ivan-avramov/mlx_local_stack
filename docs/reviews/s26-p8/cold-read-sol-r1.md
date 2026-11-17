Verdict: changes requested. Name mapping is correct, but record selection and relative worktree handling remain unsafe.

1. Leg-name coverage — no findings.

Trace through `leg_worktrees` → `leg_worktree`:

- KV tg1 pilot, s1/s2/s3, reload, makeup: `_arm_of` extracts the embedded `n16`/`x`/`v`.
- KV tg1 R1: the rehearsal regex uses the explicit arm.
- KV tg1 R2 mismatch: selects `arms[1]`, the treatment.
- KV tg1 R3 kill: selects `arms[0]`, the reference.
- KV tg2: every run and rehearsal name embeds its arm, so `_arm_of` resolves it directly.
- P426 MTP: ordinary legs embed `off`/`on`; mismatch maps to `on`, kill to `off`.

For valid generated KV records, arm order is safe: `resolve_arms` validates `(reference, treatment)`, freeze preserves that order, and `leg_worktrees` inserts those arms in the same order.

2. Wrong-arm selection

P1 — major — `benchmark/bench/p426_harvest.py:1197-1203`

`leg_worktrees` always prefers a sibling `v8_base.json` over the exact `--frozen-record`. For a rehearsal whose argv names `manifest.json`, an unrelated or stale sibling v8 silently supplies the arm order and worktrees.

Concrete scenario: `manifest.json` records `(x,v)` with current worktrees, but an old sibling v8 records `(n16,x)`. The mismatch leg resolves to the old X worktree rather than V. Distinct logs normally trigger the inode guard at `p426_harvest.py:811-816`, but the resolver has still selected the wrong arm; shared/hard-linked log files could pass that indirect check. Load the exact frozen record first and consult sibling v8 only when that record is a verified timeout amendment linked to it.

3. Watcher environment

P2 — major — `benchmark/bench/p426_wave2.py:1294-1297`

The injected `PYTHONPATH` is wrong when `cwd` is relative. `Path(cwd) / "benchmark"` remains relative, then Python resolves it from the child’s new cwd.

Concrete scenario: launched from `/repo` with `cwd="wt"` produces `PYTHONPATH=wt/benchmark`; inside child cwd `/repo/wt`, this resolves as `/repo/wt/wt/benchmark`, and `bench_watch.py` still raises `ModuleNotFoundError`. Use the resolved absolute cwd.

Apart from that, no finding: only watcher launches receive the modified environment. Chain launches retain the ordinary inherited environment, and no sequencer record is changed.

4. Test gaps

P3 — minor — `test_s26_kv_rehearsal_harvest.py:38-54`

The tests sample names rather than iterating every leg returned by `kv_legs`, `kv_tg2_legs`, and the P426 tables for every valid KV pair. In particular, direct R1 arm V and all X/V or N16/V table variants are not covered.

P4 — minor — `test_s26_kv_rehearsal_harvest.py:21-47`

The fixture never places a `v8_base.json` beside a rehearsal manifest, so P1 is untested. Add conflicting-sibling and tampered-arm-order cases, asserting refusal/no publication.

P5 — minor — `test_s26_kv_rehearsal_harvest.py:94-123`

Watcher tests use absolute `tmp_path` worktrees only, so P2 is missed. Also, the “chain keeps inherited environment” test deletes `PYTHONPATH`; it should verify a nonempty inherited value remains unchanged.
