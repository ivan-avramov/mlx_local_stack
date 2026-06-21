import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

TOOLCALL_RESP = {
    "choices": [{"message": {"content": "", "reasoning": "",
                             "tool_calls": [{"id": "c1", "type": "function",
                                             "function": {"name": "read_file",
                                                          "arguments": "{\"path\": \"a.py\"}"}}]},
                 "finish_reason": "tool_calls"}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    "timings": {"predicted_per_second": 9.0, "predicted_ms": 100.0, "peak_memory": 1.0, "prompt_n": 10},
}


class _H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(TOOLCALL_RESP).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_driver_returns_tool_calls(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MLX_SERVE_BASE", f"http://127.0.0.1:{srv.server_address[1]}")
    import importlib
    import bench.client
    importlib.reload(bench.client)
    import bench.driver
    importlib.reload(bench.driver)
    d = bench.driver.MlxServeDriver()
    out = d.complete("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16},
                     tools=[{"type": "function", "function": {"name": "read_file"}}])
    srv.shutdown()
    assert isinstance(out["tool_calls"], list) and len(out["tool_calls"]) == 1
    assert out["tool_calls"][0]["function"]["name"] == "read_file"


def test_probe_tool_calls_defaults_empty(monkeypatch):
    # Reuse the canned tool-call server but ensure the field is always a list.
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MLX_SERVE_BASE", f"http://127.0.0.1:{srv.server_address[1]}")
    import importlib
    import bench.client
    importlib.reload(bench.client)
    r = bench.client.probe("m", [{"role": "user", "content": "hi"}], {"max_tokens": 1})
    srv.shutdown()
    assert isinstance(r["tool_calls"], list)
