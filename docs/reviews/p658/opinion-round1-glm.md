I've completed the review. Here are my findings.

---

## Findings

### F1 — major — the K3 rule is never validated against the real served drafter cache; both test suites mock it

**Location:** `mlx_vlm/tests/test_p658_impl_engagement.py` (`_Drafter`, lines ~579-595), `review-material/test_p658_worker_drafter_manifest.py` (`_Drafter`, lines ~79-89), `dev/p369_phase2/worker.py:1577-1581`, `mlx_vlm/speculative/mtp.py:678`.

**Evidence:** confirmed by tracing the source.

**Problem:** The request's protection is that `--engagement-only` observes the *served* MTP-ON drafter cache and proves it equals its own unquantized template (K3: never quantized, no continuous-batching leaves). Neither the implementer's tests nor the independently-written acceptance tests exercise the real `qwen3_5_mtp` drafter on the real `cached_session` served path:

- `test_p658_impl_engagement.py::_Drafter.make_cache` returns `[KVCache(), KVCache()]` (2 leaves) and the harness sets `_cache` to a test-chosen list; `test_p658_worker_drafter_manifest.py::_Drafter.make_cache` returns `[KVCache(), KVCache()]` and the harness sets `_cache` to `[PreallocKVCache(), PreallocKVCache()]`. Neither matches the real `qwen3_5_mtp` shape — `self.layers` has `mtp_num_hidden_layers` (1 for Qwen3.8, not 2) and the served `_cache` is plain `KVCache` (not `PreallocKVCache`), and neither fake is ever batched.

So the tests assert K3 holds only against shapes the tests themselves invented. The real shape is established only by my trace: the `cached_session` B==1 path goes through `_mtp_rounds` (`mlx_vlm/speculative/mtp.py:678`), which calls `draft_model.reset(model)` with **no** `left_padding`, so `qwen3_5_mtp.make_cache(None)` returns `[KVCache() for _ in self.layers]` — unbatched, kind `native`, `batch=False` — and `drafter.make_cache()` in the worker returns the same. K3 holds today for both picks, so the mode does **not** refuse a correct arm and does **not** false-pass.

But that conclusion lives in this review, not in the suite. The batched path (`run_speculative_server_rounds` → `_mtp_rounds_batch`, `mtp.py:1102`) calls `draft_model.reset(model, left_padding=left_padding)` for `qwen3_5_mtp` (`supports_ragged_batch_acceptance = True`), which builds `[BatchKVCache(left_padding)]` — `batch=True` — and `drafter_problems` would then emit *"drafter cache holds continuous-batching leaves"* on every engagement run. Nothing in the suite would catch that regression: the fakes are never batched, so the suite stays green while real engagement runs fail.

**Failure scenario:** a future change routes the B==1 cached-session request through theContinuing F1's failure scenario and proposed change:

**Failure scenario:** a future change routes the B==1 cached-session request through the batched path (or a drafter's `supports_ragged_batch_acceptance` flips, or `make_cache(None)` starts returning a `Batch*` class). The real engagement run then fails every arm with *"drafter cache holds continuous-batching leaves"*, defeating the request's purpose — while both the implementer's `test_p658_impl_engagement.py` and the acceptance `test_p658_worker_drafter_manifest.py` stay green, because their fakes never produce a batched leaf.

**Proposed change:** add one CPU-only test that drives the real `worker.qualify_request` against a real `qwen3_5_mtp.Qwen3_5MTPDraftModel` (built from a tiny `Qwen3_5MTPConfig` / text config, as `test_speculative.py` does) with `drafter_manifest=True`, asserting `drafter_problems(observed, template) == []` and that no observed leaf has `batch=True`. This pins the K3-against-real-drafter protection the request asks for. Without it, acceptance criterion 7 ("the fork suite passes … 0 failed") does not establish that the served MTP-ON drafter cache is what the arm claims.

---

### F2 — minor — `drafter_manifest_problems` adds a "malformed leaf record" sub-case beyond the spec

**Location:** `dev/p369_phase2/qualify.py:1119` (`drafter_manifest_problems`).

**Evidence:** confirmed in the source.

**Problem:** Spec Interface 5 names exactly one problem string, `"no drafter cache manifest"`, for the cases "absent, or its `observed` or `template` is empty or not a list". The candidate additionally returns `"no drafter cache manifest (malformed leaf record)"` when a leaf record lacks `"path"` or `"kind"`. This is a scope addition beyond the spec. It is defensive (it prevents a `KeyError` in `kvmanifest.drafter_problems`, which indexes `t["path"]`/`t["kind"]`), and the acceptance test `test_an_empty_absent_or_malformed_drafter_manifest_fails_without_raising` uses a substring check (`NO_DRAFTER_MANIFEST in state["problems"]`) so it passes. No material consequence today.

**Failure scenario:** a consumer matching on the exact problem string `"no drafter cache manifest"` would miss the malformed-leaf variant. No such consumer exists in the tree.

**Proposed change:** either drop the suffix and return the bare `NO_DRAFTER_MANIFEST` for malformed leaves (converging to the spec), or record the spec's intent that malformed-leaf is a distinct case and update the acceptance test to assert the exact string. The former is simpler and matches the spec verbatim.

---

## Summary

No blocker and no major defect in the candidate code itself. I traced the supported conditions (both P475 picks, all five MTP-ON arms, `cached_session` B==1, the stack worktree layout) and confirmed:

- **False PASS:** not found. The target cache is checked by `manifest_problems` against `expected_manifest(template, expected_kv(expected))` (the arm's claimed KV), the served argv is two-way bound by `command_problems` + `binding_problems`, and the loaded drafter is verified by `check_loaded_drafter`. The drafter check (K3) only sanity-checks the drafter's own cache is unquantized — which is all the arm claims about it.
- **False refusal:** not found. The `cached_session` B==1 path uses `_mtp_rounds` (`mtp.py:678`), which calls `draft_model.reset(model)` with no `left_padding`, so the qwen3_5_mtp drafter cache is unbatched `KVCache` and K3 holds.
- **Drafter read timing:** correct — `worker.py:1577` reads `drafter._cache` after `post()` returns (response complete) and before `release_session`.
- **Without the flag:** unchanged. `engagement_only=False` defaults leave `kv_arm_gate`, `entry_problems`, `drive`, and `_drive_locked` byte-identical in behavior; the `**(dict(engagement_only=True) if engagement else {})` plumbing passes no kwarg when off.
- **Production diff:** empty — the patch touches only `dev/p369_phase2/` and `mlx_vlm/tests/`.

The two findings above are a test-coverage gap (F1, major as a gap because the request's central protection is unpinned by the suite) and a minor scope addition (F2).
