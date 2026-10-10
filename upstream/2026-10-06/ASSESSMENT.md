# mlx-vlm upstream merge assessment — fork 664c2ead vs upstream v0.7.6 1dcc142d / main fec3f503 (2026-10-06)

## Upstream merge assessment: `../mlx-vlm` (and `../mlx-serve`)

Labels: **[RUN]** verified by running, **[READ]** verified by reading, **[ASSUME]** assumption.

### P1. Divergence numbers
- Merge-base is `967bf90b` (2026-09-27), which is the M49 sync point. [RUN]
- Fork `main` `664c2ead` is **33 commits behind** `upstream/main` `fec3f503` (2026-10-06) and 1037 ahead (938 excluding merges). It matches `origin/main`, so nothing is unpublished. [RUN]
- Upstream releases since then, all already on PyPI-side tags:
  - v0.7.4 `00093678`, 2026-09-28
  - v0.7.5 `75ff19f3`, 2026-10-05
  - v0.7.6 `1dcc142d`, 2026-10-05
  - `upstream/main` is version 0.7.7 but untagged. Only 2 commits sit past v0.7.6: kolibri1 and EmbeddingGemma2. [RUN]
- Size of each side's delta against the base:
  - Fork: 178 files, +80,041/−6,762. Excluding tests and docs: 73 files, +18,371/−1,125.
  - Upstream: 189 files, +14,422/−1,199. Most of this is new models (deepseek_v41, internvl, laya, decider2, kolibri1, embedding_gemma2) plus a −553-line `rotate_half` dedupe. [RUN]
- **Upstream touched none of the core serving paths in this window:** `generate/*`, `models/cache.py`, `turboquant.py`, `epicache`, `models/qwen3_5/{language,qwen3_5}.py`, `speculative/*`, `server/generation.py`, `server/session_manager.py`, `server/anthropic.py`, tool parsers. [RUN]

### P2. Trial merge result (`upstream/main` into `main`, throwaway worktree)
- 6 files conflict. Every other file merged cleanly and passes `py_compile`. [RUN]

| File | Conflict | Difficulty | Fork feature at stake |
|---|---|---|---|
| `server/openai.py`, hunks 1–5 (imports) | Text only. Take the union of both import lists; keep the fork's `OrderedDict`, `THINKING_FORMATS`, `sanitize_strict_json` and `Completion*` schemas; add `aclosing`, `compaction`, `CompactRequest` and the request-normalization imports. | S | none |
| `server/openai.py`, hunks 6–7 (end of Responses-API streaming) | Semantic. The fork's reasoning_text.done / output_item.done event sequence collides with upstream's `stream_delta` plus compaction-progress rewrite. | M/L | Fork Responses streaming. The router does not expose `/v1/responses` (C91 doc), so the stack is unaffected, but fork tests cover this path. |
| `server/openai.py`, hunk 8 (chat completions) | The fork side is empty; upstream adds **automatic compaction**. Textually trivial, **high semantic risk** (P4). | S to merge, design call to gate | Soft clamp, `THINKING_BUDGET_CLAMP_RATIO`, session cache |
| `server/openai.py`, hunk 9 (chat message normalization) | Semantic. Upstream moved the loop into `request_normalization._chat_message_to_prompt`. The fork's loop also calls `_strip_assistant_thinking` on assistant turns. **Taking upstream's side silently drops the strip, which changes prompts and session-cache prefixes.** Fix: move the strip into `_chat_message_to_prompt`, which also makes compaction's token counting match. | M | Prompt identity, session reuse (M48) |
| `server/request_normalization.py` | Imports only (`logging` vs `json`, `List`). | S | none |
| `models/qwen3_5_moe/language.py`, `models/nemotron_h/language.py` | The fork's `moe_expand` routing collides with upstream's `mx.stop_gradient(inds)`. Fix: add `stop_gradient` in the fork's else-branch. | S | `moe_expand`. Not on the served path: both picks are dense `qwen3_5` (24 heads, 4 KV heads, no experts) [READ] |
| `tests/test_generate.py` | Two appends at the same spot; keep both. | S | tests |
| `tests/test_server.py` (5 hunks) | 2 import blocks plus 3 large upstream blocks (about 1.1K, 3.1K and 0.6K lines) landing in regions the fork restructured under C104. Needs C104-policy reconciliation and dedupe against the fork's relocated copies. | M (volume) | tests |

- **Cleanly merged but still needs action:**
  - `server/compaction.py` is new and does `from cryptography.fernet import ...` at module import. **`cryptography` is not in the stack's `.venv` or `uv.lock`**, so the worker's `mlx_vlm.server` import would fail until the stack lock is updated. [READ/RUN]
  - `requirements.txt` adds `cryptography>=43` and `mlx>=0.32.3`.
  - Also merged cleanly: `schemas.py` (`context_management` field), `responses_state.py`, `apc.py`, `app.py`/`cli.py` (decision routes; `model_kind` refactor), `qwen3_5/speculative_verifier.py` (`stop_gradient`, MoE branch only).

