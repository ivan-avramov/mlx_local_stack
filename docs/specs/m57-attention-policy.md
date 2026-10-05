# M57 — versioned fused-attention dispatch policy for native-KV full attention (build spec, 2026-10-04)

Approved C111. Evidence and reasoning: `docs/proposal-flash-attention.md` (E1–E14, P45–P75). First pick only:
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, native16 KV, MTP ON. Phase 2 serving optimization; not B/C evidence.
Registry of record does not change until the operator approves adoption.

## Policy `fused_v1` (the only non-default value; `auto` = today's behaviour)

Applies to the NATIVE branch of `mlx_vlm/models/base.py::scaled_dot_product_attention` only. Pass `force_fused=True` iff ALL hold:

1. the cache is native (not a TurboQuant cache, no `bits` attribute) and `sinks is None`;
2. query dtype is not float32;
3. query length `qL > 8`;
4. `qL >= 128` OR `num_query_heads * qL * key_length * itemsize >= 2**28` (the score tensor an unfused call would build).

Otherwise call MLX exactly as today (no `force_fused` keyword at all). Constants 8, 128 and 2**28 belong to the policy version;
changing one is a new version name. Rationale is in the proposal doc (E1, E2, E4, E10); do not restate it in code beyond one line.

## Fork (`../mlx-vlm`, branch `m57-attention-policy` from `m57-prefill-profile` @ `21d62fe6` — one lineage, one later merge and submodule bump)

- CLI `--attention-policy {auto,fused_v1}` (default `auto`) → env handoff like the other worker arguments → resolved ONCE at model
  load into a policy object stored on the model instance and on each qualified attention module (plain attribute, not a
  parameter). `scaled_dot_product_attention` gains a keyword `policy=None`; `None` and `auto` are identical to today. The
  attention function never reads the environment.
- Qualified call site: `Qwen3_5Attention.__call__` only. EXPLICITLY EXCLUDED (pass nothing): the verifier's attention in
  `mlx_vlm/models/qwen3_5/speculative_verifier.py` (its query lengths are ≤ the MTP block size and already use MLX's fused vector
  kernel), the left-padded / ragged batch path, vision towers, GatedDeltaNet layers and every other model family.
- A non-`auto` policy on a model family without qualified call sites, or on a model with attention sinks: refuse at load, exit
  nonzero before READY, one clear stderr line.
- Startup self-test when the policy is not `auto`, synthetic arrays at the model's real query/KV head counts, head dim and dtype,
  4096 keys, bounded under 30 s: `qL ∈ {9, 127, 128, 512}` × mask ∈ {`"causal"`, `None`, boolean array}. Any raise from a call the
  policy would force: exit nonzero before READY. Also assert the policy does NOT force `qL ∈ {1..8}`.
- Per-request counters in the timings the server already returns: `sdpa_forced`, `sdpa_auto` (native-branch calls by decision).
- Pool limit: `_derive_cache_limit_gb` takes the policy. Under `fused_v1` the score term is the policy's largest unfused score
  tensor (bounded by rule 4: `2**28` bytes) instead of `heads × prefill_step × max_kv × 2`. `auto` unchanged.
- Lazy prompt embeddings, separate commit: for prompts with no merged non-text features, embed each prefill chunk from its token
  ids instead of materialising the whole prompt's embeddings up front. Multimodal prompts unchanged. Outputs identical.
- `# Fork (M57)` markers on every hunk in upstream-owned files; minimal hunks; no refactors.

## Router (`../mlx-serve`, branch `m57-attention-policy`)

- `ModelConfig.attention_policy: str = ""`; read in `_load`; validate in `__post_init__`: value in {``, `auto`, `fused_v1`};
  `fused_v1` requires `type == "vision"` and `kv_bits == 0`; otherwise `ValueError` naming the model.
- `_build_command` appends `--attention-policy <value>` only for a non-empty, non-`auto` value.

## Stack (this repo)

- Fingerprint v7: `attention_policy` joins the runtime slice. Observed from the live worker's command line when a worker for the
  model is up (flag absent → `auto`, source `worker`); otherwise the registry value (source `registry`). Manifests older than v7
  compare as `auto` with source `default-pre-v7`. Registry/worker disagreement refuses the run (same shape as the C35 tripwire).
- `compare.py` refuses across differing `attention_policy`. `compare_predictor.py`'s must-differ rule is parametrised to accept
  exactly one named key (`draft_kind` or `attention_policy`); no other must-match rule is relaxed.
- Overlays for qualification live under `$STACK_WORKDIR/m57/overlays/`.

## Acceptance criteria (each needs a named test; write it first, watch it fail)

- AC1 Default preservation: registry without the field → worker command line byte-identical to before; with policy `None`/`auto`
  the native branch calls MLX with exactly today's keywords (mock asserts no `force_fused` key) for every query length.
