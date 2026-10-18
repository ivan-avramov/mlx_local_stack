"""P371 phase 4 (A13): a tiny agent CLIENT for the contract suite's core runs, a real process that makes real HTTP
requests to the scripted mock provider (`opencode_v2_mock.MockServer`) and prints the gate's event lines.

Run as `python fake_contract_client.py`; configured by the `FAKE_CLIENT_CONFIG` environment variable (JSON). Its
behaviour is the thing the contract suite's injected defects change: every defect of `arm_contract_real.DEFECTS` that is a
CLIENT defect is one key of `behaviour` here (a wrong seed on request N, an extra tool, a retry after a 500, a compaction
request with a wrong seed ...). The conforming client sends, on every request, the configured sampling, the seed of the
`NEUTRAL_OVERLAY`, the configured tools and only the roles a chat has.

The agent loop is the usual one: post the conversation, run the tool calls of the answer, post again until the model
stops. At a reduced `window` it sends one summary (compaction) request after the context outgrew the window, records the
compaction event and its tokens, and continues from the summary. Standard library only (it runs under any interpreter)."""
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SUMMARY_PROMPT = "You MUST summarize the conversation above into the template below."
SESSION = "s1"


def emit(kind, mid, **part):
    print(json.dumps(dict(type=kind, sessionID=SESSION, part=dict(id=f"{kind}-{mid}-{part.pop('suffix', '')}",
                                                                  messageID=mid, **part))), flush=True)


def tools_list(names):
    return [dict(type="function", function=dict(name=n, description=n, parameters=dict(type="object", properties={})))
            for n in names]


