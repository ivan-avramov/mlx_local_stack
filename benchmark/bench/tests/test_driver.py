import json, threading
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
