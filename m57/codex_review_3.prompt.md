Cold adversarial CODE review. Read-only: do not modify files, do not load real models, do not run any Metal/GPU workload or server.
You may run the CPU-pinned tests named below.

UNDER REVIEW: branch `m57-prefill-profile` (two commits on top of `main`) in the sibling repo ../mlx-vlm — an env-gated diagnostic
profiler for the chunked prefill loop. Diff: `git -C ../mlx-vlm diff main m57-prefill-profile`.
SPEC it must satisfy: docs/specs/m57-prefill-profiler.md in this repo (sections Deliverable, Phases, Report, Tests, Rules).
Pattern it was told to follow: ../mlx-vlm/mlx_vlm/speculative/mtp_profile.py and its use in ../mlx-vlm/mlx_vlm/speculative/mtp.py.

The profiler will be used on a production serving path (mlx_vlm server, single-sequence chunked prefill of a 27B qwen3_5 hybrid
model with preallocated KV caches, MTP speculative decoding, session caches, snapshot/retention captures) to decide where
optimisation effort goes. Two things matter above all:
 (A) With MLX_VLM_PREFILL_PROFILE unset the change must be behaviourally inert on EVERY path through the touched functions — not just
     the tested one: decode steps, MTP verification (mlx_vlm/models/qwen3_5/speculative_verifier.py reuses
     `_prepare_projected_qkv`), batched/left-padded paths, other model families, vision prompts, exceptions mid-chunk, generator
     early-exit/close, concurrent requests in one server process.
 (B) With it set, the numbers must be TRUE: MLX is lazy, so check that every phase boundary really forces and fences the work it
     claims (`mx.eval` of the right arrays, `mx.synchronize()` on the right stream — the generation loop runs under
     `mx.stream(generation_stream)`), that no work leaks into a neighbouring phase or into `other`, that phases are not double
     counted, that the per-window means and the `keys=` value are computed correctly, and that the module-level active handle cannot
     leak across requests, threads or generators.

DELIVER (markdown, ids R1, R2, ..., most severe first; cite file:line): for each finding — what is wrong, the concrete scenario,
the consequence (inert-ness broken / numbers wrong / test gap / spec deviation), and the fix. Then: which spec test requirements are
genuinely covered by mlx_vlm/tests/test_prefill_profile.py and which are only nominally covered. Then a verdict: SHIP / FIX-THEN-SHIP /
REWORK. No praise, no restating the brief. If you ran tests, give the exact command and result:
`cd ../mlx-vlm && TMPDIR=$TMPDIR PYTHONPATH=$PWD .venv/bin/python -m pytest mlx_vlm/tests/test_prefill_profile.py mlx_vlm/tests/test_mtp_profile.py -q -p no:cacheprovider`

ROUND 2. The spec now has a binding "Amendment 1" (items 1-8) written after the first review round; read it. Check (i) that each
amendment item is REALLY satisfied by the code at branch tip (not just claimed), (ii) new defects introduced by the fix commit,
(iii) anything round 1 missed. Pay particular attention to: whether the terminal-layer exemption leaves exactly the production
graph unevaluated (no more, no less — e.g. the terminal layer's KV update must still be evaluated, and the terminal layer may be a
GatedDeltaNet layer in other configs); whether the entry fence evaluates more than this chunk's slice of the embeddings; whether
the thread-local handle is cleared on every exit path. Same deliverable format (ids S1, S2, ...), same verdict scale.