### P3. Changes that affect outputs vs. neutral ones
- **Output-affecting for the stack, only if left ungated:**
  - `6ecadd76` and `86d07d14` (both in v0.7.5/v0.7.6): server-side compaction.
  - The hunk-9 strip regression, if resolved the wrong way.
- **Output-neutral for the stack:**
  - `66e68ce3` `stop_gradient` is a forward no-op, MoE only. [READ]
  - `2c54d499` typical-p fp32: deployed sampling never sets typical_p. [READ]
  - `5a97f54f` and `d73f4b1a`: diffusion and TTS models.
  - `apc.py` changes: APC is off.
  - `7c25bbb3` and `4fcbdf32`: Qwen3-VL video timestamps. `qwen3_5` uses this processor, but only the video path changes.
  - `prompt_utils.py`: audio ordering, internvl/deepseek_v41 entries, qwen3_omni thinking default.
  - `utils.py` (`c0039a0a`): `"vision"`/`"aligner"` skip-list. Only conversion is affected; at load time quantized checkpoints are still decided by the presence of `.scales`. [READ]
  - `31215370` `rotate_half` dedupe: upstream's copy is identical to the deleted one. [READ]
  - Responses-API replay fixes: route not exposed.
  - Decision CLI/API, new models.
- **Upstream reimplementing fork features:** nothing new for prompt/session caching, MTP, KV quantization, fused attention or lazy embeddings in this window. The one new overlap is **context-overflow handling**:
  - Upstream: server-side summarization.
  - Fork: soft clamp plus a 0.8 thinking-budget clamp, with opencode handling compaction on the client.
  - Recommendation: **reconcile.** Keep the fork's clamp and make automatic compaction opt-in, firing only when `context_management` is a non-empty list. The explicit compact endpoint and capsules can stay.

### P4. The main finding: automatic compaction would change 256K behaviour
- The gate is `if request.context_management != []`. The default is `None`, so this block **runs on every chat request**:
  1. It renders and tokenizes the whole prompt an extra time, including image preprocessing via `_cpu_preprocess`.
  2. If `prompt > limit − max_tokens`, it replaces old history with a temperature-0, thinking-OFF summary of 1024 tokens or fewer.
- With the deployed values (`max_kv_cache_size` 262144, `max_position_embeddings` 262144, `max_tokens` 102400), that threshold is **159,744 prompt tokens**. Today the fork serves 160K–260K prompts by clamping `max_tokens`. After an ungated merge it would silently summarize them and break session-prefix reuse. [READ; that args resolve to 102400 is ASSUME]
- If compaction were ever enabled, it writes a key file to `~/.cache/mlx-vlm`, which is outside the allowed artifact locations. `MLX_VLM_COMPACTION_KEY_FILE` would need to point under `$STACK_WORKDIR`. [READ]

### P5. MLX core version
- Today the fork and stack run MLX/mlx-metal **0.32.2** (`uv.lock`, both venvs) and mlx-lm 0.31.3. [RUN]
- v0.7.6 still requires `mlx>=0.32.2`. **Only `fec3f503` (EmbeddingGemma2, untagged) raises the floor to 0.32.3** (released 2026-09-29). [RUN]
- What 0.32.3 changes, from the release notes I read (truncated) [READ]:
  - The GQA-12/16 SDPA kernel change does not apply to our GQA of 6.
  - The `gather_qmm` NAX fix is MoE only.
  - Also: NaN propagation in arg-reductions, a `clear_streams` deadlock fix, and adaptive load concurrency.
- **Merge v0.7.6, not `upstream/main`.** That keeps MLX bumps a separate, deliberate change. Any MLX bump starts a new epoch unless paired outputs are byte-identical.

### P6. Benefits for the stack
- Effectively **none on the served path.** Nothing touches Qwen3.x dense text/vision serving, the sampler chain, KV or MTP.
- Noise from this stack's point of view: new models, decision API, compaction, APC fixes, video timestamps, Responses replay fixes. [READ]

### P7. `../mlx-serve`
- It has **no `upstream` remote**. Its GitHub parent is `raspoli/mlx-serve`, which I fetched by URL; that updated only FETCH_HEAD.
- Merge-base `a6f80eb`; 4 commits behind (v0.2.0, 2026-09-22), 23 ahead. [RUN]
- Upstream adds a decision model type, plus a Metal flush in the **inline** manager unload (`f18dfd3`). The stack's models are all `type: vision`, which routes to `process_manager`, so the flush never runs for us. [READ]
- Overlapping files: `config.py`, `router.py`, `docs/configuration.md`. No benefit; **skip.**

### P8. Fork test suite and audits
- **Test suite on fork `main`** [RUN]:
  - Command: `../mlx-vlm/.venv/bin/python -m pytest -p no:cacheprovider -q mlx_vlm/tests` (pytest 9.1.1 and pytest-subtests are already installed).
  - Result: **5477 passed, 6 skipped, 1 xfailed, 44 subtests, in 61 s.** Toy-sized MLX only, no model loaded, nothing contacted :8000; the daily driver stayed resident and idle throughout.
  - One informational warning: the golden fixture for `test_mtp_verify_scan` differs from the stack registry.
  - I did not run the suite on the trial merge.
