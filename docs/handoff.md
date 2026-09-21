# Handoff — 2026-09-20: C97 closed by e2e gate; C98(a) done; C91 fork fix pushed + bumped; C92 published; stack pushed

Read this first, then `docs/PLAN.md` and `docs/open-questions.md`. Reports this session:
[web-search e2e gate](websearch-e2e-gate-2026-09-20.md) (+ public aggregate
`websearch-e2e-gate-2026-09-20.json`).

## Operator rulings 2026-09-20

Approved P1–P4 as recommended: ratify the SearXNG pool (C97), run an end-to-end
web-search gate, publish the C89 card evidence (C92), repair C91. Declined the
native16-vs-TQ4 paired quality run (P5): the PROVISIONAL labels on the C ladder (C70)
and on native16 KV (C81) are accepted as-is; no GPU study is queued for them.

## Runtime state

Daily-driver stack is UP and is the operator's: router pid 71220 (:8000), task model pid
71221 (:8092), OWUI + SearXNG containers (`mlx_local_stack-open-webui-1`,
`mlx_local_stack-searxng-1`, up since ~2026-09-17), main model
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` loaded by the gate run and subject to the
router's idle unload. Do not restart or reload for benchmark reasons while the operator
is using it. Verify PIDs/ports before any lifecycle action.

## C97 — CLOSED (ratified + measured)

- Gate `scripts/websearch/owui_e2e_gate.py`: **10/10 PASS** (seed 20260920, 2 per
  category, mean 35 s, max 60 s, 10 `search_web`, 3 `fetch_url`, 0 fetch failures, all
  rounds converged, all cited, all expectations hit). Private evidence
  `$STACK_WORKDIR/websearch/e2e-gate-20260920/{smoke,smoke2,run1}`; do not rerun into
  those directories. `smoke` is a recorded substantive FAIL (model answered from weights
  without searching) that motivated the explicit `Search the web and cite your sources: `
  prefix; keep it.
- Corrections recorded in the 09-16 report, PLAN, open-questions and AGENTS.md: the
  shipped C-menu models are `function_calling: native`, so OWUI never runs the forced-RAG
  path — web search is the `search_web`/`fetch_url` builtin-tool path, `rag.top_k`/chunking/
  task-model query generation are not on it.
- **C98 (a) DONE (operator, P7):** seed rows reverted to the live values (`d20e926`). (c) audit still open. Original finding: `openwebui_config.json` rows `rag.top_k 12` and
  `web.loader.concurrent_requests 5` are NOT live (readback 3 and 10) — OWUI 0.11's flat
  per-key config table is not populated by the nested seed file; only `init.py`'s API
  calls take effect. The seed rows are now reverted; the
  CPU-only audit of other seed-only values (C98 c) is the remaining item.

## C91 — fork fix pushed and bumped (operator go, P9)

- Fork `4d4575a7` pushed to GitHub; stack gitlink bumped in `f623b6d` (fetched through the
  submodule's GitHub origin). The RUNNING worker still executes the 522671c4 code it
  imported at start; the fix takes effect at the next router restart. Commit body:
  `_process_cached_request` now sets `StreamingToken.token_count` from the increment of
  dispatch's cumulative `generation_tokens` (mirrors `_DiffusionBlockEmitter`); chunks
  without a count keep 1/chunk. Test `mlx_vlm/tests/test_cached_token_count.py` (7
  cases: max1/length → 1, repeated-count finalization → +0, newly reported EOS → +1,
  zero tokens, decreasing counts clamp, metrics agreement, stand-ins). Seam files 116
  pass; full fork suite 4906 pass / 10 skipped (`--ignore` `test_smoke.py` and
  `test_models.py`).
- Pre-existing unrelated failure: `test_speculative.py::test_general_quantized_verifier_matches_decode[127-nvfp4-4-16]`
  fails identically at pristine 522671c4. Not chased; note it if the fork is bumped.
- Remaining C91 steps (spec `docs/specs/c91-terminal-token-accounting.md`, items 4–5):
  cold review (not yet done); then a bounded
  real-server validation on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` — the saved
  `max_tokens: 1` calibration shape plus normal-stop and bounded-length controls — which
  needs the daily driver DOWN (one resident model) and must be proposed with exact
  requests before arming. Historical C84/C89 counts stay as recorded.

## C92 — PUBLISHED 2026-09-20 (operator go, P8)

- Prepared files re-hashed OK against `docs/huggingface-c89-prepared-2026-09-14.json`;
  result commit 4fb8425 is already on GitHub (origin/main == local before this
  session's commits). Both HF remotes are at the C88 revisions
  (`f2b38a25…` target, `41ee4495…` drafter); the C89 evidence file is NEW in each repo,
  README is an update (+19 lines each).
- Published via `$STACK_WORKDIR/hf-publish/c92-20260920/publish_c92.py --apply`: target
  `1dd70b36b8a800568576ad12fdeef3c7d3c2dc61`, drafter
  `0caad904fdd7706310f42f342226e7ae9b2d55dc`; every other file's signature unchanged,
  anonymous readback verified. Receipt `docs/huggingface-c92-update-2026-09-20.json`. Do not
  rerun the publisher.

## Git

Operator authorized (2026-09-20, in turn): fork push, submodule bump, HF publication,
then stack push — executed in that order. Verify `origin/main == HEAD` on resume.

## Resume discipline

One resident model; APC absent; retained sessions 2; full active preallocation; deployed
sampling and explicit served-overlay environment. Never alter source/config during a
live run; preserve real data and recorded failures. Commit coherent units; push only on
explicit current-turn instruction. C98 (c) remains the only open C98 item. Next decision id C99; discussion ids continue from P5
of this session's numbering (the P-sequence restarted at P1 on 2026-09-20 — earlier
handoffs' P7xx numbering is historical).
