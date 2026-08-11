#!/usr/bin/env python3
"""Prove which model server OpenWebUI's post-response task calls actually hit.

Question under test: OWUI resolves the model for title / tags / follow-up
generation through ``utils/task.py:get_task_model_id``, which gates on the CHAT
model's ``connection_type``:

    if models[chat_model]['connection_type'] == 'local': use TASK_MODEL
    else:                                                use TASK_MODEL_EXTERNAL
    fallback:                                            the CHAT model itself

``routers/openai.py`` defaults ``connection_type`` to ``'external'`` for a
connection with no explicit api_config entry, and openwebui-init only ever sets
TASK_MODEL (never TASK_MODEL_EXTERNAL) -- so the fallback can silently send
every task call to the 27B/35B chat model with thinking enabled instead of the
1.5B on the task port.

This probe answers it by observation, not by reading source: it counts
``Request completed`` lines in BOTH server logs, fires one task call per task
type through OWUI's own endpoints, and reports which log grew.

Usage (stack must be up):
    uv run python benchmark/owui_task_route_probe.py
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

OWUI = os.environ.get("OWUI_URL", "http://localhost:3000")
EMAIL = os.environ.get("OWUI_ADMIN_EMAIL", "admin@a.a")
PASSWORD = os.environ.get("OWUI_ADMIN_PASSWORD", "admin")
TASK_LOG = os.environ.get("TASK_MODEL_LOG_FILE", "logs/task_model.log")
MAIN_LOG = "logs/main_model.log"

# Candidate task-endpoint prefixes; OWUI moved these between versions, so try
# both rather than pinning to one and mis-reporting a 404 as "not routed".
TASK_PREFIXES = ("/api/v1/tasks", "/api/task")
TASK_KINDS = ("title", "tags", "follow_up")


def _req(method, path, token=None, body=None, timeout=600):
    url = path if path.startswith("http") else f"{OWUI}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read()
    return resp.status, (json.loads(raw) if raw else None)


def signin():
    try:
        _, d = _req("POST", "/api/v1/auths/signin", body={"email": EMAIL, "password": PASSWORD})
        return d["token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"signin failed: HTTP {e.code} {e.read()[:200]!r}")


def count_completions(path):
    """Count served requests in an mlx-vlm / mlx-serve log."""
    if not os.path.exists(path):
        return 0
    with open(path, "r", errors="replace") as f:
        return sum(1 for line in f if "Request completed" in line)


def main():
    token = signin()
    print(f"authenticated to {OWUI}\n")

    # --- 1. What does OWUI think the task model is? ---
    _, cfg = _req("GET", "/api/v1/tasks/config", token)
    tm = cfg.get("TASK_MODEL")
    tme = cfg.get("TASK_MODEL_EXTERNAL")
    print("=== task config ===")
    print(f"  TASK_MODEL          = {tm!r}")
    print(f"  TASK_MODEL_EXTERNAL = {tme!r}")
    for k in ("ENABLE_TITLE_GENERATION", "ENABLE_TAGS_GENERATION", "ENABLE_FOLLOW_UP_GENERATION"):
        if k in cfg:
            print(f"  {k} = {cfg[k]}")

    # --- 2. The gate: connection_type per model ---
    _, models = _req("GET", "/api/models", token)
    entries = models.get("data", models) if isinstance(models, dict) else models
    print("\n=== models / connection_type (the gate) ===")
    chat_model = None
    for m in entries:
        mid = m.get("id")
        ct = m.get("connection_type")
        owned = m.get("owned_by")
        print(f"  {mid!r:60s} connection_type={ct!r} owned_by={owned!r}")
        if mid and mid != tm and owned != "arena" and chat_model is None:
            chat_model = mid
    if chat_model is None:
        sys.exit("no non-task chat model found in /api/models")

    ct = next((m.get("connection_type") for m in entries if m.get("id") == chat_model), None)
    predicted = tm if ct == "local" else (tme or chat_model)
    print(f"\n  chat model under test : {chat_model}")
    print(f"  its connection_type   : {ct!r}")
    print(f"  => get_task_model_id predicts: {predicted}")
    print(f"     ({'TASK MODEL' if predicted == tm else 'MISROUTED TO THE CHAT MODEL'})")

    # --- 3. Observe it: fire one task call per kind, count both logs ---
    messages = [
        {"role": "user", "content": "How do I limit asyncio concurrency to N?"},
        {"role": "assistant", "content": "Use an asyncio.Semaphore bounded to N."},
    ]
    print("\n=== observed routing ===")
    print(f"{'kind':10s} {'http':>6s} {'task:8092':>10s} {'main:8000':>10s} {'elapsed':>9s}  verdict")
    for kind in TASK_KINDS:
        before_task, before_main = count_completions(TASK_LOG), count_completions(MAIN_LOG)
        status, err = None, None
        t0 = time.time()
        for prefix in TASK_PREFIXES:
            try:
                status, _ = _req(
                    "POST",
                    f"{prefix}/{kind}/completions",
                    token,
                    body={"model": chat_model, "messages": messages, "chat_id": f"probe-{kind}"},
                )
                break
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                if e.code != 404:
                    break
        elapsed = time.time() - t0
        # mlx-vlm flushes its log after the response; give it a moment.
        time.sleep(1.0)
        d_task = count_completions(TASK_LOG) - before_task
        d_main = count_completions(MAIN_LOG) - before_main
        if d_task and not d_main:
            verdict = "TASK MODEL (:8092)"
        elif d_main and not d_task:
            verdict = "*** MISROUTED to main (:8000) ***"
        elif d_task and d_main:
            verdict = "both grew (ambiguous)"
        else:
            verdict = f"neither grew ({err or 'no request served'})"
        print(f"{kind:10s} {str(status or err):>6s} {d_task:>10d} {d_main:>10d} {elapsed:>8.2f}s  {verdict}")

    print(
        "\nNote: mlx-serve routes :8000 to a worker, so a misrouted call also shows up in\n"
        "~/.mlx-serve/logs and loads/holds the big model. Cross-check elapsed time: the\n"
        "1.5B answers these in ~0.6-1.3s, a thinking 27B/35B in tens of seconds."
    )


if __name__ == "__main__":
    main()
