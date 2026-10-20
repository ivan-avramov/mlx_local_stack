# P415 plan — Cursor plan review round 3 of 3 (gpt-5.6-sol-high, `--mode ask`), plan v3

I found two points where the v3 wording may not match the fork’s actual runtime objects, so I’m tracing those consumers before deciding closure: cache capacity is not represented uniformly across leaf types, and the “first streamed chunk” boundary may already include decode work.| ID | Status | Why |
|---|---|---|
| Q1 | OPEN — High | The measured request explicitly sets `max_tokens: 32`, while every registry default sets `max_tokens: 102400`. Therefore “every key equal at each hop” is impossible. Also, generation defaults are exposed by `get_server_generation_defaults()`, not `runtime.config`. Separately attest the complete live defaults, then assert request resolution equals the request override for `max_tokens` and registry defaults for omitted fields. |
| Q2 | OPEN — High | The exception is unsound. `PromptCacheState.update()` performs shrink before the terminal chunk is delivered; `shrink_to_offset()` allocates, evaluates, and synchronizes replacement buffers. It can therefore affect the measured decode peak, and post-request capacity will no longer equal the preallocation floor. Two other checks are unbuildable as written: a 261,120-token prefill produces 509×512, 511, and final 1-token forwards—not “512 except a shorter last”—and the cached path does not place `max_kv_size` on `ResponseGenerator` or pass it to `generate_step`. Finally, mlx-serve defaults absent registry fields to `memory_limit_frac=0.85`, while mlx-vlm auto-derives a cache limit, so these are not MLX defaults. Exercise shrink separately and exclude it from decode measurement, capture initial allocation before shrink, assert the actual forward sequence, attest the cap at its real consumers, and derive memory-limit expectations from reviewed mlx-serve defaults. |
| Q3 | CLOSED | With a fresh session and required `cached_tokens == 0`, capturing `_prepare_generation_inputs` output and matching both earlier preprocessing and sizing digests binds the IDs passed into cold prefill. |
| Q4 | OPEN — High | Fifteen-second sampling still permits a competing process or power excursion to start and finish undetected while affecting several 512-token chunks. The lock covers only cooperating campaigns, and command-line classification does not identify every arbitrary Python/Metal workload. Use per-prefill-chunk checks plus a substantially tighter watcher or durable process/activity accounting; any watcher gap or unreadable state must invalidate the entry. |
| Q5 | CLOSED | Supervised groups, extinction checks, atomic state transitions, interruption handling, continuation, malformed-result handling, and final nonzero status close the lifecycle failures. |
| Q6 | CLOSED | Repeated stack, registry, submodule, import-path, fork-ref, version, snapshot-revision, and weight-hash checks sufficiently bind the executable and artifacts. |
| Q7 | OPEN — Medium | The mandatory fingerprint still omits comparability inputs that can change peak memory: model snapshot/weight hashes, fork code revision or harness version, configured context cap, resolved cache/memory limits, shrink policy, output-token count, backend, and exact prompt/template identity. A same-named mutable model could otherwise receive a misleading delta. Missing historical values must make the reference non-comparable. |
| Q8 | CLOSED | Boot, request, entry, cleanup, and total worst-case timing are bounded; timeouts fail without retry. |
| Q9 | CLOSED | Retaining and validating the exact executable prefix, its installed entry point, and its resolution into the attested fork closes worker-level backend selection. Router behavior is explicitly out of scope. |

Q10
- Severity: Medium
- Plan section: §2 Q3; §3 T4/T14
- Problem: The plan states a fixed seed but never requires the resolved request or `generate_step` kwargs to contain that seed.
- Failure scenario: Seed forwarding regresses, yet the request still emits 32 tokens with `finish_reason == "length"`. Different token and MoE-routing paths produce non-repeatable rates and peaks while the entry reports `COMPLETED`.
- Fix: Capture the measured request’s resolved `GenerationArguments.seed` and generation-call `seed`; require both to equal the fixed seed. Add a seed-dropping sabotage test.

Q11
- Severity: Medium
- Plan section: §2 Q3; §2.1 Q3; §3 T9
- Problem: The first yielded chunk is not the prefill/decode boundary. In `generate_step`, the first one-token decode `_step(y)` is issued before the first yield. Synchronizing there includes that decode work in `prefill_peak`, then resetting excludes it from `decode_peak`.
- Failure scenario: A first-decode allocation regression is charged to prefill and omitted from decode peak, while all positivity and completion checks pass.
- Fix: Read/reset memory inside `generate_step` after the prompt `_step` is synchronized and before the first decode `_step`; test that first-decode allocation belongs to the decode phase.

VERDICT: DISAGREE Q1 Q2 Q4 Q7 Q10 Q11

---

**Lead disposition:** all six applied in plan v4 §2.3 (the v3 shrink exception withdrawn) — operator decision P416.
