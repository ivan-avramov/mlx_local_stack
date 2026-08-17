"""Vendored BFCL handler: RAW OpenAI messages+tools -> mlx-serve's /v1/chat/completions,
letting the SERVER apply the served model's own chat template. Native function-calling
(FC) mode only — never bfcl's prompt-mode text.

================================================================================
THE PROBLEM THIS FIXES
================================================================================
None of our registry model names (e.g. "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
"Ornith-1.0-35B-mlx-uniform-4bit") exist in bfcl_eval's MODEL_CONFIG_MAPPING, so a
stock `bfcl generate --model <ours>` hard-raises ValueError("Unknown model_name").
The earlier workaround (benchmark/bfcl_shim/) registers our names but borrows a STOCK
per-arch handler (GemmaHandler / QwenFCHandler) — those handlers build the prompt
string THEMSELVES (`_format_prompt`, a hardcoded template for google/gemma-3-27b-it or
Qwen/Qwen3-32B-FC) and POST it to the legacy text `/v1/completions` endpoint. That is a
template confound: bfcl's idea of "the Qwen3 template" is not necessarily what the
served Qwen3.6-27B-Opus-Distill-OptiQ-4bit checkpoint's own tokenizer_config.json chat
template actually is.

This module takes the opposite approach: subclass bfcl_eval's
`OpenAICompletionsHandler` (api_inference, NOT local_inference/OSSHandler), whose
`_query_FC` already does exactly the right thing — it POSTs the untouched `messages`
list and OpenAI-schema `tools` straight to `client.chat.completions.create(...)`. Our
router's `ChatRequest` schema (src/mlx-vlm/mlx_vlm/server/schemas.py:847) applies the
served model's OWN chat template server-side from those raw messages — there is no
bfcl-owned template anywhere in this path. `model_name` IS our mlx-serve registry name,
sent as the `model` field so the router's multi-model dispatch routes correctly.

================================================================================
THE 4096-TOKEN CAP (AGENTS.md's warning) — WHERE IT LIVES AND WHY WE DON'T INHERIT IT
================================================================================
bfcl_eval/model_handler/local_inference/base_oss_handler.py `OSSHandler._query_prompting`
(~line 328) hardcodes `leftover_tokens_count = min(4096, mcl - input_token_count - 2)`.
That cap belongs ONLY to `OSSHandler` (the local_inference branch that spins up/talks to
a vLLM-style raw-text completions server) — bfcl_shim/local_handlers.py hits it because
GemmaHandler/QwenFCHandler are OSSHandler subclasses, and works around it by overriding
`_query_prompting` to raise the cap via env var. `OpenAICompletionsHandler` (api_inference)
is a SIBLING branch off `BaseHandler` directly — it does not import, subclass, or call
anything in `base_oss_handler.py`, and its own `_query_FC` sets no `max_tokens` at all
(see openai_completion.py:79-94). So the 4096 cap is structurally unreachable from this
module; we set `max_tokens` explicitly instead (`_max_tokens`, below) from the model's
deployed `generation_defaults.max_tokens` — generous headroom for thinking AND the
answer, never a harness-imposed ceiling.

================================================================================
SAMPLING — WHY WE OVERRIDE self.temperature AND CARRY extra_body
================================================================================
bfcl's own CLI/generation driver (`_llm_response_generation.py:build_handler`) does
`config.model_handler(model_name=..., temperature=args.temperature, ...)` where
`args.temperature` defaults to 0.001 (typer default) and is NEVER per-model — so without
intervention every BFCL run would measure a near-greedy, non-deployed sampling
regardless of `--temperature`. This is the same class of defect
bfcl_shim/local_handlers.py's `_ThinkingStripMixin._query_prompting` fixed for the
prompt-mode path (campaign note: only 3/400 traces carried `<think>` because the old
shim sent bare model/temperature/prompt/max_tokens and nothing else). We fix it the same
way here: pull the FULL `deployed` profile (bench.model_params.params_for(registry_name,
"deployed") — the FU-2 source of truth mlx-serve actually forwards, main_models.yaml
`generation_defaults`) once at construction, override `self.temperature`, and carry
top_p/top_k/min_p/presence_penalty/thinking_budget via `extra_body` on every request
(these are not part of the OpenAI SDK's typed `chat.completions.create()` signature, so
`extra_body` — which our router's `ChatRequest` schema accepts via `extra="allow"`
(schemas.py:31) — is the transport). THINKING STAYS ON, ALWAYS (AGENTS.md "Measurement
discipline": never disable thinking to make a benchmark work) — `enable_thinking: True`
is sent explicitly and unconditionally, not merely inherited from the registry default.
`presence_penalty` defaults to 0.0 when the registry doesn't say otherwise: a nonzero
value disables suffix decoding on this stack, i.e. it would silently measure a different
serving path than what we ship.

================================================================================
LAZY IMPORT CONTRACT
================================================================================
`import bfcl_eval` has an import-time SIDE EFFECT: `bfcl_eval.constants.eval_config`
creates `result/`, `score/`, `.file_locks/` directories at `BFCL_PROJECT_ROOT` (env var;
default = the site-packages directory bfcl_eval itself is installed in — verified: this
already happened once in this repo's `.venv-bench/lib/python3.12/site-packages/`, predating
this module) THE MOMENT it is first imported anywhere in the process, and those path
constants are frozen at that first import — setting the env var later has no effect. So
nothing in this module imports bfcl_eval (or `openai`, or `overrides`) at module scope;
every such import is deferred into a function. `bfcl_eval_available()` lets a caller
check first and degrade gracefully (AGENTS.md: "bench tooling must lazy-import heavy
deps, graceful-degrade ... never crash the batch"). A caller that wants to control WHERE
those directories land (e.g. run_bfcl_fc.py) must set `BFCL_PROJECT_ROOT` before calling
anything in this module that touches bfcl_eval.
"""
import os
import sys

