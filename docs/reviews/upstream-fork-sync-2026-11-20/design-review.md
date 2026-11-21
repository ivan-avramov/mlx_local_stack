# Upstream sync design review

Round 1 of 3. Cold read by Codex GPT-6.2 Astra on the approved specification, published MLX-VLM and MLX-Serve baselines, and the pinned upstream tree. The review did not see the integrator's changes.

| Point | Disposition | Evidence |
| --- | --- | --- |
| P4 | Adopted | Upstream worker lifespan starts preload in the background and reports HTTP 200 from health during loading. The exact MLX-Serve pin promotes any HTTP 200 to READY and releases queued calls. Preserve the old router-visible worker readiness and retain progress where compatible. |
| P5 | Adopted | On omitted context management, upstream chat can enter compaction. The new continuation helper's default generator call lacks the fork cache-state keyword. Keep the existing default gates and assert cache-state and cancellation through the normal route. |
| P6 | Adapted | Upstream standalone worker cluster management accepts the server API key and can contact peers, stage resources, and persist a registry. The stack's outer router exposes a fixed route set, and its worker binds to loopback. Check those boundaries and absence of cluster activity under stack defaults. The standalone API key grants management access to the loopback worker when configured. |
| P7 | Adopted | Standalone mesh export can write under the worker directory. The fixed outer route set omits it. Check the route set and ordinary startup and chat for mesh activity, and describe the standalone behavior. |

## Candidate verification

Round 2 of 3. Codex GPT-6.2 Astra reviewed combined tree `9db7da86e0c1da54d9acc02fd4ba247ab3bc1edb` against the published MLX-Serve pin `0555b2fe`. The original independent test author froze the request, cancellation, readiness and managed-boundary tests before viewing candidate code.

| Point | Disposition |
| --- | --- |
| P4 | Resolved. Primary preload precedes completed startup and a primary error exits startup. Health rejects pending or failed primary readiness. Optional failure diagnostics survive, and pinned MLX-Serve can still detect process exit. |
| P5 | Resolved. Ordinary chat still uses the existing session resolver and default-off compaction. Streaming and nonstreaming pass cache state. Ordinary streams pass retention, close their iterator on cancellation, and create continuation state only on explicit opt-in. |
| P6 | Resolved under the adapted scope. The outer router has no cluster or internal management route. The worker is bound to loopback, keyless management is refused before registry access, and default chat takes the local path. A configured standalone server API key has the documented local management authority. |
| P7 | Resolved. The router has no mesh route. Ordinary startup and chat create no mesh jobs or output. Explicit standalone export retains its documented files after deleting the associated in-memory record. |

No new actionable review findings. Full-suite and exact-tip receipts are tracked separately. The prepared final range and its exact-only audit differences retain the original stage boundaries in the evaluation record.