- AC2 Decision table: for a fake native cache, the policy forces exactly the set defined by rules 1–4 over `qL ∈ {1..9, 64, 127,
  128, 511, 512, 1024}` × key lengths {1024, 16384, 131072, 262144} × dtype {bf16, fp16, fp32} × sinks {none, present}.
- AC3 Propagation: registry value → `ModelConfig` → command line → loaded instance attribute → the qualified call site → the
  keyword on the MLX call; counters increment accordingly.
- AC4 Quantized dispatch unchanged: with `fused_v1` on the instance and a TurboQuant or bit-quantized cache, each quantized branch
  receives the same arguments as on `main`; existing quantized/TurboQuant tests pass unmodified.
- AC5 Scope: left-padded / ragged path, vision tower helpers and a foreign model family never see the policy.
- AC6 Loud failure: unknown value (router `ValueError`; worker argparse error); `fused_v1` with `kv_bits > 0` (router
  `ValueError`); unqualified family or sinks (worker exits nonzero before READY); self-test raise (worker exits nonzero).
- AC7 Isolation: two model instances in one process with different policies dispatch per instance; changing the environment
  after load has no effect.
- AC8 Verifier: with `fused_v1` on the instance, verifier attention calls never receive the policy or `force_fused` (block sizes
  2 and 3), and verifier outputs are bit-identical to `main` on CPU.
- AC9 Pool limit: derived value under `auto` equals today's for the first pick's shape (9); under `fused_v1` it is the policy bound
  + margin; an explicit `cache_limit_gb` still overrides.
- AC10 Lazy embeddings: text-only prompt → cache state and first-token logits bit-identical to `main` on CPU, and the
  whole-prompt embedding array is never materialised (execution sentinel); multimodal prompt → unchanged path.
- AC11 Provenance: v7 manifest carries `attention_policy` + source; worker/registry mismatch refuses; `compare.py` refuses across
  policy; the parametrised A/B tool accepts exactly one differing key; pre-v7 manifests read as `auto` / `default-pre-v7`.
- AC12 GPU parity gate (operator session, not CI): fused vs unfused vs an fp32 CPU reference at the real dtype for
  `qL ∈ {9, 127, 128, 512}`, keys {4096, 131072, 262144}; fused relative RMS error ≤ the unfused error at every cell; no NaN.

## Rules for implementers

- No real model loads, no Metal workloads, no servers. CPU tests only. Do not push. Do not bump submodules. Do not edit
  `main_models.yaml`.
- One branch per repo, small commits, conventional messages. Report: commits, `git diff --stat`, exact test commands and results,
  each AC → test name, anything not verified.

## Qualification (operator session, after cold reviews and the live gate; design to be frozen before the first arm)

- Arms on fresh lean routers, shipped state otherwise, k=2 sessions each, order-balanced, ≥ 10 min idle cooldown between arms
  with the start state recorded (AGENTS.md warm-state rule): A `auto`@512; B `fused_v1`@512 with the
  pool limit pinned at 9; latency-only screens: C `fused_v1`@512 with the derived pool limit, D `fused_v1`@1024.
- Latency ladder 8K / 32K / 64K / 128K / 256K cold + cached continuations of 100, 600 and 5000 new tokens at 64K and 128K
  (the opencode turn-size bands); TTFT, decode, `mx.get_peak_memory`, counters. The 256K rung is capacity + retrieval only.
- Quality: humanevalplus/mbppplus n=100 paired `acc_strict@81920`; long-context retrieval and chain-reasoning subsets at 64K–128K
  sized from the pilot's discordance; AgentBench 5-item smoke. Seeded 5-item pilot twice per loaded instance first.
- Predictions on record (E15, matched machine state): 128K TTFT −16 % warm / −22 % cool, 256K ≈ −30 %; peak −3.9 GB at 128K, −7.9 GB at 256K (+ ≈ 2.7 GB from lazy embeddings);
  decode unchanged; 8K / 32K TTFT within ±3 %.
- Adopt (operator approval, PROVISIONAL) iff quality holds (paired strict delta ≥ −5 pp in both sessions, long-context subsets
  with no paired loss beyond their pre-registered bound) AND no rung is slower by more than 3 % AND at least one of: 256K peak
  lower by ≥ 5 GB; TTFT lower by ≥ 8 % at 128K. A red flag, not a bonus: decode moving by more than 5 %.

## Amendment 1 (2026-10-04, after the first cold reviews of the build — a Claude reviewer and Codex `gpt-6-astra`: router SHIP, fork and stack FIX-THEN-SHIP — and a live smoke)

Binding; where it conflicts with the text above, this wins.

**Policy `fused_v1` — two more conditions (rules 5 and 6), same version name (nothing has shipped):**

5. batch size is 1 and the cache carries no left padding (single-sequence path only; the left-padded / ragged batch prefill —
   including its row-by-row recursion into the same model — must never be forced);
6. with a causal string mask, `qL <= key_length`.