# Generous fallbacks used ONLY when the registry can't answer (see _load_deployed_sampling)
# — never as a tuning knob. Matches bfcl_shim/local_handlers.py's MLX_BFCL_MAX_TOKENS
# default and AGENTS.md's "generous fixed headroom" guidance for thinking budgets.
_FALLBACK_MAX_TOKENS = 16384
_FALLBACK_THINKING_BUDGET = 16384

_HANDLER_CLASS_CACHE = None


def bfcl_eval_available() -> bool:
    """True if bfcl_eval can be imported. Does not itself set BFCL_PROJECT_ROOT — callers
    that care where its side-effect directories land must set the env var first."""
    try:
        import bfcl_eval  # noqa: F401
        return True
    except ImportError:
        return False


def _load_deployed_sampling(registry_name: str) -> dict:
    """The model's full `deployed` sampling profile (main_models.yaml
    `generation_defaults`). Falls back to the two invariants that must hold for every
    candidate we serve (never silently to a family table — see bench/model_params.py's
    own docstring on why 'deployed' fails loud) when the registry can't answer, e.g. the
    name passed isn't a registry entry. The fallback is announced on stderr, not silent."""
    try:
        from . import model_params
        return dict(model_params.params_for(registry_name, "deployed"))
    except Exception as e:  # noqa: BLE001 — registry lookup failure must not crash a run
        print(
            f"[bfcl_handler] WARNING: no deployed generation_defaults for "
            f"{registry_name!r} ({type(e).__name__}: {e}); falling back to minimal "
            f"invariants (presence_penalty=0.0, enable_thinking=True). This model will "
            f"NOT measure its tuned deployed sampling — see AGENTS.md 'deployed' profile.",
            file=sys.stderr,
        )
        return {"presence_penalty": 0.0, "enable_thinking": True}


