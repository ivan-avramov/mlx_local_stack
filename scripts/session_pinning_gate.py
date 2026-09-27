"""C102(a) live gate — do client session ids reach the worker and pin the prompt cache?

Pass/fail on the pre-registered criteria in docs/specs/c102a-session-headers.md:
  A4 opencode: `opencode run` turn → worker log `session=ses_…` on every request (pinned). The
     `--continue` turn's prefix reuse is reported (`cross_process_reuse`), not gated — see the
     2026-09-27 note in a4_opencode().
  A5 OpenWebUI: a saved-chat completion → worker log `session=<chat id>`; a 2nd turn reuses.
  A6 no client id: a bare 3-request conversation still routes anonymously and reuses on request 3.

Instrument = the worker's `Request completed … session=… cached_tokens=…` line (M45 probe parser).
Run against a freshly started stack (router :8000 on the bumped submodules, OWUI :3000):

  cd $STACK_REPO && set -a; . ./.env; set +a; \
  uv run python scripts/session_pinning_gate.py --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "benchmark"))
sys.path.insert(0, str(REPO / "scripts" / "websearch"))
from bench.session_cache_probe import LogTail, chat, filler, opencode_cmd  # noqa: E402
import owui_e2e_gate as owui  # noqa: E402


def wait_rows(log: LogTail, n: int, timeout: float) -> list[dict]:
    rows, t0 = [], time.time()
    while len(rows) < n and time.time() - t0 < timeout:
        rows += log.new_rows()
        if len(rows) < n:
            time.sleep(1)
    return rows


def a6_bare(model, log, timeout) -> dict:
    msgs = [{"role": "system", "content": "Reply with the single word OK."},
            {"role": "user", "content": filler(6, 3000) + "\n\nReply OK."}]
    out = []
    for i in range(3):
        log.new_rows()
        r = chat(model, msgs, max_tokens=8, timeout=timeout, chat_id=None)
        rows = wait_rows(log, 1, 30)
        out.append({"cached": r["cached_tokens"], "prompt": r["prompt_tokens"],
                    "session": rows[-1]["session"] if rows else None})
        msgs.append({"role": "assistant", "content": r["content"]})
        msgs.append({"role": "user", "content": f"Again {i}, reply OK."})
    ok = all(o["session"] and o["session"].startswith("anon:") for o in out) and (out[2]["cached"] or 0) >= 2500
    return {"pass": ok, "requests": out}


def a4_opencode(model, log, root: Path, timeout) -> dict:
    proj = root / "oc-proj"; proj.mkdir(parents=True, exist_ok=True)
    (proj / "hello.py").write_text("def hello(name):\n    return f'hello {name}'\n")
    env = dict(os.environ, XDG_DATA_HOME=str(root / "xdg"))
    turns = []
    for i, prompt in enumerate(("In one sentence, what does hello.py do?", "One line: what does it return for 'x'?")):
        log.new_rows()
        cmd = opencode_cmd(model, proj, prompt, first=(i == 0))
        with (root / f"oc_turn_{i + 1}.txt").open("w") as f:
            try:
                rc = subprocess.run(cmd, cwd=proj, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                rc = "timeout"
        rows = wait_rows(log, 1, 30)
        turns.append({"rc": rc, "requests": [{"session": r["session"], "cached": r["cached_tokens"], "prompt": r["prompt_tokens"]} for r in rows]})
    sessions = {r["session"] for t in turns for r in t["requests"]}
    pinned = bool(sessions) and all(s.startswith("ses_") for s in sessions) and len(sessions) == 1
    reused = any((r["cached"] or 0) >= 5000 for r in turns[1]["requests"]) if len(turns) > 1 else False
    # A4 = the session id reaches the worker on every request. Cross-process prefix reuse is
    # REPORTED, not gated: measured 2026-09-27, opencode's system prompt embeds discovered skill
    # paths, and Claude Code's synced-skills directory names rotate between runs, so a new
    # `opencode run` process diverges inside the system prompt where no DeltaNet snapshot
    # exists → full re-prefill regardless of pinning (see lab notebook 2026-09-27).
    return {"pass": pinned and all(t["rc"] == 0 for t in turns), "cross_process_reuse": reused,
            "sessions": sorted(sessions), "turns": turns}


def a5_owui(model, log, base, email, password, timeout) -> dict:
    api = owui.login(base, email, password)
    q = "Reply with the single word OK."
    chat_doc, uid, aid = owui.chat_payload(model, q, "c102a session gate")
    chat_id = api.post("/api/v1/chats/new", {"chat": chat_doc})["id"]
    payload = owui.completion_payload(model, q, chat_id, aid, str(uuid.uuid4()))
    payload["features"] = {k: False for k in payload["features"]}
    log.new_rows()
    api.post("/api/chat/completions", payload, timeout=timeout)
    rows = wait_rows(log, 1, timeout)
    first = rows[-1] if rows else None
    # second turn in the same chat: the frontend shape re-sends the history with a new message id
    time.sleep(2)
    doc = api.get(f"/api/v1/chats/{chat_id}")
    asst = owui.assistant_message(doc, aid)
    content = (asst.get("content") or "").strip() or "OK"
    aid2 = str(uuid.uuid4())
    payload2 = owui.completion_payload(model, "Again, reply OK.", chat_id, aid2, str(uuid.uuid4()))
    payload2["features"] = {k: False for k in payload2["features"]}
    payload2["messages"] = [{"role": "user", "content": q}, {"role": "assistant", "content": content},
                            {"role": "user", "content": "Again, reply OK."}]
    log.new_rows()
    api.post("/api/chat/completions", payload2, timeout=timeout)
    rows2 = wait_rows(log, 1, timeout)
    second = rows2[-1] if rows2 else None
    pinned = bool(first) and first["session"] == chat_id and bool(second) and second["session"] == chat_id
    reused = bool(second) and (second["cached_tokens"] or 0) > 0
    return {"pass": pinned and reused, "chat_id": chat_id,
            "first": first and {k: first[k] for k in ("session", "cached_tokens", "prompt_tokens")},
            "second": second and {k: second[k] for k in ("session", "cached_tokens", "prompt_tokens")}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--log", default=str(REPO / "logs/mlx_vlm.log"))
    ap.add_argument("--owui-url", default=os.environ.get("OWUI_URL", "http://localhost:3000"))
    ap.add_argument("--skip-owui", action="store_true")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--workdir", default=os.path.join(os.environ.get("STACK_WORKDIR", "/tmp"), "c102a"))
    a = ap.parse_args(argv)
    root = Path(a.workdir); root.mkdir(parents=True, exist_ok=True)
    log = LogTail(Path(a.log))
    res = {"model": a.model, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    res["A6_bare_anonymous"] = a6_bare(a.model, log, a.timeout); print("[A6]", res["A6_bare_anonymous"]["pass"], flush=True)
    res["A4_opencode"] = a4_opencode(a.model, log, root, a.timeout); print("[A4]", res["A4_opencode"]["pass"], res["A4_opencode"]["sessions"], flush=True)
    if not a.skip_owui:
        res["A5_openwebui"] = a5_owui(a.model, log, a.owui_url, os.environ.get("OWUI_ADMIN_EMAIL", "admin@a.a"),
                                      os.environ.get("OWUI_ADMIN_PASSWORD", "admin"), a.timeout)
        print("[A5]", res["A5_openwebui"]["pass"], res["A5_openwebui"]["first"], res["A5_openwebui"]["second"], flush=True)
    out = root / "gate.json"
    text = json.dumps(res, indent=1)
    for real, ph in ((os.environ.get("STACK_WORKDIR"), "$STACK_WORKDIR"), (os.path.expanduser("~"), "$HOME")):
        if real and real != "~":
            text = text.replace(real, ph)
    out.write_text(text)
    verdict = all(v.get("pass") for k, v in res.items() if isinstance(v, dict))
    print(f"[gate] {'PASS' if verdict else 'FAIL'} -> {out}", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
