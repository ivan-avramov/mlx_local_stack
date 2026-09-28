"""Live stack smoke (2026-09-27 upstream-sync gate; reusable after any fork bump).

Five cases plus a three-turn session-reuse check, through the router on :8000 at the model's
DEPLOYED sampling (`bench.model_params.params_for(model, profile="deployed")`, thinking ON,
budgets untouched). Mirrors the C84 shape (arithmetic, Python, JSON, native tool continuation,
vision) so results line up with `benchmark/results/upstream_2026-09-13_smokes.json`.

Pass/fail per case is mechanical; transport errors ESCALATE (nonzero exit, never graded).
Convergence is reported per case against the resolved thinking budget as `converged`.

  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.stack_smoke \
      --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --tag sync-2026-09-27
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from bench import client
from bench.model_params import params_for

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name"}},
            "required": ["city"],
        },
    },
}]


def _post(body: dict, headers: dict | None = None, timeout: float = 3600) -> dict:
    req = urllib.request.Request(
        client.BASE + "/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _answer(text: str) -> str:
    return client.strip_thinking(text or "").strip()


def _converged(res: dict, params: dict) -> bool:
    budget = params.get("thinking_budget")
    ct = res.get("completion_tokens") or 0
    return res.get("finish_reason") == "stop" and (budget is None or ct < budget)


def _code_block(text: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    return m.group(1) if m else text


def _synthetic_image() -> str:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (256, 256), "white")
    ImageDraw.Draw(img).ellipse((48, 48, 208, 208), fill=(220, 20, 20))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def case_arithmetic(model, params):
    res = client.probe(model, [{"role": "user", "content": "What is 17 * 23? Reply with the number only."}], params)
    ans = _answer(res["content"])
    return "391" in ans.replace(",", ""), res, ans[:80]


def case_python(model, params):
    res = client.probe(model, [{"role": "user", "content":
        "Write a Python function `is_prime(n)` that returns True for primes and False otherwise. "
        "Return ONLY the code in one ```python block."}], params)
    ns: dict = {}
    try:
        exec(_code_block(_answer(res["content"])), ns)  # noqa: S102 — smoke on our own box
        ok = ns["is_prime"](7) is True and ns["is_prime"](8) is False and ns["is_prime"](97) is True and ns["is_prime"](1) is False
    except Exception as e:  # graded as fail, never crash the smoke
        return False, res, f"exec error: {type(e).__name__}: {e}"[:120]
    return ok, res, "is_prime ok"


def case_json(model, params):
    res = client.probe(model, [{"role": "user", "content":
        'Return a JSON object with keys "city" (string, "Paris") and "population_millions" (number, about 2.1). '
        "Output only the JSON, no prose, no code fence."}], params)
    ans = _answer(res["content"])
    m = re.search(r"\{.*\}", ans, re.S)
    try:
        obj = json.loads(m.group(0) if m else ans)
        ok = obj.get("city") == "Paris" and isinstance(obj.get("population_millions"), (int, float))
    except Exception as e:
        return False, res, f"json error: {e}"[:120]
    return ok, res, json.dumps(obj)[:80]


def case_tool_continuation(model, params):
    msgs = [{"role": "user", "content": "What's the weather in Paris right now? Use the tool."}]
    r1 = client.probe(model, msgs, params, tools=TOOLS)
    calls = r1["tool_calls"]
    if not calls or calls[0]["function"]["name"] != "get_weather":
        return False, r1, f"no get_weather call (finish={r1['finish_reason']}, calls={calls!r:.80})"
    args = json.loads(calls[0]["function"]["arguments"] or "{}")
    msgs.append({"role": "assistant", "content": r1["content"] or None, "tool_calls": calls})
    msgs.append({"role": "tool", "tool_call_id": calls[0].get("id"), "name": "get_weather",
                 "content": json.dumps({"city": args.get("city", "Paris"), "temp_c": 18, "condition": "cloudy"})})
    r2 = client.probe(model, msgs, params, tools=TOOLS)
    ans = _answer(r2["content"]).lower()
    ok = r1["finish_reason"] == "tool_calls" and r2["finish_reason"] == "stop" and ("18" in ans and "cloud" in ans)
    r2["handoff"] = {"finish_reason": r1["finish_reason"], "args": args, "wall_s": r1["wall_s"]}
    return ok, r2, ans[:80]


def case_vision(model, params):
    res = client.probe(model, [{"role": "user", "content": [
        {"type": "text", "text": "What shape and colour is drawn in this image? Answer in one short sentence."},
        {"type": "image_url", "image_url": {"url": _synthetic_image()}}]}], params)
    ans = _answer(res["content"]).lower()
    return ("red" in ans and ("circle" in ans or "round" in ans or "disc" in ans or "dot" in ans)), res, ans[:80]


def case_session_reuse(model, params):
    """Pinned chat id, three turns; turn-3 must report cached_tokens > 0 and stay correct."""
    chat_id = f"smoke-{uuid.uuid4().hex[:8]}"
    hdr = {"X-MLX-VLM-Chat-Id": chat_id}
    system = "You are a terse assistant. " + ("Reference paragraph: " + "The quick brown fox jumps over the lazy dog. ") * 40
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": "Remember the number 4471. Reply OK."}]
    body = {"model": model, "stream": False, **params}
    t0 = time.perf_counter(); r1 = _post({**body, "messages": msgs}, hdr)
    msgs.append({"role": "assistant", "content": r1["choices"][0]["message"].get("content") or "OK"})
    msgs.append({"role": "user", "content": "Now remember the colour green. Reply OK."})
    r2 = _post({**body, "messages": msgs}, hdr)
    msgs.append({"role": "assistant", "content": r2["choices"][0]["message"].get("content") or "OK"})
    msgs.append({"role": "user", "content": "What number and colour did I ask you to remember? One line."})
    r3 = _post({**body, "messages": msgs}, hdr); wall = time.perf_counter() - t0
    us = r3.get("usage") or {}
    cached = (us.get("prompt_tokens_details") or {}).get("cached_tokens")
    ans = _answer(r3["choices"][0]["message"].get("content")).lower()
    ok = bool(cached) and cached > 0 and "4471" in ans and "green" in ans
    res = {"content": ans, "finish_reason": r3["choices"][0].get("finish_reason"),
           "completion_tokens": us.get("completion_tokens"), "prompt_tokens": us.get("prompt_tokens"),
           "cached_tokens_turn3": cached, "wall_s": round(wall, 1), "chat_id": chat_id,
           "cached_turn2": ((r2.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens")}
    return ok, res, f"cached_turn3={cached} prompt={us.get('prompt_tokens')} ans={ans[:50]}"


CASES = [("arithmetic", case_arithmetic), ("python", case_python), ("json", case_json),
         ("tool_continuation", case_tool_continuation), ("vision", case_vision),
         ("session_reuse_3turn", case_session_reuse)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None, help="comma-separated case names")
    a = ap.parse_args()
    params = params_for(a.model, profile="deployed")
    workdir = os.environ.get("STACK_WORKDIR") or os.path.expanduser("~/ws/mlx_local_stack_workdir")
    out = Path(a.out) if a.out else Path(workdir) / "smokes" / f"stack_smoke_{a.tag}_{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"model={a.model} params={json.dumps(params)}", flush=True)
    client.preload(a.model)
    rows = []; failed = 0
    for name, fn in CASES:
        if a.only and name not in a.only.split(","):
            continue
        try:
            ok, res, note = fn(a.model, params)
        except Exception as e:  # transport / harness failure: escalate, do not grade
            print(f"[{name}] TRANSPORT ERROR {type(e).__name__}: {e}", flush=True)
            json.dump({"status": "aborted", "model": a.model, "rows": rows, "error": f"{name}: {type(e).__name__}: {e}"}, open(out, "w"), indent=1)
            return 2
        conv = _converged(res, params)
        row = {"case": name, "pass": bool(ok), "converged": conv, "finish_reason": res.get("finish_reason"),
               "completion_tokens": res.get("completion_tokens"), "prompt_tokens": res.get("prompt_tokens"),
               "wall_s": res.get("wall_s"), "note": note}
        for k in ("cached_tokens_turn3", "cached_turn2", "handoff", "decode_tps", "peak_mem_gb"):
            if res.get(k) is not None: row[k] = res[k]
        rows.append(row); failed += not ok
        print(f"[{name}] {'PASS' if ok else 'FAIL'} conv={conv} finish={row['finish_reason']} "
              f"ctok={row['completion_tokens']} wall={row['wall_s']}s :: {note}", flush=True)
    result = {"status": "pass" if not failed else "fail", "model": a.model, "tag": a.tag, "params": params,
              "base": client.BASE, "when": datetime.now().isoformat(timespec="seconds"), "rows": rows}
    json.dump(result, open(out, "w"), indent=1)
    print(f"{result['status'].upper()} {len(rows) - failed}/{len(rows)} -> {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
