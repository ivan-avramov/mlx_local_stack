"""Transparent logging proxy :8001 -> :8000 for the M6c suffix-acceptance probe.

Streams responses through untouched; any response line mentioning draft_ fields is
appended (raw) to counters.jsonl with ts + request path. Throwaway instrument.
"""
import json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request

UP = "http://127.0.0.1:8000"
LOG = "$STACK_WORKDIR/m6c/counters.jsonl"
lock = threading.Lock()

def log_line(obj):
    with lock, open(LOG, "a") as f:
        f.write(json.dumps(obj) + "\n")

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def _proxy(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        req = urllib.request.Request(UP + self.path, data=body, method=self.command)
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length", "accept-encoding", "connection"):
                req.add_header(k, v)
        req.add_header("Accept-Encoding", "identity")
        try:
            up = urllib.request.urlopen(req, timeout=7200)
        except urllib.error.HTTPError as e:
            up = e
        self.send_response(up.code)
        for k, v in up.headers.items():
            if k.lower() not in ("transfer-encoding", "content-length", "connection"):
                self.send_header(k, v)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        buf = b""
        while True:
            chunk = up.read(4096)
            if not chunk:
                break
            self.wfile.write(("%x\r\n" % len(chunk)).encode() + chunk + b"\r\n")
            self.wfile.flush()
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if b"draft_" in line or b"predicted_per_second" in line:
                    log_line({"ts": time.time(), "path": self.path,
                              "line": line.decode("utf-8", "replace")[:2000]})
        if buf and (b"draft_" in buf or b"predicted_per_second" in buf):
            log_line({"ts": time.time(), "path": self.path,
                      "line": buf.decode("utf-8", "replace")[:2000]})
        self.wfile.write(b"0\r\n\r\n")
    def do_POST(self): self._proxy()
    def do_GET(self): self._proxy()
    def log_message(self, *a): pass

ThreadingHTTPServer(("127.0.0.1", 8001), H).serve_forever()