- **Audits** [RUN]: the 8 audit scripts in `dev/check_*.py` (also wired into `.github/workflows/upstream-parity.yml`) **already fail 6 of 8 against the merge-base itself**, so the M49 audit baseline is not green.
  - Most findings are C104 test restorations that were never recorded in the `.*-exclusions` files.
  - There are also 4 unmarked non-test hunks:
    - `generate/dispatch.py` lines 1535–1539
    - `models/qwen3_5/qwen3_5.py` lines 83–244 (M57/M58 code)
    - `server/cli.py` line 30
    - `server/openai.py` line 8
  - Until that baseline is fixed, the audits cannot serve as a post-merge pass/fail gate.

### P9. Recommendation: merge later, after M60; no cherry-picks
- Reasoning:
  - Upstream brings nothing to the served path, and the main item, compaction, is a risk that has to be neutralized.
  - Merging first would delay M60 by about 1.5–2 sessions for no quality gain.
  - If the post-M60 merge proves byte-identical, M60's certification carries over unchanged.
  - The delta is small now (33 commits, 6 conflicted files). Upstream's churn in `openai.py` grows it, but the effort stays bounded.
- Exception: if M60 or upcoming work edits `server/openai.py` or `request_normalization.py`, merge first to avoid conflicting with ourselves.
- **Useful now, with no runtime change:** fix the audit baseline (the 4 markers plus the C104 exclusions).

### P10. Merge plan (mirrors M49)
1. Branch `sync/upstream-v0.7.6` in an `$STACK_WORKDIR/upstream/<date>/mlx-vlm` worktree. Merge the **v0.7.6 tag `1dcc142d`**.
2. Resolve the P2 conflicts:
   - Hunk 9: move `_strip_assistant_thinking` into `_chat_message_to_prompt`.
   - Hunk 8: gate automatic compaction to opt-in. Write the failing test first: no `context_management` plus a prompt above `limit − max_tokens` must be neither compacted nor re-rendered, and the clamp path must stay unchanged.
   - Make the `cryptography` import lazy, or add it to the stack lock.
3. Reconcile tests per C104, then run the full suite. Compare failing test IDs with the 5477/6/1 baseline.
4. Run the 8 audits against both `967bf90b` and `1dcc142d`, and diff against the pre-merge finding list. Add the `# Fork:` markers.
5. CPU gate G0: render recorded opencode/OWUI chat requests (tool calls, reasoning_content, images) through the old and new prompt path. Token IDs must be identical.
6. Cold review against this checklist.
7. GPU gates for an **"outputs unchanged"** claim:
   - G1: `benchmark/bench/stack_smoke.py`, six cases, on both picks, paired same-seed against a `664c2ead` runtime. Required: byte-identical content, reasoning and tool calls; identical prompt and cached token counts; positive MTP counters. Also verify the worker cmdline, APC absent, and session max.
   - G2: one prompt of about 200K tokens on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. Required: no compaction (`prompt_tokens` equals the uncompacted count), clamp behaviour as before, peak memory unchanged. Prefill alone is roughly 15–20 min.
   - Any byte difference, or any MLX bump, means a **new epoch**: attribute it with an old-source control as in M43, then propose remeasurement.
8. Fresh `runserver.sh`, publish the fork, bump the submodule, update the docs. Push only with your explicit approval.

**Effort:** about 1 session for merge, tests, audits and cold review, plus about half a session of GPU time (roughly 1.5 h of box time) for G1/G2.

### P11. What could go wrong
- Ungated compaction summarizing every prompt above about 160K tokens.
- The worker crashing at import because `cryptography` is missing.
- An MLX bump slipping in through `upstream/main` on the next `uv lock`.
- Losing the assistant-thinking strip, which changes multi-turn prompts and cache reuse.
- Missing or duplicated tests from the `test_server.py` reconciliation.
- A false sense of safety from audits that were already red.
- The per-request double tokenization adding TTFT at long context, if left ungated. Its size is unmeasured [ASSUME].

### P12. Cleanup state [RUN]
- I created and removed the trial worktree with `merge --abort` and `worktree remove --force`, and deleted the empty `upstream-trial` directory.
- `git worktree list` in `../mlx-vlm` shows only `main` (`664c2ead`) plus two worktrees that already existed before this task: `f1-sync` [`sync/upstream-v0.6.15`] and `upstream/2026-09-13/mlx-vlm` [`sync/upstream-2026-09-13`]. They look stale; pruning them is your call.
- `git status` is clean on `main`; no stash, no new branch.
- Stack submodules are untouched: `src/mlx-vlm` 664c2ead, `src/mlx-serve` 3f2c87c.
- The only ref changes are new `upstream/*` remote-tracking refs and tags v0.7.4–v0.7.6 in `../mlx-vlm`, and FETCH_HEAD in `../mlx-serve`.
