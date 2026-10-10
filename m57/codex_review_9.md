**Verdict: FIX-THEN-SHIP.**

**A1 — BLOCKING: interruption can pair an old result with new provenance.** [run_retrieval.py:123]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/run_retrieval.py:123), [run_reasoning.py:198]($STACK_REPO/.claude/worktrees/agent-a6011ca833d3e6e68/benchmark/bench/run_reasoning.py:198).

Both drivers overwrite the canonical manifest **before** replacing the canonical result. With an existing `auto` result, rerun the same output name under `fused_v1`, then interrupt after manifest publication but before `os.replace`: the old result remains beside the new `fused_v1` manifest. The pending filename does not flag that canonical pair as invalid. I reproduced this for both drivers using their actual publication statements with an in-memory filesystem and injected `KeyboardInterrupt`.

Fix: publish the result and manifest through one atomic commit point, or bind them with a verified content digest and require readers to reject mismatched pairs. Add interruption coverage between manifest publication and result replacement. Atomic replacement of the result alone does not make the pair atomic.

- **Z1 — Fixed:** `provenance.py:639` treats lsof exit 1 with stderr as observation failure.
- **Z2 — Fixed for late `ServedConfigError`:** both drivers quarantine the staged result; reasoning also quarantines its journal. A1 remains a separate interruption defect.
- **Z3 — Fixed for supported entry points:** `provenance.py:728` checks server identity and router descent; `python -m mlx_vlm.server` and console-script workers pass.
- **Z4 — Fixed:** `provenance.py:652` uses completed backends, unions two completed observations, and refuses when neither completes.

Stale `.pending-<pid>` files are neither resumed nor consumed by the inspected result readers, and do not block subsequent runs. Successful publication preserves reasoning’s `--resume` input: the partial journal. The descent walk terminates on cycles; an exiting worker causes refusal rather than invented provenance.

Pytest was not run: the read-only sandbox prevents its temporary-file fixtures. Review used source inspection and the write-free reproduction above; the reported suite and live-check results remain user-supplied evidence.