"""Scripted native-v2 wire fixture, adapted from the M59 verified capture."""

from __future__ import annotations
import json
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONTEXT_ERROR = {
    "error": {
        "message": "This model's maximum context length is 4096 tokens. However, your messages resulted in 9999 tokens. Please reduce the length of the messages.",
        "type": "invalid_request_error",
        "param": "messages",
        "code": "context_length_exceeded",
    }
}


class MockServer:
    """One-based chat request script; all HTTP traffic retained in requests."""

    def __init__(self, script=None):
        self.script = script or {}
        self.requests = []
        self.chat_count = 0
        self.lock = threading.Lock()
        self.release_stream = threading.Event()
        self.stream_started = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):
                """Log message."""
                pass

            def record(self, body=None):
                """Record."""
                with owner.lock:
                    owner.requests.append(
                        {"path": self.path, "headers": dict(self.headers), "body": body}
                    )

            def reply(self, code, body):
                """Reply."""
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                """Do get."""
                self.record()
                self.reply(
                    200,
                    (
                        {"object": "list", "data": []}
                        if self.path.endswith("/models")
                        else {"status": "ok"}
                    ),
                )

            def do_POST(self):
                """Do post."""
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                self.record(body)
                with owner.lock:
                    owner.chat_count += 1
                    number = owner.chat_count
                    kind = owner.script.get(owner.chat_count, "ok")
                if kind == "http500":
                    return self.reply(
                        500, {"error": {"message": "mock internal error", "type": "server_error"}}
                    )
                if kind == "ctx400":
                    return self.reply(400, CONTEXT_ERROR)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()

                def chunk(delta, finish=None, usage=None):
                    """Chunk."""
                    data = {
                        "id": "chatcmpl-mock",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": body["model"],
                        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                    }
                    if usage:
                        data["choices"] = []
                        data["usage"] = usage
                    return ("data: " + json.dumps(data) + "\n\n").encode()

                messages = body.get("messages", [])
                if kind == "hang":
                    self.wfile.write(chunk({"role": "assistant", "content": "thinking..."}))
                    self.wfile.flush()
                    owner.stream_started.set()
                    owner.release_stream.wait(30)
                    return
                # A dict script entry always answers with its tool call, so multi-call scripts
                # (e.g. three identical shell calls) are possible; other requests finish after a tool result.
                finished = any(m.get("role") == "tool" for m in messages) and not isinstance(kind, dict)
                if finished:
                    chunks = [chunk({"role": "assistant", "content": "Done."}), chunk({}, "stop")]
                else:
                    default = {"name": "write", "input": {"path": "solution.py", "content": "answer = 42\n"}}
                    # {"calls": [tool, ...]} emits several parallel tool calls in one response.
                    tools = kind["calls"] if isinstance(kind, dict) and "calls" in kind else [
                        kind if isinstance(kind, dict) else default]
                    chunks = []
                    for index, tool in enumerate(tools):
                        # ids unique per request/index so multi-call scripts never repeat a part id
                        call_id = "call_write" if number == 1 and index == 0 else f"call_write_{number}_{index}"
                        chunks += [
                            chunk({"role": "assistant", "content": None, "tool_calls": [
                                {"index": index, "id": call_id, "type": "function",
                                 "function": {"name": tool["name"], "arguments": ""}}]}),
                            chunk({"tool_calls": [{"index": index, "function": {
                                "arguments": json.dumps(tool["input"])}}]}),
                        ]
                    chunks.append(chunk({}, "tool_calls"))
                if kind == "drop":
                    self.wfile.write(chunks[0])
                    self.wfile.flush()
                    self.connection.setsockopt(
                        socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                    )
                    self.connection.close()
                    return
                chunks += [
                    chunk(
                        {},
                        usage={"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
                    ),
                    b"data: [DONE]\n\n",
                ]
                for data in chunks:
                    self.wfile.write(data)
                    self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.closed = False
        if self.script.get(1) == "refuse":
            self.close()

    @property
    def chats(self):
        """Chats."""
        return [r for r in self.requests if r["path"].endswith("/chat/completions")]

    @property
    def tripwire_hits(self):
        """Tripwire hits."""
        return sum("/vllm-tripwire/" in r["path"] for r in self.requests)

    def close(self):
        """Close."""
        if not self.closed:
            self.release_stream.set()
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(2)
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
