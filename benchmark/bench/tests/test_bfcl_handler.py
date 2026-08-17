"""Tests for the vendored native-FC BFCL handler (bfcl_handler.py).

Covers: (a) raw messages+tools pass through untransformed — no bfcl-owned prompt
template touches them; (b) max_tokens comes from the model's deployed profile, never
the base_oss_handler 4096 cap (structurally unreachable here — see bfcl_handler.py's
module docstring); (c) native tool_calls decode to bfcl's expected [{name: args}] AST
shape; (d) thinking is requested explicitly and never disabled. The server is mocked —
no network call is made; `client.chat.completions.create` is replaced with a fake that
records its kwargs.

bfcl-eval is installed in .venv-bench, but importing it (specifically
`bfcl_eval.constants.eval_config`, reached transitively through `base_handler.py`) has a
real import-time side effect: it creates `result/`/`score/`/`.file_locks/` directories at
`BFCL_PROJECT_ROOT` (default: bfcl_eval's own site-packages install dir — this already
happened once in this repo's `.venv-bench` before this test file existed). `os.environ
.setdefault` below keeps that side effect out of site-packages for this test run,
matching the same requirement documented in run_bfcl_fc.py. Per AGENTS.md's lazy-import
convention, the whole module is skipped (not failed) when bfcl_eval isn't installed.
"""
import os
import tempfile
import types

import pytest

os.environ.setdefault(
    "BFCL_PROJECT_ROOT",
    os.path.join(tempfile.gettempdir(), "mlx_local_stack_bfcl_handler_test_root"),
)

pytest.importorskip("bfcl_eval")

import bench.bfcl_handler as H


# --------------------------------------------------------------------------- fakes
class _FakeCompletions:
    """Stand-in for `client.chat.completions` — no network call, records the request."""

    def __init__(self, tool_calls=None, content=None):
        self.captured = None
        self._tool_calls = tool_calls or []
        self._content = content

    def create(self, **kwargs):
        self.captured = kwargs
        message = types.SimpleNamespace(
            content=self._content,
            tool_calls=[
                types.SimpleNamespace(
                    id=f"call_{i}",
                    function=types.SimpleNamespace(name=name, arguments=args_json),
                )
                for i, (name, args_json) in enumerate(self._tool_calls)
            ] or None,
        )
        usage = types.SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        choice = types.SimpleNamespace(message=message)
        return types.SimpleNamespace(choices=[choice], usage=usage)


def _stub_sampling(monkeypatch, **overrides):
    """Deterministic deployed-profile stand-in — isolates handler tests from whatever
    main_models.yaml currently contains (that file is owned by another workstream)."""
    sampling = {
        "temperature": 0.3, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
        "presence_penalty": 0.0, "max_tokens": 102400, "enable_thinking": True,
        "thinking_budget": 81920,
    }
    sampling.update(overrides)
    from bench import model_params
    monkeypatch.setattr(
        model_params, "params_for",
        lambda model, profile, registry_path=None: dict(sampling),
    )
    return sampling


def _build_handler(monkeypatch, registry_name="Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
                    tool_calls=None, content=None, **sampling_overrides):
    _stub_sampling(monkeypatch, **sampling_overrides)
    cls = H._handler_class()
    handler = cls(model_name=registry_name, temperature=0.001,
                   registry_name=registry_name, is_fc_model=True)
    fake = _FakeCompletions(tool_calls=tool_calls, content=content)
    handler.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=fake)
    )
    return handler, fake


# --------------------------------------------------------------------------- (a) raw passthrough
def test_raw_messages_and_tools_pass_through_untransformed(monkeypatch):
    handler, fake = _build_handler(monkeypatch)
    messages = [{"role": "user", "content": "what is 2+2"}]
    tools = [{"type": "function", "function": {"name": "add", "parameters": {"type": "object"}}}]

    handler._query_FC({"message": messages, "tools": tools})

    # Identity, not just equality: nothing rebuilt or reformatted the payload — no
    # bfcl-owned prompt template was ever applied to it.
    assert fake.captured["messages"] is messages
    assert fake.captured["tools"] is tools
    assert fake.captured["model"] == handler.model_name