A non-`auto` policy on a worker whose default device is not the GPU: refuse at load (exit nonzero before READY). No skip.

**Fork**

- F1 Counters: `sdpa_forced` / `sdpa_auto` appear in the `timings` object of the HTTP response (non-streaming and streaming
  session-cache path) and on the "Request completed" log line, ONLY when the policy is not `auto` — under `auto` the response bytes
  are unchanged (no `null` keys). Endpoint-level test on the non-streaming cached path.
- F2 Scope: test rules 5 with a real padded batch (B > 1, eligible row lengths) and the row recursion.
- F3 Self-test: take the force decision at `key_length = max_kv` (so 9 and 127 are forced by rule 4) but issue the calls at 4096
  keys; query dtype from the model's actual attention computation, not a stand-in; on GPU, zero forced calls executed is a
  FAILURE; log calls run and elapsed time. A hung self-test is bounded by the router's readiness timeout — state that in the
  docstring instead of a post-hoc check that cannot fire.
- F4 Exit before READY: test the lifespan / readiness path with a failing policy resolution (no uvicorn), not `issubclass`.
- F5 Lazy prompt embeddings are OFF by default and enabled only by the worker flag `--lazy-prompt-embeddings` (env handoff,
  resolved once at load onto the model instance). Without the flag every path is byte-identical to before the commit.
- F6 Lazy-embedding tests against the eager path: RAW logits, prompt-end cache arrays and offsets, a warm session cache with a
  non-zero initial offset, snapshot landing and prompt-end retention boundaries, the MTP capture flow if a tiny model can drive
  it, and a real multimodal merge (must take the eager path).

**Router**

- `ModelConfig.lazy_prompt_embeddings: bool | None = None` (bool or null, vision type only, same validation style as
  `cache_session_shrink`); `_build_command` appends `--lazy-prompt-embeddings` only when it is `True`. Default command unchanged.

**Stack**

- S1 An unresolved policy on a v7 manifest (`unknown`) never pools and never compares: `is_compatible` treats it as incompatible
  with everything except an identical `unknown` on resume of the SAME run, and `compare.py` REFUSES (no warning path).
- S2 Pre-v7 normalisation applies to every older version, including the v1 early return in `is_compatible`; test v1–v6.
- S3 `compare_predictor.py`: both selectable controls (`draft_kind`, `attention_policy`, `lazy_prompt_embeddings`) must be KNOWN
  on both sides in every mode; exactly the named one differs.
- S4 Worker attribution: consider ALL worker processes, match the exact value of the `--model` argument, refuse on ambiguity.
- S5 `lazy_prompt_embeddings` joins the v7 fingerprint with the same rules as `attention_policy` (worker flag presence, else
  registry, pre-v7 = false / `default-pre-v7`, mismatch refusal, compare refusal, selectable must-differ key).

**Qualification** gains arm E: `fused_v1` + `lazy_prompt_embeddings` (latency / peak screen; quality only if adopted).

## Amendment 2 (2026-10-04, after review round 2 — router SHIP; fork and stack FIX-THEN-SHIP; live gate and AC12 parity gate PASSED)

Binding.

**Fork**

- G1 Counters appear in EVERY terminal response shape that carries timings on the session-cache path: the streamed tool-call
  final chunk and its fallback construction, the `/v1/completions` streaming final chunk, and the Responses API if it carries
  timings — through one helper. Test a streamed turn ending in tool calls without a usage chunk.
- G2 Policy suspension during row recursion is local to the executing thread / context, not an instance-wide counter. Tests:
  exception, nesting, two threads.
- G3 AC9 is REVISED: the derived pool limit under `fused_v1` equals the `auto` derivation (the batched path and the row recursion
  still run unfused at full size). A smaller pool is an explicit `cache_limit_gb` choice, qualified as arm C.
- G4 Self-test dtype: read the query dtype where the policy decides (a recording policy on a one-token forward), or keep the probe
  but route ANY probe error through the one-line `attention-policy` failure. Tests that distinguish activation dtype from weight
  dtype; the F4 lifespan test asserts the specific failure, not an or-chain.

**Stack**

- T1 Worker/registry disagreement and ambiguity for `attention_policy` and `lazy_prompt_embeddings` raise the exception class the
  drivers already re-raise (`ServedConfigError` or a subclass): a `generate` run REFUSES before its first request and before any
  manifest stamp. Test at the `generate.run` level. Report (do not change) whether the pre-existing `draft_kind` tripwire's
  `RuntimeError` is swallowed by the same handlers.
- T2 No "same run" exception: an unresolved control is incompatible with everything, including another `unknown`.
- T3 Worker matching keeps argv as a list and parses exact tokens (`--model value` and `--model=value`); a failed observation is
  distinguished from "no worker" (the former refuses, the latter falls back to the registry).
- T4 `bench/client.py` keeps `sdpa_forced` / `sdpa_auto` from response timings in the row's raw timings (as it does the draft
  counters), absent when the server omits them.
