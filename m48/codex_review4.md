Reviewed **`1bd249d3`**, read-only. Both round-three blockers are resolved; **no new regression found within the requested scope**.

Actual dispatcher + autoregressive-loop reproductions used a synthetic LM with real MLX caches on CPU. Loading the parent code in memory reproduced both old failures. **57 retention tests passed, 1 skipped; 180 related tests passed.** Working tree remained clean. No weights or live gates were run.

| Finding | Round-four verdict and evidence |
|---|---|
| **P4 — missing-capture fallback** | **RESOLVED.** Shipped Qwen thinking-on prompt: 191 tokens, boundary 190, chunking disabled. Hybrid session now clears cache, IDs, and ring; parent published 191 IDs/KV positions with recurrent state at 192. Pure-attention control still retains exactly 191 IDs/KV positions. |
| **P10 — fallback pin promotion** | **RESOLVED.** Marker stays at 100. Rings after retirement: `[100 pinned,160]` → `[100 pinned,160,200]` → `[100 pinned,200,240]`. Actual edit at 120 reuses 100; first LM call receives KV and recurrent state both at 100. Exact-marker promotion also survives: new marker 160 becomes pinned, and an edit at 180 reuses 160. |

**Fit to bump into the stack for the live gates: YES.** Live acceptance remains to be measured.