def test_no_tools_key_omitted_when_tools_empty(monkeypatch):
    handler, fake = _build_handler(monkeypatch)
    handler._query_FC({"message": [{"role": "user", "content": "hi"}], "tools": []})
    assert "tools" not in fake.captured


# --------------------------------------------------------------------------- (b) max_tokens
def test_max_tokens_comes_from_deployed_profile_not_the_4096_cap(monkeypatch):
    handler, fake = _build_handler(monkeypatch, max_tokens=102400)
    handler._query_FC({"message": [], "tools": []})
    assert fake.captured["max_tokens"] == 102400
    assert fake.captured["max_tokens"] > 4096, (
        "the base_oss_handler 4096 cap must never reach this handler — it lives only on "
        "OSSHandler, which OpenAICompletionsHandler does not subclass")


def test_max_tokens_falls_back_generously_when_registry_silent(monkeypatch):
    handler, fake = _build_handler(monkeypatch, max_tokens=None)
    handler._query_FC({"message": [], "tools": []})
    assert fake.captured["max_tokens"] == H._FALLBACK_MAX_TOKENS
    assert fake.captured["max_tokens"] > 4096


# --------------------------------------------------------------------------- (c) tool_calls decode
def test_tool_calls_decode_to_bfcl_expected_structure(monkeypatch):
    handler, fake = _build_handler(
        monkeypatch, tool_calls=[("get_weather", '{"city": "Boston"}')])
    api_response, _elapsed = handler._query_FC({"message": [], "tools": [{"type": "function"}]})
    parsed = handler._parse_query_response_FC(api_response)
    decoded = handler.decode_ast(parsed["model_responses"], "python", False)
    assert decoded == [{"get_weather": {"city": "Boston"}}]


def test_multiple_tool_calls_decode_in_order(monkeypatch):
    handler, fake = _build_handler(monkeypatch, tool_calls=[
        ("f", '{"a": 1}'), ("g", '{"b": 2}'),
    ])
    api_response, _ = handler._query_FC({"message": [], "tools": [{"type": "function"}]})
    parsed = handler._parse_query_response_FC(api_response)
    decoded = handler.decode_ast(parsed["model_responses"], "python", False)
    assert decoded == [{"f": {"a": 1}}, {"g": {"b": 2}}]


# --------------------------------------------------------------------------- (d) thinking never disabled
def test_thinking_is_requested_explicitly_and_never_disabled(monkeypatch):
    handler, fake = _build_handler(monkeypatch, enable_thinking=True, thinking_budget=81920)
    handler._query_FC({"message": [], "tools": []})
    body = fake.captured["extra_body"]
    assert body["enable_thinking"] is True
    assert body["thinking_budget"] >= 16384


def test_thinking_budget_has_a_generous_floor_even_if_registry_omits_it(monkeypatch):
    handler, fake = _build_handler(monkeypatch, thinking_budget=None)
    handler._query_FC({"message": [], "tools": []})
    body = fake.captured["extra_body"]
    assert body["enable_thinking"] is True
    assert body["thinking_budget"] >= H._FALLBACK_THINKING_BUDGET


# --------------------------------------------------------------------------- sampling carriage
def test_deployed_sampling_fields_are_carried_in_extra_body(monkeypatch):
    handler, fake = _build_handler(monkeypatch, top_p=0.95, top_k=20, min_p=0.0,
                                    presence_penalty=0.0)
    handler._query_FC({"message": [], "tools": []})
    body = fake.captured["extra_body"]
    for field in ("top_p", "top_k", "min_p", "presence_penalty"):
        assert field in body, f"{field} is not sent — the worker will use its own default"


def test_presence_penalty_defaults_to_zero_when_registry_omits_it(monkeypatch):
    # The stub sampling has NO presence_penalty key at all (true absence, not None).
    from bench import model_params
    monkeypatch.setattr(model_params, "params_for",
                         lambda model, profile, registry_path=None: {
                             "temperature": 0.3, "max_tokens": 16384})
    handler = H._handler_class()(model_name="m", temperature=0.001,
                                  registry_name="m", is_fc_model=True)
    fake = _FakeCompletions()
    handler.client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=fake))
    handler._query_FC({"message": [], "tools": []})
    assert fake.captured["extra_body"]["presence_penalty"] == 0.0, (
        "a nonzero/absent presence_penalty risks disabling suffix decoding on this stack")