def _handler_class():
    """Lazily build (and cache) the vendored handler class. Raises ImportError if
    bfcl_eval is not importable — callers should check `bfcl_eval_available()` first if
    they want to degrade instead of raising."""
    global _HANDLER_CLASS_CACHE
    if _HANDLER_CLASS_CACHE is not None:
        return _HANDLER_CLASS_CACHE

    from bfcl_eval.model_handler.api_inference.openai_completion import (
        OpenAICompletionsHandler,
    )

    class MlxServeFCHandler(OpenAICompletionsHandler):
        """Posts RAW messages+tools to our mlx-serve router; see module docstring."""

        def __init__(self, model_name, temperature, registry_name, is_fc_model, **kwargs):
            super().__init__(model_name, temperature, registry_name, is_fc_model, **kwargs)
            self._sampling = _load_deployed_sampling(registry_name)
            # bfcl's CLI temperature (default 0.001) is a harness default, not a serving
            # decision. Override unconditionally so a forgotten/wrong --temperature can
            # never silently under-measure this model at near-greedy.
            self.temperature = self._sampling.get("temperature", temperature)

        def _build_client_kwargs(self):
            """Point at OUR router via OUR OWN env vars (MLX_BFCL_*), never OPENAI_*  —
            so a shell that happens to export a real OPENAI_API_KEY/OPENAI_BASE_URL for
            something else can never make this handler hit the real OpenAI API."""
            host = os.environ.get("MLX_BFCL_HOST", "localhost")
            port = os.environ.get("MLX_BFCL_PORT", "8000")
            base_url = os.environ.get("MLX_BFCL_BASE_URL") or f"http://{host}:{port}/v1"
            api_key = os.environ.get("MLX_BFCL_API_KEY", "not-needed-mlx-serve")
            return {"base_url": base_url, "api_key": api_key}

        def _max_tokens(self) -> int:
            mt = self._sampling.get("max_tokens")
            return int(mt) if mt else _FALLBACK_MAX_TOKENS

        def _extra_body(self) -> dict:
            # `.get(k) is not None` rather than `k in self._sampling`: a registry entry
            # can carry a key with an explicit null (e.g. an empty yaml field), and that
            # must fall through to the floor below exactly like a missing key would —
            # `dict.setdefault` does not override an existing None value.
            body = {
                k: self._sampling[k]
                for k in ("top_p", "top_k", "min_p", "presence_penalty", "thinking_budget")
                if self._sampling.get(k) is not None
            }
            # Nonzero presence_penalty disables suffix decoding on this stack (AGENTS.md
            # "Known pitfalls") — default to the invariant, not the endpoint's own default.
            body.setdefault("presence_penalty", 0.0)
            # THINKING STAYS ON, ALWAYS. Requested explicitly and unconditionally — do not
            # rely on the registry default alone (campaign history: an earlier path that
            # dropped sampling silently measured only 3/400 traces carrying <think>).
            body["enable_thinking"] = True
            if not body.get("thinking_budget"):
                body["thinking_budget"] = max(
                    _FALLBACK_THINKING_BUDGET, int(self._max_tokens() * 0.8)
                )
            return body

        def _query_FC(self, inference_data: dict):
            message: list = inference_data["message"]
            tools = inference_data["tools"]
            inference_data["inference_input_log"] = {
                "message": repr(message),
                "tools": tools,
            }

            kwargs = {
                "messages": message,        # RAW passthrough — no bfcl-owned prompt template
                "model": self.model_name,   # our mlx-serve registry name (routing key)
                "temperature": self.temperature,
                "max_tokens": self._max_tokens(),
                "store": False,
                "extra_body": self._extra_body(),
            }
            if len(tools) > 0:
                kwargs["tools"] = tools      # RAW OpenAI tool schema — server applies its own template

            return self.generate_with_backoff(**kwargs)

    _HANDLER_CLASS_CACHE = MlxServeFCHandler
    return MlxServeFCHandler


def register_model(name: str, host: str = "localhost", port: int = 8000):
    """Idempotently register `name` (our mlx-serve registry name) into bfcl_eval's
    MODEL_CONFIG_MAPPING with the vendored native-FC handler above. Always FC mode
    (is_fc_model=True) — this module implements native tool-call passthrough only, never
    bfcl's prompt-mode text; a model without native function-calling support in its own
    chat template is out of scope for this handler.

    Sets MLX_BFCL_HOST/MLX_BFCL_PORT so `MlxServeFCHandler._build_client_kwargs` points
    at the right endpoint the next time bfcl builds a handler instance for this model
    (bfcl_eval's `build_handler` calls `config.model_handler(...)` with no way to pass an
    endpoint directly). Call this BEFORE `bfcl_eval._llm_response_generation.main(...)`.

    Already-registered names (by this function or anything else) are left untouched —
    idempotent, matches bfcl_shim/sitecustomize.py's registration convention.
    """
    from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING, ModelConfig

    os.environ["MLX_BFCL_HOST"] = host
    os.environ["MLX_BFCL_PORT"] = str(port)

    if name in MODEL_CONFIG_MAPPING:
        return MODEL_CONFIG_MAPPING[name]

    cfg = ModelConfig(
        model_name=name,
        display_name=f"{name} (mlx-serve local, native FC passthrough)",
        url="local",
        org="local",
        license="mit",
        model_handler=_handler_class(),
        input_price=None,
        output_price=None,
        is_fc_model=True,
        # True is REQUIRED for FC mode: OpenAI tool schemas forbid dots in function names, so
        # bfcl renames `math.factorial` -> `math_factorial` on the wire and this flag tells the
        # eval checker to map the model's call back. False cost the first smoke 3/5 items: the
        # model called `math_factorial` exactly as the schema it received named it, and the
        # checker looked for `math.factorial`.
        underscore_to_dot=True,
    )
    MODEL_CONFIG_MAPPING[name] = cfg
    return cfg
