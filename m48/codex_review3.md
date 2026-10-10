**No—do not bump `927d21bb` into the stack yet.** P5’s shipped-Qwen failure is fixed, but P4 retains a corruption path, and pin promotion introduces a continuation regression.

Reviewed committed HEAD atop `bb59774a`; working tree remained clean. Used `mlx-vlm/.venv/bin/python`, actual MLX caches on CPU, and the cached tokenizer. **55 retention tests passed, 1 skipped; 180 related tests passed.** No weights or live gates were run.

**P4 — PARTIAL, still blocking: missing captures bypass containment.**  
The explicit mismatch branch now clears the session correctly. Dispatcher reproductions confirmed this with absent, valid, and oversized anchor targets.

However, when model policy disables chunking and the planned boundary precedes prompt end, `ar.py` captures neither that boundary nor an interior anchor. The empty capture bypasses [the mismatch guard]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1402) and reaches [the legacy fallback]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1500), which trims KV without restoring recurrent state.

Actual dispatcher + autoregressive loop, shipped Qwen thinking-on template, synthetic LM updating real caches:

```text
prompt IDs:       191
planned boundary: 190
published IDs:    191
KV offset:        191
recurrent state:  after 192
```

This is a **new route into the existing P4 failure**, caused by the shorter boundary remaining uncaptured. Clear the session when no coherent captured state is available; do not publish the no-anchor fallback over recurrent layers.

**P5 — RESOLVED for the shipped Qwen case; boundary equality is unnecessary.**  
The placeholder’s common prefix and the real echo’s common prefix **can differ**. My thinking-on reproduction produced:

| Echo | Common prefix with generation prompt | Reuse outcome |
|---|---:|---|
| Content only | 190 | Exact canonical match through offset 197 |
| Includes `reasoning_content="plan"` | 191 | Content-only prediction diverges at 190; safely rewinds there |

The implementation correctly tests `k < boundary`, then returns `ids[boundary:end]` at [openai.py:524]($HOME/ws/mlx-vlm/mlx_vlm/server/openai.py:524). Thus **`k > boundary` works**: overlapping prompt tokens are included in the suffix because the cache was retired earlier. I also directly exercised the helper with a reasoning-preserving renderer: `k=191`, boundary `190`, exact reconstruction passed.

Through the actual dispatcher, content-only retirement produced **197 IDs, KV offset 197, recurrent marker 197**, matching the next rendering byte-for-byte through the assistant turn. Editing the earlier user content caused divergence at 53 and **actual reuse from pinned anchor 47**.

Two qualifications:

- The docstring’s “exactly boundary” requirement is stale; the code correctly requires **at least** the boundary.
- Placeholder `"x"` is not a universal lower-bound proof across arbitrary templates/client renderings. If the real prefix is shorter, canonical prediction is rejected; subsequent prefix checking preserves correctness, but retaining the entire user turn is not universally guaranteed.

The `ar.py` landing arithmetic passed CPU checks for both target orders and equal targets within one original chunk: `(anchor, retain)=(2,5),(5,2),(3,3)`. Checkpoints `[1,3,6]` also landed correctly, including with initial cache offset 10. Retention **equal to** the initial offset captured the start state correctly. Retention **below** it remained uncaptured—the comment claiming “at or before” overstates the implementation.

**P9 — RESOLVED as a ring primitive.**  
Existing-offset promotion now releases the old pin, pins the existing entry, and survives FIFO eviction. Both the committed regression and my actual retirement sequence passed:

```text
[100 pinned, 160, 161]
→ latest user starts at 161
→ [161 pinned, 200, 201]
edit at 180 → snapshot 161
```

**P10 — NEW: promotion pins a fallback offset instead of the unchanged user anchor, reopening P6.**  
When the latest user marker remains behind the reused cache, [pre-prefill capture]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:606) records the **current cache offset**. [Retirement]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:1263) unconditionally promotes that offset as the latest-user pin.

Actual dispatcher runs with the same user anchor at 100:

```text
retire 160: [100 pinned, 160]
retire 200: [100, 160 pinned, 200]
retire 240: [160, 200 pinned, 240]
edit at 120 → no snapshot; cold prefill
```

An in-memory comparison against the parent’s `capture_states` retained `[100 pinned, 200, 240]`; HEAD lost 100. This is a regression from the promotion change.

Keep the true user-anchor identity distinct from a best-available pre-prefill capture. A continuation must not replace an existing valid user pin merely because its cache starts later.

**P8 — PARTIAL: important coverage improved, integration gaps remain.**

- **P1:** fake-LM position-metadata coverage; actual LM position slicing remains outside these committed regressions.
- **P2/P3:** actual cache-layout mismatch and buffered-window checks are covered.
- **P4:** helper rejection is covered; dispatcher mismatch/missing-capture paths are not.
- **P5:** shipped tokenizer, thinking on/off, now covers the original newline-merge failure. Longer-prefix reasoning echoes are not covered.
- **P6/P9:** direct ring promotion/eviction is covered; repeated dispatcher continuations are not, allowing P10.
- **P7:** worker forwarding is covered.
- **Speculation:** mocked handoff verifies capture ordering, not actual MTP execution.
- Combined anchor/retention/checkpoint landings are not covered by the new committed tests.

Those gaps are CPU-testable. Live A2–A6 still require deployed-model reuse/eviction measurements, pure-attention control, the 20K tool-result case, MTP on/off output parity and smokes, and two-session full-stack pressure/swap measurements.

| Finding | Round-three verdict |
|---|---|
| P4 — consistent session publication | **PARTIAL — blocking missing-capture path** |
| P5 — template boundary and canonical suffix | **RESOLVED for verified Qwen rendering** |
| P6 — continuation anchor preservation | **REOPENED by P10** |
| P8 — regression coverage | **PARTIAL** |
| P9 — existing-offset pin promotion | **RESOLVED at primitive level** |
| P10 — fallback capture replaces true user pin | **NEW regression** |

**Fit to bump into the stack for live gates: NO.** Fix P4’s missing-capture containment and P10’s pin selection, with dispatcher regressions, first.