def test_temperature_is_overridden_from_the_deployed_profile_not_the_bfcl_cli_default(monkeypatch):
    """bfcl's CLI always constructs the handler with --temperature (default 0.001, never
    per-model) — this must not silently win over the model's tuned operating temperature."""
    handler, _fake = _build_handler(monkeypatch, temperature=0.3)
    assert handler.temperature == 0.3
    assert handler.temperature != 0.001


# --------------------------------------------------------------------------- registration
def test_register_model_adds_a_config_using_our_handler(monkeypatch):
    from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING
    name = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit-TEST-REGISTRATION"
    monkeypatch.delitem(MODEL_CONFIG_MAPPING, name, raising=False)
    try:
        cfg = H.register_model(name, host="localhost", port=8000)
        assert MODEL_CONFIG_MAPPING[name] is cfg
        assert cfg.model_handler is H._handler_class()
        assert cfg.is_fc_model is True
        assert cfg.model_name == name  # sent as the `model` field -> mlx-serve routing key
    finally:
        monkeypatch.delitem(MODEL_CONFIG_MAPPING, name, raising=False)


def test_register_model_is_idempotent(monkeypatch):
    from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING
    name = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit-TEST-IDEMPOTENT"
    monkeypatch.delitem(MODEL_CONFIG_MAPPING, name, raising=False)
    try:
        first = H.register_model(name)
        second = H.register_model(name)
        assert first is second
    finally:
        monkeypatch.delitem(MODEL_CONFIG_MAPPING, name, raising=False)


def test_register_model_sets_endpoint_env_vars_for_the_client(monkeypatch):
    H.register_model("some-registry-name-not-asserted", host="10.0.0.5", port=9999)
    assert os.environ["MLX_BFCL_HOST"] == "10.0.0.5"
    assert os.environ["MLX_BFCL_PORT"] == "9999"


# --------------------------------------------------------------------------- client endpoint
def test_client_points_at_our_router_never_the_real_openai_api(monkeypatch):
    monkeypatch.setenv("MLX_BFCL_HOST", "localhost")
    monkeypatch.setenv("MLX_BFCL_PORT", "8000")
    # Even if the shell exports real OpenAI credentials, this handler must never use them.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-never-be-used")  # fake, the test's whole point — allow-pii-pattern
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.delenv("MLX_BFCL_BASE_URL", raising=False)
    monkeypatch.delenv("MLX_BFCL_API_KEY", raising=False)

    cls = H._handler_class()
    handler = cls.__new__(cls)  # bypass __init__ (needs a live sampling lookup); test the kwarg builder alone
    kwargs = handler._build_client_kwargs()
    assert kwargs["base_url"] == "http://localhost:8000/v1"
    assert kwargs["api_key"] != "sk-should-never-be-used"  # allow-pii-pattern


# --------------------------------------------------------------------------- lazy-import contract
def test_bfcl_eval_available_reflects_a_real_import():
    assert H.bfcl_eval_available() is True  # bfcl-eval IS installed in this venv


def test_module_import_does_not_require_bfcl_eval(monkeypatch):
    """AGENTS.md: bench tooling must lazy-import heavy deps. Simulate bfcl_eval being
    absent and confirm the module is still importable — only touching bfcl_eval-backed
    functions should raise."""
    import sys
    import importlib
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "bfcl_eval" or name.startswith("bfcl_eval."):
            raise ImportError("simulated: bfcl_eval not installed")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "bench.bfcl_handler", raising=False)

    mod = importlib.import_module("bench.bfcl_handler")
    assert mod.bfcl_eval_available() is False
    with pytest.raises(ImportError):
        mod._handler_class()
    with pytest.raises(ImportError):
        mod.register_model("whatever")

    monkeypatch.delitem(sys.modules, "bench.bfcl_handler", raising=False)
    importlib.import_module("bench.bfcl_handler")  # restore the real module for later tests