class Client:
    def __init__(self, cfg):
        self.cfg = cfg
        self.behaviour = cfg.get("behaviour") or {}
        self.seed = json.loads(os.environ["NEUTRAL_OVERLAY"])["neutral_seed"]
        self.requests = 0
        self.messages = [dict(role="system", content="You are a coding agent."),
                         dict(role="user", content=os.environ.get("FAKE_CLIENT_PROMPT", "do the task"))]
        self.assistant_messages = []
        self.compaction = []
        self.step = 0
        self.last_prompt_tokens = 0
        out = Path(os.environ["FAKE_CLIENT_EXPORT"])
        self.export_path = out
        self.error_exit = None

    # ------------------------------------------------------------------ wire
    def body(self, kind):
        """The request body of one request of class `kind` (task | compaction); the defects change it here."""
        b = self.behaviour
        n = self.requests + 1
        body = dict(self.cfg["sampling"], model=self.cfg["model"], stream=True, messages=[dict(m) for m in self.messages],
                    seed=self.seed)
        names = list(self.cfg["tools"])
        if b.get("extra_tool"):
            names.append("subagent")
        if b.get("tools_change_at") == n:
            names = names[:-1] + ["shell2"]
        if kind == "compaction":
            body["messages"].append(dict(role="user", content=SUMMARY_PROMPT))
            if b.get("compaction_seed") is not None:
                body["seed"] = b["compaction_seed"]
            if b.get("compaction_budget") is not None:
                body["thinking_budget"] = b["compaction_budget"]
            if b.get("compaction_no_tools"):
                names = []
            if b.get("compaction_extra_role"):
                body["messages"].insert(1, dict(role="developer", content="x"))
        if b.get("seed_at", {}).get(str(n)) is not None:
            body["seed"] = b["seed_at"][str(n)]
        if b.get("developer_role_at") == n:
            body["messages"][0]["role"] = "developer"
        if names:
            body["tools"] = tools_list(names)
        return body

    def post(self, body):
        data = json.dumps(body).encode()
        req = urllib.request.Request(self.cfg["base"] + "/chat/completions", data=data,
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer none",
                                              **self.cfg.get("headers", {})})
        self.requests += 1
        try:
            resp = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as exc:
            return dict(status=exc.code)
        text, calls, usage, finish = "", {}, None, None
        for raw in resp:
            line = raw.decode().strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            chunk = json.loads(line[5:])
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                text += delta.get("content") or ""
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc["index"], dict(id=tc.get("id"), name="", args=""))
                    slot["id"] = tc.get("id") or slot["id"]
                    slot["name"] += (tc.get("function") or {}).get("name") or ""
                    slot["args"] += (tc.get("function") or {}).get("arguments") or ""
                finish = choice.get("finish_reason") or finish
        return dict(status=200, text=text, calls=[calls[k] for k in sorted(calls)], usage=usage or {}, finish=finish)

    def request(self, kind):
        """One request; a 500 is final unless the (defective) client retries."""
        reply = self.post(self.body(kind))
        if reply["status"] != 200 and self.behaviour.get("retry_on_500"):
            reply = self.post(self.body(kind))
        return reply

    # ------------------------------------------------------------------ session
    def tokens(self, usage):
        return dict(output=usage.get("completion_tokens", 0), reasoning=0, input=usage.get("prompt_tokens", 0),
                    cache=dict(read=0, write=0))

    def run_tool(self, call):
        args = json.loads(call["args"] or "{}")
        if call["name"] == "write":
            Path("solution.txt").write_text("answer = 42\n")
        return args

    def finish_export(self, last_finish="stop", error=None):
        doc = dict(info=dict(id=SESSION), messages=self.assistant_messages, compaction=self.compaction)
        self.export_path.write_text(json.dumps(doc))

    def assistant(self, mid, usage, finish):
        self.assistant_messages.append(dict(id=mid, type="assistant", finish=finish, tokens=self.tokens(usage)))

    def run(self):
        b = self.behaviour
        signal.signal(signal.SIGTERM, self.on_term)
        shape = b.get("shape")
        if shape == "cancel":
            Path(self.cfg["cancel_file"]).write_text("")
        while True:
            self.step += 1
            mid = f"m{self.step}"
            emit("step_start", mid)
            reply = self.request("task")
            if reply["status"] != 200:
                return self.on_http_error(mid, reply)
            usage = reply["usage"]
            self.last_prompt_tokens = usage.get("prompt_tokens", 0)
            if reply["calls"]:
                self.messages.append(dict(role="assistant", content=None, tool_calls=[
                    dict(id=c["id"], type="function", function=dict(name=c["name"], arguments=c["args"]))
                    for c in reply["calls"]]))
                for c in reply["calls"]:
                    args = self.run_tool(c)
                    self.messages.append(dict(role="tool", tool_call_id=c["id"], content="ok"))
                    now = int(time.time() * 1000)
                    emit("tool_use", mid, suffix=c["id"], type="tool", tool=c["name"],
                         state=dict(status="completed", input=args, output="ok", title=c["name"], metadata={},
                                    time=dict(start=now, end=now)))
            else:
                self.messages.append(dict(role="assistant", content=reply["text"]))
            finish = "stop" if not reply["calls"] else "tool-calls"
            if b.get("shape") == "length" and not reply["calls"]:
                finish = "length"
            self.assistant(mid, usage, finish)
            emit("step_finish", mid, tokens=self.tokens(usage))
            if shape == "cancel":
                time.sleep(60)                               # the runner cancels us; SIGTERM ends the sleep
            if self.cfg.get("window") and self.last_prompt_tokens >= self.cfg["window"] - 1000 and reply["calls"]:
                self.compact(mid)
                continue
            if not reply["calls"]:
                break
        return self.end(shape)

    def compact(self, after):
        b = self.behaviour
        reply = self.request("compaction")
        if reply["status"] != 200:
            return
        usage = reply["usage"]
        info = dict(after=after, reason="auto", usage=dict(
            input=usage.get("prompt_tokens", 0), cache_read=0, cache_write=0, output=usage.get("completion_tokens", 0),
            reasoning=0))
        if b.get("compaction_tokens_wrong"):
            info["usage"] = dict(info["usage"], output=1, input=1)
        if not b.get("compaction_uncounted"):
            self.compaction.append(info)
        if not b.get("no_compaction_event"):
            print(json.dumps(dict(type="compaction", sessionID=SESSION, info=info)), flush=True)
        self.messages = self.messages[:2] + [dict(role="user", content="summary: " + reply["text"][:80])]

    def on_http_error(self, mid, reply):
        b = self.behaviour
        if b.get("swallow_500"):                              # defect: the failure is scored as if nothing happened
            emit("step_finish", mid, tokens=self.tokens({}))
            self.assistant(mid, {}, "stop")
            self.finish_export()
            return 0
        print(json.dumps(dict(type="error", sessionID=SESSION, error=dict(type="mystery.http", status=reply["status"]))),
              flush=True)
        self.assistant(mid, {}, "error")
        self.assistant_messages[-1]["error"] = dict(type="mystery.http")
        self.finish_export()
        return 1

    def end(self, shape):
        if shape == "error":
            print(json.dumps(dict(type="error", sessionID=SESSION, error=dict(type="mystery.failure"))), flush=True)
            self.finish_export()
            return 1
        if shape == "client_cut":
            emit("step_start", f"m{self.step + 1}")
            print(json.dumps(dict(type="error", sessionID=SESSION, error=dict(
                type="aborted", message="Session interrupted: inactivity"))), flush=True)
            self.assistant_messages.append(dict(id=f"m{self.step + 1}", type="assistant", finish="error", tokens=None,
                                                error=dict(type="aborted", message="Step interrupted"), content=[],
                                                time=dict(created=1_000, streamed=3_634_000, completed=3_634_070)))
            self.finish_export()
            return 1
        self.finish_export()
        return 7 if shape == "unregistered" else 0

    def on_term(self, signum, frame):
        marker = os.environ.get("FAKE_CLIENT_SIGNALS")
        if marker:
            with open(marker, "a") as fh:
                fh.write("SIGTERM\n")
        self.finish_export()
        sys.exit(143)


if __name__ == "__main__":
    client = Client(json.loads(os.environ["FAKE_CLIENT_CONFIG"]))
    sys.exit(client.run())
