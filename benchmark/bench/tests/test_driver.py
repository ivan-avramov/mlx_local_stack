import json, threading
import pytest
from http.server import BaseHTTPRequestHandler, HTTPServer
from bench.driver import MlxServeDriver

CANNED = {
    "choices": [{"message": {"content": "ANSWER", "reasoning": ""}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 10},
    "timings": {"predicted_per_second": 20.0, "predicted_ms": 500.0, "peak_memory": 40.4, "prompt_n": 1000},
}

class _H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(CANNED).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass


def _server_returning(doc):
    body_bytes = json.dumps(doc).encode()

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _client_against(srv, monkeypatch):
    monkeypatch.setenv("MLX_SERVE_BASE", f"http://127.0.0.1:{srv.server_address[1]}")
    import importlib, bench.client; importlib.reload(bench.client)
    return bench.client


def test_complete_parses_and_derives_prefill(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MLX_SERVE_BASE", f"http://127.0.0.1:{srv.server_address[1]}")
    import importlib, bench.client; importlib.reload(bench.client)
    import bench.driver; importlib.reload(bench.driver)
    d = bench.driver.MlxServeDriver()
    out = d.complete("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()
    assert out["content"] == "ANSWER"
    assert out["prompt_tokens"] == 1000
    assert out["decode_tps"] == 20.0
    # prefill_s = wall - predicted_ms/1000 ; prefill_tps = prompt_tokens / prefill_s
    assert out["prefill_s"] > 0
    assert out["prefill_tps"] > 0


# --------------------------------------------------------------------------- P18 malformed response
def test_probe_raises_on_error_envelope_despite_200(monkeypatch):
    srv = _server_returning({"error": {"message": "model not loaded", "type": "invalid_request"}})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="error envelope"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_raises_on_missing_choices(monkeypatch):
    srv = _server_returning({"usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="choices"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_raises_on_empty_choices_list(monkeypatch):
    srv = _server_returning({"choices": []})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="choices"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_raises_on_choice_missing_message(monkeypatch):
    srv = _server_returning({"choices": [{"finish_reason": "stop"}]})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="message"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_accepts_a_tool_call_only_message_with_empty_content(monkeypatch):
    """A message with tool_calls and NO content is a LEGITIMATE completion, not malformed --
    P18 must not over-fire on every empty-content turn."""
    srv = _server_returning({
        "choices": [{"message": {"content": None, "tool_calls": [{"id": "c0", "type": "function",
                                                                   "function": {"name": "f", "arguments": "{}"}}]},
                    "finish_reason": "tool_calls"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    client = _client_against(srv, monkeypatch)
    out = client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()
    assert out["content"] == ""
    assert len(out["tool_calls"]) == 1


def test_probe_raises_on_a_response_missing_usage_P24(monkeypatch):
    """6th cold review round 6 P24 (HIGH): superseded P11's `missing_usage` nonconv_kind design --
    the mlx-serve router ALWAYS returns usage.{prompt,completion}_tokens; their absence is a
    SERVING anomaly, never a legitimate model signal, and must ESCALATE at the transport boundary
    rather than quietly becoming a scored (non-converged) row."""
    srv = _server_returning({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="usage"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_raises_on_missing_finish_reason_P24(monkeypatch):
    srv = _server_returning({"choices": [{"message": {"content": "ok"}}],
                             "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="finish_reason"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_accepts_empty_message_with_valid_finish_reason_and_usage_P36(monkeypatch):
    """7th cold review round 7 P36 (HIGH, supersedes the round-6 P24 ruling): the round-6 check
    was a REGRESSION -- `{"choices":[{"message":{}, "finish_reason": "stop"}]}` with valid usage
    is a VALID model outcome (immediate EOS), not a serving anomaly. The client boundary validates
    STRUCTURE/TELEMETRY TYPES only; classifying an empty completion is the agent loop's job."""
    srv = _server_returning({"choices": [{"message": {}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 1, "completion_tokens": 0}})
    client = _client_against(srv, monkeypatch)
    out = client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()
    assert out["content"] == "" and out["tool_calls"] == []
    assert out["finish_reason"] == "stop"
    assert out["completion_tokens"] == 0


def test_probe_accepts_length_finish_with_empty_content_and_reasoning_P36(monkeypatch):
    """P36: a `finish_reason=="length"` (max_tokens/budget hit) with empty `content` but non-empty
    `reasoning` and valid usage is a legitimate budget-hit outcome, not malformed."""
    srv = _server_returning({"choices": [{"message": {"reasoning": "thinking..."},
                                         "finish_reason": "length"}],
                             "usage": {"prompt_tokens": 10, "completion_tokens": 500}})
    client = _client_against(srv, monkeypatch)
    out = client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()
    assert out["finish_reason"] == "length"
    assert out["content"] == "" and out["reasoning"] == "thinking..."
    assert out["completion_tokens"] == 500


def test_probe_raises_on_non_integer_completion_tokens_P36(monkeypatch):
    """P36 reproduction: completion_tokens="bad" (wrong TYPE, not merely absent) must still
    escalate -- type validation, not just presence."""
    srv = _server_returning({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 1, "completion_tokens": "bad"}})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="non-negative"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_raises_on_negative_completion_tokens_P36(monkeypatch):
    srv = _server_returning({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 1, "completion_tokens": -5}})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="non-negative"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_raises_on_bool_as_completion_tokens_P36(monkeypatch):
    """A JSON `true`/`false` deserializes to Python `bool`, which IS an `int` subclass in Python
    -- must be explicitly rejected, never silently counted as 0 or 1 tokens."""
    srv = _server_returning({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 1, "completion_tokens": True}})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="non-negative"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


def test_probe_accepts_prompt_tokens_from_timings_fallback_P24(monkeypatch):
    """The usage-presence check must honor the SAME prompt_tokens fallback (usage.prompt_tokens
    OR timings.prompt_n) the return value itself uses -- not re-require usage.prompt_tokens
    directly when the timings block already supplies it."""
    srv = _server_returning({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                             "usage": {"completion_tokens": 5},
                             "timings": {"prompt_n": 1000, "predicted_per_second": 20.0}})
    client = _client_against(srv, monkeypatch)
    out = client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()
    assert out["prompt_tokens"] == 1000
    assert out["completion_tokens"] == 5


# --------------------------------------------------------------------------- P50 finish_reason validation
@pytest.mark.parametrize("value", ["content_filter", "function_call", "", "STOP", "stopp", "none"])
def test_probe_raises_on_an_unrecognized_finish_reason_string_P50(monkeypatch, value):
    """8th cold review round 8 P50: finish_reason must be one of {"stop","length","tool_calls"}
    -- the only values the served router/mlx_vlm fork ever legitimately emits. Anything else is a
    SERVING anomaly, escalated here rather than reaching convergence classification as if it were
    an ordinary model outcome."""
    srv = _server_returning({"choices": [{"message": {"content": "ok"}, "finish_reason": value}],
                             "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="finish_reason"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


@pytest.mark.parametrize("value", [True, 1, 1.5, ["stop"], {"x": "stop"}])
def test_probe_raises_on_a_non_string_finish_reason_P50(monkeypatch, value):
    srv = _server_returning({"choices": [{"message": {"content": "ok"}, "finish_reason": value}],
                             "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    client = _client_against(srv, monkeypatch)
    with pytest.raises(client.MalformedResponseError, match="finish_reason"):
        client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()


@pytest.mark.parametrize("value", ["stop", "length", "tool_calls"])
def test_probe_accepts_every_legitimate_finish_reason_P50(monkeypatch, value):
    srv = _server_returning({"choices": [{"message": {"content": "ok"}, "finish_reason": value}],
                             "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    client = _client_against(srv, monkeypatch)
    out = client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()
    assert out["finish_reason"] == value
